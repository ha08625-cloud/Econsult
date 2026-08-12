"""Unit tests for Arm A: the embedding cache, the heads, the masked loss, artefacts.

Pure unit tests: no database, no GPU, no network, so there is no ``pytestmark``.

**What runs where.** ``torch`` and ``transformers`` live in
``requirements-ml.txt``, which CI's unit job deliberately does not install, so
the tests that need them skip themselves. The split is not arbitrary -- the
things that fail *silently* are all on the stdlib side and therefore always run:

* ``test_cache_key_changes_with_*`` -- a cache key that ignores an input which
  changes the embeddings serves stale vectors, and nothing warns. Every number
  in the report would look completely normal and mean nothing. This is the most
  load-bearing test in the file and it needs no ML at all.
* ``test_metadata_carries_every_required_field`` -- the sidecar is what makes a
  set of weights identifiable later. A field discovered missing six months on
  cannot be reconstructed.
* ``test_deterministic_env_is_set_before_torch_would_read_it`` -- torch reads
  ``CUBLAS_WORKSPACE_CONFIG`` when CUDA initialises, so setting it late is a
  silent no-op and the run simply is not reproducible.

The torch-gated ones cover the two pieces whose failure modes are quiet in a
different way: ``masked_cross_entropy`` on an all-masked batch (NaN, which
destroys every weight on the next step) and the mask-weighted mean pool (which
would otherwise make an embedding depend on the longest sentence in its batch).
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.encoder_training.dataset import (
    CLASS_FALSE,
    CLASS_NULL,
    CLASS_TRUE,
    MASKED_CLASS,
    load_fold,
    load_split,
    sidecar_path,
)
from scripts.encoder_training.decision import DecisionRule
from scripts.encoder_training.embed import (
    CACHE_FORMAT_VERSION,
    EmbeddingSpec,
    EmbedError,
    cache_key,
    cache_path,
    content_digest,
    load_or_build,
    split_cache_key,
)
from scripts.encoder_training.metrics import Prediction
from scripts.encoder_training.report import BootstrapConfig, FoldRun, build_report, render_markdown
from scripts.encoder_training.train import (
    ARM_A_NAME,
    CUBLAS_ENV_VALUE,
    CUBLAS_ENV_VAR,
    DEFAULT_BASE_MODEL,
    ProbeConfig,
    ProbeFoldResult,
    TrainError,
    build_metadata,
    ensure_deterministic_env,
    head_artefact,
    load_head_artefact,
    spec_from_metadata,
    write_artefacts,
)

FIXTURES = Path(__file__).parent / "fixtures" / "encoder_training"
TRAIN = FIXTURES / "mini.fold0.train.jsonl"
VAL = FIXTURES / "mini.fold0.val.jsonl"
TEST = FIXTURES / "mini.fold0.test.jsonl"

SIGNAL = "fever_present"

SPEC = EmbeddingSpec(
    base_model="emilyalsentzer/Bio_ClinicalBERT",
    revision="0123456789abcdef0123456789abcdef01234567",
    pooling="mean",
    max_seq_len=256,
)

KEY_ARGS = {
    "signal": SIGNAL,
    "fold_index": 0,
    "split": "train",
    "generator_version": 2,
    "dataset_seed": 42,
    "digest": "abcdef0123456789",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


@pytest.fixture
def torch_module():
    return pytest.importorskip("torch", reason="requirements-ml.txt is not installed")


@pytest.fixture
def transformers_module():
    return pytest.importorskip("transformers", reason="requirements-ml.txt is not installed")


class _StubEncoder:
    """A deterministic stand-in for :class:`PooledEncoder`.

    :func:`load_or_build` only ever asks an encoder for its ``spec`` and its
    ``embed``, which is what makes the cache testable without downloading 440MB
    of weights. ``calls`` counts forward passes, so a cache *hit* can be
    asserted by the encoder not having run rather than by the file merely
    existing.
    """

    def __init__(self, spec: EmbeddingSpec, *, width: int = 8) -> None:
        self.spec = spec
        self.width = width
        self.calls = 0

    def embed(self, texts, *, batch_size=64, progress=False):
        import torch

        self.calls += 1
        rows = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            rows.append([byte / 255.0 for byte in digest[: self.width]])
        return torch.tensor(rows, dtype=torch.float32)


class _SeparableEncoder(_StubEncoder):
    """Embeddings that are a one-hot of the truth, so a working probe must score 1.0.

    Not a realistic encoder and not meant to be. It isolates the training loop:
    if the loss, the optimiser step, the epoch selection and the softmax
    prediction path are all wired correctly, a linearly separable feature is
    learned perfectly, and any failure in that chain shows up here rather than as
    a slightly disappointing number on real data.
    """

    def __init__(self, spec: EmbeddingSpec, truths: dict[str, int]) -> None:
        super().__init__(spec, width=3)
        self.truths = truths

    def embed(self, texts, *, batch_size=64, progress=False):
        import torch

        self.calls += 1
        rows = []
        for text in texts:
            row = [0.0, 0.0, 0.0]
            row[self.truths[text]] = 1.0
            rows.append(row)
        return torch.tensor(rows, dtype=torch.float32)


def _prediction(example_id, truth, predicted, unit, **kwargs):
    return Prediction(example_id=example_id, truth=truth, predicted=predicted, unit=unit, **kwargs)


def _probe_result(fold_index=0):
    """A ProbeFoldResult built by hand, with no torch anywhere near it."""
    raw = [
        _prediction(
            "test-000000",
            CLASS_TRUE,
            CLASS_TRUE,
            "cluster-a",
            label_mode="true",
            library="fever_true",
            fragment_id="fever_true:11111111",
            scores=(0.1, 0.8, 0.1),
        ),
        _prediction(
            "test-000001",
            CLASS_NULL,
            CLASS_FALSE,
            "cluster-b",
            label_mode="null_ambiguous",
            library="fever_null_hedged",
            subclass="hedged",
            fragment_id="fever_null_hedged:33333333",
            scores=(0.6, 0.1, 0.3),
        ),
    ]
    rule = DecisionRule(
        margin=0.0,
        selected_on="val",
        argmax_null_to_true_rate=0.0,
        null_to_true_rate=0.0,
        macro_f1=0.5,
    )
    return ProbeFoldResult(
        fold_index=fold_index,
        fold_run=FoldRun.build(
            fold_index=fold_index,
            n_train=6,
            n_val=4,
            n_test=len(raw),
            rule=rule,
            raw=raw,
            ruled=raw,
        ),
        head_state={
            SIGNAL: {"weight": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], "bias": [0.0, 0.1, 0.2]}
        },
        n_parameters=2307,
        best_epoch=7,
        val_macro_f1_by_epoch=(0.2, 0.5, 0.5),
        val_summary={"n_examples": 4, "effective_n": 3, "accuracy": 0.75, "macro_f1": 0.5},
        cache={"train": {"path": "x", "hit": False}},
    )


def _metadata(results, **overrides):
    payload = {
        "signal": SIGNAL,
        "arm": ARM_A_NAME,
        "encoder_facts": {**SPEC.to_dict(), "tokeniser": {"lowercases_input": False}},
        "config": ProbeConfig(),
        "device": {"device": "cpu", "kernel_launch_ok": True},
        "dataset": {"dir": "data/synthetic/generated/folds", "folds": 5, "generator_version": 2},
        "ruleset": "data/uti1.json",
        "ruleset_hash": "0" * 64,
        "results": results,
    }
    payload.update(overrides)
    return build_metadata(**payload)


# --------------------------------------------------------------------------
# The cache key (DD14)
#
# The stale-cache failure is silent: plausible numbers, no warning, no error.
# Every input that changes what an embedding *is* has to change the key, and
# these tests are the only thing that says so.
# --------------------------------------------------------------------------


def test_cache_key_is_stable_for_identical_inputs():
    assert cache_key(SPEC, **KEY_ARGS) == cache_key(SPEC, **KEY_ARGS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pooling", "cls"),
        ("max_seq_len", 512),
        ("revision", "f" * 40),
        ("base_model", "bert-base-cased"),
    ],
)
def test_cache_key_changes_with_every_encoder_input(field, value):
    """Mean and CLS are different vectors from the same weights; so is a truncation."""
    changed = EmbeddingSpec(**{**SPEC.to_dict(), field: value})
    assert cache_key(changed, **KEY_ARGS) != cache_key(SPEC, **KEY_ARGS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("signal", "dysuria_present"),
        ("fold_index", 3),
        ("split", "test"),
        ("generator_version", 3),
        ("dataset_seed", 43),
        ("digest", "0000000000000000"),
    ],
)
def test_cache_key_changes_with_every_dataset_input(field, value):
    assert cache_key(SPEC, **{**KEY_ARGS, field: value}) != cache_key(SPEC, **KEY_ARGS)


def test_cache_key_is_readable_and_carries_the_format_version():
    """A directory listing has to say what each file is; a hash alone would not."""
    key = cache_key(SPEC, **KEY_ARGS)
    assert key.startswith(f"v{CACHE_FORMAT_VERSION}.")
    assert "pool-mean" in key
    assert "len256" in key
    assert "fold0" in key
    assert cache_path("/tmp/cache", key).name.endswith(".pt")


def test_content_digest_notices_an_edited_fragment():
    """The field that catches a regeneration the version and seed cannot see.

    Editing a fragment library and regenerating with the same seed produces
    different text under an unchanged version. Without the digest that reuses the
    previous run's embeddings against the new labels.
    """
    split = load_split(TRAIN, expect_split="train")
    before = content_digest(split.examples)

    edited = list(split.examples)
    edited[0] = type(edited[0])(**{**edited[0].__dict__, "text": edited[0].text + " and chills"})
    assert content_digest(edited) != before


def test_content_digest_distinguishes_identical_text_under_different_ids():
    split = load_split(TRAIN, expect_split="train")
    swapped = list(reversed(split.examples))
    assert content_digest(swapped) != content_digest(split.examples)


def test_split_cache_key_reads_the_seed_from_the_sidecar(tmp_path):
    """The generator's own record of the seed, not what a CLI flag believes."""
    split = load_split(TRAIN, expect_split="train")
    key = split_cache_key(SPEC, split, signal=SIGNAL)
    assert f"seed{split.stats['seed']}" in key
    assert f"gen{split.generator_version}" in key


