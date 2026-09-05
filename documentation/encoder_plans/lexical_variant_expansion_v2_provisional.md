# Provisional plan: lexical variant expansion v2 — swap classes (12.10b)

**Status: provisional, revision 2 (2026-09-05).** Stage 1 of the workflow. The
design decisions are made and argued; the task list is a shape rather than an
instruction set; the open questions at the end are for the stage-2 review pass to
close.

**What revision 2 changes.** Revision 1 was written on the belief that entity
classes need no new safety machinery — six word lists and a loader. That is
wrong, and §2 is the correction: **the referent nouns the plan is built on are
already in `noise.STRUCTURAL_FROZEN`, and DD6 layer 2 rejects most of the plan's
own rules at load time.** Fixing that is now the substantive engineering of the
ticket. Revision 2 also widens the mechanism from entity classes to *swap
classes* — colloquial referents, healthcare-setting nouns and an affect class
join the six original lists — and folds in the batching constraint now written
up as `arch_training.md` §13, which changes two of revision 1's answers.

Read first: `arch_training.md` §8 (the lint's two blind faults), §10 (effective
sample size), §12.6 (the noise pass), §12.10 (this pass as built and measured),
§13 (how experiments are batched); then
`reports/encoder_training/2026-09-04-lexical-variant.md` and its
pre-registration, which are what this plan exists because of.

**The v1 plan of record is `lexical_variant_expansion_implementation.md`. Its
Task 7 — extending the fever rules to the other six signals — is deliberately
left unfinished and is superseded by this plan.** Not because it failed, but
because the fever rule set moves the surface vocabulary by a measured 10.8%, and
rolling it across six more signals would have cost roughly 200 more hand-written
invariants for a proportionate share of that. This plan is the cheaper and larger
version of the same idea.

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
| does a flip mean an error? | arguably — the words differ in register | **unambiguously yes, for the referent classes** |

That last row is why this is a *better* experiment than the one just run, and it
is worth stating plainly. There is no defensible reason for a model's answer to
change when `sister` becomes `brother`. Any flip is the model reading noise. With
`fever → temperature` a reader could always argue the two words carry different
register, which made the flip rate a softer instrument than it looked.

**The qualifier on that row is new in revision 2 and is load-bearing.** It holds
for the referent, weekday and healthcare classes, whose members are
interchangeable *by construction*. It does **not** hold for the affect class
(`worried → concerned`), which is a register swap of exactly v1's kind. That is
why DD10 gives affect its own arm and its own flip accounting rather than letting
it dilute the clean instrument.

**One thing this plan does not claim.** It adds no ideas and no effective sample
size, exactly as v1 did not. The expanded tree holds the same examples built from
the same 417 clusters. No report from this work may quote an example count as
growth.

---

## 2. The correction that reshapes this plan: layer 2 already refuses these rules

Revision 1's DD6 said:

> Structural-token invariance. Unchanged. Referent nouns are not in
> `STRUCTURAL_FROZEN`, so classes pass trivially.

**That is false.** `noise.STRUCTURAL_FROZEN` carries a block commented "Person:
whose symptom this is, which is the third-party null axis", and it contains
`mum`, `mother`, `wife`, `husband`, `dad`, `father`, `partner`, `nan`, `gran`,
`son` and `daughter` — **11 of the 38 words revision 1 proposed**.
`expand._check_structural` compares the *sequence* of frozen tokens in `find`
against the sequence in `replace` and raises on any difference, so every pair
touching a frozen word is refused when the file loads. That includes
`mum → mother`, where both sides are frozen but the sequences differ.

Measured against the **revision 2** lists of §3, which is the set this plan
actually proposes (revision 1's narrower six-list table is dropped: it made DD6a
look like a rule-count argument, and it is not one — review F2):

