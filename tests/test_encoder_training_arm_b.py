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

import dataclasses
import json
from pathlib import Path

import pytest

from scripts.encoder_training.__main__ import build_parser
from scripts.encoder_training.dataset import (
    CLASS_FALSE,
    CLASS_NULL,
    CLASS_TRUE,
    fold_dataset_path,
    load_fold,
    load_folds,
)
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
    arm_run_name,
    build_metadata,
    derive_fold_seed,
    head_artefact,
    warmup_then_decay,
    write_artefacts,
)
from tests.test_encoder_training_arm_a import _tiny_encoder_dir
from tests.test_encoder_training_merge import FOLDS as _MERGE_FOLDS
from tests.test_encoder_training_merge import write_tree as _write_source_tree

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


# --------------------------------------------------------------------------
# Joint multi-head training (task 3)
#
# ``dataset.py`` and ``metrics.py`` carry the id-remapping half of this (DD4:
# ``Example.id_for``, used by ``Prediction.from_example``), so it needs no
# torch and is covered by ``tests/test_encoder_training_dataset.py`` and
# ``tests/test_encoder_training_metrics.py``. Everything here is the training
# path itself: fanning one fold's training run out into several heads, DD6's
# shared epoch criterion, and the per-head, no-cross-head-trade margin
# selection (instruction 3).
# --------------------------------------------------------------------------

JOINT_SIGNALS = ("fever_present", "dysuria_present")


def _joint_fold(tmp_path, *, signals=JOINT_SIGNALS, name="joint2"):
    """A tiny two-signal merged fold, built by merging two miniature source trees.

    Reuses ``test_encoder_training_merge``'s own miniature generator rather than
    inventing a second one: the merge tool is already exhaustively tested
    against it, and what this module needs is a merged tree to train against,
    not a second opinion on the merge itself.
    """
    from scripts.encoder_training.merge import merge_folds

    source_dir = tmp_path / "sources"
    _write_source_tree(source_dir, signals=signals, folds=_MERGE_FOLDS)
    merged_dir = tmp_path / "merged"
    merge_folds(source_dir, signals=signals, out_dir=merged_dir, name=name, folds=_MERGE_FOLDS)
    folds = load_folds(merged_dir, name, folds=_MERGE_FOLDS)
    return folds[0]


def _drop_signal_from_val(fold, signal):
    """A copy of ``fold`` whose validation split has no example labelled for ``signal``."""
    filtered = tuple(example for example in fold.val.examples if not example.is_labelled(signal))
    return dataclasses.replace(fold, val=dataclasses.replace(fold.val, examples=filtered))


# -- stdlib-only: no torch anywhere near these ------------------------------


def test_labelled_any_is_the_union_across_heads():
    from scripts.encoder_training.dataset import Example
    from scripts.encoder_training.train import _labelled_any

    def _example(example_id, **classes):
        mask = {signal: True for signal in classes}
        return Example(
            example_id=example_id,
            split="train",
            text="x",
            label_mode="true",
            fragment_ids=("f1",),
            classes={**{s: 1 for s in classes}, **classes},
            mask=mask,
            decisive=None,
        )

    fever_only = _example("a", fever_present=1)
    dysuria_only = _example("b", dysuria_present=1)
    neither = _example("c")
    split = dataclasses.replace(
        load_fold(TRAIN, VAL, TEST).train,
        examples=(fever_only, dysuria_only, neither),
    )
    kept = _labelled_any(split, ("fever_present", "dysuria_present"))
    assert [example.example_id for example in kept] == ["a", "b"]
    # A single-signal call reduces to `_labelled`, which is the parity this
    # generalisation has to preserve (instruction 1).
    from scripts.encoder_training.train import _labelled

    assert _labelled_any(split, ("fever_present",)) == _labelled(split, "fever_present")


