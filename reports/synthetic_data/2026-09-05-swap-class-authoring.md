# Swap class authoring — completion note

**Task 6 of the lexical variant expansion v2 plan (12.10b). 2026-09-05.**

Sixteen classes in four group files, expanding to **320 rules from 71 members**.
Everything below is the reading Task 6 deliverable 5 asks for: the dry run read
as text rather than as an exit code, and the judgement calls it forced.

---

## 1. What shipped

| group | classes | members | pairs | occurrences | lines carrying ≥1 |
|---|---|---|---|---|---|
| `referent` | 13 | 45 | 252 | 569 | 507 (20.2%) |
| `calendar` | 1 | 7 | 42 | 68 | 64 (2.6%) |
| `setting` | 1 | 3 | 6 | 49 | 49 (2.0%) |
| `affect` | 1 | 5 | 20 | 71 | 71 (2.8%) |
| **all** | **16** | **71** | **320** | **757** | — |

Regenerate with `python -m scripts.synthetic_data.class_stats`. Every number in
this note is its output (DD15); none is quoted from the provisional's §3 table,
which does not reproduce.

### Reachable n-gram ceiling (deliverable 4)

`class_stats` section 4, run after DD6a unfroze the referent nouns. Revision 1's
`+25.8%` is void and this replaces it.

| scope | 3-gram | 4-gram | 5-gram |
|---|---|---|---|
| referent | +17.3% | **+27.1%** | +35.3% |
| calendar | +3.0% | +4.5% | +6.0% |
| affect | +1.7% | +2.4% | +2.9% |
| setting | +0.9% | +1.1% | +1.4% |
| **all** | **+23.4%** | **+36.8%** | **+48.3%** |

An upper bound, not a forecast: a real run draws at `--rate` and leaves
`--clean-share` untouched. CPU only, ~7 s, no GPU night needed.

---

## 2. What was dropped, and on what evidence

Each of these is a candidate list from the provisional's §3 that is **not**
shipped. None was dropped on taste.

