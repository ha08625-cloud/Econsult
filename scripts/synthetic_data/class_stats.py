"""Measure the hand-written libraries against the swap-class candidate lists.

The v2 expansion plan chooses which swap classes are worth authoring from
occurrence counts over ``data/synthetic/**/*.txt``, and the numbers it was
drafted against do not reproduce: referent occurrences are ~25% higher than
claimed and healthcare ~20% lower (v2 review, F1). This module is the
committed instrument those tables are regenerated from, so a later pass can
tell a library edit from a counting error (DD15).

Run it::

    python -m scripts.synthetic_data.class_stats

It **prints and does not assert**. It is an instrument rather than a gate: its
job is to change what gets authored, and a class that measures badly is a class
to drop in review, not a build to fail. The gate on the files that eventually
get authored is ``--dry-run-lint`` and the committed-file tests (DD10, DD13).

Three things it makes visible before authoring rather than after:

* **occurrences per member**, which is the only honest input to "is this class
  worth a review". A member with zero occurrences is not useless -- it can still
  be a ``replace`` and widen the target vocabulary (DD14) -- but a member that
  is neither a reachable ``find`` nor a plausible ``replace`` is authoring cost
  for nothing;
* **which members are frozen** by :data:`~scripts.synthetic_data.noise.STRUCTURAL_FROZEN`,
  which is what DD6a exists to unlock and therefore what sizes it;
* **determiner context per member**, which is how the "a other half" fault
  (review F6) is seen before a vowel-initial member is authored rather than
  after it has produced broken English on 17 sites.

**The counting is deliberately not routed through**
:func:`~scripts.synthetic_data.manifest.load_fragments`. The manifest also
carries the 1,000-line generated ``declarative_v1`` library, which holds zero
members of any candidate class and is not drawn at the shipped
``--declarative-share 0.0``; counting it would put a 1,000-line zero into every
denominator. Reading the ``*.txt`` files directly gives the 49 files and 2,506
non-blank non-comment lines the plan names.

Whole-word matching uses ``(?<!\\w)term(?!\\w)`` on the lowercased line, which
is the rule :func:`~scripts.synthetic_data.expand.match_sites` applies when a
rule actually fires. It is a close approximation rather than a call into that
function because ``match_sites`` needs :class:`~scripts.synthetic_data.expand.Rule`
objects, which is Task 3's loader and does not exist yet.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .lint import SIGNAL_LEXICONS, lexicon_matches
from .noise import STRUCTURAL_FROZEN, fold_token


class ClassStatsError(RuntimeError):
    """A candidate list this module refuses to guess at."""


#: The hand-written libraries. Not the manifest: see the module docstring.
LIBRARY_ROOT = Path("data/synthetic")

#: Where Task 3's authored class files land. Read if present, so this module is
#: usable before the format exists and still usable after.
CLASSES_ROOT = Path("data/expansion/classes")

#: Determiners counted in the context section. ``a``/``an`` are the pair review
#: F6 turns on; the possessives are here because a referent swap that moves
#: between "my X" and "the X" registers is a different (and unchecked) kind of
#: edit from one that does not.
DETERMINERS = ("a", "an", "the", "my", "our", "his", "her", "their")

#: The candidate lists of the provisional plan's section 3, with the two splits
#: the plan and review require: the child group four ways (DD11: number and
#: gender are declared per class, so "kids" and "kid" cannot share a list) and
#: healthcare three ways.
#:
#: These are *candidates*, not authored classes. ``practice``, ``surgery`` and
#: ``other half`` are deliberately still here despite review F5 and F6 having
#: already ruled against them: the determiner section is the evidence for those
#: findings, and an instrument that omits the members its own output condemns
#: cannot be re-run to check them.
CANDIDATE_CLASSES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "referent",
        "adult_female",
        ("mum", "mummy", "mother", "wife", "missus", "sister", "aunt", "auntie", "girlfriend"),
    ),
    (
        "referent",
        "adult_male",
        ("dad", "daddy", "father", "husband", "brother", "uncle", "boyfriend"),
    ),
    (
        "referent",
        "elder_female",
        ("nan", "nanna", "nana", "gran", "granny", "grandma", "grandmother"),
    ),
    ("referent", "elder_male", ("grandad", "granddad", "grandpa", "grandfather", "gramps")),
    (
        "referent",
        "adult_neutral",
        (
            "partner",
            "other half",
            "friend",
            "neighbour",
            "colleague",
            "coworker",
            "cousin",
            "flatmate",
            "housemate",
            "mate",
            "boss",
            "carer",
        ),
    ),
    ("referent", "child_neutral_singular", ("kid", "child", "little one", "youngest", "eldest")),
    ("referent", "child_neutral_plural", ("kids", "children")),
    ("referent", "child_female", ("daughter", "girl")),
    ("referent", "child_male", ("son", "boy")),
    (
        "calendar",
        "weekday",
        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
    ),
    ("setting", "healthcare_place", ("surgery", "practice", "clinic")),
    ("setting", "healthcare_person", ("gp", "doctor", "nurse", "clinician")),
    ("setting", "healthcare_encounter", ("appointment", "consultation", "call-back")),
    ("affect", "worry", ("worried", "concerned", "anxious", "nervous", "uneasy", "on edge")),
)


@dataclass(frozen=True)
class Corpus:
    """The hand-written libraries, read as lines.

    ``lines`` is every non-blank, non-``#`` line of every ``*.txt`` under the
    root, lowercased once here so that no counting path can forget to.
    """

    files: tuple[Path, ...]
    lines: tuple[str, ...]


@dataclass(frozen=True)
class CandidateClass:
    """One candidate swap class: a group, an id and its members."""

    group: str
    class_id: str
    members: tuple[str, ...]

    @property
    def pairs(self) -> int:
        """Ordered pairs the loader would generate from this list."""
        count = len(self.members)
        return count * (count - 1)


@dataclass(frozen=True)
class MemberStats:
    """What the corpus says about one member of one candidate class."""

    member: str
    occurrences: int
    lines: int
    #: Tokens of the member that sit in ``STRUCTURAL_FROZEN``. Non-empty means
    #: every pair touching this member is refused by expansion's layer 2 today.
    frozen_tokens: tuple[str, ...]
    #: ``signal:term`` for every signal lexicon the bare member matches. Should
    #: be empty for every member: a member that reads as a signal is a member
    #: whose swap can change a label.
    lexicon_hits: tuple[str, ...]
    #: Determiner immediately before the member, counted per occurrence.
    #: ``bare`` is "no determiner from :data:`DETERMINERS` directly before it".
    determiners: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ClassStats:
    """One candidate class measured against the corpus."""

    candidate: CandidateClass
    members: tuple[MemberStats, ...]
    #: Lines carrying at least one occurrence of any member of this class.
    lines_with_any: int
    #: Lines carrying more than one -- the DD12 collision opportunity, and the
    #: reason the memo and per-class injectivity are not theoretical.
    lines_with_multiple: int

    @property
    def occurrences(self) -> int:
        return sum(member.occurrences for member in self.members)

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(m.member for m in self.members if not m.occurrences)

    @property
    def frozen(self) -> tuple[str, ...]:
        return tuple(m.member for m in self.members if m.frozen_tokens)

    @property
    def frozen_occurrences(self) -> int:
        return sum(m.occurrences for m in self.members if m.frozen_tokens)

    @property
    def lexicon(self) -> tuple[str, ...]:
        return tuple(m.member for m in self.members if m.lexicon_hits)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def load_corpus(root: Path = LIBRARY_ROOT) -> Corpus:
    """Read every hand-written library line under ``root``.

    Blank lines and ``#`` comments are dropped, which is the denominator the
    plan names and the one figure of its that reproduces: 49 files, 2,506
    lines.
    """
    files = tuple(sorted(root.rglob("*.txt")))
    if not files:
        raise ClassStatsError(f"no '*.txt' libraries under {root}")
    lines = tuple(
        stripped.lower()
        for path in files
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )
    return Corpus(files=files, lines=lines)


def load_candidates(classes_root: Path = CLASSES_ROOT) -> tuple[tuple[CandidateClass, ...], str]:
    """The classes to measure, and one line saying where they came from.

    Authored class files win when they exist, so that after Task 3 this module
    measures what is actually shipped rather than a copy of it that can drift.
    Only ``group``, ``classes``, ``id`` and ``members`` are read; every other
    key (the invariant, the declared gender and number) belongs to the loader
    and is deliberately not interpreted here.
    """
    paths = sorted(classes_root.glob("*.classes.json")) if classes_root.is_dir() else []
    if not paths:
        candidates = tuple(
            CandidateClass(group=group, class_id=class_id, members=members)
            for group, class_id, members in CANDIDATE_CLASSES
        )
        return candidates, f"hard-coded candidate lists (no '*.classes.json' under {classes_root})"
    return tuple(c for path in paths for c in _read_class_file(path)), (
        f"{len(paths)} class file(s) under {classes_root}"
    )


def _read_class_file(path: Path) -> list[CandidateClass]:
    """Parse one class file, refusing anything it would have to guess about."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ClassStatsError(f"{path}: unreadable class file: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("classes"), list):
        raise ClassStatsError(f"{path}: expected an object with a 'classes' list")
    group = payload.get("group", path.stem.removesuffix(".classes"))
    classes = []
    for entry in payload["classes"]:
        if not isinstance(entry, dict):
            raise ClassStatsError(f"{path}: every entry of 'classes' must be an object")
        class_id, members = entry.get("id"), entry.get("members")
        if not isinstance(class_id, str) or not isinstance(members, list):
            raise ClassStatsError(f"{path}: every class needs a string 'id' and a 'members' list")
        if not all(isinstance(member, str) for member in members):
            raise ClassStatsError(f"{path}: class {class_id!r} has a non-string member")
        classes.append(CandidateClass(group=str(group), class_id=class_id, members=tuple(members)))
    return classes


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