def test_joint_fold_result_fans_out_into_single_signal_shape():
    """Instruction 5: `for_signal` is what lets the existing report machinery read it."""
    from scripts.encoder_training.train import JointFineTuneFoldResult

    raw = [
        _prediction("test-000000", CLASS_TRUE, CLASS_TRUE, "cluster-a", scores=(0.1, 0.8, 0.1)),
    ]
    fever_rule = DecisionRule(margin=0.1, macro_f1=0.6)
    dysuria_rule = DecisionRule(margin=0.3, macro_f1=0.5)
    joint = JointFineTuneFoldResult(
        fold_index=0,
        signals=("fever_present", "dysuria_present"),
        fold_runs={
            "fever_present": FoldRun.build(
                fold_index=0, n_train=6, n_val=4, n_test=1, rule=fever_rule, raw=raw, ruled=raw
            ),
            "dysuria_present": FoldRun.build(
                fold_index=0, n_train=6, n_val=4, n_test=1, rule=dysuria_rule, raw=raw, ruled=raw
            ),
        },
        head_state={
            "fever_present": {"weight": [[0.1]], "bias": [0.0]},
            "dysuria_present": {"weight": [[0.2]], "bias": [0.1]},
        },
        n_parameters=100,
        n_trainable=100,
        best_epoch=2,
        val_macro_f1_by_epoch={
            "fever_present": (0.4, 0.6),
            "dysuria_present": (0.3, 0.5),
        },
        mean_val_macro_f1_by_epoch=(0.35, 0.55),
        train_loss_by_epoch=(0.9, 0.4),
        val_summary={
            "fever_present": {"n_examples": 4, "macro_f1": 0.6},
            "dysuria_present": {"n_examples": 4, "macro_f1": 0.5},
        },
        steps_per_epoch=3,
        warmup_steps=1,
        weights_path="models/encoder/joint2/arm_b_finetune/weights/fold0.encoder.pt",
    )

    fever_single = joint.for_signal("fever_present")
    assert fever_single.fold_run.rule.margin == 0.1
    assert fever_single.val_macro_f1_by_epoch == (0.4, 0.6)
    assert fever_single.val_summary == {"n_examples": 4, "macro_f1": 0.6}
    # The weights are shared, so both fanned-out results point at every head,
    # not just their own -- a joint model's .pt cannot be sliced by signal.
    assert set(fever_single.head_state) == {"fever_present", "dysuria_present"}
    assert fever_single.best_epoch == joint.for_signal("dysuria_present").best_epoch == 2

    block = joint.to_dict()
    assert block["signals"] == ["fever_present", "dysuria_present"]
    assert block["decision_rules"]["dysuria_present"]["margin"] == 0.3
    assert block["val_macro_f1_by_epoch"]["fever_present"] == [0.4, 0.6]
    assert block["mean_val_macro_f1_by_epoch"] == [0.35, 0.55]


def test_select_then_score_multi_selects_every_head_before_scoring_anything(monkeypatch):
    """Instruction 3, generalising the holdout module's own order test.

    Every head's margin is chosen independently -- the calls to `select_margin`
    are per signal, on that signal's own predictions -- and only once every rule
    exists is `score_test` (and then `score_realistic`) called at all.
    """
    from scripts.encoder_training.train import select_then_score_multi

    calls: list[tuple[str, object]] = []
    fever_predictions = [_prediction("f0", CLASS_TRUE, CLASS_TRUE, "u1", scores=(0, 1, 0))]
    dysuria_predictions = [_prediction("d0", CLASS_NULL, CLASS_NULL, "u2", scores=(0, 0, 1))]

    def fake_select(predictions):
        calls.append(("select_margin", predictions))
        return DecisionRule(margin=0.1 if predictions is fever_predictions else 0.4)

    monkeypatch.setattr("scripts.encoder_training.train.select_margin", fake_select)

    def score_test(rules):
        calls.append(("score_test", dict(rules)))
        return {"fever_present": [], "dysuria_present": []}

    def score_realistic(rules):
        calls.append(("score_realistic", dict(rules)))
        return {"margin": {signal: rule.margin for signal, rule in rules.items()}}

    rules, test_predictions, realistic = select_then_score_multi(
        {"fever_present": fever_predictions, "dysuria_present": dysuria_predictions},
        score_test=score_test,
        score_realistic=score_realistic,
    )

    assert [name for name, _ in calls] == [
        "select_margin",
        "select_margin",
        "score_test",
        "score_realistic",
    ]
    assert rules["fever_present"].margin == 0.1
    assert rules["dysuria_present"].margin == 0.4
    assert realistic == {"margin": {"fever_present": 0.1, "dysuria_present": 0.4}}
    assert test_predictions == {"fever_present": [], "dysuria_present": []}


