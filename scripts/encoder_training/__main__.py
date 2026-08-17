"""Command-line entry point for encoder training and evaluation.

Eight subcommands.

    python -m scripts.encoder_training generate-folds --folds 5

Fifteen runs of the generator -- three splits for each of five folds -- written
under one directory by the naming convention :mod:`.dataset` reads back. Scripted
rather than documented because the fifteen runs have to agree on the fold count,
the salt and the seed derivation, and a shell loop that gets one of those wrong
produces a directory that loads cleanly and evaluates nonsense.

    python -m scripts.encoder_training merge-folds --folds 5

Reads the six per-signal fold trees and writes one merged tree beside them, ready
for joint multi-head training. Nothing is regenerated: the merged tree's
``fever_present`` slice *is* the fever tree's own slice, example for example,
which is what lets a joint model be compared pairwise against the single-signal
one. Stdlib only, and every property the concatenation relies on -- one fold
configuration, byte-identical structural nulls, no first-won fragment conflict --
is asserted rather than trusted. See :mod:`.merge`.

    python -m scripts.encoder_training baselines --folds 5

Fits the three baselines and the shuffled-label controls across every fold and
writes the evaluation report. This needs scikit-learn (``requirements-ml.txt``);
generation does not.

    python -m scripts.encoder_training smoke-cuda

Torch and the GPU only: no model, no network, no download. Runs a real matmul on
the device and prints ``torch.version.cuda`` beside the compute capability.
**This is the first command to run on a new machine**, because
``torch.cuda.is_available()`` returning ``True`` proves nothing on an
architecture the installed wheel was not built for -- the import succeeds and the
first kernel launch fails. Ten seconds here saves an afternoon. Also available
standalone as ``python -m scripts.encoder_training.smoke_cuda``.

    python -m scripts.encoder_training smoke

Everything ``smoke-cuda`` does, plus loading the encoder and printing what the
tokeniser actually does to casing. Run it second: when the kernel check fails,
the 440MB download is wasted.

    python -m scripts.encoder_training probe --folds 5

Arm A. Embeds every fold's splits once (cached), fits the ``Linear(768, 3)``
probe, selects each fold's margin on its own validation split, scores test,
writes the head artefacts and metadata sidecar, and writes the evaluation report
-- with the baselines included in the same report by default, because "does
ClinicalBERT beat bag-of-words on ``null_ambiguous``" is a paired question and
McNemar can only answer it when both models are in one report.

    python -m scripts.encoder_training finetune --folds 5

Arm B, the arm that decides the ticket's question: every layer unfrozen, three
epochs per fold, roughly two minutes each on a 12GB card. Same procedure and same
report as Arm A, and by default the same report *also* carries Arm A and the
baselines -- for the same reason, since "does fine-tuning beat the frozen probe
on ``null_ambiguous``" is the paired comparison the whole ticket turns on and
Arm A costs seconds once its embedding cache exists.

Every fold of Arm B is also scored against ``data/realistic/`` -- 67 real-text
submissions, held out permanently -- immediately **after** its margin has been
selected and its test split scored, so the set cannot influence anything. That
is the only number this package produces that speaks to text a patient actually
wrote, and it is a validity check rather than a comparison: 67 submissions
cannot rank two models. ``--no-holdout`` skips it and the report says so.

Each arm writes its artefacts under ``models/encoder/<signal>/<arm>/``. Arm B's
~440MB of fine-tuned encoder per fold goes there too and is **not** committed;
``models/.gitignore`` covers it and the metadata sidecar records where it went.

    python -m scripts.encoder_training compare-models --folds 5

Arm B over several base models against the *same* folds, in **one** report. One
report is the point: the paired McNemar tests are between the runs in a single
report, and two separately-written reports would leave only overlapping
confidence intervals -- which the 2026-08-09 numbers say could not separate
anything this comparison might find. Defaults to the incumbent
(Bio_ClinicalBERT), ``bert-base-uncased`` as the pretraining-corpus control, and
``roberta-base`` as the contender on negation scope.

No command touches ``app/``, and nothing in ``app/`` imports this. The dependency
runs one way, and ``tests/test_wiring.py`` asserts it.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.synthetic_data.__main__ import DEFAULT_FOLD_SALT
from scripts.synthetic_data.__main__ import main as generate_main

from .baselines import run_all
from .dataset import SPLITS, DatasetError, fold_dataset_path, load_folds
from .embed import POOLING_MODES, EmbedError
from .holdout import DEFAULT_HOLDOUT_PATH, HoldoutError, HoldoutSet, encoder_signals, load_holdout
from .merge import DEFAULT_SIGNALS, MergeError, merge_folds
from .report import BootstrapConfig, build_report, write_report
from .ruleset_hash import hash_ruleset_file
from .smoke_cuda import CudaSmokeError, check_device, format_report

# `train` imports torch inside its functions, exactly as `baselines` does with
# scikit-learn, so importing it here costs nothing on a machine with no ML
# wheels and keeps this whole CLI importable in CI. `model` is the one module
# that cannot avoid a module-level torch import, so it stays lazy below.
from .train import (
    ARM_A_NAME,
    ARM_B_NAME,
    DEFAULT_BASE_MODEL,
    DETERMINISM_MODES,
    VALIDATION_GUIDED_DECISIONS,
    FineTuneConfig,
    ProbeConfig,
    TrainError,
    build_joint_metadata,
    build_metadata,
    display_model,
    resolve_device,
    run_finetune,
    run_finetune_joint,
    run_probe,
    write_artefacts,
    write_joint_artefacts,
)

#: The default three-encoder comparison, and why each one is in it.
#:
#: ``Bio_ClinicalBERT`` is the incumbent -- the encoder every number on file was
#: produced with, so it is the thing the other two have to beat.
#:
#: ``bert-base-uncased`` is the **control**, not a contender. It isolates the
#: pretraining corpus: same architecture, same size, general English instead of
#: MIMIC-III discharge summaries. It also settles the casing question by
#: construction, because its vocabulary is built for lowercased text, where
#: Bio_ClinicalBERT lowercases input into a vocabulary inherited from
#: ``bert-base-cased`` (28,996 entries -- see :class:`model.TokeniserFacts`). If
#: it wins, part of the gain is the tokeniser rather than the register.
#:
#: ``roberta-base`` is the actual contender, and on a different axis than
#: clinical-vs-lay. The largest error family on file is contrastive negation --
#: "my mum had a fever, I never got one" -- which is negation scope and
#: attribution, not vocabulary. BERT-base of any pretraining corpus is weak
#: there; RoBERTa is meaningfully better. ``deberta-v3-base`` is the stronger
#: choice again on that axis and is a supported ``--base-models`` value, but it
#: is not in the default set because its tokeniser needs ``sentencepiece`` and
#: ``protobuf``, which ``requirements-ml.txt`` does not install.
DEFAULT_COMPARISON_MODELS = (
    "emilyalsentzer/Bio_ClinicalBERT",
    "bert-base-uncased",
    "roberta-base",
)

DEFAULT_SIGNAL = "fever_present"
DEFAULT_FOLDS = 5
DEFAULT_DATA_DIR = Path("data/synthetic/generated/folds")
DEFAULT_REPORT_DIR = Path("reports/encoder_training")
DEFAULT_MANIFEST = Path("data/synthetic/manifest.json")
DEFAULT_RULESET = Path("data/uti1.json")

#: Where Arm A's embedding cache lives. Under ``data/synthetic/generated/``
#: because that path is already git-ignored and this is roughly 215MB for a
#: five-fold sweep -- regenerable from the datasets plus the pinned encoder, and
#: therefore not something to keep in git.
DEFAULT_CACHE_DIR = Path("data/synthetic/generated/embeddings")

#: Where trained heads and their metadata sidecar go. A root-level ``models/``
#: never enters the production image: the Dockerfile copies ``app/`` and
#: ``data/`` explicitly rather than ``COPY . .`` (DD13).
DEFAULT_MODELS_DIR = Path("models/encoder")

#: Examples per split. The proof-of-concept proportions from
#: `arch_training.md`, per fold. Generation is seconds, so the cost of the
#: five-fold sweep is dominated by nothing at all.
DEFAULT_COUNTS = {"train": 10_000, "val": 2_000, "test": 2_000}

#: Offset added to the base seed per split, so the three splits of one fold do
#: not draw the same random stream against different pools.
_SPLIT_SEED_OFFSET = {"train": 0, "val": 1, "test": 2}

#: Spacing between folds' seeds. Wide enough that no two runs in the sweep can
#: collide however the offsets above change.
_FOLD_SEED_STRIDE = 100


def run_seed(base_seed: int, fold_index: int, split: str) -> int:
    """The generator seed for one of the fifteen runs.

    Derived rather than reused so that fold 3's validation split is not fold 3's
    training split drawn from the same stream, and recorded in the report header
    so any single run can be reproduced from the base seed alone.
    """
    return base_seed + _FOLD_SEED_STRIDE * fold_index + _SPLIT_SEED_OFFSET[split]


def generate_folds(args: argparse.Namespace) -> int:
    """Generate all K folds' three splits by calling the generator's own CLI.

    In-process rather than by subprocess: the generator's argument checking is
    the thing that catches a bad fold index, and routing through its ``main``
    means this wrapper cannot drift into a second, laxer interpretation of the
    same flags.
    """
    written = 0
    for fold_index in range(args.folds):
        for split in SPLITS:
            out_path = fold_dataset_path(args.out_dir, args.signal, fold_index, split)
            argv = [
                "--manifest",
                str(args.manifest),
                "--ruleset",
                str(args.ruleset),
                "--signal",
                args.signal,
                "--split",
                split,
                "--count",
                str(getattr(args, f"{split}_count")),
                "--seed",
                str(run_seed(args.seed, fold_index, split)),
                "--folds",
                str(args.folds),
                "--fold",
                str(fold_index),
                "--split-salt",
                args.split_salt,
                "--out",
                str(out_path),
            ]
            status = generate_main(argv)
            if status != 0:
                print(f"error: generating fold {fold_index} {split} failed", file=sys.stderr)
                return status
            written += 1

    print(f"wrote {written} datasets to {args.out_dir}")
    return 0


def run_merge_folds(args: argparse.Namespace) -> int:
    """Merge the per-signal fold trees into one, and say what was noticed.

    The cluster-key collision warning goes to stderr rather than into the
    sidecar alone: it is not an error -- it deflates effective sample size
    rather than inflating it -- but a merge that quietly folded two libraries'
    fragments into one resampling unit is exactly the kind of invisible change
    this package exists to make visible.
    """
    result = merge_folds(
        args.data_dir,
        signals=args.signals,
        out_dir=args.out_dir,
        name=args.name,
        folds=args.folds,
    )
    for warning in result.warnings:
        print(warning, file=sys.stderr)
    print(
        f"wrote {len(result.paths)} datasets holding {result.examples} examples to "
        f"{args.out_dir or args.data_dir} as signal {result.name!r}"
    )
    return 0


def _header(args: argparse.Namespace, folds, extra: dict | None = None) -> dict:
    """Everything needed to reproduce the run, recorded next to its numbers."""
    first = folds[0].train
    return {
        "signal": args.signal,
        "folds": args.folds,
        "generator_version": first.generator_version,
        "generator_base_seed": args.seed,
        "generator_seed_rule": (
            f"base + {_FOLD_SEED_STRIDE} * fold + "
            f"{{{', '.join(f'{k}: {v}' for k, v in _SPLIT_SEED_OFFSET.items())}}}"
        ),
        "split_salt": first.split_salt,
        "dataset_dir": str(args.data_dir),
        "ruleset": str(args.ruleset),
        "ruleset_hash": hash_ruleset_file(args.ruleset),
        "examples_per_fold": {
            "train": len(folds[0].train),
            "val": len(folds[0].val),
            "test": len(folds[0].test),
        },
        "shuffle_seed": args.shuffle_seed,
        **(extra or {}),
    }


def _checks(folds) -> dict:
    """What was verified rather than assumed, in the report's own words."""
    test_clusters = {info.cluster_key for fold in folds for info in fold.test.fragments.values()}
    return {
        "fragment_disjointness": (
            "checked, not assumed. Loading each fold asserts that no fragment and no cluster "
            "appears in two of its splits, so no hand-written sentence is on both sides of a "
            "train/test boundary and no `[c01]` sibling pair is split across one. Asserted at "
            "load time on every run, and a violation is a hard error rather than a warning."
        ),
        "test_partition": (
            f"checked. Across the {len(folds)} folds, {len(test_clusters)} distinct clusters are "
            "held out, each in exactly one fold, so pooling the folds counts every idea once. "
            "That figure spans every library in the manifest -- filler and other signals' "
            "libraries included -- not just this signal's; the per-slice `eff n` columns are the "
            "numbers that bound anything."
        ),
        "fold_configuration": (
            "checked. The three splits of each fold agree on generator version, fold count, fold "
            "index and salt, and all folds agree on the salt."
        ),
    }


