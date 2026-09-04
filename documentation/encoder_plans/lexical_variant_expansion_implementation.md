# Implementation plan: lexical variant expansion (decorrelating vocabulary from label)

Read first: `arch_training.md` sections 2 (label first), 3 (cluster markers), 6
(splitting), 8 (the lint and its two blind faults), 10 (effective sample size),
12.6 (the noise pass — this is built in its shape), 12.7 (order of work). Then read
reports/encoder_training/2026-09-03-paraphrase-flip-diagnostic.md

---

# Plan

Take the vocabulary the fragment libraries already use and make the *choice of
word* non-informative about the label, by rewriting finished examples with
directional, scoped, literal substitutions.

**This adds no ideas and no effective sample size.** One line written twelve
ways is one idea. No report produced by this work may quote an example or
fragment count as growth; under the architecture below the expanded tree holds
*exactly* as many examples as the clean one, which makes that mistake hard to
make.

**What it does buy** is the removal of a measured fault. `arch_training.md` §8
records two cases where surface form separated a label class perfectly, both
caught by hand and neither catchable by any check we have. The review measured
the current libraries and found the *exclusive-token* shape of that fault
already fixed, but a *frequency-skew* shape alive in fever:

| token | true (96) | false (98) | hedged (73) | metaphor (55) | thirdparty (46) | historical (45) | attribution (50) |
|---|---|---|---|---|---|---|---|
| `fever` | 17 | 27 | 10 | 6 | 36 | 41 | 0 |
| `temperature` | 25 | 26 | 8 | 1 | 7 | **0** | 0 |
| `hot` | 32 | 23 | 13 | 12 | 0 | 0 | 16 |

`fever` is on 91% of `null_historical` lines and 18% of `fever_true` lines;
`temperature` is on 26% of decisive lines and no historical line at all. A model
can learn "temperature ⇒ decisive, fever ⇒ displaced" from that as easily as
from a token that appears in one file.

**Two gates before any of it is built**, and both are designed to be allowed to
fail. Task 1 measures the skew mechanically across all seven signals. Task 2
measures whether a trained head actually flips on paraphrase. If Task 1 shows
little skew and Task 2 shows few flips, **stop at Task 2** — the ticket is not
needed and the two reports are worth having anyway.

## The architecture, in one paragraph

Expansion is **post-processing over the generated JSONL**, in the shape
`scripts/synthetic_data/noise.py` already has, not a rewrite of the committed
fragment libraries. Editing library text changes each untagged line's cluster
key — `manifest.cluster_key` is `cluster_id or normalise(text)` — and therefore
its split, so a library-level expander silently repartitions the data and the
two arms stop being comparable. Post-processing touches no library file, so no
cluster key moves, no split moves, the generator stays byte-identical, the
golden digest holds, the decisive draw is untouched, and every expanded example
is *paired by `example_id`* with its clean original, which is what makes the
decision metric a paired statistic instead of a bespoke forty-line corpus.

---

# Scope

**In scope**

* A per-token label-association lint report over the committed libraries (Task 1).
* A paraphrase-flip diagnostic and its kill gate (Task 2).
* `scripts/synthetic_data/expand.py`: a rule format, a deterministic
  text-to-text pass, per-example RNG, a sidecar `expansion` block, and the
  tree/directory guards (Task 3).
* Rule-file validation: structural-token invariance, signal-lexicon match
  invariance, and a dry-run of the existing filler-purity and cross-signal
  checks over rule-rewritten library lines (Task 4).
* The `fever_present` rule set, Tiers A and B, directional in both directions
  (Task 5).
* Training-side wiring for an expanded test tree, and the four-cell measurement
  with a pre-registered guard (Task 6).
* One composite entry in the training run console's catalogue
  (`scripts/training_gui/runs.json`) that runs Task 6's whole sequence — smoke
  test, generate, expand, dry-run guard, the four cells, flip rate — in order
  (Task 6). Data only; no console code changes. See DD12.

**Out of scope**

* Tier C (aspect and opener rewrites). It needs per-library scoping, which the
  post-processing architecture cannot express, and it is where a label flip is
  most likely. If it is ever wanted it is a separate ticket with a different
  architecture.
* Any signal other than `fever_present` until Task 6 reads out (Task 7 is
  conditional).
* Expanding the filler libraries. Filler carries no label, so expanding it
  cannot decorrelate anything (provisional DD11, unchanged).
* The two-stage decisive draw. It is *not* a no-op today — `fever_null_*` and
  `dysuria_null_*` already carry multi-line clusters, so uniform-over-clusters
  re-weights the baseline and breaks the golden digest. It is arguably correct
  on its own merits and it is **its own ticket**.
* Editing `data/synthetic/*.txt`, the manifest, `manifest.py`, `recombine.py`
  or the generator in any way. Nothing in this plan touches them.
