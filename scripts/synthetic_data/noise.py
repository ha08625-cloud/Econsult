"""Character-level damage for finished synthetic datasets.

The fragment libraries were typed by authors who were concentrating. Real
submissions are typed into a phone at eleven at night. This module is the pure
text-to-text half of the pass that closes that gap: the operations, the frozen
lexicon, the per-example RNG and :func:`damage_text`. It reads no files, knows
and imports nothing from the generator except
:func:`~scripts.synthetic_data.recombine._length_stats`, which the directory
pass needs to recompute ``token_counts`` in the shape the sidecar already uses
-- two implementations of one statistic drifting apart is worse than the
coupling. Nothing here loads a manifest, a ruleset or a pool, which is the whole
point of doing this as post-processing rather than as a generator flag
(``arch_training.md`` 12.6, DD1).

**The one risk worth naming.** Every other step in the pipeline fixes the label
*before* the text exists, so the text cannot make the label wrong (section 2).
This step edits text *after* the label is fixed, so for the first time a
mechanical step could make text stop matching its label: ``hot`` -> ``not`` is
one substitution. That is made impossible by construction rather than rare by
arithmetic, in both directions:

* a **character-level** operation never touches a frozen token, and never
  *produces* one -- the draw is rejected and redrawn instead;
* a **shape-preserving** operation (dropping an apostrophe, folding case) may
  apply to anything, frozen included, because it cannot change which word a
  token is: ``dont`` is still the negation and ``Ive`` is still first person.
  These are also the errors a phone keyboard actually produces, so they carry
  roughly half the default weight rather than being a footnote to the letter
  damage (DD10).

Rejection is tested against the frozen lexicon only, and **nothing in that test
can see the label**, so rejection rates vary by word and never by class (DD6).
Where a draw is rejected the pass redraws at most :data:`MAX_REDRAWS` times and
then leaves the word alone; the realised edit rate therefore lands slightly
below the requested one, which is telemetry rather than a bug.

The frozen set is two things joined: :data:`STRUCTURAL_FROZEN` (negation,
person, tense and modality, shared by every signal) plus the signal's own
vocabulary, taken from :data:`~scripts.synthetic_data.lint.SIGNAL_LEXICONS`.
How much of that vocabulary is frozen is the one design decision here a
reasonable person could take either way, so it is a flag rather than a
constant -- see :data:`FREEZE_MODES`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .lint import SIGNAL_LEXICONS
from .recombine import _length_stats


class NoiseError(RuntimeError):
    """A dataset or configuration the pass refuses to damage.

    Raised rather than warned about, deliberately. A missing or thin frozen
    lexicon fails *silently* otherwise: the pass runs, the output looks fine,
    and the label noise is invisible in exactly the way section 2 exists to
    prevent.
    """


#: Redraws allowed after a rejected draw before the word is left alone (DD6).
MAX_REDRAWS = 3

#: How much of a signal's own vocabulary joins the frozen set.
#:
#: ``short`` freezes vocabulary words of :data:`SHORT_WORD_MAX_LENGTH`
#: characters or fewer and leaves the longer ones damageable by at most one
#: character operation. Short words are where a single edit is proportionally
#: enormous and where the flip risk actually lives ("hot"/"not", "no"/"on"); no
#: single-character edit turns "temperature" into a negation, and the failure
#: mode for long words is degradation towards unreadable rather than inversion.
#:
#: ``all`` freezes every vocabulary word. That is the conservative reading of
#: 12.6 as literally written, and it is one flag away because it makes the
#: experiment unable to measure the thing it is named after: under ``all`` the
#: model never sees "temprature", and robustness to a misspelt "temperature" is
#: the headline claim being tested. Ship ``short``, and let the rate sweep argue
#: it back.
FREEZE_MODES = ("short", "all")

#: See :data:`FREEZE_MODES`.
DEFAULT_FREEZE_MODE = "short"

#: Share of examples the directory pass leaves completely undamaged (DD5).
DEFAULT_CLEAN_SHARE = 0.25

#: Vocabulary words this long or shorter are frozen under ``short``.
SHORT_WORD_MAX_LENGTH = 5

#: Never damaged by a character operation, never produced by one, for every
#: signal. Four groups, and each of them is a *label* rather than decoration:
#: negation decides ``true`` from ``false``, person and tense decide the null
#: axes ("my son", "last month"), and modality is what separates a hard-case
#: ``null`` from an assertion. An edit that lands inside one of these is a coin
#: flip on whether the thing the fragment exists to teach survives at all.
#:
#: Straight and curly apostrophes both fold to the straight form on lookup
#: (:func:`fold_token`), so only the straight spellings are listed. Both the
#: apostrophised and the bare spelling *are* listed, because dropping an
#: apostrophe is a legal operation here and its output has to be frozen too.
STRUCTURAL_FROZEN = (
    # Negation.
    "no",
    "not",
    "never",
    "none",
    "nothing",
    "without",
    "nor",
    "nope",
    "dont",
    "don't",
    "didnt",
    "didn't",
    "havent",
    "haven't",
    "hasnt",
    "hasn't",
    "isnt",
    "isn't",
    "wasnt",
    "wasn't",
    "arent",
    "aren't",
    "cant",
    "can't",
    "couldnt",
    "couldn't",
    "wouldnt",
    "wouldn't",
    "wont",
    "won't",
    # Person: whose symptom this is, which is the third-party null axis.
    "i",
    "im",
    "i'm",
    "ive",
    "i've",
    "my",
    "me",
    "he",
    "she",
    "they",
    "his",
    "her",
    "their",
    "him",
    "them",
    "son",
    "daughter",
    "wife",
    "husband",
    "mum",
    "mother",
    "dad",
    "father",
    "partner",
    "nan",
    "gran",
    "he's",
    "hes",
    "she's",
    "shes",
    # Tense and recency: the "is it happening now" null axis.
    "had",
    "has",
    "have",
    "was",
    "were",
    "is",
    "am",
    "are",
    "been",
    "did",
    "does",
    "do",
    "ago",
    "last",
    "since",
    "yesterday",
    "today",
    "tonight",
    "now",
    "then",
    "before",
    "after",
    "week",
    "weeks",
    "day",
    "days",
    "month",
    "months",
    # Modality: what separates a hard-case null from a claim.
    "maybe",
    "might",
    "may",
    "could",
    "think",
    "thought",
    "feel",
    "felt",
    "seems",
    "seemed",
    "probably",
    "possibly",
    "bit",
    "slightly",
    "really",
    "very",
)

#: Curly punctuation folded to ASCII on lookup. Same spirit as
#: :mod:`~scripts.synthetic_data.normalise`, which is deliberately *not*
#: imported: it also strips terminal punctuation, which is one of the things
#: this module edits on purpose and must therefore be able to see.
_APOSTROPHE_FOLD = {
    ord("‘"): "'",  # left single quotation mark
    ord("’"): "'",  # right single quotation mark
}

#: Punctuation stripped from the ends of a token before a lexicon lookup, so
#: that "fever," and "(hot)" are recognised. Internal apostrophes survive,
#: because "dont" and "don't" are separate entries.
_EDGE_PUNCTUATION = "\"'`.,!?;:()[]{}<>*_-—–“”"

#: One whitespace-separated chunk, split into the word and the punctuation
#: hanging off either end, so an operation edits the word and the punctuation
#: reassembles unchanged.
_CHUNK = re.compile(r"^(?P<prefix>\W*)(?P<word>.*?)(?P<suffix>\W*)$", re.UNICODE)

_WHITESPACE_RUN = re.compile(r"(\s+)")


def fold_token(token: str) -> str:
    """Return the lexicon-lookup form of ``token``.

    Lowercased, curly apostrophes folded to straight, edge punctuation
    stripped. Matching is case- and edge-punctuation-insensitive so that "Hot",
    "hot," and "(hot)" are all the frozen word they obviously are.
    """
    folded = unicodedata.normalize("NFKC", token).translate(_APOSTROPHE_FOLD).lower()
    return folded.strip(_EDGE_PUNCTUATION)


@dataclass(frozen=True)
class Token:
    """One whitespace-separated chunk of an example.

    ``prefix + word + suffix`` reconstructs the chunk exactly. ``word`` is
    empty for a chunk that is punctuation only ("--"), which is why the rate in
    DD4 counts tokens whose ``word`` is non-empty rather than chunks.
    """

    prefix: str
    word: str
    suffix: str
    index: int

    @property
    def is_word(self) -> bool:
        return bool(self.word)

    @property
    def text(self) -> str:
        return f"{self.prefix}{self.word}{self.suffix}"


def split_token(chunk: str) -> tuple[str, str, str]:
    """Split one whitespace-free chunk into ``(prefix, word, suffix)``."""
    match = _CHUNK.match(chunk)
    if match is None:  # pragma: no cover - the pattern matches any string
        return "", chunk, ""
    return match.group("prefix"), match.group("word"), match.group("suffix")


def split_words(text: str) -> Iterator[Token]:
    """Yield one :class:`Token` per whitespace-separated chunk of ``text``."""
    index = 0
    for piece in _WHITESPACE_RUN.split(text):
        if not piece or piece.isspace():
            continue
        prefix, word, suffix = split_token(piece)
        yield Token(prefix=prefix, word=word, suffix=suffix, index=index)
        index += 1


def count_words(text: str) -> int:
    """Number of damageable words in ``text`` -- the denominator for the rate."""
    return sum(1 for token in split_words(text) if token.is_word)


# ---------------------------------------------------------------------------
# The frozen lexicon
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoiseLexicon:
    """The two word sets that bound what an edit is allowed to do.

    ``frozen`` is never damaged by a character operation and never produced by
    one. ``damageable`` is the signal's longer vocabulary: damageable by at most
    one character operation per word, provided the result is neither a frozen
    token nor a *different* signal word.
    """

    signal: str
    freeze_mode: str
    frozen: frozenset[str]
    damageable: frozenset[str]

    def is_frozen(self, word: str) -> bool:
        return fold_token(word) in self.frozen

    def forbids(self, candidate: str, *, original: str) -> bool:
        """Whether a character operation's output must be rejected."""
        folded = fold_token(candidate)
        if folded in self.frozen:
            return True
        return folded in self.damageable and folded != fold_token(original)