def test_joint_artefacts_write_the_decision_mapping_form(tmp_path):
    """Instruction 3: `foldN.decision.json` is always `{signal: rule}`, even here."""
    from scripts.encoder_training.train import (
        JointFineTuneFoldResult,
        read_joint_decision,
        write_joint_artefacts,
    )

    raw = [_prediction("test-000000", CLASS_TRUE, CLASS_TRUE, "cluster-a", scores=(0.1, 0.8, 0.1))]
    joint = JointFineTuneFoldResult(
        fold_index=0,
        signals=("fever_present", "dysuria_present"),
        fold_runs={
            "fever_present": FoldRun.build(
                fold_index=0,
                n_train=1,
                n_val=1,
                n_test=1,
                rule=DecisionRule(margin=0.15),
                raw=raw,
                ruled=raw,
            ),
            "dysuria_present": FoldRun.build(
                fold_index=0,
                n_train=1,
                n_val=1,
                n_test=1,
                rule=DecisionRule(margin=0.25),
                raw=raw,
                ruled=raw,
            ),
        },
        head_state={"fever_present": {"weight": [[0.1]], "bias": [0.0]}},
        n_parameters=1,
        n_trainable=1,
        best_epoch=1,
        val_macro_f1_by_epoch={"fever_present": (0.5,), "dysuria_present": (0.4,)},
        mean_val_macro_f1_by_epoch=(0.45,),
        train_loss_by_epoch=(0.5,),
        val_summary={"fever_present": {}, "dysuria_present": {}},
        steps_per_epoch=1,
        warmup_steps=0,
        weights_path="w.pt",
    )
    metadata = {"arm": ARM_B_NAME, "signals": ["fever_present", "dysuria_present"]}
    directory = tmp_path / "joint2" / ARM_B_NAME
    written = write_joint_artefacts(directory, arm=ARM_B_NAME, metadata=metadata, results=[joint])
    assert len(written) == 3  # metadata + head + decision, one fold

    head = json.loads((directory / "fold0.head.json").read_text(encoding="utf-8"))
    assert head["signals"] == ["fever_present", "dysuria_present"]
    assert set(head["heads"]) == {"fever_present"}

    rules = read_joint_decision(directory / "fold0.decision.json")
    assert rules["fever_present"].margin == 0.15
    assert rules["dysuria_present"].margin == 0.25


def test_build_joint_metadata_requires_a_signal_list():
    from scripts.encoder_training.train import REQUIRED_JOINT_METADATA, build_joint_metadata

    assert "signals" in REQUIRED_JOINT_METADATA
    assert "signal" not in REQUIRED_JOINT_METADATA

    metadata = build_joint_metadata(
        signals=["fever_present", "dysuria_present"],
        arm=ARM_B_NAME,
        encoder_facts={**SPEC.to_dict(), "tokeniser": {}},
        config=FineTuneConfig(),
        device={"device": "cpu"},
        dataset={"dir": "x", "folds": 1},
        ruleset="data/uti1.json",
        ruleset_hash="0" * 64,
        results=[],
    )
    assert metadata["signals"] == ["fever_present", "dysuria_present"]
    assert "at most six of seven keys" in metadata["encoder_contract"]


def test_cli_exposes_dataset_and_signals_and_defaults_them_off():
    """A plain `finetune` call must keep resolving to today's single-signal path."""
    args = build_parser().parse_args(["finetune"])
    assert args.dataset is None
    assert args.signals is None

    joint_args = build_parser().parse_args(
        ["finetune", "--dataset", "joint6", "--signals", "fever_present", "dysuria_present"]
    )
    assert joint_args.dataset == "joint6"
    assert joint_args.signals == ["fever_present", "dysuria_present"]