* Running expansion and the noise pass (12.6) together. See DD9.

---

# Design decisions

Numbered afresh. Where one supersedes a provisional decision it says so.

### DD1 — Expansion is post-processing over the JSONL tree

*Supersedes provisional DD1, DD3 and DD7, which the review's F1, F2 and F3
between them removed the need for.*

`expand.py` reads a generated tree and writes a parallel tree with the same
filenames, the same `example_id`s, the same `labels`, the same `meta` and the
same sidecar provenance — only `text` differs. This is `noise.py`'s contract and
the reasons §12.6 gives for it apply here verbatim.

What this buys, stated so it is not re-litigated:

* **No split moves.** No library file is touched, so no cluster key changes.
* **No re-weighting.** The decisive draw never sees the pass.
* **Cluster propagation is free.** The example already carries its source
  fragments' cluster keys in the `fragments` provenance block.
* **The output is git-ignored.** `data/synthetic/generated/` already is, so the
  "commit the tree or pin a digest" question does not arise. The rule file is
  the reviewable artefact.
* **The probe is paired.** `--test-dir` already exists and
  `swap_test_split` already replaces each fold's test split with another tree's,
  so flip rate is computed over matched pairs.

The cost is that a rule cannot be scoped to a *library*: the example text
carries no character offsets back to its source fragments. That is what puts
Tier C out of scope, and Tiers A and B are class-agnostic anyway (DD4).

### DD2 — Rules are literal, directional, whole-word, and scoped to a signal

*Provisional DD2, narrowed from library scope to signal scope by DD1.*

A rule is a triple plus a declared invariant: a literal source phrase, a literal
replacement, and the signal whose tree it may run against. Never a regex over
the tree, never a symmetric synonym bag — `fever_true` contains "I checked my
temperature and it was high" and the reverse of a naive `temperature ⇄ fever`
set produces "I checked my fever and it was high".

Matching is **whole-word only**. §8 already records why: "hot" matches inside
`lithotripsy`, `photos` and `shot`.

**Both directions are usually needed, and this is the correction the review
made.** Flattening the table above needs `fever → temperature` *and*
`temperature → fever`, because `null_historical` over-uses the first exactly as
`fever_true` over-uses the second. Each direction is a separate rule with its
own declared invariant and its own safety review; neither implies the other.

### DD3 — A rule fires per match site, not per example, and the draw never sees the label

For each example the pass draws its own RNG from `example_id` (`noise.example_rng`),
draws a clean-share coin first, then walks the text left to right collecting
non-overlapping whole-word match sites (longest match wins at a position, so
"a high temperature" beats "temperature"). Each site is applied independently
with probability `--rate`, choosing among the rules matching there by weight.

Nothing in that decision path reads `labels` or `meta.label_mode`, and a test
asserts it — the same posture `noise.py` takes, and the mechanical half of what
provisional DD5 asked for.

### DD4 — Two tiers, both class-agnostic

*Provisional DD4's Tier C is dropped; see Scope.*

| Tier | What it swaps | Semantic risk |
|---|---|---|
| **A** | Orthography and contraction: `I've`↔`I have`, `haven't`↔`have not` | none — cannot change which word a token is |
| **B** | Signal vocabulary: `fever`↔`temperature`↔`high temperature` | real but boundable, and DD5/DD6 bound it |

Tier A is **not** subsumed by the noise pass. `noise.drop_apostrophe` produces
`Ive`, an error; Tier A produces `I have`, a valid alternative form. Only the
second decorrelates register, which is the fault §8's second case records.

### DD5 — A signal is expanded across every label class, and the pass cannot do otherwise

*Provisional DD5, promoted from a review discipline to a property of the
architecture.*

Because rules are scoped to a signal and applied to whole example text with no
sight of the label, a rule **cannot** be applied to `true` examples and not to
`null` ones. The trap the provisional plan correctly identified — a partial pass
manufacturing exactly the shortcut the ticket exists to remove — is closed by
construction rather than by a scope check.

It is still *measured*: the sidecar reports realised substitutions per hundred
words by label and by label mode, exactly as `noise.py` reports edit rate. A
skew there is telemetry about the libraries (a class whose lines simply contain
fewer matchable phrases), not a label-aware pass, and the report must say so.

### DD6 — Label safety: three layers, two of them mechanical and both at rule-validation time

*Provisional DD6, with layer 3 retargeted from the tree to the rules.*

1. **Per-rule declared invariant.** Every rule carries a written statement that
   it changes neither tense, person, certainty nor polarity. Human-written,
   human-reviewed, and the thing a reviewer actually reads. This is the residual
   risk: nothing mechanical catches a Tier B swap that changes the referent
   without touching a structural token.
