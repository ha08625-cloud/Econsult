# Implementation Plan: Variable fragment count in the recombination engine

## Plan

`scripts/synthetic_data/recombine.py` builds every training example from exactly two fragments.
`FRAGMENTS_PER_EXAMPLE = 2` is a module constant, and `select_fragments` asserts against it. That
was a deliberate choice — `arch_training.md` section 5 explains that holding the count constant
stops the model learning "long text means fever" — but it means the encoder only ever sees
two-clause blurbs, while real submissions are longer and messier (section 9).

This plan makes the fragment count a per-example draw from a weighted distribution supplied on the
command line, defaulting to a 50/50 mix of two- and three-fragment examples. The extra fragment is
always **filler**. The engine is written N-general: `--fragment-counts 2=0.4,3=0.4,4=0.2` works on
day one, bounded only by the number of filler libraries available.

The safety of the whole change rests on one property, and every other decision here serves it:

> **The count distribution must be identical across all four label modes.**

If three-fragment examples were more often `true` than `null`, text length would become a usable
proxy for the label. That is the exact failure `FRAGMENTS_PER_EXAMPLE` was protecting against, and
nothing downstream would surface it — it would present as a validation score that looks good and a
model that does not transfer. The count is therefore drawn from one distribution that knows nothing
about the label mode, and the stats sidecar reports the realised counts per label so the property is
checkable on every run rather than assumed.

Two tasks: the engine and CLI together (with their tests), then documentation.

---

## Scope

**In scope**

- `scripts/synthetic_data/recombine.py` — count sampling, N-general fragment selection, pool
  validation, stats
- `scripts/synthetic_data/__main__.py` — `--fragment-counts` flag
- `tests/test_synthetic_recombination.py` — updated and new tests
- `documentation/arch_training.md` — sections 5, 7, 9, 11, 12.6

**Out of scope**

- **Using another signal's fragments as the extra fragment.** Tempting, since the dysuria and
  flank_pain libraries exist — and wrong. `build_pools` drops them today on purpose: putting a
  dysuria fragment into a `fever_present` example silently asserts that it says nothing about fever,
  and that guarantee is not written anywhere the code can check. That is `arch_training.md` section
  12.5 (label vectors and declared silence), and it is a separate ticket that must land first. This
  plan's extra fragments are filler only.
- **More than one decisive fragment per example.** `Fine_tuning_plan.md` Rule 2 is one signal, one
  decisive fragment. A two-positive example doubles the evidence for the same claim and teaches
  nothing new.
- **Single-fragment examples.** N is bounded below at 2. A lone filler is a trivially easy `null`
  and a lone decisive fragment removes the noise floor entirely.
- **Unblocking generation.** `fever_null_metaphor` still has an empty `val` cell, so
  `check_no_empty_cells` still refuses to run generation against the real libraries
  (`arch_training.md` section 10). This change is testable against fixtures but produces no dataset
  until those fragments are written. That blocker is unaffected either way.
- Any change to `manifest.py`, `normalise.py`, `lint.py` or `ruleset.py`.

---

## Design Decisions

**1. The count is drawn from a weighted distribution, not derived from a max.**
`--fragment-counts 2=0.5,3=0.5` rather than `--max-fragments 3`. The mix is a real hyperparameter —
how much of the dataset should be long — and a max with an implicit uniform draw hides it. The
weighted form also extends to any N without a second flag.

**2. The count is drawn *after* the label mode, and stored on `ExampleSpec`.**
Two consequences, both wanted.

*Drawing after the mode* leaves `sample_label_mode` consuming exactly the RNG draws it consumes
today, so the realised label-mode counts for a given seed do not move. That is a free canary: if
`test_realised_label_counts_are_exactly_these_for_seed_42` starts failing, the draw ordering was
disturbed and the label distribution has silently changed.

*Storing it on the spec* means the duplicate-retry loop in `generate` reuses the same count across
redraws. If the count were re-drawn per attempt, a count that is harder to satisfy uniquely would be
quietly under-sampled — the same reasoning as the existing comment about never giving up on a label
mode partway through.