def test_run_arm_b_dispatches_single_vs_joint_by_dataset_and_signals(tmp_path, monkeypatch):
    """The routing rule itself, without paying for an encoder anywhere.

    Same dataset name as the (single) signal takes the path unchanged since
    before `--dataset`/`--signals` existed; anything else -- a merged tree, or
    more than one requested head -- takes the joint path. Both branches are
    monkeypatched to no-ops so this only tests the *routing*.
    """
    import scripts.encoder_training.__main__ as main_module

    calls: list[str] = []

    def fake_single(args, folds):
        calls.append("single")

    def fake_joint(args, folds, *, dataset_name, signals):
        calls.append(f"joint:{dataset_name}:{signals}")

    monkeypatch.setattr(main_module, "_run_arm_b_single", fake_single)
    monkeypatch.setattr(main_module, "_run_arm_b_joint", fake_joint)

    single_dir = tmp_path / "single"
    single_dir.mkdir()
    for split, source in (("train", TRAIN), ("val", VAL), ("test", TEST)):
        destination = fold_dataset_path(single_dir, SIGNAL, 0, split)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        source_stats = source.with_name(source.name + ".stats.json")
        destination_stats = destination.with_name(destination.name + ".stats.json")
        # The committed fixture's sidecar was cut from a five-fold sweep; this
        # test only puts one fold's files on disk, so the sidecar is rewritten
        # to agree with what is actually here rather than read as five.
        stats = json.loads(source_stats.read_text(encoding="utf-8"))
        stats["folds"] = 1
        destination_stats.write_text(json.dumps(stats), encoding="utf-8")

    args = build_parser().parse_args(
        ["finetune", "--signal", SIGNAL, "--data-dir", str(single_dir), "--folds", "1"]
    )
    main_module.run_arm_b(args)
    assert calls == ["single"]

    merged_dir = tmp_path / "merged"
    source_dir = tmp_path / "sources"
    from scripts.encoder_training.merge import merge_folds

    _write_source_tree(source_dir, signals=JOINT_SIGNALS, folds=_MERGE_FOLDS)
    merge_folds(
        source_dir, signals=JOINT_SIGNALS, out_dir=merged_dir, name="joint2", folds=_MERGE_FOLDS
    )
    joint_args = build_parser().parse_args(
        [
            "finetune",
            "--dataset",
            "joint2",
            "--data-dir",
            str(merged_dir),
            "--folds",
            str(_MERGE_FOLDS),
        ]
    )
    main_module.run_arm_b(joint_args)
    assert calls[1].startswith("joint:joint2:")
    assert "fever_present" in calls[1] and "dysuria_present" in calls[1]


# -- torch required: the joint training loop itself -------------------------


def test_a_head_with_no_labelled_validation_examples_fails_loudly(transformers_module, tmp_path):
    """Instruction 9: no silent default margin for a head that cannot select one."""
    from scripts.encoder_training.train import run_finetune_joint_fold

    fold = _drop_signal_from_val(_joint_fold(tmp_path), "dysuria_present")
    with pytest.raises(TrainError, match="dysuria_present.*no labelled validation examples"):
        run_finetune_joint_fold(
            fold,
            _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
            signals=JOINT_SIGNALS,
            config=_tiny_config(epochs=1),
        )


def test_joint_run_produces_one_head_one_rule_one_prediction_set_per_signal(
    transformers_module, tmp_path
):
    """The task 3 deliverable, stated directly: N heads, N rules, N prediction sets."""
    from scripts.encoder_training.train import run_finetune_joint_fold

    fold = _joint_fold(tmp_path)
    result = run_finetune_joint_fold(
        fold,
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signals=JOINT_SIGNALS,
        config=_tiny_config(epochs=2),
        weights_dir=None,
    )

    assert set(result.signals) == set(JOINT_SIGNALS)
    assert set(result.fold_runs) == set(JOINT_SIGNALS)
    assert set(result.head_state) == set(JOINT_SIGNALS)
    assert set(result.val_macro_f1_by_epoch) == set(JOINT_SIGNALS)
    assert len(result.mean_val_macro_f1_by_epoch) == 2

    # DD4: predictions are keyed by the id this example had in *that signal's*
    # own tree, not the merged id -- so single-signal ids like "test-000000",
    # never "fever_present:test-000000".
    for signal in JOINT_SIGNALS:
        fold_run = result.fold_runs[signal]
        assert fold_run.raw, f"{signal} produced no test predictions"
        for prediction in fold_run.raw:
            assert not prediction.example_id.startswith(f"fold0:{signal}:")
            assert not prediction.example_id.startswith("fold0:shared:")
            assert prediction.example_id.startswith("fold0:")


