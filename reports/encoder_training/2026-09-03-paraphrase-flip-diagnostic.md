# The paraphrase-flip diagnostic — 2026-09-03

Task 2 of the lexical variant expansion plan, and the second of its two gates.
**This document is the pre-registration.** The gate below (plan instruction 6)
is written and committed *before* any model is scored; the results section is
empty on purpose and is filled in by the run the last section describes.

Task 1 (`reports/synthetic_data/2026-09-03-token-label-association.md`) measured
the libraries and found the largest content-word association in the tree:
`fever` on 41 of 45 `fever_null_historical` lines and 0 of 50
`fever_null_attribution` ones, a within-`null` skew of 0.911. That is a fact
about the data. It is not evidence that a trained head *uses* the association.
This task asks the head directly, and it is built to be allowed to come back
negative: if a head barely changes its answer when only the vocabulary changes,
the expansion pass is not worth building and the ticket stops here.

## What is being measured

One real submission, rewritten three ways so that only its **vocabulary and
orthography** change. The fold's own decision rule is applied to the original
and to each rewrite, and the pair **flips** when the two predicted classes
differ. A flip is an error on one side of the pair, whichever side that is, and
seeing one needs no label — which is what makes this cheap: `uti1_holdout.labels.tsv`
is never opened, so the diagnostic costs the holdout nothing as a descriptive
measurement (plan DD8). It would cost the holdout its validity the moment a flip
rate were used to choose between two arms. Nothing here does that; the arm
comparison in Task 6 runs on the synthetic tree.

## The set

`data/realistic/uti1_paraphrases.tsv` — **13 submissions × 3 variants = 39
pairs**, over the real submissions rather than over test-split fragments,
because real text is where the register gap lives.

| column | what it is |
|---|---|
| `variant_id` | `holdout-NNNN-src` for the original, `holdout-NNNN-vK` for a rewrite |
| `submission_id` | the pairing key, and the resampling unit |
| `kind` | `source` or `variant` |
| `text` | one line, no tabs |

The `source` rows are the submissions **verbatim**, typos and all, and
`flip.load_paraphrases` checks them character for character against
`uti1_holdout.source.txt` on every load. That check is the thing that keeps this
a measurement of real text: a source tidied up on its way into the file measures
a rewrite against a rewrite, and the tidying is precisely the register axis being
probed.

The 13 were chosen for fever vocabulary, since `fever_present` is the pilot
signal Task 1 recommended: submissions 4, 6, 9, 13, 14, 17, 21, 24, 30, 31, 38,
41 and 52 between them carry `fever`, `temperature`, `high temperature`,
`feverish`, `hot`, and three explicit denials (`no fever`, `No fever or flank
pain`, `No fever yet`). The variants move that vocabulary in both directions —
`fever → temperature`, `temperature → fever`, both → `hot`/`running hot` — and
move the other signals' words too (`peeing`/`urinating`/`passing water`,
`urine`/`wee`, `flank`/`side`), so the same set says something about every head
in a joint checkpoint.

**What a variant may not change: tense, person, certainty, polarity.** A denial
stays a denial (`No blood, no fever` → `No blood, no high temperature`), a hedge
stays a hedge, and a first-person report stays first-person. That constraint is
enforced by hand review, not by code — the mechanical invariants in the plan's
DD6 belong to the rule files of Task 4, which do not exist and which this task
may well conclude are not needed.

**Provenance, carried into every number quoted from this set.** The variants
were written by Claude and reviewed by the maintainer. They are one model's idea
of which words are interchangeable, scored against a head built by the same
architecture. A flip found here is real — the two texts make the same claim and
the head answered differently. A flip *not* found here is weaker evidence,
because the variants may simply have failed to move the vocabulary the head is
actually reading.

## Power, stated before the numbers rather than under them

39 pairs, but the resampling unit is the **submission**: three rewrites of one
sentence are not three independent observations. So the effective *n* is 13, and
a 95% interval on a proportion at that *n* is worth roughly ±27 points at worst.

**This can separate "flips are common" from "flips are rare" and nothing finer.**
Any reading of the eventual number to the point is over-reading it, and the
report that records the result must quote the interval, not the point estimate
alone.

## The gate, pre-registered

The plan's instruction 6 asks for a gate of the form *"if the flip rate is below
X% and Task 1 showed no signal with a skew above Y, the ticket stops here"*.
**That two-clause form is now vacuous and is not what is being pre-registered
here**, which is worth saying plainly rather than quietly rewriting: Task 1 has
already read out at 0.911, so for any Y a reader would accept, the second clause
is false and the ticket could never stop no matter what the flip rate turned out
to be. The Y clause was written when Task 1's answer was unknown. It has been
answered, and the remaining decision rests on the flip rate alone.