def test_split_cache_key_refuses_a_sidecar_with_no_seed(tmp_path):
    target = tmp_path / TRAIN.name
    target.write_text(TRAIN.read_text(encoding="utf-8"), encoding="utf-8")
    stats = json.loads(sidecar_path(TRAIN).read_text(encoding="utf-8"))
    del stats["seed"]
    sidecar_path(target).write_text(json.dumps(stats), encoding="utf-8")

    split = load_split(target, expect_split="train")
    with pytest.raises(EmbedError, match="no 'seed'"):
        split_cache_key(SPEC, split, signal=SIGNAL)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("pooling", "average", "pooling must be one of"),
        ("max_seq_len", 0, "max_seq_len must be positive"),
        ("revision", "", "resolved model revision"),
    ],
)
def test_embedding_spec_rejects_an_unkeyable_encoder(field, value, message):
    with pytest.raises(EmbedError, match=message):
        EmbeddingSpec(**{**SPEC.to_dict(), field: value})


# --------------------------------------------------------------------------
# Determinism (DD11)
# --------------------------------------------------------------------------


def test_deterministic_env_is_set_before_torch_would_read_it(monkeypatch):
    monkeypatch.delenv(CUBLAS_ENV_VAR, raising=False)
    assert ensure_deterministic_env() == CUBLAS_ENV_VALUE
    assert os.environ[CUBLAS_ENV_VAR] == CUBLAS_ENV_VALUE


