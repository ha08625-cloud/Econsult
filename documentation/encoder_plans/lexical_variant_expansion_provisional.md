# Provisional plan: lexical variant expansion of the existing fragment libraries (12.1b)

**Status: superseded. Kept for its reasoning, which is largely right, and for
the record of what was decided and why.** The plan of record is
`lexical_variant_expansion_implementation.md`;
`lexical_variant_expansion_review.md` is the review that sits between them and
explains what changed. In particular DD1, DD3, DD7 and DD9 below were corrected:
expansion is post-processing over the generated JSONL rather than a replica
library tree, there is no cluster-marker emission and no two-stage draw, and the
flip-rate metric carries a pre-registered decisive-accuracy guard.

Read first: `arch_training.md` sections 2 (label first), 3 (cluster markers,
"Writing style is vocabulary"), 6 (splitting), 8 (the lint's two blind faults),
10 ("Effective sample size: count clusters, not examples"), 12.1, 12.6, 12.7.

---

## What this is, and how it differs from the 12.1 plan of record

12.1 as written is **template authoring**: write 40 templates with slots per
library and expand them into fragments. Its plan of record is
`procedural_fragment_generation_implementation.md`, and that document has since
been folded into the multi-symptom declarative ticket (12.3) — it builds a *new*
library of declarative multi-symptom sentences from an authored phrase
inventory.

This ticket is the other half of the idea and has not been written down before:
**take the 2,503 fragments that already exist and swap parts of them out.**
"I had a fever" becomes "I had a temperature", "I had a high temperature",
"I'd had a fever". "I've had" becomes "I have had", "I've been having".

It is a different mechanism with a different risk profile and — this is the part
that decides the whole ticket — **a different reason to do it**.

---

## 1. The honest case for it: this does not add data

Expanding one line into twelve does not create twelve ideas. Section 10 is
explicit: *effective sample size is the number of distinct clusters, not
examples*, and every variant of a line is the same idea written twelve times.
The arithmetic is identical to 12.6's verdict on the noise pass — "sixty-six
fragments damaged four ways is sixty-six ideas".

So if the goal is **more data, this ticket does nothing** and 12.1's template
authoring is the thing to build instead: 40 authored templates per library are
40 ideas, and swapping "fever" for "temperature" across an existing line is
zero.

**The goal that does justify it is decorrelating surface vocabulary from
label.** Section 8 records two faults the near-duplicate report cannot see, and
both are exactly this fault:

* "Dysuria" appeared on 16 lines of `dysuria_null_metaphor` and nowhere else in
  the six dysuria libraries — a perfect shortcut separating `null` from `true`
  and `false`. *A clinical term that lives in one library is a label, not
  vocabulary.*
* The first draft of `haematuria_null_hedged` was written in lowercase with no
  terminal punctuation against uniformly capitalised siblings, so **casing alone
  separated the ambiguous class perfectly**.

Both were caught by hand. Neither would be caught by any check we have. Every
library was written in one sitting by one author with one vocabulary in mind,
which is precisely the process that produces this fault, and there are 49 of
them. A variant pass that applies **the same vocabulary pool to every label
class of a signal** makes the choice of word non-informative about the label,
by construction.

That reframing carries three consequences that run through everything below:

1. **No report may ever quote an expanded fragment count as growth.** The lint
   must print variants and clusters as two separate numbers, the way section 3's
   table would have to.
2. **The measurement is a robustness probe, not an accuracy number.** See DD9.
3. **Asymmetric expansion is actively harmful** — worse than not doing it. See
   DD5, which is the trap most likely to sink this.

---

## 2. Scope

**In scope**

* A rule-file format for directional, scoped substitutions, committed and
  reviewable.
* An expander that applies rules to the committed libraries and writes a
  parallel tree, deterministically.
* Cluster propagation, so every variant of a line shares that line's cluster and
  therefore its split.
* A label-safety guard analogous to 12.6's frozen lexicon, but inverted.
* A change to the decisive draw so expansion does not re-weight ideas (DD7).
* Lint reporting over the expanded tree, plus a re-run of the existing filler
  purity and cross-signal checks against it.
* One signal (`fever`, all seven libraries) authored end to end.
* A paraphrase-robustness probe and a four-cell read-out.

**Out of scope**

* Any other signal until the probe reads out (DD10).
* Expanding the filler libraries (DD11).
* Template authoring from scratch (that is 12.1 proper) and declarative
  multi-symptom generation (12.3).
* Editing the committed `.txt` libraries in place (DD3).
* Interaction with the noise pass — open question 4.

---

## 3. Design decisions

### DD1 — The unit of expansion is the source line, and the source line is the cluster

Today an untagged line's cluster key is `normalise(text)`
(`manifest.cluster_key`). Generate a variant and leave it untagged and it gets
its own cluster key, so **the variant and its source can land in different
splits**. That is not a subtle risk, it is the leakage the whole cluster
mechanism exists to prevent, and it would happen on every one of thousands of
lines.

So expansion **must** emit a cluster marker, machine-derived from the source
line, on the source and on every variant. This is 12.1's "emit the template ID
as a cluster marker" with the source line playing the template's part.

Two things fall out of this, both good:

* It resolves 12.8's outstanding "tag the four untagged library sets" for any
  library the expander touches, without hand-tagging.
* Lines that already carry hand markers (`fever_null_*`, `dysuria_null_*`) keep
  them: variants inherit the *parent's* tag rather than getting a fresh one, so
  a hand-declared twin pair stays one cluster and does not silently become two.

`read_library` namespaces a tag as `{library}:{tag}`, so the expanded library
must carry the same manifest `name` as its source for the namespace to line up.
That is a reason to prefer DD3's replica-tree shape over a sibling library.

### DD2 — Rules are directional, scoped and literal; never a symmetric synonym bag

The tempting shape is `{"fever", "temperature", "high temperature"}` as an
interchangeable set. It breaks immediately: `fever_true` contains "I checked my
temperature and it was high", and the reverse substitution produces "I checked
my fever and it was high".

A rule is therefore a triple: **a literal source phrase, a replacement, and a
scope** naming the libraries it may apply to. Not a regex over the whole tree.
Whole-word matching only, for the reason section 8 already gives ("hot" matches
inside `lithotripsy`, `photos`, `shot`).

### DD3 — The committed libraries are not edited; expansion writes a replica tree

Editing `data/synthetic/*.txt` in place changes every `fragment_id`, every
golden digest and the section 3 count table, and makes the un-expanded arm
unreproducible. The 12.3 plan of record rejected the same move for the same
reason.

Instead the expander writes a full replica of `data/synthetic/` — same manifest
library names, same directory shape — with each source line followed by its
variants. Selected with `--data-dir`, so the two arms are one flag apart and
everything measured to date stays byte-reproducible.

**Open question 3** is whether that tree is committed (reviewable, but tens of
thousands of lines in the diff) or generated with a pinned digest checked in CI.
The recommendation is **pinned digest**: the rules are what a reviewer should
read, and the tree is their mechanical consequence.

### DD4 — Three tiers, escalating risk, shippable separately

| Tier | What it swaps | Semantic risk | Scope |
|---|---|---|---|
| **A** | Orthography and contraction: `I've`↔`I have`, `haven't`↔`have not`, `didnt`↔`didn't` | none — cannot change which word a token is | every library, filler included |
| **B** | Signal vocabulary within an authored class: `fever`→`temperature`→`high temperature` | real but boundable | the clinical libraries of that one signal, **all classes** (DD5) |
| **C** | Opener and aspect: `I've had`→`I've been having`→`I keep getting` | high — changes aspect and therefore currentness | excluded by default from `null_historical` and `null_hedged` |

Tier A is close to free and is the direct answer to the casing fault section 8
records: it is the same class of fix, applied deliberately rather than
discovered by hand. Tier C is where a label flip is most likely: "I had a fever"
→ "I've been having a fever" moves a past event into the present, which is the
axis the entire `historical` library hangs on. Tier C should probably not ship
in v1 at all.

### DD5 — A signal is expanded across every label class or not at all

This is the trap. If Tier B synonyms are applied to `fever_true` but not to
`fever_null_hedged`, then "temperature" has just become *more* predictive of
`true` than it was before. **A partial pass manufactures exactly the shortcut
the ticket exists to remove**, and it would show up as an improvement on the
synthetic test set while making the model worse on real text.

So the unit of work is not a library, it is a **signal**: all seven fever
libraries at once, and a check that fails if a Tier B rule's scope covers some
but not all of the classes its vocabulary appears in.

The cost is honest: it roughly doubles the authoring per signal against the
naive "expand the positives" version, and it means Tier B on the metaphor and
attribution libraries needs the most care, because those are the ones where a
synonym swap is most likely to break the sentence ("burning up with anger" →
"feverish with anger" is a different sentence, and possibly a different label).

### DD6 — Label safety: three layers, one of them mechanical

12.6 froze a lexicon and said *never damage these tokens*. Here the whole point
is to touch signal vocabulary, so the guard has to be different in kind:

1. **Per-rule declared invariant.** Each rule states in its file that it changes
   neither tense, person, certainty nor polarity. Human-written, human-reviewed,
   and the thing a reviewer is actually reading.
2. **Mechanical structural invariance.** The sequence of `STRUCTURAL_FROZEN`
   tokens (`noise.py`) — negation, person, tense, modality — must be *identical*
   between a source line and every variant of it, compared after contraction
   normalisation so Tier A is not falsely flagged. This catches the dangerous
   cases cheaply: a rule that inserts "not", drops "my", or turns "had" into
   "have" fails at generation time.
3. **The existing lint, re-run over the expanded tree.** Filler purity,
   the cross-signal grid and the near-duplicate report. A **new** cross-signal
   hit that the source tree did not have is a hard failure: it means a
   substitution put another signal's language into a library declared silent on
   it.

Note what layer 2 does *not* catch: a Tier B swap that changes the referent
without touching a structural token. Only layer 1 and review catch that, and
that is the residual risk this ticket carries.

### DD7 — Expansion re-weights ideas, and the draw has to change

`select_fragments` draws the decisive fragment with
`rng.choice(signal_pools[label_mode])` — **uniform over fragments**. After
expansion, a line that expands twelve ways is twelve times more likely to be
drawn than one that expands twice. Short, simple, formulaic lines expand best,
so the generated dataset would skew towards exactly the sentences that are least
like real patient text — silently, with no number showing it.

The fix is a **two-stage draw**: uniform over clusters, then uniform over the
variants within the chosen cluster. That restores today's per-idea weighting
exactly, and at zero variants it is byte-identical to today's behaviour.

The alternative — capping every line at *k* variants — is worse: expandability
varies by line, so a fixed cap either wastes the good lines or pads the bad
ones.

### DD8 — Expand the training split only, and build the expanded test set as a probe

If both arms share a byte-identical test set, the comparison is clean and the
"did the test set get easier or harder?" question that makes 12.6's experiment a
2×2 across twenty runs simply does not arise. Cluster-based splitting makes this
safe: a cluster is wholly in one split, so expanding train touches nothing else.

Separately, an **expanded test set is the diagnostic** — see DD9. It is a probe,
not a training-set change.

### DD9 — The decision metric is a paraphrase-flip probe, not the 67 submissions

`holdout.py` says it plainly: the realistic set is a **validity** instrument and
gives roughly ±12 points overall, ±25 per signal. **It cannot rank arms.** So
the thing that decides this ticket cannot be "did the holdout number go up".

The probe instead: for *N* source lines from the test split, *k* authored
variants each; run the trained head over the source and its variants; the metric
is the **flip rate** — how often a variant gets a different predicted label from
its source. That has *N* × *k* structure rather than 67 observations, the effect
is directly the thing the ticket targets, and it needs no dataset regeneration
to run.

Four cells per signal: {baseline arm, expanded arm} × {clean test, expanded
test}. The baseline-arm / expanded-test cell is the diagnostic that says whether
the fault exists at all.

### DD10 — One signal first, and a diagnostic before any of it

Fever, all seven libraries, Tiers A and B. Nothing else until the probe reads
out. Seven signals of Tier B authoring before knowing whether the fault is
measurable is the expensive way to find out it was not.

### DD11 — Filler is the *last* priority here, not the first

12.1 says "start with the filler libraries, which carry no label weight". That
advice is right for **volume** — filler is where near-duplicates cost least. It
is wrong for **decorrelation**, which is this ticket's purpose: filler carries no
label, so expanding it cannot decorrelate anything. It buys surface variety in
the part of the text the model is meant to ignore. Worth doing eventually,
not worth doing first, and the two tickets should not be confused.

---

## 4. Tasks (provisional shape, for the stage-2 pass to expand)

**Task 0 — The diagnostic, before any code.** Hand-write ~40 variants over
existing *test-split* fever lines (roughly 10 source lines × 4). Run the
currently trained fever head over source and variants. Measure the flip rate.
No generator changes, no retraining, one afternoon.
**If flips are rare, stop: the ticket is not needed.** This task exists to be
allowed to fail.

**Task 1 — Rule format and expander.** The rule file (source phrase,
replacement, scope, declared invariant), the `expand` subcommand, the replica
tree, determinism and the pinned-digest CI check.

**Task 2 — Label-safety guard.** DD6 layers 2 and 3: structural-token
invariance against `STRUCTURAL_FROZEN`, and the lint re-run with new-hit-is-a-
failure semantics.

**Task 3 — Cluster propagation and the two-stage draw.** DD1 and DD7. This is
the task that touches `manifest.py` and `recombine.py`, and the one where a
mistake is silent.

**Task 4 — Author the fever rule set.** Tiers A and B across all seven fever
libraries, under DD5's all-classes rule.

**Task 5 — Two arms, trained, four-cell probe, report.**

**Task 6 — Conditional extension** to the remaining six signals and, if the
probe justifies it, Tier C.

Tasks 1–3 are the machinery and are signal-agnostic; Task 4 is the authoring
cost that repeats per signal.

---

## 5. Open questions for the review pass

1. **Is decorrelation the goal, or volume?** If the answer is volume, this
   ticket is the wrong mechanism and 12.1's template authoring is the right one.
   Everything above assumes decorrelation.
2. **Does DD5 stand?** Expanding every label class of a signal roughly doubles
   the authoring cost against the naive version. The alternative is not "half
   the benefit" — it is a net harm, so the honest options are all-classes or
   nothing.
3. **Committed expanded tree, or generated with a pinned digest?** (DD3.)
   Recommendation: pinned digest.
4. **How does this interact with the noise pass (12.6)?** Both multiply surface
   forms and neither has been measured. Running them together makes the result
   unattributable; running them in sequence doubles the compute. A defensible
   third option is that Tier A subsumes the cheapest and most valuable half of
   the noise pass — 12.6 itself says the apostrophe and casing operations are
   "the ones most worth having" — and that the 2×2 should wait for this probe.
5. **Where does this sit in 12.7's order?** It is not currently in the list. It
   competes for attention with steps 6 and 7 (`urinary_frequency`, the missing
   `false` submissions), both of which block *reading a result* rather than
   improving one, so the provisional answer is that it goes after them.
