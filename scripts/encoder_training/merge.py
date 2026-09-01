"""Merging per-signal fold trees into one multi-head training set.

Standard library only, like :mod:`.dataset` and for the same reason: this is a
step that decides what the joint run's numbers *mean*, so every line of it has
to be coverable by CI's unit job on a runner with no GPU and no ML wheels.

**Nothing is regenerated.** Six per-signal five-fold trees already exist, and the
merge is a concatenation. That is not an optimisation, it is what makes the
comparison the ticket exists for readable: the merged tree's ``fever_present``
slice *is* the fever tree's own slice, example for example, so a joint model and
a single-signal model can be compared pairwise on it.

Three properties make the concatenation safe, and each one is asserted here
rather than trusted.

* **Fold membership does not depend on the signal.**
  :func:`~scripts.synthetic_data.manifest.fold_bucket` hashes ``{salt}:{key}``
  and knows nothing about signals, so a cluster lands in the same fold and the
  same split in all six trees. Cluster disjointness therefore survives
  concatenation for free -- and it is checked again anyway, by
  :func:`~.dataset.load_folds` on the output.
* **A missing signal key is a mask, not a ``null``.** A merged dysuria example
  carries a dysuria label and *no fever key at all*, which :mod:`.dataset` reads
  as "exclude this head from the loss". No head gains supervision from the
  merge; the shared encoder gains gradient from five other heads. Filling the
  five absent keys with ``null`` would be a different ticket and a much worse
  dataset -- see ``arch_training.md`` 12.5.
* **The filler-only examples really are the same examples.** The generator's
  seed derivation does not include the signal, so all six trees emit
  byte-identical filler-only examples. One copy is kept, labelled ``null`` for
  all six signals -- same gradients, 25% fewer forward passes at
  ``--companion-share 0``, and each head keeps exactly the 15/25/60 mix it
  trained on alone. That identity is the load-bearing one: if anyone ever adds
  the signal to the seed derivation, six *divergent* null sets would collapse
  into whichever arrived first, every head's class prior would shift, and nothing
  downstream would notice. So it is asserted position for position, and a
  mismatch is a hard error.

  **The set it runs over is ``meta.filler_only``, not the ``null_structural``
  label mode**, and at ``--companion-share`` above zero those are different sets.
  A structural null that drew a companion holds another signal's clinical
  language, which is drawn from *this* signal's eligible pool -- so it is not the
  example any other tree emitted at that index, and it is kept per signal like
  any other owned example. What survives deduplication is the filler-only
  remainder, which shrinks towards nothing as the share rises. That is this
  feature's compute bill and it is accepted rather than worked around; see
  ``arch_training.md`` section 5.

**Every merged example keeps the id it had in its own tree**, in
``meta.source_ids``, because the fresh ``example_id`` has to be unique across
six trees that all number from ``train-000000``. When a joint model reports
predictions for signal S it reports them under ``meta.source_ids[S]``, and every
existing pairing mechanism -- paired McNemar above all -- then works untouched.
The alternative, teaching the report layer that two ids are the same example,
puts that knowledge in the one module with no way to check it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .dataset import (
    LABEL_MODES,
    REQUIRED_FRAGMENT_FIELDS,
    REQUIRED_STATS_KEYS,
    SPLITS,
    fold_dataset_path,
    sidecar_path,
)

#: The label mode of an example that holds no fragment decisive for its signal.
#: Every deduplicable example has this mode, but not every example with this
#: mode is deduplicable: at ``--companion-share`` above zero a structural null
#: may hold another signal's clinical language, drawn from a pool that differs by
#: signal. ``meta.filler_only`` is the property this module keys off; this
#: constant is only used to check the two agree in the direction they must.
STRUCTURAL_NULL_MODE = "null_structural"

#: Prefix for a deduplicated filler-only example's merged id. Reserved: a signal
#: by this name would make ``{signal}:{original}`` and ``shared:{original}``
#: collide, so it is rejected rather than allowed to overwrite.
SHARED_ID_PREFIX = "shared"

#: The six signals a joint model has heads for. ``data/uti1.json`` declares a
#: seventh -- ``recent_uti_present`` -- which **now has libraries** and therefore
#: a fold tree of its own and a place in every other signal's companion pool, but
#: no trained head: the multi-symptom ticket put a seventh head explicitly out of
#: scope. So it is absent here, and a joint model still cannot satisfy
#: ``EncoderOutput.validate_against``. Adding an untrained seventh head to make
#: the arity match would put an uninitialised guess behind a contract saying the
#: encoder answered; that is strictly worse than a stub that is honestly a stub.
#: Pass ``--signals`` to merge a different set.
DEFAULT_SIGNALS = (
    "dysuria_present",
    "fever_present",
    "flank_pain_present",
    "haematuria_present",
    "nocturia_present",
    "urinary_frequency_present",
)

#: Sidecar fields every source must agree on before a merge means anything,
#: as dotted paths into the sidecar. ``generator_version`` because two
#: generators' examples are not one dataset; the fold triple because ``test``
#: names a different set of clusters under each one, so merging across two
#: triples would put one tree's test clusters in another's training split with
#: every file still loading cleanly; and ``requested.companion_share`` because a
#: merged tree mixing an arm at zero with an arm above it is uninterpretable --
#: the comparison the two arms exist for would be running against a dataset that
#: is half of each, and nothing downstream would notice.
SIDECAR_AGREEMENT_FIELDS = (
    "generator_version",
    "folds",
    "fold_index",
    "split_salt",
    "requested.companion_share",
)

#: Fragment-provenance fields that must agree where two sources describe the
#: same fragment id. A dict union would first-win a disagreement silently, and a
#: disagreement here is exactly the drift the structural-null assertion exists
#: to catch, arriving through the other door.
FRAGMENT_AGREEMENT_FIELDS = ("cluster_key", "fragment_type", "split")


class MergeError(ValueError):
    """Raised when per-signal trees cannot be merged into one honest dataset."""


def sidecar_field(stats: Mapping[str, object], field: str) -> object:
    """Read a dotted path out of a sidecar, refusing rather than defaulting.

    A missing field is a source this module has never seen -- in practice a tree
    generated before ``GENERATOR_VERSION`` 3, which has no
    ``requested.companion_share`` and no ``meta.filler_only`` either. Defaulting
    it to zero would let a pre-companion tree merge with a post-companion one on
    the strength of a guess, so it raises instead and says what to do.
    """
    value: object = stats
    walked: list[str] = []
    for part in field.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise MergeError(
                f"a source sidecar has no {field!r} (missing at {'.'.join(walked + [part])!r}). "
                "Every field the merge checks is written by GENERATOR_VERSION 3; a tree from "
                "before it has to be regenerated rather than merged on a default"
            )
        walked.append(part)
        value = value[part]
    return value


@dataclass(frozen=True)
class SourceSplit:
    """One signal's one split, read raw so it can be re-emitted verbatim."""

    signal: str
    path: Path
    records: tuple[dict, ...]
    stats: dict

    @property
    def split(self) -> str:
        return str(self.stats["split"])

    @property
    def companion_share(self) -> float:
        return float(sidecar_field(self.stats, "requested.companion_share"))

    @property
    def structural(self) -> tuple[dict, ...]:
        """The filler-only examples, in file order. Shared with every source.

        ``meta.filler_only`` and not ``label_mode``: at ``--companion-share``
        above zero a structural null may carry another signal's language, drawn
        from a pool that differs by signal, so it is no longer an example every
        tree emitted. The generator writes this key at assembly rather than
        leaving it to be re-derived, because re-deriving it needs the manifest
        and goes quietly wrong the moment a library is edited.
        """
        return tuple(record for record in self.records if record["meta"]["filler_only"])

    @property
    def owned(self) -> tuple[dict, ...]:
        """The examples only this signal has, in file order."""
        return tuple(record for record in self.records if not record["meta"]["filler_only"])