def test_deterministic_env_respects_a_value_the_caller_already_chose(monkeypatch):
    monkeypatch.setenv(CUBLAS_ENV_VAR, ":16:8")
    assert ensure_deterministic_env() == ":16:8"


def test_fold_seeds_differ_so_five_folds_are_not_one_run_repeated():
    config = ProbeConfig(seed=5)
    seeds = {config.fold_seed(index) for index in range(5)}
    assert len(seeds) == 5
    assert config.fold_seed(0) == 5


def test_probe_config_records_what_it_did_not_search_over():
    recorded = ProbeConfig().to_dict()
    assert recorded["base_model"] == DEFAULT_BASE_MODEL
    assert recorded["max_seq_len"] == 256
    assert recorded["dtype"] == "float32"
    assert "unweighted" in recorded["loss"]
    assert "validation" in recorded["epoch_selection"]


# --------------------------------------------------------------------------
# Artefacts and the metadata sidecar (provisional plan section 4.2)
# --------------------------------------------------------------------------


def test_metadata_carries_every_required_field():
    metadata = _metadata([_probe_result()])
    for field_name in (
        "arm",
        "signal",
        "classes",
        "encoder",
        "config",
        "device",
        "dataset",
        "ruleset_hash",
        "folds",
    ):
        assert field_name in metadata, field_name
    assert metadata["classes"] == ["false", "true", "null"]
    assert metadata["encoder"]["revision"] == SPEC.revision
    assert metadata["margins"]["by_fold"] == {"0": 0.0}
    assert "validation" in metadata["folds"][0]
    assert metadata["folds"][0]["best_epoch"] == 7


