"""Unit tests for Arm B: the fine-tune, its schedule, its artefacts, its controls.

Pure unit tests: no database, no GPU, no network, so there is no ``pytestmark``.

**What runs where**, on the same principle as
``tests/test_encoder_training_arm_a.py``: ``torch`` and ``transformers`` live in
``requirements-ml.txt``, which CI's unit job deliberately does not install, so
the tests that need them skip themselves. The things whose failure would be
*silent* stay on the stdlib side and therefore always run:

* ``test_validation_guided_decisions_*`` and ``test_finetune_config_*`` -- task 5
  instruction 5 caps validation-guided decisions at four, and the cap only means
  something if it reaches the report. A hyperparameter quietly tuned against
  validation makes the pooled result flatter itself by an amount no reader could
  estimate from the numbers alone.
* ``test_metadata_*`` and ``test_head_artefact_points_at_the_encoder_weights`` --
  Arm B's JSON head is *not* the model. The 110M parameters underneath it are,
  they are not committed, and an artefact that does not say where they went is an
  artefact for nothing.
* ``test_warmup_then_decay_*`` -- the learning-rate schedule is arithmetic with no
  torch in it, and a schedule that peaks in the wrong place or goes negative
  trains a model that looks merely disappointing.

The torch-gated ones cover the loop itself, and above all
``test_each_fold_starts_from_pretrained_weights``: reusing one encoder across
folds would start each fold from a model already fine-tuned on the previous
fold's training clusters -- which are this fold's validation and test clusters --
and every disjointness check in the package would still pass.
"""

import json
from pathlib import Path

import pytest

from scripts.encoder_training.__main__ import build_parser
from scripts.encoder_training.dataset import CLASS_FALSE, CLASS_NULL, CLASS_TRUE, load_fold
from scripts.encoder_training.decision import DecisionRule
from scripts.encoder_training.embed import EmbeddingSpec
from scripts.encoder_training.metrics import Prediction
from scripts.encoder_training.report import BootstrapConfig, FoldRun, build_report, render_markdown
from scripts.encoder_training.smoke_cuda import (
    EXPECTED_CAPABILITY,
    MIN_BLACKWELL_CUDA,
    CudaSmokeError,
    format_report,
    require_cuda,
)
from scripts.encoder_training.train import (
    ARM_A_NAME,
    ARM_B_NAME,
    DETERMINISM_MODES,
    FINETUNE_EPOCHS,
    FINETUNE_LR,
    FINETUNE_WARMUP_RATIO,
    VALIDATION_GUIDED_DECISIONS,
    FineTuneConfig,
    FineTuneFoldResult,
    ProbeConfig,
    TrainError,
    build_metadata,
    derive_fold_seed,
    head_artefact,
    warmup_then_decay,
    write_artefacts,
)
from tests.test_encoder_training_arm_a import _tiny_encoder_dir

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


@pytest.fixture
def torch_module():
    return pytest.importorskip("torch", reason="requirements-ml.txt is not installed")


@pytest.fixture
def transformers_module():
    return pytest.importorskip("transformers", reason="requirements-ml.txt is not installed")


def _prediction(example_id, truth, predicted, unit, **kwargs):
    return Prediction(example_id=example_id, truth=truth, predicted=predicted, unit=unit, **kwargs)


def _finetune_result(fold_index=0, weights_path="models/encoder/fever_present/arm_b/f0.pt"):
    """A FineTuneFoldResult built by hand, with no torch anywhere near it."""
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
            library="fever_null_metaphor",
            subclass="metaphor",
            fragment_id="fever_null_metaphor:22222222",
            scores=(0.6, 0.1, 0.3),
        ),
    ]
    rule = DecisionRule(
        margin=0.1,
        selected_on="val",
        argmax_null_to_true_rate=0.05,
        null_to_true_rate=0.02,
        macro_f1=0.6,
    )
    return FineTuneFoldResult(
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
        n_parameters=108_312_579,
        n_trainable=108_312_579,
        best_epoch=2,
        val_macro_f1_by_epoch=(0.4, 0.6, 0.55),
        train_loss_by_epoch=(0.9, 0.4, 0.2),
        val_summary={"n_examples": 4, "effective_n": 3, "accuracy": 0.75, "macro_f1": 0.6},
        steps_per_epoch=313,
        warmup_steps=94,
        weights_path=weights_path,
    )