@dataclass(frozen=True)
class MergeResult:
    """What one merge wrote, and the one thing it noticed but did not refuse."""

    name: str
    paths: tuple[Path, ...]
    examples: int
    #: Cluster keys whose fragments come from more than one library. Deflates
    #: effective n rather than inflating it, so it is reported and not fatal --
    #: but it is invisible, and invisible is what this package exists to prevent.
    collisions: tuple[dict, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        if not self.collisions:
            return ()
        keys = ", ".join(collision["cluster_key"] for collision in self.collisions[:5])
        return (
            f"note: {len(self.collisions)} cluster key(s) are shared by fragments from more than "
            f"one library ({keys}{' ...' if len(self.collisions) > 5 else ''}), so those fragments "
            "resample as one unit and every effective sample size below is deflated by that much. "
            "Listed in full in the merged sidecar's 'merged_from' block",
        )


# --------------------------------------------------------------------------
# Reading one source
# --------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        raise MergeError(
            f"source dataset not found: {path}. Every signal needs every fold of every split; "
            "a tree missing one fold looks complete from the directory listing"
        )

    records: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise MergeError(f"{path}:{number} is not valid JSON: {error}") from error
            if not isinstance(record, dict):
                raise MergeError(f"{path}:{number} is not a JSON object")
            records.append(record)

    if not records:
        raise MergeError(f"{path} holds no examples")
    return records