def test_metadata_records_the_encoder_contract_it_cannot_satisfy():
    """A single fever head cannot satisfy EncoderOutput, and the sidecar says so.

    ``EncoderOutput.validate_against`` requires an exact key match against the
    ruleset's ``send_to_encoder`` signals, of which ``data/uti1.json`` declares
    seven. Recorded in the artefact rather than only in a plan, so nobody wires
    this head into the engine expecting it to validate.
    """
    metadata = _metadata([_probe_result()])
    assert "EncoderOutput" in metadata["encoder_contract"]


def test_metadata_guard_fires_when_a_required_field_goes_missing(monkeypatch):
    monkeypatch.setattr(
        "scripts.encoder_training.train.REQUIRED_METADATA", ("arm", "not_a_real_field")
    )
    with pytest.raises(TrainError, match="not_a_real_field"):
        _metadata([_probe_result()])


def test_head_artefact_is_json_not_a_pickle(tmp_path):
    """Weights readable without torch, diffable in review, unable to execute on load."""
    result = _probe_result()
    metadata = _metadata([result])
    written = write_artefacts(
        tmp_path, signal=SIGNAL, arm=ARM_A_NAME, metadata=metadata, results=[result]
    )
    names = {path.name for path in written}
    assert names == {"metadata.json", "fold0.head.json", "fold0.decision.json"}

    head = load_head_artefact(tmp_path / "fold0.head.json")
    assert head["signal"] == SIGNAL
    assert head["classes"] == ["false", "true", "null"]
    assert head["heads"][SIGNAL]["bias"] == [0.0, 0.1, 0.2]
    assert head["n_parameters"] == 2307

    # The rule is its own file: the margin is retuned far more often than the
    # weights are, and it has to be readable without loading a model (DD9).
    rule = DecisionRule.read(tmp_path / "fold0.decision.json")
    assert rule.selected_on == "val"
    assert rule.margin == 0.0


def test_written_metadata_round_trips_into_an_embedding_spec(tmp_path):
    """A sidecar can re-key the cache it was trained against, or it is not provenance."""
    result = _probe_result()
    write_artefacts(
        tmp_path,
        signal=SIGNAL,
        arm=ARM_A_NAME,
        metadata=_metadata([result]),
        results=[result],
    )
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert spec_from_metadata(metadata) == SPEC


def test_artefacts_are_written_per_fold(tmp_path):
    results = [_probe_result(index) for index in range(3)]
    write_artefacts(
        tmp_path,
        signal=SIGNAL,
        arm=ARM_A_NAME,
        metadata=_metadata(results),
        results=results,
    )
    for index in range(3):
        assert (tmp_path / f"fold{index}.head.json").is_file()
        assert (tmp_path / f"fold{index}.decision.json").is_file()


def test_head_artefact_names_the_arm_it_came_from():
    artefact = head_artefact(_probe_result(), signal=SIGNAL, arm=ARM_A_NAME)
    assert artefact["arm"] == ARM_A_NAME
    assert artefact["fold"] == 0


# --------------------------------------------------------------------------
# Pooling and the masked loss -- torch required
# --------------------------------------------------------------------------


def test_cli_exposes_the_arm_and_its_defaults_without_any_ml_wheels():
    """The CLI must stay importable and parseable with no torch installed.

    ``model.py`` is the only module that imports torch at module scope; ``train``
    imports it inside its functions. If that ever slips, this import fails on
    CI's runner -- which is the machine that covers every stdlib test in the
    package -- and the whole file goes red rather than skipping quietly.
    """
    from scripts.encoder_training.__main__ import build_parser

    parser = build_parser()
    for command in ("generate-folds", "baselines", "smoke", "probe"):
        assert parser.parse_args([command]).command == command

    probe = parser.parse_args(["probe"])
    assert probe.epochs == ProbeConfig.epochs
    assert probe.batch_size == ProbeConfig.batch_size
    assert probe.train_seed == ProbeConfig.seed
    assert probe.base_model == DEFAULT_BASE_MODEL
    assert probe.pooling == "mean"
    assert probe.max_seq_len == 256
    # The cache is regenerable and large, so it belongs under the git-ignored
    # generated/ tree rather than anywhere a commit could pick it up.
    assert str(probe.cache_dir).startswith("data/synthetic/generated/")


def test_mean_pooling_ignores_padded_positions(torch_module):
    """Otherwise an embedding depends on the longest sentence in its batch.

    Which means the same text embeds differently depending on what it was batched
    with, and the numbers drift with ``--embed-batch-size`` rather than with the
    data. Silent, and it would poison the cache.
    """
    from scripts.encoder_training.model import pool

    hidden = torch_module.tensor([[[1.0, 1.0], [3.0, 3.0], [99.0, 99.0]]])
    mask = torch_module.tensor([[1, 1, 0]])
    pooled = pool(hidden, mask, "mean")
    assert pooled.tolist() == [[2.0, 2.0]]