def _fragment_provenance(folds) -> list:
    """Every fragment behind the run, once, from the sidecars the folds carry.

    Deduplicated by fragment id because the same library is read by all three
    splits of all five folds, and a coverage figure that counted a fragment
    fifteen times would still be *right* -- the ratio is unchanged -- while its
    fragment counts would be nonsense next to the cluster table beside them.

    Read from the folds rather than from the manifest on purpose. The libraries
    may have been edited since these datasets were generated, and the coverage
    reported has to describe the libraries the numbers above it came from.
    """
    seen: dict[str, object] = {}
    for fold in folds:
        for split in (fold.train, fold.val, fold.test):
            for fragment_id, info in split.fragments.items():
                seen.setdefault(fragment_id, info)
    return list(seen.values())


def _emit_report(
    runs: Sequence,
    args: argparse.Namespace,
    folds,
    *,
    stem: str,
    extra: dict | None = None,
) -> int:
    """Build and write the evaluation report every command ends with."""
    boot = BootstrapConfig(resamples=args.resamples, seed=args.bootstrap_seed, alpha=args.alpha)
    report = build_report(
        list(runs),
        header=_header(args, folds, extra),
        boot=boot,
        checks=_checks(folds),
        fragments=_fragment_provenance(folds),
    )
    json_path, markdown_path = write_report(
        report,
        args.report_dir,
        stem=stem,
        markdown=not args.no_markdown,
        fragment_rows=args.fragment_rows,
    )
    print(f"wrote {json_path}")
    if markdown_path is not None:
        print(f"wrote {markdown_path}")
    return 0


