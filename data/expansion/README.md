# Expansion rule files

One file per signal, named `<signal>.rules.json`, read by
`scripts/synthetic_data/expand.py`. A rule file is the **reviewable artefact**
of the lexical variant expansion pass: the expanded tree it produces is
git-ignored and regenerable, so what a human reads and signs off is this
directory.

## Why the files live here and not in `data/synthetic/`

`data/synthetic/` holds the hand-written fragment libraries and the manifest,
and a test asserts that it holds nothing else. A rule file is not library text.
Putting one there fails CI, which is the intended behaviour.

## The format

```json
{
  "signal": "fever_present",
  "rules": [
    {
      "id": "fever-to-temperature",
      "tier": "B",
      "find": "a fever",
      "replace": "a temperature",
      "weight": 1.0,
      "invariant": "Both are bare noun phrases naming the same state; changes neither tense, person, certainty nor polarity."
    }
  ]
}
```

| key | required | what it is |
|---|---|---|
| `id` | yes | unique within the file; it is what a rejection message and the sidecar's per-rule counts name |
| `tier` | yes | `A` (orthography and contraction) or `B` (signal vocabulary). Tier C is out of scope — see below |
| `find` | yes | a literal phrase, matched whole-word and case-insensitively |
| `replace` | yes | a literal phrase; it inherits the source's leading capitalisation |
| `weight` | no | positive, default 1.0; a share of the draw where several rules match one site |
| `invariant` | yes | see below |

The key set is **closed**: an unknown key is an error, not a comment. A misspelt
`weight` that silently defaulted, or an `invariant` typed as `invariants`, would
remove the one layer of the safety argument that no check can recover.

## Rules are directional

`fever → temperature` and `temperature → fever` are two rules, not one
symmetric pair, and each needs its own invariant and its own review. The fever
libraries need both directions — `fever_null_historical` over-uses the first
exactly as `fever_true` over-uses the second — but neither direction implies the
other. A naive symmetric swap turns "I checked my temperature and it was high"
into "I checked my fever and it was high".

## What the declared invariant means

`invariant` is a written statement that the swap **changes neither tense,
person, certainty nor polarity**. It is human-written and human-reviewed, and it
is the residual risk of the whole pass: two of the three safety layers are
mechanical and run when the file loads, but nothing mechanical catches a
substitution that changes the *referent* without touching a structural token.

The two mechanical layers, so it is clear what the invariant is left holding:

1. **Structural-token invariance.** The sequence of `noise.STRUCTURAL_FROZEN`
   tokens — negation, person, tense, modality — must be identical in `find` and
   `replace`, compared after contraction normalisation so `haven't → have not`
   is not falsely flagged.
2. **Signal-lexicon invariance.** The swap may not change whether the phrase
   reads as its **own** signal's language, and may not introduce **another**
   signal's language that `find` did not carry.

A rule that passes both and is still wrong is entirely possible. Two known
shapes, both recorded from the Task 2 diagnostic:

* **Numbers.** No lexicon holds a numeric term and `STRUCTURAL_FROZEN` holds no
  digits, so `38.4 → 37.6` passes both layers while walking a `fever_true` line
  into saying the temperature was normal. The format is deliberately literal and
  cannot express a numeric range at all; numeric variation is a different rule
  kind, needing a per-label-class safe band and a fourth validation layer.
* **Certainty adjectives.** `sure`, `certain`, `positive` and `definitely` are
  in no lexicon and not in `STRUCTURAL_FROZEN`, so `"I'm pretty sure" → "I'm
  pretty certain"` passes both layers while moving the axis that separates
  `fever_null_hedged` from `fever_true`. Hedge and certainty rewriting is Tier C
  and out of scope for this pass.

## Tiers

| tier | what it swaps | risk |
|---|---|---|
| A | orthography and contraction: `I've ↔ I have`, `haven't ↔ have not` | none — it cannot change which word a token is |
| B | signal vocabulary: `fever ↔ temperature ↔ high temperature` | real, and the layers above are what bound it |

Tier A is **not** the noise pass repeated. `noise.drop_apostrophe` produces
`Ive`, an error; Tier A produces `I have`, a valid alternative form. Only the
second decorrelates register.