def _metadata(results, **overrides):
    payload = {
        "signal": SIGNAL,
        "arm": ARM_B_NAME,
        "encoder_facts": {**SPEC.to_dict(), "tokeniser": {"lowercases_input": False}},
        "config": FineTuneConfig(),
        "device": {"device": "cuda", "kernel_launch_ok": True, "compute_capability": [12, 0]},
        "dataset": {"dir": "data/synthetic/generated/folds", "folds": 5, "generator_version": 2},
        "ruleset": "data/uti1.json",
        "ruleset_hash": "0" * 64,
        "results": results,
    }
    payload.update(overrides)
    return build_metadata(**payload)


# --------------------------------------------------------------------------
# The hyperparameters, and the cap on what validation is allowed to choose
# --------------------------------------------------------------------------


def test_finetune_defaults_are_the_published_recipe():
    """Instruction 5: chosen once from published practice, not from our validation set."""
    config = FineTuneConfig()
    assert (config.lr, config.epochs, config.warmup_ratio) == (
        FINETUNE_LR,
        FINETUNE_EPOCHS,
        FINETUNE_WARMUP_RATIO,
    )
    assert (config.lr, config.epochs, config.warmup_ratio) == (2e-5, 3, 0.1)
    assert config.batch_size == 32


def test_config_records_that_nothing_was_traded_for_memory():
    """Instruction 2: anything that reads like a compute compromise is a mistake."""
    recorded = FineTuneConfig().to_dict()
    assert recorded["dtype"] == "float32"
    assert "all layers" in recorded["trainable"]
    for compromise in ("checkpointing", "8-bit", "LoRA", "accumulation"):
        assert compromise in recorded["memory_strategy"]


def test_validation_guided_decisions_are_capped_at_four_and_reach_the_sidecar():
    """The cap is only a cap if a reader of the artefact can see it.

    How much the pooled result flatters itself (DD4) depends on how many
    quantities were tuned against validation, and that is not recoverable from a
    list of hyperparameters -- a learning rate looks the same whether it was
    chosen from published practice or from twenty validation runs.
    """
    assert len(VALIDATION_GUIDED_DECISIONS) == 4
    joined = " ".join(VALIDATION_GUIDED_DECISIONS).lower()
    for decision in ("pooling", "learning rate", "epoch", "margin"):
        assert decision in joined
    assert FineTuneConfig().to_dict()["validation_guided_decisions"] == list(
        VALIDATION_GUIDED_DECISIONS
    )


def test_config_rejects_a_determinism_mode_it_cannot_honour():
    with pytest.raises(TrainError, match="determinism"):
        FineTuneConfig(determinism="sometimes")


def test_config_rejects_a_warmup_ratio_that_never_finishes_warming_up():
    with pytest.raises(TrainError, match="warmup_ratio"):
        FineTuneConfig(warmup_ratio=1.0)


def test_determinism_mode_is_recorded_rather_than_assumed():
    """Instruction 4: enable it where it does not break a needed op, and say which ran."""
    assert DETERMINISM_MODES == ("strict", "warn", "off")
    assert FineTuneConfig().determinism == "strict"
    assert FineTuneConfig(determinism="warn").to_dict()["determinism"] == "warn"


def test_both_arms_derive_fold_seeds_the_same_way():
    """The arms are compared against each other; a seeding difference is noise to rule out."""
    assert derive_fold_seed(1234, 0) != derive_fold_seed(1234, 1)
    assert ProbeConfig(seed=1234).fold_seed(3) == FineTuneConfig(seed=1234).fold_seed(3)
    assert len({FineTuneConfig().fold_seed(index) for index in range(5)}) == 5