def test_cls_pooling_takes_the_first_position(torch_module):
    from scripts.encoder_training.model import pool

    hidden = torch_module.tensor([[[7.0, 8.0], [1.0, 1.0]]])
    mask = torch_module.tensor([[1, 1]])
    assert pool(hidden, mask, "cls").tolist() == [[7.0, 8.0]]


def test_pooling_rejects_an_unknown_mode(torch_module):
    from scripts.encoder_training.model import ModelError, pool

    hidden = torch_module.zeros((1, 2, 2))
    mask = torch_module.ones((1, 2), dtype=torch_module.long)
    with pytest.raises(ModelError, match="pooling must be one of"):
        pool(hidden, mask, "max")


def test_head_has_the_parameter_count_the_plan_claims(torch_module):
    from scripts.encoder_training.model import LinearHeads

    assert LinearHeads([SIGNAL]).n_parameters == 768 * 3 + 3 == 2307


def test_head_state_round_trips_through_plain_lists(torch_module):
    from scripts.encoder_training.model import LinearHeads

    heads = LinearHeads([SIGNAL], hidden_size=4)
    state = heads.state_lists()
    restored = LinearHeads([SIGNAL], hidden_size=4).load_state_lists(state)
    assert restored.state_lists() == state


def test_masked_loss_excludes_unlabelled_positions(torch_module):
    """DD10: a *missing* signal key is not a label of ``false``.

    With one head there is never a missing key, so this path gets no coverage
    from real data at all. Conflating "excluded from the loss" with "train
    towards null" once several heads exist teaches every head to answer "not
    mentioned" on every other head's data, and the only symptom is that the model
    is mysteriously bad.
    """
    from scripts.encoder_training.model import masked_cross_entropy

    logits = {SIGNAL: torch_module.tensor([[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]])}
    labelled_only = {SIGNAL: torch_module.tensor([[2.0, 0.0, 0.0]])}

    with_mask = masked_cross_entropy(
        logits, {SIGNAL: torch_module.tensor([CLASS_FALSE, MASKED_CLASS])}
    )
    without = masked_cross_entropy(labelled_only, {SIGNAL: torch_module.tensor([CLASS_FALSE])})
    assert with_mask.item() == pytest.approx(without.item())


def test_masked_loss_on_an_all_masked_batch_is_zero_not_nan(torch_module):
    """``F.cross_entropy`` returns NaN here, which destroys every weight next step."""
    from scripts.encoder_training.model import LinearHeads, masked_cross_entropy

    heads = LinearHeads([SIGNAL], hidden_size=4)
    pooled = torch_module.ones((2, 4))
    loss = masked_cross_entropy(
        heads(pooled), {SIGNAL: torch_module.tensor([MASKED_CLASS, MASKED_CLASS])}
    )
    assert loss.item() == 0.0
    assert loss.requires_grad

    loss.backward()
    weight_grad = heads.heads[SIGNAL].weight.grad
    assert weight_grad is not None
    assert torch_module.count_nonzero(weight_grad).item() == 0


def test_masked_loss_averages_over_all_signals_together(torch_module):
    """Not a mean of per-signal means, which would weight a rare head equally."""
    from scripts.encoder_training.model import masked_cross_entropy

    logits = {
        "a": torch_module.tensor([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]),
        "b": torch_module.tensor([[0.0, 0.0, 0.0]]),
    }
    targets = {
        "a": torch_module.tensor([CLASS_TRUE, CLASS_TRUE]),
        "b": torch_module.tensor([CLASS_NULL]),
    }
    # Every logit is uniform, so every labelled position contributes log(3)
    # whatever the weighting; what this pins is that three positions were counted
    # rather than two groups.
    import math

    assert masked_cross_entropy(logits, targets).item() == pytest.approx(math.log(3), abs=1e-6)


def test_masked_loss_demands_targets_for_every_head(torch_module):
    from scripts.encoder_training.model import ModelError, masked_cross_entropy

    with pytest.raises(ModelError, match="no targets for signal"):
        masked_cross_entropy(
            {SIGNAL: torch_module.zeros((1, 3))}, {"other": torch_module.zeros((1,))}
        )


def test_permuted_targets_keep_the_mask_and_the_class_balance(torch_module):
    from scripts.encoder_training.train import permute_targets

    targets = torch_module.tensor([[CLASS_TRUE], [CLASS_FALSE], [MASKED_CLASS], [CLASS_NULL]])
    permuted = permute_targets(targets, seed=3)

    assert permuted[2, 0].item() == MASKED_CLASS
    assert sorted(permuted[:, 0].tolist()) == sorted(targets[:, 0].tolist())


