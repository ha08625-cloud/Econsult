# Provisional plan: lexical variant expansion v2 — entity classes (12.10b)

**Status: provisional.** Stage 1 of the workflow — the design decisions are made
and argued, the task list is a shape rather than an instruction set, and the open
questions at the end are for the stage-2 review pass to close.

Read first: `arch_training.md` §8 (the lint's two blind faults), §10 (effective
sample size), §12.6 (the noise pass), §12.10 (this pass as built and measured);
then `reports/encoder_training/2026-09-04-lexical-variant.md` and its
pre-registration, which are what this plan exists because of.

**The v1 plan of record is `lexical_variant_expansion_implementation.md`. Its
Task 7 — extending the fever rules to the other six signals — is deliberately
left unfinished and is superseded by this plan.** Not because it failed, but
because §5 below shows it would have bought almost nothing: the fever rule set
moves the surface vocabulary by a measured 10.8%, and rolling it across six more
signals would have cost roughly 200 more hand-written invariants for a
proportionate share of that. This plan is the cheaper and larger version of the
same idea.

---

## 1. The rationale, stated first because it is different from v1's

**This ticket exists to reduce the model's opportunity to overfit surface
n-grams.**

The training data is built by recombining a few hundred hand-written fragments
into ten thousand examples. Every fragment therefore appears in dozens of
examples, *character for character identical every time*. A model that memorises
"the sequence `my sister has been running a temperature` means null" has learned
the fragment inventory, not the language. Widening the surface forms each
fragment can take is a direct attack on that, and it is the only lever available
that does not require writing new fragments.

**This is not what v1 was for, and the distinction has to be kept.** V1's purpose
was **decorrelation**: §8 records cases where the *choice of word* separated a
label class perfectly, and Task 1 measured `fever` on 41 of 45
`fever_null_historical` lines and 0 of 50 `fever_null_attribution` ones. V1
attacked that specific fault and, on the evidence of the 2026-09-04 run, removed
it — `null → true` flips under paraphrase fell from 46 to 10.

The two objectives are different and this plan serves the second:

| | v1 (decorrelation) | v2 (surface variety) |
|---|---|---|
| the fault | word choice predicts the label | fragments recur verbatim |
| the evidence it exists | Task 1's token–label skew | every fragment appears in dozens of examples |
| what a rule swaps | `fever` ⇄ `temperature` | `sister` ⇄ `brother` ⇄ `cousin` |
| does a flip mean an error? | arguably — the words differ in register | **unambiguously yes** |

That last row is why this is a *better* experiment than the one just run, and it
is worth stating plainly. There is no defensible reason for a model's answer to
change when `sister` becomes `brother`. Any flip is the model reading noise. With
`fever → temperature` a reader could always argue the two words carry different
register, which made the flip rate a softer instrument than it looked.

**One thing this plan does not claim.** It adds no ideas and no effective sample
size, exactly as v1 did not. The expanded tree holds the same examples built from
the same 417 clusters. No report from this work may quote an example count as
growth.

---

## 2. What changed since v1, and why v1's answer was small

The 2026-09-04 run came back small on every synthetic measure: flips 1.89% →
0.84%, and the fault costing the clean model **0.21 decisive points**. The
hypothesis this plan is built on is that the result was small because **the pass
was small**, not because the idea is wrong.

Measured over the committed libraries, applying every rule at every site — the
ceiling, not the operating point:

| rule set | hand-written units | rules | new 4-grams reachable |
|---|---|---|---|
| v1 fever rules | 36 individually-reviewed rules | 36 | **+10.8%** |
| v2 entity classes | 6 word lists | 210 | **+25.8%** |
| both together | 6 lists + 36 rules | 246 | **+36.6%** |

And the realised rate was about a quarter of the ceiling — the run recorded 1.375
substitutions per 100 words against 5.12 available. So the model saw roughly a 3%
widening of its n-gram inventory. **A small effect from a 3% intervention is the
expected result, not an informative one.**

The reason v1 was structurally limited is worth naming, because it was a
deliberate decision that was right for v1's purpose and wrong for this one.
**v1's DD11 excluded the filler libraries** on the grounds that "filler carries no
label, so expanding it cannot decorrelate anything". Correct for decorrelation.
But 45,706 of the manifest's 53,678 words are filler and other signals' text, so
the pass was pointed away from 85% of the vocabulary. **This plan reverses DD11
for the surface-variety objective while leaving it standing for decorrelation.**

---

## 3. What an entity class is, and why it is cheap