| class | ordered pairs | survive layer 2 today | occurrences | on a frozen member |
|---|---|---|---|---|
| adult female (9) | 72 | 30 | 150 | 107 |
| adult male (7) | 42 | 12 | 100 | 68 |
| elder female (7) | 42 | 20 | 20 | 17 |
| elder male (5) | 20 | 20 | 5 | 0 |
| adult neutral (12) | 132 | 110 | 151 | 51 |
| child neutral sg (5) | 20 | 20 | 27 | 0 |
| child neutral pl (2) | 2 | 2 | 31 | 0 |
| child female (2) | 2 | **0** | 49 | 46 |
| child male (2) | 2 | **0** | 40 | 35 |
| weekday (7) | 42 | 42 | 68 | 0 |
| healthcare place / person / encounter | 24 | 24 | 97 | 0 |
| affect (6) | 30 | 30 | 71 | 0 |
| **total** | **430** | **310** | **809** | **324** |

*Provenance: the occurrence and frozen-member columns are output of `python -m
scripts.synthetic_data.class_stats` (run 2026-09-05, 49 files, 2,506 non-blank
non-comment lines). The layer-2 column is `expand.structural_sequence` over
every ordered pair, per the review's §6. No number in this section is carried
forward from prose (DD15).*

**So 72% of the v2 rule set already loads today, and the case for DD6a is an
occurrence case rather than a rule-count one.** Widening the lists with
colloquial members — which are not frozen — quietly solved most of the
rule-count problem §2 opens by describing. What it did not solve:

* **324 of the 573 referent occurrences — 57% — sit on a frozen member**, because
  the frozen words are the frequent ones: `mum` 59, `partner` 51, `daughter` 46,
  `son` 35, `wife` 34, `husband` 33.
* **Both gendered child sub-classes yield zero loadable rules today.**
  `daughter` and `son` are frozen and `girl` and `boy` are not, and those two
  lists carry 89 occurrences between them — the third and fourth most frequent
  referents in the corpus.

**Consequences for the plan.**

* The `+25.8%` reachable-4-gram headline in revision 1 was computed without
  applying layer 2 and is not achievable as designed. Revision 2 quotes no
  n-gram figure; re-measuring it is Task 2, and it is a CPU measurement that runs
  before any GPU night (§13).
* The ticket is not "six word lists and a loader". It owns a change to a
  mechanical safety layer, which is the one thing revision 1 promised it would
  not do. DD6a is that change and it needs its own tests.
* The claim in revision 1's DD2 that "the lexicon safety check does not weaken as
  a result" survives; it is layer 2, not layer 3, that has to move.

---

## 3. What a swap class is, and what the classes cost

A class is one hand-written list of interchangeable members plus one declared
invariant for the list as a whole. Every ordered pair within a class becomes a
rule, so an *N*-member list yields *N*×(*N*−1) rules from one review. That is the
entire cost argument, and it is why adding colloquial members is close to free:
taking a 6-member list to 9 members takes it from 30 rules to 72.

The proposed classes, measured over the committed hand-written libraries
(`data/synthetic/**/*.txt`, 49 files, 2,506 non-blank non-comment lines). The
splits are the ones DD11 forces: the child group four ways by gender and number,
healthcare three ways, so the count is **fourteen lists**, not the thirteen
earlier drafts said:

| group | class | members | occ | pairs | absent |
|---|---|---|---|---|---|
| referent | adult female | mum, mummy, mother, wife, missus, sister, aunt, auntie, girlfriend | 150 | 72 | missus |
| referent | adult male | dad, daddy, father, husband, brother, uncle, boyfriend | 100 | 42 | daddy |
| referent | elder female | nan, nanna, nana, gran, granny, grandma, grandmother | 20 | 42 | nanna, nana, granny |
| referent | elder male | grandad, granddad, grandpa, grandfather, gramps | 5 | 20 | granddad, grandpa, grandfather, gramps |
| referent | adult neutral | partner, other half, friend, neighbour, colleague, coworker, cousin, flatmate, housemate, mate, boss, carer | 151 | 132 | coworker |
| referent | child neutral sg | kid, child, little one, youngest, eldest | 27 | 20 | — |
| referent | child neutral pl | kids, children | 31 | 2 | — |
| referent | child female | daughter, girl | 49 | 2 | — |
| referent | child male | son, boy | 40 | 2 | — |
| calendar | weekday | monday … sunday | 68 | 42 | — |
| setting | healthcare place | surgery, practice, clinic | 25 | 6 | — |
| setting | healthcare person | gp, doctor, nurse, clinician | 49 | 12 | clinician |
| setting | healthcare encounter | appointment, consultation, call-back | 23 | 6 | call-back |
| affect | worry (DD10: separate arm) | worried, concerned, anxious, nervous, uneasy, on edge | 71 | 30 | uneasy, on edge |
| | **total** | **74 words in 14 lists** | **809** | **430** | **12** |