def signal_vocabulary(signal: str) -> frozenset[str]:
    """Every word of ``signal``'s lint lexicon, flattened and folded.

    ``terms``, ``anchors`` and ``modifiers`` are flattened into one flat word
    set and multi-word phrases are split. The lexicons were built to *detect*
    signal language, so anchors and modifiers only mean anything in pairs;
    flattening them errs towards **over**-freezing, which is the safe direction
    -- fewer words get damaged and no label moves.
    """
    try:
        lexicon = SIGNAL_LEXICONS[signal]
    except KeyError:
        raise NoiseError(
            f"no frozen lexicon for signal {signal!r}; known signals are "
            f"{', '.join(sorted(SIGNAL_LEXICONS))}"
        ) from None
    words = {
        folded
        for phrase in lexicon.terms + lexicon.anchors + lexicon.modifiers
        for word in phrase.split()
        if (folded := fold_token(word))
    }
    return frozenset(words)


@cache
def noise_lexicon(signal: str, freeze_mode: str = DEFAULT_FREEZE_MODE) -> NoiseLexicon:
    """Build the frozen and damageable sets for one signal.

    This is also the guard. A signal with no lexicon, or an empty one, raises
    :class:`NoiseError` rather than quietly producing an under-protected
    dataset -- the same fail-fast posture as the generator's check that the
    signal exists in the ruleset as a ``send_to_encoder`` Boolean. The guard is
    keyed on "a non-empty lexicon exists for this signal" rather than on
    ``fever_present``, so the seven signals come for free; it comes out when
    12.5 moves the lexicon into the manifest.
    """
    if freeze_mode not in FREEZE_MODES:
        raise NoiseError(f"unknown freeze mode {freeze_mode!r}; expected one of {FREEZE_MODES}")
    vocabulary = signal_vocabulary(signal)
    if not vocabulary:
        raise NoiseError(f"frozen lexicon for signal {signal!r} is empty")
    structural = frozenset(fold_token(word) for word in STRUCTURAL_FROZEN)
    if freeze_mode == "all":
        return NoiseLexicon(
            signal=signal,
            freeze_mode=freeze_mode,
            frozen=structural | vocabulary,
            damageable=frozenset(),
        )
    short = frozenset(word for word in vocabulary if len(word) <= SHORT_WORD_MAX_LENGTH)
    return NoiseLexicon(
        signal=signal,
        freeze_mode=freeze_mode,
        frozen=structural | short,
        damageable=(vocabulary - short) - structural,
    )