* **healthcare `place`** (F5, confirmed). 6 of 18 `surgery` occurrences are the
  operation sense ("need surgery to fix it", "his knee surgery", "just had
  surgery"), and both `practice` occurrences are the attributive "practice
  nurse". The plan's determiner-anchored alternative leaves ~12 reachable sites,
  which is not worth a review. Dropped entirely.
* **healthcare `encounter`** (new; not in the review). `appointment` is the only
  member that occurs at all (22 of 23), and the libraries write "**an**
  appointment" at 8 sites. Both other members are consonant-initial, so every
  swap at those sites produces "an consultation". The class cannot be made safe
  by dropping a member, because dropping `appointment` empties it. Dropped.
* **`other half`** (F6). The loader refuses it outright — vowel-initial and
  multi-word — which is F6 turned into a mechanical check by Task 3.
* **`on edge`** (affect). Same loader rule. It occurred nowhere, so the cost is
  one unreachable target.
* **`uncle`** (new). The male class has exactly one indefinite-article site,
  "A colleague of mine has **a father** who has had blood in his urine", and
  `uncle` is the only vowel-initial member. One site of ~100, and one broken
  "a uncle" is worse than seven unreachable finds. `aunt`/`auntie` stay: the
  female class has zero article sites, so the same word shape is safe there.
  That asymmetry is measured, not principled, and a future library line writing
  "a mother" would reopen it.
* **`carer`** (new). "I'm a carer for a lady who keeps telling me…" and "I'm a
  carer for a gentleman…" break under every swap — "I'm a friend for a lady".
  3 of 9 sites, and the professional sense is not repairable by a bare-noun rule.
* **`youngest` / `eldest`** (new). "my two youngest are both saying" is plural
  and "My youngest woke me at midnight" is singular, so no truthful `number` can
  be declared for a class holding them, and DD11's declarations are the whole of
  a reviewer's handle. `eldest` is also vowel-initial where the class writes
  "a kid" at 10 sites.
* **`mummy` / `daddy`** (new). `daddy` occurs nowhere and `mummy` occurs once,
  as a child's quoted vocative ("said mummy you're too warm"), which is exactly
  the site a bare-noun swap cannot survive. An adult e-consult author does not
  write "my mummy has a fever", so neither is worth its target slot.
* **`clinician`** (new). Zero occurrences and not a register a patient writes.
* **`coworker`** (new). Zero occurrences, and British usage is `colleague`.

---

## 3. The finding neither the plan nor the review had: in-law compounds

`match_sites` bounds a whole word on non-word characters, so `-` does not stop a
match. The bare `mother` therefore matches **inside** "my mother-in-law", and
`referent.adult_female` rewrote the line to "my mum-in-law"; `wife`, `missus`
and `girlfriend` gave "my wife-in-law". Twenty-five library lines spell an
in-law relationship across seven base nouns:

```
mother in law 5   brother-in-law 4   brother in law 4   sister in law 2
father-in-law 2   daughter in law 2  mother-in-law 1    son in law 1
father in law 1   daughter-in-law 1  mum-in-law 1       mother-in law 1
```

That is 4.4% of all referent occurrences, and **`--dry-run-lint` cannot see any
of it**: no lexicon term moves, so it exits 0. It is a fluency defect rather
than a labelling one — "my wife in law" still reads as a third party — but it is
exactly the fault DD11 says the invariant and the dry-run *read* exist for.

**Fix: four compound classes, whose first job is to shadow.** Because the
longest find wins at a site, listing "mother in law" as a member takes the site
away from the bare "mother" and moves it into a class where every swap is well
formed. Hyphenated and unhyphenated are **separate classes** and must be: layer
2 reads `mother-in-law` as one token and `mother in law` as three, so the two do
not produce the same sequence and `parse_classes` refuses a class holding both.
The six hyphenated forms plus `mum-in-law` were added to `noise.PERSON_CLASSES`,
without which they yield an empty sequence and pass layer 2 *vacuously* rather
than failing closed.

23 of the 25 sites are now shadowed. The two that are not are discussed below.

---

## 4. The dry run, read as text

```
$ python -m scripts.synthetic_data.expand --dry-run-lint --rules classes
rules:    320, applied unconditionally to 3506 library lines
lines any rule rewrites: 637
INTRODUCED hits: none.
REMOVED hits: none.
PASS
```

84 seconds, not the ~3 minutes F8 budgets — the rotation passes are cheap next
to the 320 per-rule ones. **Exit 0 is the weaker half of the result.** It proves
no swap manufactures or removes a lexicon hit; it says nothing about whether the
English is sound. So every one of the 637 rewritten lines was also swept for
grammar hazards a lexicon diff cannot see: `a` + vowel, `an` + consonant,
doubled determiners, broken fixed collocations, malformed in-law compounds, and
`little` + an adult noun. Suppressing smells already present in the source line,
**12 degraded sites remain**, all in the *find* direction, none of them a label
change:

| sites | what | why it is accepted |
|---|---|---|
| 6 | "My little boy" → "my little son"; "My little girl" → "my little daughter" | Stilted, not wrong. The alternative is dropping `boy`/`girl`, which would leave `son` (35 sites) and `daughter` (46 sites) unreachable as finds — the two most frequent gendered child referents. |
| 3 | "worried sick" → "anxious sick" | A fixed collocation. Shadowing it as a member costs more than it saves: `worried` → `worried sick` then lands at ~9 degree-modified sites ("quite worried sick"). |
| 1 | "The girl at the desk next to me" → "The daughter at the desk…" | `girl`'s second sense, named in the class invariant. One site against 46. |
| 1 | "The boy my daughter's been seeing" → "The son my daughter's been seeing" | Same, one site against 35. |
| 1 | "my **mother-in law**'s house" → "my wife-in law's house" | One hyphen, one space. This is a typo in the library, not a spelling. Adding it as a member would make the pass *manufacture* that spelling as a target, so it is left alone. **Recommend fixing the library line**; that is a `data/synthetic/` edit and out of this ticket's scope. |

12 of 637 rewritten lines ≈ 1.9%. Every one is a fluency cost; none moves a
label, and none is reachable by any mechanical layer, which is the posture DD10
says this ticket now runs under.

---

## 5. F9 — the combined variant, fixed rather than accepted

The plan offered a choice: rotate the combined pass, or record that the combined
check is partial. **Rotated.**

`rewrite_exhaustively` broke a tie at a site with `min(site.rules, key=id)`, so
for a class of *n* members — whose *n*−1 rules all share a `find` — the
whole-file pass exercised one target and never the other *n*−2. It now takes a
`rotation` index, and `dry_run_lint` runs `combined_rotations(rules)` whole-file
passes over it. `combined_rotations` is the largest number of rules sharing one
folded `find`, which is *n*−1 for a class and **1** for a hand-written rule file
— so a rule file's report keeps its old single pass and its old `COMBINED`
label, byte for byte. `rotation=0` is the previous behaviour, so every other
caller is unchanged.

---

## 6. Guards added

In `tests/test_synthetic_expand.py`, mirroring the committed rule-file block:

* every class file loads through all three layers (loading *is* the assertion),
  and the rule count is a function of the committed lists;
* **DD6a fail-closed**, asserted as the property rather than as dictionary
  membership: every referent member normalises to `<third-party>` under layer 2,
  and every non-referent member — weekdays, affect adjectives, and the three
  clinicians `PERSON_CLASSES` deliberately omits — normalises to nothing;
* **DD14**: every member that occurs in the libraries fires as a `find`, and
  every member is some rule's `replace`. 11 of 71 members fire nowhere and that
  is correct — they exist to widen the target vocabulary;
* the in-law shadowing itself, at every rotation, since the referent lists are
  built on it;
* no class rewrite lands a library line on a differently-labelled library's
  line, run **at every rotation** rather than once (F9 again);
* `--dry-run-lint` over the committed libraries for all seven signals.

The committed block runs in ~2 minutes, dominated by the dry run.

One pre-existing test needed a hermeticity fix rather than a behaviour change:
`run_tree` now defaults to an empty classes directory. An arm naming no class
group falls back to `discover_class_groups()` over `data/expansion/classes`, so
from this task onward a directory-pass test built on a tmp tree would silently
have run the shipped classes against a two-rule tmp rule file.

---

## 7. Open items for the pre-registration (Task 8)

1. **The plan's own wording on invariants is wrong for referents.** It says to
   write them against `*_null_attribution` and `*_null_hedged`. For a referent
   class the load-bearing library is `*_null_thirdparty`, where the identity of
   the referent *is* the label; the invariants name that library instead. The
   affect invariant follows the plan and is written against
   `fever_null_attribution` and `fever_null_hedged` rather than
   `filler/emotional.txt`.
2. **`setting` is one class of three members and 6 pairs.** It survives at a
   +1.1% 4-gram ceiling. Whether it earns its arm is a call for Task 8; it is
   cheap to drop and nothing else depends on it.
3. **The `mother-in law` library typo** (§4) wants a one-character fix in
   `data/synthetic/`, in a ticket that is allowed to touch it.
4. **Task 7 is not done here.** The CI step that loads every rule and class file
   and runs `--dry-run-lint` is its own task; the committed-file tests above are
   the unit-level equivalent and will run in the existing unit job.
