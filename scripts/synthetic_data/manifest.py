"""Fragment library loading, deduplication and cluster-aware splitting.

Library discovery is an explicit manifest, never a glob. The manifest is what
says a file is a library *and* what it means -- signal, polarity, sub-class and
its ``null_on`` declarations about every other signal -- none of which a path
can carry. A glob would also make two faults silent that are loud today: any
``.txt`` dropped into the tree becomes training text, and a rename relabels a
library rather than failing. Files on disk but absent from the manifest are
ignored; files in the manifest but absent from disk are a hard error.

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
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .normalise import normalise

#: Permitted values for a library's ``fragment_type``.
#:
#: ``declarative`` is the JSONL-only member (:data:`LIBRARY_FORMATS`). Unlike
#: every other type it says nothing about what a line asserts: a declarative
#: library's lines each carry their own label vector, because a fragment
#: asserting fever true and dysuria false has no single polarity a filename
#: could carry.
FRAGMENT_TYPES = frozenset(
    {"positive", "negative", "ambiguous", "confounder", "filler", "declarative"}
)

#: The fragment type a JSONL library must declare, and the one type a text
#: library may not.
DECLARATIVE_TYPE = "declarative"

#: Permitted values for a library's ``format``. ``text`` is the default and the
#: 49 hand-written libraries stay on it: their ``fragment_id`` hashes the text
#: and their split hashes the cluster key, so a format change that moved either
#: would move every dataset ever generated, and a single-signal library's vector
#: is already derivable from ``fragment_type`` plus ``null_on``.
LIBRARY_FORMATS = frozenset({"text", "jsonl"})

#: A fragment's own-signal polarity, projected onto the label its own head would
#: carry. It lives here rather than in the recombiner because it is now half of
#: how a text library's per-line vector is *derived* (:func:`derive_labels`), and
#: a derivation reading its table from the module that does the drawing would be
#: a second source for a fact the manifest already states.
#:
#: ``filler`` and ``declarative`` never appear. Neither has an own signal: a
#: filler fragment's contribution to any signal comes from its ``null_on``
#: declaration, and a declarative line's comes from the line.
#:
#: ``ambiguous`` and ``confounder`` both map to ``None`` rather than being
#: absent, which is the point of the ``null_ambiguous`` mode: a confounder
#: *asserts* that the correct label is "not mentioned", it does not decline to
#: say.
FRAGMENT_TYPE_LABELS: Mapping[str, bool | None] = {
    "positive": True,
    "negative": False,
    "ambiguous": None,
    "confounder": None,
}

#: Permitted values for a ``null_on`` entry's ``basis``, and the whole of the
#: distinction the lint acts on.
#:
#: ``absent``
#:     The library never mentions the signal at all. This is the half a lexicon
#:     can check, so a lexicon hit against an ``absent`` pair is a **failure**
#:     rather than a judgement call.
#: ``policy``
#:     The library *does* talk about the signal and the correct label is ``null``
#:     anyway -- ``uti_speculation`` on ``recent_uti_present``, where forty lines
#:     name an infection and none places one inside the 30-day window. No lexicon
#:     can check this, so the entry carries a ``note`` giving the rule that makes
#:     it ``null`` and the lint *lists* the pair with its matched-line count
#:     instead of failing on it.
NULL_ON_BASES = frozenset({"absent", "policy"})

#: Keys permitted inside one ``null_on`` entry. Closed rather than open so a
#: typo ("notes") is an error instead of a note that silently does not exist.
_NULL_ON_KEYS = frozenset({"basis", "note"})

#: Keys permitted on one JSONL library line. Closed for the reason
#: :data:`_NULL_ON_KEYS` is: a typo has to be an error rather than a field that
#: silently does not exist.
_JSONL_KEYS = frozenset({"text", "labels", "cluster", "meta"})

#: The keys a JSONL line may not omit. ``cluster`` is required rather than
#: optional because a generated library's lines are near-duplicates of their
#: siblings by construction, so an untagged line would be split on its own text
#: and scatter a cluster across the train/val boundary.
_JSONL_REQUIRED_KEYS = frozenset({"text", "labels", "cluster"})


#: Split names, in band order.
SPLITS = ("train", "val", "test")

#: Upper bound (exclusive) of each split's band over ``hash % 100``: 70/15/15.
_SPLIT_BANDS = ((70, "train"), (85, "val"), (100, "test"))

#: A leading cluster marker, e.g. ``[c03] My colleague...``.
_CLUSTER_MARKER = re.compile(r"^\[([A-Za-z0-9_]+)\]\s+")


class ManifestError(ValueError):
    """Raised when the manifest, or the libraries it declares, are invalid."""


class _Undeclared:
    """The type of :data:`UNDECLARED`; not instantiated anywhere else."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNDECLARED"