def run_baselines(args: argparse.Namespace) -> int:
    folds = load_folds(args.data_dir, args.signal, folds=args.folds)
    runs = run_all(folds, signal=args.signal, shuffle_seed=args.shuffle_seed)
    return _emit_report(runs, args, folds, stem=f"{args.signal}.baselines")


def _probe_config(args: argparse.Namespace) -> ProbeConfig:
    """Build Arm A's config from the parsed arguments."""
    return ProbeConfig(
        base_model=args.base_model,
        revision=args.revision,
        pooling=args.pooling,
        max_seq_len=args.max_seq_len,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        seed=args.train_seed,
        device=args.device,
        embed_batch_size=args.embed_batch_size,
    )


def _finetune_config(args: argparse.Namespace) -> FineTuneConfig:
    """Build Arm B's config from the parsed arguments."""
    return FineTuneConfig(
        base_model=args.base_model,
        revision=args.revision,
        pooling=args.pooling,
        max_seq_len=args.max_seq_len,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        warmup_ratio=args.warmup_ratio,
        max_grad_norm=args.max_grad_norm,
        seed=args.train_seed,
        device=args.device,
        eval_batch_size=args.eval_batch_size,
        determinism=args.determinism,
    )


def _probe_config_for_arm_b(args: argparse.Namespace) -> ProbeConfig:
    """Arm A's config when it rides along in an Arm B run.

    Deliberately built from :class:`ProbeConfig`'s own defaults rather than from
    Arm B's flags: 3 epochs at learning rate 2e-5 is the fine-tuning recipe and
    would leave the probe barely fitted, which would then be reported as Arm A's
    result. Only the encoder, the device and the seed are shared.
    """
    return ProbeConfig(
        base_model=args.base_model,
        revision=args.revision,
        pooling=args.pooling,
        max_seq_len=args.max_seq_len,
        seed=args.train_seed,
        device=args.device,
        embed_batch_size=args.embed_batch_size,
    )


def _load_holdout(args: argparse.Namespace) -> HoldoutSet | None:
    """The 67 real submissions, or ``None`` when the run opted out.

    A missing file is a hard error rather than a silent skip. The holdout is the
    only measurement in this project that speaks to real patient text, and a run
    that quietly produced no real-text number because a path was wrong would
    look identical to one that produced a good one. ``--no-holdout`` is how a
    run says it meant to skip it, and the report records which happened.

    Validated against the ruleset's own ``send_to_encoder`` set, not against the
    signal being trained: a labels file that has lost a column is a labels file
    whose distribution table no longer describes it, whichever head is running.
    """
    if args.no_holdout:
        return None
    return load_holdout(args.holdout, signals=encoder_signals(args.ruleset))


def _holdout_header(holdout: HoldoutSet | None) -> str:
    if holdout is None:
        return "not scored (--no-holdout)"
    return f"{holdout.path} -- {len(holdout)} real submissions, scored after test, selects nothing"


def _artefact_dir(args: argparse.Namespace, arm: str) -> Path:
    """Where one arm's artefacts live: ``models/encoder/<signal>/<arm>/``.

    Per arm rather than per signal because both arms write ``metadata.json`` and
    ``foldN.head.json``, and a shared directory would have Arm B silently
    overwrite Arm A's -- the two results the whole ticket exists to compare.
    """
    return Path(args.models_dir) / args.signal / arm


def _joint_artefact_dir(args: argparse.Namespace, arm: str, signals: Sequence[str]) -> Path:
    """Where a joint run's artefacts live: ``models/encoder/joint<N>/<arm>/``.

    Not ``<signal>/<arm>/`` for any of the trained signals: there is no single
    signal this model belongs to, and putting it under one of six would either
    duplicate the shared ~440MB encoder across directories or leave five of six
    signal directories pointing at weights that live in a sixth (task 3
    instruction 7).
    """
    return Path(args.models_dir) / f"joint{len(signals)}" / arm


def _model_slug(label: str) -> str:
    """A label reduced to something safe to name a directory after."""
    return "".join(character if character.isalnum() else "-" for character in label).strip("-")


def _resolve_comparison_models(args: argparse.Namespace) -> list[tuple[str, str | None, str]]:
    """The ``(base_model, revision, label)`` triples one comparison run covers.

    Revisions are positional against the model list, and an empty list means
    "unpinned everywhere" -- the same unpinned-run warning the single-model
    commands print then applies to each. Labels default to the model's short
    name and must come out distinct, because the label is what separates two runs
    in one report; two runs sharing a name would be silently McNemar-compared
    against themselves.
    """
    revisions = list(args.revisions or [])
    if revisions and len(revisions) != len(args.base_models):
        raise TrainError(
            f"--revisions takes one entry per --base-models ({len(args.base_models)}) or none at "
            f"all; got {len(revisions)}"
        )
    if not revisions:
        revisions = [None] * len(args.base_models)

    labels = list(args.labels or []) or [display_model(model) for model in args.base_models]
    if len(labels) != len(args.base_models):
        raise TrainError(
            f"--labels takes one entry per --base-models ({len(args.base_models)}); "
            f"got {len(labels)}"
        )
    if len(set(labels)) != len(labels):
        raise TrainError(
            f"the run labels must be distinct, and these are not: {labels}. Two runs with one name "
            "cannot be told apart in a report, and the paired comparisons would compare a model "
            "against itself. Pass --labels explicitly"
        )
    return list(zip(args.base_models, revisions, labels, strict=True))


def _encoder_factory(args: argparse.Namespace, device: str):
    """A callable that loads a **fresh** encoder on ``device``.

    Arm B needs one per fold: reusing a single object would start each fold from
    the previous fold's fine-tuned weights, and the previous fold's training
    clusters are this fold's validation and test clusters. Nothing downstream
    would notice.
    """
    from .model import PooledEncoder

    def build():
        return PooledEncoder(
            args.base_model,
            revision=args.revision,
            pooling=args.pooling,
            max_seq_len=args.max_seq_len,
            device=device,
        ).load()

    return build


def _warn_if_unpinned(encoder) -> None:
    if not encoder.revision_pinned:
        print(
            f"warning: --revision was not given; recording the resolved commit "
            f"{encoder.revision}. Pass it explicitly to make this run repeatable.",
            file=sys.stderr,
        )


def run_smoke_cuda(args: argparse.Namespace) -> int:
    """The kernel-launch check on its own: no model, no network, no download."""
    report = check_device(args.device, cuda_required=args.require_cuda)
    for line in format_report(report):
        print(line)
    return 0


def run_smoke(args: argparse.Namespace) -> int:
    """Prove the machine can do this before asking it to do it for twenty minutes.

    Everything ``smoke-cuda`` does, and then the encoder: the 440MB download, the
    hub cache, and what the tokeniser actually does to casing.
    """
    for line in format_report(check_device(args.device)):
        print(line)
    device = resolve_device(args.device)

    from .model import PooledEncoder

    encoder = PooledEncoder(
        args.base_model,
        revision=args.revision,
        pooling=args.pooling,
        max_seq_len=args.max_seq_len,
        device=device,
    ).load()
    print(f"revision: {encoder.revision} (pinned: {encoder.revision_pinned})")
    print(f"tokeniser: {encoder.facts.to_dict()}")

    vectors = encoder.embed(
        [
            "I have burning pain when passing urine and I feel feverish.",
            "No temperature, I checked twice.",
        ]
    )
    print(f"embeddings: {tuple(vectors.shape)}, dtype {vectors.dtype}")
    if not encoder.revision_pinned:
        print(
            "warning: no --revision given. The bare model name can move, and an unpinned run is "
            "not reproducible; record this SHA and pass it next time.",
            file=sys.stderr,
        )
    return 0