# --------------------------------------------------------------------------
# The embedding cache end to end -- torch required, no model download
# --------------------------------------------------------------------------


def test_second_call_hits_the_cache_and_does_not_run_the_encoder(torch_module, tmp_path):
    split = load_split(TRAIN, expect_split="train")
    encoder = _StubEncoder(SPEC)

    first, path, hit = load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)
    assert hit is False
    assert encoder.calls == 1
    assert path.is_file()

    second, same_path, hit_again = load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)
    assert hit_again is True
    assert encoder.calls == 1, "a cache hit must not run a forward pass"
    assert same_path == path
    assert torch_module.equal(first, second)


def test_changing_pooling_mode_misses_the_cache(torch_module, tmp_path):
    """Instruction 5: verify the key changes with pooling, because the failure is silent."""
    split = load_split(TRAIN, expect_split="train")
    mean = _StubEncoder(SPEC)
    cls = _StubEncoder(EmbeddingSpec(**{**SPEC.to_dict(), "pooling": "cls"}))

    _, mean_path, _ = load_or_build(split, mean, signal=SIGNAL, directory=tmp_path)
    _, cls_path, hit = load_or_build(split, cls, signal=SIGNAL, directory=tmp_path)
    assert hit is False
    assert mean_path != cls_path
    assert cls.calls == 1


def test_a_cache_file_that_disagrees_with_its_name_is_an_error(torch_module, tmp_path):
    """Not silently rebuilt: one of the two is wrong and guessing hides which."""
    split = load_split(TRAIN, expect_split="train")
    encoder = _StubEncoder(SPEC)
    _, path, _ = load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)

    payload = torch_module.load(path, map_location="cpu", weights_only=True)
    payload["key"] = "v1.something.else"
    torch_module.save(payload, path)

    with pytest.raises(EmbedError, match="keyed"):
        load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)


def test_a_cache_file_whose_examples_moved_is_an_error(torch_module, tmp_path):
    split = load_split(TRAIN, expect_split="train")
    encoder = _StubEncoder(SPEC)
    _, path, _ = load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)

    payload = torch_module.load(path, map_location="cpu", weights_only=True)
    payload["example_ids"] = list(reversed(payload["example_ids"]))
    torch_module.save(payload, path)

    with pytest.raises(EmbedError, match="do not match"):
        load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)


def test_embeddings_are_returned_in_split_order(torch_module, tmp_path):
    split = load_split(TRAIN, expect_split="train")
    encoder = _StubEncoder(SPEC)
    embeddings, _, _ = load_or_build(split, encoder, signal=SIGNAL, directory=tmp_path)
    assert embeddings.shape[0] == len(split.examples)


# --------------------------------------------------------------------------
# Arm A end to end on the fixture fold -- torch required, no model download
# --------------------------------------------------------------------------


def test_probe_learns_a_separable_feature_and_reports_it(torch_module, tmp_path):
    """The whole arm, on features a linear probe must solve perfectly.

    Deliberately not a test that the probe is good at anything real. It isolates
    the plumbing -- embed, cache, masked loss, optimiser step, epoch selection on
    validation, margin selection on validation, then test scored once -- so that a
    break in that chain fails here instead of looking like a disappointing number
    on real data.
    """
    from scripts.encoder_training.train import run_probe

    fold = load_fold(TRAIN, VAL, TEST)
    truths = {
        example.text: example.class_for(SIGNAL)
        for split in fold.splits
        for example in split.examples
    }
    encoder = _SeparableEncoder(SPEC, truths)

    run, results = run_probe(
        [fold],
        encoder,
        signal=SIGNAL,
        config=ProbeConfig(epochs=60, batch_size=4, lr=0.1),
        cache_dir=tmp_path,
        device="cpu",
    )

    assert run.name == ARM_A_NAME
    assert run.kind == "probe"
    assert len(results) == 1
    pooled = run.pooled("ruled")
    assert len(pooled) == len(fold.test)
    assert all(prediction.correct for prediction in pooled)

    # Provenance survives into the predictions, which is what every slice in the
    # report is built from.
    assert {prediction.label_mode for prediction in pooled} <= {
        "true",
        "false",
        "null_structural",
        "null_ambiguous",
    }
    assert any(prediction.fragment_id for prediction in pooled)