So, committed before scoring:

| outcome | flip rate over the 39 pairs | what happens |
|---|---|---|
| **Stop** | point estimate **< 10%** *and* the 95% upper bound **< 20%** | The ticket stops at this report. The measured library skew is not one the head is reading, and Tasks 3–7 are not built. |
| **Proceed** | point estimate **≥ 25%** | The skew is learnable and expansion is worth building. Continue to Task 3. |
| **Judgement** | anything between | Neither answer is supported at n = 13. Resolved on the direction matrix and on the cheaper alternative below, in a written addendum to this report, not silently. |

### What a `stop` does and does not establish

Recorded now, because the `stop` row above is easy to over-read as "the
libraries are fine".

A low flip rate establishes that the head's decisions are already invariant to
the vocabulary substitutions this pass would make — **which is the whole of what
the pass does.** Tiers A and B change words and orthography and nothing else,
and the aspect and opener rewrites that would change phrasing (Tier C) are out
of scope for unrelated reasons. So a head that does not move under this probe
has nothing to gain from being trained on rephrased copies of the same lines.
The precedent is the noise 2×2 (12.6): augmentation there bought no accuracy on
the distribution the model already handled, and bought robustness to the one it
did not. That is the shape to expect here, and it is why the flip rate — not a
synthetic accuracy figure — is the outcome measure.

It does **not** establish that the libraries' *register and phrasing* are
harmless. The ticket's broader premise is that a few dozen fragments recombined
thousands of times invite the model to learn the libraries' voice rather than
their meaning, and the word-level association Task 1 measured is one narrow
instance of that. Nothing in this report measures the rest of it: sentence shape,
punctuation habits, typical length and opener are invisible to both gates, and
the one instrument that could see them — the 67 real submissions — is worth about
±12 points overall and cannot separate two arms.

If that broader concern is to be addressed, this pass is not the tool for it. It
adds no ideas and no effective sample size, and the closest evidence available
says surface multiplication over a fixed cluster set buys little: the A2 arm
generated 4.5× the recombinations of the same clusters for −0.8 to +1.3 points.
The candidate interventions are more fragments (12.1's procedural generation, or
hand-written ones), which add ideas, or Tier C rewrites under an architecture
that can scope a rule to a library. Both are separate tickets. **A `stop` here
closes this ticket, not that question**, and the write-up must say so rather than
reporting the libraries clean.

Two secondary readings, recorded now so they are not invented afterwards to fit
the result:

* **The direction matrix decides what kind of fault it is.** `true → null` and
  `false → null` flips are the 12.6 shape — the head losing a decisive call when
  the wording moves — and are the case expansion is designed for. `true → false`
  flips are a different and worse fault, and expansion is not the fix for them.
* **A high flip rate does not by itself select expansion as the remedy.**
  Rewriting `fever_null_historical` so that it does not use "fever" on 41 of its
  45 lines is a library edit costing nothing downstream: no post-processing pass,
  no parallel tree, no rule format, no split risk. If the flips concentrate in
  the `null` sub-classes, that edit is the cheaper answer and should be compared
  against Task 3 before Task 3 is built.

## Result

**Ran 2026-09-04. Flip rate 15.4%, 95% interval [2.6%, 33.3%], 6 of 39 pairs.**
The gate reads **Judgement** — neither the `Stop` row (point < 10% *and* upper
bound < 20%) nor the `Proceed` row (point >= 25%). What follows is the written
addendum the Judgement row requires, and it ends in a decision: **the ticket
proceeds to Task 3.** The reasoning is under *The decision* below; the sections
before it are the evidence that decision was made on, including the argument
against proceeding, which is kept rather than tidied away.

```
model:  models/encoder/fever_present/arm_b_finetune/weights/fold0.encoder.pt
rule:   fold0.decision.json (margin 0.55, gated class `true`, selected on val)
result: reports/encoder_training/fever_present.paraphrase_flip.json
```

### The checkpoint is not the one this document was written beside

The committed artefacts described a fold trained on **generator version 2**. The
weights were never committed, so scoring meant regenerating them, and the fold
tree regenerates at **generator version 4** — the libraries have moved since.
The head scored here is therefore a valid model trained on the *current* tree,
not a reconstruction of the old one, and its margin moved with it (0.55, where
the v2 fold 0 selected 0.0).

That is the right checkpoint for this question rather than a compromise: Task 1
measured the v4 tree, so this asks whether a head trained on the libraries whose
skew we measured reads that skew. A v2 head would have answered about libraries
we did not measure. It does mean the fold 0 numbers here are not comparable
term-by-term with the v2 figures in `fever_present.arm_b_finetune.md`. Fold 0
validation macro-F1 was 0.957 and the shuffled-label control sat at the
majority-class value, so the run is sound on its own terms.