def frozen_tokens(signal: str, freeze_mode: str = DEFAULT_FREEZE_MODE) -> frozenset[str]:
    """Tokens no character operation may touch or produce, for ``signal``."""
    return noise_lexicon(signal, freeze_mode).frozen


def damageable_signal_tokens(signal: str, freeze_mode: str = DEFAULT_FREEZE_MODE) -> frozenset[str]:
    """Signal words one character operation may damage, for ``signal``."""
    return noise_lexicon(signal, freeze_mode).damageable


# ---------------------------------------------------------------------------
# The operations
# ---------------------------------------------------------------------------

#: QWERTY neighbours, letters only, written out in both directions so the map
#: itself is the thing under test rather than a symmetrising loop. A neighbour
#: substitution is much closer to a real slip than a uniform random letter is,
#: and costs thirty lines.
KEYBOARD_NEIGHBOURS: dict[str, str] = {
    "q": "was",
    "w": "qeasd",
    "e": "wrsdf",
    "r": "etdfg",
    "t": "ryfgh",
    "y": "tughj",
    "u": "yihjk",
    "i": "uojkl",
    "o": "ipkl",
    "p": "ol",
    "a": "qwszx",
    "s": "qweadzxc",
    "d": "wersfxcv",
    "f": "ertdgcvb",
    "g": "rtyfhvbn",
    "h": "tyugjbnm",
    "j": "yuihknm",
    "k": "uiojlm",
    "l": "iopk",
    "z": "asx",
    "x": "zasdc",
    "c": "xsdfv",
    "v": "cdfgb",
    "b": "vfghn",
    "n": "bghjm",
    "m": "nhjk",
}

_APOSTROPHES = "'‘’"


def _alphabetic_positions(word: str) -> list[int]:
    return [index for index, character in enumerate(word) if character.isalpha()]


def drop_apostrophe(word: str, rng: random.Random) -> str | None:
    """``don't`` -> ``dont``. Shape-preserving: the word is still the word."""
    positions = [index for index, character in enumerate(word) if character in _APOSTROPHES]
    if not positions:
        return None
    cut = rng.choice(positions)
    return word[:cut] + word[cut + 1 :]


def lowercase(word: str, rng: random.Random) -> str | None:
    """``Monday`` -> ``monday``. Shape-preserving."""
    folded = word.lower()
    return None if folded == word else folded


def drop_letter(word: str, rng: random.Random) -> str | None:
    """Drop one letter. Needs two, or the word disappears."""
    positions = _alphabetic_positions(word)
    if len(positions) < 2:
        return None
    cut = rng.choice(positions)
    return word[:cut] + word[cut + 1 :]


def double_letter(word: str, rng: random.Random) -> str | None:
    """Double one letter -- the "temperatureature" family of slip."""
    positions = _alphabetic_positions(word)
    if not positions:
        return None
    at = rng.choice(positions)
    return word[: at + 1] + word[at] + word[at + 1 :]


def transpose_adjacent(word: str, rng: random.Random) -> str | None:
    """Swap two adjacent letters -- "the" -> "teh"."""
    positions = _alphabetic_positions(word)
    pairs = [
        (first, second)
        for first, second in zip(positions, positions[1:], strict=False)
        if second == first + 1 and word[first] != word[second]
    ]
    if not pairs:
        return None
    first, second = rng.choice(pairs)
    characters = list(word)
    characters[first], characters[second] = characters[second], characters[first]
    return "".join(characters)


def keyboard_neighbour(word: str, rng: random.Random) -> str | None:
    """Replace one letter with a QWERTY neighbour, keeping its case."""
    positions = [
        index for index in _alphabetic_positions(word) if word[index].lower() in KEYBOARD_NEIGHBOURS
    ]
    if not positions:
        return None
    at = rng.choice(positions)
    original = word[at]
    replacement = rng.choice(KEYBOARD_NEIGHBOURS[original.lower()])
    if original.isupper():
        replacement = replacement.upper()
    return word[:at] + replacement + word[at + 1 :]


def drop_terminal_punctuation(text: str, rng: random.Random, lexicon: NoiseLexicon) -> str | None:
    """Strip a single trailing ``.``, ``!`` or ``?``."""
    stripped = text.rstrip()
    if not stripped or stripped[-1] not in ".!?":
        return None
    at = len(stripped) - 1
    return text[:at] + text[at + 1 :]


def drop_space(text: str, rng: random.Random, lexicon: NoiseLexicon) -> str | None:
    """Delete one space, never one adjacent to a frozen token.

    "nofever" is a single unknown token to the tokenizer, so the negation can
    become effectively invisible while the label still says ``false``. The rule
    runs in both directions -- the space *before* a frozen token and the space
    *after* it -- so "no fever" and "not had" stay two words while "on the
    toilet again" may weld freely.

    Under ``short`` a six-character-or-longer signal word is not frozen, so
    "a temperature" may weld to "atemperature"; under ``all`` it may not. That
    is the same trade the freeze mode makes everywhere else, and the rate sweep
    is what settles it.
    """
    pieces = _WHITESPACE_RUN.split(text)
    candidates = []
    for index, piece in enumerate(pieces):
        if piece != " " or index == 0 or index + 1 >= len(pieces):
            continue
        before, after = pieces[index - 1], pieces[index + 1]
        if lexicon.is_frozen(before) or lexicon.is_frozen(after):
            continue
        welded = "".join(split_token(before + after))
        if fold_token(welded) in lexicon.frozen or fold_token(welded) in lexicon.damageable:
            continue
        candidates.append(index)
    if not candidates:
        return None
    at = rng.choice(candidates)
    return "".join(pieces[:at] + pieces[at + 1 :])


