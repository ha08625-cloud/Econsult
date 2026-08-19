"""Reading a generated dataset split, and the provenance that makes it readable.

Standard library only, deliberately. Everything that decides what a number
*means* lives here and in :mod:`.metrics`; torch lives strictly downstream. That
split is what lets CI's unit job cover every line of the load-bearing logic on a
runner with no GPU and no ML wheels.

Two files are opened per split and no others: the JSONL, and the
``.stats.json`` sidecar next to it. In particular the fragment libraries and
``manifest.json`` are **never** re-read at training time. They are the obvious
place to get cluster membership from, and using them would fail silently -- a
library edited after generation would regroup the clusters, narrowing every
confidence interval with nothing raised anywhere. The sidecar's ``fragments``
block is a snapshot taken at generation time and cannot drift from the dataset
it labels. A sidecar without that block is a hard error, never a fallback to
example-level counting: that fallback would report an effective sample size
many times too large, which is the one failure this whole package exists to
rule out.

**Classes are ``0``/``1``/``2`` for ``false``/``true``/``null``, and every
signal carries a mask.** A *missing* signal key means "this dataset says nothing
about that signal, exclude it from the loss"; an explicit ``null`` means "train
towards the null class". Conflating the two teaches every head to answer "not
mentioned" on every other head's data, and it is invisible until the model is
mysteriously bad. Masked positions hold :data:`MASKED_CLASS` (``-1``) rather
than a real class index, so a caller that forgets the mask gets a loud failure
from torch's ``ignore_index`` handling instead of a silent stream of ``false``
labels.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Class indices. Ordered ``false``/``true``/``null`` so that the two decisive
#: classes keep the 0/1 positions a binary head would have used.
CLASS_FALSE = 0
CLASS_TRUE = 1
CLASS_NULL = 2

#: Class index -> name, and the canonical ordering for every confusion matrix.
CLASS_NAMES = ("false", "true", "null")

#: Filled in where a signal has no label for an example. Negative on purpose:
#: it is torch's conventional ``ignore_index``, and unlike ``0`` it cannot be
#: mistaken for a real class by a caller who drops the mask.
MASKED_CLASS = -1

#: ``fragment_type`` of a library that carries no signal. The one type this
#: module needs to know by name, and it is read from the sidecar rather than
#: pattern-matched from library names -- ``fever_true`` and ``tangents`` look
#: equally like filler to a regex.
FILLER_TYPE = "filler"

#: The resampling unit shared by every structural null. A structural null holds
#: no decisive fragment at all: it is filler recombination, carrying the single
#: idea "no signal language anywhere". Giving each one its own unit would let
#: thousands of recombinations of a handful of filler sentences count as
#: thousands of independent observations, which is exactly the inflation
#: :mod:`.metrics` exists to prevent. The cost is the opposite bias -- one unit
#: holding a large share of a mixed slice's examples widens that slice's
#: interval -- so slices are reported separately rather than pooled blindly.
STRUCTURAL_NULL_UNIT = "__structural_null__"

#: Sidecar keys required before a split may be read. ``folds``/``fold_index``
#: are legitimately ``null`` in default 70/15/15 mode, but the *keys* must be
#: present: a sidecar that never recorded its fold configuration cannot say
#: which clusters its ``test`` split holds, and is therefore uninterpretable.
REQUIRED_STATS_KEYS = (
    "generator_version",
    "signal",
    "split",
    "folds",
    "fold_index",
    "split_salt",
    "fragments",
)

#: Sidecar fields required of every entry in the ``fragments`` block.
REQUIRED_FRAGMENT_FIELDS = ("library", "cluster_key", "fragment_type", "split")

#: The generator's label modes. ``null`` splits into two structurally distinct
#: kinds, and they are never merged here: a structural null is trivially easy
#: and an ambiguous null is the hard case the libraries exist for.
LABEL_MODES = ("true", "false", "null_structural", "null_ambiguous")

#: Split names, in band order.
SPLITS = ("train", "val", "test")

#: Filename convention for a generated fold, shared by the generator wrapper
#: that writes them and everything that reads them back. A convention rather
#: than a manifest so that a directory of datasets is self-describing: the fold
#: index is the one piece of provenance a reader needs *before* opening the
#: sidecar, because it is what says which of K files to open at all.
FOLD_FILENAME = "{signal}.fold{fold_index}.{split}.jsonl"


class DatasetError(ValueError):
    """Raised when a dataset, or its sidecar, cannot be trusted as read."""


@dataclass(frozen=True)
class FragmentInfo:
    """One fragment's provenance, as recorded in the sidecar at generation time."""

    fragment_id: str
    library: str
    cluster_key: str
    fragment_type: str
    split: str
    signal_key: str | None = None
    subclass: str | None = None

    @property
    def is_filler(self) -> bool:
        return self.fragment_type == FILLER_TYPE


