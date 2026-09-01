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
        --companion-share 0.0 \\
        --declarative-share 0.0 \\
        --emit-signals primary \\
        --out      data/synthetic/generated/fever_present.train.jsonl

Same seed + same libraries + same flags produces byte-identical output. That
is why the writer pins ``ensure_ascii=False`` and ``\\n`` line endings rather
than taking the platform default: a dataset that differs by line ending
between a developer's machine and CI is not reproducible in any useful sense.

Every run also writes ``<out>.stats.json``.

``--companion-share`` is the one flag that changes what a non-decisive slot may
hold: above zero, some of them carry another signal's clinical language instead
of filler, drawn only from libraries the manifest declares ``null`` on this run's
signal. It defaults to 0.0 and the path is skipped entirely at that value, so
every dataset generated before companions existed is still reproducible from its
seed. Read ``companions.count_by_label_mode`` in the sidecar after any non-zero
run: those rows must agree, or the companion count has become a proxy for the
label.

``--declarative-share`` is the second: above zero, a share of the *decisive*
fragments in ``true`` and ``false`` examples are procedurally generated
multi-symptom sentences -- "I have had a fever and blood in my wee, but not any
pain when I pee" -- each carrying a per-line label vector, rather than the
one-claim hand-written lines. It exists as a share rather than as a merged pool
because the generated library is larger than any hand-written one and would
otherwise become the *typical* decisive sentence, trading the one-claim prior
for a one-frame prior. It defaults to 0.0 and the draw is skipped entirely at
that value. Read ``declarative.frame_by_label_mode`` in the sidecar after any
non-zero run: those rows must agree, or the frame has become a cue for the
label.

``--emit-signals all`` widens ``labels`` from the run's own signal to every
signal the example's fragments jointly have a known status for. It is **built
and not measured**: no trained arm uses it, ``merge-folds`` refuses a tree whose
records carry more than their own signal's key, and the flag exists so that the
mechanism is written, tested and documented rather than sketched. It defaults to
``primary``, which is byte-identical to what the generator emitted before the
flag existed.

``--lint`` is a second, generation-free mode: it loads the same libraries and
prints the hedge-marker, near-duplicate, filler-purity and cross-signal reports.
It reads nothing but the manifest, so ``--ruleset``, ``--split``, ``--count``
and ``--out`` are neither required nor used. The cross-signal report has no flag
of its own deliberately: it is the same lexicons asked about every library
rather than only filler, and splitting it out would let somebody run the lint
and not see it.

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