#: What :meth:`Fragment.value_for` returns for a signal a fragment says nothing
#: about, and deliberately **not** ``None``. The whole of section 7's
#: missing-key-versus-``null`` distinction rides on those two being different: a
#: missing key masks that head's loss, and ``None`` supervises it towards "not
#: mentioned". Compare with ``is``; it has no meaningful truthiness.
UNDECLARED = _Undeclared()


@dataclass(frozen=True)
class NullOn:
    """One library's declaration that a *foreign* signal is ``null`` on its lines.

    "Foreign" is the whole of it: a library's own signal's value comes from
    ``fragment_type`` and always has, and two sources for one value is one that
    can disagree with itself. So this only ever carries ``null`` -- there is no
    cross-signal ``true`` or ``false`` state, because that is a per-*line* fact
    over libraries whose lines disagree (three of ``flank_pain_false``'s
    fifty-five lines assert dysuria), and a per-line fact needs the per-line
    label vectors that section 12.3 describes and this does not have.

    Absent means **undeclared**, not ``null``. A library says nothing about a
    signal it does not name here, and an undeclared pair is simply ineligible.
    That is deliberate: a closed-world default would mean adding an eighth
    signal silently asserted that all 48 existing libraries were silent about
    it, and ``uti_speculation`` is the standing evidence that a library nobody
    has read against a signal is not the same as a library that is silent on it.
    """

    signal: str
    basis: str
    note: str = ""


@dataclass(frozen=True)
class LibrarySpec:
    """One declared fragment library, as it appears in the manifest."""

    name: str
    file: str
    signal_key: str | None
    fragment_type: str
    subclass: str | None = None
    category: str | None = None
    #: Sorted by signal, so two manifests that declare the same pairs in a
    #: different order produce identical specs.
    null_on: tuple[NullOn, ...] = ()
    #: One of :data:`LIBRARY_FORMATS`. Defaults to ``text``, so an entry written
    #: before the field existed means what it always meant.
    format: str = "text"


def derive_labels(
    *, signal_key: str | None, fragment_type: str, null_on: Iterable[NullOn]
) -> dict[str, bool | None]:
    """Return the label vector every line of a *text* library carries.

    The two facts the manifest already states, read in one place: the library's
    own signal takes its value from ``fragment_type``, and every foreign signal
    it declares is ``null``. Anything else is absent from the result, which is
    what :data:`UNDECLARED` means.

    Sorted, so a vector's iteration order never depends on the order a manifest
    listed its ``null_on`` pairs in.
    """
    labels: dict[str, bool | None] = {entry.signal: None for entry in null_on}
    if signal_key is not None:
        if fragment_type not in FRAGMENT_TYPE_LABELS:
            raise ManifestError(
                f"fragment_type {fragment_type!r} carries a signal_key {signal_key!r} but has "
                "no own-signal polarity; only a per-line vector can say what it asserts"
            )
        labels[signal_key] = FRAGMENT_TYPE_LABELS[fragment_type]
    return dict(sorted(labels.items()))


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
    #: Resolved from the library spec at load time, so nothing downstream reads
    #: the manifest a second time. Section 7 rejects a second source of one fact
    #: for the same reason it rejects a second provenance block: the two can
    #: drift and only one of them is right.
    null_on: tuple[NullOn, ...] = ()
    #: This fragment's per-line label vector: every signal it has a known status
    #: for, mapped to ``True`` / ``False`` / ``None``. A signal *absent* from it
    #: is undeclared, and that is not the same as ``None`` -- see
    #: :meth:`value_for`.
    #:
    #: Passed ``None`` by a caller that has not got one, which is every text
    #: library: the vector is then derived by :func:`derive_labels` from
    #: ``(signal_key, fragment_type, null_on)``, so the two representations agree
    #: by construction rather than by maintenance. A JSONL library passes the
    #: line's own vector instead. It is one field either way, so nothing
    #: downstream has to know which format a fragment came from. Never ``None``
    #: after construction.
    labels: Mapping[str, bool | None] | None = None

    def __post_init__(self) -> None:
        if self.labels is None:
            object.__setattr__(
                self,
                "labels",
                derive_labels(
                    signal_key=self.signal_key,
                    fragment_type=self.fragment_type,
                    null_on=self.null_on,
                ),
            )

    def value_for(self, signal: str) -> bool | None | _Undeclared:
        """Return this fragment's value for ``signal``, or :data:`UNDECLARED`.

        Four states, not three: ``True`` and ``False`` are assertions, ``None``
        is a declared silence that supervises a head towards "not mentioned",
        and :data:`UNDECLARED` is "nobody has decided", which earns no key at
        all. Returning ``None`` for the last of those would teach every head to
        answer "not mentioned" to every question it was never trained on.
        """
        if self.labels is not None and signal in self.labels:
            return self.labels[signal]
        return UNDECLARED

    def null_on_basis(self, signal: str) -> str | None:
        """Return the declared basis for ``signal``, or ``None`` if undeclared."""
        for entry in self.null_on:
            if entry.signal == signal:
                return entry.basis
        return None

    def declares_null_on(self, signal: str) -> bool:
        """Whether this fragment's library declares ``signal`` ``null`` on every line."""
        return self.null_on_basis(signal) is not None


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


