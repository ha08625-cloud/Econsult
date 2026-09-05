# Implementation plan: lexical variant expansion v2 — swap classes (12.10b)

**Stage 2 output. 2026-09-05.** Expands
`lexical_variant_expansion_v2_provisional.md` revision 2 into tasks, with the
corrections from `lexical_variant_expansion_v2_review.md` folded in. Where the
review and the provisional disagree, this document is the plan of record.

Read first: the provisional plan's §1 (why this ticket is not v1) and §5
(DD1–DD13), then the review. `arch_training.md` §8, §10, §12.6, §12.10 and §13
are the background the provisional cites and this document does not repeat.

---

## Plan

Give the expander a **swap class**: one hand-written list of interchangeable
members plus one declared invariant, expanded by the loader into every ordered
pair. Thirteen lists of ~66 words produce ~430 rules from thirteen reviews, and
because the members belong to no signal the rules apply to every library rather
than to one. That is a direct attack on the fault §1 names — every fragment
appears in dozens of examples character for character identical — and it is the
only lever available that does not require writing new fragments.

Getting there needs a change to a mechanical safety layer. Eleven of the referent
nouns the plan is built on are in `noise.STRUCTURAL_FROZEN`, and
`expand._check_structural` refuses any pair touching one, so 57% of referent
occurrences are unreachable today and both gendered child sub-classes are empty.
DD6a is that change; **F3 is the constraint that keeps it from spreading beyond
class files**, and it is the single most important line in this document.

Seven code tasks, then pre-register, run, report.

---

## Scope

**In scope**

* A committed measurement of the libraries (Task 1), because the provisional's
  own statistics do not reproduce and they are what the authoring decisions are
  made against.
* `structural_sequence` gains an optional person-class normalisation, applied
  **only** to class-generated rules (Task 2).
* A class file format at `data/expansion/classes/*.classes.json` and a loader
  that expands it to ordered pairs, each still subject to every per-rule check
  (Task 3).
* Signal-agnostic rule loading, `--rules` and `--class-groups` arm selection, and
  the sidecar and provenance changes those force (Task 4).
* Per-example memoisation and per-class injectivity for class rules (Task 5).
* Authoring the classes and reading the dry run as text (Task 6).
* A CI step that loads every rule and class file and runs `--dry-run-lint`
  (Task 7).
* Pre-registration, the batch, the report (Tasks 8–10).

**Out of scope** — unchanged from the provisional §4, and not reopened here:
time units, numbers, laterality, reporting verbs, cross-gender and
cross-life-stage swaps, certainty and hedge adjectives, Tier C, v1's Task 7, and
any edit to `data/synthetic/*.txt`, the manifest, `manifest.py`, `recombine.py`
or the generator.

**Newly out of scope, on the review's evidence**

* **The healthcare `place` class as a bare-noun class** (review F5). 6 of 18
  `surgery` occurrences are the operation sense and both `practice` occurrences
  are the attributive "practice nurse". Task 6 either drops the class or ships it
  as determiner-anchored multi-word finds; `practice` is dropped as a standalone
  member either way.
* **`other half` as a bare member** (review F6). Vowel-initial, and 17 neutral
  sites take an indefinite article.
* **Multi-signal training.** The classes are signal-agnostic, but the batch stays
  on `fever_present`, which is where the 2026-09-04 anchor is. The roll-out
  argument in §3 is about *authoring* cost and is not a claim that this ticket
  trains seven signals. `--dry-run-lint` still runs over all seven.

---

## Design decisions

DD1–DD13 stand as written in the provisional, with these amendments. Each names
the review finding it comes from.

### DD6a (amended) — person-class comparison, gated to class-generated rules

**F3.** `_check_structural` runs from `parse_rules` for every rule, so relaxing
it relaxes hand-written signal rule files too: `my mum → my daughter` would newly
load, with only DD4's prose against it. So the relaxation is carried on the rule:

* `Rule` gains `origin: str | None` — `None` for a rule read from a
  `*.rules.json` file, the class id for a rule the loader generated.
* `structural_sequence(phrase, *, person_classes: bool = False)`. The default is
  today's behaviour, byte for byte.
* `_check_structural` passes `person_classes=rule.origin is not None`.

**The map is total over referents, not only over the frozen ones.** DD6a says a
member missing from the map must fail closed. That is only true if *every*
referent maps: with a partial map, `sister` (unfrozen) yields `()` and a
forgotten member changes nothing, which fails open. With a total map, `sister`
yields `('<third-party>',)`, so a forgotten member yields `()` and every pair
touching it is refused. The total map is also strictly stronger than today —
`sister → nurse` is currently accepted by layer 2 and would be refused, because
healthcare people are deliberately left out of the map.

