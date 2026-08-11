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

``--folds K --fold i`` is the third mode, and it is opt-in: without ``--folds``
the splitter's 70/15/15 bands are untouched and the output is byte-identical to
what it was before fold mode existed. With it, each of the K folds holds out a
different fifth of the clusters, so pooling the folds makes the whole library
the effective test set rather than the 2-to-5-cluster slices a single split
leaves behind. ``--find-fold-salt`` is a fourth, generation-free mode that
searches for salts under which every library populates every bucket.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .lint import render_report
from .manifest import ManifestError, find_fold_salts, load_fragments
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

#: Salt used in fold mode when ``--split-salt`` is not given. Chosen with
#: ``--find-fold-salt``: at K=5 only about one integer salt in forty leaves
#: every library populating all five buckets, and an unlucky assignment in a
#: library for an unrelated signal blocks the run (the empty-cell guard covers
#: the whole manifest). Which library binds shifts as libraries grow, so this
#: is not tied to one signal and editing an unrelated library can still move
#: it. ``test_the_agreed_salt_still_clears_the_real_libraries`` re-checks this
#: salt against the live manifest; if that test fails, rerun --find-fold-salt
#: and pin the new value here. Pinned rather than searched at runtime so every
#: fold of every arm splits identically.
DEFAULT_FOLD_SALT = "0"

#: How far ``--find-fold-salt`` searches by default. The search does no
#: generation, so an exhaustive sweep to here costs a second or two.
DEFAULT_SALT_SEARCH_LIMIT = 1000


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
        "--folds",
        type=int,
        default=None,
        help="split into K cross-validation folds instead of the default 70/15/15 bands. "
        "Opt-in: without this flag the split is byte-identical to what it has always been",
    )
    parser.add_argument(
        "--fold",
        type=int,
        default=None,
        help="which fold to generate, in [0, folds). Its bucket is test, the next is "
        "validation, the rest train. Requires --folds",
    )
    parser.add_argument(
        "--split-salt",
        default=None,
        help=f"salt mixed into the cluster hash before bucketing (default {DEFAULT_FOLD_SALT!r}). "
        "Requires --folds: re-salting the default bands would silently move every "
        "existing dataset's split",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="report library health instead of generating: hedge markers, "
        "cross-split near-duplicates and fever language in filler",
    )
    parser.add_argument(
        "--find-fold-salt",
        action="store_true",
        help="instead of generating, print the salts under which every library populates "
        "every fold bucket. Requires --folds",
    )
    parser.add_argument(
        "--salt-search-limit",
        type=_non_negative_int,
        default=DEFAULT_SALT_SEARCH_LIMIT,
        help="how many integer salts --find-fold-salt tries",
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


def split_options(args: argparse.Namespace) -> dict:
    """Resolve the three splitter flags into ``load_fragments`` keyword arguments.

    Returns the untouched defaults unless ``--folds`` was given, so the legacy
    path cannot be perturbed by a flag left at its default.
    """
    if args.folds is None:
        return {"folds": None, "fold_index": 0, "salt": ""}
    return {
        "folds": args.folds,
        "fold_index": args.fold or 0,
        "salt": DEFAULT_FOLD_SALT if args.split_salt is None else args.split_salt,
    }


def run_lint(args: argparse.Namespace) -> int:
    """Print the library health reports. Never modifies a library."""
    # check_cells=False: the empty-cell guard is generation's, and a lint that
    # aborts on unbalanced libraries cannot report on unbalanced libraries.
    fragments = load_fragments(args.manifest, check_cells=False, **split_options(args))
    for line in render_report(fragments):
        print(line)
    return 0


def run_find_fold_salt(args: argparse.Namespace) -> int:
    """Print the salts that leave every library populating every fold bucket.

    Generation-free, and deliberately a flag rather than a one-off script: the
    constraint has to be rediscovered every time a library grows, and doing that
    by hand is worse than keeping the search.
    """
    options = split_options(args)
    fragments = load_fragments(args.manifest, check_cells=False)
    salts = find_fold_salts(fragments, folds=options["folds"], limit=args.salt_search_limit)
    print(
        f"salts below {args.salt_search_limit} populating all {options['folds']} buckets "
        f"of every library: {len(salts)}"
    )
    for salt in salts:
        print(salt)
    if not salts:
        # Not an error exit: an empty result is a real answer about the
        # libraries, and it means a library is too small to cover K buckets
        # rather than that the search went wrong.
        print("none found; a library has fewer clusters than there are buckets, or close to it")
    return 0


def run(args: argparse.Namespace) -> int:
    # Fail fast on configuration before doing any work: a missing signal or a
    # malformed distribution discovered after a 10,000-example run is a wasted
    # run, and the project treats config drift as an error rather than
    # something to tolerate.
    distribution = parse_distribution(args.dist)
    fragment_counts = parse_fragment_counts(args.fragment_counts)
    load_and_validate(args.ruleset, args.signal)

    options = split_options(args)
    fragments = load_fragments(args.manifest, **options)
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
        folds=options["folds"],
        fold_index=options["fold_index"] if options["folds"] is not None else None,
        split_salt=options["salt"],
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


def check_fold_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject fold flags that cannot mean what they look like they mean.

    ``--fold 3`` without ``--folds`` reads as "generate fold 3" and would
    silently generate the default 70/15/15 split instead, which is the kind of
    quiet mismatch a whole evaluation can be built on top of.
    """
    if args.folds is None:
        for flag, value in (("--fold", args.fold), ("--split-salt", args.split_salt)):
            if value is not None:
                parser.error(f"{flag} requires --folds")
        if args.find_fold_salt:
            parser.error("--find-fold-salt requires --folds")
        return

    # Three, not two: fold i holds out bucket i for test and bucket i+1 for
    # validation, so at K=2 there is nothing left to train on.
    if args.folds < 3:
        parser.error(f"--folds must be at least 3, got {args.folds}")
    if args.fold is not None and not 0 <= args.fold < args.folds:
        parser.error(f"--fold must be in [0, {args.folds}), got {args.fold}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    check_fold_args(parser, args)
    if not (args.lint or args.find_fold_salt):
        missing = [f"--{name}" for name in _GENERATION_REQUIRED if getattr(args, name) is None]
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
    try:
        if args.find_fold_salt:
            return run_find_fold_salt(args)
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