### The direction matrix

Rows are the source's class, columns the variant's.

| source \ variant | false | true | null |
|---|---|---|---|
| **false** | 11 | 1 | 0 |
| **true** | 1 | 19 | 1 |
| **null** | 0 | 3 | 3 |

| transition | pairs | what the pre-registration says about it |
|---|---|---|
| `null -> true` | 3 | not anticipated; the direction the margin exists to police |
| `false -> true` | 1 | polarity flip — "a different and worse fault" |
| `true -> false` | 1 | polarity flip — "a different and worse fault" |
| `true -> null` | 1 | the 12.6 shape — **the fault expansion is designed for** |

**One pair of thirty-nine is the shape this ticket proposes to fix.**

### The flips concentrate in four submissions, and three of six are one sentence

Six flipped pairs, but only **4 of 13 submissions** flipped at all — and all
three `null -> true` flips are the three variants of a single submission,
`holdout-0004`. The whole of the dominant direction rests on one sentence
rewritten three ways, which is precisely why the resampling unit is the
submission and why the interval runs from 2.6% to 33.3%.

| submission | flip | 
|---|---|
| `holdout-0004` | `null -> true` on all three variants |
| `holdout-0024` | `true -> null` on v3 |
| `holdout-0031` | `true -> false` on v2 |
| `holdout-0038` | `false -> true` on v2 |

### Which side of each flip was right

`flip.py` never opens the label file, and nothing below selects anything: the
flip rate above stands as measured. But the same fold's holdout predictions
under the same margin are recorded in `arm_b_finetune/metadata.json`, and
reading them against these four submissions is free and changes the reading.

| submission | truth | source predicted | variant predicted | the rewrite |
|---|---|---|---|---|
| `holdout-0004` | `true` | `null` ✗ | `true` ✓ | **corrects** an error |
| `holdout-0024` | `null` | `true` ✗ | `null` ✓ | **corrects** an error |
| `holdout-0031` | `true` | `true` ✓ | `false` ✗ | **introduces** an error |
| `holdout-0038` | `false` | `false` ✓ | `true` ✗ | **introduces** an error |

Two of the four flips are the head getting the answer *right* only once the
vocabulary moves. That is not the story this ticket was written to expect. It
says the head is unstable near its decision boundary in both directions, rather
than that library vocabulary is dragging it consistently wrong — and a pass that
trains on rephrased copies has no particular reason to fix an instability that
is already symmetric.

### The reading

Recorded against the two secondary readings this document pre-registered:

1. **"The direction matrix decides what kind of fault it is."** It is mostly not
   the 12.6 fault. One pair drains a decisive call into `null`. Two are polarity
   flips, which the pre-registration already states expansion is not the fix
   for. Three are `null -> true` on one submission, and on that submission
   `true` is the correct answer.
2. **"A high flip rate does not by itself select expansion as the remedy."**
   Half the flipped pairs have `null` as the source class, which is the
   condition this document named for preferring the cheaper library edit —
   rewriting `fever_null_historical` so it does not lean on "fever" for 41 of
   its 45 lines — over building the pass.

### What this gate can and cannot weigh

Both readings above are about the *narrow* fault: whether swapping a content
word changes the answer. That is what this instrument measures, on thirteen
submissions of fever vocabulary, and it is not the whole of the ticket's
premise.

The premise is broader: a few hundred fragments recombined thousands of times
invite the model to fit the libraries' surface regularities rather than their
meaning. Word-label association is one instance. Repeated n-grams, a repeated
numeric value, a repeated hedge construction and a repeated sentence shape are
others, and **none of them is visible to this diagnostic.** A reading of the
15.4% that treats it as a verdict on the premise is over-reading it in the same
way the power note warns against for the rate itself.

**One correction to this document's own argument.** The `stop` section above
cites the A2 arm — 4.5x the recombinations of the same clusters for -0.8 to
+1.3 points — as evidence that surface multiplication buys little. A2 varied
*volume*: more draws from the same fragments, which adds no ideas and no
effective sample size, and its null result is sound on that question.
Expansion varies the *surface distribution* of those fragments, which is a
different intervention. The A2 evidence transfers less cleanly than the
sentence implies, and it should not be read as a measured prior against this
pass.

### The decision

**Proceed to Task 3.** Recorded 2026-09-04 by the maintainer, against the
Judgement row.

The reasoning, so a later reader does not have to reconstruct it:

* 15.4% is not a refutation, and this gate was always a cheap screen — its job
  was to avoid spending GPU time on a dead premise, not to settle the question.
  It came back "maybe", and "maybe" is what Task 6 exists to resolve.