**Corrected in implementation (Task 2).** Revision 2 gave `sister → flatmate` as
that example. It is the wrong one: `flatmate` is a member of
`referent/adult_neutral`, so a *total* map maps it and the pair loads. What
actually stops `sister → flatmate` is that the two words are in different
classes, and no class file can generate a cross-class pair — layer 2 cannot see
class and never could. The strictly-stronger claim itself stands; it needs a
target the map genuinely omits.

Concretely, in `noise.py` beside `STRUCTURAL_FROZEN`:

```python
FIRST_PERSON = "<first-person>"
THIRD_PARTY = "<third-party>"

#: Person tokens normalised to their class for expansion's layer 2 (DD6a).
#: Authored, never inferred: a referent missing here yields an empty sequence,
#: so every pair touching it is refused rather than silently allowed.
PERSON_CLASSES: dict[str, str] = {...}
```

keyed on `fold_token` output, mapping the seven first-person tokens (`i`, `im`,
`i'm`, `ive`, `i've`, `my`, `me`) to `FIRST_PERSON` and every referent-class
member to `THIRD_PARTY`.

Three things stay out of the map and each is a judgement worth stating in the
docstring: **pronouns** (`he`, `she`, `her`, `his`, `they`…), because DD4 forbids
cross-gender swaps precisely because a pronoun cannot be repaired and collapsing
them would hide the violation from layer 2; **healthcare people** (`gp`,
`doctor`, `nurse`, `clinician`), because a clinician is not whose symptom this
is; and **weekday and affect members**, which are not persons at all.

### DD12 (amended) — memoise the decision, and draw injectively within a class

**F7.** The memo as specified in the provisional does not remove the failure mode
it is written for, in two ways.

1. **The rate coin is per site and fires before the substitution**
   (`expand_example`, `expand.py:560`), so memoising only the *target* still
   produces *"my sister … my wife"* whenever the second site loses its coin. The
   **decision** is memoised: once a source word is drawn for in an example, every
   later occurrence of that source word takes the same outcome, substituted or
   not.
2. **Keying on the source does not stop two sources collapsing onto one target.**
   *"My wife and my sister"* with `wife → sister` firing yields *"My sister and
   my sister"*. So targets are drawn **injectively within a class**: a candidate
   whose replacement is already used in this example, or already present in the
   source text as another member of the same class, is excluded from the weighted
   draw. If every candidate at a site is excluded the site is skipped and counted
   under a new `class_collision` reason.

Injectivity is scoped to the **class**, not to the rule set: `Monday and again on
Tuesday` both going to `Friday` is the same fault, and `fever → temperature`
firing three times in a line is not a fault at all.

**Both are gated to class-generated rules**, alongside DD6a. That is not
tidiness: it is what lets DD5's `v1` arm reproduce 2026-09-04 byte for byte, and
a v1 arm that does not reproduce is not an anchor.

Minor: the memo is a local in `expand_example`, so `(folded find)` is a
sufficient key. The provisional's `(example_id, folded find)` implies a signature
change and a shared dict, and guards against a leak that a local makes
impossible.

### DD10 (amended) — the affect class stays a separate arm, on two of its three bullets

**F4.** DD10's first bullet — "neither mechanical layer protects it" — is true of
**every** class in this plan, not only affect. Checked: not one member of any of
the fourteen proposed lists matches any of the seven `SIGNAL_LEXICONS`, so layer
3 passes trivially for all of them; and after DD6a layer 2 is vacuous for weekday
and healthcare and is only a floor for referents.

