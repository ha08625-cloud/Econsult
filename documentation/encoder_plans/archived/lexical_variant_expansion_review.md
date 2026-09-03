# Review: lexical variant expansion of the existing fragment libraries

**Stage 2 review of `lexical_variant_expansion_provisional.md`.** It is not yet
an implementation plan; three findings below have to be settled first, and one
of them may cancel the ticket.

Read alongside: `arch_training.md` sections 3 (cluster markers), 6 (splitting),
8 (the lint's two blind faults), 10 (effective sample size), 12.6, 12.7.

---

## Verdict

The provisional plan's *reasoning* is right and unusually honest — it correctly
refuses the volume argument, names DD5 as the trap, and builds in a kill gate.
Three things are wrong with it as engineering, and one measurement it never
took undermines its own premise.

| | Finding | Effect |
|---|---|---|
| **F1** | DD1's machine-derived cluster marker **moves the split assignment of every currently untagged line**, so DD8's "byte-identical test set across arms" is false. | Silent. Breaks the comparison. |
| **F2** | The whole ticket is much cheaper and safer as a **post-processing pass over the generated JSONL**, in the shape `noise.py` already has, than as a replica library tree. That architecture dissolves F1, DD3, DD7 and open question 3 outright. | Removes ~half the plan. |
| **F3** | DD7's "at zero variants it is byte-identical to today's behaviour" is **false**: `fever_null_*` and `dysuria_null_*` already carry multi-line clusters, so a two-stage draw re-weights the baseline. | Breaks the golden digest and the baseline arm's comparability. |
| **F4** | The fault the ticket exists to remove is **largely already absent from the fever libraries** — measured below. But a *different* shape of the same fault is present, and it changes what the rules have to do. | Changes DD5 and DD10. |
| **F5** | The flip-rate metric has **no guard against collapse to `null`**, which is the exact failure mode 2026-08-19 had to rule out with a second metric. | A silent model scores perfectly. |

Everything else — DD2, DD4, DD5's all-classes rule, DD6's three layers, DD10's
one-signal-first, DD11's ordering against 12.1 — I agree with and would not
change.

---

## F1 — DD1 silently reassigns the splits of every untagged line

This is the "mistake that is silent" the plan flags in Task 3, and the plan
contains it.

`manifest.cluster_key` is `cluster_id or normalise(text)`, and `read_library`
namespaces a marker as `{library}:{tag}`. So for a line that carries **no**
marker today, the key the splitter hashes *is its own normalised text*. Emit a
machine-derived marker on it — which DD1 correctly requires, for the leakage
reason it gives — and the key becomes `{library}:{tag}`, a completely different
string, hashing to a different bucket.

That is 374 of fever's 463 lines (`fever_true` and `fever_false` are wholly
untagged, and 89 of 463 lines carry markers) changing split between the two
arms. DD8's claim that "both arms share a byte-identical test set" therefore
does not hold, and the four-cell probe of DD9 compares models trained *and
tested* on different partitions of the same libraries. Nothing fails; the
numbers just stop meaning what the report says they mean.

**Two ways out, and they are not equally good.**

*If the replica-tree architecture survives F2:* the derived cluster key must
hash to **exactly the string the source line hashes to today** — i.e.
`normalise(source_text)`, not a synthetic tag. The `[A-Za-z0-9_]+` marker syntax
cannot carry that (no spaces), so this needs either a widened marker grammar or
a second marker form whose resolution in `cluster_key` is "hash as the source
text". Already-tagged lines are unaffected, because `cluster_id` still wins.
This is a change to `manifest.py`'s central contract and wants its own test:
*expanding a library must not move any source line's split.*

*The cheap alternative if that is unpalatable:* generate the baseline arm from
the same expander with an empty rule set, so both arms carry identical markers
and identical splits. The cost is that the baseline arm is then no longer the
2026-08-19 baseline and must be retrained — but it is comparable, which is what
the experiment needs.

---

## F2 — This should be post-processing over the JSONL, not a replica library tree