def _read_stats(path: Path) -> dict:
    stats_path = sidecar_path(path)
    if not stats_path.is_file():
        raise MergeError(f"no stats sidecar beside {path}: expected {stats_path}")
    try:
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MergeError(f"{stats_path} is not valid JSON: {error}") from error
    if not isinstance(stats, dict):
        raise MergeError(f"{stats_path} is not a JSON object")

    missing = [key for key in REQUIRED_STATS_KEYS if key not in stats]
    if missing:
        raise MergeError(f"{stats_path} is missing required keys: {', '.join(missing)}")
    if not isinstance(stats["fragments"], dict) or not stats["fragments"]:
        raise MergeError(f"{stats_path} has an empty or malformed 'fragments' block")
    return stats


def _check_record(record: Mapping[str, object], *, signal: str, split: str, path: Path) -> None:
    """Reject a source record the merge cannot re-emit honestly.

    The label-keys check is the one that earns its place: a record carrying two
    signals' keys is either an already-merged tree being merged again or a
    dataset from a generator this module has never seen, and either way the
    merged label vectors would be built on an assumption that is false.
    """
    example_id = record.get("example_id")
    if not isinstance(example_id, str) or not example_id:
        raise MergeError(f"{path}: an example has no 'example_id'")
    if record.get("split") != split:
        raise MergeError(
            f"{path}: example {example_id!r} is labelled split {record.get('split')!r}, but its "
            f"sidecar describes split {split!r}"
        )
    if not isinstance(record.get("text"), str):
        raise MergeError(f"{path}: example {example_id!r} has no 'text'")

    labels = record.get("labels")
    if not isinstance(labels, dict):
        raise MergeError(f"{path}: example {example_id!r} has no 'labels' object")
    if set(labels) != {signal}:
        raise MergeError(
            f"{path}: example {example_id!r} carries labels for {sorted(labels)!r}, but this tree "
            f"is {signal!r}'s. The merge builds each example's vector by asserting null for every "
            "signal the source tree did not emit a key for, and an example that already emits "
            "several keys makes that assumption false. This is about the keys an example emits, "
            "not about how many signals its fragments decide: a tree generated at "
            "--declarative-share above zero holds fragments asserting three or four signals each "
            "and is still a single-key tree, because --emit-signals primary emits one. It is "
            "--emit-signals all that lands here, and 12.2 is what it is waiting on"
        )

    meta = record.get("meta")
    if not isinstance(meta, dict):
        raise MergeError(f"{path}: example {example_id!r} has no 'meta' object")
    label_mode = meta.get("label_mode")
    if label_mode not in LABEL_MODES:
        raise MergeError(
            f"{path}: example {example_id!r} has label mode {label_mode!r}, expected one of "
            f"{LABEL_MODES}"
        )
    if not isinstance(meta.get("fragment_ids"), list) or not meta["fragment_ids"]:
        raise MergeError(f"{path}: example {example_id!r} has no 'meta.fragment_ids'")
    filler_only = meta.get("filler_only")
    if not isinstance(filler_only, bool):
        raise MergeError(
            f"{path}: example {example_id!r} has no boolean 'meta.filler_only'. It is what the "
            "merge deduplicates on, and a tree from before GENERATOR_VERSION 3 does not carry "
            "it. Re-deriving it from the label mode would be right for such a tree and silently "
            "wrong for any tree generated with --companion-share above zero, so it is refused"
        )
    if filler_only and label_mode != STRUCTURAL_NULL_MODE:
        raise MergeError(
            f"{path}: example {example_id!r} is filler-only but has label mode {label_mode!r}. "
            "Every fragment being filler means no fragment is decisive, so the two can only "
            "disagree if the generator has drifted"
        )
    if label_mode == STRUCTURAL_NULL_MODE and labels[signal] is not None:
        raise MergeError(
            f"{path}: example {example_id!r} is a structural null but labels {signal!r} "
            f"{labels[signal]!r}. The merged copy asserts null for all six signals, and that "
            "assertion is only sound because each source asserts it for its own"
        )