@dataclass(frozen=True)
class Example:
    """One training example, with its label vector and its provenance resolved."""

    example_id: str
    split: str
    text: str
    label_mode: str
    fragment_ids: tuple[str, ...]
    #: signal -> class index, :data:`MASKED_CLASS` where the signal is unlabelled.
    classes: Mapping[str, int]
    #: signal -> whether this example contributes to that signal's loss.
    mask: Mapping[str, bool]
    #: The one non-filler fragment, or ``None`` for a structural null.
    decisive: FragmentInfo | None
    #: signal -> the id this example had in *that signal's own* dataset
    #: (``merge.py``'s ``meta.source_ids``), or ``None`` on a tree that was never
    #: merged. ``None`` here, not an empty mapping, is what lets :meth:`id_for`
    #: fall back to ``example_id`` unconditionally on an unmerged tree.
    source_ids: Mapping[str, str] | None = None

    @property
    def library(self) -> str | None:
        """The decisive fragment's library -- the unit slicing is done in (DD6)."""
        return None if self.decisive is None else self.decisive.library

    @property
    def subclass(self) -> str | None:
        """``hedged``, ``metaphor``, ... where the manifest sets one, else ``None``."""
        return None if self.decisive is None else self.decisive.subclass

    @property
    def fragment_id(self) -> str | None:
        """The decisive fragment's id -- the unit of the DD7 per-fragment error table."""
        return None if self.decisive is None else self.decisive.fragment_id

    @property
    def resampling_unit(self) -> str:
        """The cluster this example resamples with (DD5).

        The decisive fragment's ``cluster_key``, which groups the hand-tagged
        ``[c01]`` siblings the generator always keeps in the same split. Falls
        back to the fragment id if a fragment somehow carries no cluster tag,
        and structural nulls share :data:`STRUCTURAL_NULL_UNIT`.
        """
        if self.decisive is None:
            return STRUCTURAL_NULL_UNIT
        return self.decisive.cluster_key or self.decisive.fragment_id

    def class_for(self, signal: str) -> int:
        return self.classes.get(signal, MASKED_CLASS)

    def is_labelled(self, signal: str) -> bool:
        return self.mask.get(signal, False)

    def id_for(self, signal: str) -> str:
        """This example's id in ``signal``'s own dataset (merge.py DD4).

        On an unmerged tree ``source_ids`` is ``None`` and this is just
        ``example_id`` -- which is what keeps a single-signal run's predictions
        identical to a run made before the merge existed. On a merged tree a
        masked signal has no entry, and asking for one is a caller error: it
        means scoring a signal on an example that was never reachable for it,
        which should have been filtered out by ``is_labelled`` already.
        """
        if self.source_ids is None:
            return self.example_id
        try:
            return self.source_ids[signal]
        except KeyError as error:
            raise DatasetError(
                f"example {self.example_id!r} has no source id for {signal!r}; it is masked for "
                "that signal and must not be reachable when scoring it"
            ) from error


@dataclass(frozen=True)
class Split:
    """One split's examples plus the sidecar that describes them."""

    name: str
    path: Path
    examples: tuple[Example, ...]
    fragments: Mapping[str, FragmentInfo]
    stats: Mapping[str, object]
    signals: tuple[str, ...]

    @property
    def generator_version(self) -> object:
        return self.stats["generator_version"]

    @property
    def signal(self) -> object:
        return self.stats["signal"]

    @property
    def folds(self) -> object:
        return self.stats["folds"]

    @property
    def fold_index(self) -> object:
        return self.stats["fold_index"]

    @property
    def split_salt(self) -> object:
        return self.stats["split_salt"]

    @property
    def fold_config(self) -> tuple[object, object, object]:
        """The triple without which ``test`` does not name a definite set of clusters."""
        return (self.folds, self.fold_index, self.split_salt)

    def __len__(self) -> int:
        return len(self.examples)


