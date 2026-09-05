# Provisional plan: what to do now that augmentation has stopped paying

**Status: provisional, revision 1 (2026-09-05).** Stage 1 of the workflow: the
design decisions are argued, the task list is a shape rather than an instruction
set, and the open questions at the end are for the stage-2 review pass to close.
Nothing here is built.

**It lives in `encoder_plans/` rather than `planned_updates/` because
`arch_training.md` §12.8 names this directory as where the forward plan's plans
of record live.**

Read first: `arch_training.md` §9 (what the data is worth), §10 (the four
measured runs and the Outstanding list), §12.6 and §12.10 (the two augmentation
passes as measured), §13 (how experiments are batched);
`arch_encoder_training.md` §11 (the real-text holdout and what it can decide);
`data/realistic/README.md` (the five rules).

**What this plan is not.** It is not a fifth augmentation pass, and it does not
propose a way of writing more surface forms per idea. §1 is the argument that
that seam is worked out. It is also not a rejection of anything already built —
companions are the largest measured win in the project and stay.

---

## 1. The finding this plan starts from

Four dataset changes have now been measured against the same instrument. Set
side by side, they say something the individual write-ups do not:

| change | what kind of change | measured effect on real text |
|---|---|---|
| **companions** (§5) | **structural** — what an example is made of | **36.5% → 81.0%**, invented symptoms 191 → 35 of 268 cells |
| declarative library (12.3) | more claim density per decisive fragment | `null → true` **worse** in 6/6 signals, by up to 33.9 points |
| noise pass (12.6) | surface forms only | nil on clean text; recovers 8.5 points on damaged text |
| lexical variants (12.10) | surface forms only | −0.21 decisive points; the 1.2-point gain is inside every interval |

**One of those four moved the number that matters, and it is the only one that
changed the *shape* of a training example rather than its wording.** The other
three are the three ways of writing one idea differently, which is the family
this plan exists because you have now exhausted. `arch_training.md` says it
about each of them separately — 12.6 "adds no ideas and effective sample size is
unchanged", 12.10 "adds no ideas and no effective sample size", 12.3 "a dataset
that grows in line count has not grown in difficulty" — and the table is what
those three sentences look like together.

**So the instinct that keeps being reported back to you in every chat is
correct, and it is now measured rather than asserted.** What follows is not
"write more ideas". Writing more ideas by hand is the thing that does not scale
to 165 questions, and §2.3 does the arithmetic.

**One consequence for the run in progress.** The swap-class batch (12.10b) is
the fifth member of the surface-forms family. Finish it, because it is
pre-registered and the GPU is otherwise idle, and expect it to land inside the
intervals as v1 did. **Nothing further should be queued behind it.**

---

## 2. What the evidence says the constraint actually is

Three constraints, in the order they bind.

### 2.1 The measuring instrument, not the training data

This is the first item on §10's Outstanding list and it has grown since it was
written there. As of 2026-09-02 the margin selector varies more between folds of
one cell than the treatments vary from each other, and the document states the
consequence plainly: **no cross-arm real-text comparison in this pipeline is
trustworthy, including those already committed.**

Underneath that sits the harder version. The 67 submissions carry ±12 points
overall and ±23 to ±40 per signal on the decisive slice. 12.10 records what that
means in practice: an 11-point real-text fall in the expanded arm could not be
separated from a 12.3-point fall in an arm that 12.6 concluded was beneficial
and harmless. **Both of those readings are noise at this sample size, and no
change to the training data alters that.**

Every augmentation experiment from here is therefore being scored by an
instrument that cannot see effects of the size those experiments produce. That
is why this plan puts the instrument first, ahead of everything that would use
it.

### 2.2 The same person writes both sides

The 49 libraries are hand-written by one author. The 67-submission holdout is
hand-written by the same author. `data/realistic/README.md` records the
one-person voice as a limitation and `arch_training.md` §9 records that sixty of
the sixty-seven sit in a tidier register than the libraries aim at.

**Stated plainly: the "real text" instrument is itself synthetic, and it shares
an author with the thing it is measuring.** Every register claim in the project
is bounded by that, and no augmentation pass can reach it — a paraphrase of a
sentence one person wrote is still that person's idea of how a patient writes.

### 2.3 The arithmetic of the other 164 questions

Measured over the committed rulesets rather than estimated:

