"""Reports that keep the fragment libraries honest as they grow.

Nine reports. Eight of them change nothing and decide nothing: they print and
stop. The ninth, the phrase inventory, is the one exception in the file -- its
rules are mechanical and its faults are errors, because the inventory is
composed into hundreds of committed lines and a fault there is a fault in every
line that used the phrase.

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
* **Split coverage** lists every ``(library, split)`` cell, as lines over
  clusters, with the library's frame count beside them. Generation aborts on an
  empty cell (DD9); the lint reports it instead, because the tool you reach for
  when the generator refuses to run must not refuse for the same reason.
* **Generated libraries** are reported apart from the near-duplicate pairs
  rather than inside them (DD16): a fixed frame makes high character similarity
  between two different clusters the expected output, so the pairs carry no
  information and would bury every other library's rows. What replaces them is
  the shape of the library -- its clusters, arities and frames -- plus the one
  check a lexicon can make on a per-line vector, which is that the line's text
  does not read as a signal the vector is silent about.
* **Token / label-class association** ranks every token by how differently the
  three label classes use it. This is the first of the two faults section 8
  records as uncaught, and the reason it no longer is
  -- a clinical term living in one library is a label, not vocabulary -- plus the
  weaker frequency-skew form of it, where a token is on every class and one of
  them simply leans on it. It reports and ranks; which confined token is a fault
  and which is a null sub-class's axis word doing its job is a judgement, and it
  is not made here.
* **The phrase inventory** is checked rather than reported: an unknown signal,
  too few phrases, an over-long phrase, or a phrase that reproduces a
  hand-written library line verbatim. The last is what keeps train text out of a
  generated val fragment. Its cross-lexicon rows are a report like the others.

Matching is done on :func:`~scripts.synthetic_data.normalise.normalise` output --
already case-folded and whitespace-collapsed -- and always on word boundaries.
Naive substring matching would hit ``lithotripsy`` and ``photos`` for "hot", so
the check would fail on day one against clean data.
"""

from __future__ import annotations

import difflib
import json
import re
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .declarative import EXCLUDED_SIGNALS, MAX_PHRASE_WORDS, Phrase
from .manifest import DECLARATIVE_TYPE, SPLITS, UNDECLARED, Fragment, NullOn, cluster_key
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

#: The fewest phrases a signal may declare in the inventory. Below three, the
#: phrase becomes a near-proxy for the cluster: every line asserting that signal
#: at a given polarity says it the same one or two ways, so the split stops
#: separating surface forms and starts separating nothing. Four to six is the
#: authored aim; three is the floor a fault is raised at.
MIN_PHRASES_PER_SIGNAL = 3

#: Printed above the inventory report. Everything the generator writes is
#: composed out of this file, so a fault here is a fault in every line that used
#: the phrase -- which is why these four are errors rather than rows.
INVENTORY_HEADER = (
    "The authored phrase inventory is the input build-declarative composes into "
    "the generated library, so a fault here is a fault in every line that used "
    "the phrase. Four mechanical rules (DD10): the signal is a Boolean encoder "
    "signal in the ruleset and is not one no frame can state; it declares at "
    f"least {MIN_PHRASES_PER_SIGNAL} phrases; each bare form is at most "
    f"{MAX_PHRASE_WORDS} words; and no form reproduces a hand-written library "
    "line verbatim. The last is the load-bearing one: a phrase lifted from a "
    "library would put train text inside a generated val fragment. The other "
    "half of DD10 -- that the phrase reads correctly after both bases, and that "
    "its label is unambiguous under section 9 -- is review, and no lint can do "
    "it."
)

#: Printed above the inventory's cross-lexicon rows. Deliberately not an error:
#: see the nocturia / urinary-frequency pair, which reads as itself twice over.
INVENTORY_LEXICON_HEADER = (
    "Phrases that trip another signal's lexicon. Not an error -- the lexicons "
    "over-reach by design (arch_training.md section 4) -- but a phrase that "
    "names two signals labels only one, so each row is a phrase to re-read. The "
    "nocturia / urinary-frequency phrases appear here by construction: those two "
    "signals are said in the same words, which is exactly why their overlap is "
    "left undecided (DD14)."
)