2. **Structural-token invariance.** The sequence of `noise.STRUCTURAL_FROZEN`
   tokens must be identical between `find` and `replace`, compared after
   contraction normalisation so `haven't → have not` is not falsely flagged.
   Checked when the rule file loads, so a rule that inserts "not", drops "my" or
   turns "had" into "have" fails before a single byte is written.
3. **Signal-lexicon invariance.** Using `lint.lexicon_matches`, a rule must not
   change whether its phrase matches **its own** signal's lexicon, and must not
   introduce a match for **any other** signal's lexicon that `find` did not
   have. That is the mechanical core of the provisional plan's "re-run the lint
   over the expanded tree", done per-rule: cheaper, more precise about which
   rule is at fault, and it catches the one thing the tree re-run was for — a
   substitution putting another signal's language into a library declared silent
   on it.

Layer 3 is supplemented by Task 4's dry-run, which applies the rules to the
library lines and re-runs filler purity and the cross-signal grid on the result.
A new cross-signal hit that the source tree did not have is a hard failure.

### DD7 — The decision metric is a paired flip rate, with a pre-registered accuracy guard

*Provisional DD9, with the guard the review's F5 says is missing.*

**A model that answers `null` to everything has a flip rate of zero.**
`arch_training.md` §10 records that the companion run needed decisive-cell
accuracy to rule out exactly that, because two thirds of the cells are `null`
and a silent arm clears any `null`-driven criterion. So:

* **Primary:** flip rate — the share of *changed* pairs whose predicted class
  differs between the clean and expanded test trees. Unchanged pairs are
  excluded from the denominator; a substitution-free example cannot flip and
  including it only dilutes.
* **Guard, pre-registered before training:** decisive-cell accuracy on the
  **clean** test tree must not fall by more than the declared bound. An arm that
  lowers flip rate while losing decisive accuracy is a loss, not a win.
* **Resampling unit is the cluster, not the example.** Examples share decisive
  fragments, so example-level bootstrap understates the interval
  (`arch_training.md` §10). The `fragments` provenance block gives cluster
  membership.

### DD8 — Pre-register "nothing moves" on the synthetic test set

The clean synthetic test set is drawn from the same libraries under the same
vocabulary, so it **cannot contain** the failure this ticket targets. This is
the negative control 2026-08-19 described: "a large synthetic gain would have
meant a new shortcut rather than a removed one". Write that expectation down
before training, so a synthetic gain is read as the warning it is.

Two smaller measurement notes:

* **Flip rate needs no labels**, so measuring it on the 67 real submissions
  costs the holdout nothing as a *descriptive* diagnostic. It would cost the
  holdout its validity if used to *choose between arms*. Task 2 has no arms to
  choose between and should therefore use real text, which is where the register
  gap actually lives. Arm selection in Task 6 stays on the synthetic tree.
* The 67 submissions cannot rank arms (±12 overall, ±25 per signal —
  `holdout.py`). They are a validity instrument here as everywhere.

### DD9 — Expansion and the noise pass do not run together, and 12.6 goes first

Both multiply surface forms; running them in the same experiment makes the
result unattributable. `expand.py` therefore **refuses a tree that already
carries a `noise` block**, and vice versa is documented rather than enforced
(the noise pass is not edited by this plan).

`arch_training.md` §12.7 item 1 is closing the noise 2×2's one open cell, which
is two evaluations and no new dataset. It is built, measured and positive; this
is unbuilt. It goes first.

If the two are ever combined, the order is **expand then noise**: paraphrase
first, damage the final surface second.

### DD10 — One signal, and the pilot signal is chosen by Task 1

*Provisional DD10, with the choice of signal handed to the measurement.*

The provisional plan picked `fever` because it is the signal the §8 faults were
found in. The review's measurement suggests fever's exclusive-token fault is
already fixed, though its frequency skew is real and large. Task 1 ranks all
seven signals by skew; **the pilot is the top-ranked signal**, which will
probably but not necessarily be fever. Everything downstream is written against
`fever_present` and moves by changing one argument.

### DD11 — Where the files live

`data/synthetic/` is guarded by a test asserting nothing but libraries and the
manifest lives there. The rule files therefore live **outside** it, at
`data/expansion/<signal>.rules.json`. Getting this wrong fails CI, which is the
intended behaviour and the reason it is written down here.

### DD12 — Task 6 runs from one console entry, and that costs no code

The training run console (`architecture.md` 3.17) chains steps by listing argv
vectors in `scripts/training_gui/runs.json`; `runner.py` loops over them and
stops the run on the first failing step. **Nothing in `scripts/encoder_training/`
does the chaining**, so Task 6's sequence — smoke test, generate the clean tree,
expand it, dry-run the rules against the library lint, four `finetune`
invocations, `flip-rate` — becomes one button for the cost of a JSON entry and
no console code at all.