def test_single_signal_joint_run_matches_the_original_single_signal_path(
    transformers_module, tmp_path
):
    """Instruction 1: the parity test.

    `run_finetune_joint_fold` and `run_finetune_fold` are independent
    implementations, so this proves they agree rather than assuming it. Same
    fold, same fresh encoder weights (same tiny-BERT directory, same seed), same
    config: if the two diverge, this is where it shows.
    """
    from scripts.encoder_training.train import run_finetune_fold, run_finetune_joint_fold

    fold = load_fold(TRAIN, VAL, TEST)
    encoder_dir = _tiny_encoder_dir(tmp_path, lower=False)
    config = _tiny_config(epochs=2)

    old = run_finetune_fold(
        fold, _encoder_factory(encoder_dir), signal=SIGNAL, config=config, weights_dir=None
    )
    new = run_finetune_joint_fold(
        fold, _encoder_factory(encoder_dir), signals=[SIGNAL], config=config, weights_dir=None
    )

    assert new.best_epoch == old.best_epoch
    assert new.val_macro_f1_by_epoch[SIGNAL] == old.val_macro_f1_by_epoch
    assert new.mean_val_macro_f1_by_epoch == old.val_macro_f1_by_epoch
    assert new.train_loss_by_epoch == old.train_loss_by_epoch
    assert new.fold_runs[SIGNAL].rule.margin == old.fold_run.rule.margin
    assert [p.example_id for p in new.fold_runs[SIGNAL].raw] == [
        p.example_id for p in old.fold_run.raw
    ]
    assert [p.predicted for p in new.fold_runs[SIGNAL].raw] == [
        p.predicted for p in old.fold_run.raw
    ]
    assert [p.scores for p in new.fold_runs[SIGNAL].raw] == [p.scores for p in old.fold_run.raw]


def test_predict_finetuned_multi_matches_predict_finetuned_for_one_signal(
    transformers_module, tmp_path
):
    from scripts.encoder_training.model import LinearHeads
    from scripts.encoder_training.train import predict_finetuned, predict_finetuned_multi

    fold = load_fold(TRAIN, VAL, TEST)
    encoder = _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False))()
    heads = LinearHeads(fold.signals, hidden_size=int(encoder.model.config.hidden_size))

    single = predict_finetuned(fold.test.examples, encoder, heads, signal=SIGNAL, batch_size=2)
    multi = predict_finetuned_multi(
        fold.test.examples, encoder, heads, signals=[SIGNAL], batch_size=2
    )[SIGNAL]

    assert [p.example_id for p in single] == [p.example_id for p in multi]
    assert [p.predicted for p in single] == [p.predicted for p in multi]
    assert [p.scores for p in single] == [p.scores for p in multi]


def test_run_finetune_joint_fans_out_into_one_model_run_per_signal(transformers_module, tmp_path):
    from scripts.encoder_training.train import run_finetune_joint

    fold = _joint_fold(tmp_path)
    runs, results = run_finetune_joint(
        [fold],
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signals=JOINT_SIGNALS,
        config=_tiny_config(epochs=1),
        weights_dir=None,
    )

    assert set(runs) == set(JOINT_SIGNALS)
    for signal in JOINT_SIGNALS:
        run = runs[signal]
        assert run.kind == "finetune"
        assert len(run.folds) == 1
        assert run.name == runs[JOINT_SIGNALS[0]].name  # one shared physical run
    assert len(results) == 1