*Provenance: `python -m scripts.synthetic_data.class_stats`, run 2026-09-05.
Every figure in this section is that command's output; none is carried forward
from prose (DD15). Re-run it after any edit to `data/synthetic/**/*.txt` and
replace this table with the new output rather than patching a cell.*

Against v1's 36 rules from 36 individual reviews. **527 of the 2,506 library
lines — 21% — carry at least one referent**, and they are spread across every
signal, which is the roll-out argument: one list set covers all seven signals
where v1's fever rules would have needed authoring seven times. **40 lines carry
more than one referent occurrence**, which is the population DD12's memo and its
per-class injectivity exist for.

Three rows moved enough to change an authoring decision, and all three are
corrections to this document rather than to the libraries:

* **Referent opportunity is ~25% larger than earlier drafts claimed** (573
  occurrences against 452), which strengthens the case for the referent classes.
* **Healthcare is ~20% smaller** (97 against ~118), and `surgery` and `practice`
  are separately unsafe as bare nouns — see DD11 and the scope note on the place
  class.
* **Twelve of the 74 members never occur** and can never be a `find`. That is the
  mechanism working, not a fault: they exist to widen the *target* vocabulary,
  which is what DD14 says the "every rule fires somewhere" guard has to become.

**Colloquial members are kept British.** `grammy` is American and the only
real-text instrument this project has is 67 NHS submissions; `nan`, `nanna`,
`granny`, `gran`, `grandad`, `grandpa`, `the missus` and `my other half` are the
register actually at issue. `nanny` is excluded — it is also a childcare worker,
and a whole-word swap cannot tell the two apart.

**`my other half` joins the neutral class**, not a gendered one, which is where
the rule count is already largest and where DD4's pronoun problem does not apply.

**Multi-word members are allowed and introduce two failure modes the format does
not check** (DD11): number, because whole-word matching makes `colleague` and
`colleagues` different words and a class mixing them produces "my kids has been";
and determiner agreement, because the format has no notion of it. Both are
handled by declaring `number` on a class alongside gender and life stage, and by
splitting the child group into four sub-classes rather than one.

**`surgery` is the class system's best cautionary example** and its invariant
must name it: `surgery → practice` is right in "the surgery is closed" and wrong
in "I had surgery last year", and no mechanical layer sees the difference.

---

## 4. Scope

**In scope**

* Swap-class files at `data/expansion/classes/<class>.json`, expanded into
  ordered-pair rules by the loader (DD3). `data/expansion/` is already inside
  `OFFLINE_DATA_DIRS`, which prunes the whole subtree, so no registry change is
  needed.
* **The DD6a change to `expand._check_structural`**: person-class equivalence in
  place of literal-token equality, with tests pinning both what is newly allowed
  and what is still refused.
* Whatever change `expand.py` needs to accept a class file alongside a rule file,
  and to run rules that are **signal-agnostic** rather than scoped to one signal
  (DD2). `parse_rules` currently requires `signal` to be a member of
  `SIGNAL_LEXICONS`.
* Per-example substitution memoisation (DD12).
* Re-measuring the reachable-n-gram ceiling after DD6a, since revision 1's figure
  is void (Task 2).