Two consequences worth stating so they are not mistaken for each other:

* **Sequencing is free; single-invocation comparison is not.** `declarative-compare`
  exists in the training CLI because 12.6's paired statistics can only be
  computed inside the invocation that produced the models. Task 6 does **not**
  need that: its flip rate is computed post hoc by `flip.py` over two matched
  trees' written predictions (instruction 5), so a catalogue entry is sufficient
  and no `lexical-compare` subcommand should be written.
* **The catalogue admits only `-m` module invocations with literal or
  enumerated arguments.** `expand.py` follows `noise.py`'s template and so is
  reachable as `python -m scripts.synthetic_data.expand`, which satisfies that
  rule. Nothing in this plan needs a free-text path to reach the console.

The entry is authored once Task 1 names the pilot signal (DD10), with that
signal, its tree paths and its rule file as literals rather than as a dropdown.
If Task 7 goes ahead it becomes a `signal` parameter with the extended signals as
its committed `choices`.

---

# Task 1: Per-token label-association lint report

**A. State of the world.** Nothing in this plan is built. `arch_training.md` §8
lists six lint reports and states that a token confined to one library — the
`dysuria_null_metaphor` fault — "would not be caught by any check we have". This
task builds that check. It needs no training, no GPU and no ML wheels, runs over
all seven signals at once, and is worth keeping whatever happens to the rest of
this ticket. **It is also the first of the two gates: if it shows little skew
anywhere, say so and stop for a decision.**

**B. Files and deliverables.**

* `scripts/synthetic_data/lint.py` — new report: `token_label_association()` and
  `render_token_association()`.
* `scripts/synthetic_data/__main__.py` — wire the new section into
  `render_report`'s output.
* `tests/test_synthetic_recombination.py` — tests (unit; no
  `pytestmark` needed, no DB).
* `documentation/arch_training.md` — §8 gains a seventh report; the sentence
  saying the fault is uncatchable is corrected.
* `reports/synthetic_data/<date>-token-label-association.md` — the committed
  output over the current tree, all seven signals. A terminal scrollback is not
  where the input to a signal-selection decision lives.

**C. Instructions.**

1. Group each signal's libraries into three label classes from `fragment_type`:
   `positive → true`, `negative → false`, everything else → `null`. Filler
   libraries are not part of any signal's grouping.
2. For every token (lowercased, apostrophes folded — reuse `noise.fold_token` or
   `normalise`, do not write a third tokeniser), compute its **per-line rate** in
   each class: lines containing the token, over lines in the class. Rates, not
   counts: the classes have different sizes and raw counts mislead.
3. Rank by a skew statistic over the three rates. Keep it simple and explainable
   — max rate minus min rate, with a minimum-support floor (a token on fewer
   than five lines total is noise) — and print the statistic's definition in the
   report header rather than leaving a reader to infer it.
4. Print two blocks per signal, apart and labelled, because they are different
   faults: **tokens confined to one label class** (the §8 fault) and **tokens
   present in every class but skewed** (the fault the review found). Cap the
   detail lines the way `NEAR_DUPLICATE_DETAIL_LIMIT` does and say how many were
   elided.
5. The header must say what the report cannot see: it is per-token and
   per-library, so it is blind to multi-token style and register — §8's second
   fault, the lowercase library, would not appear here. Do not let this report
   be read as a clean bill of health.
6. Expect the axis words to dominate the "confined to one class" block — `she`
   and `he` in `thirdparty`, `ago` in `historical`, `might` in `hedged`. Those
   are the sub-class doing its job, not a fault. The report should not try to
   filter them out (any filter would be a clinical judgement in code); the
   header should tell the reader to expect them.
7. Tests: a fixture where one token is confined to one class and is ranked
   first; a fixture where rates are equal and nothing is flagged; the
   minimum-support floor; and a trap test over the *real* committed tree
   asserting the report runs and produces the axis words, so a future tokeniser
   change is visible.
8. Write the report file, and in it state which signal ranks top on skew. That
   choice is DD10's input to Task 5.

---

# Task 2: The paraphrase-flip diagnostic, and the kill gate

**A. State of the world.** Task 1 is complete and has ranked the signals by
lexical skew. Nothing else is built. This task answers the question Task 1
cannot: does a *trained head* actually change its answer when the vocabulary
changes? **This task exists to be allowed to fail.** If flips are rare, stop and
report; the ticket is not needed.

Note a practical constraint discovered in review: **the fine-tuned encoder
weights are not committed** (`models/encoder/<signal>/arm_b_finetune/fold*.head.json`
records `encoder_weights_committed: false`, and the ~440MB `weights/` directories
are git-ignored). This task therefore runs on a machine that still holds those
weights, or after retraining a single fold — one fold is ample for a diagnostic.

**B. Files and deliverables.**