`scripts/synthetic_data/noise.py` is 1,427 lines of an already-built, already-
measured pass that takes a generated tree and rewrites the `text` field of every
example, deterministically, with per-example RNG seeding (`example_rng`), a
per-label edit-rate sidecar, a `check_tree` guard, and filenames preserved so
`--data-dir` still finds it. 12.6 chose that architecture over a generator flag
for reasons stated in `arch_training.md` §12.6, and **every one of those reasons
applies here verbatim**: the generator stays byte-identical, one generation run
yields both arms, and deduplication keeps operating on clean text.

Applying the substitution rules to the finished example text instead of to the
library files gives, for free:

* **F1 disappears.** No library file changes, so no cluster key changes, so no
  split moves. The clean and expanded trees are the same examples with the same
  `example_id`s.
* **DD7 disappears.** The draw is untouched. There is no re-weighting to fix and
  no golden digest to break — which also removes F3.
* **DD3 and open question 3 disappear.** The output tree is under
  `data/synthetic/generated/`, which is already git-ignored. The rule file is
  the reviewable artefact, which is what DD3 wanted anyway.
* **DD5 becomes mechanical rather than a review discipline.** Rules scoped to a
  *signal* and applied to whole example text cannot be applied to one label class
  and not another — the pass never sees the label. And the substitution rate per
  label can be reported in a sidecar exactly as `noise.py` reports edit rate per
  label, so DD5's "check that fails if a rule's scope covers some but not all
  classes" becomes a number printed every run.
* **DD9's probe becomes paired.** `--test-dir` already exists (12.6 used it) and
  replaces every fold's test split with another tree's. With post-processing,
  example *n* in the expanded test tree is the same example as *n* in the clean
  one, so flip rate is a paired McNemar statistic over the whole test set —
  thousands of paired observations — rather than an unpaired comparison over a
  bespoke 40-line corpus. That is a far stronger instrument than Task 0 as
  written, and it costs nothing extra.

**What it gives up, stated honestly.** Rules cannot be scoped per *library*,
only per signal, because the example text carries no character offsets back to
its source fragments (`meta.fragment_ids` names them but does not locate them).
That kills DD4's Tier C exclusion rule — "excluded by default from
`null_historical` and `null_hedged`" is not expressible. Tier C is already out
of v1 and should stay out; if it is ever wanted, it wants the library-expansion
architecture and its own ticket. Tiers A and B are class-agnostic by DD5, so
they lose nothing.

The other thing it gives up is DD6 layer 3 — you cannot run the library lint
over a tree of examples. The replacement is cheaper and better targeted: apply
the rule set to the **library** lines in a dry-run mode and run the existing
filler-purity and cross-signal checks on the result. That checks the *rules*,
which is the thing under review, and needs no replica tree to be the training
input.

**Recommendation: build it as `expand.py`, a sibling of `noise.py`**, taking a
directory and a rule file, writing a parallel directory. Reuse `example_rng`,
`split_words`, `sidecar_path`, `check_directories`, `check_tree`.

---

## F3 — The two-stage draw is not a no-op today, and does not belong in this ticket

DD7 says the two-stage draw is "byte-identical to today's behaviour" at zero
variants. It is not. `select_fragments` draws `rng.choice(signal_pools[...])`
uniformly over *fragments*, and the ambiguous pool already contains multi-line
clusters: 89 of fever's 463 lines and 148 of dysuria's 256 are hand-tagged.
Drawing uniformly over clusters and then within them re-weights every one of
those hand-tagged twins downward, changing generated bytes and failing
`test_default_invocation_still_produces_the_golden_dataset`.

Two separate observations follow:

1. Under F2's architecture the two-stage draw is **not needed at all**, because
   expansion never changes the pool.
2. The two-stage draw is nonetheless *arguably correct on its own merits* —
   uniform over ideas is what §10's "count clusters, not examples" implies the
   draw should be. But it is a change to the decisive draw affecting every
   signal and every dataset generated to date, and bundling it into a
   single-signal vocabulary experiment means a moved number has two candidate
   causes. **It should be its own ticket**, measured on its own.