A class is one hand-written list of interchangeable referents. Every ordered pair
within it becomes a rule, so an *N*-word list yields *N*×(*N*−1) rules from one
review.

The proposed classes and what they cost:

| class | words | rules |
|---|---|---|
| adult female | mum, mother, wife, sister, aunt, girlfriend | 30 |
| adult male | dad, father, husband, brother, uncle, boyfriend | 30 |
| elder female | grandma, grandmother, nan, gran | 12 |
| elder male | grandad, granddad, grandfather | 6 |
| adult neutral | partner, friend, neighbour, colleague, coworker, cousin, flatmate, housemate, mate, boss | 90 |
| weekday | monday … sunday | 42 |
| **total** | **38 words in 6 lists** | **210** |

**The roll-out is genuinely cheap, and that is measured rather than asserted.**
387 library lines carry one of these referents, and they are spread across every
signal:

| where | lines |
|---|---|
| shared filler (`tangents`, `justifiers`) | 88 |
| fever | 71 |
| nocturia | 57 |
| flank pain | 39 |
| dysuria | 36 |
| urinary frequency | 35 |
| haematuria | 33 |
| recent UTI | 28 |

**82% of them are outside fever.** One list set covers all seven signals, where
v1's fever rules would have needed authoring seven times. That is the whole of
the "cheap to roll out" claim and it is the main reason to prefer this shape.

---

## 4. Scope

**In scope**

* Six entity-class word lists at `data/expansion/classes/<class>.json`, expanded
  into rules by the loader (DD3).
* Whatever change `expand.py` needs to accept a class file alongside a rule file,
  and to run rules that are **signal-agnostic** rather than scoped to one signal
  (DD2).
* Re-running the four-cell 2×2 with the **combined** fever + entity-class rule
  set, and its pre-registration.
* The `arch_training.md` §12.10 correction described in DD8.

**Out of scope**

* **Time units.** The single largest opportunity by raw count — 1,171
  occurrences, `night` alone appearing 433 times — and poison. `night`,
  `nights`, `overnight` and `midnight` are `NOCTURIA_LEXICON` *modifiers*, and
  `every hour`/`hourly` are urinary-frequency modifiers. `night → morning` on a
  nocturia line deletes the thing that makes it nocturia. See DD6: the existing
  layer-3 check rejects these mechanically, which is the reassurance rather than
  the permission.
* **Numbers.** `three` (×92), `four` (×38). §12.10 already records why: no
  lexicon holds a numeric term, so `38.4 → 37.6` passes every mechanical check
  while walking a `fever_true` line into saying the temperature was normal.
* **Laterality.** `left`/`right` (×70/×37). Decided out: it is clinical
  laterality and not worth the argument for 107 occurrences.
* **Cross-gender and cross-life-stage swaps.** DD4.
* **Child referents as a working class.** `daughter` and `son` are currently
  alone in their classes and generate nothing. Adding `boy`, `girl`, `little
  one`, `eldest`, `youngest` is a stage-2 question, not a v2 commitment.
* **Tier C** (aspect and opener rewrites), unchanged from v1.
* **v1's Task 7.** Superseded, as stated at the top.
* Editing `data/synthetic/*.txt`, the manifest, `manifest.py`, `recombine.py` or
  the generator. Unchanged from v1 DD1: this is post-processing over the JSONL.

---

## 5. Design decisions

### DD1 — Everything v1's DD1 established still holds

Expansion is post-processing over the generated tree: same filenames, same
`example_id`s, same labels, same provenance, only `text` differs. No cluster key
moves, no split moves, the golden digest holds, and every expanded example stays
paired with its clean original. Nothing in this plan reopens that.

### DD2 — Entity classes are signal-agnostic, and that is a new capability

v1's rules are scoped to a signal because the vocabulary they swap *belongs* to
that signal. `sister → brother` belongs to no signal — it appears in `tangents`,
in `justifiers`, and in all seven `*_null_thirdparty` libraries. Scoping it to
one signal would be arbitrary and would forfeit the roll-out argument in §3.

So the class file declares no signal, and `expand.py` needs to accept that. **The
lexicon safety check does not weaken as a result** — DD6's layer 3 already tests a
rule against *every* signal's lexicon for introduced matches, and a
signal-agnostic rule simply has no "own signal" to be exempt about.

### DD3 — A class is a list; the rules are generated, not written

The reviewable artefact is a word list of 6–10 members with one written
invariant for the class as a whole. The loader expands it to ordered pairs. This
is the entire cost argument: 38 words reviewed once produce 210 rules, against
v1's 36 rules reviewed 36 times producing 36.