def load_source_split(path: Path | str, *, signal: str, split: str) -> SourceSplit:
    """Read one signal's one split, checked only as far as the merge relies on it.

    Deliberately not :func:`~.dataset.load_split`: that resolves examples into
    label vectors and drops the raw record, and the merge has to re-emit ``meta``
    verbatim. The full load runs on the *output* instead, which is where it
    matters -- if the merged tree needs a new escape hatch in ``dataset.py``, the
    merge is wrong, not the loader.
    """
    path = Path(path)
    stats = _read_stats(path)
    if stats["signal"] != signal:
        raise MergeError(
            f"{sidecar_path(path)} records signal {stats['signal']!r}, but the file is named for "
            f"{signal!r}"
        )
    if stats["split"] != split:
        raise MergeError(
            f"{sidecar_path(path)} records split {stats['split']!r}, but the file is named for "
            f"{split!r}"
        )

    records = _read_jsonl(path)
    for record in records:
        _check_record(record, signal=signal, split=split, path=path)
    return SourceSplit(signal=signal, path=path, records=tuple(records), stats=stats)


# --------------------------------------------------------------------------
# The checks that make a concatenation meaningful
# --------------------------------------------------------------------------


def _check_agreement(sources: Sequence[SourceSplit]) -> None:
    """Reject sources that did not come from one fold configuration."""
    for field in SIDECAR_AGREEMENT_FIELDS:
        values = {source.signal: sidecar_field(source.stats, field) for source in sources}
        distinct = {json.dumps(value, sort_keys=True) for value in values.values()}
        if len(distinct) > 1:
            rendered = ", ".join(f"{signal}={value!r}" for signal, value in values.items())
            raise MergeError(
                f"the sources disagree on {field!r}: {rendered}. They are not views of one "
                "partition, so concatenating them would put one tree's test clusters in another "
                "tree's training split -- or one arm's examples in another arm's tree -- with "
                "every file still loading cleanly"
            )


#: Fields a shared copy has to agree on across every source before one copy can
#: stand for all of them. The label mode is not here because it is checked per
#: record instead: a filler-only example is a ``null_structural`` one or the
#: generator has drifted.
SHARED_AGREEMENT_FIELDS = (
    ("text", lambda record: record["text"]),
    ("meta.fragment_ids", lambda record: record["meta"]["fragment_ids"]),
)