* A CI step that loads every rule and class file and runs `--dry-run-lint`
  (DD13). Nothing in `.github/workflows/` or the `Makefile` currently touches
  `expand.py`.
* Re-running the 2×2 with the combined rule set, plus the two extra arms §13
  makes affordable (DD5, DD10), and its pre-registration.

**Out of scope**

* **Time units.** The single largest opportunity by raw count and poison.
  `night`, `nights`, `overnight` and `midnight` are `NOCTURIA_LEXICON`
  *modifiers*, and `every hour`/`hourly` are urinary-frequency modifiers.
  `night → morning` on a nocturia line deletes the thing that makes it nocturia.
  DD6 layer 3 rejects these mechanically, which is the reassurance rather than
  the permission.
* **Numbers.** No lexicon holds a numeric term, so `38.4 → 37.6` passes every
  mechanical check while walking a `fever_true` line into saying the temperature
  was normal.
* **Laterality.** `left`/`right`. Clinical laterality, not worth the argument.
* **Reporting verbs** (`said` 55, `says` 36, `mentioned` 17, `told` 15).
  Considered and deferred, and the reason is instructive: tense is a null axis,
  so `said ↔ says` is forbidden and the class must be tense-matched; and `told`
  takes an object, so "she said she'd been up" → "she told she'd been up" is
  broken English that no layer catches. The literal format cannot express
  subcategorisation frames, which is the same limit that puts Tier C out of
  scope.
* **Cross-gender and cross-life-stage swaps.** DD4.
* **Certainty and hedge adjectives.** Unchanged from §12.10 — and DD10 explains
  why the affect class is *not* a back door to them.
* **Tier C** (aspect and opener rewrites), unchanged from v1.
* **v1's Task 7.** Superseded.
* Editing `data/synthetic/*.txt`, the manifest, `manifest.py`, `recombine.py` or
  the generator. Unchanged from v1 DD1: this is post-processing over the JSONL.

---

## 5. Design decisions

### DD1 — Everything v1's DD1 established still holds

Expansion is post-processing over the generated tree: same filenames, same
`example_id`s, same labels, same provenance, only `text` differs. No cluster key
moves, no split moves, the golden digest holds, and every expanded example stays
paired with its clean original. Nothing in this plan reopens that.

### DD2 — Swap classes are signal-agnostic, and that is a new capability

v1's rules are scoped to a signal because the vocabulary they swap *belongs* to
that signal. `sister → brother` belongs to no signal — it appears in `tangents`,
in `justifiers`, and in all seven `*_null_thirdparty` libraries. Scoping it to
one signal would be arbitrary and would forfeit the roll-out argument in §3.

So a class file declares no signal, and `parse_rules` must stop requiring one.
**The lexicon check gets stronger rather than weaker as a result.** For a
signal-scoped rule, layer 3 asks that the phrase's *own* signal reading is
unchanged and that no *other* signal's language is introduced. A class rule has
no own signal, so the check becomes: for **every** signal *s*,
`lexicon_matches(find, s)` must equal `lexicon_matches(replace, s)` — neither
introduced nor removed. That is strictly stronger than the scoped form, and it is
what makes `night → morning` impossible to author as a class even by accident.

### DD3 — A class is a list; the rules are generated, not written

The reviewable artefact is a list of 5–12 members with one written invariant for
the class as a whole, plus its declared gender, life stage and number. The loader
expands it to ordered pairs. 66 words reviewed once produce ~434 rules, against
v1's 36 rules reviewed 36 times producing 36.

The generated rules are still subject to every per-rule check in DD6, so
generation is a convenience for the author, not a hole in the validation.

### DD4 — Swaps stay inside gender, life stage and number

**148 of the referent lines carry a gendered referent and a gendered pronoun in
the same sentence.**

> *"My **wife** has been poorly and I've been up seeing to **her**"*

