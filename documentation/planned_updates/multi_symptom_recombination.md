# Ticket 6 — Multi-symptom recombinations (provisional plan)

**Status: provisional, and superseded.** The step-2 review corrected seven things
here — see `multi_symptom_recombination_implementation.md`, "What changed from the
provisional plan". Build from that file; this one is kept for the reasoning behind
the decisions the review left standing.

**Nothing here is built and nothing here is agreed.** This is
the step-1 output for `arch_training.md` 12.2–12.5. It records the design
decisions, the measurements taken while writing it, and the questions that have
to be answered before it becomes an implementation plan.

Read first: `arch_training.md` sections 2, 3, 5, 7, 8, 9, 12.2–12.5, 12.7, 12.8,
and `reports/encoder_training/2026-08-17-plain-english.md` sections 3, 4 and 9.

---

## 1. What this ticket is answering

The 2026-08-17 sweep measured a shortcut we had predicted and never quantified.
On the synthetic test set the six-head joint model invents a symptom into a
patient's form 0.58%–2.53% of the time. On the 67 real submissions the same cell
runs **47%–89%**, and the joint model scores 39.1% across the 402 real answers
against 66.7% for answering `null` to everything.

The cause is a property of the *data*, not of joint training:

> Every `null` example for a signal pairs the absence of that signal's language
> with **bland, non-clinical filler**. No head has ever seen a message that is
> dense with clinical language about another symptom whose correct answer is
> still `null`.

So "clinical-sounding text ⇒ not `null`" is a perfect rule on our data and a
catastrophic one on real text, where the median submission asserts something
about two of the six signals and dysuria is present in 56 of 67.

**This ticket's deliverable is examples where the text is full of other
symptoms' clinical language and the label for this signal is still `null`.**
Everything else in 12.2–12.5 is machinery in service of that sentence.

---

## 2. The scope split that matters: 6a and 6b

12.5 is usually described as one thing. It is two, they have very different
costs, and only the first is on the critical path.

**6a — companion fragments, single-key output.** The non-decisive slots of an
example are drawn from *other signals' libraries* instead of from filler. The
emitted label stays exactly what it is today: one key, for the signal the run
was asked for. A `fever_present: null` example now reads "it's been burning
when I wee and I'm up three times a night", and fever is still `null`.

**6b — label vectors and multi-key output.** The same example additionally emits
`dysuria_present: true`, `nocturia_present: true`, and `null` for the signals
every fragment is declared silent about.

The important property, and the reason to separate them:

> **6a fixes the measured failure and leaves every head's class prior exactly
> where it is.** 6b adds supervision per example and moves each head's prior
> from 15/25/60 to roughly 3/5/92.

6a is a change to what the *text* contains. 6b is a change to what the *labels*
contain. The report's finding is entirely about the first. 6b is the 12.2
payoff — more label per example, one dataset instead of six, fewer forward
passes — and it is worth having, but it is an optimisation with a real cost and
it should be measured rather than assumed.

**Recommendation: build both mechanisms in this ticket, ship 6a as the default
and 6b behind a flag, and run them as two arms of one comparison.** The
machinery is nearly common — once silence is declared per library, emitting the
extra keys is a small function — and shipping only 6a would leave a knob nobody
can decide whether to turn, which is the mistake 12.6 warns about in its own
context.

---

## 3. Design decisions

### DD1 — Declared silence is three-valued, and undeclared is not silent

For every (library, signal) pair the manifest declares one of:

| state | meaning | may the library appear in an example claiming this signal's key? |
|---|---|---|
| **asserts** | the library's own signal; the value comes from `fragment_type` as today | yes, and it supplies the value |
| **silent** | every line says nothing about this signal | yes, and it contributes `null` |
| **undeclared** | nobody has decided | **no** |

Undeclared is the default and it is *not* silence. This is not pedantry — it is
the exact failure this project has already had. `arch_training.md` section 3
records that `uti_speculation` is full of lines asserting `recent_uti_present`,
which nothing catches, because a lexicon is only written for a signal we decided
to train. A closed-world default ("silent about everything I do not name") would
mean adding an eighth signal to the ruleset silently asserts that all 42
existing libraries are silent about it. Rejected.

No wildcards, and no manifest-level default block. The declaration is the
guarantee; a shorthand for asserting it in bulk is a shorthand for asserting it
without reading it.

### DD2 — Silence is declared in the manifest and proved by the lint