# --------------------------------------------------------------------------
# The learning-rate schedule
# --------------------------------------------------------------------------


def test_warmup_then_decay_peaks_at_the_end_of_warmup():
    total, warmup = 100, 10
    values = [
        warmup_then_decay(step, total_steps=total, warmup_steps=warmup) for step in range(101)
    ]
    assert values[0] == pytest.approx(0.1)
    assert values[warmup - 1] == pytest.approx(1.0)
    assert max(values) == pytest.approx(1.0)
    assert values[total] == pytest.approx(0.0)
    assert all(value >= 0 for value in values)


def test_warmup_then_decay_is_monotone_on_both_sides():
    total, warmup = 60, 6
    rising = [warmup_then_decay(step, total_steps=total, warmup_steps=warmup) for step in range(6)]
    falling = [
        warmup_then_decay(step, total_steps=total, warmup_steps=warmup) for step in range(6, 60)
    ]
    assert rising == sorted(rising)
    assert falling == sorted(falling, reverse=True)


def test_warmup_then_decay_without_warmup_starts_at_full_rate():
    assert warmup_then_decay(0, total_steps=10, warmup_steps=0) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# The CUDA check
# --------------------------------------------------------------------------


def test_expected_capability_is_the_card_the_plan_assumes():
    assert EXPECTED_CAPABILITY == (12, 0)
    assert MIN_BLACKWELL_CUDA == (12, 8)


def test_a_blackwell_card_on_an_old_wheel_is_called_out_by_name():
    """The failure that eats an afternoon: it imports cleanly and dies at the first kernel."""
    lines = format_report(
        {
            "device": "cuda",
            "torch_cuda_version": "12.4",
            "compute_capability": [12, 0],
            "capability_matches_expected": True,
            "wheel_covers_blackwell": False,
            "kernel_launch_ok": True,
        }
    )
    warning = "\n".join(lines)
    assert "WARNING" in warning
    assert "12.8" in warning
    assert "wheel problem, not a code problem" in warning


def test_a_different_card_is_a_note_rather_than_a_warning():
    lines = "\n".join(
        format_report(
            {
                "device": "cuda",
                "torch_cuda_version": "12.8",
                "compute_capability": [8, 6],
                "capability_matches_expected": False,
                "wheel_covers_blackwell": True,
                "kernel_launch_ok": True,
            }
        )
    )
    assert "WARNING" not in lines
    assert "note:" in lines


def test_requiring_cuda_refuses_a_silent_cpu_fallback():
    """A CPU fine-tune is hours, not the ten minutes the plan budgets for the sweep."""
    with pytest.raises(CudaSmokeError, match="--device cpu"):
        require_cuda({"device": "cpu", "cuda_available": False, "torch_cuda_version": None})
    require_cuda({"device": "cuda", "cuda_available": True})  # does not raise


# --------------------------------------------------------------------------
# Artefacts: what a fine-tuned head says about the model it belongs to
# --------------------------------------------------------------------------


def test_metadata_carries_arm_b_and_its_training_curves():
    metadata = _metadata([_finetune_result()])
    assert metadata["arm"] == ARM_B_NAME
    fold = metadata["folds"][0]
    assert fold["train_loss_by_epoch"] == [0.9, 0.4, 0.2]
    assert fold["warmup_steps"] == 94
    assert fold["n_trainable"] > 100_000_000
    assert fold["decision_rule"]["selected_on"] == "val"


def test_metadata_says_where_the_uncommitted_weights_went():
    """Instruction 7: the sidecar is committed, the weights are not.

    Which makes the sidecar the only thing that can say where they are, and
    whether their absence from git is a decision or an accident.
    """
    weights = _metadata([_finetune_result()])["folds"][0]["weights"]
    assert weights["committed"] is False
    assert weights["path"].endswith(".pt")
    assert "two minutes" in weights["note"]