`wife → husband` produces text no human wrote. The rule format is literal
find/replace with **no notion of agreement** and cannot repair the pronoun, so
cross-gender swaps are excluded by construction rather than by care.

The neutral class is exempt and is therefore the largest: *"My upstairs
**neighbour** comes in from **his** shift"* → `flatmate` is fine, because a
neutral noun never contradicts a pronoun. Neutral↔neutral is always safe;
neutral↔gendered is not.

Life stage is the same argument from a different direction: *"**daughter** was
sent home from school"* → `grandma` is grammatical and absurd. Absurd text is not
a label error, but it is not free, and splitting the lists costs nothing.

Number is new in revision 2 and is mechanical rather than semantic: whole-word
matching means `kid` and `kids` are unrelated strings, so a class mixing them
would produce "my kids has been". Declared `number` on the class, and the child
group split four ways.

### DD5 — The arms, and what §13 changes about them

Revision 1 ran a single combined arm and accepted that the result could not be
attributed to either half, on the argument that separating them "costs a third
arm and five more trainings". **§13 voids that argument.** At roughly two minutes
per fold, a night holds about 240 fold-trainings — twelve times the whole 2×2.
Five trainings is not a cost worth trading a permanent attribution gap for.

So the arms are:

| arm | rule set |
|---|---|
| clean | none (baseline) |
| v1 | fever rules only (already measured 2026-09-04, re-run as the anchor) |
| classes | referent + weekday + healthcare classes only |
| combined | v1 rules + those classes |
| affect | the affect class only (DD10) |

Every arm is scored against clean and expanded test trees where the 2×2 shape
applies. The read-out for every arm is pre-registered before the night; the
**decision arm is `combined`**, and the others are explicitly exploratory. That
last sentence is the discipline §13 says has to replace gating, and it matters
more here than in any previous run: five arms picked over post hoc will produce a
winner by noise.

### DD6 — The three safety layers, with layer 2 rewritten

1. **Declared invariant**, now per class rather than per rule. Thirteen
   statements instead of 434. This is a genuine reduction in what a reviewer must
   read, and it is also a concentration of risk: one wrong class invariant is
   wrong dozens of times. The class file therefore carries more declared
   structure than a rule did — gender, life stage, number, and the invariant —
   so that a reviewer is checking a small number of stated properties rather than
   re-reading prose.
2. **Structural-token invariance.** Rewritten — see DD6a.
3. **Signal-lexicon invariance.** Strengthened for class rules — see DD2.

Plus `--dry-run-lint` over the committed libraries for all seven signals, with
new-hit-is-a-failure semantics. The specific hazard it exists for — a rule that is
individually harmless and manufactures a cross-signal hit in combination — is
*more* likely here than in v1, because classes touch filler and filler is where
the `playing up → aching` case came from.

**One honest limit on layer 3, carried over from revision 1.** The lexicon check
protects *signal words*, not their *modifiers*: `high` and `raised` are in no
lexicon, and `a high temperature → a normal temperature` would pass every
mechanical check. Nothing in this plan proposes such a rule and the class
mechanism cannot express one, but the limit is written down rather than
discovered.

### DD6a — Layer 2 compares person *class*, not person *token* — NEW

`STRUCTURAL_FROZEN` freezes referent nouns for the noise pass's reasons: a
character-level edit turning `wife` into `life` destroys who has the symptom, and
the third-party null axis is exactly what the frozen block's comment names. Those
reasons do not transfer to a whole-word swap between two third-party referents.
`mum → sister` leaves the person axis precisely where it was; `mum → I` does not.

So layer 2, **for expansion only**, normalises person tokens to their class
before comparing sequences:

* `i`, `im`, `i'm`, `ive`, `i've`, `my`, `me` → `<first-person>`
* every third-party referent noun → `<third-party>`
* every other frozen token → itself

`mum → sister` then compares `('<third-party>',)` against `('<third-party>',)` and
passes. `mum → I` compares `('<third-party>',)` against `('<first-person>',)` and
is refused, with the same message quality the existing layer has.