@dataclass(frozen=True)
class Fold:
    """The three splits of one fold, cross-validated against each other."""

    train: Split
    val: Split
    test: Split

    @property
    def splits(self) -> tuple[Split, Split, Split]:
        return (self.train, self.val, self.test)

    @property
    def signals(self) -> tuple[str, ...]:
        return self.train.signals

    @property
    def fold_config(self) -> tuple[object, object, object]:
        return self.train.fold_config

    @property
    def folds(self) -> object:
        return self.train.folds

    @property
    def fold_index(self) -> object:
        return self.train.fold_index


def sidecar_path(jsonl_path: Path | str) -> Path:
    """Return the ``.stats.json`` path the generator writes beside ``jsonl_path``."""
    jsonl_path = Path(jsonl_path)
    return jsonl_path.parent / (jsonl_path.name + ".stats.json")


def label_vector(example: Example, signals: Sequence[str]) -> list[int]:
    """Class indices in ``signals`` order, :data:`MASKED_CLASS` where unlabelled."""
    return [example.class_for(signal) for signal in signals]


def mask_vector(example: Example, signals: Sequence[str]) -> list[bool]:
    """Loss mask in ``signals`` order. ``False`` means "this head saw no label"."""
    return [example.is_labelled(signal) for signal in signals]


