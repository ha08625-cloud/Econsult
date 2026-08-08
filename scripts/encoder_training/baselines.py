"""Baselines, and the negative control that says whether any of it means anything.

These are the comparison point the whole ticket is judged against. A transformer
that beats majority-class by four points on a dataset TF-IDF already solves is
not evidence about the encoder; it is evidence about how easy the dataset is.

Three baselines, each answering a different question:

* **majority class** -- what a model that has learned nothing scores. Should land
  near the generator's ``null`` share, which is a flag setting and not a
  property of anything.
* **length only** -- multinomial logistic regression on token count and nothing
  else. This is the direct measurable test of the length leak
  `arch_training.md` section 9 argues for and has never measured: fragment
  *count* is controlled across labels, fragment *length* is not. Materially
  above majority means text length is a usable proxy for the label, which is
  library work rather than model work.
* **TF-IDF + logistic regression** -- whether the dataset is keyword-solvable.
  Expected to do well on clear positives, clear negatives and
  ``null_structural`` and badly on the ambiguous sub-classes, which makes its
  *overall* accuracy close to uninformative. The number that matters is the
  ``null_ambiguous`` slice.

**scikit-learn is imported inside the fitting methods, never at module scope.**
CI's unit job installs no ML wheels, so this module has to import cleanly
without them: everything that decides what a number means -- tokenising, the
label permutation, the fold loop, the decision rule -- is then covered on an
ordinary runner, and only the two ``fit`` bodies are not.

**The shuffled-label control permutes the train split only and is evaluated on
the unpermuted test split.** Wiring it the other way is a real trap rather than
a nitpick: at Arm B a 110M-parameter model will memorise permuted train labels
and drive train loss to zero, which is correct behaviour and looks like failure
if train is where you looked. The control is built here so Arm B inherits it
already wired the right way round.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Sequence

from .dataset import CLASS_NAMES, Fold, Split
from .decision import select_margin
from .metrics import Prediction, apply_margin, repredict
from .report import FoldRun, ModelRun

#: Words for the length feature. Deliberately crude and shared with nothing
#: else: this measures length, and any definition of a token that is stable
#: across examples measures it equally well.
TOKEN_RE = re.compile(r"[A-Za-z0-9']+")

N_CLASSES = len(CLASS_NAMES)

#: Per-class scores, in :data:`.dataset.CLASS_NAMES` order.
Scores = tuple[float, ...]


def token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def training_pairs(split: Split, signal: str) -> tuple[list[str], list[int]]:
    """The texts and class indices of every example this signal is labelled on.

    Masked examples are dropped rather than defaulted: an example carrying no
    label for the signal belongs in neither the numerator nor the denominator,
    and the single-signal datasets this ticket generates have none. The filter
    exists so the multi-head case inherits the right behaviour instead of a
    silent stream of ``false``.
    """
    texts: list[str] = []
    classes: list[int] = []
    for example in split.examples:
        if not example.is_labelled(signal):
            continue
        texts.append(example.text)
        classes.append(example.class_for(signal))
    return texts, classes


def permute_classes(classes: Sequence[int], *, seed: int) -> list[int]:
    """Negative control 1: the same labels, attached to the wrong examples.

    A permutation rather than independent redraws, so the class balance is
    exactly preserved and the control differs from the real run in one respect
    only -- whether the label has anything to do with the text.
    """
    shuffled = list(classes)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def _expand(row: Sequence[float], model_classes: Sequence[int]) -> Scores:
    """Map a fitted model's class-ordered probabilities onto all three classes.

    sklearn drops classes absent from the training labels, so a fold that
    happened to contain no ``true`` examples would return two columns. Filling
    the gap with zero is right -- the model genuinely cannot predict it -- and
    doing it explicitly beats an index error somewhere downstream.
    """
    scores = [0.0] * N_CLASSES
    for value, class_index in zip(row, model_classes, strict=True):
        scores[int(class_index)] = float(value)
    return tuple(scores)


class Baseline:
    """A fitted-and-scored model. Subclasses supply :meth:`fit` and :meth:`score`."""

    name = "baseline"
    description = ""

    def fit(self, texts: Sequence[str], classes: Sequence[int]) -> Baseline:
        raise NotImplementedError

    def score(self, texts: Sequence[str]) -> list[Scores]:
        raise NotImplementedError


class MajorityBaseline(Baseline):
    """Always the most common training class. The floor every number sits above.

    Its scores are the training class frequencies, which makes the decision-rule
    machinery well defined on it -- degenerately so, since every example gets the
    same three numbers and no margin can reorder them differently for different
    examples. That degeneracy is the point: it shows what the rule does to a
    model with nothing to say.
    """

    name = "majority_class"
    description = (
        "Always predicts the most common class in its fold's training split. Expected to score "
        "the generator's `null` share, which is a flag setting rather than a property of the "
        "data."
    )

    def __init__(self) -> None:
        self._scores: Scores = tuple(0.0 for _ in range(N_CLASSES))

    def fit(self, texts: Sequence[str], classes: Sequence[int]) -> MajorityBaseline:
        counts = [0] * N_CLASSES
        for class_index in classes:
            counts[class_index] += 1
        total = sum(counts) or 1
        self._scores = tuple(count / total for count in counts)
        return self

    def score(self, texts: Sequence[str]) -> list[Scores]:
        return [self._scores for _ in texts]


class LengthBaseline(Baseline):
    """Multinomial logistic regression on token count, and nothing else.

    One feature by design. A linear model on a single feature can only carve the
    line into monotone regions, so anything it achieves above majority is
    achieved by length alone -- which is exactly the claim being tested. The
    feature is standardised against the training split so the solver's
    conditioning does not depend on how long the sentences happen to be.
    """

    name = "length_only"
    description = (
        "Logistic regression on token count alone. The direct measurable test of the length "
        "leak: anything materially above majority means text length is a usable proxy for the "
        "label, which is a fragment-library problem rather than a model one."
    )

    def __init__(self, *, seed: int = 0, max_iter: int = 1000) -> None:
        self.seed = seed
        self.max_iter = max_iter
        self._mean = 0.0
        self._sd = 1.0
        self._model = None
        self._classes: list[int] = []

    def _features(self, texts: Sequence[str]) -> list[list[float]]:
        return [[(token_count(text) - self._mean) / self._sd] for text in texts]

    def fit(self, texts: Sequence[str], classes: Sequence[int]) -> LengthBaseline:
        from sklearn.linear_model import LogisticRegression

        counts = [token_count(text) for text in texts]
        self._mean = sum(counts) / len(counts)
        variance = sum((count - self._mean) ** 2 for count in counts) / len(counts)
        self._sd = math.sqrt(variance) or 1.0

        self._model = LogisticRegression(max_iter=self.max_iter, random_state=self.seed)
        self._model.fit(self._features(texts), list(classes))
        self._classes = [int(value) for value in self._model.classes_]
        return self

    def score(self, texts: Sequence[str]) -> list[Scores]:
        rows = self._model.predict_proba(self._features(texts))
        return [_expand(row, self._classes) for row in rows]


class TfidfBaseline(Baseline):
    """TF-IDF over word unigrams and bigrams, into logistic regression.

    Tests whether the dataset is keyword-solvable. Bigrams are included because
    several of the hard sub-classes turn on two-word constructions -- "hay fever",
    "hot water", "my daughter" -- and a unigram model that failed on them would
    be failing for an uninteresting reason.
    """

    name = "tfidf_logreg"
    description = (
        "TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is "
        "keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` "
        "slice is the number that matters."
    )

    def __init__(
        self, *, seed: int = 0, max_iter: int = 2000, min_df: int = 2, max_ngram: int = 2
    ) -> None:
        self.seed = seed
        self.max_iter = max_iter
        self.min_df = min_df
        self.max_ngram = max_ngram
        self._vectorizer = None
        self._model = None
        self._classes: list[int] = []

    def fit(self, texts: Sequence[str], classes: Sequence[int]) -> TfidfBaseline:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, self.max_ngram),
            min_df=self.min_df,
            sublinear_tf=True,
        )
        matrix = self._vectorizer.fit_transform(list(texts))
        self._model = LogisticRegression(max_iter=self.max_iter, random_state=self.seed)
        self._model.fit(matrix, list(classes))
        self._classes = [int(value) for value in self._model.classes_]
        return self

    def score(self, texts: Sequence[str]) -> list[Scores]:
        rows = self._model.predict_proba(self._vectorizer.transform(list(texts)))
        return [_expand(row, self._classes) for row in rows]


#: The baselines a run evaluates, in report order.
BASELINES: tuple[Callable[[], Baseline], ...] = (
    MajorityBaseline,
    LengthBaseline,
    TfidfBaseline,
)

#: Which baselines get a shuffled-label control. Majority class is excluded
#: deliberately and the report says so: its prediction *is* the training class
#: prior, and permuting labels leaves that prior identical, so the control would
#: return the same numbers by construction and prove nothing.
CONTROLLED = ("length_only", "tfidf_logreg")


def _predict(
    split: Split, model: Baseline, signal: str, *, margin: float = 0.0
) -> list[Prediction]:
    """Score a split, keeping the per-class scores on every prediction."""
    examples = [example for example in split.examples if example.is_labelled(signal)]
    scored = model.score([example.text for example in examples])
    return [
        Prediction.from_example(example, signal, apply_margin(scores, margin), scores=scores)
        for example, scores in zip(examples, scored, strict=True)
    ]


def run_fold(
    factory: Callable[[], Baseline],
    fold: Fold,
    *,
    signal: str,
    shuffle_seed: int | None = None,
) -> FoldRun:
    """Fit one baseline on one fold and score its test split both ways.

    The order matters and is the whole procedure: fit on train, select the
    margin on **validation**, then score test once under argmax and once under
    the selected margin. Test is touched exactly once, at the end, by a rule
    that was fixed before it was opened.

    ``shuffle_seed`` turns this into negative control 1 by permuting the
    training labels. Validation and test are left alone -- the control has to be
    the same procedure differing in one respect, and it has to be scored against
    the truth.
    """
    texts, classes = training_pairs(fold.train, signal)
    if shuffle_seed is not None:
        classes = permute_classes(classes, seed=shuffle_seed)

    model = factory().fit(texts, classes)

    rule = select_margin(_predict(fold.val, model, signal))
    raw = _predict(fold.test, model, signal)
    return FoldRun.build(
        fold_index=fold.fold_index,
        n_train=len(texts),
        n_val=len(fold.val),
        n_test=len(raw),
        rule=rule,
        raw=raw,
        ruled=repredict(raw, rule.margin, gated_class=rule.gated_class),
    )


def run_baseline(
    factory: Callable[[], Baseline],
    folds: Sequence[Fold],
    *,
    signal: str,
    shuffle_seed: int | None = None,
) -> ModelRun:
    """Run one baseline across every fold, as a single reportable model."""
    prototype = factory()
    control = shuffle_seed is not None
    return ModelRun(
        name=f"{prototype.name}__shuffled" if control else prototype.name,
        kind="negative_control" if control else "baseline",
        description=(
            f"{prototype.description} **Negative control:** trained on permuted training labels "
            f"(seed {shuffle_seed}) and evaluated on the unpermuted test split, where it must "
            "land at chance."
            if control
            else prototype.description
        ),
        folds=tuple(
            run_fold(factory, fold, signal=signal, shuffle_seed=shuffle_seed) for fold in folds
        ),
    )


def run_all(
    folds: Sequence[Fold],
    *,
    signal: str,
    shuffle_seed: int = 7,
    baselines: Sequence[Callable[[], Baseline]] = BASELINES,
    controlled: Sequence[str] = CONTROLLED,
) -> list[ModelRun]:
    """Every baseline, then every shuffled-label control, in report order."""
    runs = [run_baseline(factory, folds, signal=signal) for factory in baselines]
    runs.extend(
        run_baseline(factory, folds, signal=signal, shuffle_seed=shuffle_seed)
        for factory in baselines
        if factory().name in controlled
    )
    return runs


__all__ = [
    "BASELINES",
    "CONTROLLED",
    "Baseline",
    "LengthBaseline",
    "MajorityBaseline",
    "TfidfBaseline",
    "permute_classes",
    "run_all",
    "run_baseline",
    "run_fold",
    "token_count",
    "training_pairs",
]