Four constraints on how this is built, because it is the only place v2 weakens a
mechanical layer:

* **`STRUCTURAL_FROZEN` is not edited.** The noise pass keeps the literal freeze
  it needs. The person-class map is a new shared constant, imported by `expand.py`
  the way `STRUCTURAL_FROZEN` already is — "two lists in two modules drifting
  apart is the outcome that import exists to prevent".
* **The map is authored, not inferred.** A referent that is not in the map is not
  a person as far as layer 2 is concerned, so adding a class member without
  adding it to the map fails closed rather than open. A test asserts every class
  member appears in the map.
* **Pronouns stay literal.** `he`/`she`/`her`/`his`/`they` are *not* collapsed:
  DD4 forbids cross-gender swaps precisely because the pronoun cannot be
  repaired, and collapsing pronouns to a class would make that violation
  invisible to layer 2.
* **The tests pin both directions.** What is newly allowed (`mum → sister`,
  `partner → flatmate`, `son → boy`) and what is still refused (`mum → I`,
  `my wife → I`, `sister → my sister`, and every tense, negation and modality
  case the existing tests already cover).

### DD7 — The decision metric is the paired flip rate, and it means more here

Unchanged machinery: `paired-flip-rate`, changed pairs only, cluster-level
resampling, and the pre-registered decisive-accuracy guard.

What changes is the interpretation. For a referent swap there is **no legitimate
reason for the answer to move**, so the flip rate is a direct measurement of
surface overfitting rather than a proxy for it. A pre-registered bound can
therefore be stated in absolute terms — flips on referent-only pairs should be at
or near zero for a model reading language rather than fragments — and a non-zero
rate in the clean-trained arm is itself the finding.

**Bounds are for stage 2**, and stage 2 must set them against the *observed*
1.89% baseline rather than against Task 2's real-text 15.4%. That mistake is
recorded in DD8 and is the single most reusable thing the v1 run produced.

### DD8 — The §12.10 correction

The correction is **already applied** to `arch_training.md` §12.10 and to
`reports/encoder_training/2026-09-04-lexical-variant.md` (both dated 2026-09-05).
Stage 2 should verify only that
`2026-09-04-lexical-variant-plain-english.md` carries it too, and then drop this
DD to a citation.

The substance, retained because the rest of the plan leans on it: the claim that
the synthetic guard held while real-text decisive accuracy fell 11 points, and
that the guard was therefore measuring in the wrong place, does not survive being
set beside 12.6, where the `r12` arm fell **12.3 points** on the same slice and
was concluded beneficial and harmless. Eighteen decisive cells with a ±23-point
half-width cannot separate an 11-point difference from nothing. The corrected
claim is about the instrument, not the guard. **What this changes about the
ticket:** the only evidence for harm dissolves, and the noise precedent — four
measurements of surface augmentation on this exact data, none harming clean
performance — becomes the relevant prior.

**What does not change.** The pass can still harm if misconfigured: the rule
authoring report measured it *inverting* the vocabulary bias at p = 1 and opening
a 0.218 true/false gap in `declarative_v1` where the library had 0.014. "Unlikely
to harm" holds **at a sane rate with the lint passing**, and those conditions are
load-bearing.

### DD9 — Expansion and the noise pass still do not run together

Unchanged from v1. If they are ever combined the order is expand then noise.

### DD10 — The affect class is authored, but separately, and it is not the same kind of thing — NEW

The idea is sound and cheap: `worried` (40), `concerned` (17), `anxious` (11) and
their neighbours are 71–106 occurrences of vocabulary that carries no signal, and
once the class machinery exists an affect list costs one review. But three things
separate it from the referent classes and the plan must not blur them.

* **Neither mechanical layer protects it.** No affect word appears in any of the
  seven signal lexicons (checked), and none is in `STRUCTURAL_FROZEN`. Layers 2
  and 3 both pass trivially, so the *entire* safety argument is the declared
  invariant. That is exactly the shape §12.10 ruled out of scope for certainty
  adjectives.