The decision does not change — affect is authored as its own group, run as its
own arm, and reported separately — but the reasoning is DD10's second bullet
(affect words do label work in `*_null_attribution` and `*_null_hedged`; a third
instance is `fever_true.txt:19`, *"I assumed I was just anxious about the
interview…"*) and third (folding it into `combined` costs §1's "a flip is
unambiguously an error" claim).

What replaces the first bullet is a statement about the whole ticket, and it
belongs in the pre-registration: **after DD6a, no class in this plan is protected
per-rule by either mechanical layer. The declared invariant, `--dry-run-lint` and
the committed-file tests are the entire safety argument.** That is a change of
posture from v1 and it is why Tasks 6 and 7 are not optional.

### DD14 (new) — "every rule fires somewhere" cannot survive generated pairs

`tests/test_synthetic_expand.py::test_every_committed_rule_fires_somewhere_in_the_libraries`
is a good guard and it will fail on a class file. Measured over a 384-rule
reconstruction of §3's lists, **68 rules (18%) fire nowhere**, because twelve
members occur zero times in the libraries: `missus`, `daddy`, `nanna`, `nana`,
`granny`, `granddad`, `grandpa`, `grandfather`, `gramps`, `coworker`, `uneasy`,
`on edge`.

That is the mechanism working, not a fault. Those members exist to widen the
*target* vocabulary; a member that never occurs can never be a `find` and is
still valuable as a `replace`. So for class files the guard becomes: **every
class member that occurs in the libraries fires as a `find`, and every member
occurs at least once as a `replace`.** A member that is neither is authoring cost
for nothing and should be deleted.

### DD15 (new) — the reachable-ceiling and occurrence numbers are committed code

**F1.** The provisional's library statistics do not reproduce: referent
occurrences are ~25% higher than claimed, healthcare ~20% lower, and the
referent-bearing line count is 527/2,506 rather than 470. The v1 report's `+10.8%`
and `+25.8%` reachable-4-gram figures have no committed provenance either.

Neither number is quoted again from prose. Task 1 commits the measurement and
every table in the report is its output.

---

## Task 1: Measure the libraries, and commit the measurement

**A.** Nothing in this ticket has been built. This task is deliberately first and
depends on nothing: §13 says put the cheap failure at the front, and this is the
measurement that decides which classes are worth authoring at all. It is CPU-only
and stdlib-only.

**B. Files**

* New: `scripts/synthetic_data/class_stats.py`
* New: `tests/test_synthetic_class_stats.py`
* Read: `data/synthetic/manifest.json`, `data/synthetic/**/*.txt`,
  `scripts/synthetic_data/manifest.py` (`load_fragments`),
  `scripts/synthetic_data/noise.py` (`STRUCTURAL_FROZEN`, `fold_token`),
  `scripts/synthetic_data/lint.py` (`SIGNAL_LEXICONS`, `lexicon_matches`)

**Deliverables**

1. A module runnable as `python -m scripts.synthetic_data.class_stats`, printing
   a table per candidate class: members, per-member occurrence count, total
   occurrences, lines carrying at least one member, lines carrying more than one,
   members with zero occurrences, members that are in `STRUCTURAL_FROZEN`, and
   members that match any `SIGNAL_LEXICONS` entry.
2. A second section: for every member, its determiner context counts (`a`, `an`,
   `the`, `my`, `our`, `his`, `her`, `their`, bare), which is what makes review
   F6 visible before authoring rather than after.
3. Reads the candidate lists from the class files if they exist and from a
   hard-coded candidate list if they do not, so it is usable before Task 3 and
   still usable after.
4. Tests: the counts are whole-word and case-insensitive; a member inside a
   longer word is not counted; the frozen and lexicon columns agree with
   `STRUCTURAL_FROZEN` and `lexicon_matches` rather than restating them.

**C. Instructions**

Count over non-blank, non-`#` lines of `data/synthetic/**/*.txt` — 49 files,
2,506 lines, which is the denominator the provisional names and the one number of
its that reproduces. Use `(?<!\w)term(?!\w)` on the lowercased line, matching
`match_sites`' whole-word rule; do not use `load_fragments` for the counting,
because the manifest also carries the 1,000-line generated `declarative_v1`
library, which contains **zero** members of any proposed class and is not drawn
at the shipped `--declarative-share 0.0`.

Print, do not assert. This is an instrument, not a gate — its job is to change
what gets authored in Task 6.

Then update the provisional plan's §2 and §3 tables from its output, in place,
with a line saying which command produced them. Do not carry a number forward
from prose.

---

## Task 2: Layer 2 compares person class, for class rules only (DD6a, F3)

**A.** Task 1 has committed the measurement. This is the only task that changes a
mechanical safety layer, and the prerequisite for every class rule loading at
all. `STRUCTURAL_FROZEN` is not edited.

**B. Files**

* `scripts/synthetic_data/noise.py` — add `FIRST_PERSON`, `THIRD_PARTY`,
  `PERSON_CLASSES` beside `STRUCTURAL_FROZEN` (line ~116)
* `scripts/synthetic_data/expand.py` — `structural_sequence` (line ~259),
  `_check_structural` (line ~346), `Rule` (line ~211), the `_STRUCTURAL`
  constant (line ~155)
* `tests/test_synthetic_expand.py` — extend the layer-2 block (lines 135–157)
* `tests/test_synthetic_noise.py` — the map's own tests

**Deliverables**

1. `PERSON_CLASSES` in `noise.py`, authored, keyed on `fold_token` output, total
   over every referent member of every class in the provisional's §3 plus the
   seven first-person tokens. Docstring states why pronouns, healthcare people,
   weekdays and affect words are absent.
2. `Rule.origin: str | None = None`.
3. `structural_sequence(phrase, *, person_classes: bool = False)`; with the flag,
   the token stream is mapped through `PERSON_CLASSES` **after** contraction
   expansion and before the `_STRUCTURAL` filter, and `_STRUCTURAL` includes the
   two class markers. Keys may be multi-word (space-joined folded tokens) and
   are matched **longest-first**; see the correction under C.
4. `_check_structural` uses `person_classes=rule.origin is not None`, and its
   error message names the class when it refuses a generated rule.
5. Tests, both directions.

**C. Instructions**

Order matters inside `structural_sequence`: expand contractions first, so
`I've → I have` still produces `('<first-person>', 'have')` on both sides and the
Tier A rules the pass exists to carry are not newly refused. Map, then filter to
`_STRUCTURAL`, then return.

**Corrected in implementation (Task 2): map by longest match, not per token.**
Revision 2 said "map per token". Two referent members are multi-word — `little
one` (`child_neutral_singular`) and `other half` (`adult_neutral`) — and a
per-token map cannot reach either: neither `little`/`one` nor `other`/`half` is
a sensible key on its own, so `little one` normalises to `()` and every pair
touching it is refused. That fails closed, which is safe, but it silently
deletes a member from a class and Task 6 would meet it as an unexplained dead
entry rather than a decision. So `PERSON_CLASSES` keys may be multi-word
(folded tokens joined by single spaces) and are matched longest-first, which
makes `little one` collapse to one `<third-party>` exactly as `kid` does. Pin
that no multi-word key begins with a structural token, so a match can never
swallow one; today the longest keys are `little one` and `other half`, and
neither `little` nor `other` is frozen.

(This is orthogonal to F6, which drops `other half` for the article fault —
"a other half" — not for anything layer 2 sees.)

Pin **newly allowed**, all with `origin` set: `mum → sister`, `partner →
flatmate`, `son → boy`, `daughter → girl`, `my wife → my sister`.

Pin **still refused**, with `origin` set: `mum → I`, `my wife → I`, `sister → my
sister`, `mum → my mum`, and `sister → nurse` (the new refusal — a referent
swapping to a word the map deliberately omits). Revision 2 gave `sister →
flatmate` here; that pair loads, for the reason set out under DD6a above.
`sister → plumber` is worth pinning beside it: `nurse` shows the deliberate
omission, `plumber` shows the accidental one, and the fail-closed argument is
about the second.

Pin **unchanged for hand-written rules** (`origin is None`): every existing
layer-2 case in the file still raises, plus a new one — a `*.rules.json` file
containing `my mum → my daughter` is still refused. That test is the whole point
of F3 and should carry a comment saying so.

Pin the map's totality: every member of every committed class file appears in
`PERSON_CLASSES` or is not a referent class member. Since class files do not
exist until Task 3, write this as a test over the candidate list in
`class_stats.py` and tighten it in Task 6.

Do not touch `STRUCTURAL_FROZEN`, and do not let the noise pass see
`PERSON_CLASSES`: it needs the literal freeze, and the two lists living in one
module is what stops them drifting.

---

## Task 3: The class file format and the loader (DD3, DD11)

**A.** Layer 2 now admits person-class swaps for rules carrying an `origin`.
Nothing generates such rules yet. This task adds the format and the expansion to
ordered pairs; it does not author any class and does not change how rule files
are selected at run time (that is Task 4).

**B. Files**

* `scripts/synthetic_data/expand.py` — new constants and `parse_classes`,
  `load_classes`, beside `parse_rules` (line ~385) and `load_rules` (line ~420)
* `tests/test_synthetic_expand.py` — a new block mirroring the rule-format block
  (lines 76–200)

**Deliverables**

1. The format, at `data/expansion/classes/<group>.classes.json`:

   ```json
   {
     "group": "referent",
     "classes": [
       {
         "id": "referent.adult_female",
         "gender": "female",
         "life_stage": "adult",
         "number": "singular",
         "person": "third-party",
         "tier": "B",
         "members": ["mum", "mother", "sister", "..."],
         "invariant": "..."
       }
     ]
   }
   ```

   Both key sets closed, exactly as `RULE_KEYS` and `FILE_KEYS` are and for the
   same reason: a misspelt key must be an error, not a comment.
2. `parse_classes(payload, *, source)` returning a `ClassSet` — file-free, so the
   tests can put a malformed document in front of every check without a disk.
3. Ordered-pair expansion: for each class, every `(a, b)` with `a != b` becomes a
   `Rule` with `origin=<class id>`, `tier` from the class, `invariant` from the
   class, `weight` 1.0, and a deterministic id `f"{class_id}:{a}->{b}"` with
   spaces replaced by `_`. Sorted, so two loads produce byte-identical rule
   order.
4. Every generated rule goes through `_check_shape`-equivalent validation,
   `_check_matchable`, `_check_structural` and the strengthened `_check_lexicons`
   of Task 4 — generation is a convenience for the author, not a hole (DD3).
5. Load-time checks that make DD11 and DD6 layer 1 mechanical rather than prose:
   * every member is unique within its class and across every class in the same
     group (a word in two classes is a swap that escapes its declared gender);
   * `gender`, `life_stage`, `number` and `person` are from closed vocabularies;
   * class ids are unique across all files;
   * **no member is vowel-initial unless it is a single word** (review F6): a
     multi-word vowel-initial replacement produces "a other half" and no
     mechanical layer sees it;
   * the invariant is ≥ 120 characters — twice the rule floor, because one class
     invariant now stands for dozens of rules (DD6 layer 1's concentration of
     risk);
   * a class of fewer than 2 or more than 12 members is refused: below 2 it
     generates nothing, above 12 the pair count and the review burden both stop
     being reviewable.
6. Tests for each of the above, plus: a well-formed file loads; the generated
   rule set is the full ordered-pair set; ids are stable across loads; a class
   containing a member missing from `PERSON_CLASSES` is refused by layer 2 with a
   message naming the class.

**C. Instructions**

Do **not** add a `signal` key. A class belongs to no signal — that is DD2 and it
is what Task 4 acts on.

Do **not** make `number` or `gender` do anything mechanical beyond the closed
vocabulary and the uniqueness check. They are declarations that make a reviewer's
job small and concrete; the plan does not claim the loader can check agreement,
and DD11 is explicit that the format cannot.

Keep `ExpansionError` messages in the existing register: name the file, the
class, the member and the check that refused it. A class file is authored by a
human and the rejection message is the whole of that person's feedback loop.

---

## Task 4: Signal-agnostic rules, arm selection, and provenance (DD2, DD5)

**A.** Classes parse and expand to validated rules. They cannot yet be *run*:
`parse_rules` requires a `signal` in `SIGNAL_LEXICONS`, `check_tree` requires a
`<signal>.rules.json` per signal in the tree, and the sidecar records exactly one
rule file. This task makes the five arms of DD5 expressible on the command line.

**B. Files**

* `scripts/synthetic_data/expand.py` — `_check_lexicons` (line ~355),
  `check_tree` (line ~815), `build_expansion_stats` (line ~728), `load_rulesets`
  (line ~1285), `build_parser` (line ~1311), `expand_file`/`expand_tree`
* `scripts/encoder_training/__main__.py` — `_expansion_provenance` (line ~405)
* `tests/test_synthetic_expand.py`, `tests/test_encoder_training_arm_b.py`

**Deliverables**

1. `_check_lexicons` takes `signal: str | None`. For `signal is None` (a class
   rule) the check becomes, for **every** signal *s*,
   `set(lexicon_matches(find, s)) == set(lexicon_matches(replace, s))` — neither
   introduced nor removed. That is strictly stronger than the scoped form, and it
   is what makes `night → morning` impossible to author as a class even by
   accident (DD2).
2. `--rules {signal,classes,both}`, default `both`, and
   `--class-groups <comma list>`, default every group found. Together these are
   DD5's arms:

   | arm | invocation |
   |---|---|
   | clean | no expansion |
   | v1 | `--rules signal` |
   | classes | `--rules classes --class-groups referent,calendar,setting` |
   | combined | `--rules both --class-groups referent,calendar,setting` |
   | affect | `--rules classes --class-groups affect` |

3. `--classes-dir`, default `data/expansion/classes`.
4. `check_tree` loads the per-signal rule file only when `--rules` includes
   `signal`, and a missing file is fatal only then. It still refuses a signal
   that ends up with **zero** rules, because writing an untouched copy of a tree
   under a name that says "expanded" is a silent no-op an arm comparison cannot
   see.
5. The sidecar's `expansion.requested.rules` becomes `rule_sources`: a list of
   `{path, sha256, kind, signal, count}`, `kind` in `{"rules", "classes"}` and
   `signal` null for classes. Add `class_groups` alongside.
6. `_expansion_provenance` updated to read the list. **This is not optional**:
   it currently does `isinstance(rules, Mapping)` and would silently degrade to
   `None` for every provenance field, losing the rule digests that make an arm
   reproducible — and it would do so without failing.
7. Tests: each arm loads the rule set it names; a classes-only run on a signal
   with no rule file succeeds; a run whose selection yields no rules is refused;
   the sidecar carries one entry per file with its digest; the provenance block
   in a training report names every source.

**C. Instructions**

Keep one `RuleSet`-per-signal at the point of use. The simplest shape that works:
`check_tree` returns `dict[str, tuple[Rule, ...]]` — the signal's own rules plus
the class rules, concatenated — and `expand_file` takes that tuple. The sidecar
records the *sources*, so provenance survives the concatenation.

Watch the ordering: `match_sites` prefers the longest needle and ties are broken
by weight, so a class rule and a hand-written rule matching the same site
compete. In the `combined` arm that is real — `my mum` (hand-written, if one
existed) versus `mum` (class). Longest wins, which is the behaviour already
tested at `test_the_longest_match_at_a_position_wins`; add a test that says so
explicitly for the mixed case, because it is now reachable.

Do not renumber or reword the existing `expansion` block keys beyond
`rules → rule_sources`. `dataset._read_stats` checks only the keys it requires
and an extra block is additive, but the training reports quote these names.

---

## Task 5: Per-example memoisation and per-class injectivity (DD12, F7)

**A.** The five arms run. A referent can appear more than once in one example —
40 of 2,506 library lines carry two, and the recombination is where the exposure
actually is — and today two sites draw independently, so one person becomes two.

**B. Files**

* `scripts/synthetic_data/expand.py` — `expand_example` (line ~560),
  `ExpansionResult` (line ~540), `MatchSite` (line ~455)
* `tests/test_synthetic_expand.py` — the substitution block (lines 204–300)

**Deliverables**

1. In `expand_example`, a local `memo: dict[str, str | None]` keyed on the folded
   matched text. For a site whose candidate rules all carry an `origin`:
   * if the key is in `memo`, take that outcome — `None` means leave it alone —
     and **spend no coin**;
   * otherwise draw the coin, record `None` on a loss, and on a win draw the
     replacement and record it.
2. Injectivity within a class: maintain, per class id, the set of folded
   replacements already committed in this example **union** the folded members of
   that class already present in the source text. Exclude candidates whose folded
   replacement is in that set before the weighted draw. If that empties the
   candidate list, skip the site and count `skipped["class_collision"]`.
3. Sites whose candidates carry no `origin` keep today's path exactly: coin,
   weighted choice, no memo, no injectivity.
4. Telemetry: a new `skipped` reason `class_collision`, and a new counter for how
   often the memo decided a site. DD12 asks for that number because it is also
   the size of the bug it prevents.
5. Tests: a text repeating one referent takes one outcome at every site, whether
   that outcome is "substituted" or "not"; `"my wife and my sister"` never
   produces `"my sister and my sister"`; a source word already present as a
   target is excluded; a class rule and a hand-written rule in the same example
   do not share a memo; **and a fever-only rule set produces byte-identical
   output to the pre-Task-5 code**.

**C. Instructions**

That last test is the one that matters most. DD5's `v1` arm is the anchor against
2026-09-04 and it is only an anchor if it reproduces. Write it as a golden: a
fixed seed, the committed `fever_present.rules.json`, a fixed input, and the
expected output string inline.

Mind the coin accounting. Today every site draws exactly once from the example's
`random.Random`, so the RNG stream position is a function of the site count.
Memoising means a repeated source word no longer draws, which changes the stream
for **class** rule sets. That is fine and expected; it is not fine for the fever
path, which is why the gate is on `origin` and not on a flag.

Scope injectivity to the class id, not to the rule set and not to the group.
Repeating `temperature` in a line is correct; repeating a referent is not; and
`Monday … Tuesday` both landing on `Friday` is the same fault as the referent
one.

---

## Task 6: Author the classes, and read the dry run (DD11, F5, F6, F9, DD14)

**A.** Every mechanical piece is built and tested. No class exists. This is the
authoring cost of the whole ticket and, per §3, unlike v1 it does not repeat per
signal.

**B. Files**

* New: `data/expansion/classes/referent.classes.json`,
  `calendar.classes.json`, `setting.classes.json`, `affect.classes.json`
* `scripts/synthetic_data/class_stats.py` — extend with the reachable-n-gram
  ceiling
* `tests/test_synthetic_expand.py` — the committed-file block (lines 700–798)
* Read: the provisional §3 table as re-measured by Task 1

**Deliverables**

1. The four class files. Members from §3, **less** the review's exclusions:
   * `other half` is dropped, or shipped only as the anchored pair
     `my other half` ⇄ `my partner` (F6);
   * the healthcare **place** class is dropped, or shipped with
     determiner-anchored finds — `the surgery`, `at the surgery`, `my surgery` —
     and never a bare `surgery`; `practice` is dropped as a standalone member
     either way (F5). Note before deciding: anchoring leaves the class ~12
     reachable sites, which may not be worth a review.
   * the child group splits four ways by gender and number (DD4, DD11);
   * `nanny` stays excluded (also a childcare worker); members stay British.
2. An invariant per class, ≥ 120 characters, written against the
   `*_null_attribution` and `*_null_hedged` libraries rather than against
   `emotional.txt` for the affect class (DD10), and naming any member with a
   second common sense (DD11).
3. Committed-file tests, mirroring the existing rule-file block:
   * every file loads through every layer (loading *is* the assertion);
   * every class member appears in `PERSON_CLASSES` or is not a referent —
     tighten the placeholder from Task 2;
   * **DD14's replacement for "every rule fires"**: every member that occurs in
     the libraries fires as a `find`, and every member occurs at least once as a
     `replace`. 68 of 384 generated rules fire nowhere and that is correct —
     twelve members occur zero times by design, to widen the target vocabulary;
   * no class rewrite lands a library line on a differently-labelled library's
     line. This is the existing
     `test_no_committed_rule_rewrites_a_line_into_another_librarys_line` extended
     to classes, and it is the check most likely to fire on a referent swap. A
     384-rule reconstruction produces **zero** collisions per-rule, so a failure
     here means the authored lists differ from the reconstruction and the
     difference wants looking at;
   * `--dry-run-lint` passes over the committed libraries for all seven signals.
4. The reachable-n-gram ceiling, re-measured now that layer 2 admits the frozen
   referents. Revision 1's `+25.8%` is void and no figure is quoted until this
   produces one. Committed as code (DD15), CPU only, run before any GPU night.
5. `--dry-run-lint` output read **as text**, not only as an exit code, and the
   reading written into the task's completion note. A rule that produces broken
   English introduces no lexicon hit and exits 0; that is DD11 and F5 is the
   worked instance.

**C. Instructions**

Author against Task 1's measurement, not against §3's table. Delete any member
Task 1 shows occurring zero times *and* not wanted as a target.

Expect `--dry-run-lint` to take about **three minutes**, not seconds (F8): it is
12.0 s for 36 rules over 3,506 fragments and linear in rule count. Budget for it
and do not assume a hang.

**On F9, and this is the one judgement call left in this task.**
`rewrite_exhaustively` breaks ties with `min(site.rules, key=lambda r: r.id)`, so
under the `COMBINED` variant a whole class collapses onto whichever target sorts
first: 1 of *N*−1 targets per source is exercised in combination, and the rest
never are. Per-rule variants still cover every pair. What is thinned is exactly
the hazard DD6 says `--dry-run-lint` exists for and calls *more* likely here than
in v1. Either extend `dry_run_lint` to run *N*−1 combined passes for class rule
sets, round-robining the target index — deterministic, same order of cost as the
per-rule pass — or record explicitly in the completion note that the combined
check is partial for classes and why that was accepted. Do not leave it
undiscussed.

---

## Task 7: CI loads every rule and class file (DD13, F8)

**A.** The classes are authored and their tests pass locally. Nothing in
`.github/workflows/` or the `Makefile` runs `expand.py`, so a class file can be
committed broken, or rot silently as the lexicons grow — which is what makes
DD10's "layer 3 will reject it when a mental-health signal arrives" theoretical
rather than true.

**B. Files**

* `.github/workflows/tests.yml` — the `ruleset-validation` job (lines 44–90)
* `Makefile`

**Deliverables**

1. A step in **`ruleset-validation`**, not `unit`. That job is gated on
   `data/**` (the `changes` filter, line 41), and a class file edit is a `data/`
   edit that skips the unit job entirely — which is the same reasoning the three
   steps already in that job carry in their comments. Copy that comment style.
2. The step runs `python -m scripts.synthetic_data.expand --dry-run-lint`, which
   with Task 4's defaults loads every `*.rules.json` and every `*.classes.json`
   and exits non-zero on a manufactured hit.
3. A `make` target so the same command is one word locally.
4. The step's comment states the measured cost: ~3 minutes at ~430 rules, linear
   in rule count. Do not write "a couple of seconds".

**C. Instructions**

Stdlib plus `requirements.txt` only — no GPU, no ML wheels. That is the whole
point of the step and it is what §13 means by a check that runs before a GPU
night rather than inside one.

If the runtime is judged too long for every `data/**` PR, the cheap fix is to
memoise the lint by rewritten text inside `dry_run_lint`: most variants leave
most fragments untouched, so the lint currently re-runs on identical strings
thousands of times. Do that rather than sampling the rules — a sampled check is
not a check.

---

## Task 8: Pre-register (DD5, DD7, DD10, F10)

**A.** All seven code tasks are done and every CPU measurement exists. Nothing
has been trained.

**Deliverables**

1. The five arms of DD5, with **`combined` named as the decision arm** and the
   other four named explicitly as exploratory. §13 says this is the discipline
   that replaces gating, and with five arms picked over post hoc a winner appears
   by noise.
2. Bounds stated in absolute terms and anchored on the **observed 1.89%**
   synthetic baseline, not on Task 2's 15.4% real-text figure. That anchoring
   mistake is DD8 and it is the most reusable thing the v1 run produced.
3. Separate bounds and separate read-outs for the referent classes and for affect
   (DD10). The referent bound may be stated as "at or near zero", because there
   is no defensible reason for a model's answer to change when `sister` becomes
   `brother`; the affect bound may not, because that is a register swap of v1's
   kind.
4. The DD10-amended posture, written down: after DD6a no class is protected
   per-rule by either mechanical layer, so the declared invariants,
   `--dry-run-lint` and the committed-file tests are the whole safety argument.
5. The canary, **with its condition** (F10). `0.9329` is the clean-trained
   decisive accuracy on the clean test tree with a 95% CI of [0.9119, 0.9527] —
   a trained-model measurement, not a generation digest. Bit-exact reproduction
   needs `--determinism strict` (the default) *and* an unchanged GPU, driver and
   torch build. Record the torch version and device name alongside the value, and
   state that a mismatch stops the night for investigation with an environment
   change as the first thing to rule out.
6. Every arm's read-out written before the night.

---

## Task 9: Run the batch

**A.** Pre-registered. GPU night.

**Deliverables**

1. A composite entry in `scripts/training_gui/runs.json`, parameterless, in the
   shape of the existing lexical entry (line ~852). Adding an arm is a catalogue
   edit, not a code change (§13).
2. The batch **opens** with `smoke-cuda`, the reproduce check (Task 8 item 5) and
   `--dry-run-lint`. A wasted night should fail in minute five, not hour eight.
3. Five arms, the 2×2 shape where it applies, scored against clean and expanded
   test trees.
4. At roughly two minutes per fold a night holds about 240 fold-trainings, so
   five arms is comfortably affordable and there is room for the rate sweep of
   open question 6 if Task 8 pre-registers it.

---

## Task 10: Report

**Deliverables**

1. Against the pre-registration, item by item, **including the items that fail**.
2. Referent-class and affect-class flip rates reported separately (DD10).
3. The memo-firing rate from Task 5's telemetry, which DD12 asks for because it
   is the size of the bug the memo prevents.
4. Every library statistic quoted as the output of `class_stats.py`, with the
   command (DD15).
5. A plain-English companion, and — per DD8 — verify that
   `2026-09-04-lexical-variant-plain-english.md` carries the §12.10 correction
   already applied to `arch_training.md` and to the main report.

---

## What is still open after this plan

Closed by the review, using the code: open questions 1 (shared map, gated per
F3), 2 (the declared fields become load-time checks — Task 3 deliverable 5), 4
(affect stays a separate arm, on DD10's second and third bullets), and 7
(reporting verbs stay out).

Still genuinely open, and Task 8's to settle:

* **What bound** (question 3). Absolute, anchored on 1.89%, separately for
  referents and affect.
* **Whether ~800 occurrences move a model at all** (question 5). Task 1 says the
  opportunity is larger than the provisional claimed — 573 referent occurrences
  on 527 of 2,506 lines, 21% — but nothing yet says a model notices, and Task 9
  is allowed to answer negatively.
* **Whether the rate needs re-tuning, and whether to sweep it as arms**
  (question 6). The class site density differs measurably from fever's; Task 1
  produces that number, so the sweep can be argued rather than guessed.
* **Whether to author the healthcare place class at all** (new, F5). Task 6
  decides, with the anchored-form site count in hand.