The declaration is a per-library `silent_on` list. The lint check is a direct
generalisation of the one that already exists: today `filler_lexicon_hits`
walks fragments where `fragment_type == "filler"` and matches all six lexicons;
generalised, it walks every library and matches the lexicons for the signals
that library **claims** to be silent about. Filler libraries become libraries
declaring silence on every signal, and the existing check falls out as a special
case with no behaviour change.

It runs in CI against the committed tree with a per-pair baseline, exactly like
`FILLER_PURITY_BASELINE`. An entry in the baseline is a claim that a line reads
as another signal's language, is staying where it is anyway, and that somebody
decided that on purpose.

### DD3 — Companion drawing is a flag, and at zero it is byte-identical

`--companion-share P` (default `0.0`) is the probability that a non-decisive
slot is drawn from another signal's eligible libraries rather than from filler.
At `P=0.0` the whole companion path is skipped — not merely weighted to zero,
*skipped*, so it consumes no RNG draw and the output is byte-identical to
today's for the same seed. Fold mode set this precedent and there is a test
shape to copy.

This is what makes the comparison readable. The same seed, the same libraries
and `--companion-share 0` reproduces the A1 datasets exactly; only `P` varies.

### DD4 — The companion draw must be blind to the label, and the sidecar must prove it

This is section 5's fragment-count argument in a new place, and it is the
easiest thing in this ticket to get wrong.

If companions were more common in `true` examples than in `null` ones, we would
have replaced "clinical language ⇒ not null" with "clinical language ⇒ true",
which is the same failure wearing a different hat. So:

* the companion/filler decision is drawn from one distribution that never sees
  the label mode;
* **which** signal and **which** of its libraries is drawn uniformly over
  eligible libraries, also blind to the label mode — so companions are not
  disproportionately `true` in `true` examples;
* the sidecar gains a `companions` block reporting realised companion share
  **by label and by label mode**, the signal mix, and the companion label mix
  per primary label class.

Nothing downstream would surface a violation on its own. It would present as a
validation score that looks fine and a model that does not transfer — which is
precisely the shape of the thing this ticket exists to fix.

### DD5 — Combination is validated on the vector, not on the primary signal

For each signal S over the fragments of one example:

| fragments' states on S | result |
|---|---|
| any fragment **undeclared** on S | **no key for S** (masked; section 7's missing-key semantics) |
| ≥1 asserts, all assertions agree | key = that value |
| ≥2 assert and disagree | **forbidden combination — never drawn** |
| all silent | key = `null` |

Label-first survives intact, and this is the point (12.5). The target vector is
chosen first, each pool is filtered down to the fragments compatible with it,
and then the draw happens. We never generate text and inspect it. Filtering
before drawing rather than drawing and rejecting also keeps generation
deterministic and stops the accept/reject rate quietly skewing the mix.

### DD6 — At most one fragment per signal per example

Today's Rule 2 ("one signal, one decisive fragment") generalises rather than
disappears. Two dysuria fragments in one example either agree — doubling the
evidence for one claim and teaching nothing — or disagree, which DD5 forbids
anyway. One per signal makes the disagreement case unreachable by construction
instead of by check.

### DD7 — Companions come from the same split as the example

`build_pools` already restricts to one split, so this is free — but it has to be
stated, because the failure is subtle. If a fever *test* example could contain a
dysuria *train* fragment, and that same dysuria fragment appeared in fever's
training examples, the model has seen part of the test text during training.
Section 6's whole argument is that a fragment lives on exactly one side of the
split; that argument now has to hold across signals too.

### DD8 — Filler eligibility becomes signal-dependent, and that has consequences

A library can only be drawn into an example claiming key S if it is declared
silent (or asserting) on S. That makes the *available filler libraries* a
function of which signal is being generated — for `recent_uti_present`,
`uti_speculation` is out and at least four `expectations` lines are out (see
section 5).

Three consequences, all of which have to be accepted rather than worked around:

* `_draw_filler` picks a library uniformly, so five libraries versus four
  changes every generated example for that signal. Unavoidable; it lands in the
  same `GENERATOR_VERSION` bump as everything else here.
* The fragment-count ceiling (section 5) is the number of *eligible* filler
  libraries, so it is now per-signal. A `recent_uti` run caps at four fragments
  where the others cap at five.
* **The structural nulls stop being byte-identical across the six per-signal
  runs**, which is the load-bearing assertion `merge-folds` makes and refuses to
  proceed without. See DD10.

### DD9 — The class prior is a decided number, not an emergent one

Under 6b the arithmetic is unavoidable: a signal is decisive in one run and
merely silent in the other six, so each head's realised prior moves from
15/25/60 towards something like 3/5/92, the exact figure depending on
`--companion-share`. 12.8 predicted this ("the fever head would see ~93% `null`
rather than 60%").

**Do not reweight the loss.** `arch_encoder_training.md` section 8 rejected that
deliberately and the reasoning still holds: the training mix is a generator flag
rather than a measured prior over real submissions, so reweighting corrects
towards a second arbitrary target, whereas the decision margin is tunable,
versioned, documented and already selected per head on validation data.

What this ticket owes instead is that the prior is **reported and chosen**: the
sidecar states each signal's realised label mix, and the mix is reachable by
flag rather than being whatever falls out. Note the standing worry from the
2026-08-17 report §9.3 — the margin is currently selected on validation data
where the dangerous cell barely occurs. This ticket makes that cell occur in
validation, which is the first time margin selection will have been given a fair
question to answer.

### DD10 — What happens to `merge-folds`

Two options, and this is a real fork.

* **(a) Keep per-signal runs and the merge.** Under 6a nothing changes for the
  merge except that the byte-identical structural-null assertion breaks
  (DD8). Each run's nulls are kept separately, the tree grows, and each head is
  masked on the others as today.
* **(b) Generate the multi-signal dataset directly** and let it replace the
  merge for this purpose. This is where 12.2 says the architecture is going
  ("trained multi-head from one dataset rather than one dataset per head").

Recommendation: **(a) for this ticket**, (b) as a follow-up. The merge tool is
built, tested and understood; replacing it in the same ticket that changes what
every example contains would mean two independent things moving at once and no
clean A1 to compare against. The structural-null assertion is relaxed to "assert
identity when `--companion-share` is 0 in every source, and record the share in
`merged_from` otherwise".

### DD11 — This bumps `GENERATOR_VERSION` and regenerates everything

2 → 3. Two consequences to state plainly rather than discover:

* **Every number on file becomes non-comparable.** The 2026-08-16 and 2026-08-17
  results were measured on datasets this ticket changes. A fresh A1 baseline at
  `--companion-share 0` is part of the ticket, not a follow-up, or there is
  nothing to compare against.
* The deferred `expectations.txt` split (section 3) and the
  `documentation/encoder/` DD3 change land here, because this is the change that
  regenerates everything anyway and section 3 says the split waits for exactly
  that.

---

## 4. The measurement that sizes this ticket

The expensive part of ticket 6 is not the code. It is deciding, for ~200
(library, signal) pairs, whether the library is actually silent. Run against the
committed tree with the six existing lexicons, applied to signal libraries
rather than only to filler:

| lines | rate | library → foreign signal it reads as |
|---|---|---|
| 9 | 19% | `nocturia_null_thirdparty` → `urinary_frequency_present` |
| 8 | 15% | `nocturia_true` → `urinary_frequency_present` |
| 6 | 11% | `nocturia_false` → `urinary_frequency_present` |
| 5 | 12% | `dysuria_null_hedged` → `urinary_frequency_present` |
| 5 | 11% | `urinary_frequency_false` → `nocturia_present` |
| 4 | 9% | `nocturia_null_historical` → `urinary_frequency_present` |
| 3 | 7% | `urinary_frequency_null_hedged` → `nocturia_present` |
| 3 | 7% | `haematuria_null_hedged` → `fever_present` |
| 3 | 7% | `urinary_frequency_true` → `nocturia_present` |
| 3 | 6% | `nocturia_null_attribution` → `dysuria_present` |
| … | | 19 further pairs at 1–2 lines each |

**29 (library, foreign-signal) pairs, touching 22 of the 42 libraries.** Read it
as a lower bound: the lexicons catch 59%–91% of their own positive libraries
(section 8), so the true count is higher.

Inspecting the hits splits them into three kinds, and the split is the actual
work of this ticket:

**Genuine cross-assertions requiring a clinical decision.** `nocturia_true`
holds "Four trips to the bathroom between midnight and six this morning".
Whether that asserts `urinary_frequency_present` is a *labelling policy
question* (section 9's "undeclared policy" case), not a lint failure — and it is
the nocturia/urinary-frequency pair the 2026-08-17 report already identified as
the entangled one. `urinary_frequency_false`'s "I haven't had to get up any more
than usual for a wee" is arguably `nocturia_present: false`.

**Known documented leaks.** `flank_pain_false`'s "My sides feel fine, it's just
uncomfortable when I wee" — the counter-example section 3 has been carrying for
months, now caught mechanically for the first time.

**Lexicon over-reach.** `haematuria_null_hedged` → fever on "I dont think the
last person flushed properly" and "on that hot day walking". A flushed toilet is
not a flushed face. These are baseline entries, precisely as "blood test" and
"kidney scan" already are.

Three ways to resolve a non-silent pair, in increasing cost:

1. **Leave it undeclared.** That library cannot companion in that signal's run.
   Free, honest, and the right default for v1 — a smaller eligible pool is a
   smaller dataset, not a wrong one.
2. **Rewrite the lines.** Right where the line is incidentally impure.
3. **Declare the assertion per line**, which needs the JSONL library format of
   12.3. Out of scope here; it is what the nocturia/urinary-frequency pair will
   eventually want.

---

## 5. `recent_uti_present`: what the new libraries have to satisfy

Five libraries at 40 fragments each are being written now — `true`, `false`,
`null_historical`, `null_hedged`, `null_thirdparty`. The encoder prompt is:

> *Does the response indicate the patient has had a urine infection in the last
> 30 days?*

**Write the labelling policy down before the fragments, not after.** Section 9
is explicit that a ceiling asserted after a disappointing number is an excuse,
and `urinary_frequency` is the worked example of doing it the right way round.
Five questions this signal forces, all of which real submissions produce:

1. **A suspected current infection.** "I reckon it's another UTI" — a *suspected*
   infection is not a *had*. Proposed policy: `null` unless diagnosed or
   treated. Load-bearing, because all 40 lines of `uti_speculation` are this case.
2. **Treatment as a proxy for diagnosis.** "I finished a course of
   nitrofurantoin ten days ago." Proposed policy: **`true`** — antibiotics for a
   urine infection inside the window are a diagnosis. This is one of the two
   filler families section 9 found missing from the libraries entirely, so it is
   worth covering deliberately.
3. **The window is 30 days and the `historical` axis is the window, not the
   tense.** "I had one last year" is `null` — it says nothing about the last 30
   days — not `false`. Fragments need a time marker that actually clears 30
   days; "a while back" belongs in `hedged`, not `historical`.
4. **What makes `false` reachable.** "I've never had a water infection" and "not
   for years" both work. Worth confirming 40 are available, because a `false`
   library that is really 40 rewordings of two ideas is 2 clusters (section 3).
5. **Non-urinary infections are the hard confounder.** "I had thrush last month
   and got antibiotics for it", "I was treated for a chest infection in July".
   Every surface cue points the right way and the answer is `null`. **This is the
   `adjacent` axis and it is the one library most worth adding to the five**, on
   the same reasoning that makes `attribution` and `adjacent` the hardest axes
   for every other signal.

Two things the new libraries break on arrival, both of which are the point:

* **`uti_speculation` stops being usable filler.** 11+ of its 40 lines assert or
  hedge a prior infection. Under DD1 it is undeclared on `recent_uti_present`
  and therefore ineligible in `recent_uti` runs. See DD8 for the consequences.
* **`expectations.txt` is not silent either.** "I think I need stronger
  antibiotics this time as the last lot didn't clear it properly", "I had
  trimethoprim last time and it didn't touch it", "Can I try a different
  antibiotic as trimethoprim doesn't seem to help me anymore", "it always comes
  back". Either those lines move into the `recent_uti` libraries, or
  `expectations` is undeclared on this signal and unavailable to it.

**The fold salt is not at risk.** 164 of the first 200 salts currently populate
all five buckets of every library, so `"0"` has substantial slack; five new
40-cluster libraries have a per-library failure probability under 0.1%. It rises
if the libraries are heavily cluster-tagged. If it ever does fail,
`--find-fold-salt` is the fix — but changing the salt reshuffles every fragment
in every library and invalidates every dataset on disk, so it is not a free move
and it should not be made in the same change as anything else.

---

## 6. What has to be true for this ticket to have worked

One measurement, decided before the run per the house rule:

**The primary claim.** On the 67 real submissions, a head trained at
`--companion-share > 0` has a materially lower `null → true` rate than the same
head at share 0, at comparable accuracy on the decisive slice. That is the cell
the 2026-08-17 report put at 47%–89%, and it is the only number that can say
this worked.

**The negative control.** On the synthetic test set the improvement should be
small or absent, because the synthetic set cannot see this failure — its
`null → true` cell already runs at 0.58%–2.53%. **A large synthetic gain would be
suspicious, not encouraging**, and would suggest companions have introduced a new
shortcut rather than removed one.

**Predictions recorded now:**

* 6a will substantially reduce the real-text `null → true` rate. This is the
  most confident prediction in the ticket; the mechanism is understood and
  directly addressed.
* 6a will *not* get the joint model above the 66.7% all-`null` floor on its own.
  Everything else about the transfer gap — register, claim density, our own
  labelling — is untouched by this ticket.
* 6b (multi-key) will beat 6a on training efficiency per example and will be
  roughly neutral or slightly worse on `null → true`, because the 92% `null`
  prior pushes the head towards `null` for reasons unrelated to reading the text.
* The nocturia/urinary-frequency pair will resist. Their libraries are the two
  that are least silent about each other, so they are the two that get the
  fewest companions from each other under option 1 of section 4.

---

## 7. Provisional task breakdown

For step 2 to review and step 3 to expand. Roughly in dependency order.

1. **The cross-signal silence report.** Generalise `filler_lexicon_hits` to any
   library, add a `recent_uti_present` lexicon, print the full grid. No manifest
   change, no generator change. This is a reporting-only change that sizes
   everything after it and can land immediately.
2. **The `recent_uti_present` libraries and their labelling policy**, written
   into `arch_training.md` section 9 alongside the `urinary_frequency` rules.
   Independent of all code work.
3. **Manifest schema: `silent_on`, and the declaration pass.** Parse, validate,
   fail generation on an undeclared pair that a run needs. The CI baseline for
   known non-silent pairs. This is the ticket's real cost.
4. **Companion drawing (6a).** `--companion-share`, eligibility filtering, DD4's
   blindness, the `companions` sidecar block, the byte-identity test at share 0.
5. **Label vectors and multi-key emission (6b).** DD5's combination rule,
   `--emit-signals primary|all`, the per-signal realised prior in the sidecar.
6. **`GENERATOR_VERSION` 3, the `expectations.txt` split, `merge-folds`
   relaxation, regenerate the A1 baseline.**
7. **The run and the report.** Two arms minimum (share 0 vs share > 0), five
   folds, scored on the synthetic test set *and* the 67 real submissions, with
   the real-text `null → true` cell as the headline.

---

## 8. Open questions

1. **Is 6b in this ticket at all, or does it become ticket 6c?** The
   recommendation above is to build it behind a flag and measure it. The
   argument for deferring is that 6a alone is the fix and 6b changes every
   head's prior at the same time.
2. **`nocturia_true` and `urinary_frequency`: silent or asserting?** A clinical
   decision that nothing in the tooling can make. It affects 30+ lines across
   six libraries and it is the pair the model is already worst at.
3. **Does `recent_uti_present` get an `adjacent` library?** Section 5.5 argues
   yes and it is cheap to add now, expensive to add later.
4. **Do the four `expectations.txt` treatment-history lines move into the
   `recent_uti` libraries, or does `expectations` go undeclared on that signal?**
   The first is better data and forces the file split; the second is free.
5. **What companion share?** A sweep (0, 0.3, 0.6, 1.0) is the honest answer and
   costs four times the training. One non-zero value plus the control is the
   minimum that says anything.

---

## 9. What this ticket deliberately does not do

* **It does not make the encoder deployable.** Seven heads and a safety review
  against `arch_encoder.md`'s boundary are still between here and that, and
  `EncoderOutput.validate_against` still requires all seven keys.
* **It does not fix the register gap.** The 67 real submissions sit in a tidier
  register than the libraries aim at, and companions do not change register.
* **It does not add ideas.** Every companion fragment is a fragment that already
  exists in some library. Effective sample size per signal is unchanged
  (section 10), and every confidence interval this pipeline prints stays exactly
  as wide as it is today. What changes is what the *null* examples look like,
  which is the whole point and is not a coverage gain.
* **It does not touch 12.1 (templating) or 12.6 (character noise).** Both remain
  independent and neither blocks this.
