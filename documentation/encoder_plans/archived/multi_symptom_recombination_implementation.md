# Implementation Plan: Multi-symptom recombinations (ticket 6)

**Status: complete. Tasks 1-7 landed; the run trained on 2026-08-19.** The
write-ups are `reports/encoder_training/2026-08-19.md` and
`2026-08-19-plain-english.md`, and the current state is `arch_training.md`
section 10. Three of three scored criteria held and the fifth prediction held for
one of its two signals; `urinary_frequency` is the open item and is now an
argument for 12.3's per-line label vectors. This document stays on disk as the
record of what was built and why.

Step-2 output. This is the review-and-correction pass over the provisional plan,
expanded into tasks that can each be handed to a fresh chat. (The provisional
plan lived at `planned_updates/multi_symptom_recombination.md`, a path that does
not exist in this repository; there is nothing on disk to mark superseded.)

Read first: `arch_training.md` sections 2, 3, 5, 7, 8, 9, 12.2–12.5, 12.7, 12.8;
`arch_encoder_training.md` section 8; `reports/encoder_training/2026-08-17-plain-english.md`
sections 3, 4, 8 and 9; `planned_updates/encoder_next_steps.md` section 3.

**The provisional plan stays on disk unchanged.** Where this document disagrees
with it, this document is the one to build from. The disagreements are listed in
"What changed from the provisional plan" below, because several of them change
what a task costs.

---

# Orientation for someone new to this

The encoder reads a patient's free text and answers seven yes/no/not-mentioned
questions about it. It is trained on synthetic data: a few hundred hand-written
sentence fragments, recombined into thousands of examples. The label is always
decided *before* the text is drawn, so a label can never be wrong about its own
text (`arch_training.md` section 2).

On 2026-08-17 we trained one model on all six signals at once and scored it on
67 hand-written realistic submissions. It reads what patients *do* say very
well, and it invents symptoms patients never mentioned 47%–89% of the time. It
scores 39.1% on real text where answering "not mentioned" to everything scores
66.7%.

The cause is a property of the data. Every `null` example for a signal pairs the
absence of that signal's language with **bland, non-clinical filler**. No head
has ever seen a message dense with clinical language about another symptom whose
correct answer is still `null`. So "clinical-sounding text ⇒ not `null`" is a
perfect rule on our data and a catastrophic one on real text, where the median
submission asserts something about two of the six signals.

**This ticket's deliverable is examples where the text is full of other symptoms'
clinical language and the label for this signal is still `null`.** Everything
else here is machinery in service of that sentence.

---

# Plan

Build the mechanism that lets a fragment from one signal's library appear
in another signal's example, safely, and prove it fixed the measured failure.

Three things have to be true before a dysuria fragment may sit in a
`fever_present: null` example:

1. Somebody has decided, in writing, that every line of that dysuria library is
   `null` on fever — and the manifest records it, per library and per signal.
2. The generator draws that companion fragment in a way that cannot correlate
   with the label, because if it did we would have replaced "clinical language ⇒
   not null" with "clinical language ⇒ true", which is the same failure wearing
   a different hat.
3. The comparison against today's data is readable: same seed, same libraries,
   one flag, and at zero the generator behaves exactly as it does now.

Then train two arms, score them on the 67 submissions once, and record the
number whatever it says.

---

# Scope

**In scope**

* A per-library, per-signal declaration in the manifest of which signals a
  library's lines are `null` on, with the basis for each claim.
* A generalised lint that checks the machine-checkable half of that declaration
  in CI, and lists the other half as a standing review item.
* `--companion-share P`: non-decisive slots drawn from other signals' eligible
  libraries instead of filler. Default 0.0, and at 0.0 the path is inert.
* `--emit-signals primary|all`: multi-key label vectors. **Built, tested, and
  not measured in this ticket** (DD13).
* Six new `recent_uti_present` libraries and the labelling policy they are
  written against, in `arch_training.md` section 9.
* `GENERATOR_VERSION` 3, the deferred `expectations.txt` split, the `merge-folds`
  relaxation, and a regenerated baseline.
* Two trained arms plus one free third arm, scored on the synthetic test set and
  on the 67 submissions, with a written-up report.

**Out of scope**