def parse_null_on(
    payload: object, *, library: str, own_signal: str | None, signals: Collection[str] | None
) -> tuple[NullOn, ...]:
    """Validate one library's ``null_on`` block and return it sorted by signal.

    The block is an object keyed by signal rather than a list of objects, which
    buys the duplicate check for free: a repeated signal is a duplicate JSON key
    within one object, and ``test_the_manifest_has_no_duplicate_json_keys``
    already walks every object in the manifest looking for exactly that. A list
    would need its own duplicate check and would not be covered by the guard
    that already exists.

    ``signals`` is the set of signals the run's ruleset sends to the encoder.
    When it is given, a declaration naming anything else is an error -- that is
    what catches a typo, since a misspelled signal is otherwise indistinguishable
    from a pair nobody declared. It is optional because the reporting tools load
    the manifest without a ruleset, and a lint that refuses to run because the
    manifest is wrong is useless exactly when it is needed.
    """
    if payload is None:
        return ()
    if not isinstance(payload, dict):
        raise ManifestError(
            f"library {library!r} has a 'null_on' that is not an object keyed by signal: "
            f"{payload!r}"
        )

    entries: list[NullOn] = []
    for signal, body in payload.items():
        if signal == own_signal:
            raise ManifestError(
                f"library {library!r} declares null_on for its own signal {signal!r}; that "
                "value comes from fragment_type, and two sources for one value is one that "
                "can disagree with itself"
            )
        if signals is not None and signal not in signals:
            raise ManifestError(
                f"library {library!r} declares null_on for {signal!r}, which the ruleset "
                f"does not send to the encoder (known: {', '.join(sorted(signals))})"
            )
        if not isinstance(body, dict):
            raise ManifestError(
                f"library {library!r} has a null_on entry for {signal!r} that is not an "
                f"object: {body!r}"
            )
        unknown = sorted(set(body) - _NULL_ON_KEYS)
        if unknown:
            raise ManifestError(
                f"library {library!r} has unknown key(s) {', '.join(unknown)} in its "
                f"null_on entry for {signal!r} (permitted: basis, note)"
            )
        basis = body.get("basis")
        if basis not in NULL_ON_BASES:
            permitted = ", ".join(sorted(NULL_ON_BASES))
            raise ManifestError(
                f"library {library!r} declares null_on for {signal!r} with unknown basis "
                f"{basis!r} (permitted: {permitted})"
            )
        note = body.get("note", "")
        if not isinstance(note, str):
            raise ManifestError(
                f"library {library!r} has a non-string note in its null_on entry for "
                f"{signal!r}: {note!r}"
            )
        if basis == "policy" and not note.strip():
            raise ManifestError(
                f"library {library!r} declares null_on for {signal!r} with basis 'policy' "
                "and no note; a policy claim is the half no lexicon can check, so the rule "
                "that makes the label null has to be written down"
            )
        entries.append(NullOn(signal=signal, basis=basis, note=note))

    return tuple(sorted(entries, key=lambda entry: entry.signal))