def test_probe_result_records_the_validation_numbers_its_margin_came_from(torch_module, tmp_path):
    """Instruction 7: the margin and the evidence for it, per fold."""
    from scripts.encoder_training.train import run_probe

    fold = load_fold(TRAIN, VAL, TEST)
    truths = {
        example.text: example.class_for(SIGNAL)
        for split in fold.splits
        for example in split.examples
    }
    _, results = run_probe(
        [fold],
        _SeparableEncoder(SPEC, truths),
        signal=SIGNAL,
        config=ProbeConfig(epochs=10, batch_size=4, lr=0.1),
        cache_dir=tmp_path,
        device="cpu",
    )
    block = results[0].to_dict()
    assert block["decision_rule"]["selected_on"] == "val"
    assert block["validation"]["n_examples"] == len(fold.val)
    assert 1 <= block["best_epoch"] <= 10
    assert len(block["val_macro_f1_by_epoch"]) == 10
    assert block["cache"]["train"]["hit"] is False


def test_probe_control_permutes_training_labels_only(torch_module, tmp_path):
    """Negative control 1, wired so the control is scored against the truth.

    The separable feature makes this exact rather than statistical: the honest run
    scores 1.0 on test, and the permuted run cannot, because its labels no longer
    correspond to the one-hot feature it was fitted on.
    """
    from scripts.encoder_training.train import run_probe

    fold = load_fold(TRAIN, VAL, TEST)
    truths = {
        example.text: example.class_for(SIGNAL)
        for split in fold.splits
        for example in split.examples
    }
    config = ProbeConfig(epochs=60, batch_size=4, lr=0.1)

    control, _ = run_probe(
        [fold],
        _SeparableEncoder(SPEC, truths),
        signal=SIGNAL,
        config=config,
        cache_dir=tmp_path,
        device="cpu",
        shuffle_seed=11,
    )
    assert control.is_control
    assert control.name.endswith("__shuffled")
    assert "Negative control" in control.description

    honest, _ = run_probe(
        [fold],
        _SeparableEncoder(SPEC, truths),
        signal=SIGNAL,
        config=config,
        cache_dir=tmp_path,
        device="cpu",
    )
    honest_correct = sum(1 for prediction in honest.pooled("ruled") if prediction.correct)
    control_correct = sum(1 for prediction in control.pooled("ruled") if prediction.correct)
    assert honest_correct > control_correct


def test_probe_refuses_a_signal_the_dataset_does_not_carry(torch_module, tmp_path):
    from scripts.encoder_training.train import run_probe

    fold = load_fold(TRAIN, VAL, TEST)
    with pytest.raises(TrainError, match="not one of this dataset's signals"):
        run_probe(
            [fold],
            _StubEncoder(SPEC),
            signal="dysuria_present",
            config=ProbeConfig(epochs=1),
            cache_dir=tmp_path,
            device="cpu",
        )


def test_probe_run_renders_as_a_report(torch_module, tmp_path):
    """Arm A reports in the same format as the baselines, which is the deliverable."""
    from scripts.encoder_training.train import run_probe

    fold = load_fold(TRAIN, VAL, TEST)
    truths = {
        example.text: example.class_for(SIGNAL)
        for split in fold.splits
        for example in split.examples
    }
    run, _ = run_probe(
        [fold],
        _SeparableEncoder(SPEC, truths),
        signal=SIGNAL,
        config=ProbeConfig(epochs=5, batch_size=4, lr=0.1),
        cache_dir=tmp_path,
        device="cpu",
    )
    report = build_report(
        [run], header={"arm": ARM_A_NAME}, boot=BootstrapConfig(resamples=16, seed=0)
    )
    markdown = render_markdown(report)
    assert f"`{ARM_A_NAME}`" in markdown
    assert "eff n" in markdown


# --------------------------------------------------------------------------
# The real encoder wrapper -- transformers required, still no download
# --------------------------------------------------------------------------


def _tiny_encoder_dir(tmp_path: Path, *, lower: bool) -> Path:
    """A minimal local BERT, so the wrapper is tested without a 440MB download.

    Hidden size 768 because :class:`PooledEncoder` asserts it -- a silently
    different width would produce a head of the wrong shape and a cache that
    cannot be compared with anything already on disk.
    """
    from transformers import BertConfig, BertModel

    directory = tmp_path / f"tiny-{'lower' if lower else 'cased'}"
    directory.mkdir(parents=True, exist_ok=True)
    vocab = [
        "[PAD]",
        "[UNK]",
        "[CLS]",
        "[SEP]",
        "[MASK]",
        "fever",
        "Fever",
        "i",
        "have",
        "a",
        "no",
        "temperature",
        ".",
    ]
    (directory / "vocab.txt").write_text("\n".join(vocab) + "\n", encoding="utf-8")
    (directory / "tokenizer_config.json").write_text(
        json.dumps({"do_lower_case": lower, "tokenizer_class": "BertTokenizer"}), encoding="utf-8"
    )
    BertModel(
        BertConfig(
            vocab_size=len(vocab),
            hidden_size=768,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=16,
            max_position_embeddings=64,
        )
    ).save_pretrained(str(directory))
    return directory