Tier C (aspect and opener rewrites) would need a rule scoped to a *library*, and
the example text carries no offsets back to its source fragments — so this
architecture cannot express it, and `expand.py` rejects the tier by name.

## Checking a rule file against the libraries before you run it

```
python -m scripts.synthetic_data.expand --dry-run-lint [--signal fever_present]
```

The two mechanical layers above look at a rule's `find` and `replace` in
isolation. This mode looks at what the rule does to the **committed library
text**, which is where a rule that is individually harmless can still be wrong:
a lexicon match needing an anchor and a modifier can be completed by a swap that
carries neither on its own, so `playing up → aching` passes both layers and then
turns "my back has been playing up" into flank-pain language.

It applies every rule to every library line **unconditionally** — not at
`--rate`, because the worst case is the case worth checking — once per rule and
once with the whole file at play, and diffs the filler-purity and cross-signal
reports against the same two over the originals.

* A **new** hit of either kind fails the run (exit code 1) and names the rule,
  the library, the signal and the line before and after. It fails even for the
  cross-signal report, which ordinarily only reports: an existing hit is a
  labelling decision somebody made, a new one was manufactured by a rule.
* A **removed** hit is printed and is not a failure — but a rule that makes an
  existing hit disappear has changed what that library says, so read it.

The mode reads the libraries and writes nothing: no tree is generated and none
is expanded. With no flags it checks **every** `*.rules.json` in this directory
and **every** `classes/*.classes.json`, which is what CI runs; `--signal`
narrows the first, `--class-groups` the second, and `--rules` drops either side.
Budget minutes rather than seconds: the cost is linear in rule count, and a
swap-class group is hundreds of generated rules.

## Choosing which rules run: `--rules` and `--class-groups`

There are two kinds of rule file and a run selects between them. A
`<signal>.rules.json` is hand-written and belongs to one signal; a
`classes/<group>.classes.json` is a swap class, belongs to no signal, and
expands to every ordered pair of its members. `--rules` picks the kinds and
`--class-groups` picks which groups:

| arm | invocation | what it is |
|---|---|---|
| clean | (no expansion) | the baseline |
| v1 | `--rules signal` | the hand-written rules alone; reproduces the 2026-09-04 anchor byte for byte |
| classes | `--rules classes --class-groups referent,calendar,setting` | the swap classes alone |
| combined | `--rules both --class-groups referent,calendar,setting` | both, concatenated |
| affect | `--rules classes --class-groups affect` | the affect classes, reported separately |

`--rules` defaults to `both` and `--class-groups` defaults to every group with a
file in `--classes-dir`. Two things are errors rather than empty selections: a
named group with no file (a typo, never a state), and a selection that leaves a
signal with **no rules at all** — writing an untouched copy of a tree under a
name that says "expanded" is a silent no-op an arm comparison cannot see. A
missing `<signal>.rules.json` is fatal only when `--rules` asks for one, so a
classes-only arm runs against a signal that has no rule file.

Within a run the two sources are simply concatenated. There is no precedence
between them: `match_sites` prefers the longest `find` and breaks a tie by
weight, so a hand-written `my mum` beats a class's `mum` at the same site for
the same reason one hand-written rule beats another.

## What the sidecar records

The expanded tree's `*.stats.json` grows an `expansion` block, and its
`requested.rule_sources` is a list with **one entry per file** — `path`,
`sha256`, `kind` (`rules` or `classes`), `signal` (null for a class file) and
`count` — beside `requested.class_groups`. One entry per file rather than one
block for "the" rule file is what survives the concatenation: `--rate` and
`--seed` reproduce a tree only in combination with every file that was on disk
at the time, and these files are hand-edited between runs. The training reports
carry the same list through `_expansion_header`.

## Running the pass

```
python -m scripts.synthetic_data.expand \
  --in-dir data/synthetic/generated/<clean tree> \
  --out-dir data/synthetic/generated/<expanded tree> \
  --rate 0.5 \
  --rules both
```

Every layer runs at load time, before a byte is written, so a bad rule is
rejected with its id and the layer that refused it.