---

## F4 — The fault is not in the fever libraries in the shape the plan assumes

The plan's motivating cases are §8's two: a clinical term living in one library,
and a register that separates one library. Both were fixed by hand. Before
authoring rules for seven libraries, it is worth ten minutes of measurement to
ask whether any comparable fault remains. I ran it.

**Tokens appearing five or more times across the seven fever libraries and
confined to a single label class: three.** They are `cant` (12, `null_hedged`),
`thought` (6, `fever_true`) and `kept` (5, `fever_true`). None is signal
vocabulary; `cant` is the hedging axis expressing itself, which is what that
library is *for*. The dysuria equivalent is twelve tokens and they are `she`,
`he`, `wees`, `ago`, `might`, `says` — the third-party and historical axes,
again inherent to the sub-class rather than accidental. `dysuria` itself no
longer appears anywhere, so §8's worked example is genuinely fixed.

**The signal vocabulary is already spread across all three classes:**

| token | true (96) | false (98) | hedged (73) | metaphor (55) | thirdparty (46) | historical (45) | attribution (50) |
|---|---|---|---|---|---|---|---|
| `fever` | 17 | 27 | 10 | 6 | 36 | 41 | 0 |
| `temperature` | 25 | 26 | 8 | 1 | 7 | 0 | 0 |
| `hot` | 32 | 23 | 13 | 12 | 0 | 0 | 16 |

So the exclusive-token fault the plan cites is **not present**, and DD10's
choice of fever as the pilot signal is, on this evidence, the signal least
likely to show an effect.

**But look at the same table again and there is a real fault of a different
shape.** `fever` appears on 91% of `null_historical` lines and 18% of
`fever_true` lines. `temperature` appears on 26% of `true` and `false` lines and
**zero** `null_historical` lines. That is not an exclusive token; it is a strong
frequency skew, and a model can learn "temperature ⇒ decisive, fever ⇒
displaced" from it just as well.

Three consequences:

* **The premise survives, in a corrected form.** The ticket's target is a
  marginal-frequency skew, not a token that lives in one file. Expansion does fix
  it — expanding `fever`→`temperature` inside `null_historical` creates
  `temperature`-bearing historical lines where there are currently none.
* **One-directional rules only half-decorrelate.** DD2 is right that rules must
  be directional and literal. It under-states the consequence: flattening this
  table needs `fever`→`temperature` *and* `temperature`→`fever` rules, each
  separately scoped and separately safety-reviewed, because `fever_true`
  over-uses `temperature` exactly as `null_historical` over-uses `fever`.
* **There is a cheaper diagnostic than Task 0, and it should be a permanent
  lint report.** A per-token label-association report over the committed
  libraries — for every token, its rate in each label class of its signal, ranked
  by skew — costs about thirty lines, needs no training, runs over all seven
  signals at once, and mechanically catches the *first* of §8's two blind faults,
  which §8 says "would not be caught by any check we have". It also tells the
  author *which* words need rules instead of asking them to expand everything.
  I would build this before Task 0 and I would keep it whatever the ticket
  decides, because it has value independent of expansion.

---

## F5 — Flip rate needs a co-primary guard

DD9 makes flip rate the decision metric. **A model that answers `null` to
everything has a flip rate of zero.** That is not hypothetical: §10 records that
two thirds of the real-text cells are `null`, that a silent arm clears both the
guard and the primary criterion of the companion run, and that only
decisive-cell accuracy ruled it out. The same trap is open here and the plan
does not close it.

Adopt the 2026-08-19 shape verbatim: **flip rate is the primary criterion,
decisive-cell accuracy on the clean test set is a pre-registered guard, and an
arm that lowers flip rate while losing decisive accuracy is a loss.** Both
numbers pre-registered before training, per §12.9's "declare a bound before you
train".

Two smaller notes on the measurement:

* **Pre-register the expected synthetic result as "nothing moves".** The clean
  synthetic test set is drawn from the same libraries under the same vocabulary,
  so it *cannot contain* the failure the ticket targets — the exact situation
  2026-08-19 called the negative control, where "a large synthetic gain would
  have meant a new shortcut rather than a removed one". Writing this down in
  advance is what stops a synthetic gain being read as success.
