"""Fragment library loading, deduplication and cluster-aware splitting.

Library discovery is an explicit manifest, never a glob: ``data/synthetic/``
also holds ``scratch/``, which contains working notes (``fever_synonyms.jsonl``)
and an unfinished generator spec (``fever_true.yaml``) that a filename-convention
glob would inject straight into training text. Files on disk but absent from the
manifest are ignored; files in the manifest but absent from disk are a hard
error. Library files live under ``symptoms/<signal>/`` and ``filler/``, so a
manifest ``file`` is a relative path rather than a bare filename.

Splitting hashes the *cluster* key rather than the text. ``fever_null`` is two
generation batches over the same concept list, reworded, so text-level
deduplication catches only the two exact duplicates and hash-splitting would
scatter paraphrase twins across the train/val boundary. That is precisely the
lexical leakage fragment-level splitting exists to prevent, and it would bias
validation upward rather than merely adding noise.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
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


def assign_split(cluster_key: str) -> str:
    """Map a cluster key to ``train``/``val``/``test`` via a stable hash.

    Deterministic across processes and unaffected by ``PYTHONHASHSEED``, so no
    split-assignment file needs storing and the assignment stays stable as
    libraries grow. Python's built-in ``hash()`` is salted per process and is
    deliberately not used.
    """
    bucket = int(hashlib.sha256(cluster_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    for upper, split in _SPLIT_BANDS:
        if bucket < upper:
            return split
    raise AssertionError(f"unreachable: bucket {bucket} outside 0-99")


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


def read_library(spec: LibrarySpec, base_dir: Path) -> list[Fragment]:
    """Read one library file into fragments, split already assigned.

    ``spec.file`` is a path relative to the manifest, and must stay inside the
    manifest's own directory: the libraries are the training corpus, so a
    ``file`` that escapes upwards would silently widen what counts as one.

    Blank lines are skipped. A leading cluster marker is stripped into
    ``cluster_id``, namespaced as ``{library}:{tag}``; the remainder is the
    verbatim text.
    """
    path = base_dir / spec.file
    if not path.resolve().is_relative_to(base_dir.resolve()):
        raise ManifestError(
            f"library {spec.name!r} declares file {spec.file!r}, which resolves outside "
            f"the manifest directory {base_dir}"
        )
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
        cluster_key = cluster_id or normalise(text)
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
                split=assign_split(cluster_key),
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


def check_no_empty_cells(fragments: list[Fragment], specs: list[LibrarySpec]) -> None:
    """Assert every (library, split) cell holds at least one fragment.

    Hash-based splitting only approximates 70/15/15 on small libraries, so a
    sub-class can plausibly land zero fragments in a split. A silent empty cell
    makes a whole sub-class invisible to evaluation; this makes it loud.
    """
    empty = empty_cells(fragments, specs)
    if empty:
        raise ManifestError(
            "these (library, split) cells are empty, so a sub-class would be invisible to "
            f"evaluation: {', '.join(empty)}"
        )


def load_fragments(manifest_path: Path, *, check_cells: bool = True) -> list[Fragment]:
    """Load, validate, deduplicate and split every declared library.

    ``check_cells=False`` skips the empty-cell guard. That is for the reporting
    tools only: a lint that refuses to run because the libraries are unbalanced
    is useless exactly when it is most needed, since diagnosing that imbalance
    is part of its job. Generation always keeps the guard on.
    """
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs = parse_manifest(payload)

    base_dir = manifest_path.parent
    fragments: list[Fragment] = []
    for spec in specs:
        fragments.extend(read_library(spec, base_dir))

    fragments = deduplicate(fragments)
    if check_cells:
        check_no_empty_cells(fragments, specs)
    return fragments