* `scripts/encoder_training/flip.py` — new module: load a set of texts, score
  them through an injected scorer, apply a decision rule, and compute flip rate
  with a cluster-resampled interval. Standard library plus the existing
  `metrics` helpers only; the forward pass is **injected**, exactly as
  `holdout.py` does it, so CI's no-GPU unit job can cover everything that
  decides what the number means.
* `scripts/encoder_training/__main__.py` — a `flip-rate` subcommand.
  **Do not call it `probe`**: that name is already taken by Arm A.
* `data/realistic/uti1_paraphrases.tsv` (or similar) — the hand-written
  paraphrase set: for each chosen submission, the original plus *k* variants.
* `tests/test_encoder_training_flip.py` — unit tests.
* `reports/encoder_training/<date>-paraphrase-flip-diagnostic.md` — the result
  and the go/no-go.

**C. Instructions.**

1. Build the paraphrase set by hand over the **67 real submissions**, not over
   test-split fragments. Real text is where the register gap lives, and flip
   rate needs no labels, so this consumes none of the holdout's validity as a
   descriptive measurement (DD8). Roughly 10–15 submissions × 3–4 variants.
   Vary *only* vocabulary and orthography — a variant that changes tense,
   person, certainty or polarity is a different claim and must not be in the
   set. Record each variant's source id so pairing is explicit in the file.
2. `flip.py` takes `(texts) -> {signal: per-class scores}` — the same callable
   shape `holdout.score_holdout` takes, which `train.encoder_scorer` already
   produces. Do not import torch in this module.
3. The metric: for each (source, variant) pair, apply the fold's decision rule
   to both and compare predicted classes. Report overall flip rate, the flip
   *direction* matrix (which class went to which — 12.6 found decisive recall
   draining into `null`, and the direction was the useful half of that finding),
   and per-signal rates.