**3. The emitted dataset changes even at `2=1.0`, and that is accepted.**
Sampling the count consumes one `rng.random()` before fragment selection, which shifts the stream
every subsequent draw reads from. So a single-count mix produces the same *label distribution* as
today but different *text*. Special-casing "skip the draw when there is only one candidate" would
make `2=1.0` and `2=0.999,3=0.001` behave discontinuously for no benefit. The proof-of-concept run
has never been produced (section 10), so there is no dataset to preserve. `GENERATOR_VERSION` bumps
to 2.

**4. Exactly one decisive fragment at every N; the remainder are filler.**
`true` at N=4 is one positive plus three filler. This means the decisive fragment's share of the
text falls as N rises — 50% at N=2, 20% at N=5. That is the point (harder, more realistic examples)
but it is also why "more is better" is false for this knob: past some N each example carries the
same one supervised claim buried in progressively more noise, so the supervision-per-token drops
while the token cost of training rises. The 50/50 default keeps the mean at 2.5.

**5. Fillers within one example come from distinct libraries, in every mode.**
Today only `null_structural` enforces this. Extending it to all modes changes no two-fragment
behaviour (the other modes draw a single filler), and it stops three-fragment examples reading as
three consecutive tangents in the same voice.

The consequence is a hard ceiling: N cannot exceed the number of filler libraries, because a
structural null at N needs N distinct ones. There are five (`tangents`, `justifiers`, `emotional`,
`expectations`, `uti_speculation`). As N approaches five, structural nulls stop being random in
library composition — at N=5 every one of them contains exactly one fragment from each library. So
{2, 3} is comfortable, 4 is the practical limit against today's libraries, and anything beyond wants
more filler libraries rather than a code change.

**6. The filler-library check lives in `generate`, not `build_pools`.**
`build_pools` cannot know the requested count mix, and the existing test fixtures deliberately build
pools with only two filler libraries. So `_check_pools` keeps its current ≥2 floor unchanged, and
`generate` validates `len(pools.filler) >= max(fragment_counts)` at the top, before any example is
built — consistent with how the distribution and ruleset are validated up front elsewhere.

**7. The stats sidecar reports realised counts per label.**
This is the leak detector for the entire feature and is not optional. Without it, a skewed count
distribution is invisible. Reported both by label and by label mode, alongside token counts broken
down by fragment count so the existing "class medians within ~1.5×" heuristic in section 9 stays
interpretable.

**8. Fragment count is derived from `len(meta["fragment_ids"])`, not stored separately.**
It is already unambiguously present in the record. A second copy is one more thing that can disagree
with itself.

---

## Task 1: Engine, CLI and tests

**A. State of the world.** Nothing has been implemented. `recombine.py` fixes the count at two via
`FRAGMENTS_PER_EXAMPLE`; `select_fragments` builds a two-item list per label mode and asserts its
length; `__main__.py` has no count flag; the test suite asserts two fragments in several places.
This task delivers the whole behaviour change with its tests. It is not split further because the
code cannot be meaningfully verified without the test updates, and the diff is small.

**B. Files and deliverables.**

- `scripts/synthetic_data/recombine.py` — count parsing, sampling, N-general selection, validation,
  stats fields, version bump
- `scripts/synthetic_data/__main__.py` — `--fragment-counts` flag threaded through
- `tests/test_synthetic_recombination.py` — updated and new tests

**C. Instructions.**

*`recombine.py`*

1. Delete `FRAGMENTS_PER_EXAMPLE`. Add `DEFAULT_FRAGMENT_COUNTS = {2: 0.5, 3: 0.5}` with a comment
   recording that the mix must not vary by label mode and why (see Plan section above).