def lowercase_all(text: str, rng: random.Random, lexicon: NoiseLexicon) -> str | None:
    """Fold the whole example.

    Its own operation rather than an accumulation of per-word lowercasing,
    because section 8 records a case where casing alone separated a whole
    library, and that is a property of the example rather than of a word.
    """
    folded = text.lower()
    return None if folded == text else folded


#: Applied to one word at a time. The two shape-preserving operations are
#: allowed on frozen tokens; the four character-level ones are not.
WORD_OPERATIONS = {
    "drop_apostrophe": drop_apostrophe,
    "lowercase": lowercase,
    "drop_letter": drop_letter,
    "double_letter": double_letter,
    "transpose_adjacent": transpose_adjacent,
    "keyboard_neighbour": keyboard_neighbour,
}

#: The operations a frozen token is *not* protected from, because neither can
#: change which word a token is.
SHAPE_PRESERVING_OPERATIONS = frozenset({"drop_apostrophe", "lowercase"})

#: The operations that can turn one word into another, and are therefore
#: rejected against the frozen lexicon in both directions.
CHARACTER_OPERATIONS = frozenset(WORD_OPERATIONS) - SHAPE_PRESERVING_OPERATIONS

#: Applied once per example rather than per word.
TEXT_OPERATIONS = {
    "drop_terminal_punctuation": drop_terminal_punctuation,
    "drop_space": drop_space,
    "lowercase_all": lowercase_all,
}

#: Default per-word weights. Half the mass sits on the two shape-preserving
#: operations (DD10): missing apostrophes and lost capitals are what a phone
#: keyboard actually produces, they survive spellcheck because they are not
#: misspellings, and they cannot produce a different word.
WORD_OPERATION_WEIGHTS: dict[str, float] = {
    "drop_apostrophe": 0.25,
    "lowercase": 0.25,
    "drop_letter": 0.15,
    "double_letter": 0.10,
    "transpose_adjacent": 0.10,
    "keyboard_neighbour": 0.15,
}

#: Default whole-text weights. These are *not* shares of a weighted draw: each
#: operation gets its own Bernoulli draw per example at
#: ``min(1, rate * words * weight)``, so a weight of 1.0 makes the operation
#: about as likely as one more damaged word in the same example.
TEXT_OPERATION_WEIGHTS: dict[str, float] = {
    "drop_terminal_punctuation": 1.0,
    "drop_space": 0.5,
    "lowercase_all": 0.5,
}


def example_rng(seed: int | str, example_id: str) -> random.Random:
    """Per-example RNG, keyed on the example id rather than the line number.

    ``sha256`` rather than :func:`hash`, which is salted per process and would
    make two invocations disagree. Keying on the id is what makes noising a
    20,000-line file leave the first 10,000 lines identical to noising the
    10,000-line one, matching section 7's reproducibility property (DD3).
    """
    digest = hashlib.sha256(f"{seed}|{example_id}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def damage_word(
    word: str,
    rng: random.Random,
    lexicon: NoiseLexicon,
    *,
    weights: Mapping[str, float] | None = None,
) -> tuple[str, str | None]:
    """Apply at most one operation to ``word``.

    Draw an operation by weight and apply it. The result is rejected -- and the
    draw repeated, at most :data:`MAX_REDRAWS` times -- when the operation was
    character-level and the original was frozen, or the result folds to a
    frozen token, or it folds to a *different* damageable signal word. A draw
    whose operation cannot apply at all (no apostrophe, nothing to lowercase)
    is a rejection too. After the last redraw the word is returned unchanged
    (DD6); no looping, so the realised rate lands a little under the requested
    one.

    Returns ``(word, operation_name_or_None)``. Never composes two operations.
    """
    table = WORD_OPERATION_WEIGHTS if weights is None else weights
    names = [name for name, weight in table.items() if weight > 0]
    if not names:
        return word, None
    mass = [table[name] for name in names]
    for _ in range(MAX_REDRAWS + 1):
        name = rng.choices(names, weights=mass, k=1)[0]
        character_level = name in CHARACTER_OPERATIONS
        if character_level and lexicon.is_frozen(word):
            continue
        candidate = WORD_OPERATIONS[name](word, rng)
        if candidate is None or candidate == word:
            continue
        if character_level and lexicon.forbids(candidate, original=word):
            continue
        return candidate, name
    return word, None


@dataclass(frozen=True)
class DamageResult:
    """One example's damaged text and the telemetry the sidecar reports.

    ``words`` is the rate's denominator -- chunks with a word in them, so "--"
    does not count. ``selected`` is how many of those the Bernoulli draw picked,
    ``edited`` how many an operation actually landed on, and ``rejected`` the
    difference: a word whose every draw was refused by the frozen lexicon, or
    whose drawn operation could not apply at all (no apostrophe to drop, no
    capital to fold). Those are left alone rather than retried forever (DD6),
    which is why the realised rate lands under the requested one.

    ``operations`` counts whole-text operations too, so ``sum(operations)`` is
    the edit count the sidecar divides by ``words`` -- an example can carry more
    edits than it had words selected.
    """

    text: str
    operations: Counter[str]
    words: int
    selected: int
    edited: int
    rejected: int