| | count |
|---|---|
| ruleset files in `data/` | 30 (plus 12 drafts in `question_drafts/`) |
| `send_to_encoder` signal occurrences | 183 |
| **distinct `encoder_prompt` wordings** | **165** |
| of those, compound questions (contain "or") | 101 |
| ways the fever question is currently worded | 7 |
| hand-written libraries for the 7 UTI signals | 49 |
| hand-written lines in them | ~2,500 |

**At the current cost model, 165 questions is roughly 1,150 libraries and 58,000
hand-written lines — about 23 times the corpus that took the project to this
point, for one condition's seven signals.** Your own estimate of 1,000+
libraries was right and slightly conservative.

Two further facts make it worse rather than better. **101 of the 165 questions
are compound** ("a fever or feeling generally unwell", "painful swallowing
together with fever or difficulty opening the mouth fully") — a per-signal
library set has to express the disjunction in its fragments, and the
`null`/`true` boundary for a compound question is a policy decision of the kind
§9 says has to be written down before the run that measures it. And **the same
clinical question is worded seven different ways across the rulesets**, so a
per-signal head is trained per *wording* unless something makes wordings share.

**The conclusion this plan draws: the per-signal, per-library cost model does
not reach 165 questions, and no improvement in how fragments are written changes
that.** What changes it is either a much cheaper authoring loop (§4, DD4–DD8) or
a model that does not need a library set per question (DD10). This plan proposes
measuring both.

---

## 3. Scope

**In scope.** Six workstreams, deliberately independent so the stage-2 pass can
drop any of them without disturbing the rest:

1. **A real-text corpus with three roles** — the instrument problem (DD1–DD3).
2. **A cheap, immediate fix to the margin selector** that needs no new data (DD3).
3. **A different authoring loop** — mining, minimal pairs, scripted drafting
   (DD4–DD8).
4. **Domain-adaptive pretraining** — the one model-side lever needing no labels
   (DD9).
5. **A question-conditioned model** and the leave-one-signal-out experiment that
   decides whether it works (DD10).
6. **An LLM ceiling baseline** on the holdout (DD11).

**Out of scope.** Any new surface-form augmentation pass. Any change to the
generator's label-first invariant (§2), the split machinery (§6), the manifest
(§4) or the merge (§7). Deployment of anything.

**Explicitly not decided here.** Whether the encoder survives DD10 and DD11.
This plan proposes the measurements; it does not pre-commit to their outcome,
and the stage-2 pass should resist writing one in.

---

## 4. Design decisions proposed

### DD1 — Real text gets three roles, and they must not be confused

Today `data/realistic/` has one role: a frozen holdout that selects nothing.
That is correct and must not change. But it means **there is no real text the
project is allowed to make decisions against**, which is why the margin selector
has no honest home (DD3) and why every arm comparison is scored on
recombinations.

Proposed: three roles, in separate files, with the distinction enforced by the
loader rather than by memory.

| role | may select? | may train? | purpose |
|---|---|---|---|
| **`holdout`** (today's 67, append-only) | **no** | **no** | validity: is a synthetic number evidence about real text at all |
| **`dev`** (new) | **yes** | no | the margin, the arm choice, which fragments to write next |
| **`train-real`** (new, later, gated) | yes | yes | only if governance and licences permit; see DD2 |

**The three must be disjoint by writer and by scenario.** A dev set written by
the same person from the same scenario list as the holdout is the holdout with
extra steps.

**Size, from the arithmetic rather than from taste.** A decisive slice of *n*
cells at ~80% accuracy carries a half-width of about `1.96·sqrt(0.8·0.2/n)`:

| decisive cells per signal | half-width | submissions needed (fever's current rate) |
|---|---|---|
| 18 (today) | ±18.5 points | 67 |
| 60 | ±10 points | ~220 |
| 250 | ±5 points | ~900 |

**So ~200–250 submissions per condition buys roughly ±10 points per signal, and
±5 points is not worth what it costs.** ±10 is enough to separate a companion-
sized effect (45 points) and not enough to separate a lexical-variant-sized one
(1.2 points) — which is the honest reading, because the second kind should not
be being chased anyway (§1).

**This is the largest single item in the plan and it is not a coding task.**

### DD2 — Multi-writer first; external corpora second, behind a licence gate

Three sources, in cost order. Only the first is unambiguously available.

**(a) Other people writing to a scenario card.** Four or five writers, twenty
messages each, from scenario cards that fix the clinical facts (and therefore
the label vector) while leaving the writing free. This is the only source that
directly attacks §2.2, it needs no governance work, and 100 submissions from
five writers is worth more than 300 more from one.

**Labelling stays label-first**: the card fixes the facts before the text
exists, exactly as the generator fixes the label before drawing fragments. Where
a writer's text does not match its card, the *card* is corrected or the text is
discarded — the label is never re-derived from the text.

**(b) Public patient-written corpora**, as a source of *ideas and register*
rather than of training text. Candidates worth checking: the HealthCareMagic and
iCliniq question sets distributed with ChatDoctor, MedDialog, and the r/AskDocs
academic releases. Condition-specific forums (Patient.info, HealthUnlocked) are
readable without any dataset at all.

**Three honest caveats, and the review pass should treat all three as blocking
until checked.** I cannot verify current licence terms from here, and several of
these releases are research-only, which is a different posture from a commercial
product — **licence review comes before any of this text is read into a build
step.** Forum writers are also not e-consult writers: self-selected, longer,
often chronic, and writing to strangers rather than to their own GP, so the
register transfers imperfectly. And the safest use is the weakest: reading a
corpus to derive an idea inventory (DD4) is a different act from training on it,
and this plan proposes only the former until a licence check says otherwise.

**(c) Real submissions from the live system.** The correct long-term source, and
`arch_training.md` §1 already records that it needs governance work first. Not
in scope; named so the plan does not read as though it were unaware of it.

### DD3 — Fix the margin selector by freezing it, now, and by a dev set later

The §10 Outstanding item #1 blocks reading everything below it. It has a cheap
fix that is available immediately and a proper fix that waits on DD1.

**Now, free: freeze the margin.** Select no margin per fold; fix it at one
pre-registered value for every cell of a comparison and report the arm
difference at that value. The absolute accuracy will be worse than the tuned
version. **That is the correct trade**: the tuned version's variation between
folds of one cell is currently larger than the treatment effects being measured,
so a fixed margin buys a readable comparison at the cost of a flattering
headline. Reporting the whole margin curve per arm is strictly better still and
costs nothing but a loop over thresholds on saved predictions.

**Later, properly: select the margin on the real-text dev set.** 2026-08-19's
closing note — that no future margin should be selected on a validation split in
which the failure cannot occur — is unactionable today because no such split
exists that the rules permit selecting on. DD1's `dev` role is what makes it
actionable, and it is the main reason the dev set is worth building separately
from the holdout.

### DD4 — Mine ideas from real text instead of asking a model to invent them

**This is the direct answer to "the LLM goes weird after 30 ideas".** The model
is being asked to enumerate a space from nothing, which is the task it is worst
at; §1 of `fragment_authoring_prompts.md` already records that an LLM asked for
forty fragments returns forty rewordings of six ideas.

Proposed loop, per library:

1. Gather real texts about the symptom (DD2a's scenario messages, DD2b's forum
   reading).
2. Cluster them, or read them, into an **idea inventory** — one line per
   distinct situation, not per sentence.
3. The LLM's job becomes *one label-clean fragment per idea from a supplied
   list*, which is a constrained rewriting task rather than an invention task.
4. What is left over is the coverage gap, and it is a measurement rather than a
   feeling.

**A coverage metric falls out of this and is worth building on its own.** For
each real text, the similarity to its nearest synthetic fragment. The
distribution says which parts of the real space the libraries do not reach, and
therefore what to author next — replacing "author uniformly until it feels
done". It also gives an honest stopping rule, which the project currently lacks.

### DD5 — Author minimal pairs across the label boundary

The 2026-08-16 sweep found errors landing on the clear `_true`/`_false`
libraries rather than on the hard `null` confounders, and named
`urinary_frequency_true` (65.8%) and `nocturia_true` (71.1%) as the worst two.
**The weak spot is the decisive libraries, which is also where the idea space is
genuinely small** — there really are only so many ways to say it burns when you
pee.

That bind resolves if the unit of authoring stops being "another idea" and
becomes **the smallest edit that moves an existing fragment to a different
label**. LLMs are markedly better at constrained edits than at open generation,
and the edit targets exactly the boundary the errors sit on.

**Both members of a pair share a cluster marker**, so they never land on
opposite sides of a split. The mechanism exists (§3, §6) and needs no change.

**The risk, recorded before the work.** A library of minimal pairs can teach the
single edited token rather than the distinction — "the word *might* means
`null`". That is the §8 exclusive-token fault arriving by a new route, it is
visible to the token / label-class association report, and **the report must be
run over any minimal-pair library before it is committed.**

### DD6 — Scenario-first whole messages, with rejection that never relabels

Real submissions are narratives: onset, progression, what was tried, what is
wanted, two or three claims interleaved. Every generated example is fragments
joined with a space. §9 already records what the libraries never produce — a
past fever and a present one in one sentence — and §12.8 records that structural
nulls are the least realistic example type in the dataset.

12.3 attacked this with fixed frames and it failed, measurably: everything
`declarative_v1` emits is an easy case, 100.0% with a diagonal confusion matrix.
**The failure was the rigidity of the frames, not the multi-claim idea**, and the
distinction matters because companions — the same idea done structurally — is
the biggest win on file.

Proposed: sample a structured scenario **including its label vector**, have an
LLM render it as one message, and have a second, blind LLM label the rendered
text. **Agreement keeps the example; disagreement never relabels it.** The label
was fixed before the text existed, so §2's invariant survives: the second
labeller is a rejection filter, not a labelling step.

**The failure mode of that filter is the same one that sank `declarative_v1`,
and it must be measured rather than argued.** Discarding on disagreement
systematically removes the examples that are hard to read — which is precisely
how a library comes to score 100%. Mitigations: route disagreements to human
review rather than auto-discard, cap the share of any one library's draw, and
**score the resulting slice's difficulty the way 2026-09-02 scored
`declarative_v1`.** A generated library that scores 100% is a library that has
added volume and no difficulty, and the project now has a number for that.

### DD7 — Authoring becomes a script against an API; review stays human

The copy-paste loop is the thing that does not reach 1,150 libraries, and it is
the part of the current process with no engineering behind it at all.

Proposed shape: a library spec (signal, polarity, sub-class, boundary rules,
existing lines) in, many small sampled calls out (persona, context, length,
register varied per call rather than per prompt), deduplicated against existing
lines by the same similarity the near-duplicate report already uses, run through
`--lint`, emitted as a **draft file for human review**.

**Nothing about the review obligation changes.** `fragment_authoring_prompts.md`
§3 stays exactly as written: read every line, check the idea list rather than
the line count, delete anything you would hesitate over. What is automated is
the typing and the bookkeeping, not the judgement.

**Two properties the review pass should hold it to.** The script must be
reproducible enough to be re-run (model, prompt and seed recorded per draft),
and a drafted library must be distinguishable from a hand-written one in the
manifest — `fragment_authoring_prompts.md` §1 already proposes comparing
LLM-drafted clusters against hand-written ones for how well they are learned,
and that comparison is only possible if the provenance is recorded.

### DD8 — Where the idea budget goes, corrected against the measurements

The intuitive allocation — spend it on the null and false axes, since the
decisive space is small — **is contradicted by 2026-08-16**, which found the
null confounders sitting at 0.90–1.00 recall and the errors on the decisive
libraries. The budget goes where the errors are:

1. **Non-vocabulary decisive phrasings** — the claim carried by idiom,
   measurement or physical description rather than by the symptom's noun. This
   is exactly what Prompt B in `fragment_authoring_prompts.md` was written for,
   and DD4's mining is a better source of it than a model's imagination.
2. **The contrastive negative** — a fever that belongs to someone else or to
   another time, followed by a denial. The largest single error family on file.
3. **The nocturia / urinary-frequency pair**, which is a *labelling policy*
   problem rather than an idea-count one and is already specified in 12.9 and
   `planned_updates/urinary_frequency_nocturia_labelling.md`. No number of new
   fragments fixes an undeclared pair.
4. **The two filler families §9 identified and nobody built** — what the patient
   has already tried, and relevant history and risk factors — which appear in
   about half and about a quarter of the real submissions respectively.

### DD9 — Domain-adaptive pretraining: the one model lever needing no labels

`roberta-base` is fine-tuned straight from the public checkpoint. Continuing
masked-language-model pretraining on unlabelled in-register text before
fine-tuning is the standard treatment for a register gap, and it is the only
model-side change in this plan that consumes **no labels at all** — which
matters, because unlabelled patient-register text is the one input that is cheap
at scale.

**Realistic expectation: small.** RoBERTa's pretraining already includes a great
deal of informal web writing, so the gap is narrower than it feels; and the
gains reported for domain-adaptive pretraining generally assume a corpus far
larger than a few thousand forum posts. **The reason to run it anyway is that it
costs one slot in a night** (§13: a night is ~240 fold-trainings and MLM on a
few megabytes is a fraction of that), and it is a clean A/B against an identical
fine-tune.

Subject to DD2's licence gate for anything not written by the project.

### DD10 — A question-conditioned model, and the experiment that decides it

**This is the only proposal in the plan that changes the 165-question
arithmetic**, so it is the one worth the most care.

Today: one head per signal, one library set per signal, `finetune --signal X`.
`arch_encoder_training.md` §1 frames the whole package as six independent
three-way classifications.

Proposed alternative: **one model that reads the question and the text
together** — the `encoder_prompt` concatenated with the submission — and answers
`true`/`false`/`null`. The null axes are textbook entailment phenomena: "my mum
has a fever" not entailing "I have a fever" is third-party displacement, and an
NLI-pretrained cross-encoder starts from a representation built for exactly that.

**Three things make this cheap to test rather than a rewrite.**

* **The data already exists.** The merged `joint6` tree carries one labelled key
  per example, which is one `(question, text, label)` triple. `--emit-signals
  all` (12.2, built and never used) would yield several per example, and this is
  the first thing that has wanted it.
* **Evaluation does not change.** Predictions are still per signal, so every
  existing per-library table, McNemar comparison and holdout scoring applies
  unchanged.
* **The runtime contract gets easier, not harder.** §9 of
  `arch_encoder_training.md` records that a single fever head cannot satisfy
  `EncoderOutput.validate_against`, which requires a key per `send_to_encoder`
  signal. A question-conditioned model emits a key per question by construction.

**The decisive experiment is leave-one-signal-out, and it fits in one night.**
Train on five signals' triples, evaluate on the sixth's held-out tree with that
signal's question supplied and no supervised example of it ever seen. If the
result is usable, **the marginal cost of question 166 stops being a library set
and becomes a question string plus a policy decision**, and the whole scaling
problem changes shape. If it is not, that is worth knowing before authoring
1,150 libraries.

**Stated honestly: there is no in-repo evidence for this yet.** It is the
standard result for question-conditioned and NLI-style classification generally,
and the leave-one-signal-out cell is what turns it into evidence here. Two known
risks: the model may key on question *wording* rather than meaning (testable —
paraphrase the question and re-score, which is the flip diagnostic pointed at
the question instead of the text), and the 101 compound questions are harder for
this shape than for a per-signal head, not easier.

### DD11 — Measure an LLM ceiling on the holdout, and record it

**Score the 67 submissions with a general-purpose LLM given the same
`encoder_prompt` the encoder gets.** No GPU, no training, costs pennies, and
**no real patient data is involved** — the set is hand-written, which is the one
circumstance in which this measurement is free of governance questions.

The reason it belongs in this plan: it bounds everything else in it. If a
zero-shot LLM sits in the nineties where Arm P sits at 81.0%, then the encoder's
remaining gap is not a data problem and several workstreams above are being
spent in the wrong place. If it does not, that is the strongest evidence the
project has ever had that the encoder approach is the right shape.

**It is a candidate model under README rule 3, so the number is recorded
whichever way it comes out**, including if it is uncomfortable.

**The honest counter-arguments to acting on a good result**, which the review
pass should weigh rather than skip: per-submission cost and latency, the
governance of sending real patient free text to a third party at runtime (which
this *measurement* avoids and a *deployment* would not), and reproducibility of a
hosted model against `arch_encoder_training.md`'s determinism posture. None of
them is a reason not to take the measurement.

**One rule question this raises, flagged rather than resolved.** README rule 2
says the holdout selects nothing, and a ceiling reading that changed the
project's architecture would be selection of a kind. The defence is that rule 2
exists to stop per-model tuning against 67 texts, and a single recorded reading
used once for a strategic decision is a different act. **It is arguable, and
DD1's dev set removes the argument entirely** — which is another reason to build
it first. Open question OQ3.

### DD12 — What would make this plan wrong

Recorded now so it can be scored later, in the spirit of §9:

* If the swap-class batch (12.10b) produces a real-text effect outside the
  intervals, §1's table has a fifth row that disagrees with it and the
  surface-forms family is not exhausted after all.
* If DD10's leave-one-signal-out cell fails badly, the per-signal cost model is
  the only one available and DD4–DD8 become the whole plan rather than half of
  it.
* If DD11 shows a zero-shot LLM at or below Arm P, DD9 and DD10 are the right
  places to spend and the authoring workstreams are the constraint.

---

## 5. Predictions, recorded before the work

Following `arch_encoder_training.md`'s convention that a prediction written
afterwards is a rationalisation.

1. **The swap-class batch lands inside the intervals**, as v1 did.
2. **Freezing the margin (DD3) lowers absolute accuracy by a few points and
   changes at least one committed arm comparison's direction.** If no comparison
   moves, the margin was not the confound 2026-09-02 says it was.
3. **DD9 (domain-adaptive pretraining) moves decisive accuracy by less than 2
   points** and is inside the intervals. Run it because it is nearly free, not
   because it is expected to work.
4. **DD10's leave-one-signal-out cell scores well above chance and clearly below
   a signal trained with its own supervision.** The interesting question is the
   size of the gap, not its direction — a gap small enough to close with a
   handful of per-question examples is what would change the project.
5. **DD11's zero-shot LLM beats Arm P's 81.0% on the holdout.** Recorded because
   it is the prediction that would be most inconvenient if true, and writing it
   down is what stops it being explained away afterwards.
6. **The multi-writer dev set (DD2a) is the item that produces the largest
   surprise**, because §2.2 is the limitation that has never once been tested.

---

## 6. Tasks (provisional shape, for the stage-2 pass to expand)

Ordered by what unblocks what, not by size. §13's rule applies throughout: CPU
gates run first and alone, GPU work batches into a night.

* **T1 — Freeze the margin (DD3).** No new data. A pre-registered constant, plus
  a margin curve per arm computed from saved predictions. Unblocks every
  comparison below.
* **T2 — Scenario cards and a multi-writer dev set (DD1, DD2a).** ~200
  submissions, ≥4 writers, disjoint from the holdout by writer and scenario.
  The largest and least technical item.
* **T3 — The LLM ceiling reading (DD11).** Independent of everything; do it
  early because it is cheap and it may reorder the rest.
* **T4 — Coverage metric and idea inventory (DD4).** Nearest-synthetic-neighbour
  distance per real text; the gap list is the authoring queue.
* **T5 — The drafting script (DD7)**, then minimal pairs (DD5) for
  `urinary_frequency_true` and `nocturia_true` first, since they are the two
  worst libraries on file.
* **T6 — Leave-one-signal-out, question-conditioned (DD10).** One night. Needs
  T1 to be readable.
* **T7 — Domain-adaptive pretraining (DD9).** Same night as T6 if the corpus
  passes DD2's licence gate.
* **T8 — Scenario-first message generation (DD6)**, with the difficulty check
  that `declarative_v1` failed, and the token/label-class report over anything
  T5 or T6 produced.

**T1, T3 and T4 need no GPU and no new data, and none of them depends on the
others.**

---

## 7. Open questions for the review pass

1. **Does the dev set (DD1) live in `data/realistic/` beside the holdout, or in
   a directory of its own?** Beside it is convenient and is exactly how a file
   gets scored by the wrong loader. A separate directory with its own loader
   that *cannot* be pointed at the holdout is the safer shape and costs more.
2. **Who writes the dev set, and how are the scenario cards sourced?** The whole
   value of DD2a is that the writers are not the library author, so this is a
   real-world constraint rather than a design choice.
3. **Is DD11's ceiling reading compatible with README rule 2**, or must it wait
   for the dev set? §DD11 argues it is; the argument is not airtight, and the
   conservative answer costs one workstream's ordering.
4. **Does DD10 replace the per-signal heads or sit beside them?** Beside them is
   answerable in one night; replacing them is a rewrite of `train.py`,
   `dataset.py` and the report layer, and should not be started before the
   leave-one-signal-out number exists.
5. **What licence review is needed before any external corpus is read into a
   build step (DD2b)**, and who does it? Blocking for T7 and for any use of
   external text beyond human reading.
6. **Should the compound questions (101 of 165) get a policy treatment of their
   own?** §9's rule — a labelling policy written down before the run that
   measures it — has never been applied to a disjunctive question, and 61% of
   the project's questions are disjunctive.
7. **What is the actual authoring cost of one library, in hours?** §2.3's
   arithmetic is in lines because the git history here starts on 2026-08-31 and
   does not carry the authoring period. **It is the single most important number
   for deciding between DD4–DD8 and DD10, and only you have it.**