2. Extract the shared parsing work out of `parse_distribution` into a private helper — something
   like `_parse_weighted_terms(text, *, flag) -> dict[str, float]` — covering: splitting on commas,
   the `key=weight` shape, duplicate keys, non-numeric and negative weights, and the sum-to-1.0
   check within `1e-9`. Keep the flag name in the error messages so a bad `--fragment-counts` does
   not report itself as a `--dist` problem.

   `parse_distribution` then adds only its label-specific checks (unknown label, missing label) and
   its behaviour and error strings must not change — its existing tests should pass untouched.

   New `parse_fragment_counts(text) -> dict[int, float]` adds: keys parse as integers, every key
   is ≥ 2, at least one term present. Raise `DistributionError` throughout, so `__main__.py`'s
   existing exception handling covers it with no change.

3. Extract the cumulative-sum draw used by `sample_label_mode` into a helper that takes an explicit
   iteration order, and use it for both. The module docstring's rule — *every collection sampled
   from is a sorted sequence* — applies: iterate `sorted(fragment_counts)`, never the dict's
   insertion order, or the output starts depending on the order the CLI parsed the flag terms in.

4. `ExampleSpec` gains `fragment_count: int`. `make_spec` gains a `fragment_counts` argument and
   draws the count **after** `sample_label_mode`, storing it on the spec. Do not reorder these two
   draws (DD2).

5. `select_fragments(rng, pools, label_mode, fragment_count)`:
   - `true` / `false` / `null_ambiguous`: one fragment from the matching signal pool, then
     `fragment_count - 1` fillers.
   - `null_structural`: `fragment_count` fillers.
   - In both cases draw fillers one at a time, accumulating the libraries used and passing them all
     as `exclude` to `_draw_filler`, so every filler in an example comes from a different library
     (DD5). `_draw_filler` already takes an `exclude` sequence and raises `PoolError` naming it when
     no candidate remains, so no change is needed there.
   - Keep the `rng.shuffle` and keep the post-condition assertion, now comparing against
     `fragment_count`.

6. `generate` gains `fragment_counts: dict[int, float] | None = None`, defaulting to
   `DEFAULT_FRAGMENT_COUNTS`. Before the loop, validate `len(pools.filler) >= max(fragment_counts)`
   and raise `PoolError` naming the requested maximum and the libraries available (DD6). Pass
   `fragment_counts` into `make_spec` and `spec.fragment_count` into `select_fragments`.

7. Bump `GENERATOR_VERSION` to 2.

8. `build_stats` gains a `fragment_counts` argument (the requested mix) and emits:
   - under `requested`: `"fragment_counts": {"2": 0.5, "3": 0.5}`
   - a new top-level `"fragment_counts"` block with `by_label` and `by_label_mode`, each mapping the
     label/mode to a count-keyed tally, e.g. `{"true": {"2": 78, "3": 78}, ...}`
   - `token_counts` gains a `by_fragment_count` sibling to the existing `by_label` and
     `by_label_mode`

   Use **string keys** in every emitted mapping. `json.dump` coerces integer keys to strings
   silently, and a dict that round-trips as string-keyed but is written as int-keyed will bite
   whoever reads the sidecar back. Derive each example's count from `len(meta["fragment_ids"])`
   (DD8).

*`__main__.py`*

9. Add `DEFAULT_FRAGMENT_COUNTS_ARG = "2=0.5,3=0.5"` and a `--fragment-counts` argument defaulting
   to it, with help text saying the mix is label-independent by design.

10. In `run`, parse it alongside `parse_distribution` — before `load_fragments`, so a malformed flag
    fails before any file is read — and thread it into both `generate` and `build_stats`.

11. Update the module docstring's worked example to include the flag.

*`tests/test_synthetic_recombination.py`*

12. **Update** `test_every_example_holds_exactly_two_fragments` → rename to reflect variable counts;
    assert each example's fragment count is one of the requested set, and that `fragment_ids` and
    `fragment_subclasses` are the same length.

13. **Update** `test_structural_nulls_draw_two_fillers_from_different_libraries` → all fragments are
    filler and all libraries are distinct, at whatever count the example drew. Note the shared test
    fixture has only two filler libraries, so tests that exercise N=3 need a fixture with at least
    three; add one rather than widening the existing one, so the two-filler pool-error case stays
    available.

