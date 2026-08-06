"""Reports that keep the fragment libraries honest as they grow.

Three reports, none of which change a single fragment: they print and stop.

* **Hedge markers** flag lines in the decisive libraries that read as uncertain,
  as a prompt to re-read them by hand. Precision here is poor by construction --
  see :data:`HEDGE_REPORT_HEADER` -- because the deliberate confounders in these
  libraries are *built out of* hedge language that then gets resolved.
* **Cross-split near-duplicates** are the feedback loop on the manual clustering
  pass. Only pairs that straddle a split boundary are reported, because those are
  the ones that bias validation upward rather than merely adding noise.
* **Filler purity** screens filler fragments for fever language. A filler library
  that quietly acquires a fever mention would put fever text into an example
  labelled ``null`` on the strength of its structure.
* **Split coverage** lists every ``(library, split)`` cell. Generation aborts on
  an empty cell (DD9); the lint reports it instead, because the tool you reach
  for when the generator refuses to run must not refuse for the same reason.

Matching is done on :func:`~scripts.synthetic_data.normalise.normalise` output --
already case-folded and whitespace-collapsed -- and always on word boundaries.
Naive substring matching would hit ``lithotripsy`` and ``photos`` for "hot", so
the check would fail on day one against clean data.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .manifest import SPLITS, Fragment
from .normalise import normalise

#: Uncertainty language, reported in ``positive`` and ``negative`` libraries only.
HEDGE_MARKERS = (
    "could be",
    "hard to tell",
    "i think",
    "maybe",
    "might",
    "not sure",
    "pretty sure",
    "probably",
    "reckon",
)

#: Printed above the hedge report. The precision figure is deliberate: a long
#: list here is normal, not a crisis, and nobody should automate on this output.
HEDGE_REPORT_HEADER = (
    "Hedge markers are a prompt to re-read a line by hand, never a relabelling "
    "signal. Precision is roughly 25% against the current libraries: the "
    "deliberate confounders are built out of hedge language that the fragment "
    "then resolves ('I thought maybe I was dehydrated but when I checked I had a "
    "temperature'), so most hits are correctly labelled."
)

#: Fever language that must not appear in a filler fragment.
FEVER_LEXICON = (
    "boiling",
    "burning up",
    "chills",
    "clammy",
    "febrile",
    "fever",
    "feverish",
    "flushed",
    "freezing",
    "hot",
    "pyrexia",
    "rigor",
    "shiver",
    "sweats",
    "temperature",
    "warm",
)

#: difflib ratio at or above which two fragments count as near-duplicates.
#: A character-level ratio misses "Monday -> Tuesday, husband -> boyfriend"
#: rewrites, so whatever this reports is a lower bound on the real twinning.
NEAR_DUPLICATE_THRESHOLD = 0.60

#: Worst offenders printed in full; the rest are counted only.
NEAR_DUPLICATE_DETAIL_LIMIT = 10

#: Libraries whose fragments carry a decisive label, and so are worth hedging
#: against. Ambiguous and confounder libraries are *supposed* to hedge.
_DECISIVE_TYPES = ("positive", "negative")


def _compile(terms: Sequence[str]) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((term, re.compile(rf"\b{re.escape(term)}\b")) for term in terms)


_HEDGE_PATTERNS = _compile(HEDGE_MARKERS)
_FEVER_PATTERNS = _compile(FEVER_LEXICON)


@dataclass(frozen=True)
class LexiconHit:
    """One fragment matching one or more terms of a lexicon."""

    fragment_id: str
    library: str
    terms: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class NearDuplicate:
    """Two fragments of one library that are similar and in different splits."""

    library: str
    ratio: float
    left: Fragment
    right: Fragment


def _matching_terms(text: str, patterns: Sequence[tuple[str, re.Pattern[str]]]) -> tuple[str, ...]:
    key = normalise(text)
    return tuple(term for term, pattern in patterns if pattern.search(key))


def _hits(
    fragments: Iterable[Fragment], patterns: Sequence[tuple[str, re.Pattern[str]]]
) -> list[LexiconHit]:
    hits = [
        LexiconHit(
            fragment_id=fragment.fragment_id,
            library=fragment.library,
            terms=terms,
            text=fragment.text,
        )
        for fragment in fragments
        if (terms := _matching_terms(fragment.text, patterns))
    ]
    return sorted(hits, key=lambda hit: hit.fragment_id)


def hedge_marker_hits(fragments: Iterable[Fragment]) -> list[LexiconHit]:
    """Report hedge language in the decisive (positive/negative) libraries."""
    return _hits((f for f in fragments if f.fragment_type in _DECISIVE_TYPES), _HEDGE_PATTERNS)


def filler_lexicon_hits(fragments: Iterable[Fragment]) -> list[LexiconHit]:
    """Report fever language in the filler libraries.

    This is the one report with a test behind it: a new hit means a filler
    library has acquired a fever mention, which is a labelling bug in the data
    rather than a style problem.
    """
    return _hits((f for f in fragments if f.fragment_type == "filler"), _FEVER_PATTERNS)


def cross_split_near_duplicates(
    fragments: Iterable[Fragment], threshold: float = NEAR_DUPLICATE_THRESHOLD
) -> list[NearDuplicate]:
    """Report similar within-library fragment pairs that straddle a split.

    Same-split pairs are ignored: they cost a little diversity, but they do not
    let a validation example borrow lexical content from a training example,
    which is the failure this exists to surface. Roughly 4,500 comparisons for
    a 96-fragment library, so no indexing scheme is warranted.
    """
    by_library: dict[str, list[Fragment]] = {}
    for fragment in fragments:
        by_library.setdefault(fragment.library, []).append(fragment)

    pairs: list[NearDuplicate] = []
    for library in sorted(by_library):
        members = sorted(by_library[library], key=lambda f: f.fragment_id)
        keys = [normalise(f.text) for f in members]
        for i, left in enumerate(members):
            for j in range(i + 1, len(members)):
                right = members[j]
                if left.split == right.split:
                    continue
                ratio = difflib.SequenceMatcher(None, keys[i], keys[j]).ratio()
                if ratio >= threshold:
                    pairs.append(
                        NearDuplicate(library=library, ratio=ratio, left=left, right=right)
                    )
    return sorted(pairs, key=lambda p: (-p.ratio, p.left.fragment_id, p.right.fragment_id))


def _wrap(text: str, width: int = 100) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _counts_by_library(items: Iterable[LexiconHit | NearDuplicate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.library] = counts.get(item.library, 0) + 1
    return counts


def _count_lines(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["  (none)"]
    return [f"  {library}: {counts[library]}" for library in sorted(counts)]


def render_report(fragments: Sequence[Fragment]) -> list[str]:
    """Render all three reports as printable lines."""
    hedges = hedge_marker_hits(fragments)
    duplicates = cross_split_near_duplicates(fragments)
    leaks = filler_lexicon_hits(fragments)

    lines: list[str] = [
        f"Fragment lint: {len(fragments)} fragments across "
        f"{len({f.library for f in fragments})} libraries",
        "",
        f"Hedge markers in decisive libraries: {len(hedges)}",
        f"  {HEDGE_REPORT_HEADER}",
    ]
    lines += _count_lines(_counts_by_library(hedges))
    for hit in hedges:
        lines.append(f"    {hit.fragment_id} [{', '.join(hit.terms)}] {_wrap(hit.text)}")

    lines += [
        "",
        f"Cross-split near-duplicates (ratio >= {NEAR_DUPLICATE_THRESHOLD}): {len(duplicates)}",
    ]
    lines += _count_lines(_counts_by_library(duplicates))
    for pair in duplicates[:NEAR_DUPLICATE_DETAIL_LIMIT]:
        lines.append(f"    {pair.ratio:.2f} {pair.library}")
        lines.append(f"      {pair.left.split:<5} {_wrap(pair.left.text, 90)}")
        lines.append(f"      {pair.right.split:<5} {_wrap(pair.right.text, 90)}")
    if len(duplicates) > NEAR_DUPLICATE_DETAIL_LIMIT:
        lines.append(
            f"    ... and {len(duplicates) - NEAR_DUPLICATE_DETAIL_LIMIT} more, "
            "counted above but not shown"
        )

    lines += ["", f"Fever language in filler libraries: {len(leaks)}"]
    lines += _count_lines(_counts_by_library(leaks))
    for hit in leaks:
        lines.append(f"    {hit.fragment_id} [{', '.join(hit.terms)}] {_wrap(hit.text)}")

    lines += ["", "Split coverage (DD9: generation aborts on an empty cell)"]
    lines += render_split_coverage(fragments)
    return lines


def render_split_coverage(fragments: Sequence[Fragment]) -> list[str]:
    """Render the per-library fragment count in each split, flagging empties."""
    counts: dict[str, dict[str, int]] = {}
    for fragment in fragments:
        cell = counts.setdefault(fragment.library, dict.fromkeys(SPLITS, 0))
        cell[fragment.split] += 1

    lines = [f"  {'library':<24}" + "".join(f"{split:>7}" for split in SPLITS)]
    empty = 0
    for library in sorted(counts):
        row = counts[library]
        empty += sum(1 for split in SPLITS if not row[split])
        marker = "  <- empty cell" if any(not row[split] for split in SPLITS) else ""
        lines.append(f"  {library:<24}" + "".join(f"{row[split]:>7}" for split in SPLITS) + marker)
    lines.append(f"  empty cells: {empty}")
    return lines