* **Affect words already do label work in the committed libraries.** Two lines,
  found while writing this plan:

  > `nocturia_null_attribution.txt:16` — "I wake up **anxious** around three most
  > nights and end up wandering to the bathroom"
  >
  > `urinary_frequency_null_hedged.txt:13` — "I've been **anxious** about all
  > this so I may be reading too much into my toilet trips"

  In both, the affect word *is* the attribution or the hedge — the axes a class
  must not touch. `anxious → fed up` breaks the first. Referents are
  interchangeable by construction; affect words are not, and the class invariant
  has to be written against the `*_null_attribution` and `*_null_hedged`
  libraries specifically rather than against `emotional.txt`.
* **It costs v2 its best property.** §1's table claims a flip is *unambiguously*
  an error. `worried → apprehensive` is a register change and a reader can argue
  register, which is the softness that made v1's instrument weaker than it
  looked. Folding affect into the combined arm contaminates the one clean
  measurement this plan has.

**The decision: author it as its own class group, run it as its own arm, and
report its flip rate separately from the referent classes'.** The class is
restricted to intensity- and valence-matched members (`worried`, `concerned`,
`anxious`, `nervous`, `uneasy`, `on edge`) and explicitly excludes
`fed up`, `embarrassed`, `annoyed`, `panicking`, `terrified` and anything else
that moves intensity. **This is the plan author's call and the one decision in
revision 2 the user did not make; it is cheap to overturn in stage 2, and
overturning it means folding affect into `combined` and accepting that the flip
rate no longer means what §1 says it means.**

**One forward-looking note, because reusability is the stated motive for this
whole ticket.** If a mental-health signal is ever written, `anxious` enters a
lexicon and `worried → anxious` starts failing layer 3 at load time. That is the
machinery working — but only if the class files are loaded somewhere automatic,
which is DD13.

### DD11 — Multi-word and colloquial members, and what the format cannot check — NEW

`_check_matchable` requires `find` to begin and end on a word character, which
multi-word members satisfy. What the format does not check is agreement:

* **Number.** `colleague` and `colleagues` are unrelated strings under whole-word
  matching. Declared `number` per class; the child group splits four ways.
* **Determiners.** `colleague → buddy at work` is right after "my" and "a" and
  the format has no way to know. The invariant must state the frames the class is
  authored for, and `--dry-run-lint` output must be read as text rather than only
  as a pass/fail — a rule that produces broken English produces no new lexicon
  hit and will pass.
* **Ambiguity.** `surgery` (§3) is the standing example, and the general rule is
  that a member with a second common sense needs the invariant to name it.

### DD12 — Referent substitution is memoised per example — NEW

Rules fire per match site independently. An example is a recombination of several
fragments, so a referent can appear more than once in one example — and two
independent draws turn *"my wife has been up in the night … my wife is worried"*
into two different people. This is a coherence failure the fever rules could not
produce, because alternating `fever` and `temperature` in one example is
harmless.

Within the committed libraries a single *line* rarely repeats a referent (29 of
470 referent-bearing lines carry two, and one repeats the same word), but the
recombination is where the exposure is and it has not been measured.

**The decision: the expander memoises per example.** Once a class fires on a
given source word within one example, every later occurrence of that same source
word in that example takes the same target. Cheap to implement, removes the whole
failure mode, and the memo is keyed on `(example_id, folded find)` so it cannot
leak between examples. Stage 2 should measure how often the memo actually fires,
because that number is also the size of the bug it prevents.

### DD13 — Rule and class files are loaded in CI — NEW

Nothing in `.github/workflows/` or the `Makefile` currently runs `expand.py`, so
a rule file can be committed broken, or rot silently as the lexicons grow (DD10).
A CI step that loads every file in `data/expansion/` and runs `--dry-run-lint`
costs a couple of seconds, needs no GPU and no ML wheels, and is what makes the
"layer 3 will reject it when the lexicon arrives" reassurance true rather than
theoretical. It also belongs to the class of checks §13 says must run *before* a
GPU night rather than inside one.

