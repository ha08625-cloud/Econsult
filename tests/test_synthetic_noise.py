"""Unit tests for the character-level noise pass.

Pure unit tests on fixed strings -- no manifest, no ruleset, no fold tree, no
database -- so there is no ``pytestmark``. That the pass is testable this way is
the point of it being post-processing rather than a generator flag
(``arch_training.md`` 12.6, DD1). The directory-pass tests at the bottom do
touch the filesystem, but only a tmp tree they build by hand.

Most of these are volume tests rather than single-draw assertions. The property
being defended is "this can never happen", and the only honest way to check a
never against a random process is to run it a few thousand times.
"""

import json
import re
import string
from collections import Counter

import pytest

from scripts.encoder_training import dataset
from scripts.synthetic_data import noise
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


# ---------------------------------------------------------------------------
# The directory pass
#
# These do touch the filesystem, but only a tmp tree: still no manifest, no
# ruleset and no database. The fixtures below build a fold tree by hand rather
# than running the generator, because coupling this suite to the generator is
# the one thing DD1 exists to prevent.
# ---------------------------------------------------------------------------

SPLITS = ("train", "val", "test")

#: One word pool for every label. The rate-by-label test rests on this: if the
#: three classes are written from the same words, any difference in realised
#: edit density is the pass's doing rather than the vocabulary's.
WORD_POOL = (
    "woke",
    "sweating",
    "again",
    "kitchen",
    "morning",
    "bins",
    "collected",
    "walking",
    "upstairs",
    "shivering",
    "temperature",
    "burning",
    "rough",
    "curtains",
    "neighbour",
    "parcel",
)

#: Which fragment each label mode holds, and whether it is decisive. Mirrors
#: the generator's invariant, which ``dataset._decisive_fragment`` re-checks:
#: exactly one decisive fragment, except for a structural null, which has none.
MODE_FRAGMENTS = {
    "true": ("pos", "fill"),
    "false": ("neg", "fill"),
    "null_ambiguous": ("amb", "fill"),
    "null_structural": ("fill", "other"),
}

MODE_LABELS = {
    "true": True,
    "false": False,
    "null_ambiguous": None,
    "null_structural": None,
}


def fragment_block(split):
    """Provenance for one split, with fragment ids and clusters unique to it.

    ``load_fold`` asserts that no fragment and no cluster straddles a split
    boundary, so the fixture has to respect that or the loadability test proves
    only that the fixture is wrong.
    """
    entries = {
        "pos": ("fever", "positive", SIGNAL),
        "neg": ("fever", "negative", SIGNAL),
        "amb": ("fever_adjacent", "ambiguous", SIGNAL),
        "fill": ("bins", "filler", None),
        "other": ("weather", "filler", None),
    }
    return {
        f"{split}-{name}": {
            "library": library,
            "cluster_key": f"{split}-{name}-cluster",
            "fragment_type": fragment_type,
            "split": split,
            "signal_key": signal_key,
            "subclass": None,
        }
        for name, (library, fragment_type, signal_key) in entries.items()
    }


def example_text(rng, words=12):
    return " ".join(rng.choice(WORD_POOL) for _ in range(words)).capitalize() + "."