* **Per-line label vectors** (12.3's JSONL library format). This is what the
  nocturia/urinary-frequency pair eventually wants and it is not this ticket.
  The consequence is that cross-signal *assertion* is not expressible here at
  all — see DD1.
* **Replacing `merge-folds` with direct multi-signal generation** (12.2's
  end state). Follow-up; see DD11.
* **A sweep over P.** One non-zero value plus the control (DD15).
* **Templating (12.1) and character noise (12.6).** Independent; neither blocks
  this and this blocks neither.
* **Making the encoder deployable.** `EncoderOutput.validate_against` still
  requires all seven keys and seven heads do not exist.
* **The register gap.** The 67 submissions sit in a tidier register than the
  libraries aim at, and companions do not change register.

---

# What changed from the provisional plan

Seven corrections, listed here because each one changes a cost or a claim.

1. **DD1's `asserts` state is deleted.** It cannot be implemented: `fragment_type`
   is the polarity of the library's *own* signal, so there is no field a foreign
   signal's value could come from, and the flagged pairs are per-line facts over
   libraries whose lines disagree. Cross-signal `true`/`false` needs 12.3.
2. **The declaration is about the *value*, not about topical silence** — and it
   gains a `basis`, because only one of the two bases is machine-checkable. The
   provisional DD2's claim that the generalised lint "falls out as a special case
   with no behaviour change" is not true once the second basis exists.
3. **`uti_speculation` probably stays usable.** Under the provisional plan's own
   §5.1 and §5.3 policy, none of its 40 lines asserts a UTI inside 30 days. This
   removes most of DD8's consequences and roughly halves task 3's cost (DD18).
4. **DD4's blindness has a hole.** Per-slot blindness is not per-example
   blindness: structural nulls have N companion-eligible slots where every other
   mode has N−1, so at the same share they get twice the companions at N=2. Fixed
   by drawing over N−1 slots in every mode (DD5).
5. **The success criterion conflicted with Ticket A's standing rule.** Choosing P
   by sweeping against the 67 submissions is selection. P is now chosen on stated
   grounds before any real-text scoring (DD14, DD15).
6. **DD3's byte-identity claim and DD11's `expectations.txt` split contradict
   each other.** Both are kept; the byte-identity test is a fixture test, and the
   shipped Arm 0 tree is explicitly not byte-identical to the 2026-08-17 data (DD4, DD16).
7. **6b is built and not measured.** The decision rule's constraint is relative
   to argmax, so a 92% `null` prior changes the constraint as well as the head,
   and the two arms are not comparable on the deciding metric (DD12, DD13).

---

# Design Decisions

### DD1 — The declaration is a value, not a topic, and `undeclared` is the default

For every (library, signal) pair where the signal is **not** the library's own:

| state | meaning | eligible as a companion in a run claiming this signal's key? | contributes |
|---|---|---|---|
| **`null_on`** | the correct label for this signal is `null` on **every** line, whether or not the line mentions it | yes | `null` |
| **undeclared** | nobody has decided | **no** | — |

For the library's own signal the value comes from `fragment_type`, exactly as
today. That is the only place a `true` or `false` can come from.

**There is no cross-signal `asserts` state, and there cannot be one in this
ticket.** The provisional plan proposed one whose value "comes from
`fragment_type`". Two reasons that fails:

* `fragment_type` is the polarity of the library's own signal. `flank_pain_false`
  is `negative`, but the three lines in it that mention urination assert
  `dysuria_present: **true**`. There is no field the foreign value could be read
  from without inventing one.
* It is a per-library claim over lines that disagree — 3 of 55 `flank_pain_false`
  lines. A cross-signal assertion is a per-line fact, and per-line facts need
  12.3's JSONL format, which is out of scope.

So the entangled pairs stay **undeclared**, which is not a workaround: it is the
honest state for a pair nobody can decide at library granularity.

**Undeclared is the default and it is not silence.** `arch_training.md` section 3
records that `uti_speculation` was full of lines nothing caught, because a
lexicon is only written for a signal we decided to train. A closed-world default
("silent about everything I do not name") would mean adding an eighth signal
silently asserts that all 42 existing libraries are silent about it. Rejected.

**No wildcards and no manifest-level default block.** The declaration is the
guarantee; a shorthand for asserting it in bulk is a shorthand for asserting it
without reading it. Task 1 makes the typing tractable a different way — it prints
a paste-ready block — but every entry still lands in the manifest explicitly.

### DD2 — Two bases, and only one of them is machine-checkable

This is the correction that matters most, because the provisional plan claimed a
guarantee it cannot deliver uniformly.

A `null_on` entry carries a `basis`:

* **`absent`** — the library never mentions the signal at all. The lint checks
  this: a lexicon hit against an `absent` pair is a **failure**. The existing
  `filler_lexicon_hits` becomes exactly this check applied to filler libraries,
  and passes unchanged.
* **`policy`** — the library *does* talk about the signal, and the correct label
  is `null` anyway. `uti_speculation` on `recent_uti_present` under DD18 is the
  worked case; so is every `*_null_*` library on its own signal. The lint
  **cannot** check this. A lexicon hit here is expected.

A `policy` entry therefore requires a `note` giving the rule that makes it
`null`, and the lint prints every `policy` pair with its matched-line count
beside it, so "23 of `uti_speculation`'s 40 lines read as `recent_uti_present`
language and we decided all 40 are `null`" is a visible standing claim rather
than an invisible one.

**Say the limit plainly in `arch_training.md`:** the ticket's central safety
guarantee is machine-checked for `absent` pairs and hand-judged for `policy`
pairs, and the lexicons that do the checking catch 59%–91% of their own positive
libraries and 25–45 points less of the negative ones (section 8). Even the
checked half is a lower bound. Under-claiming this now is what stops it being
discovered as a surprise later.

### DD3 — 6a can produce wrong labels too

The provisional plan framed the split as "6a changes what the text contains, 6b
changes what the labels contain", and concluded 6a is the low-risk half. The
first clause is right and the conclusion is half wrong.

Under 6a, a companion drawn from a library **wrongly** declared `null_on` for the
primary signal makes that example's single emitted label a lie. 6a and 6b carry
the same *kind* of label-corruption risk; what differs is how many keys are at
risk per example, and what happens to the class prior.

The consequence for sequencing: **the declaration pass (task 3) is load-bearing
for 6a, not only for 6b.** It cannot be deferred behind the companion flag.

### DD4 — Companion drawing is a flag, and at zero the whole path is inert

`--companion-share P`, default `0.0`.

At `P = 0.0` **both** the companion draw and the eligibility filtering are
skipped. Both, not just the draw — `_draw_filler` picks with
`rng.choice(candidates)`, so changing the candidate list changes the outcome of
*the same* draw. Skipping only the companion branch would still move every
generated example. Fold mode set the precedent for a flag that is inert at its
default and there is a test shape to copy.

Two things to state rather than discover:

* **Why byte-identity holds for the six existing signals anyway.** The lint
  already establishes filler is silent on all six, so every filler library is
  `null_on` all six and the eligible set is unchanged. It stops holding the
  moment any filler library goes undeclared on one of the six — which is a
  reason to keep that from happening quietly, not a reason to relax the test.
* **The byte-identity test is a fixture test.** On the shipped tree DD16's
  `expectations.txt` split takes filler from five libraries to six and changes
  every `_draw_filler` outcome. So `--companion-share 0` reproduces the A1
  datasets *given the pre-split manifest*, and the shipped Arm 0 tree is a
  regeneration, not a reproduction. Both are true; write both down.

### DD5 — The companion **count** is drawn per example, blind to the label mode

This closes a hole in the provisional DD4 and it is the easiest thing in the
ticket to get wrong.

Per-slot blindness is not per-example blindness. A `null_structural` example at
count N has **N** non-decisive slots; `true`, `false` and `null_ambiguous` have
**N−1**. An independent per-slot draw at share P therefore gives structural nulls
twice the expected companions at the default N=2. Companion count becomes a proxy
for the label mode — section 5's shortcut in a new place — and it points the
wrong way: *more clinical companion text ⇒ more likely `null`*. A model can learn
that without reading anything, and it would **flatter this ticket's headline for
exactly the wrong reason**.

**The rule: the companion draw runs over N−1 slots in every mode.** For
`null_structural` the remaining slot is always filler. Every mode then has the
same number of companion-eligible slots at the same fragment count, the
distribution is exactly equalised by construction rather than by check, and a
structural null keeps at least one filler fragment.

The sidecar reports realised companion count **by label and by label mode**, in
the same shape as the existing `fragment_counts.by_label` guard, and a test
asserts the rows agree. This is the leak detector; nothing downstream would
surface a violation on its own. It would present as a validation score that looks
fine and a model that does not transfer, which is precisely the shape of the
thing this ticket exists to fix.

### DD6 — Which companion is drawn is blind to the label mode too

The signal is drawn uniformly over signals with at least one eligible library,
then the library uniformly within it, then the fragment — none of it seeing the
label mode. Otherwise companions would be disproportionately `true` in `true`
examples and we would have taught "clinical language ⇒ true".

**The primary signal's own libraries are never eligible as companions.** The
primary signal enters an example only through the decisive slot. Without this
rule a `fever_null_hedged` fragment could land in a `fever_present`
`null_structural` example, `null_structural` and `null_ambiguous` collapse into
each other, and `--null-ambiguous-ratio` — which `arch_training.md` section 5
calls the single most consequential setting in the generator — stops meaning
anything.

The sidecar reports the companion signal mix, and the companion label mix per
primary label class.

### DD7 — Combination is validated on the vector, not on the primary signal

For each signal S over the fragments of one example:

| fragments' states on S | result |
|---|---|
| any fragment **undeclared** on S | **no key for S** (masked; section 7's missing-key semantics) |
| exactly one fragment asserts S (it is that fragment's own signal) | key = that value |
| all fragments `null_on` S | key = `null` |
| two fragments would assert S | unreachable by DD8 |

**Label-first survives intact, and this is the point (12.5).** The target vector
is chosen first, each pool is filtered down to the fragments compatible with it,
and then the draw happens. We never generate text and inspect it. Filtering
before drawing rather than drawing and rejecting also keeps generation
deterministic and stops the accept/reject rate quietly skewing the mix.

### DD8 — At most one fragment per signal per example

Today's Rule 2 ("one signal, one decisive fragment") generalises rather than
disappears. Two dysuria fragments in one example either agree — doubling the
evidence for one claim and teaching nothing — or disagree, which DD7's last row
forbids. One per signal makes the disagreement case unreachable by construction
instead of by check.

### DD9 — Companions come from the same split as the example

`build_pools` already restricts to one split and `fold_bucket` is a pure hash of
the cluster key and salt with no knowledge of signals, so a fragment sits in the
same split whichever signal's run is generating. This is therefore free — but it
has to be stated, because the failure is subtle. If a fever *test* example could
contain a dysuria *train* fragment, and that dysuria fragment also appeared in
fever's training examples, the model would have seen part of the test text during
training. Section 6's argument that a fragment lives on exactly one side of the
split now has to hold across signals too, and it does.

### DD10 — What `null_structural` means at P > 0, and what it costs

At `P > 0` a structural null is no longer filler-only. It keeps its name because
it keeps its defining property — **no fragment decisive for the primary signal** —
and it stops being trivially easy, which is exactly what `arch_training.md` 12.8
asks for ("a dysuria sentence labelled `fever_present: null` is a better
structural null than any filler-only recombination").

Two consequences:

* **The sidecar gains `filler_only` as a fact separate from `label_mode`**, so
  the merge and the report can each see which examples are still deduplicable
  without re-deriving it from `fragment_ids`.
* **The merge's structural-null dedup stops firing.** It applies only to
  filler-only examples, and at P > 0 there are almost none. Today's saving is 25%
  of forward passes; losing it grows the merged tree by roughly 1.5× against
  today, i.e. about a third more compute per epoch on the joint arm. That is the
  ticket's compute bill. It is accepted, not worked around, and it belongs in the
  cost section rather than being discovered during the run.

### DD11 — `merge-folds` is kept and relaxed, not replaced

Two options and it is a real fork:

* **(a) Keep per-signal runs and the merge.** Each run's nulls are kept
  separately where they diverge, the tree grows, and each head is masked on the
  others as today.
* **(b) Generate the multi-signal dataset directly** and let it replace the merge.
  This is where 12.2 says the architecture is going.

**(a) for this ticket, (b) as a follow-up.** The merge tool is built, tested and
understood; replacing it in the same ticket that changes what every example
contains would move two things at once and leave no clean control to compare
against.

The relaxation is precise: `check_structural_nulls` asserts byte-identity over
the **filler-only** examples only, and records each source's `companion_share` in
`merged_from`. **A merge whose sources disagree on `companion_share` is refused** —
a merged tree mixing arms would be uninterpretable and nothing downstream would
notice, which is the same reasoning behind the existing `generator_version` and
`(folds, fold_index, split_salt)` refusals.

### DD12 — The class prior is decided and reported, and it moves the decision rule

**Do not reweight the loss.** `arch_encoder_training.md` section 8 rejected that
deliberately and the reasoning holds: the training mix is a generator flag rather
than a measured prior over real submissions, so reweighting corrects towards a
second arbitrary target, whereas the decision margin is tunable, versioned,
documented and already selected per head on validation data.

What this ticket owes instead: the sidecar states each signal's realised label
mix, and the mix is reachable by flag rather than being whatever falls out.

**And one thing the provisional plan missed.** The decision rule's objective is
*maximise macro-F1 **subject to** a `null → true` rate no worse than argmax's*.
The constraint is relative to argmax, so moving the prior moves the constraint,
not just the head. Under 6b at roughly 92% `null`, argmax already almost never
answers `true`, the constraint tightens sharply, and the selector picks a margin
that suppresses `true` for reasons that have nothing to do with reading the text.
A success criterion phrased as "lower `null → true` at comparable accuracy" would
score that as a win. This is why 6b is built and not measured (DD13) and why the
criterion carries a declared floor (DD14).

**The buried win, promoted.** 6a makes the dangerous cell occur **in synthetic
validation** for the first time. Margin selection has always been done on
validation data where that failure barely happens — the standing worry in the
2026-08-17 report §9.3 — and this is the first time it will be given a fair
question to answer. It costs no retraining at all, and it is arm C.

### DD13 — Three arms, and the third is free

| arm | what it is | cost |
|---|---|---|
| **Arm 0** | `--companion-share 0`, five folds, joint six-head. The control, and the regenerated baseline at `GENERATOR_VERSION` 3. | 5 fold-trainings |
| **Arm P** | `--companion-share P`, five folds, otherwise identical. | 5 fold-trainings |
| **Arm C** | Arm 0's trained heads, **margin re-selected on Arm P's validation split**. No retraining. | free |

Arm C is what separates "the training data change helped" from "the *margin
selection* data change helped". If Arm C captures most of Arm P's gain, the
cheap fix was available without regenerating anything and that is the headline.

**6b (`--emit-signals all`) is built behind the flag and not measured here.**
Three reasons: DD12's argmax interaction makes it non-comparable on the deciding
metric; a third trained arm is five more fold-trainings against a GPU budget that
has not yet paid for the previous ticket's outstanding sweep; and the predictions
below already say it will be neutral-to-worse on the headline. It gets correctness
tests on the emitted vectors and nothing more. Measuring it is a follow-up with a
question of its own ("does more label per example buy training efficiency?"),
which is not this ticket's question.

### DD14 — What the 67 submissions may and may not decide

`encoder_next_steps.md` section 3, in writing since before the set existed:
*"Never used to select anything. Not a margin, not a pooling mode, not an epoch
count, not which fragments to write next."* The 2026-08-17 report §9.1 repeats
it. The provisional plan's §6 made the real-text cell the number that decides
whether the ticket worked and its §8.5 proposed a four-point sweep over P, which
is selection and would burn the only instrument in the project that can see this
failure.

So:

* **P is chosen before any real-text scoring**, on the grounds in DD15.
* **The real set scores Arm 0, Arm P and Arm C once each**, and the numbers are
  recorded whatever they say.
* **The comparison is paired** — same 67 submissions, McNemar, through the
  existing `compare_models` path. Report §8's ±23 per-symptom figure is for
  independent estimates and would make almost nothing detectable; paired is what
  the layer already does and what the 2026-08-17 run used.
* **The criterion carries a declared threshold and a floor**, not an adjective.
  See Predictions.

### DD15 — Choosing P without the real set

P is the share of non-decisive slots carrying another signal's language. The
target it should be reasoned against is the real corpus's **claim density**:
`arch_training.md` section 9 measures the median real submission as asserting
something about **two** of the six signals.

At the default `2=0.5,3=0.5` mix, DD5 gives N−1 companion-eligible slots, so
**P = 0.5** puts on average 0.5 companions in a two-fragment example and 1.0 in a
three-fragment one — landing the modal example at two clinical claims, one
decisive and one companion. That is the reasoning; it is recorded here rather
than swept.

`P = 1.0` is degenerate and is not a candidate: it removes filler from every
non-decisive slot, so the dataset loses the register the filler libraries supply
and widens the very gap this ticket does not fix.

### DD16 — `GENERATOR_VERSION` 3, and what becomes non-comparable

2 → 3. Three things to state plainly:

* **Every number on file becomes non-comparable.** The 2026-08-16 and 2026-08-17
  results were measured on datasets this ticket changes. A fresh Arm 0 baseline is
  part of the ticket, not a follow-up, or there is nothing to compare against.
* **The deferred `expectations.txt` split lands here** (`arch_training.md`
  section 3 says it waits for exactly this bump), along with the
  `documentation/encoder/` DD3 change. The split takes filler from five libraries
  to six, which changes every `_draw_filler` outcome — so the shipped Arm 0 tree
  is a regeneration and not a reproduction (DD4).
* **The fold salt is not at risk but is not free either.** 164 of the first 200
  salts populate all five buckets of every library, so `"0"` has slack, and six
  new 40-fragment libraries have a per-library failure probability under 0.1%.
  If it ever does fail, `--find-fold-salt` is the fix — but changing the salt
  reshuffles every fragment in every library and invalidates every dataset on
  disk, so it must not be changed in the same commit as anything else. Note the
  guard (`test_the_agreed_salt_still_clears_the_real_libraries`) runs against the
  live manifest, so it can fail at task 2 — the moment the libraries land, before
  any generator work.

### DD17 — The fragment-count ceiling moves **both** ways

The provisional plan recorded only the lowering. Both directions are real:

* **Up.** Companions are additional distinct libraries, so at P > 0 an example
  can hold more fragments than there are filler libraries. The ceiling becomes
  *(eligible filler libraries) + (other signals with at least one eligible
  library)*, capped by DD8's one-per-signal. `generate()`'s up-front check must
  know this or it will refuse valid configurations. **This is the first thing
  that has ever raised that ceiling** — `arch_training.md` sections 5 and 9 both
  say only new filler libraries can, and both need correcting.
* **Down, conditionally.** If a filler library goes undeclared on some signal,
  that signal's ceiling drops. Under DD18 this does not currently happen to any
  of the seven; if DD18's reading is overturned, `recent_uti_present` caps at four
  where the others cap at five.

### DD18 — `recent_uti_present`: the policy, written before the fragments

The encoder prompt, verbatim from `data/uti1.json`:

> *Does the response indicate the patient has had a urine infection in the last
> 30 days?*

`arch_training.md` section 9 is explicit that a ceiling asserted after a
disappointing number is an excuse, and `urinary_frequency` is the worked example
of writing the policy down first. Six rules, all of which real submissions force:

1. **A suspected current infection is `null`.** "I reckon it's another UTI" — a
   *suspected* infection is not a *had*. `null` unless diagnosed or treated.
2. **Treatment is a proxy for diagnosis.** "I finished a course of nitrofurantoin
   ten days ago" is **`true`**: antibiotics for a urine infection inside the
   window are a diagnosis. This is one of the two filler families section 9 found
   missing from the libraries entirely, so it is worth covering deliberately.
3. **The axis is the 30-day window, not the tense.** "I had one last year" is
   `null` — it says nothing about the last 30 days — **not `false`**. A
   `historical` fragment needs a time marker that actually clears 30 days; "a
   while back" belongs in `hedged`.
4. **`false` is reachable and must be genuinely varied.** "I've never had a water
   infection" and "not for years" both work. Confirm 40 distinct ideas are
   available: a `false` library that is 40 rewordings of two ideas is 2 clusters.
5. **Non-urinary infections are the hard confounder and get their own library.**
   "I had thrush last month and got antibiotics for it", "I was treated for a
   chest infection in July". Every surface cue points the right way and the answer
   is `null`. This is the `adjacent` axis, and it is the one library most worth
   adding, on the same reasoning that makes `attribution` and `adjacent` the
   hardest axes for every other signal. **Six libraries, not five.**
6. **Recurrence without a window marker is `null`.** "I'm prone to them", "it
   always comes back", "like last time" say nothing about the last 30 days.

**Rules 1, 3 and 6 have a large consequence the provisional plan got backwards.**
Read against the committed `uti_speculation.txt`, all 40 lines: line 28 is "I had
one last year" (explicitly outside the window); the rest are either suspicion
about the current episode or recurrence with no window marker. **Not one line
asserts a urine infection inside 30 days.** So `uti_speculation` is `null_on`
`recent_uti_present` with basis `policy`, and it stays fully usable as filler.

The same reading applies to `expectations.txt`. Of the four lines the provisional
plan cites, "I had trimethoprim last time and it didn't touch it", "Can I try a
different antibiotic as trimethoprim doesn't seem to help me anymore" and "it
always comes back" all lack a window marker and are `null` under rules 3 and 6.
Only "I think I need stronger antibiotics this time as the last lot didn't clear
it properly" arguably implies a recently-treated episode — one line, not eleven.

This also corrects `arch_training.md` section 3, which says `uti_speculation` is
"full of lines that assert it outright". That sentence was written before this
policy existed and is wrong under it.

**If the user overturns this reading** (open question 1), the fallback is
mechanical and the plan does not change shape: `uti_speculation` goes undeclared
on `recent_uti_present`, DD17's downward branch applies, and the affected
`expectations` lines move into the new libraries rather than being declared.

### DD19 — Resolving a non-silent pair: three options, and the default

The cross-signal report (task 1) finds 29 (library, foreign-signal) pairs across
22 of the 42 libraries. Three ways to resolve one, in increasing cost:

1. **Leave it undeclared.** That library cannot companion in that signal's run.
   Free, honest, and the right default for v1 — a smaller eligible pool is a
   smaller dataset, not a wrong one.
2. **Declare `null_on` with basis `policy`** and write the note. For lines that
   mention the signal and are genuinely `null` on it.
3. **Rewrite the lines.** Right where a line is incidentally impure.

Per-line assertion is option 4 and needs 12.3; it is out of scope and it is what
the nocturia/urinary-frequency pair will eventually want.

**Budget for triage, not just for decisions.** The lexicons were tuned to stay
quiet about *filler*'s legitimate vocabulary — "blood test", "kidney scan", "a bad
night's sleep" are all real filler lines and all three are in the lint's trap
test. Signal libraries are dense in exactly that vocabulary, so the 29 pairs will
carry proportionally more lexicon over-reach than the filler run ever did.
`haematuria_null_hedged` → fever on "I dont think the last person flushed
properly" is the type: a flushed toilet is not a flushed face.

---

# Predictions, recorded before the run

Per the house rule that a result explained after the fact is an excuse.

**The declared success criterion.**

* **Primary.** On the 67 submissions, paired against Arm 0 on the same
  submissions, Arm P's `null → true` rate is at least **20 percentage points
  lower on at least four of the six signals**. That is the cell the 2026-08-17
  report put at 47%–89%, and it is the only number that can say this worked. The
  threshold is a judgement recorded in advance so it can be scored, not a derived
  quantity.
* **Guard.** Arm P's overall real-text accuracy is not below Arm 0's. Clearing
  the 66.7% all-`null` floor is reported as a separate outcome and is **not** the
  success condition — no arm is expected to clear it (prediction 2).
* **Negative control.** On the synthetic test set, `null → true` moves by less
  than 2 points in either direction. **A large synthetic gain is suspicious, not
  encouraging**: the synthetic set cannot see this failure, its cell already runs
  at 0.58%–2.53%, and a big move there would suggest companions introduced a new
  shortcut rather than removing one.

**Predictions.**

1. Arm P substantially reduces the real-text `null → true` rate. The most
   confident prediction in the ticket; the mechanism is understood and directly
   addressed.
2. Arm P does **not** get the joint model above the 66.7% all-`null` floor on its
   own. Everything else about the transfer gap — register, claim density, our own
   labelling — is untouched by this ticket.
3. **Arm C captures a meaningful fraction of Arm P's gain**, because margin
   selection has never had a validation set in which this failure occurs. If it
   captures nearly all of it, the training-data change is not what did the work
   and that is the finding.
4. The nocturia/urinary-frequency pair resists. Their libraries are the two least
   declarable `null_on` each other, so they get the fewest companions from each
   other under DD19's default.
5. 6b, when it is eventually measured, beats 6a on training efficiency per example
   and is roughly neutral or slightly worse on `null → true`, because the 92%
   `null` prior pushes the head towards `null` for reasons unrelated to reading
   the text.
6. **The sidecar shows no material difference in companion count by label mode.**
   If it does, DD5 has failed and the run is void — not reinterpreted.

---

# Task 1: The cross-signal silence report

## A. State of the world

The lint (`arch_training.md` section 8) checks that the five **filler** libraries
contain no language for the six signals that have libraries. It runs in CI
against the committed tree, currently passes with an empty per-signal baseline,
and cannot see anything about signal libraries or about `recent_uti_present`.

Nothing in this ticket has been started. This task changes no generator
behaviour and no manifest, so it can land immediately and it sizes everything
after it.

## B. Files and deliverables

**Modified:**
* `scripts/synthetic_data/lint.py` — a `RECENT_UTI_LEXICON`; generalise
  `filler_lexicon_hits` into a function over any library set; a new report
  section rendering the full grid.
* `scripts/synthetic_data/__main__.py` — no new flag; the new section prints
  under the existing `--lint`.
* `tests/test_synthetic_recombination.py` — self-test sentences for the new
  lexicon; make the recall guard skip signals with no positive library.
* `documentation/arch_training.md` — section 8 gains the cross-signal report and
  the seventh lexicon; the section 3 "Cross-signal silence" text is updated to
  say the check now exists.

**Deliverables:** `python -m scripts.synthetic_data --lint` prints, for every
(library, signal) pair, the matched line count and rate — and a **paste-ready
`null_on` block** for every pair with zero hits, which is what makes task 3
affordable without a wildcard.

## C. Instructions

1. **Generalise, do not duplicate.** `filler_lexicon_hits` currently filters
   `fragment_type == "filler"` and then loops signals. Extract the loop into a
   function taking any fragment iterable and any signal set, and re-express
   `filler_lexicon_hits` as a call to it. The existing test
   (`test_no_filler_fragment_contains_signal_language`) must pass **unchanged** —
   if it needs editing, the extraction is wrong.
2. **Skip the library's own signal.** A fragment matching its own signal's
   lexicon is the lexicon working, not a leak, and
   `test_every_lexicon_reaches_most_of_its_own_library` already measures that
   deliberately.
3. **Add `RECENT_UTI_LEXICON`.** It is an anchor-plus-modifier pair like the five
   urinary signals, not a term list: anchors are infection nouns (`uti`,
   `cystitis`, `water infection`, `urine infection`, `bladder infection`, `kidney
   infection`), modifiers are diagnosis/treatment/recency markers. Whole-word
   matching only — the existing `\b` compilation, not substrings. Add its
   `LEXICON_SELF_TEST` sentences in the same commit.
4. **The recall guard must not fail before task 2 lands.**
   `test_every_lexicon_reaches_most_of_its_own_library` parametrises over
   `SIGNAL_LEXICONS` and reads the positive library from the manifest;
   `recent_uti_present` has none yet. Parametrise instead over signals that
   **have** a positive library in the live manifest, so the new signal joins the
   guard automatically when task 2 lands. Do not add an exemption list — an
   exemption is a thing somebody has to remember to remove.
5. **Print rate as well as count**, and sort by count descending. The reader's
   job is triage across ~250 pairs, and "9 lines, 19%" is the unit of that
   decision.
6. **Emit the paste-ready block.** For every pair with zero hits, print a
   manifest fragment declaring `null_on` with `basis: "absent"`. State in the
   output header that this is *evidence of topical absence at 59%–91% lexicon
   recall, not proof*, and that a human still confirms the library's subject
   matter before committing it. That confirmation is one judgement per pair, not
   per line.
7. **Record the grid in the ticket**, not just in stdout. The 29 pairs the
   provisional plan found are the input to task 3 and they need to survive the
   chat that produced them.
8. **No manifest change and no generator change in this task.** If either is
   being edited, the task has grown.

---

# Task 2: `recent_uti_present` — the policy and six libraries

## A. State of the world

Task 1 is complete: the lint prints a cross-signal grid and has a
`recent_uti_present` lexicon whose recall guard is dormant until this task lands.

`recent_uti_present` is the seventh `send_to_encoder` signal in `data/uti1.json`,
it has no libraries, and it is the reason a six-head model could not be wired in
even if we wanted to. No code changes in this task at all.

## B. Files and deliverables

**New:**
* `data/synthetic/conditions/uti/symptoms/recent_uti/recent_uti_true.txt`
* `…/recent_uti_false.txt`
* `…/recent_uti_null_historical.txt`
* `…/recent_uti_null_hedged.txt`
* `…/recent_uti_null_thirdparty.txt`
* `…/recent_uti_null_adjacent.txt`

**Modified:**
* `data/synthetic/manifest.json` — six entries. **`null_on` is task 3's job**;
  this task adds `name`/`file`/`signal_key`/`fragment_type`/`subclass` only.
* `documentation/arch_training.md` — the DD18 policy written into section 9
  alongside the `urinary_frequency` rules; six rows in the section 3 table; the
  tree in section 3; the null-axes table gains this signal's axis choices.

**Deliverables:** six libraries at 40+ fragments each, and the labelling policy
in writing **before** any of them was written.

## C. Instructions

1. **Write DD18's six rules into `arch_training.md` section 9 first, in a
   separate commit from the fragments.** The whole point of the
   `urinary_frequency` precedent is the order. A reviewer should be able to see
   the policy commit predates the fragment commit.
2. **The `adjacent` library is not optional** (DD18 rule 5). Non-urinary
   infections treated with antibiotics are the case where every surface cue points
   the right way and the answer is `null`. Cheap now, expensive later.
3. **`historical` must clear 30 days explicitly.** A fragment whose time marker is
   vague ("a while back", "a few months ago, maybe") is `hedged`, not
   `historical`. This is the axis distinction and it is easy to blur.
4. **Check `false` for cluster count, not line count.** 40 rewordings of "never"
   and "not for years" is 2 clusters and section 3's near-duplicate report will
   say so. Write distinct situations.
5. **Section 8's register rule applies.** *Writing style is vocabulary.* If one
   of the six is written in lowercase with no terminal punctuation against five
   that are not, casing alone separates that class perfectly and the numbers are
   meaningless. Write all six in one sitting or re-read for register afterwards.
6. **Cluster-tag anything written as a twin**, per section 3. Growing a library
   means new ideas, not new twins, and a wrong marker costs both ways.
7. **Run `--lint` and read the new signal's own row.** The recall guard activates
   the moment the positive library exists; if `recent_uti_present` scores under
   45% on its own positive library, the lexicon is wrong, the library leans on
   euphemism, or both — diagnose which before moving on.
8. **Expect `test_the_agreed_salt_still_clears_the_real_libraries` to be the
   first thing that fails** if six new libraries break the salt (DD16). If it
   does, stop and raise it — do not edit a library to make it pass and do not
   change the salt in this commit.
9. **Update the section 3 table and tree in the same commit as the files.** Two
   CI tests assert the table against the files on disk, and `arch_training.md` is
   in the workflow's `rulesets` path filter precisely so a doc edit cannot skip
   them.

---

# Task 3: Manifest `null_on`, the declaration pass, the CI baseline

## A. State of the world

Tasks 1 and 2 are complete: the lint prints a cross-signal grid with a
paste-ready block, and `recent_uti_present` has six libraries and a written
policy. The manifest still declares nothing about cross-signal silence, and
`build_pools` still drops other signals' fragments entirely.

**This is the ticket's real cost**, and per DD3 it is load-bearing for 6a — not
only for 6b.

## B. Files and deliverables

**Modified:**
* `scripts/synthetic_data/manifest.py` — parse and validate `null_on` on
  `LibrarySpec`; carry the resolved per-signal value onto `Fragment`.
* `scripts/synthetic_data/lint.py` — enforce `absent`, list `policy`.
* `data/synthetic/manifest.json` — the declarations. ~250 pairs.
* `tests/test_synthetic_recombination.py` — schema tests, the CI baseline, the
  own-signal-collision test.
* `documentation/arch_training.md` — a new subsection under section 4 (the
  manifest) describing `null_on` and its two bases; section 8 gains the enforced
  check and its baseline.

**Deliverables:** a manifest where every pair a run needs is either declared or
explicitly undeclared, a CI check that fails on an `absent` pair acquiring signal
language, and generation that **refuses to start** on an undeclared pair it needs.

## C. Instructions

1. **Schema.** `null_on` is a list of objects, not strings:
   `{"signal": "...", "basis": "absent" | "policy", "note": "..."}`. Validate:
   the signal exists in the ruleset's `send_to_encoder` set; a `policy` entry
   **requires** a non-empty `note`; a library may not declare `null_on` for its
   **own** `signal_key` (that value comes from `fragment_type` and two sources
   for one value is one that can disagree with itself); no duplicate signals in
   one list.
2. **Absent is the default and it is `undeclared`, not `null`.** A library with
   no `null_on` list is undeclared on everything except its own signal. Do not
   add a manifest-level default block and do not accept a wildcard — DD1.
3. **Carry the declaration onto `Fragment`**, resolved at load time, so
   `build_pools` and the companion draw never re-read the manifest. A second
   source of the same fact is the failure mode section 7 rejects the fragment
   provenance block for.
4. **Two lint behaviours, not one** (DD2). An `absent` pair with a lexicon hit is
   a **failure**, baselined per pair exactly like `FILLER_PURITY_BASELINE`. A
   `policy` pair is **listed** with its matched-line count and its note. Do not
   collapse them into one report — the whole point is that one is checked and one
   is asserted.
5. **The CI baseline is per (library, signal) pair**, and an entry in it is a
   claim that a line reads as another signal's language, is staying where it is
   anyway, and somebody decided that on purpose. Start it empty and add only what
   the declaration pass deliberately keeps.
6. **The declaration pass itself.** Paste task 1's zero-hit block, then work the
   flagged pairs by DD19's three options. Expect the split the provisional plan
   found: genuine cross-assertions needing a clinical decision (→ undeclared),
   known documented leaks (→ rewrite), and lexicon over-reach (→ baseline).
   `flank_pain_false`'s three "it's just uncomfortable when I wee" lines are the
   documented leak and this is where they finally get resolved.
7. **`nocturia` and `urinary_frequency` stay undeclared on each other** unless the
   user says otherwise (open question 2). DD1 means a library-level assertion
   cannot express what those lines actually do, and prediction 4 already expects
   them to resist.
8. **`uti_speculation` gets `basis: "policy"` on `recent_uti_present`** with
   DD18's rules 1, 3 and 6 quoted in the note — assuming open question 1 comes
   back confirming DD18. If it does not, leave it undeclared and say so in the
   note-free absence.
9. **Generation fails fast on an undeclared pair it needs.** A `PoolError` at
   startup naming the library and the signal, not a silent drop halfway through
   10,000 examples. The message should say which of DD19's three options resolves
   it.
10. **Nothing in this task changes a generated byte.** `build_pools` may now
    *carry* other signals' fragments, but no draw uses them until task 4. Assert
    that: regenerate a fixture dataset before and after and diff it.

---

# Task 4: Companion drawing (6a)

## A. State of the world

Tasks 1–3 are complete: every (library, signal) pair a run needs is declared,
CI enforces the checkable half, and `Fragment` carries its resolved per-signal
values. Generation is still byte-identical to `GENERATOR_VERSION` 2 — no draw
uses a companion yet.

This task is the fix for the measured failure.

## B. Files and deliverables

**Modified:**
* `scripts/synthetic_data/recombine.py` — `--companion-share` plumbing;
  eligibility filtering; the companion count draw (DD5); the companion draw
  (DD6); `filler_only` in the record; the `companions` sidecar block; the ceiling
  arithmetic (DD17).
* `scripts/synthetic_data/__main__.py` — `--companion-share`, defaulting to 0.0.
* `tests/test_synthetic_recombination.py` — the byte-identity test, the blindness
  tests, the eligibility tests, the ceiling test.
* `documentation/arch_training.md` — section 5 gains the companion slot; section 7
  gains the `companions` sidecar block and `filler_only`; the section 5 and 9
  ceiling sentences are corrected per DD17.

**Deliverables:** `--companion-share 0.5` produces a dataset whose `null`
examples are full of other symptoms' clinical language, and
`--companion-share 0` produces byte-identical output to today's for the same
seed and the pre-split manifest.

## C. Instructions

1. **Inert at zero means both branches skipped** (DD4). No companion draw *and*
   no eligibility filtering, because `_draw_filler` uses `rng.choice(candidates)`
   and a changed candidate list changes the same draw's outcome. The test is
   digest equality against a committed fixture, in the shape fold mode already
   uses.
2. **Draw the companion count over N−1 slots in every mode** (DD5), including
   `null_structural`, whose remaining slot is always filler. Do not write a
   per-slot Bernoulli — the equalisation has to be by construction, and this is
   the single easiest thing in the ticket to get subtly wrong.
3. **The count draw takes no label and no label mode**, exactly as
   `sample_fragment_count` does today, and for the same reason. Give it the same
   docstring treatment; the next reader needs to know why the signature is bare.
4. **Draw signal, then library, then fragment, each uniformly, none of them
   seeing the label mode** (DD6). Uniform over *signals*, not over the pooled
   fragments — otherwise the largest library dominates, which is the same reason
   `_draw_filler` picks a library first.
5. **The primary signal's own libraries are never eligible** (DD6). Assert it in
   a test that fails if a `fever_present` example ever contains a fragment whose
   `signal_key` is `fever_present` in a non-decisive slot.
6. **One fragment per signal per example** (DD8). Track drawn signals the way
   `select_fragments` already tracks `used_libraries`.
7. **Companions come from the same split** (DD9) — free, because `build_pools` is
   already split-restricted, but write the test anyway. It is the assertion that
   would silently stop holding if pools were ever built per signal.
8. **The ceiling arithmetic moves both ways** (DD17). `generate()`'s up-front
   check currently compares the largest requested count against
   `len(pools.filler)`. It must now compare against eligible filler libraries plus
   eligible companion signals. Keep the error message's shape — it names the flag,
   the number needed and the number available, and that is why it is useful.
9. **`filler_only` goes in `meta`**, derived at assembly and written once (DD10).
   The merge and the report both need it and neither should re-derive it from
   `fragment_ids`.
10. **The `companions` sidecar block** carries: realised companion count **by
    label and by label mode** (the DD5 leak detector), the companion signal mix,
    and the companion label mix per primary label class. String-keyed like every
    other tally in `build_stats` — `json.dump` coerces int keys silently.
11. **Test the blindness numerically, not structurally.** Generate a few thousand
    examples at P = 0.5 and assert the companion-count distribution agrees across
    label modes within tolerance. A test that only checks the code path does not
    catch DD5's hole, which is arithmetic rather than control flow.
12. Per CLAUDE.md: typecheck and run `tests/test_synthetic_recombination.py`
    only. Skip the full suite and skip `npm run build`; CI's unit job is the gate.

---

# Task 5: Label vectors and multi-key emission (6b)

## A. State of the world

Task 4 is complete: `--companion-share` works, is inert at zero, and its
blindness is tested. Every example still emits exactly one key, for the signal
the run was asked for.

**This task is built and not measured** (DD13). It exists so the knob is there,
tested, and documented; the arm that would measure it is a follow-up.

## B. Files and deliverables

**Modified:**
* `scripts/synthetic_data/recombine.py` — DD7's combination rule; `labels_for_mode`
  generalised to a vector; the per-signal realised prior in the sidecar.
* `scripts/synthetic_data/__main__.py` — `--emit-signals primary|all`, defaulting
  to `primary`.
* `tests/test_synthetic_recombination.py` — the combination-rule table as tests.
* `documentation/arch_training.md` — 12.2 and 12.5 updated to say which half is
  built; section 7's missing-key-vs-`null` paragraph gains the vector case.

**Deliverables:** `--emit-signals all` emits a correct label vector per example,
and `--emit-signals primary` is byte-identical to task 4's output.

## C. Instructions

1. **Implement DD7's table exactly, including the masked row.** Any fragment
   undeclared on S ⇒ **no key for S**. Not `null`. Section 7's distinction between
   a missing key and a `null` value is the thing that makes merged training sound,
   and getting it backwards teaches every head to answer "not mentioned" to every
   question it was not trained on.
2. **Test the table row by row**, including the unreachable row: assert that a
   two-assertion example cannot be constructed, so DD8 is verified rather than
   assumed.
3. **`--emit-signals primary` must be byte-identical** to task 4's output for the
   same seed. Same fixture-digest shape as DD4's test.
4. **Report the realised prior per signal in the sidecar**, so DD12's "decided and
   reported, not emergent" is a fact in the file rather than a claim in a doc.
   Expect roughly 3/5/92 per head at `all`.
5. **Do not touch the training path.** `train.py` already separates `--dataset`
   from `--signals` and reads a vector fine. If it needs changing, that is the
   follow-up ticket, not this one.
6. **Do not generate a `--emit-signals all` tree for the run.** Task 7's arms are
   Arm 0, Arm P and Arm C. Adding a fourth is what DD13 declines.

---

# Task 6: `GENERATOR_VERSION` 3, the split, the merge relaxation, regeneration

## A. State of the world

Tasks 1–5 are complete: the mechanism exists, is tested and is inert at its
defaults. Nothing on disk has been regenerated and `GENERATOR_VERSION` is still 2.

## B. Files and deliverables

**Modified:**
* `scripts/synthetic_data/recombine.py` — `GENERATOR_VERSION = 3`.
* `data/synthetic/filler/expectations_uti.txt` (new) and
  `data/synthetic/filler/expectations.txt` — the deferred split; manifest entries
  for both, with `null_on` declarations for each half.
* `scripts/encoder_training/merge.py` — `check_structural_nulls` restricted to
  `filler_only` examples; `companion_share` recorded in `merged_from` and refused
  when sources disagree.
* `tests/test_encoder_training_merge.py` — the relaxed assertion and the new refusal.
* `documentation/arch_training.md` — section 3's `expectations.txt` paragraph
  (the split has now happened); section 7's merge contract; section 12.7's
  sequencing.
* `documentation/encoder/` — the DD3 change section 3 defers to this bump.

**Deliverables:** Arm 0 and Arm P fold trees on disk for all seven signals, and a
merged tree per arm that `dataset.load_folds` accepts with no new escape hatch.

## C. Instructions

1. **Bump the version in its own commit, before regenerating.** The merge refuses
   sources that disagree on `generator_version`, which is the guard that stops a
   half-regenerated tree being trained on.
2. **Split `expectations.txt` by the section 3 rule** — condition-specific
   vocabulary goes to `conditions/uti/filler/`, the rest stays shared. About 26 of
   100 lines are UTI-specific. Both halves need their own `null_on` declarations;
   do not copy the parent's without re-reading, because the split changes what each
   half contains.
3. **Relax, do not delete, the structural-null assertion** (DD11). It still runs;
   it runs over `filler_only` examples. Deleting it would put back the failure it
   was written for: six divergent null sets collapsing into whichever arrived
   first, every head's prior shifting, and nothing downstream noticing.
4. **Refuse a merge whose sources disagree on `companion_share`.** Same shape as
   the existing `generator_version` refusal, same reasoning.
5. **Regenerate both arms at identical settings apart from P.** Same seed, same
   counts, same folds, same salt. If anything else differs the comparison is not
   readable and there is no way to recover it after the fact.
6. **Record in the section 10 table that every prior number is now
   non-comparable** (DD16). Not as a footnote — the tables themselves need a
   header line saying which `GENERATOR_VERSION` produced them.
7. **Correct the two ceiling sentences** in sections 5 and 9 per DD17, and the
   `uti_speculation` sentence in section 3 per DD18. All three are load-bearing
   statements that are now wrong.

---

# Task 7: The run and the report

## A. State of the world

Tasks 1–6 are complete: Arm 0 and Arm P fold trees exist for all seven signals,
each merged into a joint tree, at `GENERATOR_VERSION` 3.

## B. Files and deliverables

**Modified:**
* `scripts/encoder_training/report.py` — a `companions` header block; the
  `null → true` cell as the headline on the real-text section.
* `reports/encoder_training/<date>.md` and `<date>-plain-english.md` — the write-up.
* `documentation/arch_training.md` section 10 — current state.
* `planned_updates/multi_symptom_recombination.md` — mark superseded by this file.

**Deliverables:** one report per signal holding Arm 0, Arm P and Arm C, with the
real-text `null → true` cell as the headline and the declared threshold scored.

## C. Instructions

1. **Ten fold-trainings: Arm 0 × 5 folds, Arm P × 5 folds.** Joint six-head, the
   established recipe, nothing else varied.
2. **Arm C costs nothing and must not be skipped** (DD13). Take Arm 0's trained
   heads and re-run `select_margin` against Arm P's validation split. No
   retraining, no regeneration. It is the arm that tells you whether the expensive
   half of this ticket was necessary.
3. **Score on both instruments** (`arch_training.md` section 9): the fold-pooled
   synthetic test set *and* the 67 submissions. They answer different questions
   and neither replaces the other.
4. **The real-text comparison is paired** (DD14) — same submissions, McNemar,
   through the existing `compare_models` path, which already refuses to silently
   skip a pair for any reason other than a genuine dataset difference.
5. **Score the declared threshold as written**, before interpreting anything.
   20 points on at least four of six signals, the accuracy guard, and the negative
   control. Record whether each held. Three of four held last time and saying so
   plainly is what made that report usable.
6. **Read the negative control the right way round.** A large synthetic gain is
   evidence of a new shortcut, not of success.
7. **Check the DD5 leak detector before reading any score.** If the sidecar shows
   companion count differing by label mode, prediction 6 has failed and the run is
   void — do not reinterpret it.
8. **Say what the 67 submissions are.** Hand-written by us, labelled by us,
   provenance unresolved and still gating committing the corpus
   (`arch_training.md` section 9). The 2026-08-17 report calls them "hand-written
   realistic submissions"; keep that wording rather than "real submissions". The
   difference is load-bearing for how much the headline is worth.
9. **State the fold-mode optimism** — each fold's margin was tuned on a sibling
   fold's test clusters — as every report using fold mode has to.

---

# Cost

| task | shape | rough size |
|---|---|---|
| 1 | lint only, no manifest or generator change | small, lands immediately |
| 2 | six libraries × 40 fragments, plus the policy | large but purely authoring, no code |
| 3 | ~250 declarations, ~29 needing judgement, plus schema and lint enforcement | **the ticket's real cost** |
| 4 | generator change with four blindness tests | medium |
| 5 | combination rule, flag off by default | small |
| 6 | version bump, file split, merge relaxation, regeneration | medium, mostly waiting |
| 7 | 10 fold-trainings + 1 free arm, plus the write-up | GPU-bound |

Tasks 1 and 2 are independent of each other and of everything else, so they can
run in parallel. Tasks 3–6 are strictly sequential.

**Compute.** Ten fold-trainings, plus DD10's loss of the structural-null dedup:
at P > 0 the merged tree keeps six copies of what it used to keep one of, growing
the joint tree by roughly 1.5× against today — about a third more forward passes
per epoch on Arm P. Arm 0 is unaffected. The previous ticket's outstanding sweep
(`joint_multi_head_training_implementation.md` task 5) is still unpaid, so
these two runs compete for the same GPU.

---

# Open questions for the user

1. **Does DD18's reading of `uti_speculation` hold?** Under rules 1, 3 and 6, not
   one of its 40 lines asserts a urine infection inside 30 days, so it stays
   usable as filler and roughly half of task 3's expected cost disappears. This is
   a clinical labelling call and it is the single question that most changes what
   this ticket costs. The provisional plan assumed the opposite. If it is
   overturned the fallback is mechanical (DD17's downward branch) and nothing
   else changes.
2. **`nocturia_true` and `urinary_frequency`: confirm they stay undeclared?**
   DD1 means a library-level assertion cannot express what those lines do, so the
   only options are undeclared or rewriting 30+ lines across six libraries.
   Recommend undeclared, and accept prediction 4.
3. **P = 0.5?** DD15's reasoning is the real corpus's claim density: the median
   real submission asserts something about two of six signals, and P = 0.5 lands
   the modal example at two claims. If you would rather a different value, it
   needs to be chosen on grounds like these and **not** by scoring against the 67
   submissions (DD14).
4. **Confirm 6b is built and not measured?** DD13's argument is that its arm is
   not comparable on the deciding metric and costs five more fold-trainings. The
   provisional plan recommended measuring it as a second arm.
5. **Which run goes first** — this ticket's two arms, or the previous ticket's
   outstanding A1/A2/A3 sweep? They compete for the same GPU, and this ticket
   makes the previous one's datasets non-comparable (DD16), which is an argument
   for either order depending on whether that sweep's numbers are still wanted.