def test_joint_weights_file_records_every_head(torch_module, transformers_module, tmp_path):
    from scripts.encoder_training.train import run_finetune_joint_fold

    weights_dir = tmp_path / "weights"
    fold = _joint_fold(tmp_path)
    result = run_finetune_joint_fold(
        fold,
        _encoder_factory(_tiny_encoder_dir(tmp_path, lower=False)),
        signals=JOINT_SIGNALS,
        config=_tiny_config(epochs=1),
        weights_dir=weights_dir,
    )
    payload = torch_module.load(result.weights_path, map_location="cpu", weights_only=False)
    assert set(payload["signals"]) == set(JOINT_SIGNALS)
    assert set(payload["heads"]) == set(JOINT_SIGNALS)


# --------------------------------------------------------------------------
# The three-arm comparison report (task 4)
#
# Stdlib only, and deliberately so: the thing under test is the report shape --
# which arms end up in which report, which pairs are tested, which are recorded
# as untestable, and what the header has to say before any of them is read.
# None of that needs an encoder, and all of it is what the sweep's conclusion
# will be read off. The arms here are majority-class runs standing in for three
# fine-tunes; what makes them A1, A2 and A3 is which tree they were scored on.
# --------------------------------------------------------------------------


def _joint_folds(tmp_path, *, signals=JOINT_SIGNALS, name="joint2"):
    """A source tree and the merged tree beside it, both loaded."""
    from scripts.encoder_training.merge import merge_folds

    source_dir = tmp_path / "sources"
    merged_dir = tmp_path / "merged"
    _write_source_tree(source_dir, signals=signals, folds=_MERGE_FOLDS)
    merge_folds(source_dir, signals=signals, out_dir=merged_dir, name=name, folds=_MERGE_FOLDS)
    return (
        source_dir,
        {signal: load_folds(source_dir, signal, folds=_MERGE_FOLDS) for signal in signals},
        load_folds(merged_dir, name, folds=_MERGE_FOLDS),
    )


def _stub_result(best_epoch, history):
    """The two fields the selected-epoch header line reads off a fold result."""
    return dataclasses.replace(
        FineTuneFoldResult(
            fold_index=0,
            fold_run=FoldRun(
                fold_index=0,
                n_train=1,
                n_val=1,
                n_test=1,
                rule=DecisionRule(margin=0.0, macro_f1=0.5),
                raw=(),
                ruled=(),
            ),
            head_state={},
            n_parameters=1,
            n_trainable=1,
            best_epoch=best_epoch,
            val_macro_f1_by_epoch=history,
            train_loss_by_epoch=(1.0,),
            val_summary={},
            steps_per_epoch=1,
            warmup_steps=0,
        )
    )


def test_selected_epochs_prints_the_head_s_own_best_only_when_it_differs():
    """DD6: where the shared criterion and this head's own best diverge, say so."""
    from scripts.encoder_training.__main__ import _selected_epochs

    agreeing = [_stub_result(1, (0.1, 0.9, 0.5)), _stub_result(2, (0.1, 0.2, 0.9))]
    assert _selected_epochs(agreeing, SIGNAL) == "1, 2"

    # A joint fold: one epoch chosen by the mean across heads, and a per-head
    # history that would have chosen a different one.
    class _Joint:
        best_epoch = 2
        val_macro_f1_by_epoch = {SIGNAL: (0.1, 0.9, 0.4), "dysuria_present": (0.1, 0.2, 0.9)}

    line = _selected_epochs([_Joint()], SIGNAL)
    assert line.startswith("2 (")
    assert "own best epoch would have been 1" in line


def test_labelled_positions_are_unchanged_by_the_merge(tmp_path):
    """The DD1 row that keeps the arms table honest: A3 adds no supervision.

    A merged tree holds every signal's examples, so its examples-per-epoch is
    several times A1's -- but each head is masked wherever it has no label, so
    the number of positions it receives gradient from is the same on both trees.
    An arms table printing only the first number would say the opposite of what
    is true.
    """
    from scripts.encoder_training.__main__ import _labelled_positions

    _, single, merged = _joint_folds(tmp_path)
    for signal in JOINT_SIGNALS:
        assert _labelled_positions(merged, signal) == _labelled_positions(single[signal], signal)
    assert len(merged[0].train) > len(single[JOINT_SIGNALS[0]][0].train)


