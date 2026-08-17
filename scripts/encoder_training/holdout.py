"""The realistic held-out set: loading it, and saying what a number on it is worth.

Standard library only, and the forward pass is **injected** rather than
imported. That is the same tier boundary :mod:`.dataset` and :mod:`.metrics` sit
on, and it exists for the same reason: everything that decides what a number
*means* has to be coverable by CI's unit job on a runner with no GPU and no ML
wheels. This module takes a callable ``(texts) -> {signal: per-class scores}``
and knows nothing about torch.

**What this set is for.** Every other number this package produces is scored on
recombinations of the same fragment libraries the models were trained on --
two or three fragments, one supervised claim plus filler, same register, same
generator. `data/realistic/README.md` puts the question plainly: 92.9% there
could be 55% here and no report currently produced would show it. 67 hand-written
submissions, labelled once and never used to select anything, are the only thing
in this project that speaks to real patient text.

**What it cannot do, and this is the part that gets over-read.** It cannot rank
two models. 67 submissions with no cluster structure give roughly +/-12 points
on one overall figure and +/-25 or worse on a per-signal decisive slice, so it
cannot separate arms, encoders or margins -- that is what the fold-pooled
synthetic test set is for. It is a **validity** instrument, and the failure it
can detect is the large one: a model that scores in the nineties on
recombinations and lands near chance on real text is unmissable here.

Three things the loader is strict about, each because collapsing them would
quietly destroy the distinction the set exists to preserve.

* **A blank cell is not ``null``.** README rule 4 says a signal the labeller
  cannot judge has its key *omitted*; ``null`` means "the text raises the
  territory and does not settle it". Reading this file with
  ``csv.DictReader`` and mapping every cell through ``bool`` would merge the
  two and invent a label, which is the exact failure the label-first design
  exists to prevent. Omitted signals are excluded from both the numerator and
  the denominator, exactly as :mod:`.dataset` excludes a masked signal.
* **The header is validated against the ruleset.** A column for a signal the
  ruleset does not send to the encoder, or a missing column for one it does, is
  a hard error rather than a silently narrower evaluation.
* **The resampling unit is the submission** (README rule 5). There is no
  cluster structure here, so each submission is one independent observation --
  unlike the synthetic sets, where the unit is the fragment cluster. A
  submission contributes up to six cells and they resample together.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .dataset import CLASS_FALSE, CLASS_NAMES, CLASS_NULL, CLASS_TRUE
from .metrics import (
    DEFAULT_ALPHA,
    DEFAULT_RESAMPLES,
    Interval,
    Prediction,
    accuracy,
    apply_margin,
    bootstrap_confusion_ci,
    confusion_matrix,
    macro_f1,
    per_class_metrics,
)

#: The default labels file, and the only one that exists.
DEFAULT_HOLDOUT_PATH = Path("data/realistic/uti1_holdout.labels.tsv")

#: Columns that are not signals.
ID_COLUMN = "submission_id"
TEXT_COLUMN = "text"

#: Cell value -> class index. A cell that is blank after stripping is *omitted*
#: and appears in none of these; see the module docstring.
CELL_CLASSES = {"false": CLASS_FALSE, "true": CLASS_TRUE, "null": CLASS_NULL}

#: Two-sided normal coverage used by :func:`worst_case_half_width`.
Z_95 = 1.959963984540054

#: Reproduced verbatim from `data/realistic/README.md` rather than
#: cross-referenced, and carried into every report that quotes a number from
#: this set. The labeller and the model share an architecture; no amount of
#: resampling would reveal a blind spot they share, so the limitation has to
#: travel with the number rather than sit in a file the reader has not opened.
PROVENANCE_NOTE = (
    "**The labels were proposed by Claude and reviewed by the maintainer.** They were not "
    "produced independently of the models being scored. This is a real limitation and it belongs "
    "in every report that uses this set: the labeller and the model share an architecture and "
    "could in principle share a blind spot, which would inflate the score in a way no amount of "
    "resampling would reveal."
)

#: The other limitation the README asks every report to carry.
VOICE_NOTE = (
    "67 submissions written by one person share that person's voice and that person's idea of "
    "what a patient sounds like. Real submissions vary by age, first language, literacy, how ill "
    "the person feels while typing, and what they think a GP wants to hear. This is a large "
    "improvement on recombinations and it is still not a random sample of patients."
)

#: What the set can and cannot decide, printed beside the numbers rather than
#: under them. The whole failure mode here is a reader taking a per-signal
#: figure at face value, and a caveat printed after the number it qualifies is a
#: caveat nobody reads.
POWER_NOTE = (
    "This set cannot rank two models. Every figure below carries its own `n` and a worst-case "
    "half-width -- the widest a 95% interval on a proportion can be at that `n` -- and on the "
    "per-signal decisive slices that is +/-20 points or worse. It is a validity instrument: it "
    "can show that a number in the nineties on recombinations is really 55% on real text, which "
    "is the question that matters most and which nothing else here answers. It cannot separate "
    "two arms, and a report that uses it to is misreading it."
)

#: Signals with no `false` examples anywhere in the set, so a model that never
#: predicts `false` is not penalised on them. Derived at load time rather than
#: hard-coded, but the *reason* is fixed: the largest error family in the
#: synthetic evaluation was explicit denial, and where a signal has no denials
#: here, this set measures nothing about it.
RECALL_ONLY_NOTE = (
    "no `false` examples in this set, so its number is very nearly a recall-only measurement: "
    "nothing here tests whether an explicit denial is read correctly, which was the largest "
    "error family in the synthetic evaluation"
)


class HoldoutError(ValueError):
    """Raised when the holdout set, or a scoring of it, cannot be trusted."""


@dataclass(frozen=True)
class Submission:
    """One held-out submission: its text, and the signals a labeller could judge.

    ``classes`` holds only the judged signals. A signal absent from it was left
    blank by the labeller and is excluded from scoring entirely -- it is neither
    a ``null`` the model should have found nor a mistake it made.
    """

    submission_id: str
    text: str
    classes: Mapping[str, int]
    omitted: tuple[str, ...]

    def is_judged(self, signal: str) -> bool:
        return signal in self.classes


@dataclass(frozen=True)
class HoldoutSet:
    """The 67 submissions, the signals they were labelled for, and where they came from."""

    path: Path
    signals: tuple[str, ...]
    submissions: tuple[Submission, ...]

    def __len__(self) -> int:
        return len(self.submissions)

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(submission.text for submission in self.submissions)

    def judged(self, signal: str) -> tuple[Submission, ...]:
        """The submissions a labeller could judge this signal on."""
        return tuple(submission for submission in self.submissions if submission.is_judged(signal))

    def distribution(self, signal: str) -> dict[str, int]:
        """``true``/``false``/``null`` counts, plus how many cells were omitted.

        The counts that bound anything are ``true`` and ``false``: a ``null``
        example is one the majority-class baseline scores perfectly.
        """
        counts = {name: 0 for name in CLASS_NAMES}
        omitted = 0
        for submission in self.submissions:
            if submission.is_judged(signal):
                counts[CLASS_NAMES[submission.classes[signal]]] += 1
            else:
                omitted += 1
        return {**counts, "omitted": omitted, "decisive": counts["true"] + counts["false"]}


def encoder_signals(ruleset_path: Path | str) -> tuple[str, ...]:
    """The ruleset's ``send_to_encoder`` signals, in declaration order.

    Read straight from the JSON rather than through ``app/``'s loader, for the
    reason :mod:`.ruleset_hash` gives: offline tooling must not couple to
    runtime wiring, and an offline tool recording what it scored should not be
    the thing that decides whether a ruleset is deployable.
    """
    ruleset_path = Path(ruleset_path)
    if not ruleset_path.is_file():
        raise HoldoutError(f"ruleset not found: {ruleset_path}")
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    questions = ruleset.get("questions")
    if not isinstance(questions, list):
        raise HoldoutError(f"ruleset {ruleset_path} has no 'questions' list")
    return tuple(
        question["answer_key"]
        for question in questions
        if isinstance(question, dict)
        and question.get("send_to_encoder") is True
        and isinstance(question.get("answer_key"), str)
    )


def _class_for_cell(value: str, *, submission_id: str, signal: str) -> int | None:
    """Map one TSV cell to a class index, or ``None`` for an omitted signal."""
    stripped = value.strip()
    if not stripped:
        return None
    if stripped not in CELL_CLASSES:
        raise HoldoutError(
            f"submission {submission_id!r} has {stripped!r} for {signal!r}; a cell must be "
            "'true', 'false', 'null', or blank for a signal the labeller could not judge. "
            "Blank and 'null' are different claims and this loader will not merge them"
        )
    return CELL_CLASSES[stripped]


def load_holdout(path: Path | str = DEFAULT_HOLDOUT_PATH, *, signals: Sequence[str]) -> HoldoutSet:
    """Load and validate the labels TSV against the ruleset's encoder signals.

    ``signals`` is the ruleset's ``send_to_encoder`` set -- every one of them
    must be a column and no other signal column may appear. A signal with no
    trained head is simply not scored later; it is still required here, because
    a labels file that has quietly lost a column is a labels file whose
    distribution table no longer describes it.
    """
    path = Path(path)
    if not path.is_file():
        raise HoldoutError(
            f"holdout labels not found: {path}. Pass --no-holdout to run without the real-text "
            "check, and record in the report that it was skipped"
        )

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as error:
            raise HoldoutError(f"{path} is empty") from error
        rows = [row for row in reader if any(cell.strip() for cell in row)]

    for required in (ID_COLUMN, TEXT_COLUMN):
        if required not in header:
            raise HoldoutError(f"{path} has no {required!r} column; its header is {header}")

    columns = [name for name in header if name not in (ID_COLUMN, TEXT_COLUMN)]
    expected = tuple(signals)
    missing = [signal for signal in expected if signal not in columns]
    unexpected = [name for name in columns if name not in expected]
    if missing or unexpected:
        raise HoldoutError(
            f"{path} does not match the ruleset's send_to_encoder signals. "
            f"missing: {missing or 'none'}; unexpected: {unexpected or 'none'}. A holdout scored "
            "against a different signal set than the ruleset declares is scoring something nobody "
            "asked for"
        )

    index = {name: position for position, name in enumerate(header)}
    submissions: list[Submission] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, start=2):
        if len(row) != len(header):
            raise HoldoutError(
                f"{path}:{number} has {len(row)} fields against the header's {len(header)}"
            )
        submission_id = row[index[ID_COLUMN]].strip()
        if not submission_id:
            raise HoldoutError(f"{path}:{number} has no {ID_COLUMN}")
        if submission_id in seen:
            raise HoldoutError(
                f"{path}:{number} repeats submission id {submission_id!r}; ids are assigned by "
                "line order in the source file and must be unique"
            )
        seen.add(submission_id)

        text = row[index[TEXT_COLUMN]]
        if not text.strip():
            raise HoldoutError(f"{path}:{number} ({submission_id}) has no text")

        classes: dict[str, int] = {}
        omitted: list[str] = []
        for signal in expected:
            value = _class_for_cell(row[index[signal]], submission_id=submission_id, signal=signal)
            if value is None:
                omitted.append(signal)
            else:
                classes[signal] = value
        submissions.append(
            Submission(
                submission_id=submission_id,
                text=text,
                classes=classes,
                omitted=tuple(omitted),
            )
        )

    if not submissions:
        raise HoldoutError(f"{path} holds no submissions")
    return HoldoutSet(path=path, signals=expected, submissions=tuple(submissions))


def worst_case_half_width(n: int, *, z: float = Z_95) -> float | None:
    """The widest a 95% interval on a proportion can be at this ``n``.

    ``z * sqrt(0.25 / n)``, the normal half-width at p = 0.5. Deliberately the
    *worst* case rather than the one implied by the observed proportion: this
    number is printed beside a score so a reader can see what the sample can
    support before reading the score, and a half-width computed from the score
    itself narrows exactly where the score is highest.
    """
    if n < 1:
        return None
    return z * math.sqrt(0.25 / n)


def _interval_dict(interval: Interval) -> dict:
    return {
        "point": interval.point,
        "low": interval.low,
        "high": interval.high,
        "effective_n": interval.effective_n,
        "resamples_used": interval.resamples_used,
    }


def _slice_block(
    predictions: Sequence[Prediction],
    *,
    resamples: int,
    seed: int,
    alpha: float,
) -> dict:
    """Accuracy over one slice, with its interval and the power it carries.

    ``effective_n`` here is the number of distinct *submissions* behind the
    slice, not the number of cells: a submission contributing six cells is one
    observation, and the bootstrap resamples it whole.
    """
    matrix = confusion_matrix(predictions)
    interval = bootstrap_confusion_ci(
        predictions, accuracy, resamples=resamples, seed=seed, alpha=alpha
    )
    return {
        "n_cells": len(predictions),
        "n_submissions": interval.effective_n,
        "confusion": [list(row) for row in matrix],
        "accuracy": _interval_dict(interval),
        "macro_f1": macro_f1(matrix),
        "worst_case_half_width": worst_case_half_width(interval.effective_n),
    }


def _decisive(predictions: Sequence[Prediction]) -> list[Prediction]:
    """The cells whose truth is ``true`` or ``false``.

    The README calls this the decisive column and says it is the one that
    bounds anything: a ``null`` cell is one the majority-class baseline scores
    perfectly, so a model that answers "no information" everywhere posts a high
    ``all`` figure and nothing at all here.
    """
    return [prediction for prediction in predictions if prediction.truth != CLASS_NULL]


def _margin_for(margin: float | Mapping[str, float], signal: str) -> float:
    """Resolve one signal's margin, whether the caller passed one for all or one each.

    A plain ``float`` is the single-model shape every command used before joint
    training existed, and stays the default so nothing here changes for them. A
    mapping is what a joint model needs: each head's margin was selected
    independently on its own validation split (task 3 instruction 3 -- no
    cross-head trade), so there is no single number to apply to every column.
    """
    if isinstance(margin, Mapping):
        if signal not in margin:
            raise HoldoutError(
                f"no margin given for {signal!r}; every signal being scored needs its own "
                f"already-selected margin, and {list(margin)} did not include it"
            )
        return margin[signal]
    return margin


def build_predictions(
    holdout: HoldoutSet,
    scores: Mapping[str, Sequence[Sequence[float]]],
    *,
    signals: Sequence[str],
    margin: float | Mapping[str, float] = 0.0,
    gated_class: int = CLASS_TRUE,
) -> dict[str, list[Prediction]]:
    """Turn one forward pass into per-signal predictions, keyed by submission.

    ``scores`` holds one row per submission per signal, in the order
    :attr:`HoldoutSet.texts` returned them. Omitted cells are dropped here and
    nowhere else, so every downstream count is over judged cells only.

    ``margin`` is either one number applied to every signal (a single-head run)
    or a signal -> margin mapping (a joint run, where each head's margin was
    chosen independently and there is no one number that means "the margin").
    """
    per_signal: dict[str, list[Prediction]] = {}
    for signal in signals:
        rows = scores.get(signal)
        if rows is None:
            raise HoldoutError(
                f"the scorer returned nothing for {signal!r}; it was asked for "
                f"{list(signals)} and answered {sorted(scores)}"
            )
        if len(rows) != len(holdout):
            raise HoldoutError(
                f"the scorer returned {len(rows)} rows for {signal!r} against "
                f"{len(holdout)} submissions"
            )
        resolved_margin = _margin_for(margin, signal)
        predictions: list[Prediction] = []
        for submission, row in zip(holdout.submissions, rows, strict=True):
            if not submission.is_judged(signal):
                continue
            values = tuple(float(value) for value in row)
            predictions.append(
                Prediction(
                    # Unique per cell, so two signals' cells for one submission
                    # cannot collide; the resampling unit below is the
                    # submission, which is what makes them move together.
                    example_id=f"{submission.submission_id}:{signal}",
                    truth=submission.classes[signal],
                    predicted=apply_margin(values, resolved_margin, gated_class=gated_class),
                    unit=submission.submission_id,
                    scores=values,
                )
            )
        per_signal[signal] = predictions
    return per_signal


def score_holdout(
    holdout: HoldoutSet,
    scorer: Callable[[Sequence[str]], Mapping[str, Sequence[Sequence[float]]]],
    *,
    signals: Sequence[str],
    margin: float | Mapping[str, float] = 0.0,
    gated_class: int = CLASS_TRUE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
) -> dict:
    """Score one model against the holdout, under a margin chosen elsewhere.

    **This function selects nothing.** ``margin`` arrives already chosen on the
    fold's own validation split, and the caller is expected to have scored the
    synthetic test set first -- README rule 2 says this set never selects
    anything, and the way to make that a structural property rather than a
    promise is to give it nothing to select with.

    ``margin`` is one number for a single-head model, or a signal -> margin
    mapping for a joint one: each head's margin is selected independently
    (task 3 instruction 3), so a joint model has no single margin to quote.

    ``signals`` is the set of heads the model actually has. A ruleset signal
    with no head is listed in the result and not scored; a head whose signal the
    holdout does not label is an error, because it would be silently dropped.
    """
    requested = tuple(signals)
    unknown = [signal for signal in requested if signal not in holdout.signals]
    if unknown:
        raise HoldoutError(
            f"asked to score {unknown} against {holdout.path}, which labels {list(holdout.signals)}"
        )

    scores = scorer(holdout.texts)
    per_signal = build_predictions(
        holdout, scores, signals=requested, margin=margin, gated_class=gated_class
    )

    by_signal: list[dict] = []
    pooled: list[Prediction] = []
    for signal in requested:
        predictions = per_signal[signal]
        pooled.extend(predictions)
        distribution = holdout.distribution(signal)
        matrix = confusion_matrix(predictions)
        entry = {
            "signal": signal,
            "margin": _margin_for(margin, signal),
            "distribution": distribution,
            "all": _slice_block(predictions, resamples=resamples, seed=seed, alpha=alpha),
            "decisive": _slice_block(
                _decisive(predictions), resamples=resamples, seed=seed, alpha=alpha
            ),
            "per_class": {
                name: {
                    "support": metrics.support,
                    "predicted": metrics.predicted,
                    "recall": metrics.recall,
                    "precision": metrics.precision,
                }
                for name, metrics in per_class_metrics(matrix).items()
            },
            "null_to_true": {
                "count": matrix[CLASS_NULL][CLASS_TRUE],
                "null_support": sum(matrix[CLASS_NULL]),
            },
        }
        if not distribution["false"]:
            entry["caveat"] = RECALL_ONLY_NOTE
        by_signal.append(entry)

    return {
        "path": str(holdout.path),
        "n_submissions": len(holdout),
        "signals_scored": list(requested),
        "signals_not_scored": [signal for signal in holdout.signals if signal not in requested],
        "margin": margin,
        "selected_nothing": (
            "scored after the margin was selected on validation and after the synthetic test "
            "split was scored. This set selects nothing (README rule 2), and the call order is "
            "what makes that structural rather than a promise"
        ),
        "resampling_unit": "the submission (README rule 5); there is no cluster structure here",
        "bootstrap": {"resamples": resamples, "seed": seed, "alpha": alpha},
        "overall": _slice_block(pooled, resamples=resamples, seed=seed, alpha=alpha),
        "decisive": _slice_block(_decisive(pooled), resamples=resamples, seed=seed, alpha=alpha),
        "by_signal": by_signal,
        "provenance": PROVENANCE_NOTE,
        "voice": VOICE_NOTE,
        "power": POWER_NOTE,
    }


__all__ = [
    "CELL_CLASSES",
    "DEFAULT_HOLDOUT_PATH",
    "POWER_NOTE",
    "PROVENANCE_NOTE",
    "RECALL_ONLY_NOTE",
    "VOICE_NOTE",
    "HoldoutError",
    "HoldoutSet",
    "Submission",
    "build_predictions",
    "encoder_signals",
    "load_holdout",
    "score_holdout",
    "worst_case_half_width",
]