from . import declarative
from .lint import inventory_report_faults, render_report
from .manifest import ManifestError, find_fold_salts, load_fragments
from .recombine import (
    DEFAULT_COMPANION_SHARE,
    DEFAULT_DECLARATIVE_SHARE,
    DEFAULT_EMIT_SIGNALS,
    DEFAULT_NULL_AMBIGUOUS_RATIO,
    EMIT_SIGNALS_MODES,
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
from .ruleset import RulesetError, encoder_signals, load_and_validate

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
    parser.add_argument(
        "--companion-share",
        type=float,
        default=DEFAULT_COMPANION_SHARE,
        help="share of an example's non-decisive slots carrying another signal's clinical "
        "language instead of filler. Eligibility is the library's null_on declaration for "
        "this run's signal and nothing else. At the default 0.0 the whole path is skipped "
        "and the output is what it was before companions existed; the count is drawn over "
        "the same number of slots in every label mode, so it cannot become a proxy for the "
        "label",
    )
    parser.add_argument(
        "--declarative-share",
        type=float,
        default=DEFAULT_DECLARATIVE_SHARE,
        help="share of true/false examples whose decisive fragment is drawn from the "
        "declarative library -- procedurally generated multi-symptom sentences carrying a "
        "per-line label vector -- rather than from the hand-written pool for the same "
        "label. At the default 0.0 the draw is skipped entirely and the output is what it "
        "was before declarative fragments existed. It governs the decisive slot only: a "
        "declarative fragment that is null on this run's signal is an eligible companion at "
        "any share. null_ambiguous never draws from it -- a fixed frame cannot express a "
        "hedge, so every generated line is an easy case",
    )
    parser.add_argument(
        "--emit-signals",
        choices=list(EMIT_SIGNALS_MODES),
        default=DEFAULT_EMIT_SIGNALS,
        help="how many signals a record carries a label for. 'primary' emits one key, for "
        "this run's signal, and is byte-identical to the output before this flag existed. "
        "'all' also emits a key for every companion signal the example's fragments jointly "
        "have a known status for -- a signal any fragment is undeclared on gets no key at "
        "all, which masks that head's loss rather than supervising it towards 'not "
        "mentioned'. Built and not measured: no trained arm uses it and merge-folds refuses "
        "a multi-key tree",
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
        "cross-split near-duplicates, every signal's language in filler, the "
        "full (library, foreign signal) grid with its paste-ready null_on block, "
        "what each generated library is made of, and the phrase inventory. Exits "
        "non-zero on an inventory fault and on nothing else",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help="the declarative phrase inventory --lint checks and --build-declarative "
        f"composes (default {str(declarative.DEFAULT_INVENTORY)!r})",
    )
    parser.add_argument(
        "--build-declarative",
        action="store_true",
        help="instead of generating, expand the authored phrase inventory into the committed "
        "declarative JSONL library. Writes a tracked file, so it is a deliberate act and a "
        "reviewable diff rather than something recombination does at runtime",
    )
    parser.add_argument(
        "--target-count",
        type=_non_negative_int,
        default=declarative.DEFAULT_TARGET_COUNT,
        help="how many declarative lines --build-declarative writes, stratified across arities "
        f"by --arity-weights (default {declarative.DEFAULT_TARGET_COUNT})",
    )
    parser.add_argument(
        "--arity-weights",
        default=declarative.DEFAULT_ARITY_WEIGHTS,
        help="how many symptoms a declarative sentence names, as a weighted mix, e.g. "
        f"{declarative.DEFAULT_ARITY_WEIGHTS!r}; must sum to 1.0. Arity 1 is excluded -- a "
        "one-symptom declarative sentence is what the hand-written libraries already are",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="with --build-declarative, regenerate into memory and exit non-zero if the "
        "committed library differs, instead of writing. This is what stops the library and "
        "the inventory drifting apart silently",
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
    """Print the library health reports. Never modifies a library.

    Exits non-zero on an inventory fault and on nothing else. Every other report
    here is a prompt to re-read something, and a lint that failed on those would
    be a lint nobody could run; an inventory fault is different in kind, because
    the inventory is composed into hundreds of committed lines and a phrase
    lifted from a library puts train text inside a generated val fragment (DD10).
    """
    # check_cells=False: the empty-cell guard is generation's, and a lint that
    # aborts on unbalanced libraries cannot report on unbalanced libraries.
    fragments = load_fragments(args.manifest, check_cells=False, **split_options(args))
    if not args.ruleset.is_file():
        raise RulesetError(f"ruleset not found: {args.ruleset}")
    signals = encoder_signals(json.loads(args.ruleset.read_text(encoding="utf-8")))
    inventory_path = declarative.DEFAULT_INVENTORY if args.inventory is None else args.inventory

    for line in render_report(fragments, inventory_path=inventory_path, encoder_signals=signals):
        print(line)

    faults = inventory_report_faults(inventory_path, fragments, signals)
    if faults:
        print(
            f"error: the declarative phrase inventory has {len(faults)} fault(s); "
            "see the inventory section above",
            file=sys.stderr,
        )
        return 1
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


def run_build_declarative(args: argparse.Namespace) -> int:
    """Expand the phrase inventory into the committed JSONL library, or check it.

    Generation-free in the recombiner's sense: it reads neither the manifest nor
    the ruleset, and writes a library rather than a dataset.
    """
    out_path = declarative.DEFAULT_OUT if args.out is None else args.out
    lines, content = declarative.build(
        inventory_path=(
            declarative.DEFAULT_INVENTORY if args.inventory is None else args.inventory
        ),
        target_count=args.target_count,
        arity_weights=args.arity_weights,
        seed=args.seed,
    )

    if args.check:
        if not out_path.is_file():
            print(f"error: {out_path} does not exist; run --build-declarative", file=sys.stderr)
            return 1
        current = out_path.read_text(encoding="utf-8")
        if current != content:
            print(
                f"error: {out_path} is not what the inventory and these flags generate "
                f"(committed {len(current.splitlines())} lines, regenerated {len(lines)}). "
                "Rerun --build-declarative and commit the diff",
                file=sys.stderr,
            )
            return 1
        print(f"{out_path} matches the inventory ({len(lines)} lines)")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {out_path}")
    for line in declarative.summarise(lines):
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
    # The set a null_on declaration may name, so a misspelled signal fails here
    # rather than presenting as a pair nobody declared.
    signals = encoder_signals(json.loads(Path(args.ruleset).read_text(encoding="utf-8")))

    options = split_options(args)
    fragments = load_fragments(args.manifest, signals=signals, **options)
    pools = build_pools(fragments, args.signal, args.split)
    if pools.undeclared_filler:
        # Loud rather than fatal: an undeclared filler library lowers the
        # fragment-count ceiling and moves every _draw_filler outcome, and both
        # are worth knowing about even in a run that still succeeds.
        print(
            f"warning: {len(pools.undeclared_filler)} filler librar"
            f"{'y is' if len(pools.undeclared_filler) == 1 else 'ies are'} undeclared on "
            f"{args.signal!r} and excluded from this run: "
            f"{', '.join(pools.undeclared_filler)}",
            file=sys.stderr,
        )

    examples, telemetry = generate(
        pools,
        count=args.count,
        seed=args.seed,
        distribution=distribution,
        null_ambiguous_ratio=args.null_ambiguous_ratio,
        fragment_counts=fragment_counts,
        companion_share=args.companion_share,
        declarative_share=args.declarative_share,
        emit_signals=args.emit_signals,
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
        companion_share=args.companion_share,
        declarative_share=args.declarative_share,
        emit_signals=args.emit_signals,
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


def check_build_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject build-mode flags that cannot mean what they look like they mean.

    ``--check`` without ``--build-declarative`` reads as "check something" and
    would silently generate a dataset instead, which is the same class of quiet
    mismatch :func:`check_fold_args` exists for.
    """
    if args.build_declarative:
        if args.lint:
            parser.error("--build-declarative and --lint are separate modes; run one at a time")
        return
    if args.check:
        parser.error("--check requires --build-declarative")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    check_fold_args(parser, args)
    check_build_args(parser, args)
    if not (args.lint or args.find_fold_salt or args.build_declarative):
        missing = [f"--{name}" for name in _GENERATION_REQUIRED if getattr(args, name) is None]
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
    try:
        if args.build_declarative:
            return run_build_declarative(args)
        if args.find_fold_salt:
            return run_find_fold_salt(args)
        return run_lint(args) if args.lint else run(args)
    except (
        declarative.DeclarativeError,
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