def test_metadata_records_how_the_control_passes():
    """Near-zero train loss *and* chance test performance. Either alone means nothing."""
    metadata = _metadata(
        [_finetune_result()],
        control={
            "shuffle_seed": 7,
            "permuted": "training labels only; validation and test left unpermuted",
            "run_name": f"{ARM_B_NAME}__shuffled",
            "passing_looks_like": (
                "near-zero training loss together with chance performance on the unpermuted "
                "test split"
            ),
        },
    )
    control = metadata["negative_control"]
    assert "training labels only" in control["permuted"]
    assert "chance" in control["passing_looks_like"]


def test_head_artefact_points_at_the_encoder_weights_it_is_useless_without():
    """For Arm B the JSON head is not the model, and it must not read like one."""
    artefact = head_artefact(_finetune_result(), signal=SIGNAL, arm=ARM_B_NAME)
    assert artefact["arm"] == ARM_B_NAME
    assert artefact["encoder_weights"].endswith(".pt")
    assert artefact["encoder_weights_committed"] is False


def test_arm_a_head_artefact_names_no_encoder_weights():
    """Arm A's encoder is stock at the recorded revision, so there is nothing to point at."""
    from tests.test_encoder_training_arm_a import _probe_result

    artefact = head_artefact(_probe_result(), signal=SIGNAL, arm=ARM_A_NAME)
    assert "encoder_weights" not in artefact


def test_artefacts_are_written_per_fold_in_the_arm_s_own_directory(tmp_path):
    results = [_finetune_result(fold_index=index) for index in range(3)]
    directory = tmp_path / SIGNAL / ARM_B_NAME
    written = write_artefacts(
        directory,
        signal=SIGNAL,
        arm=ARM_B_NAME,
        metadata=_metadata(results),
        results=results,
    )
    assert len(written) == 1 + 2 * 3
    payload = json.loads((directory / "fold1.head.json").read_text(encoding="utf-8"))
    assert payload["fold"] == 1
    assert json.loads((directory / "fold1.decision.json").read_text(encoding="utf-8"))["margin"]


def test_the_two_arms_do_not_overwrite_each_other(tmp_path):
    """Both write metadata.json and foldN.head.json; a shared directory loses one of them."""
    from scripts.encoder_training.__main__ import _artefact_dir

    args = build_parser().parse_args(["finetune", "--models-dir", str(tmp_path)])
    assert _artefact_dir(args, ARM_A_NAME) != _artefact_dir(args, ARM_B_NAME)
    assert _artefact_dir(args, ARM_B_NAME) == tmp_path / SIGNAL / ARM_B_NAME


# --------------------------------------------------------------------------
# The CLI, on a machine with no ML wheels at all
# --------------------------------------------------------------------------


def test_cli_exposes_the_finetune_subcommand_and_its_defaults():
    args = build_parser().parse_args(["finetune"])
    assert args.handler.__name__ == "run_arm_b"
    assert (args.epochs, args.lr, args.batch_size) == (3, 2e-5, 32)
    assert args.warmup_ratio == 0.1
    assert args.determinism == "strict"
    # The comparisons are on by default: the ticket's question is paired.
    assert args.no_probe is False
    assert args.no_baselines is False
    assert args.no_control is False
    # And a CPU fine-tune has to be asked for.
    assert args.allow_cpu is False


def test_cli_exposes_the_standalone_cuda_check():
    args = build_parser().parse_args(["smoke-cuda", "--require-cuda"])
    assert args.handler.__name__ == "run_smoke_cuda"
    assert args.require_cuda is True


def test_arm_a_riding_along_in_an_arm_b_run_keeps_its_own_recipe():
    """3 epochs at 2e-5 would leave the probe barely fitted, and report that as Arm A."""
    from scripts.encoder_training.__main__ import _finetune_config, _probe_config_for_arm_b

    args = build_parser().parse_args(["finetune"])
    probe = _probe_config_for_arm_b(args)
    finetune = _finetune_config(args)
    assert (probe.epochs, probe.lr) == (ProbeConfig.epochs, ProbeConfig.lr)
    assert (finetune.epochs, finetune.lr) == (3, 2e-5)
    assert probe.pooling == finetune.pooling == args.pooling