def test_tokeniser_casing_is_probed_rather_than_assumed(transformers_module, tmp_path):
    """Instruction 2: check ``do_lower_case`` behaviourally, and record it.

    ``arch_training.md`` section 5 preserves original casing verbatim and
    Bio_ClinicalBERT descends from ``bert-base-cased``, so casing is probably
    signal-bearing. The attribute is a constructor argument a repository can set
    either way, so the fact worth recording is what the tokeniser *does*.
    """
    from scripts.encoder_training.model import PooledEncoder

    cased = PooledEncoder(
        str(_tiny_encoder_dir(tmp_path, lower=False)), revision="local-test"
    ).load()
    lowered = PooledEncoder(
        str(_tiny_encoder_dir(tmp_path, lower=True)), revision="local-test"
    ).load()

    assert cased.facts.lowercases_input is False
    assert lowered.facts.lowercases_input is True
    assert cased.facts.reported_do_lower_case is False
    assert cased.to_dict()["tokeniser"]["lowercases_input"] is False

    # Both fixtures carry `Fever` in the vocabulary, so both vocabularies are
    # cased. Only the lowercasing one throws the casing away: it looks `Fever` up
    # as `fever` and the cased entry becomes unreachable. That combination is
    # Bio_ClinicalBERT's -- `do_lower_case: true` over a vocabulary inherited
    # from `bert-base-cased` -- and it is the reason the fact is recorded rather
    # than the pair of booleans left for a reader to combine.
    assert cased.facts.cased_vocab is True
    assert lowered.facts.cased_vocab is True
    assert cased.facts.discards_casing is False
    assert lowered.facts.discards_casing is True
    assert lowered.to_dict()["tokeniser"]["discards_casing"] is True


def test_encoder_without_a_resolvable_revision_refuses_to_be_cached(transformers_module, tmp_path):
    """A local directory has no commit, and an unkeyed cache is worse than an error.

    Worse because it is the failure that produces plausible numbers: nothing
    crashes, and next month's weights are silently compared against last month's
    report.
    """
    from scripts.encoder_training.model import PooledEncoder

    directory = str(_tiny_encoder_dir(tmp_path, lower=False))
    with pytest.raises(EmbedError, match="--revision"):
        PooledEncoder(directory).load()


def test_encoder_embeds_to_one_vector_per_text(transformers_module, tmp_path):
    from scripts.encoder_training.model import EXPECTED_HIDDEN_SIZE, PooledEncoder

    encoder = PooledEncoder(
        str(_tiny_encoder_dir(tmp_path, lower=False)), revision="local-test", max_seq_len=32
    ).load()
    vectors = encoder.embed(["i have a fever .", "no temperature ."], batch_size=1)
    assert tuple(vectors.shape) == (2, EXPECTED_HIDDEN_SIZE)
    assert vectors.dtype.is_floating_point
    assert encoder.spec.revision == "local-test"


def test_mean_and_cls_pooling_give_different_vectors(transformers_module, tmp_path):
    """DD3: the flag exists so the two get compared once rather than argued about."""
    from scripts.encoder_training.model import PooledEncoder

    directory = str(_tiny_encoder_dir(tmp_path, lower=False))
    texts = ["i have a fever ."]
    mean = PooledEncoder(directory, revision="local-test", pooling="mean").load().embed(texts)
    cls = PooledEncoder(directory, revision="local-test", pooling="cls").load().embed(texts)
    assert not mean.equal(cls)


def test_embedding_a_text_is_independent_of_its_batch(transformers_module, tmp_path):
    """The mask-weighted pool, proved on real padding rather than a hand-made tensor.

    One text embedded alone and the same text embedded beside a much longer one
    must agree. If they do not, every cached vector depends on
    ``--embed-batch-size``.
    """
    from scripts.encoder_training.model import PooledEncoder

    encoder = PooledEncoder(
        str(_tiny_encoder_dir(tmp_path, lower=False)), revision="local-test"
    ).load()
    alone = encoder.embed(["no temperature ."])
    batched = encoder.embed(["no temperature .", "i have a fever . i have a fever ."])
    assert alone[0].allclose(batched[0], atol=1e-5)
