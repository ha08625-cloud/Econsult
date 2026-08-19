"""Unit tests for the character-level noise pass.

Pure unit tests on fixed strings -- no manifest, no ruleset, no fold tree, no
database -- so there is no ``pytestmark``. That the pass is testable this way is
the point of it being post-processing rather than a generator flag
(``arch_training.md`` 12.6, DD1).

Most of these are volume tests rather than single-draw assertions. The property
being defended is "this can never happen", and the only honest way to check a
never against a random process is to run it a few thousand times.
"""

import string
from collections import Counter

import pytest

from scripts.synthetic_data.noise import (
    CHARACTER_OPERATIONS,
    DEFAULT_FREEZE_MODE,
    FREEZE_MODES,
    KEYBOARD_NEIGHBOURS,
    MAX_REDRAWS,
    SHAPE_PRESERVING_OPERATIONS,
    TEXT_OPERATION_WEIGHTS,
    WORD_OPERATION_WEIGHTS,
    NoiseError,
    count_words,
    damage_text,
    damage_word,
    drop_apostrophe,
    drop_space,
    drop_terminal_punctuation,
    example_rng,
    fold_token,
    frozen_tokens,
    keyboard_neighbour,
    lowercase,
    lowercase_all,
    noise_lexicon,
    signal_vocabulary,
    split_words,
    transpose_adjacent,
)

SIGNAL = "fever_present"

#: Enough draws that a one-in-a-thousand hole in a "never" would show.
VOLUME = 10_000

#: Fewer draws where each one walks a whole sentence rather than one word.
SENTENCE_VOLUME = 2_000


def damaged_words(text, *, rate=1.0, freeze_mode=DEFAULT_FREEZE_MODE, draws=VOLUME, **kwargs):
    """Yield the folded output tokens of ``draws`` independent damage runs."""
    for index in range(draws):
        output, _ = damage_text(
            text,
            example_rng(7, f"example-{index}"),
            rate=rate,
            signal=SIGNAL,
            freeze_mode=freeze_mode,
            **kwargs,
        )
        yield output


# ---------------------------------------------------------------------------
# The lexicon
# ---------------------------------------------------------------------------


def test_fever_vocabulary_splits_by_length_under_short():
    lexicon = noise_lexicon(SIGNAL, "short")
    # The words a single edit could invert.
    for word in ("hot", "warm", "fever", "no", "not", "my", "his", "had", "was"):
        assert word in lexicon.frozen
    # The words the exercise exists to damage.
    assert "temperature" in lexicon.damageable
    assert "temperature" not in lexicon.frozen
    assert not (lexicon.frozen & lexicon.damageable)


def test_freeze_all_leaves_nothing_damageable():
    lexicon = noise_lexicon(SIGNAL, "all")
    assert lexicon.damageable == frozenset()
    assert signal_vocabulary(SIGNAL) <= lexicon.frozen
    assert "temperature" in lexicon.frozen


def test_structural_words_are_frozen_for_every_signal():
    for signal in ("fever_present", "dysuria_present", "haematuria_present"):
        frozen = frozen_tokens(signal)
        assert {"no", "not", "i", "my", "had", "maybe"} <= frozen


def test_unknown_signal_is_refused_rather_than_under_protected():
    with pytest.raises(NoiseError, match="no frozen lexicon"):
        frozen_tokens("not_a_signal")
    with pytest.raises(NoiseError, match="unknown freeze mode"):
        frozen_tokens(SIGNAL, "some_other_mode")


def test_lookup_is_case_and_punctuation_insensitive():
    lexicon = noise_lexicon(SIGNAL)
    for spelling in ("Hot", "hot,", "(hot)", "HOT.", "hot"):
        assert lexicon.is_frozen(spelling)
    # Curly apostrophes fold to straight, so only one spelling is listed.
    assert lexicon.is_frozen("don’t")
    assert lexicon.is_frozen("don't")
    assert fold_token("Don’t.") == "don't"


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------


def test_split_words_reassembles_and_counts():
    text = "I've had a temperature -- since Monday!"
    tokens = list(split_words(text))
    assert " ".join(token.text for token in tokens) == text
    assert [token.word for token in tokens if token.is_word] == [
        "I've",
        "had",
        "a",
        "temperature",
        "since",
        "Monday",
    ]
    # "--" is a chunk with no word, so it is not part of the rate's denominator.
    assert count_words(text) == 6


def test_rate_zero_is_a_no_op():
    text = "I've had a temperature since Monday and I feel really rough."
    for index in range(200):
        output, realised = damage_text(text, example_rng(3, str(index)), rate=0.0, signal=SIGNAL)
        assert output == text
        assert realised == Counter()


# ---------------------------------------------------------------------------
# Label safety: the whole risk of the ticket
# ---------------------------------------------------------------------------


def test_hot_and_not_are_never_produced_from_each_other():
    for output in damaged_words("I felt hot"):
        assert "not" not in {fold_token(token.word) for token in split_words(output)}
    for output in damaged_words("no temperature, I checked"):
        assert "hot" not in {fold_token(token.word) for token in split_words(output)}