The generated rules are still subject to every per-rule check in DD6, so
generation is a convenience for the author, not a hole in the validation.

### DD4 — Swaps stay inside gender and life stage, and this is not fastidiousness

**148 of the 387 referent lines — 38% — carry a gendered referent and a gendered
pronoun in the same sentence.**

> *"My **wife** has been poorly and I've been up seeing to **her**"*

`wife → husband` produces text no human wrote. The rule format is literal
find/replace with **no notion of agreement** and cannot repair the pronoun, so
cross-gender swaps are excluded by construction rather than by care.

The neutral class is exempt and is therefore the largest: *"My upstairs
**neighbour** comes in from **his** shift"* → `flatmate` is fine, because a
neutral noun never contradicts a pronoun. Neutral↔neutral is always safe;
neutral↔gendered is not.

Life stage is the same argument from a different direction. 38 lines put the
referent somewhere age-specific — *"**daughter** was sent home from school"* —
where `grandma` is grammatical and absurd. Absurd text is not a label error, but
it is not free either, and splitting the lists costs nothing.

**This restriction is what takes the payoff from +40.1% to +25.8%.** It is worth
paying: the unrestricted version breaks the grammar of well over a third of the
lines it touches.

### DD5 — v1's rules and the entity classes run together, and the cost is named

The v2 arm is the **combined** rule set. The trade-off, recorded so it is not
discovered later: running both means the result cannot be attributed to either
half. That is exactly DD9's argument for keeping expansion and the noise pass
apart, and it is being knowingly accepted here for two reasons — the v1 half is
already independently measured (2026-09-04), so the combined arm is read against
a known quantity rather than against nothing; and the alternative costs a third
arm and five more trainings to separate two things nobody intends to ship
separately.

**A stage-2 question, not a decision:** whether to add an entity-classes-only arm
anyway, at five trainings and ~10 minutes, to make the attribution explicit.

### DD6 — The safety layers are unchanged, and the most tempting mistake is already blocked

All three of v1's layers apply, with one clarification each:

1. **Declared invariant**, now per class rather than per rule. Six statements
   instead of 210. This is a genuine reduction in what a reviewer must read, and
   it is also a concentration of risk: one wrong class invariant is wrong 30
   times. Stage 2 should decide whether a class needs a stricter review than a
   rule did.
2. **Structural-token invariance.** Unchanged. Referent nouns are not in
   `STRUCTURAL_FROZEN`, so classes pass trivially — which is a reason to lean on
   layer 3 rather than a reason to relax.
3. **Signal-lexicon invariance.** This is the layer that matters here, and it is
   already sufficient for the worst case in scope. `night → morning` changes
   whether the phrase matches `NOCTURIA_LEXICON` and is **rejected when the rule
   file loads**, before a byte is written. The single most attractive extension
   to this plan is mechanically blocked by machinery that already exists.

Plus `--dry-run-lint` over the committed libraries, unchanged, with new-hit-is-a-
failure semantics. The specific hazard it exists for — a rule that is individually
harmless and manufactures a cross-signal hit in combination — is *more* likely
here than in v1, because classes touch filler and filler is where the
`playing up → aching` case came from.

**One honest limit on layer 3, found while writing this plan.** The lexicon check
protects *signal words*, not their *modifiers*: `high` (×118) and `raised` (×96)
are in no lexicon, and `a high temperature → a normal temperature` would pass
every mechanical check. Nothing in this plan proposes such a rule, and the class
mechanism cannot express one — but the limit should be written down rather than
discovered.

### DD7 — The decision metric is the paired flip rate, and it means more here

Unchanged machinery: `paired-flip-rate`, changed pairs only, cluster-level
resampling, and the pre-registered decisive-accuracy guard.

What changes is the interpretation. For an entity swap there is **no legitimate
reason for the answer to move**, so the flip rate is a direct measurement of
surface overfitting rather than a proxy for it. A pre-registered bound can
therefore be stated in absolute terms — flips on entity-only pairs should be at
or near zero for a model that is reading language rather than fragments — and a
non-zero rate in the clean-trained arm is itself the finding.

**Bounds are for stage 2**, and stage 2 must set them against the *observed*
1.89% baseline rather than against Task 2's real-text 15.4%. That mistake is
recorded in DD8 and is the single most reusable thing the v1 run produced.

### DD8 — The §12.10 correction ships with this plan

The 2026-09-04 write-ups contain a finding that does not survive scrutiny, and it
is currently in `arch_training.md` §12.10 as "the most useful thing this run
taught us". It is corrected in the same PR as this plan because the two are the
same argument.