def damage_example(
    text: str,
    rng: random.Random,
    *,
    rate: float,
    signal: str,
    freeze_mode: str = DEFAULT_FREEZE_MODE,
    word_weights: Mapping[str, float] | None = None,
    text_weights: Mapping[str, float] | None = None,
) -> DamageResult:
    """Damage one example, returning the text and its telemetry.

    Each word is selected independently with probability ``rate`` -- Bernoulli
    per word, not per example, so per-example counts vary naturally and the
    only correlation with the label is the length one section 9 already
    describes and measures (DD4). Each whole-text operation then gets one draw
    of its own at ``min(1, rate * words * weight)``.

    The pass never sees the label. That is the whole safety argument for the
    rate, and the reason the sidecar measures it per label anyway (DD9).
    """
    lexicon = noise_lexicon(signal, freeze_mode)
    realised: Counter[str] = Counter()
    pieces = _WHITESPACE_RUN.split(text)
    words = 0
    selected = 0
    edited = 0
    for index, piece in enumerate(pieces):
        if not piece or piece.isspace():
            continue
        prefix, word, suffix = split_token(piece)
        if not word:
            continue
        words += 1
        if rng.random() >= rate:
            continue
        selected += 1
        damaged, operation = damage_word(word, rng, lexicon, weights=word_weights)
        if operation is None:
            continue
        edited += 1
        realised[operation] += 1
        pieces[index] = f"{prefix}{damaged}{suffix}"
    result = "".join(pieces)

    table = TEXT_OPERATION_WEIGHTS if text_weights is None else text_weights
    for name, weight in table.items():
        if weight <= 0:
            continue
        if rng.random() >= min(1.0, rate * words * weight):
            continue
        candidate = TEXT_OPERATIONS[name](result, rng, lexicon)
        if candidate is None or candidate == result:
            continue
        result = candidate
        realised[name] += 1
    return DamageResult(
        text=result,
        operations=realised,
        words=words,
        selected=selected,
        edited=edited,
        rejected=selected - edited,
    )


def damage_text(
    text: str,
    rng: random.Random,
    *,
    rate: float,
    signal: str,
    freeze_mode: str = DEFAULT_FREEZE_MODE,
    word_weights: Mapping[str, float] | None = None,
    text_weights: Mapping[str, float] | None = None,
) -> tuple[str, Counter[str]]:
    """:func:`damage_example` without the telemetry, for callers that only want
    the text and the tally of what fired."""
    result = damage_example(
        text,
        rng,
        rate=rate,
        signal=signal,
        freeze_mode=freeze_mode,
        word_weights=word_weights,
        text_weights=text_weights,
    )
    return result.text, result.operations


# ---------------------------------------------------------------------------
# The directory pass
# ---------------------------------------------------------------------------

#: The only tree the pass will read from or write to. ``data/synthetic/`` holds
#: the hand-written fragment libraries and the manifest; a pass that could be
#: pointed at those could destroy the source material, and no flag is worth
#: that. Overridable by callers (the tests point it at a tmp tree) but not by
#: the CLI.
GENERATED_ROOT = Path("data/synthetic/generated")

#: Key order of a written record, matching :func:`~.recombine.to_record`, so a
#: diff between a clean tree and its noisy twin shows only ``text``.
RECORD_KEYS = ("example_id", "split", "text", "labels", "meta")

#: Sidecar fields every file in one input tree must agree on. A half-regenerated
#: tree -- three folds from one salt and two from another -- should fail here
#: rather than at training time, where it presents as an inexplicable score.
TREE_AGREEMENT_FIELDS = ("signal", "folds", "split_salt")

#: The three splits' label names, and the four label modes, as the sidecar
#: keys them. Duplicated from :mod:`~.recombine` rather than imported because
#: they are the *sidecar's* vocabulary here, not the generator's.
LABELS = ("true", "false", "null")
LABEL_MODES = ("true", "false", "null_structural", "null_ambiguous")


def sidecar_path(jsonl_path: Path) -> Path:
    """The ``.stats.json`` the generator writes beside ``jsonl_path``.

    Same convention as ``__main__.write_outputs`` and
    ``encoder_training.dataset.sidecar_path``, computed here rather than
    imported from either: it is three tokens of string arithmetic, and taking a
    dependency on the training package from the generation package to get it
    would be the tail wagging the dog.
    """
    return jsonl_path.parent / (jsonl_path.name + ".stats.json")


def label_name(value: object) -> str:
    """Render a label value as its sidecar key: ``true``, ``false`` or ``null``."""
    return "null" if value is None else ("true" if value else "false")


def parse_operation_weights(text: str | None) -> tuple[dict[str, float], dict[str, float]]:
    """Parse ``name=weight,...`` into ``(word_weights, text_weights)``.

    Parsed the way ``__main__``'s own weighted-mix flags are parsed, but with
    two differences that follow from what the weights *mean*. Word weights are
    shares of one weighted draw, so they are normalised here rather than
    required to sum to one. Whole-text weights are not shares of anything --
    each is a multiplier on its own Bernoulli draw at ``rate * words * weight``
    -- so they are taken verbatim.

    Naming any word operation replaces the whole word table; naming any
    whole-text operation replaces the whole text table. Anything unnamed in a
    table that was replaced is off. That is blunter than merging with the
    defaults, and deliberately so: a sweep cell that means "only apostrophes"
    should not silently keep five other operations because they were not
    mentioned.
    """
    if not text or not text.strip():
        return dict(WORD_OPERATION_WEIGHTS), dict(TEXT_OPERATION_WEIGHTS)

    parsed: dict[str, float] = {}
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, separator, raw = chunk.partition("=")
        name = name.strip()
        if not separator:
            raise NoiseError(
                f"malformed --operation-weights term {chunk!r}, expected 'operation=weight'"
            )
        if name in parsed:
            raise NoiseError(f"operation {name!r} appears twice in --operation-weights")
        if name not in WORD_OPERATIONS and name not in TEXT_OPERATIONS:
            known = ", ".join(sorted(set(WORD_OPERATIONS) | set(TEXT_OPERATIONS)))
            raise NoiseError(f"unknown operation {name!r} in --operation-weights; known: {known}")
        try:
            weight = float(raw)
        except ValueError:
            raise NoiseError(f"weight for {name!r} is not a number: {raw!r}") from None
        if weight < 0:
            raise NoiseError(f"weight for {name!r} is negative: {weight}")
        parsed[name] = weight

    word = {name: weight for name, weight in parsed.items() if name in WORD_OPERATIONS}
    whole = {name: weight for name, weight in parsed.items() if name in TEXT_OPERATIONS}
    if not word:
        word = dict(WORD_OPERATION_WEIGHTS)
    else:
        total = sum(word.values())
        if total <= 0:
            raise NoiseError("--operation-weights leaves every word operation at zero")
        word = {name: weight / total for name, weight in word.items()}
    if not whole:
        whole = dict(TEXT_OPERATION_WEIGHTS)
    return word, whole