def run_arm_a(args: argparse.Namespace) -> int:
    """Arm A end to end: embed, fit, select, score, write artefacts, write the report.

    ``check_device`` comes before the encoder is loaded, and that ordering is the
    point of it being a separate call: it sets ``CUBLAS_WORKSPACE_CONFIG``, which
    torch reads when it initialises CUDA, so setting it later is a silent no-op
    (DD11) -- and it launches a real kernel, which is cheaper to fail on than a
    440MB download is.
    """
    folds = load_folds(args.data_dir, args.signal, folds=args.folds)
    device_facts = check_device(args.device)
    device = device_facts["device"]
    for line in format_report(device_facts):
        print(line)

    encoder = _encoder_factory(args, device)()
    _warn_if_unpinned(encoder)

    config = _probe_config(args)
    run, results = run_probe(
        folds,
        encoder,
        signal=args.signal,
        config=config,
        cache_dir=args.cache_dir,
        device=device,
        progress=args.progress,
    )
    runs = [run]

    control_meta = None
    if not args.no_control:
        control_run, _ = run_probe(
            folds,
            encoder,
            signal=args.signal,
            config=config,
            cache_dir=args.cache_dir,
            device=device,
            shuffle_seed=args.shuffle_seed,
            progress=args.progress,
        )
        runs.append(control_run)
        control_meta = {
            "shuffle_seed": args.shuffle_seed,
            "permuted": "training labels only; validation and test left unpermuted",
            "run_name": control_run.name,
        }

    ruleset_hash = hash_ruleset_file(args.ruleset)
    metadata = build_metadata(
        signal=args.signal,
        arm=ARM_A_NAME,
        encoder_facts=encoder.to_dict(),
        config=config,
        device=device_facts,
        dataset={
            "dir": str(args.data_dir),
            "folds": args.folds,
            "generator_version": folds[0].train.generator_version,
            "generator_base_seed": args.seed,
            "split_salt": folds[0].train.split_salt,
            "dataset_seeds": [fold.train.stats.get("seed") for fold in folds],
            "examples_per_fold": {
                "train": len(folds[0].train),
                "val": len(folds[0].val),
                "test": len(folds[0].test),
            },
        },
        ruleset=str(args.ruleset),
        ruleset_hash=ruleset_hash,
        results=results,
        control=control_meta,
    )
    artefact_dir = _artefact_dir(args, ARM_A_NAME)
    for path in write_artefacts(
        artefact_dir, signal=args.signal, arm=ARM_A_NAME, metadata=metadata, results=results
    ):
        print(f"wrote {path}")

    # The baselines come *after* the artefacts are on disk, deliberately. They are
    # seconds of work but they are the one step here that can fail on a missing
    # dependency, and discarding a completed probe run because scikit-learn is not
    # installed would be a poor trade.
    if not args.no_baselines:
        runs[1:1] = run_all(folds, signal=args.signal, shuffle_seed=args.shuffle_seed)

    return _emit_report(
        runs,
        args,
        folds,
        stem=f"{args.signal}.{ARM_A_NAME}",
        extra={
            "arm": ARM_A_NAME,
            "base_model": args.base_model,
            "model_revision": encoder.revision,
            "revision_pinned": encoder.revision_pinned,
            "pooling": args.pooling,
            "max_seq_len": args.max_seq_len,
            "tokeniser_lowercases": encoder.facts.lowercases_input,
            "tokeniser_vocab_size": encoder.facts.vocab_size,
            "tokeniser_discards_casing": encoder.facts.discards_casing,
            "device": device,
            "probe_epochs": args.epochs,
            "train_seed": args.train_seed,
            "artefacts": str(artefact_dir),
        },
    )


def run_arm_b(args: argparse.Namespace) -> int:
    """Arm B end to end: fine-tune every fold, score test once, write everything.

    ``--dataset`` names the fold tree to load; ``--signals`` names the heads to
    train and evaluate against it, defaulting to every signal the loaded fold
    declares (task 3 instruction 1). A plain ``finetune --signal fever_present``
    call still resolves both to ``fever_present`` and takes the single-signal
    path below completely unchanged -- same stem, same artefact directory, same
    report -- which is what makes a single-signal run's numbers comparable to
    every report committed before this command could merge datasets at all.
    Anything else (a merged tree, or several ``--signals``) takes the joint path.
    """
    dataset_name = args.dataset or args.signal
    folds = load_folds(args.data_dir, dataset_name, folds=args.folds)
    signals = tuple(args.signals) if args.signals else tuple(folds[0].signals)

    if len(signals) == 1 and dataset_name == signals[0]:
        return _run_arm_b_single(args, folds)
    return _run_arm_b_joint(args, folds, dataset_name=dataset_name, signals=signals)