* **Flip rate needs no labels**, so it can be measured on the 67 real
  submissions without touching their labels — which means it does *not* consume
  the holdout's validity as a descriptive diagnostic. It would consume it if
  used to *choose between arms*, so: descriptive on the realistic set, selective
  only on the synthetic one. Task 0 has no arms to choose between yet, so it can
  and should use real text, which is where the register gap actually lives.

---

## Answers to the plan's five open questions

1. **Decorrelation, not volume.** Agreed, and F4 sharpens it: specifically
   marginal-frequency decorrelation, not exclusive-token removal.
2. **DD5 stands.** All-classes or nothing is right, and under F2's architecture
   it is free rather than a doubling of authoring cost, because the pass cannot
   see the label.
3. **Moot under F2.** The tree is generated output under an already-git-ignored
   directory. If the replica-library architecture survives anyway, pinned digest.
4. **Do not run them together, and 12.6 goes first.** Tier A is *not* subsumed
   by the noise pass — `drop_apostrophe` produces `Ive`, an error; Tier A
   produces `I have`, a valid alternative form, and only the second decorrelates
   register. But 12.6 is built, measured and positive with one open cell costing
   two evaluations, and this is unbuilt. Closing that cell first is strictly
   cheaper and keeps the result attributable.
5. **After §10's outstanding items 1 and 2, as the plan says** — with one
   exception: the F4 lint report and Task 0 need no GPU and should run now, in
   parallel with whatever holds the compute.

---

## Revised task list

**Task 0a — Per-token label-association lint report (new, do first).** Rate of
every token in each label class of its signal, ranked by skew, over all seven
signals. No training. Permanent report regardless of what happens to this
ticket. This is what says whether the fault exists and where.

**Task 0b — The flip-rate diagnostic**, as the plan describes, but over
paraphrases of the 67 real submissions rather than test-split fragments, scored
with the existing fever head. Descriptive only. *If flips are rare and 0a shows
little skew, stop.* This gate is real and should be respected.

**Task 1 — `expand.py`, a post-processing pass in `noise.py`'s shape.** Rule
file (source phrase, replacement, signal scope, declared invariant), whole-word
matching, per-example deterministic RNG, sidecar reporting substitution rate per
label, tree checks. Plus DD6 layer 2 (structural-token invariance against
`STRUCTURAL_FROZEN` after contraction normalisation) and one extra mechanical
check the plan misses: **a rule must not change whether a line matches its
signal's lexicon in `SIGNAL_LEXICONS`** — cheap, reuses existing code, and
catches a swap that walks a line out of its own vocabulary.

**Task 2 — Rule-file dry-run lint.** Apply the rules to the library lines and
re-run filler purity and the cross-signal grid on the result; a new cross-signal
hit is a hard failure. DD6 layer 3, retargeted at the rules.

**Task 3 — Author the fever rule set**, Tiers A and B, directional in both
directions, aimed at the skews Task 0a ranks rather than at everything.

**Task 4 — Two arms, four cells, paired flip rate plus the decisive-accuracy
guard.** Five folds × two arms is ten trainings and twenty evaluations, the same
arithmetic 12.6 paid for its 2×2. Pre-register both bounds and the
"nothing moves on synthetic" expectation.

**Task 5 — Conditional extension** to the remaining six signals, prioritised by
Task 0a's skew ranking rather than by signal order.

*Dropped:* cluster propagation and the two-stage draw (F2 removes the need; the
draw becomes its own ticket per F3), and the replica library tree.

---

## Two small things

* **`probe` is already a subcommand** of `scripts.encoder_training` (Arm A, the
  frozen probe). Whatever this one is called, it should not be that.
* **No report may quote an expanded example count as growth** — the plan says
  this and it is right, and under F2 it is automatic, since the expanded tree has
  exactly as many examples as the clean one and carries the same `fragments`
  provenance block with the same cluster keys.