def _majority_arm(label, dataset, folds_by_signal, *, unpaired=False):
    """One arm's runs, from the majority baseline rather than from an encoder.

    Named the way :func:`train.run_finetune` names a labelled run, because the
    run name is what separates two arms in one report -- ``compare_models`` keys
    its pairs on it, and two arms sharing a name would be compared against
    themselves.
    """
    from scripts.encoder_training.__main__ import _as_unpaired
    from scripts.encoder_training.baselines import MajorityBaseline, run_baseline

    runs = {}
    for signal, folds in folds_by_signal.items():
        run = dataclasses.replace(
            run_baseline(MajorityBaseline, folds, signal=signal),
            name=arm_run_name(ARM_B_NAME, label),
        )
        runs[signal] = _as_unpaired(run, prefix=label) if unpaired else run
    return runs


def _three_arm_reports(tmp_path, monkeypatch, *, capsys=None):
    """Run ``_emit_joint_reports`` over three stand-in arms and read the results."""
    import scripts.encoder_training.__main__ as main_module

    source_dir, single, merged = _joint_folds(tmp_path)
    volume_dir = tmp_path / "volume"
    _write_source_tree(volume_dir, signals=JOINT_SIGNALS, folds=_MERGE_FOLDS)
    volume = {
        signal: load_folds(volume_dir, signal, folds=_MERGE_FOLDS) for signal in JOINT_SIGNALS
    }

    arms = [
        main_module.JointArm(
            label=main_module.ARM_A1_LABEL,
            dataset=str(source_dir),
            folds_by_signal=single,
            runs=_majority_arm(main_module.ARM_A1_LABEL, source_dir, single),
            results={signal: [_stub_result(1, (0.1, 0.9))] for signal in JOINT_SIGNALS},
        ),
        main_module.JointArm(
            label=main_module.ARM_A2_LABEL,
            dataset=str(volume_dir),
            folds_by_signal=volume,
            runs=_majority_arm(main_module.ARM_A2_LABEL, volume_dir, volume, unpaired=True),
            results={signal: [_stub_result(1, (0.1, 0.9))] for signal in JOINT_SIGNALS},
        ),
        main_module.JointArm(
            label=main_module.ARM_A3_LABEL,
            dataset="joint2",
            folds_by_signal={signal: merged for signal in JOINT_SIGNALS},
            runs=_majority_arm(
                main_module.ARM_A3_LABEL, "joint2", {signal: merged for signal in JOINT_SIGNALS}
            ),
            results={signal: [_stub_result(0, (0.9, 0.1))] for signal in JOINT_SIGNALS},
        ),
    ]

    report_dir = tmp_path / "reports"
    args = build_parser().parse_args(
        [
            "joint-compare",
            "--signals",
            *JOINT_SIGNALS,
            "--folds",
            str(_MERGE_FOLDS),
            "--data-dir",
            str(source_dir),
            "--volume-dir",
            str(volume_dir),
            "--report-dir",
            str(report_dir),
            "--no-baselines",
        ]
    )
    status = main_module._emit_joint_reports(
        args,
        arms=arms,
        signals=JOINT_SIGNALS,
        baseline_folds=single,
        joint_dataset="joint2",
        device="cpu",
        holdout=None,
        encoder_header={},
    )
    assert status == 0
    return report_dir


def test_joint_compare_writes_one_report_per_signal_holding_every_arm(tmp_path, monkeypatch):
    report_dir = _three_arm_reports(tmp_path, monkeypatch)

    for signal in JOINT_SIGNALS:
        report = json.loads((report_dir / f"{signal}.joint_comparison.json").read_text())
        assert report["header"]["signal"] == signal
        names = [model["name"] for model in report["models"]]
        assert len(names) == 3
        assert len(set(names)) == 3
        # Every report gets its *own* signal's cluster-tag coverage, not the
        # first signal's. The union handed to `build_report` spans three trees
        # and every signal in them; the filter is what makes it per report.
        libraries = [row["library"] for row in report["cluster_tag_coverage"]["libraries"]]
        assert libraries == [f"{signal.removesuffix('_present')}_true"]