def check_structural_nulls(sources: Sequence[SourceSplit]) -> tuple[dict, ...]:
    """Return the filler-only examples every source emitted, asserting they agree.

    On ``text`` and ``meta.fragment_ids``, matched by ``example_id``: the
    identity the union depends on, asserted rather than assumed. If the
    generator's seed derivation ever grew a signal term, six divergent null sets
    would silently collapse to one tree's, shifting every head's class prior with
    nothing downstream the wiser.

    **Relaxed, not deleted, when companions arrived**, in two steps.

    The set it runs over is ``meta.filler_only`` rather than the
    ``null_structural`` label mode. Above ``--companion-share 0`` a structural
    null may hold another signal's language, drawn from a pool that differs by
    signal, so it is not the example any other tree emitted and is kept per
    signal rather than asserted identical to trees it cannot be identical to.

    And the sources are matched by ``example_id`` rather than by position,
    because above zero the filler-only sets are *nearly* but not exactly the same
    set. :func:`~scripts.synthetic_data.recombine.generate` rejects an example
    whose normalised text it has already emitted and redraws on the same
    per-example RNG, and the ``seen`` set diverges between trees as soon as their
    companions do -- so an index that collided in one tree and not in another
    lands on a different draw there, and can come out holding a companion in one
    tree and filler alone in the next. Measured on the committed libraries at
    ``--companion-share 0.5``: 1121 filler-only examples in a 10,000-example
    split against 1118 that all six sources agree on. The agreed ones are
    deduplicated; the three that not every source emitted are kept per signal,
    where they are ordinary owned examples carrying an honest ``null`` for their
    own head and a mask for the others.

    **At ``--companion-share 0`` that divergence is impossible**, so it is a hard
    error there rather than a tolerated remainder: with no companions every
    filler-only draw is signal-independent, down to which texts the ``seen`` set
    already holds, so a disagreement could only be the drift this function exists
    to catch.
    """
    reference = sources[0]
    indexed = [{record["example_id"]: record for record in source.structural} for source in sources]
    shared_ids = set(indexed[0]).intersection(*indexed[1:])

    for example_id in sorted(shared_ids):
        left = indexed[0][example_id]
        for source, records in zip(sources[1:], indexed[1:], strict=True):
            right = records[example_id]
            for field, getter in SHARED_AGREEMENT_FIELDS:
                if getter(left) != getter(right):
                    raise MergeError(
                        f"fold {reference.stats['fold_index']} {reference.split!r}: filler-only "
                        f"example {example_id!r} disagrees on {field} between "
                        f"{reference.signal!r} ({getter(left)!r}) and {source.signal!r} "
                        f"({getter(right)!r}). Keeping one copy would silently drop the others"
                    )

    unshared = set().union(*indexed) - shared_ids
    if unshared and all(source.companion_share == 0.0 for source in sources):
        listed = ", ".join(sorted(unshared)[:5])
        raise MergeError(
            f"fold {reference.stats['fold_index']} {reference.split!r}: {len(unshared)} "
            f"example(s) are filler-only in some sources and not in others ({listed}"
            f"{' ...' if len(unshared) > 5 else ''}), at --companion-share 0 where every "
            "filler-only draw is signal-independent and this cannot happen. Something has made "
            "the generator's draws depend on the signal, which is the drift that would otherwise "
            "collapse six divergent null sets into whichever arrived first"
        )

    # Reference file order, so the merged tree stays byte-reproducible.
    return tuple(record for record in reference.structural if record["example_id"] in shared_ids)


