"""Command-line entry point for encoder training and evaluation.

Four subcommands.

    python -m scripts.encoder_training generate-folds --folds 5

Fifteen runs of the generator -- three splits for each of five folds -- written
under one directory by the naming convention :mod:`.dataset` reads back. Scripted
rather than documented because the fifteen runs have to agree on the fold count,
the salt and the seed derivation, and a shell loop that gets one of those wrong
produces a directory that loads cleanly and evaluates nonsense.

    python -m scripts.encoder_training baselines --folds 5

Fits the three baselines and the shuffled-label controls across every fold and
writes the evaluation report. This needs scikit-learn (``requirements-ml.txt``);
generation does not.

    python -m scripts.encoder_training smoke

Loads the encoder, prints what the device and tokeniser actually are, and runs a
real kernel. **Run this before anything else on a new machine.** It exists
because ``torch.cuda.is_available()`` returning ``True`` proves nothing on an
architecture the installed wheel was not built for: the import succeeds and the
first kernel launch fails. Ten seconds here saves an afternoon.

    python -m scripts.encoder_training probe --folds 5

Arm A. Embeds every fold's splits once (cached), fits the ``Linear(768, 3)``
probe, selects each fold's margin on its own validation split, scores test,
writes the head artefacts and metadata sidecar, and writes the evaluation report
-- with the baselines included in the same report by default, because "does
ClinicalBERT beat bag-of-words on ``null_ambiguous``" is a paired question and
McNemar can only answer it when both models are in one report.

No command touches ``app/``, and nothing in ``app/`` imports this. The dependency
runs one way, and ``tests/test_wiring.py`` asserts it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.synthetic_data.__main__ import DEFAULT_FOLD_SALT
from scripts.synthetic_data.__main__ import main as generate_main

from .baselines import run_all
from .dataset import SPLITS, DatasetError, fold_dataset_path, load_folds
from .embed import POOLING_MODES, EmbedError
from .report import BootstrapConfig, build_report, write_report
from .ruleset_hash import hash_ruleset_file

# `train` imports torch inside its functions, exactly as `baselines` does with
# scikit-learn, so importing it here costs nothing on a machine with no ML
# wheels and keeps this whole CLI importable in CI. `model` is the one module
# that cannot avoid a module-level torch import, so it stays lazy below.
from .train import (
    ARM_A_NAME,
    DEFAULT_BASE_MODEL,
    ProbeConfig,
    TrainError,
    build_metadata,
    device_report,
    ensure_deterministic_env,
    resolve_device,
    run_probe,
    write_artefacts,
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


def run_baselines(args: argparse.Namespace) -> int:
    folds = load_folds(args.data_dir, args.signal, folds=args.folds)
    runs = run_all(folds, signal=args.signal, shuffle_seed=args.shuffle_seed)
    boot = BootstrapConfig(resamples=args.resamples, seed=args.bootstrap_seed, alpha=args.alpha)
    report = build_report(runs, header=_header(args, folds), boot=boot, checks=_checks(folds))
    json_path, markdown_path = write_report(
        report,
        args.report_dir,
        stem=f"{args.signal}.baselines",
        markdown=not args.no_markdown,
        fragment_rows=args.fragment_rows,
    )
    print(f"wrote {json_path}")
    if markdown_path is not None:
        print(f"wrote {markdown_path}")
    return 0


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


def run_smoke(args: argparse.Namespace) -> int:
    """Prove the machine can do this before asking it to do it for twenty minutes."""
    from .model import PooledEncoder

    ensure_deterministic_env()
    device = resolve_device(args.device)
    report = device_report(device)
    for key, value in report.items():
        print(f"{key}: {value}")

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

    ``ensure_deterministic_env`` runs before ``model`` is imported, and that
    ordering is the point of it being a separate call: torch reads
    ``CUBLAS_WORKSPACE_CONFIG`` when it initialises CUDA, so setting it after the
    import is a silent no-op (DD11).
    """
    ensure_deterministic_env()

    from .model import PooledEncoder

    folds = load_folds(args.data_dir, args.signal, folds=args.folds)
    device = resolve_device(args.device)
    device_facts = device_report(device)
    print(f"device: {device_facts}")

    encoder = PooledEncoder(
        args.base_model,
        revision=args.revision,
        pooling=args.pooling,
        max_seq_len=args.max_seq_len,
        device=device,
    ).load()
    if not encoder.revision_pinned:
        print(
            f"warning: --revision was not given; recording the resolved commit "
            f"{encoder.revision}. Pass it explicitly to make this run repeatable.",
            file=sys.stderr,
        )

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
    artefact_dir = Path(args.models_dir) / args.signal
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

    boot = BootstrapConfig(resamples=args.resamples, seed=args.bootstrap_seed, alpha=args.alpha)
    header = _header(
        args,
        folds,
        extra={
            "arm": ARM_A_NAME,
            "base_model": args.base_model,
            "model_revision": encoder.revision,
            "revision_pinned": encoder.revision_pinned,
            "pooling": args.pooling,
            "max_seq_len": args.max_seq_len,
            "tokeniser_lowercases": encoder.facts.lowercases_input,
            "device": device,
            "probe_epochs": args.epochs,
            "train_seed": args.train_seed,
            "artefacts": str(artefact_dir),
        },
    )
    report = build_report(runs, header=header, boot=boot, checks=_checks(folds))
    json_path, markdown_path = write_report(
        report,
        args.report_dir,
        stem=f"{args.signal}.{ARM_A_NAME}",
        markdown=not args.no_markdown,
        fragment_rows=args.fragment_rows,
    )
    print(f"wrote {json_path}")
    if markdown_path is not None:
        print(f"wrote {markdown_path}")
    return 0


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

    baselines = subparsers.add_parser(
        "baselines", help="fit the baselines and controls, and write the report"
    )
    _add_report_args(baselines)
    baselines.set_defaults(handler=run_baselines)

    smoke = subparsers.add_parser(
        "smoke", help="load the encoder and run a real kernel; run this first on a new machine"
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (DatasetError, EmbedError, TrainError) as error:
        # The three failures a caller can actually fix: an untrustworthy dataset,
        # an encoder that cannot be identified well enough to key a cache, and a
        # misconfigured run. A one-line message beats a traceback for all three.
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