def test_the_paired_arm_is_tested_and_the_volume_arm_is_recorded_as_untestable(
    tmp_path, monkeypatch
):
    """DD1 and DD2 together: A1 vs A3 is the answer, A2 pairs with nothing.

    A3's predictions carry the ids they had in the signal's own tree (DD4), so
    the pairing works with no help from the report layer; A2's are a different
    dataset's and must come back as a recorded skip rather than as an absence.
    """
    import scripts.encoder_training.__main__ as main_module

    report_dir = _three_arm_reports(tmp_path, monkeypatch)
    report = json.loads((report_dir / f"{SIGNAL}.joint_comparison.json").read_text())

    tested = {(entry["a"], entry["b"]) for entry in report["comparisons"]}
    assert tested
    for a, b in tested:
        assert main_module.ARM_A2_LABEL not in a
        assert main_module.ARM_A2_LABEL not in b
    assert any(main_module.ARM_A1_LABEL in a and main_module.ARM_A3_LABEL in b for a, b in tested)

    skipped = report["skipped_comparisons"]
    assert skipped
    assert all(
        main_module.ARM_A2_LABEL in entry["a"] or main_module.ARM_A2_LABEL in entry["b"]
        for entry in skipped
    )
    assert all(entry["n_common"] == 0 for entry in skipped)

    markdown = (report_dir / f"{SIGNAL}.joint_comparison.md").read_text()
    assert "Pairs that could not be tested" in markdown


def test_the_header_carries_the_arms_the_epochs_and_what_no_arm_isolates(tmp_path, monkeypatch):
    """Task 4 instructions 7 and 8, in the header rather than in an appendix."""
    import scripts.encoder_training.__main__ as main_module

    report_dir = _three_arm_reports(tmp_path, monkeypatch)
    report = json.loads((report_dir / f"{SIGNAL}.joint_comparison.json").read_text())
    header = report["header"]

    assert len(header["arms"]) == 3
    for label in (
        main_module.ARM_A1_LABEL,
        main_module.ARM_A2_LABEL,
        main_module.ARM_A3_LABEL,
    ):
        assert any(label in line for line in header["arms"])
        assert label in header["selected_epochs"]
    # The DD1 table: both numbers, per arm, or the arms table says the joint arm
    # added supervision it did not add.
    assert all("examples per epoch" in line for line in header["arms"])
    assert all("labelled positions" in line for line in header["arms"])

    assert header["predictions"] == list(main_module.JOINT_PREDICTIONS)
    assert "No arm is matched to A3" in header["what_no_arm_isolates"]

    markdown = (report_dir / f"{SIGNAL}.joint_comparison.md").read_text()
    assert "what no arm isolates" in markdown
    assert "examples per epoch" in markdown
    # The predictions are the thing the write-up is scored against, so they have
    # to be readable in the markdown, not only in the sidecar.
    assert "possibly slightly negative" in markdown


def test_the_volume_arm_may_not_be_pointed_at_the_paired_arm_s_own_tree(tmp_path):
    """Two seeds of one dataset reported as a volume effect would be a silent lie."""
    import scripts.encoder_training.__main__ as main_module

    args = build_parser().parse_args(
        [
            "joint-compare",
            "--data-dir",
            str(tmp_path),
            "--volume-dir",
            str(tmp_path),
        ]
    )
    with pytest.raises(TrainError, match="same tree"):
        main_module.run_joint_compare(args)


def test_cli_exposes_joint_compare_and_its_three_trees():
    args = build_parser().parse_args(["joint-compare"])
    assert args.handler.__name__ == "run_joint_compare"
    assert len(args.signals) == 6
    assert args.joint_dataset is None
    # A2 is on by default: it is what separates a movement between A1 and A3
    # from a difference in encoder gradient steps.
    assert args.no_volume_arm is False
    # The negative control is off by default here, as in compare-models.
    assert args.control is False