def parse_manifest(payload: dict, *, signals: Collection[str] | None = None) -> list[LibrarySpec]:
    """Validate the manifest's metadata and return its library specs.

    Checks that do not need the filesystem happen here: permitted
    ``fragment_type``, unique ``name``, ``signal_key``/``fragment_type``
    agreement, the ``format`` field and what it excludes, and the ``null_on``
    block (:func:`parse_null_on`).

    **Format and label source are one decision.** A ``jsonl`` library must
    declare ``fragment_type: "declarative"`` and must declare neither
    ``signal_key`` nor ``null_on``, because both are library-*level* statements
    about what every line means and a declarative library's lines each state
    that for themselves. Permitting both would be two sources for one value,
    which is the reason section 4 gives for not letting a library declare
    ``null_on`` for its own signal: two sources can disagree, and only one of
    them is right.
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

        library_format = entry.get("format", "text")
        if library_format not in LIBRARY_FORMATS:
            permitted = ", ".join(sorted(LIBRARY_FORMATS))
            raise ManifestError(
                f"library {name!r} has unknown format {library_format!r} (permitted: {permitted})"
            )

        signal_key = entry.get("signal_key")
        if library_format == "jsonl":
            if fragment_type != DECLARATIVE_TYPE:
                raise ManifestError(
                    f"library {name!r} has format 'jsonl' but fragment_type "
                    f"{fragment_type!r}; a JSONL library's lines carry a label vector each, "
                    f"so its only permitted fragment_type is {DECLARATIVE_TYPE!r}"
                )
            for field in ("signal_key", "null_on"):
                if entry.get(field) is not None:
                    raise ManifestError(
                        f"library {name!r} has format 'jsonl' and also declares {field!r}; "
                        "that is a library-level statement about every line, and this "
                        "library's lines each carry their own label vector"
                    )
        else:
            if fragment_type == DECLARATIVE_TYPE:
                raise ManifestError(
                    f"library {name!r} has fragment_type {DECLARATIVE_TYPE!r} but format "
                    "'text'; a text line has nowhere to carry a label vector, so the type "
                    "is only meaningful with format 'jsonl'"
                )
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
                null_on=parse_null_on(
                    entry.get("null_on"),
                    library=name,
                    own_signal=signal_key,
                    signals=signals,
                ),
                format=library_format,
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
                null_on=spec.null_on,
            )
        )

    if not fragments:
        raise ManifestError(f"library {spec.name!r} resolved to zero non-blank lines: {path}")
    return fragments


def parse_jsonl_labels(
    payload: object, *, where: str, signals: Collection[str] | None
) -> dict[str, bool | None]:
    """Validate one JSONL line's ``labels`` object and return it sorted by signal.

    Three states are expressible and the fourth is expressed by omission:
    ``true`` and ``false`` assert, ``null`` declares the line silent on that
    signal, and a signal the object does not name is undeclared -- exactly as in
    ``null_on`` (section 4), and earning no key downstream for the same reason.

    ``signals`` is the run's encoder signals when they are known; a line naming
    anything else is an error, since a misspelled signal is otherwise
    indistinguishable from one nobody declared. It is optional because the
    reporting tools load the manifest without a ruleset.
    """
    if not isinstance(payload, dict):
        raise ManifestError(
            f"{where} has a 'labels' that is not an object keyed by signal: {payload!r}"
        )
    if not payload:
        raise ManifestError(
            f"{where} has an empty 'labels'; a line that states nothing about any signal is "
            "filler, and filler belongs in a filler library"
        )

    labels: dict[str, bool | None] = {}
    for signal, value in payload.items():
        if signals is not None and signal not in signals:
            raise ManifestError(
                f"{where} labels {signal!r}, which the ruleset does not send to the encoder "
                f"(known: {', '.join(sorted(signals))})"
            )
        if value is not None and not isinstance(value, bool):
            raise ManifestError(
                f"{where} has a non-boolean, non-null value for {signal!r}: {value!r} "
                "(true asserts, false denies, null declares the line silent, and omitting "
                "the signal leaves it undeclared)"
            )
        labels[signal] = value
    return dict(sorted(labels.items()))


def read_jsonl_library(
    spec: LibrarySpec,
    base_dir: Path,
    *,
    folds: int | None = None,
    fold_index: int = 0,
    salt: str = "",
    signals: Collection[str] | None = None,
) -> list[Fragment]:
    """Read one JSONL library into fragments, split already assigned.

    One JSON object per line; blank lines are skipped. The line's ``labels``
    become the fragment's vector directly -- nothing about a JSONL fragment's
    meaning is read from its library, which is the whole reason the format
    exists.

    ``fragment_id``, ``cluster_id`` and the split are computed exactly as they
    are for a text library (:func:`read_library`): the id hashes the normalised
    text, the cluster is namespaced ``{library}:{tag}`` as a ``[c01]`` marker is,
    and the split hashes the cluster key. A generated library is a committed
    build artefact and the machinery must not be able to tell it apart.
    """
    path = base_dir / spec.file
    if not path.is_file():
        raise ManifestError(f"library {spec.name!r} declares missing file: {path}")

    fragments: list[Fragment] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        where = f"library {spec.name!r} line {number}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{where} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ManifestError(f"{where} is not a JSON object: {payload!r}")

        unknown = sorted(set(payload) - _JSONL_KEYS)
        if unknown:
            raise ManifestError(
                f"{where} has unknown key(s) {', '.join(unknown)} "
                f"(permitted: {', '.join(sorted(_JSONL_KEYS))})"
            )
        missing = sorted(_JSONL_REQUIRED_KEYS - set(payload))
        if missing:
            raise ManifestError(f"{where} is missing required key(s) {', '.join(missing)}")

        text = payload["text"]
        if not isinstance(text, str) or not normalise(text):
            raise ManifestError(f"{where} has a blank or non-string 'text': {text!r}")

        cluster = payload["cluster"]
        if not isinstance(cluster, str) or not cluster.strip():
            raise ManifestError(f"{where} has a blank or non-string 'cluster': {cluster!r}")

        meta = payload.get("meta", {})
        if not isinstance(meta, dict):
            raise ManifestError(f"{where} has a 'meta' that is not an object: {meta!r}")

        labels = parse_jsonl_labels(payload["labels"], where=where, signals=signals)
        cluster_id = f"{spec.name}:{cluster.strip()}"
        key = cluster_key(cluster_id, text)
        fragments.append(
            Fragment(
                fragment_id=make_fragment_id(spec.name, text),
                text=text,
                library=spec.name,
                # A declarative fragment has no *one* signal, so the scalar stays
                # empty and everything downstream reads the vector instead.
                signal_key=None,
                fragment_type=spec.fragment_type,
                subclass=spec.subclass,
                category=spec.category,
                cluster_id=cluster_id,
                split=assign_split(key, folds=folds, fold_index=fold_index, salt=salt),
                null_on=(),
                labels=labels,
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
        if existing.labels != fragment.labels:
            # Two declarative lines share a fragment_type, so the check above
            # cannot see a collision between them. Their vectors are the whole
            # of what they claim, and first-wins on a disagreement is how a
            # dataset acquires a wrong label.
            raise ManifestError(
                f"text appears in {existing.library!r} with labels {dict(existing.labels)} "
                f"and in {fragment.library!r} with labels {dict(fragment.labels)}, so it "
                f"carries two conflicting labels: {fragment.text!r}"
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
    signals: Collection[str] | None = None,
) -> list[Fragment]:
    """Load, validate, deduplicate and split every declared library.

    ``check_cells=False`` skips the empty-cell guard. That is for the reporting
    tools only: a lint that refuses to run because the libraries are unbalanced
    is useless exactly when it is most needed, since diagnosing that imbalance
    is part of its job. Generation always keeps the guard on.

    ``folds``, ``fold_index`` and ``salt`` select fold mode; see
    :func:`assign_split`.

    ``signals`` is passed straight to :func:`parse_null_on`; generation supplies
    the ruleset's encoder signals so a misspelled declaration fails at startup,
    and the reporting tools leave it out.
    """
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs = parse_manifest(payload, signals=signals)

    base_dir = manifest_path.parent
    fragments: list[Fragment] = []
    for spec in specs:
        if spec.format == "jsonl":
            fragments.extend(
                read_jsonl_library(
                    spec,
                    base_dir,
                    folds=folds,
                    fold_index=fold_index,
                    salt=salt,
                    signals=signals,
                )
            )
        else:
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