14. **Update** `test_ambiguous_nulls_carry_exactly_one_signal_fragment` → exactly one
    ambiguous/confounder fragment and the rest filler.

15. **Update** `test_decisive_fragments_appear_in_both_positions` → the positive fragment is
    observed in every position up to `max(fragment_counts) - 1`.

16. **Update** the byte-identical, JSONL-schema and stats-sidecar tests for the new fields.

17. **New, and the important one:** the count distribution does not vary by label mode. Generate a
    few thousand examples, tally counts per label mode, and assert each mode's realised 2:3 ratio
    sits within a tight band of the requested mix. This is the test that would catch a future change
    reintroducing the length leak — give it a comment saying so.

18. **New:** `test_realised_label_counts_are_exactly_these_for_seed_42` must still pass with its
    existing golden numbers (DD2). If it does not, the count draw was placed before the mode draw.
    Add a comment at that test recording why it is load-bearing for this feature.

19. **New:** requesting a count larger than the filler library count raises `PoolError` before any
    example is generated, and the message names the shortfall.

20. **New:** `parse_fragment_counts` rejects a count below 2, a non-integer key, weights that do not
    sum to 1.0, duplicate keys and an empty string — and its errors name `--fragment-counts` rather
    than `--dist`.

21. **New:** an N-general case — `--fragment-counts 4=1.0` against a fixture with four filler
    libraries produces only four-fragment examples, each with exactly one decisive fragment.

22. **New:** growing `--count` still does not move earlier examples, with a mixed count distribution
    (the per-example seeding property, re-verified under the new draw).

**Verification.** Per `CLAUDE.md`: typecheck, then run `tests/test_synthetic_recombination.py`
alone. Do not run the full suite or `npm run build`. CI's unit job is the gate.

Also run the lint by hand to confirm it is unaffected — it does not import anything this task
touches, but it shares the CLI:

```
python -m scripts.synthetic_data --lint
```

Generation against the real libraries will still fail on the `fever_null_metaphor` empty cell. That
is expected and is not a regression.

---

## Task 2: Documentation

**A. State of the world.** Task 1 is complete: the generator draws a fragment count per example from
a label-independent weighted distribution, defaulting to `2=0.5,3=0.5`, with the extra fragments
always filler. `arch_training.md` still describes the two-fragment behaviour as invariant.

**B. Files and deliverables.** `documentation/arch_training.md` only.

**C. Instructions.**

23. **Section 5** ("How one example is built") is the substantive edit. It currently opens "Every
    example is exactly **two fragments**... Always two, in every label class" and then explains why.
    Rewrite so the *reasoning survives the change*: the invariant was never "two", it was "the count
    must not correlate with the label". State the new behaviour, the default mix, that the extra
    fragments are filler, and that the count is drawn independently of the label mode with the
    sidecar reporting the realised split. Update the four-row composition table to show both counts.

24. **Section 7** ("Output"): add the new sidecar fields — `requested.fragment_counts`, the
    top-level `fragment_counts` block, `token_counts.by_fragment_count`.

25. **Section 9** ("What this data is and is not worth"): two additions.
    - The "examples are about two sentences long" paragraph needs correcting, but do not oversell
      it — the mean is now 2.5 fragments, not a realistic submission length.
    - A new caveat: a two-fragment example and a three-fragment example sharing two fragments are
      counted as two distinct examples but are not independent. Unique-text deduplication does not
      catch this, so the effective sample size is somewhat below the raw count, and more so as N
      rises.

26. **Section 11** ("Running it"): document `--fragment-counts`, its default, and the filler-library
    ceiling from DD5.

27. **Section 12.6** ("Sequencing"): add a short note that variable fragment count was implemented
    ahead of the listed order, that it is independent of steps 1–2 (it changes how many fragments an
    example holds, not which labels may be emitted), and that the extra fragments are filler
    precisely because using other signals' fragments requires step 2 first.

Sections 1–4, 6, 8, 10 and 12.1–12.5 need no change.