def _run_arm_b_single(args: argparse.Namespace, folds) -> int:
    """The single-signal path, unchanged since before ``--dataset``/``--signals`` existed.

    The order of the first three statements is the point of them being separate.
    ``check_device`` sets ``CUBLAS_WORKSPACE_CONFIG`` and then runs a real matmul
    *before* 440MB of weights are downloaded and before the first fold starts:
    torch reads that variable when it initialises CUDA, so setting it later is a
    silent no-op (DD11), and a wheel that cannot launch a kernel should cost ten
    seconds rather than twenty minutes.

    By default the report also carries Arm A and the baselines. That is not
    padding: the ticket's question is whether the encoder or the libraries are
    the bottleneck, which is a *paired* comparison between the arms on the
    ``null_ambiguous`` slice, and McNemar can only make it when both models are
    in one report. Arm A costs seconds once its embedding cache exists.
    """
    # Loaded before the encoder and before the first fold, so a bad path or a
    # labels file that no longer matches the ruleset costs a second rather than
    # an hour of GPU followed by a report with a hole in it.
    holdout = _load_holdout(args)
    # A CPU fine-tune is hours rather than the two minutes per fold the plan
    # budgets, so falling back to it silently would be a worse outcome than
    # stopping. Asking for it explicitly still works, either way round.
    cuda_required = not args.allow_cpu and args.device != "cpu"
    device_facts = check_device(args.device, cuda_required=cuda_required)
    device = device_facts["device"]
    for line in format_report(device_facts):
        print(line)

    factory = _encoder_factory(args, device)
    config = _finetune_config(args)
    weights_dir = None if args.no_weights else _artefact_dir(args, ARM_B_NAME) / "weights"

    runs: list = []

    # Arm A first, while an untouched encoder is loaded: it is the reference the
    # fine-tune is compared against, and it is also where the encoder's identity
    # for the sidecar comes from. Dropped immediately afterwards -- five 440MB
    # models plus optimiser state is what the memory budget is being spent on.
    reference = factory()
    _warn_if_unpinned(reference)
    encoder_facts = reference.to_dict()
    probe_header = {
        "model_revision": reference.revision,
        "revision_pinned": reference.revision_pinned,
        "tokeniser_lowercases": reference.facts.lowercases_input,
        "tokeniser_vocab_size": reference.facts.vocab_size,
        # A cased vocabulary behind a lowercasing tokeniser means patient casing
        # never reaches the model, whatever `arch_training.md` section 5 preserves
        # upstream. True for Bio_ClinicalBERT. Surfaced in the header because it
        # changes how any comparison against another encoder should be read.
        "tokeniser_discards_casing": reference.facts.discards_casing,
    }
    if not args.no_probe:
        probe_run, _ = run_probe(
            folds,
            reference,
            signal=args.signal,
            config=_probe_config_for_arm_b(args),
            cache_dir=args.cache_dir,
            device=device,
            progress=args.progress,
        )
        runs.append(probe_run)
    del reference

    run, results = run_finetune(
        folds,
        factory,
        signal=args.signal,
        config=config,
        weights_dir=weights_dir,
        holdout=holdout,
        progress=args.progress,
    )
    runs.append(run)

    control_meta = None
    if not args.no_control:
        control_run, _ = run_finetune(
            folds,
            factory,
            signal=args.signal,
            config=config,
            # The control's weights are never used for anything, so they are not
            # written: 2.2GB to record a model whose labels were nonsense.
            weights_dir=None,
            shuffle_seed=args.shuffle_seed,
            # Nor is the control scored on the holdout. README rule 3 asks for
            # the number of every *candidate* model to be recorded; a model
            # fitted on permuted labels is not a candidate, and 67 real
            # submissions are too few to spend on confirming that it is bad.
            holdout=None,
            progress=args.progress,
        )
        runs.append(control_run)
        control_meta = {
            "shuffle_seed": args.shuffle_seed,
            "permuted": "training labels only; validation and test left unpermuted",
            "run_name": control_run.name,
            "passing_looks_like": (
                "near-zero training loss (the model memorises the permutation) together with "
                "chance performance on the unpermuted test split. Either one alone is not the "
                "control passing; the per-fold train_loss_by_epoch in this sidecar is where the "
                "first half is read"
            ),
        }

    metadata = build_metadata(
        signal=args.signal,
        arm=ARM_B_NAME,
        encoder_facts=encoder_facts,
        config=config,
        device=device_facts,
        dataset={
            "dir": str(args.data_dir),
            "folds": args.folds,
            "generator_version": folds[0].train.generator_version,
            "generator_base_seed": args.seed,
            "split_salt": folds[0].train.split_salt,
            "dataset_seeds": [fold.train.stats.get("seed") for fold in folds],
            "examples_per_fold": {
                "train": len(folds[0].train),
                "val": len(folds[0].val),
                "test": len(folds[0].test),
            },
        },
        ruleset=str(args.ruleset),
        ruleset_hash=hash_ruleset_file(args.ruleset),
        results=results,
        control=control_meta,
    )
    artefact_dir = _artefact_dir(args, ARM_B_NAME)
    for path in write_artefacts(
        artefact_dir, signal=args.signal, arm=ARM_B_NAME, metadata=metadata, results=results
    ):
        print(f"wrote {path}")

    if not args.no_baselines:
        runs[0:0] = run_all(folds, signal=args.signal, shuffle_seed=args.shuffle_seed)

    return _emit_report(
        runs,
        args,
        folds,
        stem=f"{args.signal}.{ARM_B_NAME}",
        extra={
            "arm": ARM_B_NAME,
            "base_model": args.base_model,
            "pooling": args.pooling,
            "max_seq_len": args.max_seq_len,
            "device": device,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "warmup_ratio": args.warmup_ratio,
            "determinism": args.determinism,
            "train_seed": args.train_seed,
            "trainable": "all layers unfrozen",
            "holdout": _holdout_header(holdout),
            "validation_guided_decisions": list(VALIDATION_GUIDED_DECISIONS),
            "artefacts": str(artefact_dir),
            "weights": (
                "not written (--no-weights)"
                if weights_dir is None
                else f"{weights_dir} -- ~440MB per fold, not committed"
            ),
            **probe_header,
        },
    )


def _run_arm_b_joint(
    args: argparse.Namespace, folds, *, dataset_name: str, signals: Sequence[str]
) -> int:
    """The joint path: one encoder, several heads sharing it, one report per head.

    Arm A and the baselines do not ride along here, unlike the single-signal
    path. Both answer one question each -- a frozen probe or a bag-of-words
    model over one head -- and the ticket's paired comparison (A1 vs A3) is
    against a single-signal Arm B run made with the plain ``finetune`` path, not
    against a probe fitted beside the joint encoder. ``--no-probe`` and
    ``--no-baselines`` are effectively always on here.
    """
    holdout = _load_holdout(args)
    cuda_required = not args.allow_cpu and args.device != "cpu"
    device_facts = check_device(args.device, cuda_required=cuda_required)
    device = device_facts["device"]
    for line in format_report(device_facts):
        print(line)

    factory = _encoder_factory(args, device)
    config = _finetune_config(args)
    artefact_dir = _joint_artefact_dir(args, ARM_B_NAME, signals)
    weights_dir = None if args.no_weights else artefact_dir / "weights"

    reference = factory()
    _warn_if_unpinned(reference)
    encoder_facts = reference.to_dict()
    probe_header = {
        "model_revision": reference.revision,
        "revision_pinned": reference.revision_pinned,
        "tokeniser_lowercases": reference.facts.lowercases_input,
        "tokeniser_vocab_size": reference.facts.vocab_size,
        "tokeniser_discards_casing": reference.facts.discards_casing,
    }
    del reference

    runs_by_signal, results = run_finetune_joint(
        folds,
        factory,
        signals=signals,
        config=config,
        weights_dir=weights_dir,
        holdout=holdout,
        progress=args.progress,
    )

    control_meta = None
    control_runs_by_signal: dict | None = None
    if not args.no_control:
        control_runs_by_signal, _ = run_finetune_joint(
            folds,
            factory,
            signals=signals,
            config=config,
            # As with the single-signal path: a control's weights are never
            # used for anything, so they are not written.
            weights_dir=None,
            shuffle_seed=args.shuffle_seed,
            # Nor is the control scored on the holdout -- README rule 3 asks
            # for the number of every *candidate* model, and a model fitted on
            # permuted labels is not one.
            holdout=None,
            progress=args.progress,
        )
        control_meta = {
            "shuffle_seed": args.shuffle_seed,
            "permuted": "training labels only; validation and test left unpermuted",
            "run_name": next(iter(control_runs_by_signal.values())).name,
            "passing_looks_like": (
                "near-zero training loss (the model memorises the permutation) together with "
                "chance performance on the unpermuted test split, on every head at once -- one "
                "shared encoder, one control"
            ),
        }

    metadata = build_joint_metadata(
        signals=signals,
        arm=ARM_B_NAME,
        encoder_facts=encoder_facts,
        config=config,
        device=device_facts,
        dataset={
            "dir": str(args.data_dir),
            "name": dataset_name,
            "folds": args.folds,
            "generator_version": folds[0].train.generator_version,
            "generator_base_seed": args.seed,
            "split_salt": folds[0].train.split_salt,
            "dataset_seeds": [fold.train.stats.get("seed") for fold in folds],
            "examples_per_fold": {
                "train": len(folds[0].train),
                "val": len(folds[0].val),
                "test": len(folds[0].test),
            },
        },
        ruleset=str(args.ruleset),
        ruleset_hash=hash_ruleset_file(args.ruleset),
        results=results,
        control=control_meta,
    )
    for path in write_joint_artefacts(
        artefact_dir, arm=ARM_B_NAME, metadata=metadata, results=results
    ):
        print(f"wrote {path}")

    # One report per trained head (DD5): each is that signal's own view of the
    # one physical joint run, in the same report shape a single-signal Arm B
    # run produces, just under a stem that cannot collide with one.
    boot = BootstrapConfig(resamples=args.resamples, seed=args.bootstrap_seed, alpha=args.alpha)
    for signal in signals:
        signal_runs = [runs_by_signal[signal]]
        if control_runs_by_signal is not None:
            signal_runs.append(control_runs_by_signal[signal])
        per_signal_args = argparse.Namespace(**{**vars(args), "signal": signal})
        header = _header(
            per_signal_args,
            folds,
            extra={
                "dataset": dataset_name,
                "joint_signals": list(signals),
                "arm": ARM_B_NAME,
                "base_model": args.base_model,
                "pooling": args.pooling,
                "max_seq_len": args.max_seq_len,
                "device": device,
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "lr": args.lr,
                "warmup_ratio": args.warmup_ratio,
                "determinism": args.determinism,
                "train_seed": args.train_seed,
                "trainable": "all layers unfrozen, shared by every head",
                "holdout": _holdout_header(holdout),
                "validation_guided_decisions": list(VALIDATION_GUIDED_DECISIONS),
                "artefacts": str(artefact_dir),
                "weights": (
                    "not written (--no-weights)"
                    if weights_dir is None
                    else f"{weights_dir} -- ~440MB shared per fold, not committed"
                ),
                **probe_header,
            },
        )
        report = build_report(
            signal_runs,
            header=header,
            boot=boot,
            checks=_checks(folds),
            fragments=_fragment_provenance(folds),
        )
        json_path, markdown_path = write_report(
            report,
            args.report_dir,
            stem=f"{signal}.{dataset_name}.{ARM_B_NAME}",
            markdown=not args.no_markdown,
            fragment_rows=args.fragment_rows,
        )
        print(f"wrote {json_path}")
        if markdown_path is not None:
            print(f"wrote {markdown_path}")
    return 0


