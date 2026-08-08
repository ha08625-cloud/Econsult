"""Command-line entry point for encoder training and evaluation.

Two subcommands so far.

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

Neither command touches ``app/``, and nothing in ``app/`` imports this. The
dependency runs one way, and ``tests/test_wiring.py`` asserts it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.synthetic_data.__main__ import DEFAULT_FOLD_SALT
from scripts.synthetic_data.__main__ import main as generate_main

from .baselines import run_all
from .dataset import SPLITS, DatasetError, fold_dataset_path, load_folds
from .report import BootstrapConfig, build_report, write_report
from .ruleset_hash import hash_ruleset_file

DEFAULT_SIGNAL = "fever_present"
DEFAULT_FOLDS = 5
DEFAULT_DATA_DIR = Path("data/synthetic/generated/folds")
DEFAULT_REPORT_DIR = Path("reports/encoder_training")
DEFAULT_MANIFEST = Path("data/synthetic/manifest.json")
DEFAULT_RULESET = Path("data/uti1.json")

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


def _header(args: argparse.Namespace, folds) -> dict:
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
    baselines.add_argument("--signal", default=DEFAULT_SIGNAL)
    baselines.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    baselines.add_argument("--seed", type=int, default=42)
    baselines.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    baselines.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    baselines.add_argument("--ruleset", type=Path, default=DEFAULT_RULESET)
    baselines.add_argument(
        "--shuffle-seed",
        type=int,
        default=7,
        help="seed for the permuted-label negative control",
    )
    baselines.add_argument("--resamples", type=int, default=BootstrapConfig.resamples)
    baselines.add_argument("--bootstrap-seed", type=int, default=BootstrapConfig.seed)
    baselines.add_argument("--alpha", type=float, default=BootstrapConfig.alpha)
    baselines.add_argument(
        "--fragment-rows",
        type=int,
        default=40,
        help="how many rows of the per-fragment error table the markdown prints inline; "
        "the JSON always holds every fragment",
    )
    baselines.add_argument("--no-markdown", action="store_true")
    baselines.set_defaults(handler=run_baselines)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except DatasetError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ModuleNotFoundError as error:
        # The one import failure worth translating: scikit-learn lives in
        # requirements-ml.txt, which nothing installs by default and CI never
        # installs at all.
        print(
            f"error: {error}. The baselines need the ML dependencies: "
            "pip install -r requirements-ml.txt",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