@dataclass
class NoiseTally:
    """Running totals behind the sidecar's ``noise.realised`` block.

    Kept per label and per label mode because that is the point of the block
    (DD9): equality of edit density across the classes holds by construction --
    nothing in the rejection test can see the label -- and is measured on every
    run anyway, because if error density ever tracked the label the model would
    learn "misspelt implies fever" and nothing else in the pipeline would show
    it.
    """

    words: Counter[str] = field(default_factory=Counter)
    edits: Counter[str] = field(default_factory=Counter)
    mode_words: Counter[str] = field(default_factory=Counter)
    mode_edits: Counter[str] = field(default_factory=Counter)
    examples: Counter[str] = field(default_factory=Counter)
    clean: Counter[str] = field(default_factory=Counter)
    operations: Counter[str] = field(default_factory=Counter)
    total_words: int = 0
    selected: int = 0
    edited: int = 0
    rejected: int = 0

    def add(self, result: DamageResult, *, label: str, label_mode: str, was_clean: bool) -> None:
        edits = sum(result.operations.values())
        self.words[label] += result.words
        self.edits[label] += edits
        self.mode_words[label_mode] += result.words
        self.mode_edits[label_mode] += edits
        self.examples[label] += 1
        self.clean[label] += int(was_clean)
        self.operations.update(result.operations)
        self.total_words += result.words
        self.selected += result.selected
        self.edited += result.edited
        self.rejected += result.rejected

    def merge(self, other: NoiseTally) -> None:
        for name in ("words", "edits", "mode_words", "mode_edits", "examples", "clean"):
            getattr(self, name).update(getattr(other, name))
        self.operations.update(other.operations)
        self.total_words += other.total_words
        self.selected += other.selected
        self.edited += other.edited
        self.rejected += other.rejected

    @property
    def edits_per_hundred_words(self) -> float:
        total = sum(self.edits.values())
        return 0.0 if not self.total_words else round(100 * total / self.total_words, 4)

    def by_label_rates(self) -> dict[str, float]:
        return {
            label: (
                0.0
                if not self.words[label]
                else round(100 * self.edits[label] / self.words[label], 4)
            )
            for label in LABELS
        }

    def by_label_mode_rates(self) -> dict[str, float]:
        return {
            mode: (
                0.0
                if not self.mode_words[mode]
                else round(100 * self.mode_edits[mode] / self.mode_words[mode], 4)
            )
            for mode in LABEL_MODES
        }

    @property
    def largest_by_label_gap(self) -> float:
        """Widest spread in edit density across the labels that appear at all.

        The one number worth reading first after a run. It is not a tolerance
        check -- the pass has no threshold to fail -- but a gap that is not
        close to zero means something has learned to see the label.
        """
        rates = [rate for label, rate in self.by_label_rates().items() if self.words[label]]
        return 0.0 if len(rates) < 2 else round(max(rates) - min(rates), 4)

    def clean_share(self) -> dict[str, float]:
        return {
            label: (
                0.0
                if not self.examples[label]
                else round(self.clean[label] / self.examples[label], 4)
            )
            for label in LABELS
        }

    @property
    def overall_clean_share(self) -> float:
        total = sum(self.examples.values())
        return 0.0 if not total else round(sum(self.clean.values()) / total, 4)


def build_noise_stats(
    stats: Mapping[str, object],
    *,
    tally: NoiseTally,
    texts: Sequence[tuple[str, str, str, str]],
    source_dir: str,
    seed: int,
    rate: float,
    clean_share: float,
    freeze_mode: str,
    word_weights: Mapping[str, float],
    text_weights: Mapping[str, float],
) -> dict:
    """Return the output sidecar: the input's, with two things changed.

    ``token_counts`` is recomputed from the damaged texts, because deleting a
    space changes a word count and a sidecar has to describe the file sitting
    next to it (DD8). Everything else is passed through untouched --
    ``fragments``, ``fragment_pool_sizes``, ``fragment_counts``, ``requested``,
    ``realised`` and the whole fold configuration all describe the *fragments*,
    and the fragments were not edited. ``generator_version`` in particular is
    not bumped: the three splits of a fold must agree on it
    (``dataset._check_fold_agreement``) and a noisy tree is still that
    generator's output (DD7).

    A ``noise`` block is added. Its presence is the marker that a tree is
    noisy -- a clean tree has no such key -- which is also the guard against
    double-noising.

    ``texts`` is one ``(text, label, label_mode, fragment_count)`` row per
    damaged example.
    """
    output = deepcopy(dict(stats))

    by_label: dict[str, list[str]] = {label: [] for label in LABELS}
    by_mode: dict[str, list[str]] = {mode: [] for mode in LABEL_MODES}
    by_count: dict[str, list[str]] = {}
    for text, label, mode, count_key in texts:
        by_label.setdefault(label, []).append(text)
        by_mode.setdefault(mode, []).append(text)
        by_count.setdefault(count_key, []).append(text)
    # Keep the key set the input sidecar had, so a fragment count that happens
    # to be absent from one file does not silently vanish from its sidecar.
    previous = output.get("token_counts")
    previous_counts = previous.get("by_fragment_count", {}) if isinstance(previous, dict) else {}
    count_keys = sorted(set(by_count) | set(previous_counts), key=lambda key: (len(key), key))
    output["token_counts"] = {
        "by_label": {label: _length_stats(by_label.get(label, [])) for label in LABELS},
        "by_label_mode": {mode: _length_stats(by_mode.get(mode, [])) for mode in LABEL_MODES},
        "by_fragment_count": {key: _length_stats(by_count.get(key, [])) for key in count_keys},
    }

    output["noise"] = {
        "source_dir": source_dir,
        "seed": seed,
        "requested": {
            "rate": rate,
            "clean_share": clean_share,
            "freeze_signal_vocabulary": freeze_mode,
            "operation_weights": {
                "word": dict(word_weights),
                "text": dict(text_weights),
            },
        },
        "realised": {
            # DD9. These rows must agree with each other. If they ever stop
            # agreeing, error density has become a proxy for the label and
            # every number downstream of the dataset is worthless.
            "edits_per_hundred_words": {
                "by_label": tally.by_label_rates(),
                "by_label_mode": tally.by_label_mode_rates(),
                "overall": tally.edits_per_hundred_words,
                "largest_by_label_gap": tally.largest_by_label_gap,
            },
            "clean_share": {
                "by_label": tally.clean_share(),
                "overall": tally.overall_clean_share,
            },
            "operations": dict(sorted(tally.operations.items())),
            # ``selected`` minus ``edited`` is the DD6 gap: words the Bernoulli
            # draw picked whose every operation the frozen lexicon refused. It
            # is why the realised rate sits under the requested one.
            "words": {
                "total": tally.total_words,
                "selected": tally.selected,
                "edited": tally.edited,
                "rejected_then_left_alone": tally.rejected,
            },
        },
    }
    return output