def merge_fragments(sources: Sequence[SourceSplit]) -> dict[str, dict]:
    """Union the sources' provenance blocks, refusing to first-win a conflict."""
    merged: dict[str, dict] = {}
    origin: dict[str, str] = {}
    for source in sources:
        for fragment_id, entry in source.stats["fragments"].items():
            if not isinstance(entry, dict):
                raise MergeError(
                    f"{sidecar_path(source.path)}: fragment {fragment_id!r} is not a JSON object"
                )
            missing = [field for field in REQUIRED_FRAGMENT_FIELDS if field not in entry]
            if missing:
                raise MergeError(
                    f"{sidecar_path(source.path)}: fragment {fragment_id!r} is missing "
                    f"{', '.join(missing)}"
                )
            existing = merged.get(fragment_id)
            if existing is None:
                merged[fragment_id] = dict(entry)
                origin[fragment_id] = source.signal
                continue
            for field in FRAGMENT_AGREEMENT_FIELDS:
                if existing[field] != entry[field]:
                    raise MergeError(
                        f"fragment {fragment_id!r} disagrees on {field!r} between "
                        f"{origin[fragment_id]!r} ({existing[field]!r}) and {source.signal!r} "
                        f"({entry[field]!r}). A dict union would keep the first silently, and the "
                        "two trees would then be describing different fragments by one name"
                    )
    return dict(sorted(merged.items()))


def cluster_collisions(fragments: Mapping[str, Mapping[str, object]]) -> tuple[dict, ...]:
    """Cluster keys shared by fragments from more than one library.

    A tagged cluster cannot do this: its key is ``{library}:{tag}``, namespaced
    by construction. An *untagged* one can, because the key falls back to the
    normalised text, which is not library-qualified -- so identical text in two
    signals' libraries becomes one resampling unit spanning both. That deflates
    effective n rather than inflating it, which is the safe direction, so this is
    reported and never fatal.
    """
    by_key: dict[str, dict[str, set]] = {}
    for fragment_id, entry in fragments.items():
        bucket = by_key.setdefault(
            str(entry["cluster_key"]),
            {"libraries": set(), "signal_keys": set(), "fragments": set()},
        )
        bucket["libraries"].add(entry.get("library"))
        bucket["signal_keys"].add(entry.get("signal_key"))
        bucket["fragments"].add(fragment_id)

    return tuple(
        {
            "cluster_key": key,
            "libraries": sorted(bucket["libraries"], key=str),
            "signal_keys": sorted(bucket["signal_keys"], key=str),
            "fragments": sorted(bucket["fragments"]),
        }
        for key, bucket in sorted(by_key.items())
        if len(bucket["libraries"]) > 1
    )


# --------------------------------------------------------------------------
# Building the merged split
# --------------------------------------------------------------------------


def _interleave(groups: Sequence[Sequence[dict]]) -> list[dict]:
    """Round-robin the groups, so any prefix of the file is representative.

    Training shuffles batch order every epoch, so file order carries no meaning
    for the run itself -- but a concatenation would leave the first seven
    thousand lines all one signal, which makes every ``head`` of the file and
    every truncated smoke run silently unrepresentative. Fixed order either way,
    so the merge is byte-reproducible.
    """
    merged: list[dict] = []
    for position in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if position < len(group):
                merged.append(group[position])
    return merged


def _owned_record(record: Mapping[str, object], *, signal: str) -> dict:
    """One signal's own example, re-emitted with a merged id.

    The five other heads get **no key**, which :mod:`.dataset` reads as "mask
    this head". Writing ``null`` for them instead would assert that a dysuria
    sentence says nothing about fever -- which is true of the *text* and is
    exactly the supervision the merge deliberately does not add (12.5).
    """
    meta = dict(record["meta"])
    meta["source_ids"] = {signal: record["example_id"]}
    return {
        "example_id": f"{signal}:{record['example_id']}",
        "split": record["split"],
        "text": record["text"],
        "labels": dict(record["labels"]),
        "meta": meta,
    }