4. Interval: resample at the **submission** level, since the realistic set has
   no cluster structure and one submission's variants are not independent of one
   another (`holdout.py`'s rule 5). Reuse `metrics`' existing bootstrap.
5. Report honestly on power. Ten submissions × four variants is 30-ish paired
   observations; that can separate "flips are common" from "flips are rare" and
   nothing finer. Say so in the report rather than quoting a precise rate.
6. **Write the gate down before running it.** Something of the form: if the flip
   rate over paraphrase pairs is below *X*% and Task 1 showed no signal with a
   skew above *Y*, the ticket stops here. Choose *X* and *Y* and commit them
   before scoring, then report against them.
7. Tests: a fixture scorer with hand-made scores, asserting flip rate and the
   direction matrix; the submission-level resampling unit; and that a malformed
   paraphrase file (a variant with no source, a source with no variants) is a
   hard error rather than a silently smaller set.

---

# Task 3: `expand.py` — the post-processing pass

**A. State of the world.** Tasks 1 and 2 are complete and the gate was passed:
there is measurable skew and measurable flip. Nothing of the expansion machinery
exists. `scripts/synthetic_data/noise.py` is the template for this task in the
strongest sense — read it before writing anything, and mirror its structure,
its guard posture and its docstring discipline rather than inventing a second
idiom for the same job.

**B. Files and deliverables.**

* `scripts/synthetic_data/expand.py` — the rule format, the loader and its
  validation, the text-to-text pass, the directory pass, the sidecar block, the
  guards, and an argparse `main`.
* `data/expansion/README.md` — what a rule file is and what the declared
  invariant means. (DD11: **not** under `data/synthetic/`.)
* `tests/test_synthetic_expand.py` — unit tests.
* `documentation/arch_training.md` — a new §12 subsection for this pass.

**C. Instructions.**

1. **Rule file format**, JSON, one file per signal:
   ```json
   {
     "signal": "fever_present",
     "rules": [
       {
         "id": "fever-to-temperature",
         "tier": "B",
         "find": "a fever",
         "replace": "a temperature",
         "weight": 1.0,
         "invariant": "Both are bare noun phrases naming the same state; changes neither tense, person, certainty nor polarity."
       }
     ]
   }
   ```
   Closed key set — an unknown key is an error, not a comment, for the reason
   `_NULL_ON_KEYS` is closed. `invariant` is required and must be non-empty;
   a rule with no written justification is the one thing no check can recover.
   Duplicate `id`s are an error.
2. **Rule validation at load time**, all of it before any file is written:
   * whole-word matchability (`find` must not be empty or start/end mid-word);
   * DD6 layer 2 — `STRUCTURAL_FROZEN` token sequence identical between `find`
     and `replace` after contraction normalisation. Import `STRUCTURAL_FROZEN`
     from `noise.py`; do not copy it, and do not let a second list start drifting;
   * DD6 layer 3 — `lint.lexicon_matches` match-*status* for the rule's own
     signal is equal for `find` and `replace`, and no *other* signal's lexicon
     matches `replace` that did not match `find`;
   * the error message names the rule id, the layer that rejected it and why.
     A rule file is authored by a human and rejected messages are the whole
     of that person's feedback loop.
3. **The pass.** `expand_text(text, rules, rng, rate)`, pure and file-free, in
   the shape of `damage_text`. Per DD3: clean-share coin first, then
   left-to-right non-overlapping match sites, longest match first at a position,
   each site applied independently at `--rate`, weighted choice among rules
   matching there. Preserve the source's leading capitalisation on the
   replacement — matching is case-insensitive, output is not.
4. **The directory pass**, mirroring `noise_tree`: same filenames, `RECORD_KEYS`
   order preserved so a diff against the clean tree shows only `text`,
   `example_id`/`split`/`labels`/`meta` copied through untouched, sidecar written
   beside each file.
5. **Guards**, all startup errors, all modelled on `check_directories` and
   `check_tree`:
   * in-dir and out-dir both under `data/synthetic/generated/`, not equal, not
     nested — reuse `noise.check_directories` if it generalises cleanly, else
     mirror it;
   * refuse a tree already carrying an `expansion` block (expanding twice
     compounds in a way no rate describes);
   * refuse a tree carrying a `noise` block (DD9 — unattributable);
   * refuse a tree whose sidecar `signal` has no rule file;
   * refuse sidecars that disagree on `TREE_AGREEMENT_FIELDS`.
6. **The sidecar `expansion` block**: requested rate, clean share, seed, rule
   file path and its digest, per-rule application counts, sites rejected and
   why, and — the DD5 instrument — realised substitutions per hundred words
   **by label and by label mode**. `_read_stats` only checks for required keys,
   so an extra top-level block is additive and safe.
7. **Determinism**: same tree, same rules, same seed, same bytes. Test it.
8. **The label-blindness test**: assert that `expand_text` and the site-selection
   path never read `labels` or `meta`. Write it the way `noise.py`'s equivalent
   is written — the property is the whole safety argument, and §2 is what it
   protects.
9. Tests: rule validation rejecting each of the three layers with a distinct
   message; whole-word matching not firing inside a longer word; longest-match
   precedence; capitalisation preservation; determinism; every guard; the
   sidecar's per-label block; and a round-trip asserting `example_id`, `labels`
   and `meta` are byte-identical between the clean and expanded trees.

---

# Task 4: Rule-file dry-run against the library lint

**A. State of the world.** Task 3 is complete: rules load, validate per-rule and
rewrite trees. What per-rule validation cannot see is an *aggregate* effect — a
rule that is individually harmless but, applied across a library, puts another
signal's language somewhere that library is declared silent about. This task is
DD6 layer 3's supplement.

**B. Files and deliverables.**

* `scripts/synthetic_data/expand.py` — a `--dry-run-lint` mode.
* `tests/test_synthetic_expand.py` — tests.
* `documentation/arch_training.md` — a paragraph in the new subsection.

**C. Instructions.**

1. Load the committed libraries through `manifest.load_fragments` with
   `check_cells=False` — same posture as the lint, for the same reason.
2. Apply every rule to every line **unconditionally** (not at `--rate`): this is
   the worst case, and the worst case is what you want to check.
3. Run `lint.filler_lexicon_hits` and `lint.cross_signal_cells` over the
   rewritten fragments and diff against the same two run over the originals.
4. **A new filler-purity hit is a hard failure.** **A new cross-signal hit is a
   hard failure** here even though the ordinary cross-signal report only
   reports — the difference is that an existing hit is a labelling decision
   somebody made, and a new one was manufactured by a rule.
5. Print removed hits too. A rule that makes an existing hit disappear has
   changed what a library says and wants reading, even though it is not a
   failure.
6. This mode reads libraries and writes nothing. Say so in the docstring, and
   keep it in `expand.py` rather than `lint.py`: the lint's contract is that it
   reports on the tree as committed.
7. Tests: a rule that introduces a foreign-signal match fails and names the rule
   and the pair; a rule set that changes nothing passes with an empty diff; the
   mode writes no files.

---

# Task 5: Author the `fever_present` rule set

**A. State of the world.** Tasks 1–4 are complete: the machinery exists,
validates and dry-runs. This task is the authoring cost, and it is the one that
repeats per signal. Task 1's report says which signal ranks top on skew and
therefore which signal this is actually for — the instructions below say
`fever_present`, and if Task 1 ranked another signal first, substitute it and
say so in the commit.

**B. Files and deliverables.**

* `data/expansion/fever_present.rules.json` — the rule set.
* `reports/synthetic_data/<date>-fever-expansion-rules.md` — the authoring
  rationale: which skews from Task 1 each rule targets, and the dry-run output.
* `tests/test_synthetic_expand.py` — a test that the committed rule file loads
  and passes all three validation layers and the dry-run lint, against the real
  tree. This is the guard that a future library edit does not quietly invalidate
  a rule.

**C. Instructions.**

1. Work from Task 1's ranked skew list, not from intuition. The point is to
   flatten measured skews; a rule for a word that is already evenly distributed
   is authoring cost for nothing.
2. **Tier A first** — contraction and orthography pairs, in both directions.
   These are close to free, cannot change which word a token is, and are the
   direct answer to §8's casing fault.
3. **Tier B, in both directions** (DD2). For fever the table in the Plan section
   says the work: `fever → temperature` matters most in `null_historical` and
   `null_thirdparty`, `temperature → fever` in `fever_true` and `fever_false`.
   Because the pass is class-blind, you author the pair and the classes take
   care of themselves.
4. Write a real `invariant` for every rule. "Same thing, different word" is not
   one. Name what is preserved: tense, person, certainty, polarity.
5. Watch the metaphor and attribution libraries hardest. "Burning up with anger"
   → "feverish with anger" is a different sentence and possibly a different
   label. If a phrase only reads safely inside a clinical frame, the rule's
   `find` should carry enough of that frame to be safe everywhere — literal
   phrases are longer than single words for exactly this reason.
6. Run `--dry-run-lint` and paste its output into the report file. If it fails,
   the rule is wrong; do not baseline it.
7. Re-run Task 1's report over the rule-rewritten libraries and put the
   before/after skew table in the report. That is the direct evidence the rules
   do what they were authored to do, and it costs one command.

---

# Task 6: Two arms, four cells, and the read-out

**A. State of the world.** Tasks 1–5 are complete: rules exist and are validated.
Nothing has been trained. This is the measurement, and it is the expensive task
of this plan — though "expensive" here means well under an hour of GPU, not
12.6's four. **Twenty trainings, not ten**: see the correction in instruction 3.

**B. Files and deliverables.**

* `scripts/encoder_training/__main__.py` — `_test_dataset_header` learns to
  record an `expansion` block from the test tree's sidecar, beside the `noise`
  block it already records.
* `scripts/encoder_training/flip.py` — extended to compute the paired,
  cluster-resampled flip rate over two matched JSONL trees (Task 2 built the
  unpaired real-text version).
* `reports/encoder_training/<date>-lexical-variant-preregistration.md` —
  **committed before the first training run.**
* `reports/encoder_training/<date>-lexical-variant.md` and its JSON — the result.
* `scripts/training_gui/runs.json` — one composite entry running the whole
  sequence below (DD12). Data only; no change to `catalogue.py`, `server.py`,
  `runner.py` or the page.
* `tests/test_training_gui.py` — the catalogue-shape assertions for that entry.
* `documentation/arch_training.md` §10 and §12 — the finding, and whether the
  pass is adopted.

**C. Instructions.**

1. **Pre-register first, in a committed file, before any GPU time**: the flip-rate
   bound that counts as success, the decisive-accuracy guard bound (DD7), and
   DD8's explicit statement that the expected synthetic movement is *nothing*
   and that a large synthetic gain is evidence of a new shortcut. §12.9's "declare
   a bound before you train" is the precedent and it is not optional here.
2. Generate once, expand once. One generation run yields the clean tree;
   `expand.py` yields the expanded tree from it. Both arms therefore share
   provenance and neither can differ by a generator change.
3. **Expand the training split only** for the training arm; the clean and
   expanded *test* trees are both used as test sets, via `--test-dir`, in all
   four cells. Cells are (train tree × test tree):

   | | clean test | expanded test |
   |---|---|---|
   | **clean-trained** | today's baseline | *the diagnostic cell — does the fault exist?* |
   | **expanded-trained** | the guard cell | the robustness cell |

   **Twenty trainings, not ten.** An earlier draft of this plan said ten, on the
   reasoning that training depends only on the training tree and so one trained
   model could be scored against both test trees. That is true of the *models*
   and false of the *CLI*: `--test-dir` is a single `Path`
   (`scripts/encoder_training/__main__.py`), not a repeatable one, so each cell
   is its own `finetune` invocation and each invocation trains its own five
   folds. Four cells × five folds = twenty trainings.

   This is left as twenty rather than fixed. At one signal and five folds a cell
   is roughly ten minutes, so the whole measurement is ~40 minutes of GPU;
   teaching `--test-dir` to repeat would save about twenty minutes and cost a
   change to the training CLI's evaluation path, which is not a trade worth
   making for one experiment. What matters is that **the pre-registration and any
   time estimate say twenty**, because a plan that budgets half the GPU time it
   needs is how a measurement gets cut short.
4. Wire `_test_dataset_header` to record the expanded tree's `expansion` block —
   rate, clean share, rule-file digest, seed — the way it already records
   `test_dataset_noise`. A report that cannot say which tree it was scored
   against is not a result.
5. Compute the paired flip rate between the clean-test and expanded-test
   predictions of the *same* arm, over pairs the pass actually changed, resampled
   at the **cluster** level (DD7). The `fragments` provenance block gives cluster
   membership; do not resample examples.
6. Score the guard: decisive-cell accuracy on the clean test tree, both arms,
   against the pre-registered bound.
7. Also score the realistic set for both arms, and report it **as a validity
   check only** — ±12 overall and ±25 per signal cannot rank arms
   (`holdout.py`). It is there to catch the large failure, not to pick a winner.
8. **Add the composite catalogue entry** (DD12), before the first real run, so
   the measurement is one button and the sequence is committed rather than
   retyped. Steps, in order:

   1. `smoke-cuda` — ten seconds, and it fails immediately on a broken driver.
   2. `generate-folds --folds 5 --signal <pilot> --out-dir <clean tree>`.
   3. `python -m scripts.synthetic_data.expand` over the clean tree, writing the
      expanded tree.
   4. `python -m scripts.synthetic_data.expand --dry-run-lint` against the rule
      file (Task 4). Seconds, writes nothing, and it fails the run before any GPU
      time if the rule file has drifted since Task 5 validated it. Putting a
      guard *inside* the sequence is the point of having a sequence.
   5. The four `finetune` invocations, one per cell, in the table's order.
   6. `flip-rate`.

   Every path is a literal; the entry takes no parameters. Add the two
   catalogue-shape tests the console's suite already has an idiom for: that the
   `--data-dir` and `--test-dir` values across the four training steps are
   exactly the two trees steps 2 and 3 write, and that step 1 is the smoke test.
   The first is the one that matters — it catches a cell pointed at the wrong
   tree in CI, in a second, instead of in a report that silently compares a tree
   against itself.

9. Write the report against the pre-registration, item by item, including the
   items that failed. Note in it that effective sample size is identical in every
   cell — expansion creates no clusters — so a gain can only mean robustness to
   paraphrase, never better coverage. State the GPU cost as twenty trainings.

---

# Task 7: Conditional extension (do not start until Task 6 reads out)

**A. State of the world.** Task 6 is complete and its report either justifies
extension or does not.

**B. Files and deliverables.** `data/expansion/<signal>.rules.json` per signal,
each with its dry-run output and before/after skew table; `arch_training.md`
updated.

**C. Instructions.**

1. Order the remaining six signals by **Task 1's skew ranking**, not by signal
   order and not by how easy the authoring looks.
2. Everything from Task 3 and 4 is signal-agnostic and already built; per signal
   this is Task 5 repeated plus one more arm if a per-signal measurement is
   wanted. It probably is not — one signal's read-out is what the pilot was for.
   If a per-signal measurement *is* wanted, Task 6's composite catalogue entry
   gains a `signal` parameter whose `choices` are the extended signals, rather
   than being copied per signal (DD12).
3. Do not extend to Tier C without a new plan. It needs per-library scoping,
   which this architecture cannot express, and it is where a label flip is most
   likely.
4. Re-read `arch_training.md` §12.7 before starting: this competes for attention
   with steps that block *reading* a result rather than improving one, and those
   come first.

---

# Testing and documentation obligations

Per `CLAUDE.md` and `arch_training.md` §12:

* Every test file in this plan is a **unit** test — no database, no GPU, no ML
  wheels. None needs `pytestmark = pytest.mark.integration`, and none needs a
  change to `ci.yml` or the `Makefile`. `tests/test_synthetic_expand.py` and
  `tests/test_encoder_training_flip.py` are picked up by the existing
  `pytest tests/ -m "not integration"` job.
* `tests/test_synthetic_recombination.py` already runs in CI's ruleset job
  against the committed tree; the Task 1 report's trap test belongs there.
* Task 6's catalogue-entry assertions go in the existing
  `tests/test_training_gui.py`, which is already a unit test file in the same
  job. They read `runs.json` and assert its shape; they start nothing.
* `arch_training.md` is updated **within** the task that changes the behaviour,
  not in a documentation task at the end: §8 in Task 1, a new §12 subsection in
  Task 3, a paragraph in Task 4, §10 and the adoption decision in Task 6.
* Per-chat testing follows `CLAUDE.md`: typecheck and run only the touched test
  files; skip the full suite and `npm run build`; CI's unit job is the gate.

# What this plan deliberately does not do

* It does not touch `manifest.py`, `recombine.py`, the manifest, or any `.txt`
  library. Every dataset and number produced to date stays reproducible.
* It does not change the decisive draw. The two-stage draw is a real idea and a
  separate ticket.
* It does not claim expansion adds data. It adds none, and every report in it
  has to say so.