def read_sidecar(jsonl_path: Path) -> dict:
    """Load the sidecar beside ``jsonl_path``, or explain why the pass stops.

    A missing sidecar is fatal here rather than at training time.
    ``dataset._read_stats`` refuses to load a dataset with no sidecar, so
    emitting the JSONL alone would produce a tree that fails when a GPU is
    already warm instead of when the pass is one second old.
    """
    path = sidecar_path(jsonl_path)
    if not path.is_file():
        raise NoiseError(f"no stats sidecar beside {jsonl_path}: expected {path}")
    try:
        stats = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise NoiseError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(stats, dict):
        raise NoiseError(f"{path} is not a JSON object")
    return stats


def check_directories(
    in_dir: Path, out_dir: Path, *, force: bool = False, root: Path | None = None
) -> None:
    """Refuse an input/output pair that could damage something irreplaceable.

    Every one of these is a startup error rather than a warning. The pass
    rewrites text in place-shaped ways, and the failure modes here are all
    silent: a tree noised on top of itself, a second pass over an already-noisy
    tree, a run that quietly reaches ``data/synthetic/`` where the hand-written
    libraries live.
    """
    # Resolved at call time rather than bound as a default, so a caller (and
    # the tests) can point the whole guard at a tree of its own.
    root = GENERATED_ROOT if root is None else root
    resolved_root = root.resolve()
    source = in_dir.resolve()
    target = out_dir.resolve()

    if not source.is_dir():
        raise NoiseError(f"--in-dir is not a directory: {in_dir}")
    for name, path in (("--in-dir", source), ("--out-dir", target)):
        if path != resolved_root and not path.is_relative_to(resolved_root):
            raise NoiseError(
                f"{name} resolves outside {root}: {path}. The pass reads and writes generated "
                "trees only -- the fragment libraries and the manifest are not its business"
            )
    if source == target:
        raise NoiseError(f"--out-dir is --in-dir ({target}); the pass never noises a tree in place")
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise NoiseError(
            f"--out-dir {target} and --in-dir {source} are nested; the output tree must be a "
            "sibling, or a run would read files it has already written"
        )
    if target.exists() and any(target.iterdir()) and not force:
        raise NoiseError(f"--out-dir is not empty: {target}. Pass --force to write into it anyway")


def check_tree(paths: Sequence[Path], sidecars: Sequence[Mapping[str, object]]) -> None:
    """Refuse an input tree that cannot be noised honestly.

    Three checks, all of which fail silently otherwise. A signal with no frozen
    lexicon is the dangerous one: the pass runs, the output looks fine, and the
    label noise is invisible in exactly the way section 2 exists to prevent. A
    tree already carrying a ``noise`` block would be damaged twice, compounding
    in a way no rate describes. And a tree whose files disagree on the fold
    configuration was half-regenerated, which presents at training time as a
    score nobody can explain.
    """
    if not paths:
        raise NoiseError("no *.jsonl files found under --in-dir")

    for path, stats in zip(paths, sidecars, strict=True):
        if "noise" in stats:
            raise NoiseError(
                f"{sidecar_path(path)} already carries a 'noise' block; noising a noisy tree "
                "compounds the damage in a way no rate describes"
            )
        signal = stats.get("signal")
        if not isinstance(signal, str) or not signal:
            raise NoiseError(f"{sidecar_path(path)} records no 'signal'")
        # Raises NoiseError naming the signal when the lexicon is missing or
        # empty. Keyed on "a non-empty lexicon exists" rather than hard-coded
        # to fever_present, so the seven signals come nearly free; it comes out
        # when 12.5 moves the lexicon into the manifest.
        try:
            noise_lexicon(signal)
        except NoiseError as error:
            raise NoiseError(f"{sidecar_path(path)}: {error}") from None

    for field_name in TREE_AGREEMENT_FIELDS:
        values = {json.dumps(stats.get(field_name), sort_keys=True) for stats in sidecars}
        if len(values) > 1:
            raise NoiseError(
                f"the sidecars under --in-dir disagree on {field_name!r} "
                f"({', '.join(sorted(values))}); this tree was half-regenerated, and noising it "
                "would hide that until training time"
            )


