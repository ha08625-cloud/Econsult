"""Fragment library loading, deduplication and cluster-aware splitting.

Library discovery is an explicit manifest, never a glob: ``data/synthetic/``
also contains scratch notes (``drafts/fever_synonyms.jsonl``) and a generator
spec (``drafts/fever_true.yaml``), and a filename-convention glob would inject
both straight into training text. Files on disk but absent from the manifest
are ignored; files in the manifest but absent from disk are a hard error.

A manifest ``file`` is a path relative to the manifest, so libraries are free
to live in subdirectories (``conditions/uti/symptoms/fever/``, ``filler/``). The
directory carries no meaning to this module -- grouping is for readers, and
every property the generator relies on comes from the manifest entry.

Splitting hashes the *cluster* key rather than the text. ``fever_null`` is two
generation batches over the same concept list, reworded, so text-level
deduplication catches only the two exact duplicates and hash-splitting would
scatter paraphrase twins across the train/val boundary. That is precisely the
lexical leakage fragment-level splitting exists to prevent, and it would bias
validation upward rather than merely adding noise.

The splitter has two modes. The default is the 70/15/15 band over ``hash % 100``
described above. Fold mode (``folds=K``) instead maps each cluster to one of K
buckets and rotates which bucket is test, so every cluster is a test cluster in
exactly one fold and pooling the folds makes the whole library the effective
test set. Fold mode is opt-in and the default path is byte-identical to what it
was before fold mode existed -- every dataset generated so far, and every number
in ``arch_training.md`` section 10, depends on that digest not moving.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .normalise import normalise

#: Permitted values for a library's ``fragment_type``.
FRAGMENT_TYPES = frozenset({"positive", "negative", "ambiguous", "confounder", "filler"})

#: Split names, in band order.
SPLITS = ("train", "val", "test")

#: Upper bound (exclusive) of each split's band over ``hash % 100``: 70/15/15.
_SPLIT_BANDS = ((70, "train"), (85, "val"), (100, "test"))

#: A leading cluster marker, e.g. ``[c03] My colleague...``.
_CLUSTER_MARKER = re.compile(r"^\[([A-Za-z0-9_]+)\]\s+")


class ManifestError(ValueError):
    """Raised when the manifest, or the libraries it declares, are invalid."""


@dataclass(frozen=True)
class LibrarySpec:
    """One declared fragment library, as it appears in the manifest."""

    name: str
    file: str
    signal_key: str | None
    fragment_type: str
    subclass: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class Fragment:
    """A single fragment, resolved from a library file and assigned a split."""

    fragment_id: str
    text: str
    library: str
    signal_key: str | None
    fragment_type: str
    subclass: str | None
    category: str | None
    cluster_id: str | None
    split: str


def parse_line(line: str) -> tuple[str | None, str]:
    """Split a raw library line into ``(cluster_tag, verbatim_text)``.

    The cluster tag is the bare marker text (``"c03"``), not yet namespaced by
    library; ``None`` when the line carries no marker.
    """
    stripped = line.strip()
    match = _CLUSTER_MARKER.match(stripped)
    if match is None:
        return None, stripped
    return match.group(1), stripped[match.end() :].strip()


def make_fragment_id(library: str, text: str) -> str:
    """Return ``{library}:{sha1(normalised_text)[:8]}``.

    Stable across reordering and insertion, which line numbers are not, so
    provenance survives library edits.
    """
    digest = hashlib.sha1(normalise(text).encode("utf-8")).hexdigest()  # noqa: S324
    return f"{library}:{digest[:8]}"


def cluster_key(cluster_id: str | None, text: str) -> str:
    """Return the key the splitter hashes: the cluster when tagged, else the text.

    The single definition of "same idea". :func:`read_library` splits on it and
    the stats sidecar records it, so a consumer grouping examples by idea uses
    the generator's own grouping rather than reconstructing one that can drift.
    """
    return cluster_id or normalise(text)


def _split_digest(key: str, salt: str) -> int:
    """Hash a (salted) cluster key to an integer.

    An empty salt hashes the bare cluster key, reproducing the pre-fold-mode
    digest exactly. Salting is not a security measure -- it is how a second,
    independent split assignment is obtained from the same libraries.
    """
    salted = f"{salt}:{key}" if salt else key
    return int(hashlib.sha256(salted.encode("utf-8")).hexdigest()[:8], 16)


def fold_bucket(key: str, folds: int, salt: str = "") -> int:
    """Return which of ``folds`` buckets a cluster key falls in."""
    if folds < 2:
        raise ManifestError(f"folds must be at least 2: {folds}")
    return _split_digest(key, salt) % folds


def assign_split(key: str, *, folds: int | None = None, fold_index: int = 0, salt: str = "") -> str:
    """Map a cluster key to ``train``/``val``/``test`` via a stable hash.

    Deterministic across processes and unaffected by ``PYTHONHASHSEED``, so no
    split-assignment file needs storing and the assignment stays stable as
    libraries grow. Python's built-in ``hash()`` is salted per process and is
    deliberately not used.

    With ``folds=None`` this is the 70/15/15 band over ``hash % 100``. With
    ``folds=K`` the key falls in one of K buckets: bucket ``fold_index`` is
    test, bucket ``fold_index + 1`` is validation, and the rest are train --
    60/20/20 at K=5, with every cluster a test cluster in exactly one fold.

    Note that fold *i*'s validation bucket is fold *i+1*'s test bucket. Within a
    fold that is not leakage (each fold trains its own model and never sees its
    own test bucket), but a result pooled across folds carries a little optimism
    from it, because each fold's decision margin was chosen on a sibling fold's
    test clusters. The evaluation report says so rather than leaving a reader to
    discover it.
    """
    if folds is None:
        bucket = _split_digest(key, salt) % 100
        for upper, split in _SPLIT_BANDS:
            if bucket < upper:
                return split
        raise AssertionError(f"unreachable: bucket {bucket} outside 0-99")

    if not 0 <= fold_index < folds:
        raise ManifestError(f"fold index {fold_index} is outside [0, {folds})")
    bucket = fold_bucket(key, folds, salt)
    if bucket == fold_index:
        return "test"
    if bucket == (fold_index + 1) % folds:
        return "val"
    return "train"


def parse_manifest(payload: dict) -> list[LibrarySpec]:
    """Validate the manifest's metadata and return its library specs.

    Checks that do not need the filesystem happen here: permitted
    ``fragment_type``, unique ``name``, and ``signal_key``/``fragment_type``
    agreement.
    """
    libraries = payload.get("libraries")
    if not isinstance(libraries, list) or not libraries:
        raise ManifestError("manifest has no 'libraries' list")

    specs: list[LibrarySpec] = []
    seen_names: set[str] = set()
    for entry in libraries:
        name = entry.get("name")
        if not name:
            raise ManifestError(f"manifest entry has no 'name': {entry!r}")
        if name in seen_names:
            raise ManifestError(f"duplicate library name in manifest: {name!r}")
        seen_names.add(name)

        file = entry.get("file")
        if not file:
            raise ManifestError(f"library {name!r} has no 'file'")

        fragment_type = entry.get("fragment_type")
        if fragment_type not in FRAGMENT_TYPES:
            permitted = ", ".join(sorted(FRAGMENT_TYPES))
            raise ManifestError(
                f"library {name!r} has unknown fragment_type {fragment_type!r} "
                f"(permitted: {permitted})"
            )

        signal_key = entry.get("signal_key")
        if fragment_type == "filler" and signal_key is not None:
            raise ManifestError(
                f"library {name!r} is filler but declares signal_key {signal_key!r}; "
                "filler fragments carry no signal"
            )
        if fragment_type != "filler" and signal_key is None:
            raise ManifestError(
                f"library {name!r} has fragment_type {fragment_type!r} but no signal_key; "
                "only filler libraries may omit one"
            )

        specs.append(
            LibrarySpec(
                name=name,
                file=file,
                signal_key=signal_key,
                fragment_type=fragment_type,
                subclass=entry.get("subclass"),
                category=entry.get("category"),
            )
        )
    return specs


def read_library(
    spec: LibrarySpec,
    base_dir: Path,
    *,
    folds: int | None = None,
    fold_index: int = 0,
    salt: str = "",
) -> list[Fragment]:
    """Read one library file into fragments, split already assigned.

    Blank lines are skipped. A leading cluster marker is stripped into
    ``cluster_id``, namespaced as ``{library}:{tag}``; the remainder is the
    verbatim text.

    ``folds``, ``fold_index`` and ``salt`` are passed straight to
    :func:`assign_split`; see there for what they mean.
    """
    path = base_dir / spec.file
    if not path.is_file():
        raise ManifestError(f"library {spec.name!r} declares missing file: {path}")

    fragments: list[Fragment] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tag, text = parse_line(line)
        if not normalise(text):
            continue
        cluster_id = f"{spec.name}:{tag}" if tag else None
        key = cluster_key(cluster_id, text)
        fragments.append(
            Fragment(
                fragment_id=make_fragment_id(spec.name, text),
                text=text,
                library=spec.name,
                signal_key=spec.signal_key,
                fragment_type=spec.fragment_type,
                subclass=spec.subclass,
                category=spec.category,
                cluster_id=cluster_id,
                split=assign_split(key, folds=folds, fold_index=fold_index, salt=salt),
            )
        )

    if not fragments:
        raise ManifestError(f"library {spec.name!r} resolved to zero non-blank lines: {path}")
    return fragments


def deduplicate(fragments: list[Fragment]) -> list[Fragment]:
    """Drop repeated normalised texts, globally rather than per library.

    There are currently no cross-library duplicates, so global deduplication is
    a no-op today. It exists because a future collision between, say, a
    ``fever_null`` library and ``tangents`` would be one text carrying two
    conflicting labels -- so a duplicate whose ``fragment_type`` disagrees is a
    hard error rather than a silent first-wins. Within a library the first
    occurrence is kept.
    """
    kept: dict[str, Fragment] = {}
    result: list[Fragment] = []
    for fragment in fragments:
        key = normalise(fragment.text)
        existing = kept.get(key)
        if existing is None:
            kept[key] = fragment
            result.append(fragment)
            continue
        if existing.fragment_type != fragment.fragment_type:
            raise ManifestError(
                f"text appears in {existing.library!r} as {existing.fragment_type!r} and in "
                f"{fragment.library!r} as {fragment.fragment_type!r}, so it carries two "
                f"conflicting labels: {fragment.text!r}"
            )
    return result


def empty_cells(fragments: list[Fragment], specs: list[LibrarySpec]) -> list[str]:
    """Return the ``library/split`` cells holding no fragments, in library order."""
    populated: dict[str, set[str]] = defaultdict(set)
    for fragment in fragments:
        populated[fragment.library].add(fragment.split)

    return [
        f"{spec.name}/{split}"
        for spec in specs
        for split in SPLITS
        if split not in populated[spec.name]
    ]


def check_no_empty_cells(
    fragments: list[Fragment], specs: list[LibrarySpec], *, hint: str = ""
) -> None:
    """Assert every (library, split) cell holds at least one fragment.

    Hash-based splitting only approximates 70/15/15 on small libraries, so a
    sub-class can plausibly land zero fragments in a split. A silent empty cell
    makes a whole sub-class invisible to evaluation; this makes it loud.

    The guard runs over the *whole* manifest, before anything filters by signal,
    so a library for an unrelated signal can block a run. That is deliberate;
    ``hint`` exists so fold mode can say what to do about it rather than
    weakening it.
    """
    empty = empty_cells(fragments, specs)
    if empty:
        raise ManifestError(
            "these (library, split) cells are empty, so a sub-class would be invisible to "
            f"evaluation: {', '.join(empty)}{hint}"
        )


def load_fragments(
    manifest_path: Path,
    *,
    check_cells: bool = True,
    folds: int | None = None,
    fold_index: int = 0,
    salt: str = "",
) -> list[Fragment]:
    """Load, validate, deduplicate and split every declared library.

    ``check_cells=False`` skips the empty-cell guard. That is for the reporting
    tools only: a lint that refuses to run because the libraries are unbalanced
    is useless exactly when it is most needed, since diagnosing that imbalance
    is part of its job. Generation always keeps the guard on.

    ``folds``, ``fold_index`` and ``salt`` select fold mode; see
    :func:`assign_split`.
    """
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs = parse_manifest(payload)

    base_dir = manifest_path.parent
    fragments: list[Fragment] = []
    for spec in specs:
        fragments.extend(
            read_library(spec, base_dir, folds=folds, fold_index=fold_index, salt=salt)
        )

    fragments = deduplicate(fragments)
    if check_cells:
        hint = (
            ""
            if folds is None
            else (
                f"; this is fold {fold_index} of {folds} under salt {salt!r} -- run "
                "--find-fold-salt to list the salts that populate every bucket of "
                "every library"
            )
        )
        check_no_empty_cells(fragments, specs, hint=hint)
    return fragments


def library_clusters(fragments: Iterable[Fragment]) -> list[tuple[str, str]]:
    """Return the distinct ``(library, cluster_key)`` pairs, in a stable order.

    The unit of splitting, and therefore the unit every coverage question is
    asked in. Clustered siblings collapse to one pair, which is the point:
    ``fever_null_hedged``'s three validation fragments are two ideas.
    """
    return sorted({(f.library, cluster_key(f.cluster_id, f.text)) for f in fragments})


def bucket_coverage(fragments: Iterable[Fragment], *, folds: int, salt: str) -> dict[str, set[int]]:
    """Return, per library, which of ``folds`` buckets its clusters populate."""
    coverage: dict[str, set[int]] = defaultdict(set)
    for library, key in library_clusters(fragments):
        coverage[library].add(fold_bucket(key, folds, salt))
    return dict(coverage)


def find_fold_salts(fragments: Iterable[Fragment], *, folds: int, limit: int) -> list[str]:
    """Return the integer salts below ``limit`` that leave no library short of a bucket.

    A library that misses a bucket empties a cell in at least one fold, which
    :func:`check_no_empty_cells` refuses -- and because that guard covers the
    whole manifest, an unrelated library's unlucky assignment blocks every
    signal. Searching for a salt is the honest fix; weakening the guard is not.

    Passing is a floor, not a health signal. ``dysuria_null_thirdparty`` has
    seven clusters, so surjecting onto five buckets leaves some fold's test cell
    holding exactly one idea. The salt makes the run start; it does not make the
    cell worth reading.
    """
    clusters = library_clusters(fragments)
    found: list[str] = []
    for candidate in range(limit):
        salt = str(candidate)
        coverage: dict[str, set[int]] = defaultdict(set)
        for library, key in clusters:
            coverage[library].add(fold_bucket(key, folds, salt))
        if all(len(buckets) == folds for buckets in coverage.values()):
            found.append(salt)
    return found