**What was claimed:** the synthetic decisive-accuracy guard held while the
expanded arm's *real-text* decisive accuracy fell 11 points, therefore the guard
was measuring somewhere the failure it was designed for does not appear.

**Why it does not hold.** The noise 2×2 ran the same instrument over four arms
built by a different augmentation, and its real-text decisive figures are:

| trained on | decisive acc, clean test | real-text decisive |
|---|---|---|
| clean | 93.3% | 76.7% ± 17.3 |
| 3% typos | 93.5% | 76.7% ± 12.7 |
| 6% typos | 93.8% | 78.9% ± 9.9 |
| 12% typos | 94.3% | **64.4%** ± 19.9 |

`r12` dropped **12.3 points** on that slice — more than the expansion arm's 11.1
— and the noise 2×2 concluded that arm was beneficial and harmless. An 11-point
swing on 18 decisive cells with a ±23-point half-width is an ordinary draw, not a
detected harm.

**The corrected claim:** the real-text decisive slice cannot establish a harm of
this size in either direction. That is a limitation of the instrument, not a
finding about the guard, and it should never have been written up as one.

**What this changes about the ticket.** The only evidence for harm dissolves, and
the noise precedent — four measurements of surface augmentation on this exact
data, none harming clean performance, all nudging it up monotonically — becomes
the relevant prior. The risk/reward case for continuing is better than the
2026-09-04 write-up concluded.

**What does not change.** The pass can still harm if misconfigured: the rule
authoring report measured it *inverting* the vocabulary bias at p = 1 and opening
a 0.218 true/false gap in `declarative_v1` where the library had 0.014. "Unlikely
to harm" holds **at a sane rate with the lint passing**, and those conditions are
load-bearing.

### DD9 — Expansion and the noise pass still do not run together

Unchanged from v1. If they are ever combined the order is expand then noise.

---

## 6. Tasks (provisional shape, for the stage-2 pass to expand)

**Task 1 — The class file format and the loader.** A class is a list plus one
declared invariant; the loader expands it to ordered pairs and runs every
existing per-rule check over each. Signal-agnostic rule files (DD2). The bulk of
the work is validation, not generation.

**Task 2 — Author the six classes**, with their invariants, and run
`--dry-run-lint` over the committed libraries for all seven signals rather than
fever alone. This is where the DD6 cross-signal hazard would surface.

**Task 3 — The §12.10 correction** (DD8), across `arch_training.md` and the two
2026-09-04 reports. No code. Ships in the same PR as this plan; listed as a task
so it is not forgotten if the plan is split.

**Task 4 — Pre-register**, with bounds set against the observed 1.89% baseline
and an explicit statement of what an entity-swap flip means (DD7).

**Task 5 — Run the 2×2** with the combined rule set and read it out. Twenty
trainings, ~40 minutes, machinery unchanged. One free correctness check falls
out: the clean-trained/clean-test cell must reproduce **0.9329** decisive exactly,
since generation is deterministic and that cell is untouched by this plan. If it
does not, something in the pipeline moved and the run is void before anything is
interpreted.

**Task 6 — Report**, against the pre-registration, item by item, including the
items that fail.

Tasks 1 and 3 are signal-agnostic machinery. Task 2 is the authoring cost, and
unlike v1 it does **not** repeat per signal.

---

## 7. Open questions for the review pass

1. **Do the classes need a stricter review than a rule did?** DD6 layer 1 goes
   from 36 statements to 6, and one wrong class invariant is wrong 30 times.
   Cheaper to read, more concentrated to get wrong.
2. **Should there be an entity-classes-only arm?** DD5 accepts unattributability
   to save five trainings. Ten minutes of GPU buys it back.
3. **What bound?** DD7 says absolute rather than relative, and stage 2 must
   choose the number. The v1 mistake — a bound anchored on an instrument other
   than the one being measured — is the thing to avoid.
4. **Are the child classes worth completing?** `daughter` and `son` currently
   generate nothing. Adding four or five words makes two more classes work.
5. **Is 387 lines enough to move a model at all?** They are 11% of the fragment
   inventory. The +25.8% n-gram figure says the *surface* moves; nothing yet says
   a model notices, and this question is exactly what Task 5 exists to answer —
   and is allowed to answer negatively.
6. **Does the rate need re-tuning?** 0.4 at clean share 0.25 was chosen from
   fever's library statistics. The entity classes have a different site density
   and nobody has looked at what the combined set does at that rate.
