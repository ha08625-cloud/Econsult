"""Command-line entry point for the synthetic fragment recombiner.

    python -m scripts.synthetic_data \\
        --manifest data/synthetic/manifest.json \\
        --ruleset  data/uti1.json \\
        --signal   fever_present \\
        --split    train \\
        --count    10000 \\
        --seed     42 \\
        --dist     null=0.60,false=0.25,true=0.15 \\
        --null-ambiguous-ratio 0.5 \\
        --fragment-counts 2=0.5,3=0.5 \\
        --out      data/synthetic/generated/fever_present.train.jsonl

Same seed + same libraries + same flags produces byte-identical output. That
is why the writer pins ``ensure_ascii=False`` and ``\\n`` line endings rather
than taking the platform default: a dataset that differs by line ending
between a developer's machine and CI is not reproducible in any useful sense.

Every run also writes ``<out>.stats.json``.

``--lint`` is a second, generation-free mode: it loads the same libraries and
prints the hedge-marker, near-duplicate and filler-purity reports. It reads
nothing but the manifest, so ``--ruleset``, ``--split``, ``--count`` and
``--out`` are neither required nor used.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .lint import render_report
from .manifest import ManifestError, load_fragments
from .recombine import (
    DEFAULT_NULL_AMBIGUOUS_RATIO,
    DistributionError,
    PoolError,
    PoolExhaustedError,
    build_pools,
    build_stats,
    generate,
    parse_distribution,
    parse_fragment_counts,
    to_record,
)
from .ruleset import RulesetError, load_and_validate

DEFAULT_MANIFEST = Path("data/synthetic/manifest.json")
DEFAULT_RULESET = Path("data/uti1.json")
DEFAULT_DIST = "null=0.60,false=0.25,true=0.15"
DEFAULT_FRAGMENT_COUNTS_ARG = "2=0.5,3=0.5"


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError(f"must not be negative: {raw}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.synthetic_data",
        description="Recombine synthetic fragments into a label-first JSONL training set.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ruleset", type=Path, default=DEFAULT_RULESET)
    parser.add_argument("--signal", default="fever_present")
    # Required for generation but meaningless for --lint, so requiredness is
    # enforced in main() rather than by argparse.
    parser.add_argument("--split", choices=["train", "val", "test"])
    parser.add_argument("--count", type=_non_negative_int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--dist",
        default=DEFAULT_DIST,
        help="label distribution, e.g. 'null=0.60,false=0.25,true=0.15'; must sum to 1.0",
    )
    parser.add_argument(
        "--null-ambiguous-ratio",
        type=float,
        default=DEFAULT_NULL_AMBIGUOUS_RATIO,
        help="share of null examples carrying a fever-adjacent fragment rather than none",
    )
    parser.add_argument(
        "--fragment-counts",
        default=DEFAULT_FRAGMENT_COUNTS_ARG,
        help="how many fragments an example holds, as a weighted mix, e.g. '2=0.5,3=0.5'; "
        "must sum to 1.0, every count at least 2, and the largest count may not exceed "
        "the number of filler libraries. The mix is applied identically to every label "
        "mode by design -- a count that varied by label would make text length a proxy "
        "for the label",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--lint",
        action="store_true",
        help="report library health instead of generating: hedge markers, "
        "cross-split near-duplicates and fever language in filler",
    )
    return parser


#: Flags that generation cannot run without.
_GENERATION_REQUIRED = ("split", "count", "out")


def write_outputs(out_path: Path, examples, stats: dict) -> Path:
    """Write the JSONL and its stats sidecar, returning the sidecar path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for example in examples:
            handle.write(json.dumps(to_record(example), ensure_ascii=False) + "\n")

    stats_path = out_path.parent / (out_path.name + ".stats.json")
    with stats_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    return stats_path


def run_lint(args: argparse.Namespace) -> int:
    """Print the library health reports. Never modifies a library."""
    # check_cells=False: the empty-cell guard is generation's, and a lint that
    # aborts on unbalanced libraries cannot report on unbalanced libraries.
    for line in render_report(load_fragments(args.manifest, check_cells=False)):
        print(line)
    return 0


def run(args: argparse.Namespace) -> int:
    # Fail fast on configuration before doing any work: a missing signal or a
    # malformed distribution discovered after a 10,000-example run is a wasted
    # run, and the project treats config drift as an error rather than
    # something to tolerate.
    distribution = parse_distribution(args.dist)
    fragment_counts = parse_fragment_counts(args.fragment_counts)
    load_and_validate(args.ruleset, args.signal)

    fragments = load_fragments(args.manifest)
    pools = build_pools(fragments, args.signal, args.split)

    examples, telemetry = generate(
        pools,
        count=args.count,
        seed=args.seed,
        distribution=distribution,
        null_ambiguous_ratio=args.null_ambiguous_ratio,
        fragment_counts=fragment_counts,
    )
    stats = build_stats(
        examples,
        telemetry=telemetry,
        fragments=fragments,
        pools=pools,
        count=args.count,
        seed=args.seed,
        distribution=distribution,
        null_ambiguous_ratio=args.null_ambiguous_ratio,
        fragment_counts=fragment_counts,
        manifest_path=str(args.manifest),
        ruleset_path=str(args.ruleset),
    )
    stats_path = write_outputs(args.out, examples, stats)

    realised = stats["realised"]
    print(
        f"wrote {realised['count']} examples to {args.out} "
        f"(true={realised['labels']['true']}, false={realised['labels']['false']}, "
        f"null={realised['labels']['null']}, "
        f"rejections={stats['duplicate_rejections']}); stats at {stats_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.lint:
        missing = [f"--{name}" for name in _GENERATION_REQUIRED if getattr(args, name) is None]
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
    try:
        return run_lint(args) if args.lint else run(args)
    except (
        DistributionError,
        ManifestError,
        PoolError,
        PoolExhaustedError,
        RulesetError,
        json.JSONDecodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
