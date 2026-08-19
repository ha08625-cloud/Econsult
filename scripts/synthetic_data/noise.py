"""Character-level damage for finished synthetic datasets.

The fragment libraries were typed by authors who were concentrating. Real
submissions are typed into a phone at eleven at night. This module is the pure
text-to-text half of the pass that closes that gap: the operations, the frozen
lexicon, the per-example RNG and :func:`damage_text`. It reads no files, knows
nothing about folds or sidecars, and imports nothing from the generator
(``recombine``, ``manifest``) -- that is the whole point of doing this as
post-processing rather than as a generator flag (``arch_training.md`` 12.6, DD1).

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

import hashlib
import random
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache

from .lint import SIGNAL_LEXICONS


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
    """Damage one example. Returns the text and a tally of realised operations.

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
    for index, piece in enumerate(pieces):
        if not piece or piece.isspace():
            continue
        prefix, word, suffix = split_token(piece)
        if not word:
            continue
        words += 1
        if rng.random() >= rate:
            continue
        damaged, operation = damage_word(word, rng, lexicon, weights=word_weights)
        if operation is None:
            continue
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
    return result, realised