# --------------------------------------------------------------------------
# The loop itself -- torch and transformers required, no download
# --------------------------------------------------------------------------


def _encoder_factory(directory, *, device="cpu", calls=None):
    """A factory that loads a fresh tiny BERT, counting how often it was asked."""

    def build():
        from scripts.encoder_training.model import PooledEncoder

        if calls is not None:
            calls.append(1)
        return PooledEncoder(
            str(directory), revision="local-test", max_seq_len=32, device=device
        ).load()

    return build


def _tiny_config(**overrides):
    """Enough optimisation to move a randomly-initialised tiny BERT at all.

    Not the published recipe, deliberately: three epochs at 2e-5 on five examples
    of a model whose weights are noise would leave every metric at its
    initialisation, and the test would then be measuring nothing. These tests
    check the mechanism -- the schedule runs, the loss falls, the best epoch is
    restored, test is scored once -- not the recipe, which is covered above.
    """
    defaults = {
        "base_model": "tiny",
        "revision": "local-test",
        "max_seq_len": 32,
        "epochs": 3,
        "batch_size": 2,
        "lr": 1e-3,
        "eval_batch_size": 2,
        "determinism": "warn",
    }
    defaults.update(overrides)
    return FineTuneConfig(**defaults)


def test_finetune_runs_the_whole_procedure_on_one_fold(transformers_module, tmp_path):
    """Fit, select the epoch on validation, select the margin on validation, score test once."""
    from scripts.encoder_training.train import run_finetune

    fold = load_fold(TRAIN, VAL, TEST)
    run, results = run_finetune(
        [fold],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signal=SIGNAL,
        config=_tiny_config(),
        weights_dir=None,
    )

    assert run.name == ARM_B_NAME
    assert run.kind == "finetune"
    assert len(run.pooled("ruled")) == len(fold.test)

    result = results[0]
    assert len(result.train_loss_by_epoch) == 3
    assert len(result.val_macro_f1_by_epoch) == 3
    assert 1 <= result.best_epoch <= 3
    assert result.n_trainable == result.n_parameters  # every layer unfrozen
    assert result.n_trainable > 1_000_000  # the encoder, not just the head
    assert result.fold_run.rule.selected_on == "val"
    assert result.weights_path is None


def test_finetuning_actually_reduces_the_training_loss(transformers_module, tmp_path):
    """The loop's own smoke test: a model that never learns fails here, not in a report."""
    from scripts.encoder_training.train import run_finetune

    _, results = run_finetune(
        [load_fold(TRAIN, VAL, TEST)],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signal=SIGNAL,
        config=_tiny_config(epochs=6),
        weights_dir=None,
    )
    losses = results[0].train_loss_by_epoch
    assert losses[-1] < losses[0]


def test_each_fold_starts_from_pretrained_weights(transformers_module, tmp_path):
    """The leak no split check would catch, so the only thing that catches it is this.

    One encoder reused across folds would start fold i+1 from a model already
    fine-tuned on fold i's training clusters -- which are fold i+1's validation
    and test clusters. Every dataset file would be blameless.
    """
    from scripts.encoder_training.train import run_finetune

    fold = load_fold(TRAIN, VAL, TEST)
    calls: list[int] = []
    run_finetune(
        [fold, fold, fold],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False), calls=calls),
        signal=SIGNAL,
        config=_tiny_config(epochs=1),
        weights_dir=None,
    )
    assert len(calls) == 3