def run_compare_models(args: argparse.Namespace) -> int:
    """Arm B over several encoders, against the same folds, in one report.

    One report rather than one per encoder, and that is the whole point of the
    command. ``compare_models`` runs its paired McNemar tests between the runs it
    finds in a single report, and the 2026-08-09 decisive interval was
    [79.1, 88.0] with a per-fold sd of 4.4% -- two independently-written reports
    would have overlapping intervals at any difference this comparison could
    plausibly produce, and nothing paired to fall back on. Same folds, same
    seeds, same decision-rule procedure, compared on the examples the models
    disagree about.

    The negative control is **off** by default here, unlike every other command.
    It is per-encoder work, it would triple the cost of an already 3x sweep, and
    the question it answers -- can this pipeline learn from permuted labels --
    was answered by the run that motivated this one. ``--control`` turns it back
    on; the report says which was done either way.
    """
    models = _resolve_comparison_models(args)
    folds = load_folds(args.data_dir, args.signal, folds=args.folds)
    holdout = _load_holdout(args)
    cuda_required = not args.allow_cpu and args.device != "cpu"
    device_facts = check_device(args.device, cuda_required=cuda_required)
    device = device_facts["device"]
    for line in format_report(device_facts):
        print(line)

    runs: list = []
    encoders: list[dict] = []

    for base_model, revision, label in models:
        print(f"\n=== {label} ({base_model}) ===", flush=True)
        # A per-model copy of the parsed arguments, so every config builder below
        # stays the one the single-model commands use. Rebuilding the configs by
        # hand here is how the two paths drift into disagreeing about a default.
        model_args = argparse.Namespace(**vars(args))
        model_args.base_model = base_model
        model_args.revision = revision

        factory = _encoder_factory(model_args, device)
        reference = factory()
        _warn_if_unpinned(reference)
        facts = reference.to_dict()
        encoders.append({"label": label, **facts})
        tokeniser = facts.get("tokeniser") or {}
        if tokeniser.get("discards_casing"):
            print(
                f"note: {label} lowercases its input into a cased vocabulary "
                f"({tokeniser['vocab_size']} entries), so patient casing reaches the model as "
                "subword fragmentation rather than as signal.",
                file=sys.stderr,
            )

        if args.with_probe:
            probe_run, _ = run_probe(
                folds,
                reference,
                signal=args.signal,
                config=_probe_config_for_arm_b(model_args),
                cache_dir=args.cache_dir,
                device=device,
                label=label,
                progress=args.progress,
            )
            runs.append(probe_run)
        del reference

        arm = f"{ARM_B_NAME}__{_model_slug(label)}"
        weights_dir = None if args.no_weights else Path(args.models_dir) / args.signal / arm
        config = _finetune_config(model_args)
        run, results = run_finetune(
            folds,
            factory,
            signal=args.signal,
            config=config,
            weights_dir=None if weights_dir is None else weights_dir / "weights",
            holdout=holdout,
            label=label,
            progress=args.progress,
        )
        runs.append(run)

        if args.control:
            control_run, _ = run_finetune(
                folds,
                factory,
                signal=args.signal,
                config=config,
                weights_dir=None,
                shuffle_seed=args.shuffle_seed,
                holdout=None,
                label=label,
                progress=args.progress,
            )
            runs.append(control_run)

        metadata = build_metadata(
            signal=args.signal,
            arm=arm,
            encoder_facts=facts,
            config=config,
            device=device_facts,
            dataset={
                "dir": str(args.data_dir),
                "folds": args.folds,
                "generator_version": folds[0].train.generator_version,
                "generator_base_seed": args.seed,
                "split_salt": folds[0].train.split_salt,
                "dataset_seeds": [fold.train.stats.get("seed") for fold in folds],
                "examples_per_fold": {
                    "train": len(folds[0].train),
                    "val": len(folds[0].val),
                    "test": len(folds[0].test),
                },
            },
            ruleset=str(args.ruleset),
            ruleset_hash=hash_ruleset_file(args.ruleset),
            results=results,
            control=None,
        )
        for path in write_artefacts(
            Path(args.models_dir) / args.signal / arm,
            signal=args.signal,
            arm=arm,
            metadata=metadata,
            results=results,
        ):
            print(f"wrote {path}")

    if not args.no_baselines:
        # Once, not once per encoder: the baselines do not depend on which
        # transformer is being compared, and three identical `tfidf_logreg` rows
        # would add nine meaningless McNemar comparisons to the report.
        runs[0:0] = run_all(folds, signal=args.signal, shuffle_seed=args.shuffle_seed)

    return _emit_report(
        runs,
        args,
        folds,
        stem=f"{args.signal}.model_comparison",
        extra={
            "arm": ARM_B_NAME,
            "comparison": [
                {
                    "label": label,
                    "base_model": encoder["base_model"],
                    "revision": encoder["revision"],
                    "revision_pinned": encoder["revision_pinned"],
                    "vocab_size": (encoder.get("tokeniser") or {}).get("vocab_size"),
                    "lowercases_input": (encoder.get("tokeniser") or {}).get("lowercases_input"),
                    "discards_casing": (encoder.get("tokeniser") or {}).get("discards_casing"),
                }
                for (_, _, label), encoder in zip(models, encoders, strict=True)
            ],
            "pooling": args.pooling,
            "max_seq_len": args.max_seq_len,
            "device": device,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "warmup_ratio": args.warmup_ratio,
            "determinism": args.determinism,
            "train_seed": args.train_seed,
            "arm_a_included": args.with_probe,
            "holdout": _holdout_header(holdout),
            "negative_control": "run per encoder" if args.control else "not run (--control is off)",
            "artefacts": str(Path(args.models_dir) / args.signal),
        },
    )


