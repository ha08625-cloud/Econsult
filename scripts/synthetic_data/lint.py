"""Reports that keep the fragment libraries honest as they grow.

Three reports, none of which change a single fragment: they print and stop.

* **Hedge markers** flag lines in the decisive libraries that read as uncertain,
  as a prompt to re-read them by hand. Precision here is poor by construction --
  see :data:`HEDGE_REPORT_HEADER` -- because the deliberate confounders in these
  libraries are *built out of* hedge language that then gets resolved.
* **Cross-split near-duplicates** are the feedback loop on the manual clustering
  pass. Only pairs that straddle a split boundary are reported, because those are
  the ones that bias validation upward rather than merely adding noise.
* **Filler purity** screens filler fragments for the language of *every* signal
  with libraries. A filler library that quietly acquires a fever mention would
  put fever text into an example labelled ``null`` on the strength of its
  structure, and the same is true of the five urinary signals.
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


@dataclass(frozen=True)
class Lexicon:
    """The language that would falsify a ``null`` label for one signal.

    Two shapes, because the signals come in two shapes.

    ``terms`` match on their own. Fever works this way: it is a state with a
    name, so "feverish" in a filler fragment is a leak whatever surrounds it.

    ``anchors`` and ``modifiers`` are the two halves of a claim that needs
    both, and a fragment must match one of each. Every urinary signal works
    this way, because none of them can be named in one word without either
    over- or under-reaching. "Blood" is a blood test until it is in urine;
    "kidney" is a kidney scan until something hurts; "night" is a bad night's
    sleep until someone gets up to wee. Splitting the claim in two is what lets
    the check stay quiet about the filler libraries' entirely legitimate talk of
    urine cultures, kidney function and broken sleep, while still firing the
    moment a filler line puts the two halves together.

    The cost is recall against euphemism: fragments that say "I'm going every
    twenty minutes" name no anchor at all and are not matched. See section 8 of
    ``arch_training.md`` for the measured per-signal figures.
    """

    terms: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()
    modifiers: tuple[str, ...] = ()


#: Printed above the filler-purity report. A hit has three legitimate
#: resolutions and they are not interchangeable; clearing one by widening the
#: baseline is how the check ends up checking nothing.
FILLER_PURITY_HEADER = (
    "A hit is one of three things, and which one is a judgement call: the "
    "lexicon is too broad (narrow it, and add the phrase to the trap test); the "
    "line genuinely leaks (move it out of filler or rewrite it); or it is an "
    "accepted exception (baseline it in the test, with the reason). Grouped by "
    "the signal whose null label the hit would falsify."
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

#: Named urination. Deliberately excludes the euphemistic "go" -- "going on",
#: "go to work" and "get back to normal" are ordinary filler English, and
#: pairing a bare "go" with a pain or frequency word made the check fire on
#: "family issues that have been dragging on".
URINATION_ANCHORS = (
    "bathroom",
    "bladder",
    "loo",
    "pass urine",
    "pass water",
    "passed urine",
    "passed water",
    "passing urine",
    "passing water",
    "pee",
    "peed",
    "peeing",
    "pees",
    "stream",
    "toilet",
    "toilets",
    "urinate",
    "urinated",
    "urinating",
    "urination",
    "urine",
    "wee",
    "weeing",
    "wees",
)

#: Pain of any kind. Shared by dysuria and flank pain, which differ only in
#: what they attach the pain to.
PAIN_MODIFIERS = (
    "ache",
    "aches",
    "aching",
    "achy",
    "agony",
    "colic",
    "colicky",
    "cramp",
    "cramping",
    "cramps",
    "discomfort",
    "dragging",
    "gripping",
    "hurt",
    "hurting",
    "hurts",
    "kick",
    "killing me",
    "knife",
    "pain",
    "painful",
    "pains",
    "sore",
    "soreness",
    "stabbing",
    "stitch",
    "tender",
    "tenderness",
    "throbbing",
    "twinge",
    "twinges",
    "uncomfortable",
    "wincing",
)

#: Pain on passing urine: the pain words, plus the burning and stinging
#: register that is specific to this symptom.
DYSURIA_LEXICON = Lexicon(
    terms=("dysuria",),
    anchors=URINATION_ANCHORS,
    modifiers=PAIN_MODIFIERS
    + (
        "acid",
        "broken glass",
        "burn",
        "burning",
        "burns",
        "burnt",
        "burny",
        "needles",
        "raw",
        "razor blades",
        "scalding",
        "searing",
        "sharp",
        "sting",
        "stinging",
        "stings",
        "stingy",
        "stung",
    ),
)

#: Passing urine more often than usual. The weakest of the six by recall: this
#: library leans hardest on euphemism, so a fragment often carries the
#: frequency half and no anchor at all.
URINARY_FREQUENCY_LEXICON = Lexicon(
    anchors=URINATION_ANCHORS,
    modifiers=(
        "again and again",
        "all day",
        "all the time",
        "back and forth",
        "constant",
        "constantly",
        "doubled",
        "every few minutes",
        "every five minutes",
        "every half hour",
        "every hour",
        "every ten minutes",
        "every twenty minutes",
        "frequency",
        "frequently",
        "hourly",
        "keep needing",
        "keeps needing",
        "lot more",
        "more",
        "more frequently",
        "more often",
        "more regularly",
        "more than usual",
        "non stop",
        "nonstop",
        "often",
        "over and over",
        "regularly",
        "shorter and shorter",
        "times",
        "trips",
        "twice as much",
        "twice as often",
        "up and down",
    ),
)

#: Getting up in the night to pass urine. The modifiers are night-and-rising
#: language, not night language alone: sleeping badly because the neighbour's
#: dog barks is not nocturia, and the filler libraries are full of it.
NOCTURIA_LEXICON = Lexicon(
    terms=("nocturia",),
    anchors=URINATION_ANCHORS,
    modifiers=(
        "1am",
        "2am",
        "3am",
        "4am",
        "5am",
        "asleep",
        "bed",
        "early hours",
        "get up",
        "gets up",
        "getting up",
        "got up",
        "midnight",
        "night",
        "nightly",
        "nights",
        "overnight",
        "sleep",
        "sleeping",
        "slept",
        "small hours",
        "trips",
        "wake",
        "wakes",
        "waking",
        "woke",
        "woken",
    ),
)

#: Pain in the loin, side or back. The anchor set is body parts rather than
#: urination: "kidney" without a pain word is a kidney scan, which filler is
#: entitled to ask for, and "back" without one is getting back to work.
FLANK_PAIN_LEXICON = Lexicon(
    terms=("renal colic",),
    anchors=(
        "back",
        "flank",
        "flanks",
        "kidney",
        "kidneys",
        "loin",
        "loins",
        "rib",
        "ribcage",
        "ribs",
        "side",
        "sides",
    ),
    modifiers=PAIN_MODIFIERS,
)

#: Blood in urine. "Blood test" and "blood pressure tablets" are both in the
#: filler libraries today and neither is haematuria, so the blood half never
#: fires without something urinary to put it in.
HAEMATURIA_LEXICON = Lexicon(
    terms=(
        "blood in my water",
        "blood in the water",
        "haematuria",
        "hematuria",
        "passed blood",
        "passing blood",
    ),
    anchors=URINATION_ANCHORS + ("bowl", "pan", "sample", "tissue"),
    modifiers=(
        "blood",
        "bloodstained",
        "bloody",
        "burgundy",
        "clot",
        "clots",
        "cola",
        "cranberry",
        "crimson",
        "maroon",
        "pink",
        "pinkish",
        "plum",
        "red",
        "redder",
        "reddish",
        "ribena",
        "rose",
        "rosé",
        "rust",
        "rusty",
        "scarlet",
        "streaks",
    ),
)

#: Every signal the filler libraries must stay silent about, keyed by the
#: ruleset signal name so a hit can say which label it falsifies. The seventh
#: ``send_to_encoder`` signal, ``recent_uti_present``, has no libraries and so
#: nothing to be silent about yet.
SIGNAL_LEXICONS: dict[str, Lexicon] = {
    "fever_present": Lexicon(terms=FEVER_LEXICON),
    "dysuria_present": DYSURIA_LEXICON,
    "urinary_frequency_present": URINARY_FREQUENCY_LEXICON,
    "nocturia_present": NOCTURIA_LEXICON,
    "flank_pain_present": FLANK_PAIN_LEXICON,
    "haematuria_present": HAEMATURIA_LEXICON,
}

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

#: Compiled once at import: six lexicons over four hundred filler fragments is
#: a few hundred thousand searches, and recompiling per call makes the lint the
#: slowest thing in the test suite for no reason.
_COMPILED_LEXICONS = {
    signal: (
        _compile(lexicon.terms),
        _compile(lexicon.anchors),
        _compile(lexicon.modifiers),
    )
    for signal, lexicon in SIGNAL_LEXICONS.items()
}


@dataclass(frozen=True)
class LexiconHit:
    """One fragment matching one or more terms of a lexicon."""

    fragment_id: str
    library: str
    terms: tuple[str, ...]
    text: str
    #: Which signal's silence the hit falsifies. Empty for the hedge report,
    #: which is about a fragment's own label rather than another signal's.
    signal: str = ""


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


def lexicon_matches(text: str, signal: str) -> tuple[str, ...]:
    """Return why ``text`` reads as ``signal`` language, or an empty tuple.

    A co-occurrence match is reported as ``anchor+modifier`` with every matched
    term on each side, because "which two words did this" is the whole of what a
    reader needs to decide between narrowing the lexicon and rewriting the line.
    """
    terms, anchors, modifiers = _COMPILED_LEXICONS[signal]
    matched = _matching_terms(text, terms)
    hit_anchors = _matching_terms(text, anchors)
    hit_modifiers = _matching_terms(text, modifiers)
    if hit_anchors and hit_modifiers:
        matched += (f"{'/'.join(hit_anchors)}+{'/'.join(hit_modifiers)}",)
    return matched


def filler_lexicon_hits(fragments: Iterable[Fragment]) -> list[LexiconHit]:
    """Report every signal's language in the filler libraries.

    This is the one report with a test behind it: a new hit means a filler
    library has acquired a mention of a symptom, which is a labelling bug in the
    data rather than a style problem. Filler is paired with examples of every
    label, so a fragment that says something about a signal makes every ``null``
    example it lands in a lie about that signal.
    """
    filler = [f for f in fragments if f.fragment_type == "filler"]
    hits = [
        LexiconHit(
            fragment_id=fragment.fragment_id,
            library=fragment.library,
            terms=matched,
            text=fragment.text,
            signal=signal,
        )
        for signal in SIGNAL_LEXICONS
        for fragment in filler
        if (matched := lexicon_matches(fragment.text, signal))
    ]
    return sorted(hits, key=lambda hit: (hit.signal, hit.fragment_id))


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

    lines += [
        "",
        f"Signal language in filler libraries: {len(leaks)}",
        f"  {FILLER_PURITY_HEADER}",
    ]
    for signal in SIGNAL_LEXICONS:
        for_signal = [hit for hit in leaks if hit.signal == signal]
        lines.append(f"  {signal}: {len(for_signal)}")
        for hit in for_signal:
            lines.append(
                f"    {hit.library} {hit.fragment_id} [{', '.join(hit.terms)}] {_wrap(hit.text)}"
            )

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