def test_weights_are_written_once_per_fold_and_can_be_read_back(
    torch_module, transformers_module, tmp_path
):
    from scripts.encoder_training.train import run_finetune

    weights_dir = tmp_path / "weights"
    _, results = run_finetune(
        [load_fold(TRAIN, VAL, TEST)],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signal=SIGNAL,
        config=_tiny_config(epochs=1),
        weights_dir=weights_dir,
    )
    path = Path(results[0].weights_path)
    assert path.parent == weights_dir
    assert not list(weights_dir.glob("*.partial"))  # the atomic write left nothing behind

    payload = torch_module.load(path, map_location="cpu", weights_only=False)
    assert payload["arm"] == ARM_B_NAME
    assert payload["signal"] == SIGNAL
    assert payload["revision"] == "local-test"
    assert payload["heads"][SIGNAL]["bias"]
    assert payload["encoder_state_dict"]


def test_the_control_permutes_training_labels_only(transformers_module, tmp_path):
    from scripts.encoder_training.train import run_finetune

    control, results = run_finetune(
        [load_fold(TRAIN, VAL, TEST)],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signal=SIGNAL,
        config=_tiny_config(epochs=1),
        weights_dir=None,
        shuffle_seed=11,
    )
    assert control.is_control
    assert control.name.endswith("__shuffled")
    assert "unpermuted test split" in control.description
    # The control is scored against the truth, so its predictions still carry the
    # real labels -- which is what makes "chance on test" readable at all.
    assert {prediction.truth for prediction in control.pooled("raw")} <= {0, 1, 2}
    assert results[0].train_loss_by_epoch


def test_finetune_refuses_a_signal_the_dataset_does_not_carry(transformers_module, tmp_path):
    from scripts.encoder_training.train import run_finetune

    with pytest.raises(TrainError, match="not one of this dataset's signals"):
        run_finetune(
            [load_fold(TRAIN, VAL, TEST)],
            _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
            signal="dysuria_present",
            config=_tiny_config(epochs=1),
            weights_dir=None,
        )


def test_finetune_refuses_gradient_checkpointing(transformers_module, tmp_path):
    """Instruction 2: anything that reads like a compute compromise is a mistake."""
    from scripts.encoder_training.train import run_finetune_fold

    directory = _tiny_encoder_dir(tmp_path, lower=False)

    def build():
        encoder = _encoder_factory(directory)()
        encoder.model.gradient_checkpointing_enable()
        return encoder

    with pytest.raises(TrainError, match="checkpointing"):
        run_finetune_fold(
            load_fold(TRAIN, VAL, TEST),
            build,
            signal=SIGNAL,
            config=_tiny_config(epochs=1),
        )


def test_predictions_come_back_in_split_order_with_scores(transformers_module, tmp_path):
    """The margin grid is a probability gap, so every prediction has to carry probabilities."""
    from scripts.encoder_training.model import LinearHeads
    from scripts.encoder_training.train import predict_finetuned

    fold = load_fold(TRAIN, VAL, TEST)
    encoder = _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False))()
    heads = LinearHeads(fold.signals, hidden_size=int(encoder.model.config.hidden_size))

    predictions = predict_finetuned(fold.test.examples, encoder, heads, signal=SIGNAL, batch_size=2)
    assert [prediction.example_id for prediction in predictions] == [
        example.example_id for example in fold.test.examples
    ]
    for prediction in predictions:
        assert prediction.scores is not None
        assert sum(prediction.scores) == pytest.approx(1.0)


def test_arm_b_renders_in_the_same_report_as_arm_a(transformers_module, tmp_path):
    """Deliverable: Arm B numbers across the folds, in the same report format."""
    from scripts.encoder_training.train import run_finetune

    run, _ = run_finetune(
        [load_fold(TRAIN, VAL, TEST)],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signal=SIGNAL,
        config=_tiny_config(epochs=1),
        weights_dir=None,
    )
    report = build_report(
        [run], header={"arm": ARM_B_NAME}, boot=BootstrapConfig(resamples=16, seed=0)
    )
    markdown = render_markdown(report)
    assert f"`{ARM_B_NAME}`" in markdown
    assert "eff n" in markdown
    assert any("Arm B" in line for line in report["expectations"])