@pytest.mark.parametrize("freeze_mode", FREEZE_MODES)
def test_no_frozen_token_is_ever_changed_by_a_character_operation(freeze_mode):
    text = "no fever but my son was really hot last night and I had a temperature"
    lexicon = noise_lexicon(SIGNAL, freeze_mode)
    original = [token.word for token in split_words(text)]
    edits = 0
    # Whole-text operations are off so the token alignment survives; drop_space
    # has its own test below.
    for output in damaged_words(
        text, freeze_mode=freeze_mode, draws=SENTENCE_VOLUME, text_weights={}
    ):
        damaged = [token.word for token in split_words(output)]
        assert len(damaged) == len(original)
        edits += sum(1 for before, after in zip(original, damaged, strict=True) if before != after)
        for before, after in zip(original, damaged, strict=True):
            if not lexicon.is_frozen(before):
                continue
            # Only the shape-preserving operations may have run, and neither
            # can change which word the token is.
            assert after.lower().replace("'", "") == before.lower().replace("'", "")
    # Not vacuous: the unfrozen words in the fixture were damaged.
    assert edits > 0


def test_a_character_operation_never_produces_a_frozen_token():
    lexicon = noise_lexicon(SIGNAL)
    rng = example_rng(11, "produce")
    produced = Counter()
    for word in ("hots", "nod", "nowt", "mya", "hat", "wasp", "temperature"):
        for _ in range(VOLUME // 10):
            damaged, operation = damage_word(word, rng, lexicon)
            if operation in CHARACTER_OPERATIONS:
                assert not lexicon.is_frozen(damaged)
                produced[operation] += 1
    # Not a vacuous pass: character operations did fire.
    assert sum(produced.values()) > 0


def test_a_character_operation_never_produces_a_different_signal_word():
    lexicon = noise_lexicon(SIGNAL, "short")
    rng = example_rng(13, "signal-swap")
    others = lexicon.damageable - {"burning"}
    for _ in range(VOLUME):
        damaged, operation = damage_word("burning", rng, lexicon)
        if operation in CHARACTER_OPERATIONS:
            assert fold_token(damaged) not in others


def test_drop_space_never_welds_a_frozen_token():
    text = "no fever the bins were collected late on friday morning"
    lexicon = noise_lexicon(SIGNAL)
    frozen = [token.word for token in split_words(text) if lexicon.is_frozen(token.word)]
    assert frozen, "the fixture must contain frozen tokens or this proves nothing"
    welds = 0
    for output in damaged_words(
        text,
        draws=SENTENCE_VOLUME,
        word_weights={},
        text_weights={"drop_space": 1.0},
    ):
        tokens = [token.word for token in split_words(output)]
        for word in frozen:
            assert word in tokens
        welds += len(text.split()) - len(tokens)
    # Not vacuous: spaces between unfrozen words were deleted.
    assert welds > 0


def test_drop_space_returns_none_when_every_gap_is_adjacent_to_a_frozen_token():
    lexicon = noise_lexicon(SIGNAL)
    rng = example_rng(17, "no-candidates")
    assert drop_space("I felt hot", rng, lexicon) is None


# ---------------------------------------------------------------------------
# The shape-preserving operations, which 12.6 as literally written would forbid
# ---------------------------------------------------------------------------


def test_apostrophe_and_casing_do_fire_on_frozen_tokens():
    lexicon = noise_lexicon(SIGNAL)
    rng = example_rng(19, "shape")
    assert lexicon.is_frozen("don't") and lexicon.is_frozen("I've")
    assert drop_apostrophe("don't", rng) == "dont"
    assert drop_apostrophe("I've", rng) == "Ive"
    assert lowercase("I've", rng) == "i've"
    assert lowercase("dont", rng) is None

    seen = Counter()
    for _ in range(VOLUME):
        for word in ("don't", "I've"):
            damaged, operation = damage_word(word, rng, lexicon)
            if operation is not None:
                assert operation in SHAPE_PRESERVING_OPERATIONS
                seen[damaged] += 1
    assert seen["dont"] > 0
    assert seen["Ive"] > 0
    assert seen["i've"] > 0


def test_terminal_punctuation_drops_one_character():
    rng = example_rng(23, "terminal")
    lexicon = noise_lexicon(SIGNAL)
    assert drop_terminal_punctuation("I felt hot.", rng, lexicon) == "I felt hot"
    assert drop_terminal_punctuation("Really?", rng, lexicon) == "Really"
    assert drop_terminal_punctuation("hot!!", rng, lexicon) == "hot!"
    assert drop_terminal_punctuation("I felt hot", rng, lexicon) is None


def test_lowercase_all_folds_the_example():
    rng = example_rng(29, "fold")
    lexicon = noise_lexicon(SIGNAL)
    assert lowercase_all("I Felt Hot", rng, lexicon) == "i felt hot"
    assert lowercase_all("i felt hot", rng, lexicon) is None


# ---------------------------------------------------------------------------
# Freeze mode
# ---------------------------------------------------------------------------


def test_temperature_is_damageable_under_short_and_frozen_under_all():
    text = "I had a temperature this evening"
    position = 3

    def word_at_position(freeze_mode):
        # Whole-text operations off, so position 3 is still "temperature".
        for output in damaged_words(
            text, freeze_mode=freeze_mode, draws=SENTENCE_VOLUME, text_weights={}
        ):
            words = [token.word for token in split_words(output)]
            assert len(words) == len(text.split())
            yield words[position]

    variants = Counter(word_at_position("short"))
    assert variants["temperature"] < SENTENCE_VOLUME, "temperature was never damaged"
    for variant in variants:
        # One character operation, so at most one character of difference.
        assert abs(len(variant) - len("temperature")) <= 1

    assert set(word_at_position("all")) == {"temperature"}


@pytest.mark.parametrize("freeze_mode", FREEZE_MODES)
def test_hot_is_never_edited_under_either_freeze_mode(freeze_mode):
    for output in damaged_words(
        "I felt hot", freeze_mode=freeze_mode, draws=SENTENCE_VOLUME, text_weights={}
    ):
        assert "hot" in [token.word for token in split_words(output)]


# ---------------------------------------------------------------------------
# Reproducibility (DD3)
# ---------------------------------------------------------------------------


def test_same_seed_and_text_give_the_same_output():
    text = "I've had a temperature since Monday, felt really rough all week."
    first, first_ops = damage_text(text, example_rng(42, "ex-1"), rate=0.2, signal=SIGNAL)
    second, second_ops = damage_text(text, example_rng(42, "ex-1"), rate=0.2, signal=SIGNAL)
    assert first == second
    assert first_ops == second_ops
    # A different id is a different draw, or the keying is not doing anything.
    others = {
        damage_text(text, example_rng(42, f"ex-{index}"), rate=0.2, signal=SIGNAL)[0]
        for index in range(50)
    }
    assert len(others) > 1


def test_example_rng_is_keyed_on_the_id_not_the_position():
    ids = [f"fever-{index:04d}" for index in range(20)]
    text = "woke up sweating again in the small hours"
    short_run = {
        example_id: damage_text(text, example_rng(5, example_id), rate=0.3, signal=SIGNAL)[0]
        for example_id in ids[:10]
    }
    long_run = {
        example_id: damage_text(text, example_rng(5, example_id), rate=0.3, signal=SIGNAL)[0]
        for example_id in ids
    }
    for example_id, output in short_run.items():
        assert long_run[example_id] == output


# ---------------------------------------------------------------------------
# The QWERTY map and the weights
# ---------------------------------------------------------------------------


def test_keyboard_map_covers_every_letter_and_is_symmetric():
    assert set(KEYBOARD_NEIGHBOURS) == set(string.ascii_lowercase)
    for letter, neighbours in KEYBOARD_NEIGHBOURS.items():
        assert len(set(neighbours)) >= 2, letter
        assert letter not in neighbours
        for neighbour in neighbours:
            assert letter in KEYBOARD_NEIGHBOURS[neighbour], f"{letter} -> {neighbour}"


def test_keyboard_neighbour_preserves_case_and_length():
    rng = example_rng(31, "keys")
    for _ in range(500):
        damaged = keyboard_neighbour("Temperature", rng)
        assert damaged is not None
        assert len(damaged) == len("Temperature")
        assert damaged[0].isupper()
        assert damaged != "Temperature"


def test_operations_return_none_when_they_cannot_apply():
    rng = example_rng(37, "none")
    assert drop_apostrophe("dont", rng) is None
    assert lowercase("dont", rng) is None
    assert transpose_adjacent("a", rng) is None
    assert transpose_adjacent("aa", rng) is None
    assert keyboard_neighbour("123", rng) is None


def test_default_weights_put_half_the_mass_on_shape_preserving_operations():
    total = sum(WORD_OPERATION_WEIGHTS.values())
    shape = sum(WORD_OPERATION_WEIGHTS[name] for name in SHAPE_PRESERVING_OPERATIONS)
    assert shape == pytest.approx(total / 2)
    assert set(WORD_OPERATION_WEIGHTS) == CHARACTER_OPERATIONS | SHAPE_PRESERVING_OPERATIONS
    assert set(TEXT_OPERATION_WEIGHTS) == {
        "drop_terminal_punctuation",
        "drop_space",
        "lowercase_all",
    }


def test_damage_word_gives_up_rather_than_looping():
    """A word every draw must reject comes back unchanged, not never."""
    lexicon = noise_lexicon(SIGNAL)
    rng = example_rng(41, "give-up")
    for _ in range(1000):
        # "hot" is frozen, so every character draw is rejected, and it has no
        # apostrophe and no capital, so both shape draws fail too.
        damaged, operation = damage_word("hot", rng, lexicon)
        assert (damaged, operation) == ("hot", None)
    assert MAX_REDRAWS == 3


def test_at_most_one_operation_per_word():
    lexicon = noise_lexicon(SIGNAL, "short")
    rng = example_rng(43, "single")
    for _ in range(VOLUME):
        damaged, operation = damage_word("temperature", rng, lexicon)
        if operation is None:
            assert damaged == "temperature"
            continue
        # One character operation changes the length by at most one.
        assert abs(len(damaged) - len("temperature")) <= 1