* **Task 6's diagnostic cell is the instrument this question deserves.** A
  clean-trained model scored against the expanded test tree asks "does the
  fault exist?" across the whole synthetic tree at cluster-level resampling,
  rather than 39 pairs at effective n = 13. Deciding against building on the
  weaker instrument, while the stronger one is already designed and costs about
  forty minutes of GPU, is the wrong order to spend evidence in.
* The machinery is reusable beyond synonym swaps. A deterministic, label-blind,
  validated text-substitution pass with a rule format is infrastructure for
  every surface-diversity question this project has, not a single-use fix for
  the `fever`/`temperature` skew.
* The system is pre-live and experimental. The cost of building and measuring
  is bounded and known; the cost of a premise wrongly dismissed is not.

The library edit (reducing `fever`'s 91% occupancy of `fever_null_historical`)
and widening the paraphrase set both remain worth doing. They are no longer
alternatives to this ticket — they are cheap, independent, and they make every
future read-out sharper.

### Two authoring hazards found while deciding, recorded before Task 5

Neither blocks Task 3. Both are places where a plausible rule passes both
mechanical layers of DD6 and only the human-written invariant stands, so they
belong in the rule author's hands before the first rule is written.

**1. Numeric variation crosses a clinical threshold, and nothing mechanical
sees it.** Varying a temperature value looks like the safest possible rewrite
and is not. `FEVER_LEXICON` (`scripts/synthetic_data/lint.py`) holds no numeric
terms and `STRUCTURAL_FROZEN` (`scripts/synthetic_data/noise.py`) holds no
digits, so for a rule `38.4 -> 37.6` DD6 layer 2 and layer 3 both pass
unchanged. But the fever libraries already encode the ~38.0 threshold —

```
36.5, 36.8   in the normal-temperature lines
38.2, 39.5   in the fever lines
```

— so a sweep across 37.6-41.0 walks a `fever_true` line into saying the
patient's temperature was normal. That is §2's label-first invariant broken
silently, by the one pass that edits text after the label is fixed.

Numeric variation is therefore a **different rule kind**, not a Tier B literal
swap: it needs a per-label-class safe band (`true`: 38.0-41.0; `false`:
35.5-37.4) and a fourth validation layer asserting the band does not cross the
threshold. Note also that Task 3's rule format is literal `find`/`replace`
strings and **cannot express a numeric range at all**, so this is a deliberate
scope addition rather than a rule anyone can author on day one. Task 3 should
say so in `expand.py`'s docstring.

**2. Certainty adjectives are unfrozen.** `sure`, `certain`, `positive` and
`definitely` are in no signal lexicon and not in `STRUCTURAL_FROZEN`, whose
modality block stops at `maybe`, `might`, `may`, `could`, `think`, `thought`,
`feel`, `felt`, `seems`, `seemed`, `probably`, `possibly`. So
`"I'm pretty sure" -> "I'm pretty certain"` passes both mechanical layers while
moving the axis that *defines* `fever_null_hedged` against `fever_true`.

Two consequences: hedge and certainty rewriting belongs in Tier C (out of scope
for this pass), not Tier B; and `STRUCTURAL_FROZEN` should gain the certainty
adjectives as a small standalone change, since the gap is a mismatch between
what that list is documented to protect and what it actually holds. That fix is
worth making whatever happens to this ticket.

**Where the instinct is safe:** Tier A. Contraction and orthography pairs
cannot change which word a token is, and they attack §8's recorded register
fault — the lowercase library — which is nearer the n-gram concern than any
Tier B swap.

### How it was run

On the machine holding the GPU, with `requirements-ml.txt` installed:

```
python -m scripts.encoder_training generate-folds --signal fever_present --folds 5
python -m scripts.encoder_training finetune --signal fever_present --folds 5 \
  --revision e2da8e2f811d1448a5b465c236feacd80ffbac7b

python -m scripts.encoder_training flip-rate \
  --weights models/encoder/fever_present/arm_b_finetune/weights/fold0.encoder.pt \
  --out reports/encoder_training/fever_present.paraphrase_flip.json
```

**One fold, not five.** The question is whether flips are common or rare, and a
number bounded by 13 submissions is not improved by averaging five models over
the same 13. A second fold scored anyway would be reported as its own rate, not
pooled: the folds share no test data but they do share these submissions.

The margin is read from the fold's own `fold0.decision.json` rather than
defaulted to argmax, so the rate describes the model as it would be deployed.
The weights are git-ignored and were deleted after the run; the head, the
decision rule and `metadata.json` beside them are committed, and they are what
make this checkpoint identifiable.
