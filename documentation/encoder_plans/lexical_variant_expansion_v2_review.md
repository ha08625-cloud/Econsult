# Review of the v2 provisional plan — lexical variant expansion, swap classes (12.10b)

**Stage 2, review pass. 2026-09-05.** Reviews
`lexical_variant_expansion_v2_provisional.md` revision 2 against the code and the
committed libraries. Every number below was measured rather than repeated; the
commands are in §6 so the next pass can re-run them.

**Verdict: the design is sound and DD6a is the right correction. Ship it, with
ten changes.** Two of them are safety changes that must land before any class is
authored (findings 3 and 5); two invalidate a stated cost (findings 1 and 8); one
is a bug in a decision that reads as already solved (finding 7).

---

## 1. What checks out

Verified directly, no change needed:

* **`STRUCTURAL_FROZEN` does freeze the referent nouns.** The "Person" block
  carries `son`, `daughter`, `wife`, `husband`, `mum`, `mother`, `dad`,
  `father`, `partner`, `nan`, `gran` — 11 words, exactly as §2 says.
  `expand._check_structural` compares `structural_sequence(find)` against
  `structural_sequence(replace)` and raises on any difference, so a pair
  touching one of them is refused at load. §2's central claim is correct and it
  is the reason revision 2 exists.
* **57% of referent occurrences sit on a frozen member** (324 of 573 over the
  2,506 hand-written library lines). §2 says 55–61%. The share is right even
  though the underlying counts are not (finding 1), and it is the number that
  justifies DD6a.
* **`data/expansion/` is already inside `OFFLINE_DATA_DIRS`**
  (`app/core/condition_registry.py:39`, `frozenset({"synthetic", "expansion"})`),
  so §4 is right that no registry change is needed.
* **Nothing in `.github/workflows/` or the `Makefile` runs `expand.py`.** DD13's
  premise holds.
* **`parse_rules` does require `signal in SIGNAL_LEXICONS`**
  (`expand.py:~390`), so DD2's change is real work.
* **DD10's two cited lines are exact**, verbatim, at the line numbers given.
  There is a third worth adding: `fever_true.txt:19` — *"I assumed I was just
  **anxious** about the interview which is why I felt so hot but when I checked I
  had a temperature"* — where the affect word carries a misattribution that the
  line then corrects. It strengthens the DD10 argument rather than weakening it.
* **`rewrite_exhaustively` does not loop**, despite the name: it walks
  `match_sites` once and rewrites each site once. A class containing both
  `mum → sister` and `sister → mum` cannot oscillate. Worth stating because it
  is the first thing a reader worries about with generated bidirectional pairs.
* **`_check_matchable` accepts multi-word members.** `other half`,
  `little one` and `call-back` all begin and end on a word character.
* **`--determinism strict` is the training default**
  (`scripts/encoder_training/train.py:230`), so Task 6's canary is *reproducible
  in principle* — see finding 10 for the condition the plan omits.

---

## 2. Findings that change the plan

### F1 — The library statistics do not reproduce, and every one is an undercount

Measured over `data/synthetic/**/*.txt`, non-blank non-comment lines — the same
denominator the plan names, and the line count agrees exactly at **2,506**:

| plan claim | plan | measured |
|---|---|---|
| adult female occurrences | 114 | **150** |
| adult male | 78 | **100** |
| elder female | 18 | **20** |
| elder male | 3 | **5** |
| adult neutral | 113 | **151** |
| child (all four sub-classes) | 126 | **147** |
| weekday | 68 | **68** ✓ |
| healthcare | ~118 | **97** |
| affect | 71 | **71** ✓ |
| lines carrying ≥1 referent (§3) | 470 / 19% | **527 / 21%** |
| lines with >1 referent occurrence (DD12) | 29 | **40** |
| gendered referent + gendered pronoun (DD4) | 148 | **191** |
| `mum` / `partner` / `daughter` / `wife` / `husband` / `son` (§2) | 42 / 41 / 33 / 27 / 25 / 25 | **59 / 51 / 46 / 34 / 33 / 35** |