def noise_file(
    in_path: Path,
    out_path: Path,
    *,
    rate: float,
    seed: int,
    clean_share: float,
    freeze_mode: str = DEFAULT_FREEZE_MODE,
    word_weights: Mapping[str, float] | None = None,
    text_weights: Mapping[str, float] | None = None,
    stats: Mapping[str, object] | None = None,
) -> NoiseTally:
    """Damage one split's JSONL and write it, with its sidecar, to ``out_path``.

    ``example_id``, ``split``, ``labels`` and ``meta`` are copied through
    untouched: only ``text`` is edited, and the record's key order is
    :data:`RECORD_KEYS` so a diff against the clean tree shows exactly that.
    Each example draws its own RNG from its id rather than its position (DD3),
    then draws the clean-share coin before anything else (DD5).
    """
    stats = read_sidecar(in_path) if stats is None else stats
    signal = stats["signal"]
    word_weights = dict(WORD_OPERATION_WEIGHTS if word_weights is None else word_weights)
    text_weights = dict(TEXT_OPERATION_WEIGHTS if text_weights is None else text_weights)

    tally = NoiseTally()
    rows: list[tuple[str, str, str, str]] = []
    records: list[dict] = []
    with in_path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise NoiseError(f"{in_path} line {number} is not valid JSON: {error}") from error
            records.append(record)

    for record in records:
        example_id = record["example_id"]
        rng = example_rng(seed, example_id)
        # First draw of the example, before the text is even looked at, so the
        # clean share cannot depend on anything about the example (DD5).
        was_clean = rng.random() < clean_share
        if was_clean:
            result = DamageResult(
                text=record["text"],
                operations=Counter(),
                words=count_words(record["text"]),
                selected=0,
                edited=0,
                rejected=0,
            )
        else:
            result = damage_example(
                record["text"],
                rng,
                rate=rate,
                signal=signal,
                freeze_mode=freeze_mode,
                word_weights=word_weights,
                text_weights=text_weights,
            )
        record["text"] = result.text
        meta = record.get("meta", {})
        label = label_name(record.get("labels", {}).get(signal))
        label_mode = meta.get("label_mode", "unknown")
        tally.add(result, label=label, label_mode=label_mode, was_clean=was_clean)
        rows.append((result.text, label, label_mode, str(len(meta.get("fragment_ids", [])))))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            ordered = {key: record[key] for key in RECORD_KEYS if key in record}
            ordered.update({key: value for key, value in record.items() if key not in ordered})
            handle.write(json.dumps(ordered, ensure_ascii=False) + "\n")

    output_stats = build_noise_stats(
        stats,
        tally=tally,
        texts=rows,
        source_dir=str(in_path.parent),
        seed=seed,
        rate=rate,
        clean_share=clean_share,
        freeze_mode=freeze_mode,
        word_weights=word_weights,
        text_weights=text_weights,
    )
    with sidecar_path(out_path).open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(output_stats, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    return tally


def noise_tree(
    in_dir: Path,
    out_dir: Path,
    *,
    rate: float,
    seed: int = 42,
    clean_share: float = DEFAULT_CLEAN_SHARE,
    freeze_mode: str = DEFAULT_FREEZE_MODE,
    word_weights: Mapping[str, float] | None = None,
    text_weights: Mapping[str, float] | None = None,
    force: bool = False,
    root: Path | None = None,
) -> NoiseTally:
    """Damage a whole fold tree, filenames and all, into ``out_dir``.

    Whole tree in, whole tree out (DD2). ``dataset.FOLD_FILENAME`` is how
    ``scripts/encoder_training/`` finds a fold at all, so a noisy file named
    ``...train.noisy.jsonl`` would simply be invisible to it; every file keeps
    its name, and anything that is neither a dataset nor a sidecar is copied
    through byte-for-byte so the output tree is a drop-in ``--data-dir``.
    """
    check_directories(in_dir, out_dir, force=force, root=root)
    paths = sorted(in_dir.rglob("*.jsonl"))
    sidecars = [read_sidecar(path) for path in paths]
    check_tree(paths, sidecars)

    known = {path for path in paths} | {sidecar_path(path) for path in paths}
    total = NoiseTally()
    for path, stats in zip(paths, sidecars, strict=True):
        target = out_dir / path.relative_to(in_dir)
        total.merge(
            noise_file(
                path,
                target,
                rate=rate,
                seed=seed,
                clean_share=clean_share,
                freeze_mode=freeze_mode,
                word_weights=word_weights,
                text_weights=text_weights,
                stats=stats,
            )
        )

    for path in sorted(in_dir.rglob("*")):
        if not path.is_file() or path in known:
            continue
        target = out_dir / path.relative_to(in_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return total


def _rate(raw: str) -> float:
    value = float(raw)
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(f"must be in (0, 1]: {raw}")
    return value


def _share(raw: str) -> float:
    value = float(raw)
    if not 0 <= value < 1:
        raise argparse.ArgumentTypeError(f"must be in [0, 1): {raw}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.synthetic_data.noise",
        description="Write a damaged copy of a generated fold tree, ids and filenames intact.",
    )
    parser.add_argument("--in-dir", type=Path, required=True, help="a generated fold tree")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="where the damaged copy goes; must be a sibling of --in-dir, never inside it",
    )
    parser.add_argument(
        "--rate",
        type=_rate,
        required=True,
        help="probability that any one word is selected for damage, Bernoulli per word rather "
        "than per example (DD4). Required rather than defaulted: there is no rate that is "
        "obviously right, and the sweep is the point",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--clean-share",
        type=_share,
        default=DEFAULT_CLEAN_SHARE,
        help="share of examples left completely undamaged. Real submissions run from immaculate "
        "to unreadable; a dataset where every example carries the same error density is its "
        "own kind of unrealistic (DD5)",
    )
    parser.add_argument(
        "--freeze-signal-vocabulary",
        choices=list(FREEZE_MODES),
        default=DEFAULT_FREEZE_MODE,
        help="how much of the signal's own vocabulary joins the frozen set. 'short' freezes "
        f"words of {SHORT_WORD_MAX_LENGTH} characters or fewer, where one edit is "
        "proportionally enormous and the flip risk lives; 'all' freezes the lot, which is "
        "12.6 as literally written and leaves the experiment unable to see a misspelt "
        "'temperature'",
    )
    parser.add_argument(
        "--operation-weights",
        default=None,
        help="'name=weight,...'. Word-operation weights are normalised rather than required to "
        "sum to one; whole-text weights are multipliers on their own draw and are taken "
        "verbatim. Naming any operation of a kind replaces that whole table",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write into a non-empty --out-dir",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        word_weights, text_weights = parse_operation_weights(args.operation_weights)
        tally = noise_tree(
            args.in_dir,
            args.out_dir,
            rate=args.rate,
            seed=args.seed,
            clean_share=args.clean_share,
            freeze_mode=args.freeze_signal_vocabulary,
            word_weights=word_weights,
            text_weights=text_weights,
            force=args.force,
        )
    except NoiseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    # The three numbers worth seeing without opening a sidecar: what the rate
    # actually came out at, whether it came out the same for every label, and
    # how much of the gap between requested and realised the frozen lexicon
    # accounts for.
    print(
        f"wrote {sum(tally.examples.values())} examples to {args.out_dir} "
        f"(edits/100 words={tally.edits_per_hundred_words}, "
        f"largest by-label gap={tally.largest_by_label_gap}, "
        f"words left alone after rejection={tally.rejected})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