@cache
def member_pattern(member: str) -> re.Pattern[str]:
    """Whole-word, case-insensitive matcher for one member.

    ``(?<!\\w)`` / ``(?!\\w)`` rather than ``\\b`` so that a member ending in a
    non-word character (``call-back``) is still bounded on both sides the way
    ``match_sites`` bounds it.
    """
    return re.compile(rf"(?<!\w){re.escape(member.lower())}(?!\w)")


def frozen_tokens(member: str) -> tuple[str, ...]:
    """Which of ``member``'s tokens expansion's layer 2 holds frozen."""
    return tuple(
        folded for token in member.split() if (folded := fold_token(token)) in STRUCTURAL_FROZEN
    )


def lexicon_hits(member: str) -> tuple[str, ...]:
    """Every signal lexicon the bare member reads as, as ``signal:terms``."""
    return tuple(
        f"{signal}:{'/'.join(matched)}"
        for signal in SIGNAL_LEXICONS
        if (matched := lexicon_matches(member, signal))
    )


def _determiner_counts(member: str, lines: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    """Count the determiner directly before each occurrence of ``member``."""
    pattern = member_pattern(member)
    counts: Counter[str] = Counter()
    for line in lines:
        for match in pattern.finditer(line):
            before = re.search(r"(\w+)\W*$", line[: match.start()])
            word = before.group(1) if before else ""
            counts[word if word in DETERMINERS else "bare"] += 1
    return tuple((key, counts[key]) for key in (*DETERMINERS, "bare") if counts[key])


def measure_member(member: str, corpus: Corpus) -> MemberStats:
    """Measure one member against the corpus."""
    pattern = member_pattern(member)
    hits = [len(pattern.findall(line)) for line in corpus.lines]
    return MemberStats(
        member=member,
        occurrences=sum(hits),
        lines=sum(1 for count in hits if count),
        frozen_tokens=frozen_tokens(member),
        lexicon_hits=lexicon_hits(member),
        determiners=_determiner_counts(member, corpus.lines),
    )


def measure_class(candidate: CandidateClass, corpus: Corpus) -> ClassStats:
    """Measure one candidate class, including its own line-level collisions."""
    members = tuple(measure_member(member, corpus) for member in candidate.members)
    per_line = [
        sum(len(member_pattern(member).findall(line)) for member in candidate.members)
        for line in corpus.lines
    ]
    return ClassStats(
        candidate=candidate,
        members=members,
        lines_with_any=sum(1 for count in per_line if count),
        lines_with_multiple=sum(1 for count in per_line if count > 1),
    )


def group_lines(
    candidates: tuple[CandidateClass, ...], group: str, corpus: Corpus
) -> tuple[int, int]:
    """Lines carrying one member of ``group``, and lines carrying more than one.

    Measured across the group rather than per class because the plan's
    headline referent figure ("527 of 2,506 lines") is a group figure, and
    because DD12's collision is scoped to the class but its *opportunity* is
    not: "my wife and my brother" is two classes on one line.
    """
    members = tuple(
        member
        for candidate in candidates
        if candidate.group == group
        for member in candidate.members
    )
    per_line = [sum(len(member_pattern(m).findall(line)) for m in members) for line in corpus.lines]
    return sum(1 for count in per_line if count), sum(1 for count in per_line if count > 1)


# ---------------------------------------------------------------------------
# The reachable n-gram ceiling (DD15)
# ---------------------------------------------------------------------------

#: Window sizes the ceiling is reported at. Four is the one the v1 report
#: quoted; three and five are here because a single width is easy to pick after
#: the fact and a trend is not.
NGRAM_WIDTHS = (3, 4, 5)

#: Most lines carry no member at all and a handful carry three. The cap is a
#: guard against a future library line with a dozen, not a live constraint: it
#: is reported when it binds, and a report that never says "capped" is a report
#: whose numbers are exact.
MAX_LINE_VARIANTS = 100_000

#: Tokens for the n-gram count: runs of word characters and apostrophes, so
#: "haven't" is one token and "mother-in-law" is three. Deliberately cruder
#: than :func:`~scripts.synthetic_data.normalise.normalise`; the ceiling is a
#: ratio of two counts taken the same way, and the tokeniser cancels.
_TOKEN = re.compile(r"[\w']+")


@dataclass(frozen=True)
class NgramCeiling:
    """Distinct n-grams the libraries hold, and the number a swap set reaches."""

    width: int
    baseline: int
    reachable: int
    capped_lines: int

    @property
    def gain(self) -> float:
        return 100 * (self.reachable - self.baseline) / self.baseline if self.baseline else 0.0


def tokenise(text: str) -> list[str]:
    """Lowercased word tokens of one line."""
    return _TOKEN.findall(text.lower())


def _line_units(
    line: str, members_by_class: Sequence[tuple[str, ...]]
) -> list[tuple[tuple[str, ...], ...]]:
    """One line as a list of slots, each slot a tuple of token-tuple alternatives.

    A stretch of text that matches no member is a slot with exactly one
    alternative, so the whole line is one uniform structure and the caller does
    not branch. A stretch that matches member *m* of class *C* is a slot whose
    alternatives are every member of *C* including *m* itself -- ``m`` stays in
    because DEFAULT_CLEAN_SHARE means the unrewritten line is reachable too.

    Matching is longest-first and left-to-right, which is what
    :func:`~scripts.synthetic_data.expand.match_sites` does, so "mother in law"
    claims its span before the bare "mother" can.
    """
    lowered = line.lower()
    spans: list[tuple[int, int, tuple[str, ...]]] = []
    for members in members_by_class:
        for member in members:
            for match in member_pattern(member).finditer(lowered):
                spans.append((match.start(), match.end(), members))
    # Longest first at a position, then left to right, then drop overlaps.
    spans.sort(key=lambda span: (span[0], -(span[1] - span[0])))
    chosen: list[tuple[int, int, tuple[str, ...]]] = []
    cursor = 0
    for start, end, members in spans:
        if start < cursor:
            continue
        chosen.append((start, end, members))
        cursor = end

    units: list[tuple[tuple[str, ...], ...]] = []
    cursor = 0
    for start, end, members in chosen:
        units.append((tuple(tokenise(line[cursor:start])),))
        units.append(tuple(tuple(tokenise(member)) for member in members))
        cursor = end
    units.append((tuple(tokenise(line[cursor:])),))
    return units


def _line_variants(
    units: Sequence[tuple[tuple[str, ...], ...]], cap: int = MAX_LINE_VARIANTS
) -> tuple[list[list[str]], bool]:
    """Every token sequence the slots can produce, and whether the cap bound.

    Exact rather than sampled: the ceiling is a ceiling, and a sampled ceiling
    is a floor with a confusing name. When the cap binds the line contributes
    only its unrewritten form and the caller reports the count, so a capped run
    understates the ceiling and never overstates it.
    """
    total = 1
    for slot in units:
        total *= len(slot)
        if total > cap:
            return [[token for slot in units for token in slot[0]]], True
    variants: list[list[str]] = [[]]
    for slot in units:
        variants = [prefix + list(alternative) for prefix in variants for alternative in slot]
    return variants, False


def ngram_ceiling(
    candidates: Sequence[CandidateClass],
    corpus: Corpus,
    width: int,
) -> NgramCeiling:
    """Distinct ``width``-grams before and after ``candidates`` are let loose.

    The number the plan calls the reachable ceiling: not what a run produces,
    which depends on ``--rate`` and the draw, but what the vocabulary *could*
    produce if every site took every value. It is the honest upper bound on
    what this ticket buys, and it is code rather than prose because revision
    1's ``+25.8%`` had no committed provenance and did not reproduce (DD15).
    """
    members_by_class = tuple(candidate.members for candidate in candidates)
    baseline: set[tuple[str, ...]] = set()
    reachable: set[tuple[str, ...]] = set()
    capped = 0
    for line in corpus.lines:
        tokens = tokenise(line)
        baseline.update(
            tuple(tokens[index : index + width]) for index in range(len(tokens) - width + 1)
        )
        variants, was_capped = _line_variants(_line_units(line, members_by_class))
        capped += was_capped
        for variant in variants:
            reachable.update(
                tuple(variant[index : index + width]) for index in range(len(variant) - width + 1)
            )
    return NgramCeiling(
        width=width, baseline=len(baseline), reachable=len(reachable), capped_lines=capped
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def render(
    stats: tuple[ClassStats, ...],
    corpus: Corpus,
    source: str,
) -> list[str]:
    """The whole report, as lines."""
    out = [
        "swap-class candidate statistics",
        f"corpus: {len(corpus.files)} files, {len(corpus.lines)} non-blank non-comment lines "
        f"under {LIBRARY_ROOT}",
        f"classes: {source}",
        "",
        "Section 1 -- occurrences per class",
        "",
    ]
    out += _render_classes(stats, corpus)
    out += ["", "Section 2 -- determiner context per member", ""]
    out += _render_determiners(stats)
    out += ["", "Section 3 -- group rollup", ""]
    out += _render_groups(stats, corpus)
    out += ["", "Section 4 -- reachable n-gram ceiling", ""]
    out += _render_ceiling(stats, corpus)
    return out


def _render_ceiling(stats: tuple[ClassStats, ...], corpus: Corpus) -> list[str]:
    """Section 4: what the swap set could reach, per group and all together."""
    candidates = tuple(entry.candidate for entry in stats)
    groups = list(dict.fromkeys(candidate.group for candidate in candidates))
    out = [
        "  Distinct n-grams the committed libraries hold, and the number reachable",
        "  if every member site took every value of its class. An upper bound, not",
        "  a forecast: a real run draws at --rate and leaves --clean-share alone.",
        "",
        f"  {'scope':<12}{'n':>3}{'baseline':>11}{'reachable':>11}{'gain':>9}",
    ]
    for scope, selected in [
        *((group, tuple(c for c in candidates if c.group == group)) for group in groups),
        ("ALL", candidates),
    ]:
        for width in NGRAM_WIDTHS:
            ceiling = ngram_ceiling(selected, corpus, width)
            out.append(
                f"  {scope:<12}{ceiling.width:>3}{ceiling.baseline:>11}"
                f"{ceiling.reachable:>11}{ceiling.gain:>8.1f}%"
            )
            if ceiling.capped_lines:
                out.append(
                    f"    CAPPED on {ceiling.capped_lines} line(s): the figure understates "
                    f"the ceiling"
                )
    return out


def _render_classes(stats: tuple[ClassStats, ...], corpus: Corpus) -> list[str]:
    out: list[str] = []
    for entry in stats:
        candidate = entry.candidate
        out.append(
            f"[{candidate.group}] {candidate.class_id} "
            f"-- {len(candidate.members)} members, {candidate.pairs} ordered pairs"
        )
        out.append(f"  {'member':<16}{'occ':>6}{'lines':>7}  {'frozen':<13}{'lexicon'}")
        for member in sorted(entry.members, key=lambda m: (-m.occurrences, m.member)):
            frozen = "/".join(member.frozen_tokens) or "-"
            out.append(
                f"  {member.member:<16}{member.occurrences:>6}{member.lines:>7}  "
                f"{frozen:<13}{', '.join(member.lexicon_hits) or '-'}"
            )
        share = _pct(entry.lines_with_any, len(corpus.lines))
        out.append(
            f"  total occurrences {entry.occurrences}; "
            f"lines with >=1 {entry.lines_with_any} ({share}); "
            f"lines with >1 {entry.lines_with_multiple}"
        )
        out.append(
            f"  frozen members {len(entry.frozen)}/{len(candidate.members)} carrying "
            f"{entry.frozen_occurrences} occurrences "
            f"({_pct(entry.frozen_occurrences, entry.occurrences)} of the class); "
            f"zero-occurrence members {len(entry.absent)}"
        )
        if entry.absent:
            out.append(f"    absent: {', '.join(entry.absent)}")
        if entry.lexicon:
            out.append(f"    SIGNAL LEXICON MATCH: {', '.join(entry.lexicon)}")
        out.append("")
    return out


def _render_determiners(stats: tuple[ClassStats, ...]) -> list[str]:
    out = [
        "  What sits directly before each occurrence. A member that is never bare",
        "  is a member no bare-noun rule can safely target, and a vowel-initial",
        "  member is unsafe wherever another member of its class takes 'a'.",
        "",
    ]
    for entry in stats:
        out.append(f"[{entry.candidate.group}] {entry.candidate.class_id}")
        for member in entry.members:
            if not member.occurrences:
                continue
            contexts = ", ".join(f"{name} {count}" for name, count in member.determiners)
            out.append(f"  {member.member:<16}{contexts}")
        out += _render_article_agreement(entry)
        out.append("")
    return out


def _render_article_agreement(entry: ClassStats) -> list[str]:
    """Flag the one agreement fault that is mechanically checkable.

    Symmetric on purpose. Review F6 raises "a other half"; "an appointment"
    swapped for "an consultation" is the same fault in the other direction and
    the encounter class is where it lives. Either way the invariant cannot see
    it and neither can ``--dry-run-lint``: a broken rewrite introduces no
    lexicon hit and exits 0 (DD11).
    """
    sites = {
        article: sum(
            count
            for member in entry.members
            for name, count in member.determiners
            if name == article
        )
        for article in ("a", "an")
    }
    vowel = [m.member for m in entry.members if m.member[:1] in "aeiou"]
    consonant = [m.member for m in entry.members if m.member[:1] not in "aeiou"]
    out = [f"  article sites in this class: a {sites['a']}, an {sites['an']}"]
    if sites["a"] and vowel:
        out.append(f"    'a' + VOWEL-INITIAL MEMBER at {sites['a']} sites: {', '.join(vowel)}")
    if sites["an"] and consonant:
        out.append(
            f"    'an' + CONSONANT-INITIAL MEMBER at {sites['an']} sites: {', '.join(consonant)}"
        )
    return out


def _render_groups(stats: tuple[ClassStats, ...], corpus: Corpus) -> list[str]:
    candidates = tuple(entry.candidate for entry in stats)
    out: list[str] = []
    for group in dict.fromkeys(candidate.group for candidate in candidates):
        occurrences = sum(e.occurrences for e in stats if e.candidate.group == group)
        pairs = sum(e.candidate.pairs for e in stats if e.candidate.group == group)
        any_line, multi_line = group_lines(candidates, group, corpus)
        out.append(
            f"  {group:<10}{occurrences:>6} occurrences  {pairs:>5} pairs  "
            f"lines >=1 {any_line} ({_pct(any_line, len(corpus.lines))})  lines >1 {multi_line}"
        )
    out.append(
        f"  {'ALL':<10}{sum(e.occurrences for e in stats):>6} occurrences  "
        f"{sum(e.candidate.pairs for e in stats):>5} pairs  "
        f"{sum(len(e.candidate.members) for e in stats)} members in {len(stats)} lists"
    )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.synthetic_data.class_stats",
        description=(
            "Measure the hand-written libraries against the swap-class candidate lists. "
            "Prints; never fails on what it finds."
        ),
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=LIBRARY_ROOT,
        help=f"directory of hand-written '*.txt' libraries (default: {LIBRARY_ROOT})",
    )
    parser.add_argument(
        "--classes-dir",
        type=Path,
        default=CLASSES_ROOT,
        help=f"directory of authored '*.classes.json' files, if any (default: {CLASSES_ROOT}). "
        "Falls back to the hard-coded candidate lists when it holds none",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        corpus = load_corpus(args.library_root)
        candidates, source = load_candidates(args.classes_dir)
    except ClassStatsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    stats = tuple(measure_class(candidate, corpus) for candidate in candidates)
    print("\n".join(render(stats, corpus, source)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