Excluding the `filler` directories gets `mum` to 41 and `partner` to 38, so the
plan may have been measured over a narrower file set than the one it names — but
that reconstruction does not fit the other rows either, and §3's "indicative"
member lists cannot explain a gap in the referent-bearing *line* count, which is
list-shape-insensitive.

**Two of the three deviations point the same way and none of them is fatal.**
Referent opportunity is ~25% larger than the plan claims and healthcare is ~20%
smaller. §2's frozen share and the weekday and affect rows survive.

**What to do:** commit the measurement as a script under `scripts/synthetic_data/`
(or a `reports/` notebook) and quote its output, so a later pass can tell a
library edit from a counting error. Re-run §3's table and open question 5 against
it. The v1 report's habit of quoting a figure with no reproducible provenance is
exactly what DD8 is a correction to.

### F2 — DD6a's payoff is an occurrence payoff, not a rule-count payoff, and §2's table misleads about it

§2's table (134 of 210 rules survive) is measured against **revision 1's** six
narrower lists. Against **revision 2's** wider lists, run through the real
`structural_sequence`:

| class | pairs | survive layer 2 today |
|---|---|---|
| adult female (9) | 72 | 30 |
| adult male (7) | 42 | 12 |
| elder female (7) | 42 | 20 |
| elder male (5) | 20 | 20 |
| adult neutral (12) | 132 | 110 |
| child neutral sg (5) | 20 | 20 |
| child neutral pl (2) | 2 | 2 |
| child female (daughter, girl) | 2 | **0** |
| child male (son, boy) | 2 | **0** |
| weekday (7) | 42 | 42 |
| healthcare place / person / encounter | 24 | 24 |
| affect (6) | 30 | 30 |
| **total** | **430** | **310** |

So **72% of the v2 rule set already loads today** and DD6a unlocks 120 rules, not
a majority. Widening the lists with colloquial members (which are not frozen) is
what did that — the plan's own §3 change quietly solved most of the rule-count
problem it opens §2 by describing.

The case for DD6a is undamaged, but it has to be stated in the right currency:

* **57% of referent occurrences are unreachable without it** (F1's 324 of 573),
  because the frozen members are the frequent ones.
* **Both gendered child sub-classes are empty without it.** `daughter` and `son`
  are frozen and `girl`/`boy` are not, so those two lists yield zero loadable
  rules today — and they carry 81 occurrences between them, the third and fourth
  most frequent referents in the corpus.

**What to do:** replace §2's table with the v2 one above, and move the
justification to occurrence coverage. Otherwise a stage-3 reader sees "DD6a buys
120 of 430 rules" and reasonably asks whether a mechanical safety layer is worth
weakening for it.

### F3 — DD6a must be gated to class-generated rules (safety)

`_check_structural` is called from `parse_rules` for **every** rule, including
the hand-written `fever_present.rules.json` and any future signal rule file.
Relaxing it to person-*class* comparison relaxes it for those too. Today
`my mum → my daughter` is refused mechanically; under DD6a as written it would
load, and only DD4's authoring convention — which is prose, not a check — stands
against it.

DD6a's four constraints are all about *how the map is built*. None of them is
about *which rules it applies to*, and the plan describes the change as "for
expansion only", which reads as "not the noise pass" rather than "not
hand-written rules".

**What to do:** carry the provenance on the rule. A `Rule` gains something like
`from_class: bool` (or the loader passes a comparison mode), person-class
comparison applies only when it is set, and hand-written rule files keep the
literal comparison they have. A test pins that a hand-written file containing
`my mum → my daughter` is still refused. This costs one field and removes the
only way DD6a widens blast radius beyond the thing it was argued for.

### F4 — DD10's first bullet is wrong; affect is not uniquely unprotected

Checked every member of all fourteen proposed lists against all seven entries of
`SIGNAL_LEXICONS` via `lint.lexicon_matches`: **not one member of any class
matches any lexicon.** So DD6 layer 3 passes trivially for the referent, weekday
and healthcare classes exactly as it does for affect. And after DD6a, layer 2 is
*also* vacuous for weekday and healthcare (no member is frozen), and for
referents it is reduced to a floor — it blocks `mum → I`, and nothing else a
class could express.

DD10's first bullet therefore does not distinguish affect from anything else in
the plan. Its **second** bullet (affect words do label work in
`*_null_attribution` and `*_null_hedged`) and **third** (folding affect into
`combined` costs §1's "a flip is unambiguously an error" claim) do, and they are
sufficient on their own.

**What to do:** keep the separate arm; rewrite the first bullet as a statement
about the whole plan rather than about affect. The honest version is: *"after
DD6a, no class in this plan is protected per-rule by either mechanical layer.
The declared invariant and `--dry-run-lint` are the entire safety argument for
all of them, and that is a change in posture from v1 that the reviewer should
price in."* That is a bigger and more useful sentence than the one it replaces,
and it raises the stakes on DD13 and on F5 below.

### F5 — The healthcare *place* class is unsafe as specified (safety)

§3 names `surgery` as "the class system's best cautionary example" and then
ships it anyway with the invariant as the only guard. Measured:

* **6 of 18 `surgery` occurrences are the operation sense** — *"after my
  gallbladder surgery"*, *"recovering from abdominal surgery"*, *"the surgery I
  had as a teenager"*, *"his knee surgery"*, *"I'm worried this might need
  surgery to fix it"*, *"My elderly dad's just had surgery"*. `surgery → clinic`
  is wrong on a third of its sites, and on the fifth it changes what the patient
  is asking about.
* **Both `practice` occurrences are the attributive "practice nurse"**
  (`fever_null_attribution.txt:48`, `recent_uti_true.txt:37`). `practice →
  surgery` yields "surgery nurse"; `practice → clinic` yields "clinic nurse".
  There is no site in the corpus where `practice` is a bare noun, so **every**
  rule with `practice` on either side is wrong at every site it can fire.

An invariant cannot fix this, because the invariant is a statement about the
class and the fault is per-site. Neither can `--dry-run-lint`: a broken rewrite
introduces no lexicon hit and exits 0 (DD11 says this; F5 is the instance).

**What to do:** either drop the place class, or make its `find` phrases
determiner- and preposition-anchored multi-word strings — `the surgery`,
`at the surgery`, `my surgery` — which the literal format supports and which
excludes "had surgery" and "need surgery" by construction. Drop `practice` as a
standalone member either way. The person and encounter sub-classes have no
equivalent problem and can stay as they are. Note that anchoring cuts the place
class's reachable sites to the ~12 non-operation `surgery` occurrences, which is
worth weighing against authoring it at all.

### F6 — `other half` produces "a other half"

DD11 raises determiner agreement in the abstract. The concrete instance is in the
neutral class, which is the one the plan calls largest and safest. Indefinite
articles on neutral members: `a friend` 10, `a colleague` 4, `a carer` 3 — **17
sites** where any rule with a vowel-initial multi-word replacement produces
broken English, and `other half` is the only vowel-initial member proposed.

**What to do:** drop `other half` (4 occurrences; it costs the class almost
nothing) or restrict it to a `my other half` ⇄ `my partner` style anchored pair.
Add "no vowel-initial member unless anchored" to whatever the class-file
checklist becomes — it is the one agreement rule that is mechanically checkable
and therefore should not be left to the invariant.

### F7 — DD12's memo does not remove the failure mode it is written for

Two gaps, both visible in `expand_example` (`expand.py:560`):

1. **The rate coin is per site and fires before the substitution.** Memoising the
   *target* leaves the *decision* unmemoised, so *"my wife has been up in the
   night … my wife is worried"* still becomes *"my sister … my wife"* whenever
   the second site loses its coin. The memo has to cover the coin as well: once
   a source word is drawn for in an example, every later occurrence of that
   source word takes the same outcome, substituted or not.
2. **The memo is keyed on the source, so it does not stop two sources
   collapsing onto one target.** *"My wife and my sister both…"* with
   `wife → sister` firing yields *"My sister and my sister"* — a coherence
   failure the memo as specified cannot see. 40 library lines carry more than
   one referent occurrence (F1) and the recombination is where this actually
   bites, exactly as DD12 says. Fix: draw targets injectively per example —
   exclude any target already used in this example and any referent already
   present in the source text.

Minor: `expand_example` has no `example_id` parameter and the memo is naturally
scoped to one call, so `(folded find)` alone is a sufficient key. DD12's
`(example_id, folded find)` implies a signature change and a shared dict that
neither is needed nor helps; the leak it guards against is impossible if the memo
is a local.

### F8 — DD13's cost estimate is two orders of magnitude low

Measured on this machine:

```
$ time python -m scripts.synthetic_data.expand --dry-run-lint
rules:    36, applied unconditionally to 3506 library lines
real    0m12.031s
```

`dry_run_lint` builds one variant per rule plus one COMBINED variant and lints
every fragment for every variant, so cost is linear in rule count: ~0.32 s per
variant. **430 class rules → 431 variants → ~140 s**, plus the fever file, so
roughly **2.5–3 minutes** rather than DD13's "a couple of seconds". It also grows
with every member added — taking one 9-member list to 12 adds 60 rules and 20
seconds.

Still cheap enough for CI and DD13 is still right that it should exist. But the
plan should say three minutes, and stage 2 should decide whether to memoise the
lint by rewritten text (most variants leave most fragments untouched, so the
lint is re-run on identical strings thousands of times) before the class set
grows again.

### F9 — `dry_run_lint`'s COMBINED variant barely tests classes

`rewrite_exhaustively` tie-breaks with `min(site.rules, key=lambda r: r.id)`.
Within a class every member matches at a site, so COMBINED collapses the whole
class onto whichever target sorts first by rule id: one of *N*−1 targets per
source is exercised in combination, the rest never.

Per-rule variants still cover every pair individually, so layer 3's per-rule
supplement is intact. What is thinned is precisely the thing DD6 says the mode
exists for — *"a rule that is individually harmless and manufactures a
cross-signal hit in combination"* — and DD6 also says that hazard is *more*
likely here than in v1.

**What to do:** for class rule sets, run *N*−1 combined passes (one per target
index, round-robin across the class) or one combined pass with a seeded random
target choice recorded in the report. The first is deterministic and costs the
same order as the per-rule pass; prefer it.

### F10 — Task 6's canary needs its condition stated

`0.9329` is the clean-trained decisive accuracy on the clean test tree
(`2026-09-04-lexical-variant.md` §2), with a 95% CI of [0.9119, 0.9527]. It is a
trained-model measurement, not a generation digest. Task 6 says it "must return
0.9329 decisive exactly, since generation is deterministic" — but deterministic
generation only guarantees the *data* is identical. Bit-exact reproduction of the
*accuracy* additionally requires `--determinism strict` (the default, so fine)
**and** an unchanged GPU, driver and torch build.

As written, the first torch bump voids a night for a reason unrelated to this
plan, and — worse — a reader who sees the canary miss will not know whether to
investigate the pipeline or the environment.

**What to do:** state it as "0.9329 on unchanged hardware and unchanged torch; a
mismatch stops the night for investigation, and a torch, driver or GPU change is
a benign explanation to rule out first". Record the torch version and device name
alongside the canary value in the pre-registration so the check can distinguish
the two cases without a human remembering.

---

## 3. The open questions, where the code settles them

1. **Person-class map shape — shared map, not a per-class field.** A per-class
   `person: third-party` declaration cannot express the refusal that DD6a exists
   to keep: `mum → I` is refused because `I` is in the *first-person* class, and
   `I` belongs to no swap class, so there is nowhere to put its declaration. The
   map is required regardless; a per-class field would be a second, redundant
   place to get it wrong. Take the shared map, add DD6a's "every class member
   appears in the map" test, and gate it per F3.
2. **How strict a review does a class invariant need?** The declared
   gender/life-stage/number fields are worth more if they are *checked* rather
   than merely declared. Three load-time checks make thirteen invariants
   tolerable: every ordered pair within a class agrees on all three fields (true
   by construction, so it is really a check that the class was split correctly);
   every member appears in the person-class map (DD6a already asks for this);
   and no member is vowel-initial unless anchored (F6). Beyond that the invariant
   is prose and F4 is the honest framing of what that means.
3. **What bound?** Stage 2's call. Anchor on 1.89%, per DD7 and DD8.
4. **Does affect stay a separate arm?** Yes — on DD10's second and third bullets,
   not its first (F4).
5. **Is it enough to move a model?** Re-measure first (F1): 573 referent
   occurrences on 527 of 2,506 lines (21%), plus 68 weekday, ~97 healthcare and
   71 affect. Larger than the plan claims, and the question stays open.
6. **Rate sweep?** No objection. Note that the class site density is genuinely
   different from fever's and can be measured on CPU before the night — add it to
   Task 2's measurements rather than sweeping blind.
7. **Reporting verbs?** Leave scoped out. The subcategorisation argument in §4 is
   correct and the class format cannot express the frame constraint.

---

## 4. Task list, with the review's changes folded in

Same seven tasks. Changes:

* **Task 1** additionally carries F3 (gate person-class comparison to
  class-generated rules, with a test that a hand-written `my mum → my daughter`
  is still refused).
* **Task 2** additionally carries F7 (memoise the coin, not only the target; draw
  injectively per example), F9 (round-robin combined variants for class rule
  sets), and the F1 measurement script whose output §3's table quotes. The
  re-measured n-gram ceiling should be reported against the corrected counts.
* **Task 3** drops or anchors the healthcare place class (F5) and drops or
  anchors `other half` (F6) before authoring begins, rather than discovering both
  in the dry-run output.
* **Task 4** budgets ~3 minutes, not seconds (F8).
* **Task 5** records the torch version and device alongside the canary (F10).
* **Tasks 6 and 7** unchanged.

Nothing here changes the task ordering or the claim that Tasks 1, 2 and 4 are
signal-agnostic machinery.

---

## 5. One thing the plan gets right that is worth keeping in stage 3

§1's table — *"does a flip mean an error? unambiguously yes, for the referent
classes"* — is the best property this ticket has, and DD10 protects it correctly.
F4 does not weaken it: the argument is semantic (referents are interchangeable by
construction) and does not depend on either mechanical layer. But it does depend
on F5 and F6 being fixed, because a class that produces "recovering from
abdominal clinic" makes a flip mean "the model noticed the text broke", which is
not the measurement §1 promises.

---

## 6. How every number above was measured

* Library statistics (F1, F5, F6): whole-word `(?<!\w)term(?!\w)` counts over
  non-blank, non-`#` lines of `data/synthetic/**/*.txt`, lowercased. 49 files,
  2,506 lines.
* Layer-2 survival (F2): `scripts.synthetic_data.expand.structural_sequence` over
  every ordered pair of §3's member lists, with the child group split four ways
  per DD11 and healthcare split three ways per §3.
* Frozen share (F2): members tested against
  `scripts.synthetic_data.noise.STRUCTURAL_FROZEN`.
* Lexicon coverage (F4): `scripts.synthetic_data.lint.lexicon_matches(member, s)`
  for every member and every `s in SIGNAL_LEXICONS`.
* Dry-run cost (F8): `time python -m scripts.synthetic_data.expand
  --dry-run-lint` on the committed `fever_present.rules.json`.
* Note `python` must be 3.12+ here — `recombine.py` uses PEP 695 generics and
  will not parse on 3.11.