#: Printed above the generated-vector report.
DECLARATIVE_VECTOR_HEADER = (
    "Generated lines whose label vector asserts nothing about a signal, in text "
    "the lexicon reads as that signal. Two states and they mean different "
    "things. 'null' is a declared silence that supervises the head towards 'not "
    "mentioned', so a hit is a label the line's own text argues with. "
    "'undeclared' is the nocturia / urinary-frequency pair (DD14): the line says "
    "nothing about the partner and earns no key for it, so nothing is being "
    "taught either way. Most hits of both kinds are one clause's urinary anchor "
    "pairing with another clause's modifier across a comma, which is the "
    "lexicon working as designed on a sentence that names four symptoms; a bare "
    "term match would not be, and a test pins both the pairs and the shapes."
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

#: The three label classes a signal's libraries are grouped into for the
#: token-association report. Ordered as the report prints them.
TOKEN_LABEL_CLASSES = ("true", "false", "null")

#: How a library's ``fragment_type`` maps onto those classes. Everything not
#: named here -- ``ambiguous`` and ``confounder`` -- is ``null``, which is what
#: the head is supervised towards for all of them.
_TOKEN_LABEL_CLASS_BY_TYPE = {"positive": "true", "negative": "false"}

#: Lines a token must appear on, across a signal's libraries, before it is
#: ranked at all. Below this the rate differences are one or two sentences and
#: the ranking is noise.
MIN_TOKEN_SUPPORT = 5

#: Worst offenders printed in full per block; the rest are counted only, the
#: way :data:`NEAR_DUPLICATE_DETAIL_LIMIT` does it.
TOKEN_ASSOCIATION_DETAIL_LIMIT = 12

#: Printed above the token-association report. Longer than the other headers
#: because this report has four separate ways of being misread and section 8
#: records two faults that reached the libraries through exactly this gap.
TOKEN_ASSOCIATION_HEADER = (
    "For each signal, every library is grouped into one of three label classes "
    "by fragment_type -- positive->true, negative->false, everything else->null "
    "-- and each token's *per-line rate* is counted in each class: lines "
    "containing the token over lines in the class. Rates, not counts: the three "
    "classes are different sizes and raw counts mislead. Tokens are ranked by "
    "'skew': the highest of the three rates minus the lowest, taken "
    f"over tokens on at least {MIN_TOKEN_SUPPORT} lines of the signal. A token "
    "whose skew is large is one a head can read the label off, whatever the "
    "sentence around it says.\n"
    "    Four things this report cannot see or does not rank, none of which is "
    "a reason to read a short list here as a clean bill of health:\n"
    "    (1) It is per-token, so it is blind to multi-token style and register. "
    "Section 8's second recorded fault -- one library written entirely in "
    "lowercase with no terminal punctuation against uniformly capitalised "
    "siblings -- would not appear here at all.\n"
    "    (2) Skew *within* the null class is not in the ranking. null is five "
    "libraries for some signals, and a token used by the historical library and "
    "not the metaphor one has a modest three-class skew and a large one across "
    "the sub-classes. That is what the per-library breakdown on each row is "
    "for; read it, do not trust the rank alone.\n"
    "    (3) High-frequency function words dominate the ranking by "
    "construction, because a rate near 0.5 has the most room to move. 'was', "
    "'but', 'a' and 'the' at the top of a block are the tense and register "
    "difference between the classes, which is real but is not a vocabulary "
    "swap anyone can make.\n"
    "    (4) The axis word of a null sub-class is *supposed* to be confined to "
    "it -- 'she' and 'he' in third-party, 'ago' in historical, 'might' in "
    "hedged. Expect them at the top of the first block. No filter is applied, "
    "because deciding which confined token is a fault and which is the "
    "sub-class doing its job is a clinical judgement and does not belong in "
    "code.\n"
    "    Filler libraries carry no signal_key and so are in no signal's "
    "grouping. Generated libraries are excluded too: their lines state their "
    "labels one at a time rather than by fragment_type, so there is no class to "
    "group them into."
)


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


@dataclass(frozen=True)
class GeneratedLibrary:
    """What a generated library is made of, in the units DD15 caps it in.

    The cluster count is what the near-duplicate report is replaced by (DD16),
    and the arity and per-cluster distributions are what say whether the budget
    was right: one so small that most clusters are empty and one so large that
    every cluster carries a dozen near-identical siblings are both visible here
    and nowhere else.
    """

    library: str
    lines: int
    clusters: int
    #: ``{arity: lines}`` and ``{frame: lines}``, both read from the line's
    #: ``meta``. Empty when a generated library carries no such key rather than
    #: guessed at, because a missing distribution is a fact about the library.
    by_arity: Mapping[str, int]
    by_frame: Mapping[str, int]
    #: Cluster sizes, ascending. Summarised rather than listed: 316 clusters is
    #: past what anyone reads line by line, and min/median/max is the shape.
    cluster_sizes: tuple[int, ...]


def _tally(values: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def generated_libraries(fragments: Iterable[Fragment]) -> dict[str, GeneratedLibrary]:
    """Return the generated libraries, keyed by name, with their distributions."""
    members: dict[str, list[Fragment]] = {}
    for fragment in fragments:
        if is_generated(fragment):
            members.setdefault(fragment.library, []).append(fragment)

    summaries: dict[str, GeneratedLibrary] = {}
    for library in sorted(members):
        lines = members[library]
        sizes: dict[str, int] = {}
        for fragment in lines:
            key = cluster_key(fragment.cluster_id, fragment.text)
            sizes[key] = sizes.get(key, 0) + 1
        summaries[library] = GeneratedLibrary(
            library=library,
            lines=len(lines),
            clusters=len(sizes),
            by_arity=_tally(
                f.meta["arity"] for f in lines if isinstance(f.meta, Mapping) and "arity" in f.meta
            ),
            by_frame=_tally(
                f.meta["frame"] for f in lines if isinstance(f.meta, Mapping) and "frame" in f.meta
            ),
            cluster_sizes=tuple(sorted(sizes.values())),
        )
    return summaries


def frames_by_library(fragments: Iterable[Fragment]) -> dict[str, dict[str, int]]:
    """Return ``{library: {frame: lines}}``, empty for a hand-written library.

    ``arch_training.md`` 12.1 asks for the frame count beside the line count for
    exactly one reason: a templated library's line count is its template count
    multiplied by something, and reading the first without the second is how a
    library comes to look richer than it is. A hand-written library has no
    frames and gets an empty mapping rather than a one, because "one frame" and
    "no frames" are opposite claims about a library.
    """
    frames: dict[str, dict[str, int]] = {}
    for fragment in fragments:
        counts = frames.setdefault(fragment.library, {})
        frame = fragment.meta.get("frame") if isinstance(fragment.meta, Mapping) else None
        if frame is not None:
            counts[str(frame)] = counts.get(str(frame), 0) + 1
    return {library: dict(sorted(frames[library].items())) for library in sorted(frames)}


def clusters_by_split(fragments: Iterable[Fragment]) -> dict[str, dict[str, int]]:
    """Return ``{library: {split: distinct clusters}}``.

    The cluster, not the line, is the unit the split is assigned in, so this is
    the count that says whether a split cell holds several ideas or one idea
    written six ways. Keyed on :func:`~scripts.synthetic_data.manifest.cluster_key`
    so it counts what the splitter counted, marker or no marker.
    """
    seen: dict[str, dict[str, set[str]]] = {}
    for fragment in fragments:
        cells = seen.setdefault(fragment.library, {split: set() for split in SPLITS})
        cells[fragment.split].add(cluster_key(fragment.cluster_id, fragment.text))
    return {
        library: {split: len(seen[library][split]) for split in SPLITS} for library in sorted(seen)
    }


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


@dataclass(frozen=True)
class TokenAssociation:
    """One token's per-line rate across one signal's three label classes.

    The row carries the class and library totals it was computed against rather
    than only the rates, because a rate of 1.0 on a class of four lines and one
    on a class of 269 are not the same claim and a reader of the report should
    not have to go and find the denominator.
    """

    signal: str
    token: str
    #: ``{class: lines containing the token}`` and ``{class: lines in class}``.
    #: Every class in :data:`TOKEN_LABEL_CLASSES` is present in both, so a zero
    #: is a measured absence rather than a missing key.
    class_lines: Mapping[str, int]
    class_totals: Mapping[str, int]
    #: The same two counts per library, restricted to the libraries the token
    #: actually appears in. This is what makes skew *within* the null class
    #: readable -- see caveat (2) in :data:`TOKEN_ASSOCIATION_HEADER`.
    library_lines: Mapping[str, int]
    library_totals: Mapping[str, int]

    @property
    def support(self) -> int:
        """Lines across the whole signal that contain the token."""
        return sum(self.class_lines.values())

    @property
    def rates(self) -> dict[str, float]:
        """Per-line rate in each class. An empty class scores 0.0, not a crash."""
        return {
            label: (self.class_lines[label] / self.class_totals[label])
            if self.class_totals[label]
            else 0.0
            for label in TOKEN_LABEL_CLASSES
        }

    @property
    def skew(self) -> float:
        """Highest class rate minus lowest. The statistic rows are ranked by."""
        rates = self.rates.values()
        return max(rates) - min(rates)

    @property
    def classes_present(self) -> int:
        """How many of the three classes the token appears on at least one line of."""
        return sum(1 for label in TOKEN_LABEL_CLASSES if self.class_lines[label])


def _label_class(fragment: Fragment) -> str:
    """Return ``true`` / ``false`` / ``null`` for a hand-written library's type."""
    return _TOKEN_LABEL_CLASS_BY_TYPE.get(fragment.fragment_type, "null")


def _line_tokens(text: str) -> frozenset[str]:
    """Return the distinct folded tokens on one line.

    A set, not a list: the report counts *lines containing* a token, so a line
    saying "hot, really hot" is one line for "hot" and not two.

    ``fold_token`` is imported here rather than at module scope because
    :mod:`~scripts.synthetic_data.noise` imports this module for
    :data:`SIGNAL_LEXICONS`, so the module-level import would be a cycle. It is
    imported rather than reimplemented because a second tokeniser would sooner
    or later disagree with the one the noise pass freezes words with, and then
    this report would be measuring tokens nothing else in the pipeline has.
    """
    from .noise import fold_token

    return frozenset(folded for folded in (fold_token(word) for word in text.split()) if folded)


def token_label_association(
    fragments: Iterable[Fragment], *, min_support: int = MIN_TOKEN_SUPPORT
) -> dict[str, list[TokenAssociation]]:
    """Return each signal's tokens ranked by label-class skew, highest first.

    This is the check section 8 records as missing: "a token that appears in
    exactly one library ... would not be caught by any check we have". A token
    confined to one label class is a label wearing vocabulary's clothes, and the
    dysuria case that prompted it -- "dysuria" on 16 lines of one ``null``
    library and nowhere else in the signal -- is a skew of exactly 1.0 minus 0.

    Filler libraries (no ``signal_key``) and generated ones (labels per line,
    not per library) are excluded; see :data:`TOKEN_ASSOCIATION_HEADER`.

    Ties break on the token so the ranking is stable across runs, which is what
    lets the committed report be diffed when a library changes.
    """
    by_signal: dict[str, list[Fragment]] = {}
    for fragment in fragments:
        # The signal_key test already excludes both, because the manifest
        # refuses a signal_key on a filler library and on a JSONL one alike.
        # is_generated is named anyway: it is the reason rather than the
        # mechanism, and a future format that carried both would otherwise be
        # grouped by a fragment_type that says nothing about what its lines
        # assert.
        if fragment.signal_key is None or is_generated(fragment):
            continue
        by_signal.setdefault(fragment.signal_key, []).append(fragment)

    ranked: dict[str, list[TokenAssociation]] = {}
    for signal in sorted(by_signal):
        members = by_signal[signal]
        class_totals = dict.fromkeys(TOKEN_LABEL_CLASSES, 0)
        library_totals: dict[str, int] = {}
        class_lines: dict[str, dict[str, int]] = {}
        library_lines: dict[str, dict[str, int]] = {}

        for fragment in members:
            label = _label_class(fragment)
            class_totals[label] += 1
            library_totals[fragment.library] = library_totals.get(fragment.library, 0) + 1
            for token in _line_tokens(fragment.text):
                per_class = class_lines.setdefault(token, dict.fromkeys(TOKEN_LABEL_CLASSES, 0))
                per_class[label] += 1
                per_library = library_lines.setdefault(token, {})
                per_library[fragment.library] = per_library.get(fragment.library, 0) + 1

        rows = [
            TokenAssociation(
                signal=signal,
                token=token,
                class_lines=dict(per_class),
                class_totals=dict(class_totals),
                library_lines=dict(sorted(library_lines[token].items())),
                library_totals={
                    library: library_totals[library] for library in sorted(library_lines[token])
                },
            )
            for token, per_class in class_lines.items()
            if sum(per_class.values()) >= min_support
        ]
        ranked[signal] = sorted(rows, key=lambda row: (-row.skew, row.token))
    return ranked


@dataclass(frozen=True)
class InventoryFault:
    """One broken rule in the authored phrase inventory. Always an error."""

    signal: str
    #: The offending phrase form, or empty when the fault is the signal's.
    form: str
    reason: str


@dataclass(frozen=True)
class InventoryLexiconHit:
    """An inventory phrase for one signal that reads as another signal."""

    signal: str
    form: str
    foreign_signal: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class VectorHit:
    """A generated line carrying signal language its own vector does not assert."""

    fragment_id: str
    library: str
    #: The signal whose lexicon matched.
    signal: str
    #: ``"null"`` (the vector declares the line silent about the signal) or
    #: ``"undeclared"`` (the vector has no key for it at all).
    state: str
    terms: tuple[str, ...]
    text: str


def read_inventory(path: Path) -> tuple[dict[str, tuple[Phrase, ...]], list[InventoryFault]]:
    """Parse the phrase inventory defensively: return what parsed, and what did not.

    ``declarative.load_inventory`` raises on the first structural fault, which is
    right for a build and wrong for a report -- a lint that aborts on the
    inventory prints nothing about the fifty libraries either. This reads the
    same file and turns the same faults into rows, so one run names every one of
    them. The build remains the strict gate: nothing here relaxes it.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, [InventoryFault(signal="", form=str(path), reason=f"cannot be read: {error}")]
    if not isinstance(payload, dict) or not payload:
        return {}, [
            InventoryFault(
                signal="", form=str(path), reason="is not a non-empty object keyed by signal"
            )
        ]

    inventory: dict[str, tuple[Phrase, ...]] = {}
    faults: list[InventoryFault] = []
    for signal in sorted(payload):
        spec = payload[signal]
        if not isinstance(spec, dict) or not isinstance(spec.get("phrases"), list):
            faults.append(InventoryFault(signal, "", "has no 'phrases' list"))
            continue
        phrases: list[Phrase] = []
        for entry in spec["phrases"]:
            pair = (entry.get("text"), entry.get("negated")) if isinstance(entry, dict) else ()
            if len(pair) != 2 or not all(isinstance(form, str) and form.strip() for form in pair):
                faults.append(
                    InventoryFault(
                        signal,
                        repr(entry),
                        "is not a {'text', 'negated'} object of two non-empty strings",
                    )
                )
                continue
            phrases.append(Phrase(text=pair[0], negated=pair[1]))
        inventory[signal] = tuple(phrases)
    return inventory, faults


def inventory_faults(
    inventory: Mapping[str, Sequence[Phrase]],
    *,
    library_lines: Iterable[str],
    encoder_signals: Iterable[str],
) -> list[InventoryFault]:
    """Return every broken inventory rule (DD10), by signal, signal-level first.

    Every rule is checked against every phrase rather than stopping at the first
    fault, because the reader is about to edit one file and wants the whole list.

    ``library_lines`` is the hand-written corpus -- the generated library is
    excluded, because a generated line *is* composed of inventory phrases and
    comparing them would report the generator working. ``encoder_signals`` comes
    from the ruleset rather than from the manifest, for the same reason
    ``null_on`` validation does: a signal being written has a declaration before
    it has libraries.
    """
    known = set(encoder_signals)
    lines = {normalise(line) for line in library_lines}
    faults: list[InventoryFault] = []
    for signal in sorted(inventory):
        phrases = inventory[signal]
        if signal in EXCLUDED_SIGNALS:
            faults.append(
                InventoryFault(
                    signal,
                    "",
                    "cannot be stated by a declarative frame: its label turns on a 30-day "
                    "window and the section 9 policy rules, not on what the sentence "
                    "mentions (DD9)",
                )
            )
        elif signal not in known:
            faults.append(
                InventoryFault(
                    signal,
                    "",
                    "is not a Boolean signal the ruleset sends to the encoder, so lines "
                    "asserting it would carry a key no head consumes",
                )
            )
        if len(phrases) < MIN_PHRASES_PER_SIGNAL:
            faults.append(
                InventoryFault(
                    signal,
                    "",
                    f"declares {len(phrases)} phrases, fewer than the {MIN_PHRASES_PER_SIGNAL} "
                    "below which the phrase becomes a proxy for the cluster",
                )
            )
        for phrase in phrases:
            if len(phrase.text.split()) > MAX_PHRASE_WORDS:
                faults.append(
                    InventoryFault(
                        signal, phrase.text, f"is over {MAX_PHRASE_WORDS} words in its bare form"
                    )
                )
            for form in (phrase.text, phrase.negated):
                if normalise(form) in lines:
                    faults.append(
                        InventoryFault(
                            signal,
                            form,
                            "reproduces a hand-written library line verbatim, which would put "
                            "train text inside a generated val fragment",
                        )
                    )
    return faults


def inventory_lexicon_hits(
    inventory: Mapping[str, Sequence[Phrase]],
) -> list[InventoryLexiconHit]:
    """Report inventory phrases that read as a signal other than their own.

    Reported, never failed. The lexicons over-reach by design and this is the
    per-phrase view of the same 28 baselined hits the libraries carry -- but a
    phrase is reused across hundreds of generated lines, so re-reading one here
    is worth more than re-reading one library line.
    """
    hits: list[InventoryLexiconHit] = []
    for signal in sorted(inventory):
        for phrase in inventory[signal]:
            for foreign in SIGNAL_LEXICONS:
                if foreign == signal:
                    continue
                for form in (phrase.text, phrase.negated):
                    if terms := lexicon_matches(form, foreign):
                        hits.append(InventoryLexiconHit(signal, form, foreign, terms))
    return sorted(hits, key=lambda hit: (hit.signal, hit.foreign_signal, hit.form))


def declarative_vector_hits(fragments: Iterable[Fragment]) -> list[VectorHit]:
    """Check a generated line's per-line vector against its own text.

    The only check a lexicon can make on a per-line vector, and it is one-sided:
    it can say "the text reads as a signal the vector is silent about", and it
    can never say the vector is right. An *asserted* signal is skipped for the
    reason :func:`signal_language_hits` skips a library's own signal -- a line
    asserting dysuria matching the dysuria lexicon is the lexicon working.

    Both remaining states are reported and kept apart, because only one of them
    is a claim: ``null`` supervises a head towards "not mentioned" and so is
    contradicted by the text, while ``undeclared`` teaches nothing at all and is
    the DD14 pair by construction.
    """
    hits: list[VectorHit] = []
    for fragment in fragments:
        if not is_generated(fragment):
            continue
        for signal in SIGNAL_LEXICONS:
            value = fragment.value_for(signal)
            if value is True or value is False:
                continue
            if terms := lexicon_matches(fragment.text, signal):
                hits.append(
                    VectorHit(
                        fragment_id=fragment.fragment_id,
                        library=fragment.library,
                        signal=signal,
                        state="undeclared" if value is UNDECLARED else "null",
                        terms=terms,
                        text=fragment.text,
                    )
                )
    return sorted(hits, key=lambda hit: (hit.signal, hit.state, hit.fragment_id))


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


def render_report(
    fragments: Sequence[Fragment],
    *,
    inventory_path: Path | None = None,
    encoder_signals: Iterable[str] = (),
) -> list[str]:
    """Render every report as printable lines.

    ``inventory_path`` is optional so the library reports can be run against a
    manifest that has no declarative library -- a fixture, or the tree before
    this ticket. When it is given, the inventory section is rendered and its
    faults are returned by :func:`inventory_report_faults` for the caller to
    exit on: a report function that decided the exit code would be a report
    function nobody could run for a look.
    """
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

    lines += ["", "Generated libraries (not compared above)"]
    lines += render_generated_libraries(fragments)

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

    lines += ["", "Token / label-class association (section 8's first uncaught fault)"]
    lines += render_token_association(fragments)

    lines += ["", "Split coverage (DD9: generation aborts on an empty cell)"]
    lines += render_split_coverage(fragments)

    if inventory_path is not None:
        lines += ["", "Declarative phrase inventory"]
        lines += render_inventory(
            inventory_path, fragments=fragments, encoder_signals=encoder_signals
        )
    return lines


def inventory_report_faults(
    inventory_path: Path, fragments: Iterable[Fragment], encoder_signals: Iterable[str]
) -> list[InventoryFault]:
    """Return the inventory's hard faults: what ``--lint`` exits non-zero on."""
    inventory, structural = read_inventory(inventory_path)
    return structural + inventory_faults(
        inventory,
        library_lines=[f.text for f in fragments if not is_generated(f)],
        encoder_signals=encoder_signals,
    )


def render_generated_libraries(fragments: Sequence[Fragment]) -> list[str]:
    """Render each generated library's line, cluster, arity and frame distribution."""
    generated = generated_libraries(fragments)
    lines: list[str] = [
        "  A fixed frame makes near-duplicate text the expected output, so the pairs "
        "above carry no signal for these; the cluster and frame counts are what to read "
        "instead (DD16).",
        f"  libraries: {len(generated)}",
    ]
    if not generated:
        lines.append("  (none)")
    for summary in generated.values():
        lines.append(
            f"  {summary.library}: {summary.lines} lines across {summary.clusters} clusters"
        )
        for arity, count in summary.by_arity.items():
            lines.append(f"    arity {arity}: {count} lines")
        sizes = summary.cluster_sizes
        if sizes:
            lines.append(
                f"    lines per cluster: min {sizes[0]}, median {sizes[len(sizes) // 2]}, "
                f"max {sizes[-1]}"
            )
        for frame, count in summary.by_frame.items():
            lines.append(f"    frame {frame}: {count} lines")

    hits = declarative_vector_hits(fragments)
    lines += ["", f"  Generated vectors carrying another signal's language: {len(hits)}"]
    lines.append(f"  {DECLARATIVE_VECTOR_HEADER}")
    by_cell: dict[tuple[str, str], list[VectorHit]] = {}
    for hit in hits:
        by_cell.setdefault((hit.signal, hit.state), []).append(hit)
    if not by_cell:
        lines.append("    (none)")
    for signal, state in sorted(by_cell):
        cell = by_cell[(signal, state)]
        # A hit naming the signal in a word of its own is a different animal
        # from one pairing a urinary anchor with another clause's modifier, and
        # only the anchor side of the latter varies -- listing every
        # "toilet/urine/wee+pain" permutation buries the distinction the reader
        # is here for. So: the two counts, and the modifiers that did it.
        named = [hit for hit in cell if any("+" not in term for term in hit.terms)]
        modifiers = sorted(
            {
                modifier
                for hit in cell
                for term in hit.terms
                if "+" in term
                for modifier in term.split("+", 1)[1].split("/")
            }
        )
        bare_terms = sorted({term for hit in named for term in hit.terms if "+" not in term})
        lines.append(
            f"    {signal:<28}{state:<12}{len(cell):>5}  "
            f"{len(cell) - len(named)} by anchor+modifier, {len(named)} naming the signal"
        )
        if modifiers:
            lines.append(f"      modifiers: {', '.join(modifiers)}")
        if bare_terms:
            lines.append(f"      terms: {', '.join(bare_terms)}")
        # Named hits first: those are the ones where the text says the signal
        # outright and the vector says nothing, which is the only shape here
        # that would be a labelling fault rather than lexicon over-reach.
        shown = named + [hit for hit in cell if hit not in named]
        for hit in shown[:CROSS_SIGNAL_DETAIL_LIMIT]:
            lines.append(f"      {hit.fragment_id} {_wrap(hit.text, 84)}")
        if len(cell) > CROSS_SIGNAL_DETAIL_LIMIT:
            lines.append(
                f"      ... and {len(cell) - CROSS_SIGNAL_DETAIL_LIMIT} more, counted "
                "above but not shown"
            )
    return lines


def render_inventory(
    inventory_path: Path,
    *,
    fragments: Sequence[Fragment],
    encoder_signals: Iterable[str] = (),
) -> list[str]:
    """Render the inventory's faults and its cross-lexicon rows."""
    inventory, structural = read_inventory(inventory_path)
    faults = structural + inventory_faults(
        inventory,
        library_lines=[f.text for f in fragments if not is_generated(f)],
        encoder_signals=encoder_signals,
    )
    lines: list[str] = [f"  {INVENTORY_HEADER}", f"  {inventory_path}"]
    lines.append(f"  {len(inventory)} signals, {sum(len(p) for p in inventory.values())} phrases")
    for signal in sorted(inventory):
        lines.append(f"    {signal:<28}{len(inventory[signal]):>3} phrases")

    lines += ["", f"  faults (a failure): {len(faults)}"]
    for fault in faults:
        subject = f"{fault.signal} {fault.form!r}" if fault.form else fault.signal
        lines += textwrap.wrap(f"    {subject}: {fault.reason}", 96, subsequent_indent="      ")

    hits = inventory_lexicon_hits(inventory)
    lines += ["", f"  phrases reading as another signal: {len(hits)}"]
    lines.append(f"  {INVENTORY_LEXICON_HEADER}")
    for hit in hits:
        lines.append(
            f"    {hit.signal:<28}{hit.foreign_signal:<28}[{', '.join(hit.terms)}] {hit.form!r}"
        )
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


def _render_token_rows(rows: Sequence[TokenAssociation]) -> list[str]:
    """Render one block's detail lines, capped and with the elision counted."""
    if not rows:
        return ["      (none)"]
    lines = []
    for row in rows[:TOKEN_ASSOCIATION_DETAIL_LIMIT]:
        rates = row.rates
        cells = "".join(f"{rates[label]:>8.3f}" for label in TOKEN_LABEL_CLASSES)
        lines.append(f"      {row.token:<18}{row.skew:>7.3f}{row.support:>7}{cells}")
        breakdown = "  ".join(
            f"{library} {row.library_lines[library]}/{row.library_totals[library]}"
            for library in row.library_lines
        )
        # Wrapped rather than truncated: this line is the only place the
        # within-null spread is readable, so an elided tail would elide the
        # thing caveat (2) sends the reader here for.
        lines += textwrap.wrap(
            breakdown, 96, initial_indent="        ", subsequent_indent="        "
        )
    if len(rows) > TOKEN_ASSOCIATION_DETAIL_LIMIT:
        lines.append(
            f"      ... and {len(rows) - TOKEN_ASSOCIATION_DETAIL_LIMIT} more, "
            "counted above but not shown"
        )
    return lines


def render_token_association(fragments: Sequence[Fragment]) -> list[str]:
    """Render the per-signal token-label association report.

    Two blocks per signal, printed apart and labelled, because they are
    different faults. The first is section 8's: a token confined to one label
    class, which separates that class perfectly. The second is the frequency
    skew found later in the fever libraries, where a token is on every class and
    simply used far more by one of them; a head can read that as easily as it
    can read a token it only ever sees on one side.
    """
    ranked = token_label_association(fragments)
    lines: list[str] = []
    for paragraph in TOKEN_ASSOCIATION_HEADER.split("\n"):
        lines += textwrap.wrap(paragraph.strip(), 96, initial_indent="  ", subsequent_indent="  ")
    header = f"      {'token':<18}{'skew':>7}{'lines':>7}" + "".join(
        f"{label:>8}" for label in TOKEN_LABEL_CLASSES
    )
    for signal in sorted(ranked):
        rows = ranked[signal]
        if not rows:
            lines += ["", f"  {signal}: no token clears the support floor"]
            continue
        totals = rows[0].class_totals
        sizes = ", ".join(f"{label} {totals[label]}" for label in TOKEN_LABEL_CLASSES)
        confined = [row for row in rows if row.classes_present == 1]
        spread = [row for row in rows if row.classes_present > 1]
        lines += [
            "",
            f"  {signal}: {len(rows)} tokens on {MIN_TOKEN_SUPPORT}+ lines ({sizes} lines)",
            f"    confined to one label class: {len(confined)}",
            header,
        ]
        lines += _render_token_rows(confined)
        lines += [
            f"    present in more than one label class but skewed: {len(spread)}",
            header,
        ]
        lines += _render_token_rows(spread)
    return lines


#: Printed above the split-coverage table.
SPLIT_COVERAGE_HEADER = (
    "Each cell is lines/clusters. The cluster is the unit the split is assigned "
    "in, so a cell whose two numbers are far apart holds fewer ideas than lines "
    "-- one idea written six ways rather than six ideas. 'frames' counts the "
    "distinct sentence frames a generated library was composed from and is '-' "
    "for a hand-written one, where every line is its own frame: 12.1 asks for "
    "the frame count beside the line count because a templated library's lines "
    "are its frames multiplied by something, and reading the first without the "
    "second is how a library comes to look richer than it is."
)


def render_split_coverage(fragments: Sequence[Fragment]) -> list[str]:
    """Render each library's lines and clusters per split, its frames, and empties."""
    counts: dict[str, dict[str, int]] = {}
    for fragment in fragments:
        cell = counts.setdefault(fragment.library, dict.fromkeys(SPLITS, 0))
        cell[fragment.split] += 1
    clusters = clusters_by_split(fragments)
    frames = frames_by_library(fragments)

    lines = [f"  {SPLIT_COVERAGE_HEADER}"]
    lines.append(
        f"  {'library':<36}" + "".join(f"{split:>12}" for split in SPLITS) + f"{'frames':>8}"
    )
    empty = 0
    for library in sorted(counts):
        row = counts[library]
        empty += sum(1 for split in SPLITS if not row[split])
        marker = "  <- empty cell" if any(not row[split] for split in SPLITS) else ""
        cells = "".join(f"{row[split]}/{clusters[library][split]}".rjust(12) for split in SPLITS)
        frame_count = str(len(frames[library])) if frames[library] else "-"
        lines.append(f"  {library:<36}" + cells + f"{frame_count:>8}" + marker)
    lines.append(f"  empty cells: {empty}")
    return lines