---

## 6. Tasks (provisional shape, for the stage-2 pass to expand)

**Task 1 — Layer 2's person-class comparison (DD6a).** The shared person-class
map, the change to `_check_structural`, and the tests pinning both what is newly
allowed and what is still refused. `STRUCTURAL_FROZEN` untouched. This is the
prerequisite for every other task and the only task that changes a safety layer.

**Task 2 — The class file format and the loader.** A class is a list plus
declared gender, life stage, number and one invariant; the loader expands it to
ordered pairs and runs every per-rule check over each. Signal-agnostic rule files
(DD2), per-example memoisation (DD12). Re-measure the reachable-n-gram ceiling
now that layer 2 admits the frozen referents, since revision 1's `+25.8%` is
void. CPU only.

**Task 3 — Author the classes** (§3), with their invariants, and run
`--dry-run-lint` over the committed libraries for all seven signals rather than
fever alone. The affect class is authored here but kept in its own group (DD10).
This is where the DD6 cross-signal hazard and the DD11 agreement hazards surface,
and the dry-run output is read as text, not only as an exit code.

**Task 4 — CI loads the rule and class files (DD13).** No GPU, no ML wheels.

**Task 5 — Pre-register**, with bounds set against the observed 1.89% baseline,
an explicit statement of what a referent-swap flip means (DD7), the five arms of
DD5, and which one is the decision arm. Every arm's read-out is written down
before the night (§13).

**Task 6 — Run the batch and read it out.** Five arms; the 2×2 shape where it
applies. The batch opens with the canary and the reproduce check: the
clean-trained/clean-test cell must return **0.9329** decisive exactly, since
generation is deterministic and that cell is untouched by this plan. If it does
not, something in the pipeline moved and the night is void before anything is
interpreted — which is the whole point of putting it first rather than last
(§13).

**Task 7 — Report**, against the pre-registration, item by item, including the
items that fail, and with referent-class and affect-class flip rates reported
separately.

Tasks 1, 2 and 4 are signal-agnostic machinery. Task 3 is the authoring cost, and
unlike v1 it does **not** repeat per signal.

---

## 7. Open questions for the review pass

1. **Is DD6a's person-class map the right shape, or should it be a per-class
   declaration instead?** A shared map is one place to get wrong; a per-class
   `person: third-party` field puts the declaration next to the words it
   describes but lets two classes disagree. Stage 2 picks one.
2. **How strict a review does a class invariant need?** Layer 1 goes from 434
   statements to 13. Cheaper to read, more concentrated to get wrong. The
   declared gender/life-stage/number fields are a partial answer; stage 2 should
   decide whether that is enough.
3. **What bound?** DD7 says absolute rather than relative, and stage 2 must
   choose the number, separately for the referent classes and for affect. The v1
   mistake — a bound anchored on an instrument other than the one being measured
   — is the thing to avoid.
4. **Does affect stay a separate arm?** DD10 is the plan author's call, not the
   user's.
5. **Is ~700 referent, weekday, setting and affect occurrences enough to move a
   model at all?** They sit on 19% of the fragment inventory. Nothing yet says a
   model notices, and Task 6 is allowed to answer negatively.
6. **Does the rate need re-tuning, and should it be swept as arms?** 0.4 at clean
   share 0.25 was chosen from fever's library statistics; the classes have a
   different site density. §13 makes a three- or four-rate sweep affordable in
   one night, which is a better answer than picking one operating point from
   library statistics and hoping. The cost is more arms to pre-register.
7. **Should the reporting-verb class be reconsidered** once someone has looked at
   whether a tense- and frame-matched subset (`said`, `mentioned`, `remarked`)
   is worth ~120 occurrences? Scoped out in §4 on the subcategorisation argument,
   which stage 2 may judge too cautious.
