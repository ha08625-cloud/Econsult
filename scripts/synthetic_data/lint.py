"""Reports that keep the fragment libraries honest as they grow.

Six reports, none of which change a single fragment: they print and stop.

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
* **Cross-signal language** is the same check as filler purity, run over every
  library against every signal that is not its own. Filler purity asks a
  question with one right answer; this one asks a question whose answer is a
  decision, so it reports and proposes rather than failing. Its zero-hit pairs
  are printed as pasteable ``null_on`` declarations, which is what makes
  declaring roughly 250 pairs by hand affordable without a wildcard.
* **Declared ``null_on`` pairs** are the other side of that decision, once it has
  been made. ``absent`` pairs are re-checked and a hit is a failure; ``policy``
  pairs are listed with their matched-line count and their note, because a
  lexicon cannot check them and an unchecked claim should at least be visible.
  Undeclared pairs are listed too -- that list is the cost of every decision
  deliberately left unmade.
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
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .manifest import DECLARATIVE_TYPE, SPLITS, Fragment, NullOn
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

#: Printed above the cross-signal report. Says what the zero means, because a
#: zero here is about to be pasted into the manifest as a guarantee.
CROSS_SIGNAL_HEADER = (
    "For every (library, signal) pair where the signal is not the library's "
    "own: how many of the library's lines read as that signal's language. This "
    "is evidence of topical absence at 59%-91% lexicon recall, NOT proof. A "
    "zero means nobody has found the signal's language in the library, not that "
    "it is not there -- a human confirms the library's subject matter before "
    "committing a null_on declaration for it. That is one judgement per pair, "
    "not per line. A non-zero cell has three resolutions (arch_training.md "
    "section 3): leave the pair undeclared, declare null_on with basis "
    "'policy' and a note, or rewrite the lines."
)

#: Printed above the paste-ready block. The block is a typing aid and nothing
#: more: no wildcard and no manifest-level default exists, because a shorthand
#: for asserting these in bulk is a shorthand for asserting them without
#: reading them.
NULL_ON_BLOCK_HEADER = (
    "Paste-ready null_on declarations for the zero-hit pairs, one block per "
    "library. Only basis 'absent' is ever proposed here: it is the half of the "
    "declaration a lexicon can check, so a hit against a declared 'absent' pair "
    "is a failure rather than a judgement call. The other basis, 'policy' -- "
    "the library does talk about the signal and the label is null anyway -- is "
    "hand-written and hand-judged. Read the library before pasting its block: "
    "the lint has found nothing, which is not the same as there being nothing."
)

#: Printed above the declared-pair report. Two halves because DD2 splits the
#: guarantee in two and only one half is machine-checkable; collapsing them into
#: one report is how the checked half stops being checked.
DECLARED_PAIR_HEADER = (
    "Declared null_on pairs, split by basis. An 'absent' pair claims the library "
    "never mentions the signal, which is the half a lexicon can check: a hit "
    "here is a FAILURE, resolved exactly as a filler-purity hit is (narrow the "
    "lexicon and add the phrase to the trap test; rewrite the line; or baseline "
    "the pair with the reason). A 'policy' pair claims the library does mention "
    "the signal and the label is null anyway, which no lexicon can check: hits "
    "are expected, and what is printed instead is the matched-line count beside "
    "the note, so the size of the standing claim is visible rather than implied."
)

#: Matching lines printed per non-silent cell before the rest are counted only.
CROSS_SIGNAL_DETAIL_LIMIT = 4

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

#: A urine infection diagnosed or treated inside the last 30 days. Anchors are
#: the infection nouns; modifiers are the diagnosis, treatment and recency
#: markers that turn naming an infection into asserting one happened recently.
#:
#: The split matters more here than for any other signal, because the anchor
#: half on its own is the single commonest thing a patient says in these
#: libraries: ``uti_speculation`` names an infection on nearly every line and
#: asserts a recent one on none of them ("Probably just another water
#: infection, happens quite often" is a guess about *now*, not a diagnosis).
#: The recency markers deliberately stop short of "last time", "last year" and
#: "again", which are the ways that library talks about the past: none of them
#: places an infection inside the window, and section 9's labelling policy
#: makes all three ``null``.
RECENT_UTI_LEXICON = Lexicon(
    anchors=(
        "bladder infection",
        "cystitis",
        "kidney infection",
        "urinary infection",
        "urinary tract infection",
        "urine infection",
        "uti",
        "utis",
        "water infection",
        "water works infection",
    ),
    modifiers=(
        "a fortnight ago",
        "amoxicillin",
        "antibiotic",
        "antibiotics",
        "cefalexin",
        "ciprofloxacin",
        "confirmed",
        "course",
        "days ago",
        "diagnosed",
        "earlier this month",
        "fortnight ago",
        "fosfomycin",
        "grew",
        "macrobid",
        "nitrofurantoin",
        "pivmecillinam",
        "prescribed",
        "prescription",
        "recently",
        "sent off",
        "showed up",
        "tested positive",
        "this month",
        "trimethoprim",
        "treated",
        "treatment",
        "weeks ago",
    ),
)

#: Every signal a library may have to stay silent about, keyed by the ruleset
#: signal name so a hit can say which label it falsifies. All seven
#: ``send_to_encoder`` signals are here. ``recent_uti_present`` has no libraries
#: of its own yet, so nothing measures its recall against one -- the recall
#: guard parametrises over the signals that *do* have a positive library, and
#: this one joins it automatically when they land.
SIGNAL_LEXICONS: dict[str, Lexicon] = {
    "fever_present": Lexicon(terms=FEVER_LEXICON),
    "dysuria_present": DYSURIA_LEXICON,
    "urinary_frequency_present": URINARY_FREQUENCY_LEXICON,
    "nocturia_present": NOCTURIA_LEXICON,
    "flank_pain_present": FLANK_PAIN_LEXICON,
    "haematuria_present": HAEMATURIA_LEXICON,
    "recent_uti_present": RECENT_UTI_LEXICON,
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


def signal_language_hits(
    fragments: Iterable[Fragment], signals: Iterable[str] | None = None
) -> list[LexiconHit]:
    """Report foreign-signal language in any set of fragments.

    "Foreign" is the whole of the generalisation: a fragment is never checked
    against its *own* signal's lexicon, because a ``dysuria_true`` line matching
    the dysuria lexicon is the lexicon working rather than a leak, and
    ``test_every_lexicon_reaches_most_of_its_own_library`` already measures that
    deliberately. Filler carries no ``signal_key``, so nothing is skipped for it
    and :func:`filler_lexicon_hits` is unchanged by the generalisation.

    ``signals`` defaults to every signal with a lexicon.
    """
    checked = tuple(SIGNAL_LEXICONS) if signals is None else tuple(signals)
    members = list(fragments)
    hits = [
        LexiconHit(
            fragment_id=fragment.fragment_id,
            library=fragment.library,
            terms=matched,
            text=fragment.text,
            signal=signal,
        )
        for signal in checked
        for fragment in members
        if fragment.signal_key != signal and (matched := lexicon_matches(fragment.text, signal))
    ]
    return sorted(hits, key=lambda hit: (hit.signal, hit.fragment_id))


def filler_lexicon_hits(fragments: Iterable[Fragment]) -> list[LexiconHit]:
    """Report every signal's language in the filler libraries.

    This is the one report with a test behind it: a new hit means a filler
    library has acquired a mention of a symptom, which is a labelling bug in the
    data rather than a style problem. Filler is paired with examples of every
    label, so a fragment that says something about a signal makes every ``null``
    example it lands in a lie about that signal.

    A special case of :func:`signal_language_hits` -- the ``absent`` half of the
    cross-signal declaration (DD2), applied to the libraries that have always
    had to satisfy it.
    """
    return signal_language_hits(f for f in fragments if f.fragment_type == "filler")


@dataclass(frozen=True)
class CrossSignalCell:
    """One (library, foreign signal) pair, with how much of the library matched.

    ``matched`` counts *lines*, not terms: the reader's decision is about the
    library, and "9 lines, 19%" is the unit that decision is made in.
    """

    library: str
    signal: str
    matched: int
    lines: int
    hits: tuple[LexiconHit, ...]

    @property
    def rate(self) -> float:
        return self.matched / self.lines if self.lines else 0.0

    @property
    def silent(self) -> bool:
        return self.matched == 0


def is_generated(fragment: Fragment) -> bool:
    """Whether a fragment came from a procedurally generated library.

    Three of the reports below treat such a library differently, and all three
    for one reason: a generated library states its meaning **per line** and has
    no library-level declaration to check. Its ``null_on`` block is empty by
    construction (a JSONL library may not declare one), and the character
    similarity between its lines is the expected output of a fixed frame rather
    than evidence of anything.
    """
    return fragment.fragment_type == DECLARATIVE_TYPE


def generated_libraries(fragments: Iterable[Fragment]) -> dict[str, tuple[int, int]]:
    """Return ``{library: (lines, clusters)}`` for the generated libraries."""
    lines: dict[str, int] = {}
    clusters: dict[str, set[str]] = {}
    for fragment in fragments:
        if not is_generated(fragment):
            continue
        lines[fragment.library] = lines.get(fragment.library, 0) + 1
        clusters.setdefault(fragment.library, set()).add(fragment.cluster_id or fragment.text)
    return {library: (lines[library], len(clusters[library])) for library in sorted(lines)}


def cross_signal_cells(
    fragments: Iterable[Fragment], signals: Iterable[str] | None = None
) -> list[CrossSignalCell]:
    """Return every (library, foreign signal) cell, worst first.

    Every library is covered, filler included: task 3 has to declare filler's
    pairs too, and a report that silently omitted the libraries the existing
    check already covers would leave a reader guessing which half they were
    looking at.

    Every library except a generated one. The grid exists to drive ``null_on``
    authoring -- it puts a lexicon's opinion beside a library-level declaration
    so a human can decide the pair -- and a generated library has no such
    declaration to decide: each of its lines states its own vector, and lexicon
    language it asserts is the whole point of it. Including it would add rows
    that read as unconsidered pairs and can never be considered.

    Sorted by matched count descending, then library, then signal -- the pairs
    that need a human decision first, and the long tail of zero-hit pairs after
    them.
    """
    checked = tuple(SIGNAL_LEXICONS) if signals is None else tuple(signals)
    members = list(fragments)

    by_library: dict[str, list[Fragment]] = {}
    own_signal: dict[str, str | None] = {}
    for fragment in members:
        if is_generated(fragment):
            continue
        by_library.setdefault(fragment.library, []).append(fragment)
        own_signal[fragment.library] = fragment.signal_key

    cells: list[CrossSignalCell] = []
    for library in sorted(by_library):
        lines = by_library[library]
        for signal in checked:
            if own_signal[library] == signal:
                continue
            hits = signal_language_hits(lines, (signal,))
            cells.append(
                CrossSignalCell(
                    library=library,
                    signal=signal,
                    matched=len(hits),
                    lines=len(lines),
                    hits=tuple(hits),
                )
            )
    return sorted(cells, key=lambda cell: (-cell.matched, cell.library, cell.signal))


def absent_pair_hits(fragments: Iterable[Fragment]) -> list[LexiconHit]:
    """Report lexicon hits against pairs declared ``null_on`` with basis ``absent``.

    The generalisation of :func:`filler_lexicon_hits` to every library that has
    made the same claim. ``absent`` says the library never mentions the signal,
    so a hit is a claim contradicted by the text and the check has teeth; a test
    holds this to a per-pair baseline in CI.

    ``policy`` pairs are deliberately not here. They assert the label rather than
    the silence, so a hit against one is the lexicon working: see
    :func:`policy_pairs`.

    Filler purity stays a separate, *stricter* check over the filler libraries,
    and the two differ on exactly the two filler pairs declared ``policy``
    (``uti_speculation`` and ``expectations`` on ``recent_uti_present``). Keeping
    it strict is the point: filler is paired with examples of every label, so a
    filler line that acquires signal language is worth catching even where the
    declaration would tolerate it.
    """
    members = list(fragments)
    hits: list[LexiconHit] = []
    for signal in SIGNAL_LEXICONS:
        for fragment in members:
            if fragment.null_on_basis(signal) != "absent":
                continue
            if matched := lexicon_matches(fragment.text, signal):
                hits.append(
                    LexiconHit(
                        fragment_id=fragment.fragment_id,
                        library=fragment.library,
                        terms=matched,
                        text=fragment.text,
                        signal=signal,
                    )
                )
    return sorted(hits, key=lambda hit: (hit.signal, hit.fragment_id))


@dataclass(frozen=True)
class DeclaredPair:
    """One declared (library, signal) pair, with what the lexicon found in it."""

    library: str
    signal: str
    basis: str
    note: str
    matched: int
    lines: int

    @property
    def rate(self) -> float:
        return self.matched / self.lines if self.lines else 0.0


def declared_pairs(fragments: Iterable[Fragment], basis: str) -> list[DeclaredPair]:
    """Return every declared pair of one ``basis``, worst first.

    Counts *lines*, not terms, for the same reason the cross-signal grid does:
    "23 of 40 lines" is the unit the standing claim is read in.
    """
    members = list(fragments)
    by_library: dict[str, list[Fragment]] = {}
    for fragment in members:
        by_library.setdefault(fragment.library, []).append(fragment)

    pairs: list[DeclaredPair] = []
    for library in sorted(by_library):
        lines = by_library[library]
        declared: dict[str, NullOn] = {entry.signal: entry for entry in lines[0].null_on}
        for signal in sorted(declared):
            entry = declared[signal]
            if entry.basis != basis or signal not in SIGNAL_LEXICONS:
                continue
            matched = sum(1 for f in lines if lexicon_matches(f.text, signal))
            pairs.append(
                DeclaredPair(
                    library=library,
                    signal=signal,
                    basis=entry.basis,
                    note=entry.note,
                    matched=matched,
                    lines=len(lines),
                )
            )
    return sorted(pairs, key=lambda pair: (-pair.matched, pair.library, pair.signal))


def policy_pairs(fragments: Iterable[Fragment]) -> list[DeclaredPair]:
    """Return the ``policy`` pairs -- the half of the guarantee nobody can check."""
    return declared_pairs(fragments, "policy")


def undeclared_pairs(fragments: Iterable[Fragment]) -> list[tuple[str, str]]:
    """Return the (library, foreign signal) pairs carrying no declaration.

    The default state, and the one worth printing: an undeclared pair is a
    library that cannot be used as a companion in that signal's run, so the list
    is the cost of every decision deliberately left unmade.

    Generated libraries are excluded, as they are from the cross-signal grid and
    for the same reason: their eligibility is decided per line by the line's own
    vector, so a library-level pair there is not a decision anyone can make.
    """
    members = list(fragments)
    own: dict[str, str | None] = {}
    declared: dict[str, set[str]] = {}
    for fragment in members:
        if is_generated(fragment):
            continue
        own[fragment.library] = fragment.signal_key
        declared[fragment.library] = {entry.signal for entry in fragment.null_on}
    return sorted(
        (library, signal)
        for library in own
        for signal in SIGNAL_LEXICONS
        if signal != own[library] and signal not in declared[library]
    )


def cross_split_near_duplicates(
    fragments: Iterable[Fragment],
    threshold: float = NEAR_DUPLICATE_THRESHOLD,
    *,
    include_generated: bool = False,
) -> list[NearDuplicate]:
    """Report similar within-library fragment pairs that straddle a split.

    Same-split pairs are ignored: they cost a little diversity, but they do not
    let a validation example borrow lexical content from a training example,
    which is the failure this exists to surface. Roughly 4,500 comparisons for
    a 96-fragment library, so no indexing scheme is warranted.

    Generated libraries are skipped unless ``include_generated`` asks for them
    (DD16). The report's purpose is *unintended* twinning in hand-written
    libraries; in a generated one, two lines from different clusters share a
    frame and most of a sentence by construction, so the pairs carry no
    information -- and there are tens of thousands of them, which buries every
    other library's rows and costs a minute of wall clock to produce. The
    generated libraries are named in their own section of the report instead.
    """
    by_library: dict[str, list[Fragment]] = {}
    for fragment in fragments:
        if is_generated(fragment) and not include_generated:
            continue
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

    generated = generated_libraries(fragments)
    lines += [
        "",
        f"Generated libraries (not compared above): {len(generated)}",
        "  A fixed frame makes near-duplicate text the expected output, so pairs "
        "here carry no signal; the cluster count is what to read instead.",
    ]
    if not generated:
        lines.append("  (none)")
    for library, (count, clusters) in generated.items():
        lines.append(f"  {library}: {count} lines across {clusters} clusters")

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

    lines += ["", "Cross-signal language (every library, every foreign signal)"]
    lines += render_cross_signal_report(fragments)

    lines += ["", "Declared null_on pairs"]
    lines += render_declared_pairs(fragments)

    lines += ["", "Split coverage (DD9: generation aborts on an empty cell)"]
    lines += render_split_coverage(fragments)
    return lines


def render_declared_pairs(fragments: Sequence[Fragment]) -> list[str]:
    """Render the enforced ``absent`` half and the asserted ``policy`` half.

    The two halves are printed apart and labelled, because the whole content of
    DD2 is that one of them is checked and the other is a standing claim, and a
    reader who cannot tell them apart has neither.
    """
    absent = declared_pairs(fragments, "absent")
    policy = policy_pairs(fragments)
    undeclared = undeclared_pairs(fragments)
    failures = absent_pair_hits(fragments)

    lines: list[str] = [f"  {DECLARED_PAIR_HEADER}"]
    lines.append(f"  {len(absent)} absent, {len(policy)} policy, {len(undeclared)} undeclared")

    lines += ["", f"  absent pairs with a lexicon hit (a failure): {len(failures)}"]
    for hit in failures:
        lines.append(
            f"    {hit.library} -> {hit.signal} {hit.fragment_id} "
            f"[{', '.join(hit.terms)}] {_wrap(hit.text, 80)}"
        )

    lines += ["", f"  policy pairs, with the lines the lexicon reads as the signal: {len(policy)}"]
    for pair in policy:
        lines.append(
            f"    {pair.library:<34}{pair.signal:<28}{pair.matched:>3}/{pair.lines:<3}"
            f"{pair.rate:>6.0%}"
        )
        # Wrapped rather than truncated: a policy note is the whole of the
        # unverifiable claim, and half of one is worse than a pointer to it.
        lines += [f"      {line}" for line in textwrap.wrap(pair.note, 92)]

    lines += ["", f"  undeclared pairs, ineligible as companions: {len(undeclared)}"]
    for library, signal in undeclared:
        lines.append(f"    {library:<34}{signal}")
    return lines


def render_cross_signal_report(fragments: Sequence[Fragment]) -> list[str]:
    """Render the full (library, foreign signal) grid and the null_on block.

    Two halves, and they are two different jobs. The grid is triage across
    roughly 250 pairs, so every pair gets exactly one line carrying the count
    and the rate, worst first, with the matched lines themselves under the
    non-silent ones. The block is the typing that follows, for the silent ones
    only.
    """
    cells = cross_signal_cells(fragments)
    noisy = [cell for cell in cells if not cell.silent]
    silent = [cell for cell in cells if cell.silent]

    lines: list[str] = [f"  {CROSS_SIGNAL_HEADER}"]
    lines.append(
        f"  {len(cells)} pairs across {len({cell.library for cell in cells})} libraries: "
        f"{len(noisy)} with at least one match, {len(silent)} silent"
    )
    lines.append(f"  {'library':<36}{'signal':<28}{'lines':>7}{'rate':>8}")
    for cell in cells:
        lines.append(
            f"  {cell.library:<36}{cell.signal:<28}"
            f"{cell.matched:>3}/{cell.lines:<3}{cell.rate:>7.0%}"
        )
        for hit in cell.hits[:CROSS_SIGNAL_DETAIL_LIMIT]:
            lines.append(f"      {hit.fragment_id} [{', '.join(hit.terms)}] {_wrap(hit.text, 84)}")
        if len(cell.hits) > CROSS_SIGNAL_DETAIL_LIMIT:
            lines.append(
                f"      ... and {len(cell.hits) - CROSS_SIGNAL_DETAIL_LIMIT} more matching "
                "lines, counted above but not shown"
            )

    lines += ["", f"  {NULL_ON_BLOCK_HEADER}"]
    lines += render_null_on_block(silent)
    return lines


def render_null_on_block(cells: Sequence[CrossSignalCell]) -> list[str]:
    """Render the silent cells as pasteable manifest ``null_on`` declarations."""
    by_library: dict[str, list[str]] = {}
    for cell in cells:
        by_library.setdefault(cell.library, []).append(cell.signal)
    if not by_library:
        return ["  (no silent pairs)"]

    lines: list[str] = []
    for library in sorted(by_library):
        lines.append(f"  {library}")
        lines.append('    "null_on": {')
        entries = [
            f'      "{signal}": {{"basis": "absent"}}' for signal in sorted(by_library[library])
        ]
        lines += [entry + "," for entry in entries[:-1]] + entries[-1:]
        lines.append("    }")
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