def _class_for_label(value: object, *, example_id: str, signal: str) -> int:
    """Map a JSON label value to a class index.

    ``is True``/``is False`` rather than truthiness: ``isinstance(True, int)``
    holds in Python, so a numeric label would otherwise slip through as a
    Boolean and land in the wrong class.
    """
    if value is None:
        return CLASS_NULL
    if value is True:
        return CLASS_TRUE
    if value is False:
        return CLASS_FALSE
    raise DatasetError(
        f"example {example_id!r} has a non-Boolean label for {signal!r}: {value!r}; "
        "labels must be true, false or null"
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        raise DatasetError(f"dataset not found: {path}")

    records: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise DatasetError(f"{path}:{number} is not valid JSON: {error}") from error
            if not isinstance(record, dict):
                raise DatasetError(f"{path}:{number} is not a JSON object")
            records.append(record)

    if not records:
        raise DatasetError(f"{path} holds no examples")
    return records


def _read_stats(path: Path) -> dict:
    stats_path = sidecar_path(path)
    if not stats_path.is_file():
        raise DatasetError(
            f"no stats sidecar beside {path}: expected {stats_path}. The dataset alone does "
            "not say which fragments are the same idea, so it cannot be evaluated honestly"
        )
    try:
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DatasetError(f"{stats_path} is not valid JSON: {error}") from error
    if not isinstance(stats, dict):
        raise DatasetError(f"{stats_path} is not a JSON object")

    missing = [key for key in REQUIRED_STATS_KEYS if key not in stats]
    if missing:
        raise DatasetError(
            f"{stats_path} is missing required keys: {', '.join(missing)}. A sidecar written "
            "before the fragment-provenance block existed cannot support cluster-level "
            "evaluation, and counting examples instead would report an effective sample size "
            "many times too large; regenerate the dataset rather than reading it"
        )
    return stats


def _fragment_index(stats: Mapping[str, object], stats_path: Path) -> dict[str, FragmentInfo]:
    """Build the fragment index from the sidecar's provenance block."""
    block = stats["fragments"]
    if not isinstance(block, dict) or not block:
        raise DatasetError(
            f"{stats_path} has an empty or malformed 'fragments' block; cluster membership and "
            "library provenance both come from it and neither is recoverable from the JSONL"
        )

    index: dict[str, FragmentInfo] = {}
    for fragment_id, entry in block.items():
        if not isinstance(entry, dict):
            raise DatasetError(f"{stats_path}: fragment {fragment_id!r} is not a JSON object")
        missing = [field for field in REQUIRED_FRAGMENT_FIELDS if field not in entry]
        if missing:
            raise DatasetError(
                f"{stats_path}: fragment {fragment_id!r} is missing {', '.join(missing)}"
            )
        index[fragment_id] = FragmentInfo(
            fragment_id=fragment_id,
            library=entry["library"],
            cluster_key=entry["cluster_key"],
            fragment_type=entry["fragment_type"],
            split=entry["split"],
            signal_key=entry.get("signal_key"),
            subclass=entry.get("subclass"),
        )
    return index


def _decisive_fragment(
    fragment_ids: Sequence[str],
    fragments: Mapping[str, FragmentInfo],
    *,
    example_id: str,
    label_mode: str,
    label_keys: Collection[str],
    path: Path,
) -> FragmentInfo | None:
    """Return the one fragment decisive **for this example's own signal**, or ``None``.

    Filler-ness is read from the sidecar's ``fragment_type``, never inferred
    from the library name (DD6). The generator's rule is exactly one decisive
    fragment per example, none for a structural null; both directions are
    checked because a violation would silently mislabel every slice the
    fragment appears in.

    **"Decisive" has always meant decisive for the signal being supervised**, and
    the companion draw is what made the difference visible. Above
    ``--companion-share 0`` a non-decisive slot may hold another signal's
    clinical language, which is non-filler and says nothing about this example's
    label -- the whole point of it. So the test is the fragment's ``signal_key``
    against the keys the example actually carries a label for, rather than
    filler-ness alone. Before companions the two were the same test, because the
    only non-filler fragment an example could hold was its own.
    """
    held = [fragments[fragment_id] for fragment_id in fragment_ids]
    decisive = [
        fragment
        for fragment in held
        if not fragment.is_filler and fragment.signal_key in label_keys
    ]

    if len(decisive) > 1:
        names = ", ".join(fragment.fragment_id for fragment in decisive)
        raise DatasetError(
            f"{path}: example {example_id!r} holds {len(decisive)} fragments decisive for the "
            f"signal(s) it is labelled for ({names}); exactly one is the generator's invariant, "
            "and two would make its label ambiguous. A dataset from --emit-signals all lands "
            "here by design: it carries a key for every signal its fragments jointly decide, so "
            "several fragments are decisive at once and no single-decisive slice describes it"
        )

    if label_mode in LABEL_MODES:
        structural = label_mode == "null_structural"
        if structural and decisive:
            raise DatasetError(
                f"{path}: example {example_id!r} is a structural null but holds decisive "
                f"fragment {decisive[0].fragment_id!r}"
            )
        if not structural and not decisive:
            raise DatasetError(
                f"{path}: example {example_id!r} has label mode {label_mode!r} but holds no "
                "decisive fragment"
            )

    return decisive[0] if decisive else None


def _build_example(
    record: Mapping[str, object],
    fragments: Mapping[str, FragmentInfo],
    *,
    signals: Sequence[str],
    split_name: str,
    path: Path,
) -> Example:
    example_id = record.get("example_id")
    if not isinstance(example_id, str) or not example_id:
        raise DatasetError(f"{path}: an example has no 'example_id'")

    split = record.get("split")
    if split != split_name:
        raise DatasetError(
            f"{path}: example {example_id!r} is labelled split {split!r}, but its sidecar "
            f"describes split {split_name!r}"
        )

    labels = record.get("labels")
    if not isinstance(labels, dict):
        raise DatasetError(f"{path}: example {example_id!r} has no 'labels' object")

    meta = record.get("meta")
    if not isinstance(meta, dict):
        raise DatasetError(f"{path}: example {example_id!r} has no 'meta' object")

    raw_ids = meta.get("fragment_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise DatasetError(f"{path}: example {example_id!r} has no 'meta.fragment_ids'")

    unknown = [fragment_id for fragment_id in raw_ids if fragment_id not in fragments]
    if unknown:
        raise DatasetError(
            f"{path}: example {example_id!r} cites fragments absent from the sidecar's "
            f"provenance block: {', '.join(map(str, unknown))}"
        )
    foreign = [fragment_id for fragment_id in raw_ids if fragments[fragment_id].split != split_name]
    if foreign:
        raise DatasetError(
            f"{path}: example {example_id!r} in split {split_name!r} draws on fragments the "
            f"sidecar assigns elsewhere: {', '.join(map(str, foreign))}"
        )

    label_mode = meta.get("label_mode")
    if not isinstance(label_mode, str):
        raise DatasetError(f"{path}: example {example_id!r} has no 'meta.label_mode'")

    # Missing key -> masked; explicit null -> the null class. See the module
    # docstring: these two are the mistake that stays invisible longest.
    classes = {signal: MASKED_CLASS for signal in signals}
    mask = {signal: False for signal in signals}
    for signal, value in labels.items():
        classes[signal] = _class_for_label(value, example_id=example_id, signal=signal)
        mask[signal] = True

    text = record.get("text")
    if not isinstance(text, str):
        raise DatasetError(f"{path}: example {example_id!r} has no 'text'")

    raw_source_ids = meta.get("source_ids")
    source_ids: dict[str, str] | None = None
    if raw_source_ids is not None:
        if not isinstance(raw_source_ids, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_source_ids.items()
        ):
            raise DatasetError(
                f"{path}: example {example_id!r} has a malformed 'meta.source_ids'; expected a "
                "signal -> id mapping of strings"
            )
        source_ids = dict(raw_source_ids)

    return Example(
        example_id=example_id,
        split=split_name,
        text=text,
        label_mode=label_mode,
        fragment_ids=tuple(raw_ids),
        classes=classes,
        mask=mask,
        decisive=_decisive_fragment(
            raw_ids,
            fragments,
            example_id=example_id,
            label_mode=label_mode,
            # The example's own keys, not the run's head set: a merged tree's
            # dysuria example is masked on fever, and the fever companion in it
            # is decisive for nothing anybody is scoring.
            label_keys=frozenset(labels),
            path=path,
        ),
        source_ids=source_ids,
    )


def _signals_in(records: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    """The union of label keys, sorted. The head set a caller has data for."""
    signals: set[str] = set()
    for record in records:
        labels = record.get("labels")
        if isinstance(labels, dict):
            signals.update(labels)
    return tuple(sorted(signals))


def load_split(
    path: Path | str, *, signals: Sequence[str] | None = None, expect_split: str | None = None
) -> Split:
    """Load one split's JSONL together with its stats sidecar.

    ``signals`` pins the head set. Pass it whenever more than one split is being
    read: a signal that happens to be absent from one file's examples would
    otherwise produce label vectors of different widths per split. Left unset,
    it is the union of the label keys actually present.

    ``expect_split`` asserts which split this is meant to be, so a mis-ordered
    argument fails here rather than as an inexplicable score later.
    """
    path = Path(path)
    stats = _read_stats(path)
    stats_path = sidecar_path(path)

    split_name = stats["split"]
    if not isinstance(split_name, str) or split_name not in SPLITS:
        raise DatasetError(f"{stats_path} records split {split_name!r}, expected one of {SPLITS}")
    if expect_split is not None and split_name != expect_split:
        raise DatasetError(f"{path} is split {split_name!r} but was loaded as {expect_split!r}")

    fragments = _fragment_index(stats, stats_path)
    records = _read_jsonl(path)
    resolved = tuple(signals) if signals is not None else _signals_in(records)
    if not resolved:
        raise DatasetError(f"{path} has no labelled signals")

    examples = tuple(
        _build_example(record, fragments, signals=resolved, split_name=split_name, path=path)
        for record in records
    )
    return Split(
        name=split_name,
        path=path,
        examples=examples,
        fragments=fragments,
        stats=stats,
        signals=resolved,
    )


def _check_fold_agreement(splits: Sequence[Split]) -> None:
    """Reject three splits that did not come from one generator run.

    Three splits from two generator versions, or from two fold configurations,
    produce a result nobody can interpret and nothing else would flag: the files
    load, the training runs, and ``test`` quietly names a different set of
    clusters from the one ``train`` was held out against.
    """
    for field in ("generator_version", "signal", "folds", "fold_index", "split_salt"):
        values = {split.name: split.stats[field] for split in splits}
        distinct = {json.dumps(value, sort_keys=True) for value in values.values()}
        if len(distinct) > 1:
            rendered = ", ".join(f"{name}={value!r}" for name, value in values.items())
            raise DatasetError(
                f"the splits of this fold disagree on {field!r}: {rendered}. They were not "
                "generated by one run, so no number derived from them is interpretable"
            )


def _check_disjoint(splits: Sequence[Split]) -> None:
    """Assert no fragment, and no cluster, appears in two splits of one fold.

    The generator guarantees this and its own tests cover it. It is asserted
    again here because the entire meaning of the evaluation rests on it: a
    fragment on both sides of the boundary turns the test score into a
    memorisation score, and inheriting a guarantee is not the same as checking
    it. Clusters as well as fragments, because ``[c01]`` siblings are one idea
    written twice -- splitting a *cluster* leaks just as effectively as
    splitting a fragment, and only the cluster check would catch it.
    """
    for left in range(len(splits)):
        for right in range(left + 1, len(splits)):
            first, second = splits[left], splits[right]

            shared_fragments = sorted(set(first.fragments) & set(second.fragments))
            if shared_fragments:
                raise DatasetError(
                    f"fragments appear in both the {first.name!r} and {second.name!r} splits: "
                    f"{', '.join(shared_fragments[:5])}"
                    f"{' ...' if len(shared_fragments) > 5 else ''}"
                )

            first_clusters = {info.cluster_key for info in first.fragments.values()}
            second_clusters = {info.cluster_key for info in second.fragments.values()}
            shared_clusters = sorted(first_clusters & second_clusters)
            if shared_clusters:
                raise DatasetError(
                    f"clusters straddle the {first.name!r}/{second.name!r} boundary, so the same "
                    f"idea is on both sides: {', '.join(shared_clusters[:5])}"
                    f"{' ...' if len(shared_clusters) > 5 else ''}"
                )


def load_fold(
    train: Path | str,
    val: Path | str,
    test: Path | str,
    *,
    signals: Sequence[str] | None = None,
) -> Fold:
    """Load the three splits of one fold, cross-checked against each other.

    The checks are the point of this function existing at all: agreement on the
    generator version and fold configuration, and fragment- and cluster-level
    disjointness between every pair of splits.
    """
    paths = {"train": Path(train), "val": Path(val), "test": Path(test)}
    if signals is None:
        # One cheap extra pass over the JSONL so every split ends up with the
        # same head set. A signal absent from one split's examples would
        # otherwise give that split narrower label vectors than its siblings.
        resolved = tuple(
            sorted({signal for path in paths.values() for signal in _signals_in(_read_jsonl(path))})
        )
    else:
        resolved = tuple(signals)

    loaded = {
        name: load_split(path, signals=resolved, expect_split=name) for name, path in paths.items()
    }
    splits = [loaded["train"], loaded["val"], loaded["test"]]
    _check_fold_agreement(splits)
    _check_disjoint(splits)
    return Fold(train=loaded["train"], val=loaded["val"], test=loaded["test"])


def swap_test_split(fold: Fold, test_fold: Fold) -> Fold:
    """Keep ``fold``'s train and val splits, take its test split from ``test_fold``.

    This is the whole of the cross-tree evaluation: a model trained on one
    generated tree, scored on the *same held-out clusters* written a different
    way -- damaged text against clean, say. Nothing else in this package can
    express that, because every other path trains and scores inside one
    ``--data-dir``.

    The checks are what make the swapped number mean anything. The two folds
    must agree on the signal and on the whole fold configuration, and their test
    splits must hold **exactly the same example ids and the same fragment ids**.
    That is the difference between "the same evaluation set in a different
    surface form" and "some other dataset's test split", and without it pointing
    ``--test-dir`` at an unrelated tree would produce a plausible-looking score
    with no interpretation at all.

    The head sets must match too. A test tree missing one of the training
    tree's signals loads perfectly happily -- a missing label key means
    "masked", by design -- so the score for that head would silently become an
    average over nothing.
    """
    for field in ("signal", "folds", "fold_index", "split_salt"):
        left = fold.test.stats.get(field)
        right = test_fold.test.stats.get(field)
        if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
            raise DatasetError(
                f"{test_fold.test.path} cannot supply the test split for {fold.test.path}: they "
                f"disagree on {field!r} ({left!r} vs {right!r}). They are not two views of one "
                "partition, so a model trained against one and scored against the other is "
                "scored on clusters it may have trained on"
            )

    if fold.signals != test_fold.signals:
        raise DatasetError(
            f"{test_fold.test.path} carries signals {test_fold.signals} but the training tree "
            f"carries {fold.signals}. A signal absent from the test tree reads as masked rather "
            "than as an error, so the swap would quietly score that head on no examples"
        )

    _check_same_ids(
        "example",
        {example.example_id for example in fold.test.examples},
        {example.example_id for example in test_fold.test.examples},
        fold=fold,
        test_fold=test_fold,
    )
    _check_same_ids(
        "fragment",
        set(fold.test.fragments),
        set(test_fold.test.fragments),
        fold=fold,
        test_fold=test_fold,
    )

    return Fold(train=fold.train, val=fold.val, test=test_fold.test)


def _check_same_ids(
    kind: str, expected: Collection[str], found: Collection[str], *, fold: Fold, test_fold: Fold
) -> None:
    """Assert two test splits describe the same held-out material."""
    missing = sorted(set(expected) - set(found))
    extra = sorted(set(found) - set(expected))
    if not missing and not extra:
        return
    detail = []
    if missing:
        detail.append(
            f"missing {len(missing)} ({', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''})"
        )
    if extra:
        detail.append(
            f"unexpected {len(extra)} ({', '.join(extra[:5])}{' ...' if len(extra) > 5 else ''})"
        )
    raise DatasetError(
        f"{test_fold.test.path} does not hold the same {kind} ids as {fold.test.path}: "
        f"{'; '.join(detail)}. A cross-tree evaluation is only meaningful when the two test "
        "splits are the same held-out clusters differing in surface form"
    )


def fold_dataset_path(directory: Path | str, signal: str, fold_index: int, split: str) -> Path:
    """Where one fold's split lives, by the :data:`FOLD_FILENAME` convention."""
    if split not in SPLITS:
        raise DatasetError(f"{split!r} is not one of {SPLITS}")
    return Path(directory) / FOLD_FILENAME.format(signal=signal, fold_index=fold_index, split=split)


def _check_test_partition(folds: Sequence[Fold]) -> None:
    """Assert no cluster is a test cluster in two folds.

    This is the property that makes pooling predictions across folds mean
    anything: every cluster is held out exactly once, so the pooled test set is
    the whole library counted once rather than some clusters counted twice and
    others not at all. It follows from the splitter's arithmetic, which is
    exactly why it is worth asserting -- a change to the bucketing that broke it
    would leave every file loading cleanly and every number quietly weighted.
    """
    seen: dict[str, int] = {}
    for fold in folds:
        index = fold.fold_index
        for info in fold.test.fragments.values():
            previous = seen.setdefault(info.cluster_key, index)
            if previous != index:
                raise DatasetError(
                    f"cluster {info.cluster_key!r} is a test cluster in both fold {previous} and "
                    f"fold {index}; pooling the folds would count it twice and miss another"
                )


def load_folds(
    directory: Path | str,
    signal: str,
    *,
    folds: int,
    signals: Sequence[str] | None = None,
) -> tuple[Fold, ...]:
    """Load all K folds of one signal from a directory of generated datasets.

    Every check :func:`load_fold` makes within a fold, plus three across them:
    each file must record the fold index its filename claims, all K must agree
    on the fold configuration, and no cluster may be held out twice. The first
    is the one most likely to fire in practice -- regenerating a single fold
    with the wrong ``--fold`` leaves a directory that looks complete.
    """
    if folds < 1:
        raise DatasetError(f"folds must be at least 1: {folds}")

    loaded = []
    for fold_index in range(folds):
        paths = {split: fold_dataset_path(directory, signal, fold_index, split) for split in SPLITS}
        fold = load_fold(paths["train"], paths["val"], paths["test"], signals=signals)
        if fold.folds != folds:
            raise DatasetError(
                f"{paths['test']} was generated with folds={fold.folds!r}, but is being read as "
                f"one of {folds}"
            )
        if fold.fold_index != fold_index:
            raise DatasetError(
                f"{paths['test']} is named fold {fold_index} but its sidecar records fold "
                f"{fold.fold_index!r}; regenerating one fold with the wrong --fold leaves a "
                "directory that looks complete and evaluates nonsense"
            )
        loaded.append(fold)

    salts = {json.dumps(fold.train.split_salt) for fold in loaded}
    if len(salts) > 1:
        raise DatasetError(
            f"the folds disagree on split_salt ({', '.join(sorted(salts))}), so they are not K "
            "views of one partition and pooling them is meaningless"
        )
    _check_test_partition(loaded)
    return tuple(loaded)