def write_split(
    directory,
    *,
    split,
    count=12,
    signal=SIGNAL,
    fold_index=0,
    folds=5,
    split_salt="0",
    seed=1,
    stats_overrides=None,
    with_sidecar=True,
):
    """Write one split's JSONL and sidecar into ``directory``, and return its path."""
    import random as _random

    rng = _random.Random(f"{split}|{seed}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{signal}.fold{fold_index}.{split}.jsonl"

    modes = list(MODE_FRAGMENTS)
    records = []
    for index in range(count):
        mode = modes[index % len(modes)]
        fragment_ids = [f"{split}-{name}" for name in MODE_FRAGMENTS[mode]]
        records.append(
            {
                "example_id": f"{signal}-{split}-{index:05d}",
                "split": split,
                "text": example_text(rng),
                "labels": {signal: MODE_LABELS[mode]},
                "meta": {
                    "label_mode": mode,
                    "filler_only": mode == "null_structural",
                    "fragment_ids": fragment_ids,
                    "fragment_subclasses": [None, None],
                    "seed": seed,
                    "generator_version": "7",
                },
            }
        )
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    if with_sidecar:
        stats = {
            "generator_version": "7",
            "seed": seed,
            "signal": signal,
            "split": split,
            "folds": folds,
            "fold_index": fold_index,
            "split_salt": split_salt,
            "fragments": fragment_block(split),
            "requested": {"count": count},
            "realised": {"count": len(records)},
            "token_counts": {
                "by_label": {label: {"count": 0} for label in ("true", "false", "null")},
                "by_label_mode": {mode: {"count": 0} for mode in MODE_FRAGMENTS},
                "by_fragment_count": {"2": {"count": len(records)}},
            },
        }
        stats.update(stats_overrides or {})
        sidecar = noise.sidecar_path(path)
        sidecar.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return path


def write_tree(directory, *, splits=SPLITS, **kwargs):
    """A whole fold's three splits, ready for ``dataset.load_fold``."""
    return [write_split(directory, split=split, **kwargs) for split in splits]


def read_records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def tree(tmp_path):
    """A clean input tree, and the root the guards are checked against."""
    source = tmp_path / "clean"
    write_tree(source)
    return source


def run_tree(source, target, **kwargs):
    kwargs.setdefault("rate", 0.2)
    kwargs.setdefault("root", source.parent)
    return noise.noise_tree(source, target, **kwargs)


# ---------------------------------------------------------------------------
# Whole tree in, whole tree out (DD2)
# ---------------------------------------------------------------------------


def test_the_output_tree_keeps_every_filename_and_every_field_but_text(tree, tmp_path):
    target = tmp_path / "noisy"
    run_tree(tree, target)

    assert sorted(path.name for path in target.iterdir()) == sorted(
        path.name for path in tree.iterdir()
    )
    changed = 0
    total = 0
    for source_path in sorted(tree.glob("*.jsonl")):
        before = read_records(source_path)
        after = read_records(target / source_path.name)
        assert len(before) == len(after)
        for original, damaged in zip(before, after, strict=True):
            for key in ("example_id", "split", "labels", "meta"):
                assert original[key] == damaged[key]
            assert list(damaged) == list(original), "key order must match to_record"
            total += 1
            changed += original["text"] != damaged["text"]
    # Roughly 1 - clean_share of examples carry damage. Loose bounds: this is a
    # smoke test that the pass fired, not a check on the rate.
    assert 0.4 * total < changed < total


def test_files_that_are_neither_dataset_nor_sidecar_are_copied_through(tree, tmp_path):
    (tree / "README.txt").write_text("how this tree was generated\n", encoding="utf-8")
    target = tmp_path / "noisy"
    run_tree(tree, target)
    assert (target / "README.txt").read_text(encoding="utf-8") == "how this tree was generated\n"


def test_the_noisy_tree_loads_through_load_fold(tree, tmp_path):
    """The integration check: no flags changed, no filenames changed."""
    target = tmp_path / "noisy"
    run_tree(tree, target)
    paths = {split: target / f"{SIGNAL}.fold0.{split}.jsonl" for split in SPLITS}
    fold = dataset.load_fold(paths["train"], paths["val"], paths["test"])
    assert fold.fold_index == 0
    assert fold.train.stats["noise"]["requested"]["rate"] == 0.2
    # And the clean tree still loads, or the comparison proves nothing.
    clean_paths = {split: tree / f"{SIGNAL}.fold0.{split}.jsonl" for split in SPLITS}
    dataset.load_fold(clean_paths["train"], clean_paths["val"], clean_paths["test"])


# ---------------------------------------------------------------------------
# Reproducibility (DD3)
# ---------------------------------------------------------------------------


def test_two_runs_write_byte_identical_files(tree, tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    run_tree(tree, first)
    run_tree(tree, second)
    for path in sorted(first.iterdir()):
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name


def test_noising_a_prefix_gives_a_prefix_of_the_noised_whole(tmp_path):
    """Keying the RNG on the id rather than the line number is what buys this."""
    long_dir = tmp_path / "long"
    write_split(long_dir, split="train", count=200)
    short_dir = tmp_path / "short"
    write_split(short_dir, split="train", count=200)
    short_path = short_dir / f"{SIGNAL}.fold0.train.jsonl"
    lines = short_path.read_text(encoding="utf-8").splitlines()[:100]
    short_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    long_out, short_out = tmp_path / "long-noisy", tmp_path / "short-noisy"
    run_tree(long_dir, long_out)
    run_tree(short_dir, short_out)
    long_records = read_records(long_out / f"{SIGNAL}.fold0.train.jsonl")
    short_records = read_records(short_out / f"{SIGNAL}.fold0.train.jsonl")
    assert len(short_records) == 100
    assert long_records[:100] == short_records


# ---------------------------------------------------------------------------
# The sidecar (DD7, DD8, DD9)
# ---------------------------------------------------------------------------


def test_the_sidecar_keeps_everything_the_fragments_describe(tree, tmp_path):
    target = tmp_path / "noisy"
    run_tree(tree, target)
    for source_path in sorted(tree.glob("*.jsonl")):
        before = json.loads(noise.sidecar_path(source_path).read_text(encoding="utf-8"))
        after = json.loads(
            noise.sidecar_path(target / source_path.name).read_text(encoding="utf-8")
        )
        # DD7: nothing _check_fold_agreement reads may move.
        for key in ("generator_version", "signal", "folds", "fold_index", "split_salt", "split"):
            assert after[key] == before[key]
        # DD8: the fragments were not edited, so the blocks describing them
        # are passed through; token_counts describes the text and is not.
        assert after["fragments"] == before["fragments"]
        assert after["requested"] == before["requested"]
        assert after["realised"] == before["realised"]
        assert after["token_counts"] != before["token_counts"]
        assert set(after["token_counts"]) == set(before["token_counts"])
        assert after["token_counts"]["by_label"]["true"]["count"] > 0


def test_the_noise_block_is_the_marker_that_a_tree_is_noisy(tree, tmp_path):
    target = tmp_path / "noisy"
    run_tree(tree, target, rate=0.15, seed=7, clean_share=0.2)
    for source_path in sorted(tree.glob("*.jsonl")):
        assert "noise" not in json.loads(
            noise.sidecar_path(source_path).read_text(encoding="utf-8")
        )
        block = json.loads(
            noise.sidecar_path(target / source_path.name).read_text(encoding="utf-8")
        )["noise"]
        assert block["source_dir"] == str(tree)
        assert block["seed"] == 7
        assert block["requested"] == {
            "rate": 0.15,
            "clean_share": 0.2,
            "freeze_signal_vocabulary": "short",
            "operation_weights": {
                "word": dict(WORD_OPERATION_WEIGHTS),
                "text": dict(TEXT_OPERATION_WEIGHTS),
            },
        }
        realised = block["realised"]
        assert set(realised["edits_per_hundred_words"]["by_label"]) == {"true", "false", "null"}
        assert realised["operations"]
        words = realised["words"]
        assert words["total"] > 0
        assert words["selected"] == words["edited"] + words["rejected_then_left_alone"]


def test_the_realised_clean_share_lands_near_the_requested_one(tmp_path):
    source = tmp_path / "clean"
    write_split(source, split="train", count=2000)
    target = tmp_path / "noisy"
    tally = run_tree(source, target, clean_share=0.25)
    assert tally.overall_clean_share == pytest.approx(0.25, abs=0.03)
    for label, share in tally.clean_share().items():
        assert share == pytest.approx(0.25, abs=0.05), label


def test_edit_density_does_not_vary_by_label(tmp_path):
    """The test that would catch a future change making rejection label-aware.

    Every label's text is drawn from one word pool, so the three classes differ
    only in the label written beside them -- which nothing in the pass can see.
    """
    source = tmp_path / "clean"
    write_split(source, split="train", count=2000)
    target = tmp_path / "noisy"
    tally = run_tree(source, target, rate=0.2)

    rates = tally.by_label_rates()
    assert all(rate > 0 for rate in rates.values()), rates
    spread = max(rates.values()) - min(rates.values())
    assert spread / (sum(rates.values()) / len(rates)) < 0.10, rates
    assert tally.largest_by_label_gap == pytest.approx(spread, abs=1e-4)


# ---------------------------------------------------------------------------
# The guards. Every one of these fails silently if it is not a startup error.
# ---------------------------------------------------------------------------


def test_an_output_dir_that_is_the_input_dir_is_refused(tree):
    with pytest.raises(noise.NoiseError, match="never noises a tree in place"):
        run_tree(tree, tree)


@pytest.mark.parametrize("nested", ["child", "parent"])
def test_nested_input_and_output_directories_are_refused(tree, tmp_path, nested):
    target = tree / "inside" if nested == "child" else tree.parent
    with pytest.raises(noise.NoiseError, match="nested"):
        run_tree(tree, target)


def test_a_directory_outside_the_generated_root_is_refused(tree, tmp_path):
    outside = tmp_path / "elsewhere" / "noisy"
    with pytest.raises(noise.NoiseError, match="resolves outside"):
        # The real root, which no tmp path can be inside.
        noise.noise_tree(tree, outside, rate=0.2)


def test_a_non_empty_output_dir_needs_force(tree, tmp_path):
    target = tmp_path / "noisy"
    target.mkdir()
    (target / "leftover.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(noise.NoiseError, match="is not empty"):
        run_tree(tree, target)
    run_tree(tree, target, force=True)
    assert (target / f"{SIGNAL}.fold0.train.jsonl").is_file()


def test_a_dataset_with_no_sidecar_is_refused(tmp_path):
    source = tmp_path / "clean"
    write_tree(source)
    orphan = write_split(source, split="train", fold_index=1, with_sidecar=False)
    with pytest.raises(noise.NoiseError, match=re.escape(str(orphan))):
        run_tree(source, tmp_path / "noisy")


def test_a_signal_with_no_frozen_lexicon_is_refused(tmp_path):
    source = tmp_path / "clean"
    write_tree(source, signal="not_a_signal")
    with pytest.raises(noise.NoiseError, match="no frozen lexicon"):
        run_tree(source, tmp_path / "noisy")


def test_an_already_noisy_tree_is_refused(tree, tmp_path):
    first = tmp_path / "noisy"
    run_tree(tree, first)
    with pytest.raises(noise.NoiseError, match="already carries a 'noise' block"):
        run_tree(first, tmp_path / "noisier")


def test_a_half_regenerated_tree_is_refused(tmp_path):
    source = tmp_path / "clean"
    write_split(source, split="train")
    write_split(source, split="val")
    write_split(source, split="test", stats_overrides={"split_salt": "9"})
    with pytest.raises(noise.NoiseError, match="disagree on 'split_salt'"):
        run_tree(source, tmp_path / "noisy")


def test_an_empty_input_tree_is_refused(tmp_path):
    source = tmp_path / "clean"
    source.mkdir()
    with pytest.raises(noise.NoiseError, match="no \\*.jsonl files"):
        run_tree(source, tmp_path / "noisy")


def test_a_missing_input_dir_is_refused(tmp_path):
    with pytest.raises(noise.NoiseError, match="not a directory"):
        run_tree(tmp_path / "nowhere", tmp_path / "noisy")


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


def test_operation_weights_default_to_the_module_tables():
    word, text = noise.parse_operation_weights(None)
    assert word == WORD_OPERATION_WEIGHTS
    assert text == TEXT_OPERATION_WEIGHTS


def test_operation_weights_normalise_word_weights_and_replace_the_table():
    word, text = noise.parse_operation_weights("drop_letter=3,double_letter=1")
    assert word == {"drop_letter": 0.75, "double_letter": 0.25}
    # Naming no whole-text operation leaves that table alone.
    assert text == TEXT_OPERATION_WEIGHTS


def test_whole_text_weights_are_taken_verbatim_because_they_are_not_shares():
    word, text = noise.parse_operation_weights("drop_space=2.0")
    assert text == {"drop_space": 2.0}
    assert word == WORD_OPERATION_WEIGHTS


@pytest.mark.parametrize(
    ("argument", "message"),
    [
        ("drop_letter", "malformed"),
        ("nonsense=1", "unknown operation"),
        ("drop_letter=1,drop_letter=2", "appears twice"),
        ("drop_letter=lots", "not a number"),
        ("drop_letter=-1", "negative"),
        ("drop_letter=0", "every word operation at zero"),
    ],
)
def test_bad_operation_weights_are_refused(argument, message):
    with pytest.raises(noise.NoiseError, match=message):
        noise.parse_operation_weights(argument)


def test_main_writes_a_tree_and_reports_the_three_numbers(tree, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(noise, "GENERATED_ROOT", tree.parent)
    target = tmp_path / "noisy"
    code = noise.main(
        ["--in-dir", str(tree), "--out-dir", str(target), "--rate", "0.2", "--seed", "3"]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "edits/100 words=" in printed
    assert "largest by-label gap=" in printed
    assert "words left alone after rejection=" in printed
    assert (target / f"{SIGNAL}.fold0.train.jsonl").is_file()


def test_main_reports_a_refusal_rather_than_a_traceback(tree, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(noise, "GENERATED_ROOT", tree.parent)
    code = noise.main(["--in-dir", str(tree), "--out-dir", str(tree), "--rate", "0.2"])
    assert code == 2
    assert "error: " in capsys.readouterr().err


@pytest.mark.parametrize("rate", ["0", "1.5", "-0.1"])
def test_a_rate_outside_the_unit_interval_is_refused_by_argparse(rate):
    with pytest.raises(SystemExit):
        noise.build_parser().parse_args(["--in-dir", "a", "--out-dir", "b", "--rate", rate])


def test_freeze_all_is_one_flag_away(tmp_path):
    """The conservative variant of 12.6, which the rate sweep argues against.

    The word pool carries "temperature" and "burning", both damageable under
    ``short``. Under ``all`` every occurrence must survive every split of a
    whole tree at rate 1.0 and no clean share -- the freeze mode is the only
    thing standing between them and an edit.
    """
    source = tmp_path / "clean"
    write_split(source, split="train", count=300)
    target = tmp_path / "noisy"
    run_tree(source, target, freeze_mode="all", rate=1.0, clean_share=0.0)

    path = target / f"{SIGNAL}.fold0.train.jsonl"
    sidecar = json.loads(noise.sidecar_path(path).read_text(encoding="utf-8"))
    assert sidecar["noise"]["requested"]["freeze_signal_vocabulary"] == "all"

    def tally(records):
        # Folded, so that dropping the terminal full stop off "temperature."
        # does not read as a new occurrence of "temperature".
        return Counter(
            fold_token(token.word) for record in records for token in split_words(record["text"])
        )

    before = tally(read_records(source / path.name))
    after = tally(read_records(path))
    assert before["temperature"] > 0 and before["burning"] > 0
    for word in ("temperature", "burning"):
        assert after[word] == before[word], word