def _add_report_args(parser: argparse.ArgumentParser) -> None:
    """Arguments shared by every command that writes an evaluation report."""
    parser.add_argument("--signal", default=DEFAULT_SIGNAL)
    parser.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--ruleset", type=Path, default=DEFAULT_RULESET)
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        default=7,
        help="seed for the permuted-label negative control",
    )
    parser.add_argument("--resamples", type=int, default=BootstrapConfig.resamples)
    parser.add_argument("--bootstrap-seed", type=int, default=BootstrapConfig.seed)
    parser.add_argument("--alpha", type=float, default=BootstrapConfig.alpha)
    parser.add_argument(
        "--fragment-rows",
        type=int,
        default=40,
        help="how many rows of the per-fragment error table the markdown prints inline; "
        "the JSON always holds every fragment",
    )
    parser.add_argument("--no-markdown", action="store_true")


def _add_holdout_args(parser: argparse.ArgumentParser) -> None:
    """The real-text holdout, for the commands that fine-tune an encoder.

    Not on ``baselines`` or ``probe``. Arm A scores from a cached embedding
    matrix keyed to the synthetic splits, and the baselines are fitted on
    tokens, so neither has a forward pass to hand these 67 submissions without
    new machinery -- and a bag-of-words number on real text is not what the set
    is for. Arm B carries the encoder that would eventually be deployed, so it
    is where the question is worth asking.
    """
    parser.add_argument(
        "--holdout",
        type=Path,
        default=DEFAULT_HOLDOUT_PATH,
        help="the realistic held-out labels TSV. Scored once per fold model, after the margin "
        "has been selected on validation and after the synthetic test split has been scored, so "
        "that it cannot select anything. A missing file is an error, not a silent skip",
    )
    parser.add_argument(
        "--no-holdout",
        action="store_true",
        help="skip the real-text holdout. The report then says the check was skipped rather "
        "than reporting nothing, which is the difference between a run that meant to skip it and "
        "one whose path was wrong",
    )