def _shared_record(record: Mapping[str, object], *, signals: Sequence[str]) -> dict:
    """One filler-only example, kept once and labelled ``null`` for every signal.

    Sound only because every source asserts ``null`` for its own signal on this
    exact example (checked in :func:`_check_record`) and because the six copies
    are byte-identical (checked in :func:`check_structural_nulls`). The lint that
    holds the filler libraries silent about all six signals is what makes the
    assertion true in the first place; see ``arch_training.md`` 12.8.
    """
    meta = dict(record["meta"])
    meta["source_ids"] = {signal: record["example_id"] for signal in signals}
    return {
        "example_id": f"{SHARED_ID_PREFIX}:{record['example_id']}",
        "split": record["split"],
        "text": record["text"],
        "labels": {signal: None for signal in signals},
        "meta": meta,
    }


def _realised(records: Sequence[Mapping[str, object]], signals: Sequence[str]) -> dict:
    """What actually came out, per head, next to what the sources put in."""
    modes = {mode: 0 for mode in LABEL_MODES}
    per_signal = {signal: {"true": 0, "false": 0, "null": 0} for signal in signals}
    for record in records:
        modes[record["meta"]["label_mode"]] += 1
        for signal, value in record["labels"].items():
            name = "null" if value is None else ("true" if value is True else "false")
            per_signal[signal][name] += 1
    return {
        "count": len(records),
        "label_modes": modes,
        # Per head, over the positions that head is *not* masked on. The joint
        # run adds no supervision to any head, so each of these should match the
        # source tree's own realised counts exactly.
        "labelled_by_signal": per_signal,
    }


def merge_split(sources: Sequence[SourceSplit], *, name: str) -> tuple[list[dict], dict]:
    """Merge one split of every source into records plus a merged sidecar."""
    if not sources:
        raise MergeError("nothing to merge: no source splits given")

    signals = [source.signal for source in sources]
    if len(set(signals)) != len(signals):
        raise MergeError(f"the sources must be distinct signals, and these are not: {signals}")
    if name in signals:
        raise MergeError(
            f"the merged name {name!r} is also one of the source signals; the merged tree would "
            "overwrite that signal's fold files"
        )
    if name == SHARED_ID_PREFIX or SHARED_ID_PREFIX in signals:
        raise MergeError(
            f"{SHARED_ID_PREFIX!r} is reserved for deduplicated structural nulls' example ids"
        )

    _check_agreement(sources)
    shared = check_structural_nulls(sources)
    shared_ids = {record["example_id"] for record in shared}
    fragments = merge_fragments(sources)
    collisions = cluster_collisions(fragments)

    # Everything the shared copy does not already stand for, which above
    # --companion-share 0 includes the handful of filler-only examples not every
    # source emitted. Keyed on the shared set rather than on `filler_only` so
    # that "deduplicated" and "kept per signal" partition the tree between them
    # by construction, with no example in both and none in neither.
    emitted = [
        [record for record in source.records if record["example_id"] not in shared_ids]
        for source in sources
    ]
    groups = [
        [_owned_record(record, signal=source.signal) for record in own]
        for source, own in zip(sources, emitted, strict=True)
    ]
    groups.append([_shared_record(record, signals=signals) for record in shared])
    records = _interleave(groups)

    reference = sources[0].stats
    seeds = {json.dumps(source.stats.get("seed")) for source in sources}
    stats = {
        "generator_version": reference["generator_version"],
        # One seed only where all six agree, which they do whenever the seed
        # derivation is signal-independent -- the same fact the structural-null
        # identity rests on. Where they do not, there is no single seed and
        # saying so beats naming one of them.
        "seed": sources[0].stats.get("seed") if len(seeds) == 1 else None,
        "signal": name,
        "split": sources[0].split,
        "folds": reference["folds"],
        "fold_index": reference["fold_index"],
        "split_salt": reference["split_salt"],
        "signals": list(signals),
        "realised": _realised(records, signals),
        "fragments": fragments,
        "merged_from": {
            "sources": [
                {
                    "signal": source.signal,
                    "path": str(source.path),
                    "examples": len(source.records),
                    # What this source contributed under its own id: everything
                    # the deduplicated copy does not already stand for.
                    "signal_owned": len(own),
                    "filler_only": len(source.structural),
                    "companion_share": source.companion_share,
                    "seed": source.stats.get("seed"),
                }
                for source, own in zip(sources, emitted, strict=True)
            ],
            # The arm this tree belongs to. Every source agrees on it or the
            # merge refused, so one value describes the whole tree -- and a
            # merged tree that did not record it would be indistinguishable from
            # the other arm's once it left the directory it was written in.
            "companion_share": sources[0].companion_share,
            "filler_only": {
                "kept": len(shared),
                "dropped_as_duplicates": len(shared) * (len(sources) - 1),
                # Filler-only in some sources and not in others, so no one copy
                # describes what every head was trained on. Kept per signal.
                # Zero at --companion-share 0, where it is a hard error.
                "kept_per_signal": sum(
                    1
                    for source in sources
                    for record in source.structural
                    if record["example_id"] not in shared_ids
                ),
                "note": (
                    "the sources emit byte-identical filler-only examples, so one copy is kept "
                    "and labelled null for every signal. Checked position for position on "
                    "example_id, text and meta.fragment_ids, not assumed. Deduplication keys on "
                    "meta.filler_only rather than on the null_structural label mode: above "
                    "--companion-share 0 a structural null may carry another signal's language "
                    "drawn from a pool that differs by signal, so it is kept per signal and this "
                    "count falls towards zero as the share rises"
                ),
            },
            "example_ids": (
                "meta.source_ids maps each signal to the id this example had in that signal's own "
                "tree. Report predictions for signal S under meta.source_ids[S] and every paired "
                "comparison against that signal's single-signal run works untouched"
            ),
            "cluster_key_collisions": {
                "count": len(collisions),
                "note": (
                    "cluster keys shared by fragments from more than one library. Untagged "
                    "fragments key on normalised text, which is not library-qualified, so "
                    "identical text in two libraries resamples as one unit. Deflates effective n "
                    "rather than inflating it, so it is reported and not fatal"
                ),
                "keys": list(collisions),
            },
        },
    }
    return records, stats


