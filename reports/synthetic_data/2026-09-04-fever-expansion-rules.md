# The `fever_present` expansion rule set — 2026-09-04

Task 5 of the lexical variant expansion plan: the authoring of
`data/expansion/fever_present.rules.json`, and the evidence that the rules do
what they were authored to do.

Read alongside `reports/synthetic_data/2026-09-03-token-label-association.md`
(Task 1, the measured skews these rules target),
`reports/encoder_training/2026-09-03-paraphrase-flip-diagnostic.md` (Task 2 and
the decision to proceed) and `data/expansion/README.md` (the rule format and
the three validation layers).

```
rule file: data/expansion/fever_present.rules.json
digest:    31cc52905b63dfc3695e07c77f253d7022713cfefb081a4d04de63411d47b843
rules:     36 -- 15 Tier A, 21 Tier B
```

## The signal

`fever_present`, which is what Task 1 recommended and what the plan is written
against. Task 1 recorded that a literal reading of DD10 ("the pilot is the
top-ranked signal") points at `haematuria_present`, whose top token is the
frozen negation word `no`, and that the deviation is deliberate: fever carries
the largest content-word association in the tree on the one word Tier B exists
to swap. Nothing found while authoring changes that, so no substitution of
signal was needed and the plan's text stands as written.

## What the rules target

Task 1's ranked list, not intuition. Three measured facts do the work:

| fact from Task 1 | rules |
|---|---|
| `fever` on 41/45 `null_historical` and 36/46 `null_thirdparty` lines, against 17/96 `true` and 27/98 `false` | the twelve `fever → temperature` rules |
| `temperature` on 22/96 `true` and 20/98 `false` lines and **0/45** historical | the seven `temperature → fever` rules, plus `a high temperature → a fever` |
| §8's register fault: whole libraries written in one orthographic register | the fifteen Tier A rules |

Every rule fires somewhere in the committed libraries; a rule that matches
nothing is authoring cost for nothing, and two drafted rules (`have not →
haven't`, `do not → don't`) were dropped for exactly that reason after the site
counts came back zero. `tests/test_synthetic_expand.py` asserts the property so
a later library edit that strands a rule shows up as a failure.

### The rule set, with the sites each rule finds in the committed libraries

"fever libs" is the seven hand-written `fever_*` libraries; "declarative" is
`declarative_v1`, the generated library the phrase inventory composes; "all" is
every library in the manifest, which is what an expanded fold tree is built out
of.

| find | replace | tier | fever libs | declarative | all |
|---|---|---|---|---|---|
| `I've` | `I have` | A | 83 | 0 | 291 |
| `I have` | `I've` | A | 16 | 1326 | 1401 |
| `I'm` | `I am` | A | 76 | 0 | 379 |
| `I am` | `I'm` | A | 1 | 0 | 17 |
| `haven't` | `have not` | A | 17 | 0 | 42 |
| `didn't` | `did not` | A | 9 | 0 | 15 |
| `did not` | `didn't` | A | 0 | 0 | 1 |
| `don't` | `do not` | A | 11 | 0 | 60 |
| `Ive` | `I've` | A | 5 | 0 | 35 |
| `im` | `I'm` | A | 23 | 0 | 53 |
| `dont` | `don't` | A | 7 | 0 | 20 |
| `didnt` | `didn't` | A | 1 | 0 | 4 |
| `havent` | `haven't` | A | 6 | 0 | 16 |
| `cant` | `can't` | A | 12 | 0 | 30 |
| `wasnt` | `wasn't` | A | 0 | 0 | 4 |
| `had a fever` | `had a temperature` | B | 35 | 45 | 80 |
| `with a fever` | `with a temperature` | B | 21 | 0 | 21 |
| `have a fever` | `have a temperature` | B | 3 | 0 | 3 |
| `running a fever` | `running a temperature` | B | 6 | 0 | 6 |
| `got a fever` | `got a temperature` | B | 4 | 0 | 4 |
| `get a fever` | `get a temperature` | B | 4 | 0 | 4 |
| `getting a fever` | `getting a temperature` | B | 2 | 0 | 2 |
| `having a fever` | `having a temperature` | B | 2 | 0 | 2 |
| `ran a fever` | `ran a temperature` | B | 2 | 0 | 2 |
| `run a fever` | `run a temperature` | B | 1 | 0 | 1 |
| `developed a fever` | `developed a temperature` | B | 2 | 0 | 2 |
| `any fever` | `any temperature` | B | 1 | 56 | 57 |
| `fevers` | `temperatures` | B | 11 | 0 | 11 |
| `had a temperature` | `had a fever` | B | 10 | 57 | 67 |
| `have a temperature` | `have a fever` | B | 2 | 0 | 2 |
| `running a temperature` | `running a fever` | B | 4 | 0 | 4 |
| `with a temperature` | `with a fever` | B | 3 | 0 | 3 |
| `get a temperature` | `get a fever` | B | 2 | 0 | 2 |
| `run a temperature` | `run a fever` | B | 1 | 0 | 1 |
| `a high temperature` | `a fever` | B | 5 | 99 | 104 |
| `high temperatures` | `fevers` | B | 3 | 0 | 3 |

Tier B is **verb-anchored rather than bare**. There is no `fever → temperature`
rule, and that is instruction 5 in force: the fever libraries use the bare word
figuratively more often than clinically — "hay fever", "cabin fever", "world cup
fever", "fever pitch", "a feverish panic", "working themselves up into a fever"
— and a phrase that only reads safely inside a clinical frame has to carry
enough of that frame to be safe everywhere. The anchored phrases pay for
themselves: **no Tier B rule rewrites a single line of `fever_null_metaphor` or
`fever_null_attribution`**, checked exhaustively rather than at a rate, and that
is a committed test.

### What was deliberately not authored

Each of these is a measured skew the rules leave alone, so the reasons are on
the record rather than left as an omission.

* **`hot` (3-class skew 0.181, the largest in the fever table; 0/45 historical,
  0/46 thirdparty, 32/96 true).** Every candidate swap is unsafe. `hot → warm`
  is an intensity change on a `true` line, not a synonym; and `hot` is the word
  the metaphor library is built out of — "hot under the collar", "hot water",
  "hot air", "hot potato", "blowing hot and cold" — so any rule bare enough to
  reach the decisive lines reaches those too. This is the largest fault in the
  fever vocabulary that this pass cannot touch.
* **`my temperature` (8/98 false, 9/96 true, 0 elsewhere) and `my temp`.** The
  naive swap is the one DD2 names: "my temperature has been normal" becoming
  "my fever has been normal" inverts the label. There is no safe replacement,
  because the possessive frame is what makes the phrase a *measurement* rather
  than a claim.
* **`feverish` (skew 0.011).** Already even. A rule for it is cost for nothing.
* **Numbers.** `38.2 → 37.6` is the hazard Task 2 recorded: the libraries encode
  the ~38.0 threshold in their values, no lexicon holds a numeric term, and the
  rule format cannot express a range at all. Out of scope by construction.
* **Certainty adjectives** (`sure`, `certain`, `definitely`). Task 2's second
  recorded hazard: unfrozen, in no lexicon, and the axis that separates
  `null_hedged` from `true`. Tier C, out of scope.
* **Casing.** `_check_matchable` refuses a swap that only changes case, and it
  is right to: casing is the noise pass's business. So §8's lowercase-library
  fault is only *half* addressed here — Tier A repairs the missing apostrophes
  in those libraries and cannot touch the missing capitals.
* **Apostrophe *dropping*** (`don't → dont`). That is `noise.drop_apostrophe`,
  which produces an error deliberately. Tier A only produces valid forms, so the
  register-repair rules run one way.

## The dry run (instruction 6)

```
Rule dry run against the library lint
=====================================
manifest: data/synthetic/manifest.json
signals:  fever_present
rules:    36, applied unconditionally to 3506 library lines
lines any rule rewrites: 1968

INTRODUCED hits: none.

REMOVED hits: none.

PASS: no rule manufactures a lexicon hit the committed libraries do not have.
```

All three load-time layers pass — loading the file *is* that assertion, since
`load_rules` raises on any of them — and the aggregate check finds no
manufactured cross-signal or filler-purity hit, per rule or with the whole file
at play.

One check the dry run cannot make, added as a committed test instead: no
rewrite lands on a line belonging to a **differently labelled library**. A
rewritten line that is character-for-character another library's line asserts
what its own label denies, and it is not a lexicon fault so nothing in Task 4
would see it. Measured over the whole manifest at the exhaustive rate: zero.

## Before and after (instruction 7)

Task 1's statistic, recomputed over the rule-rewritten libraries. **Every
"after" number here is the exhaustive rewrite** — every site fired — which is
the worst case and not how the pass runs. The rate sweep below is the honest
picture, and it is the finding of this task.

Per-line rates in the seven hand-written fever libraries:

| token | false (98) | attribution (50) | hedged (73) | historical (45) | metaphor (55) | thirdparty (46) | true (96) | 3-class skew |
|---|---|---|---|---|---|---|---|---|
| `fever` **before** | 27 | 0 | 10 | 41 | 5 | 36 | 17 | 0.165 |
| `fever` **after** | 18 | 0 | 9 | 14 | 5 | 19 | 15 | **0.027** |
| `temperature` **before** | 20 | 0 | 7 | 0 | 1 | 7 | 22 | 0.173 |
| `temperature` **after** | 28 | 0 | 8 | 27 | 1 | 24 | 23 | **0.063** |
| `hot` before = after | 23 | 16 | 13 | 0 | 12 | 0 | 32 | 0.181 |
| `warm` before = after | 2 | 4 | 17 | 0 | 1 | 0 | 10 | 0.084 |
| `feverish` before = after | 4 | 0 | 4 | 1 | 2 | 1 | 3 | 0.011 |

`temperature` on **0/45 historical lines becomes 27/45**, which is the specific
association Task 1 named — "temperature ⇒ decisive, fever ⇒ displaced" — being
removed rather than reduced. And `hot`, the largest single skew in the table, is
untouched, for the reasons above.

### The finding: the rate is not a free parameter, and 1.0 is wrong

Running every rule everywhere does not flatten the skew. It **inverts** it. The
statistic that matters is the gap between the *decisive* libraries (`true` +
`false`) and the *displaced* ones (`null_historical` + `null_thirdparty`) — the
contrast Task 1 said a head could read the label off. Below, `p` is the
probability that any one match site fires, which is `(1 - clean_share) × rate`;
each row is the mean of 60 draws.

|  p | fever decisive | fever displaced | fever gap | temp decisive | temp displaced | temp gap |
|---|---|---|---|---|---|---|
| 0.000 | 0.227 | 0.846 | −0.619 | 0.216 | 0.077 | **+0.140** |
| 0.250 | 0.214 | 0.730 | −0.517 | 0.228 | 0.193 | **+0.035** |
| 0.375 | 0.206 | 0.674 | −0.468 | 0.234 | 0.249 | **−0.015** |
| 0.500 | 0.200 | 0.607 | −0.406 | 0.238 | 0.316 | −0.079 |
| 0.625 | 0.189 | 0.547 | −0.357 | 0.247 | 0.376 | −0.130 |
| 0.750 | 0.182 | 0.485 | −0.303 | 0.253 | 0.438 | −0.185 |
| 1.000 | 0.170 | 0.363 | −0.193 | 0.263 | 0.560 | −0.298 |

Two things to read off it:

1. **`temperature`'s association is fully removable, and it crosses zero at
   p ≈ 0.30.** Past that the rules have not neutralised the cue, they have
   reversed its sign — by p = 1 `temperature` is a *displaced*-vocabulary word
   as strongly as it was ever a decisive one. The `DEFAULT_CLEAN_SHARE`
   docstring anticipates this ("a tree in which every `fever` became a
   `temperature` would have swapped one perfect association for another"); this
   is that sentence measured.
2. **`fever`'s association is not removable by this pass at any rate.** It falls
   from −0.619 to −0.193 at p = 1 and no further, because closing it needs
   *more* fever vocabulary in the decisive libraries, and those lines mostly say
   it with words Tier B cannot touch ("burning up", "boiling", "hot", a
   thermometer reading). The remaining gap is a property of how the libraries
   are written, and the fix for it is the library edit Task 1 named as the
   cheaper alternative, not a rule.

**Recommended operating point for Task 6: `--rate 0.4` at the default
`--clean-share 0.25`**, giving p = 0.30 — the point that zeroes the
`temperature` cue while taking about a fifth off the `fever` one. This is a
recommendation from the library statistics, not a tuned result; Task 6 measures
flip rate and decisive accuracy, and if it sweeps the rate this table says which
direction the interesting range lies in.

### What happened to Task 1's headline 0.911

Task 1's Reading B ranked signals on the widest gap *within* the `null`
sub-classes, and `fever` at 0.911 was the largest content-word association in
the tree. That statistic moves much less than the decisive/displaced gap does
(mean of 40 draws):

| p | `fever` within-null | `temperature` within-null |
|---|---|---|
| 0.000 | 0.911 | 0.152 |
| 0.250 | 0.771 | 0.239 |
| 0.500 | 0.635 | 0.348 |
| 0.750 | 0.517 | 0.471 |
| 1.000 | 0.413 | 0.600 |

That floor is structural, not a weakness of the rules. The minimum of the
within-null spread is `fever_null_attribution`, which uses **no** fever
vocabulary at all — 0/50 for `fever` and 0/50 for `temperature`, because its
lines attribute heat to the menopause, a thyroid, sertraline or a hot kitchen —
and `fever_null_metaphor` is nearly as empty of it. A substitution pass can only
move words that are already there; it cannot put fever vocabulary into a library
that never mentions it. Closing that gap is a library edit, which is what Task 1
said in the first place.

So `fever`'s within-null spread is not the statistic to judge these rules by,
and the report says so before the numbers rather than after them. The
decisive/displaced table above is, because that is the contrast a head would
have to read the label off.

### One skew the rules manufacture, and the rule that was added to hold it down

`declarative_v1` — 1000 generated lines, and the library the site counts above
show dominating the tree — is **excluded from Task 1's instrument** ("generated
libraries carry labels per line, not per library"). It carries a fever
vocabulary fault of its own, in the exclusive-token shape §8 records: the
negative frame says "not had **any fever**" and "not a **high temperature**",
the positive frame says "had **a fever**" and "had **a temperature**", and
`a fever` appears on 72 of 240 fever-positive lines and **0 of 196
fever-negative** ones. This was found while authoring and is reported here
because it is a fault in the phrase inventory that no committed check looks at;
it is not this ticket's to fix.

It matters here because a first draft of the rule set rewrote the negative
frame's `a (high) temperature` into `a fever` while leaving its `any fever`
alone, which **manufactured** a true/false vocabulary gap where the generated
library had almost none: |true − false| in the `fever` rate went from 0.014 to
0.142 at p = 0.5 and 0.218 at p = 1. That is the DD5 hazard arriving from a
direction DD5 does not close — the pass is label-blind, but a rule set can still
be *unbalanced across the frames that carry the labels*.

Adding `any fever → any temperature` (57 sites, 56 of them in `declarative_v1`)
holds it down:

| p | fever true | fever false | \|true − false\| | (first draft) |
|---|---|---|---|---|
| 0.000 | 0.300 | 0.286 | 0.014 | 0.014 |
| 0.250 | 0.336 | 0.310 | 0.026 | 0.040 |
| 0.500 | 0.377 | 0.328 | 0.049 | 0.142 |
| 1.000 | 0.450 | 0.383 | 0.067 | 0.218 |

The residual is small and grows with the rate, which is a third independent
argument for the low rate recommended above. It is telemetry Task 6 should
watch: the sidecar's by-label substitution density is the live version of this
table.

## What this task does not establish

* **That any of it helps.** These are library statistics. Whether a trained head
  reads the association is Task 2's question (answered "maybe", 15.4% flip rate,
  interval [2.6%, 33.3%]) and Task 6's (unanswered).
* **That the tree gets bigger.** It does not. The expanded tree holds exactly as
  many examples as the clean one, paired `example_id` for `example_id`. One line
  written twelve ways is one idea.
* **That the invariants are right.** Thirty-six written invariants are the
  residual risk of the whole pass, and no test reads one. The committed test
  asserts only that each is present and long enough not to be a placeholder.
  What stands behind them is review.
* **That the libraries' register is decorrelated.** Tier A repairs apostrophes;
  the lowercase-library fault §8 records is also a *casing* fault, and casing
  belongs to the noise pass. Half the recorded fault is addressed here.