def _add_encoder_args(parser: argparse.ArgumentParser) -> None:
    """Arguments describing which encoder to load, and how."""
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument(
        "--revision",
        default=None,
        help="the base model's commit SHA. The bare name emilyalsentzer/Bio_ClinicalBERT can "
        "move, so leaving this unset makes a run unreproducible; the resolved SHA is recorded "
        "either way, and a warning is printed when it was not pinned.",
    )
    parser.add_argument("--pooling", choices=POOLING_MODES, default="mean")
    parser.add_argument("--max-seq-len", type=int, default=256)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.encoder_training",
        description="Generate cross-validation folds and evaluate models against them.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate-folds", help="generate all K folds' three splits")
    generate.add_argument("--signal", default=DEFAULT_SIGNAL)
    generate.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--split-salt", default=DEFAULT_FOLD_SALT)
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--ruleset", type=Path, default=DEFAULT_RULESET)
    generate.add_argument("--out-dir", type=Path, default=DEFAULT_DATA_DIR)
    for split, default in DEFAULT_COUNTS.items():
        generate.add_argument(f"--{split}-count", type=int, default=default)
    generate.set_defaults(handler=generate_folds)

    merge = subparsers.add_parser(
        "merge-folds",
        help="merge the per-signal fold trees into one multi-head tree",
    )
    merge.add_argument(
        "--signals",
        nargs="+",
        default=list(DEFAULT_SIGNALS),
        help="the signals to merge. Defaults to the six with fragment libraries; the ruleset's "
        "seventh send_to_encoder signal, recent_uti_present, has none and therefore no head",
    )
    merge.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    merge.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    merge.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="where the merged tree goes. Defaults to --data-dir, so the merged files sit beside "
        "the trees they came from under the same naming convention",
    )
    merge.add_argument(
        "--name",
        default=None,
        help="the merged tree's name, used in the signal position of the fold filename so that "
        "load_folds reads it with no special case. Defaults to joint<N>",
    )
    merge.set_defaults(handler=run_merge_folds)

    baselines = subparsers.add_parser(
        "baselines", help="fit the baselines and controls, and write the report"
    )
    _add_report_args(baselines)
    baselines.set_defaults(handler=run_baselines)

    smoke_cuda = subparsers.add_parser(
        "smoke-cuda",
        help="run a real kernel on the training device; no model, no network. Run this first",
    )
    smoke_cuda.add_argument("--device", default="auto")
    smoke_cuda.add_argument(
        "--require-cuda",
        action="store_true",
        help="exit non-zero if the run would fall back to the CPU",
    )
    smoke_cuda.set_defaults(handler=run_smoke_cuda)

    smoke = subparsers.add_parser(
        "smoke", help="everything smoke-cuda does, plus loading the encoder and its tokeniser"
    )
    _add_encoder_args(smoke)
    smoke.add_argument("--device", default="auto")
    smoke.set_defaults(handler=run_smoke)

    probe = subparsers.add_parser("probe", help="Arm A: the frozen probe, across every fold")
    _add_report_args(probe)
    _add_encoder_args(probe)
    probe.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    probe.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    probe.add_argument("--device", default="auto")
    probe.add_argument("--epochs", type=int, default=ProbeConfig.epochs)
    probe.add_argument("--batch-size", type=int, default=ProbeConfig.batch_size)
    probe.add_argument("--lr", type=float, default=ProbeConfig.lr)
    probe.add_argument("--weight-decay", type=float, default=ProbeConfig.weight_decay)
    probe.add_argument(
        "--train-seed",
        type=int,
        default=ProbeConfig.seed,
        help="seed for the probe's initialisation and batch order; distinct from --seed, which "
        "is the generator's",
    )
    probe.add_argument("--embed-batch-size", type=int, default=ProbeConfig.embed_batch_size)
    probe.add_argument(
        "--no-baselines",
        action="store_true",
        help="omit the baselines from the report. They are included by default because the "
        "ticket's question -- does the encoder beat bag-of-words on null_ambiguous -- is a paired "
        "one, and McNemar needs both models in the same report to answer it. Needs scikit-learn; "
        "the head artefacts are written before this step so a missing wheel costs only the "
        "comparison",
    )
    probe.add_argument(
        "--no-control",
        action="store_true",
        help="skip the shuffled-label negative control. It doubles the run time and is the only "
        "thing that says the rest of the numbers mean anything, so skip it only when iterating",
    )
    probe.add_argument("--progress", action="store_true", help="print embedding progress per batch")
    probe.set_defaults(handler=run_arm_a)

    finetune = subparsers.add_parser(
        "finetune", help="Arm B: unfreeze every layer and fine-tune, across every fold"
    )
    _add_report_args(finetune)
    _add_encoder_args(finetune)
    _add_holdout_args(finetune)
    finetune.add_argument(
        "--dataset",
        default=None,
        help="the fold tree to load, i.e. the signal position of the fold filename. Defaults to "
        "--signal, which is today's behaviour. Pass a merged tree's name (e.g. joint6, from "
        "merge-folds) to train jointly; --signals then names which of its heads to train",
    )
    finetune.add_argument(
        "--signals",
        nargs="+",
        default=None,
        help="the heads to train and evaluate against --dataset. Defaults to every signal the "
        "loaded fold declares, which is --signal alone on an unmerged tree and every merged "
        "signal on one from merge-folds. Passing the same single value as --signal and --dataset "
        "takes the unchanged single-signal path; anything else takes the joint path, which skips "
        "Arm A and the baselines (both are single-head machinery) and writes one report per head",
    )
    finetune.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    finetune.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    finetune.add_argument("--device", default="auto")
    finetune.add_argument("--epochs", type=int, default=FineTuneConfig.epochs)
    finetune.add_argument("--batch-size", type=int, default=FineTuneConfig.batch_size)
    finetune.add_argument("--lr", type=float, default=FineTuneConfig.lr)
    finetune.add_argument("--weight-decay", type=float, default=FineTuneConfig.weight_decay)
    finetune.add_argument("--warmup-ratio", type=float, default=FineTuneConfig.warmup_ratio)
    finetune.add_argument("--max-grad-norm", type=float, default=FineTuneConfig.max_grad_norm)
    finetune.add_argument("--eval-batch-size", type=int, default=FineTuneConfig.eval_batch_size)
    finetune.add_argument(
        "--embed-batch-size",
        type=int,
        default=ProbeConfig.embed_batch_size,
        help="batch size for Arm A's embedding pass, when Arm A rides along in this report",
    )
    finetune.add_argument(
        "--determinism",
        choices=DETERMINISM_MODES,
        default=FineTuneConfig.determinism,
        help="how hard to insist on deterministic kernels. 'strict' raises when an op has no "
        "deterministic implementation, 'warn' prints and continues, 'off' disables the check. "
        "Whichever ran is recorded in the metadata sidecar",
    )
    finetune.add_argument(
        "--train-seed",
        type=int,
        default=FineTuneConfig.seed,
        help="seed for the head's initialisation and the batch order; distinct from --seed, "
        "which is the generator's",
    )
    finetune.add_argument(
        "--allow-cpu",
        action="store_true",
        help="permit a CPU fine-tune. Off by default because a silent fallback to the CPU turns "
        "a ten-minute sweep into an overnight one; --device cpu says the same thing explicitly",
    )
    finetune.add_argument(
        "--no-weights",
        action="store_true",
        help="do not write the fine-tuned encoders. Each is ~440MB and none is committed; they "
        "are regenerable in about two minutes per fold from the pinned seeds",
    )
    finetune.add_argument(
        "--no-probe",
        action="store_true",
        help="omit Arm A from the report. It is included by default because 'does fine-tuning "
        "beat the frozen probe on null_ambiguous' is the paired comparison the ticket turns on, "
        "and it costs seconds once the embedding cache exists",
    )
    finetune.add_argument(
        "--no-baselines",
        action="store_true",
        help="omit the baselines from the report. Needs scikit-learn; the artefacts are written "
        "before this step so a missing wheel costs only the comparison",
    )
    finetune.add_argument(
        "--no-control",
        action="store_true",
        help="skip the shuffled-label negative control. It doubles the run time and is the only "
        "thing that says the rest of the numbers mean anything, so skip it only when iterating",
    )
    finetune.add_argument(
        "--progress", action="store_true", help="print per-epoch training loss and validation score"
    )
    finetune.set_defaults(handler=run_arm_b)

    compare = subparsers.add_parser(
        "compare-models",
        help="Arm B over several base models, against the same folds, in one report",
    )
    _add_report_args(compare)
    _add_holdout_args(compare)
    compare.add_argument(
        "--base-models",
        nargs="+",
        default=list(DEFAULT_COMPARISON_MODELS),
        help="the encoders to compare. Each must be a BERT-base-sized model (hidden size 768); "
        "anything else is rejected at load time rather than silently reshaping the head",
    )
    compare.add_argument(
        "--revisions",
        nargs="*",
        default=None,
        help="commit SHAs, one per --base-models entry, or none at all. An unpinned comparison is "
        "not reproducible and each unpinned model prints the usual warning",
    )
    compare.add_argument(
        "--labels",
        nargs="*",
        default=None,
        help="what each encoder is called in the report and its artefact directory. Defaults to "
        "the model's short name, and must be distinct",
    )
    compare.add_argument("--pooling", choices=POOLING_MODES, default="mean")
    compare.add_argument("--max-seq-len", type=int, default=256)
    compare.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    compare.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    compare.add_argument("--device", default="auto")
    compare.add_argument("--epochs", type=int, default=FineTuneConfig.epochs)
    compare.add_argument("--batch-size", type=int, default=FineTuneConfig.batch_size)
    compare.add_argument("--lr", type=float, default=FineTuneConfig.lr)
    compare.add_argument("--weight-decay", type=float, default=FineTuneConfig.weight_decay)
    compare.add_argument("--warmup-ratio", type=float, default=FineTuneConfig.warmup_ratio)
    compare.add_argument("--max-grad-norm", type=float, default=FineTuneConfig.max_grad_norm)
    compare.add_argument("--eval-batch-size", type=int, default=FineTuneConfig.eval_batch_size)
    compare.add_argument("--embed-batch-size", type=int, default=ProbeConfig.embed_batch_size)
    compare.add_argument(
        "--determinism", choices=DETERMINISM_MODES, default=FineTuneConfig.determinism
    )
    compare.add_argument("--train-seed", type=int, default=FineTuneConfig.seed)
    compare.add_argument("--allow-cpu", action="store_true")
    compare.add_argument(
        "--no-weights",
        action="store_true",
        help="do not write the fine-tuned encoders. ~440MB per fold per model, so a three-model "
        "sweep writes ~6.6GB; none of it is committed and all of it is regenerable",
    )
    compare.add_argument(
        "--with-probe",
        action="store_true",
        help="also run Arm A on each encoder. Off by default: it doubles the number of runs in "
        "the report and every extra run adds a row to each paired-comparison table, and the "
        "frozen-vs-fine-tuned question is already settled",
    )
    compare.add_argument(
        "--control",
        action="store_true",
        help="run the shuffled-label negative control for each encoder. Off by default here "
        "alone: it is per-encoder work that would triple an already 3x sweep, and it answers a "
        "question the run that motivated this comparison already answered",
    )
    compare.add_argument(
        "--no-baselines",
        action="store_true",
        help="omit the baselines. They are fitted once rather than once per encoder, since they "
        "do not depend on which transformer is in the report",
    )
    compare.add_argument("--progress", action="store_true")
    compare.set_defaults(handler=run_compare_models)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (
        CudaSmokeError,
        DatasetError,
        EmbedError,
        HoldoutError,
        MergeError,
        TrainError,
    ) as error:
        # The failures a caller can actually fix: an untrustworthy dataset, an
        # encoder that cannot be identified well enough to key a cache, a
        # holdout file that does not match the ruleset, per-signal trees that
        # cannot honestly be merged, and a misconfigured run.
        # A one-line message beats a traceback for all of them.
        # Torch's own errors are deliberately left to propagate: a kernel-launch
        # failure is diagnosed from the stack, not from a summary.
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ModuleNotFoundError as error:
        # The one class of import failure worth translating: torch, transformers
        # and scikit-learn all live in requirements-ml.txt, which nothing
        # installs by default and CI never installs at all.
        print(
            f"error: {error}. The baselines and both arms need the ML dependencies: "
            "pip install -r requirements-ml.txt (read its header first if this machine has a "
            "Blackwell GPU)",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