def write_merged_split(
    records: Sequence[Mapping[str, object]], stats: Mapping[str, object], path: Path | str
) -> Path:
    """Write one merged split and its sidecar, by the fold-file convention."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    sidecar_path(path).write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return path


def merge_folds(
    data_dir: Path | str,
    *,
    signals: Sequence[str] = DEFAULT_SIGNALS,
    out_dir: Path | str | None = None,
    name: str | None = None,
    folds: int,
) -> MergeResult:
    """Merge every fold and split of every signal into one tree under ``out_dir``.

    Output filenames follow :data:`~.dataset.FOLD_FILENAME` with ``name`` in the
    signal position, so ``load_folds(out_dir, name, folds=K)`` reads the result
    with every existing check applying and no special case anywhere.
    """
    if folds < 1:
        raise MergeError(f"folds must be at least 1: {folds}")
    if len(signals) < 2:
        raise MergeError(f"a merge needs at least two signals, got {list(signals)}")

    data_dir = Path(data_dir)
    out_dir = Path(out_dir) if out_dir is not None else data_dir
    name = name or f"joint{len(signals)}"

    written: list[Path] = []
    collisions: dict[str, dict] = {}
    examples = 0
    for fold_index in range(folds):
        for split in SPLITS:
            sources = [
                load_source_split(
                    fold_dataset_path(data_dir, signal, fold_index, split),
                    signal=signal,
                    split=split,
                )
                for signal in signals
            ]
            records, stats = merge_split(sources, name=name)
            written.append(
                write_merged_split(
                    records, stats, fold_dataset_path(out_dir, name, fold_index, split)
                )
            )
            examples += len(records)
            for collision in stats["merged_from"]["cluster_key_collisions"]["keys"]:
                collisions.setdefault(collision["cluster_key"], collision)

    return MergeResult(
        name=name,
        paths=tuple(written),
        examples=examples,
        collisions=tuple(collisions[key] for key in sorted(collisions)),
    )
