# Expansion rule files

One JSON file per signal, named `<signal>.rules.json`, read by
`scripts/synthetic_data/expand.py`. Each file is a list of literal, directional,
whole-word substitutions applied to a *generated* fold tree — never to the
fragment libraries.

## Why they live here and not in `data/synthetic/`

`data/synthetic/` holds the hand-written fragment libraries and the manifest, and
`tests/test_synthetic_recombination.py::test_the_library_tree_contains_nothing_but_libraries_and_the_manifest`
asserts that it holds nothing else. A rule file placed there fails CI, which is
the intended behaviour: the guard exists because a scratch list of synonyms that
sits in the library tree for months gets adopted by a future glob, a future tool,
or a reader who assumes everything there is live.

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
| `id` | yes | unique within the file; names the rule in error messages and in the sidecar's per-rule counts |
| `tier` | yes | `A` (orthography and contraction) or `B` (signal vocabulary). There is no Tier C — see below |
| `find` | yes | the literal phrase to match, whole-word, case-insensitively |
| `replace` | yes | the literal replacement. The source's leading capitalisation is carried onto it, so a sentence opener stays capitalised |
| `weight` | no | relative weight when several rules match the same span. Positive; defaults to `1.0` |
| `invariant` | yes | see below. Must be non-empty |

The key set is **closed** at both levels: an unknown key is an error, not a
comment. A typo in an optional key would otherwise be a silently ignored
instruction, and here the ignored instruction could be the one bounding a
substitution's safety.

## Rules are directional, and both directions are usually needed

`fever → temperature` and `temperature → fever` are two separate rules with two
separate invariants. Neither implies the other, and a symmetric synonym bag is
wrong: reversing a naive `temperature ⇄ fever` set turns the real `fever_true`
line "I checked my temperature and it was high" into "I checked my fever and it
was high".

Flattening a skew normally needs both. `fever` is over-used in
`fever_null_historical` exactly as `temperature` is over-used in `fever_true`, so
one direction alone moves the imbalance rather than removing it.

## What the declared invariant means

**It is the only layer that catches a substitution changing the *referent*
without touching a structural token, and it is read by a human.** The two
mechanical layers below cannot see that "burning up with anger" and "feverish
with anger" are different sentences.

So write what is *preserved*, naming the four things the labels hang on:

- **tense** — "had" and "have" are different claims about when
- **person** — "my fever" and "her fever" are different people's fevers
- **certainty** — "a fever" and "maybe a fever" are different confidence levels
- **polarity** — "a fever" and "no fever" are opposite claims

> "Same thing, different word" is **not** an invariant. It asserts the
> conclusion and records no reasoning, and a reviewer cannot check it.

A good one names the grammatical category and the preserved properties:

> "Both are bare noun phrases naming the same state; changes neither tense,
> person, certainty nor polarity."

Watch the metaphor and attribution libraries hardest. If a phrase only reads
safely inside a clinical frame, put enough of that frame into `find` — which is
why literal phrases are usually longer than single words.

## The three validation layers

All of them run when the file loads, before a single byte is written, and the
error message names the rule, the layer that refused it and why.

1. **The declared invariant** — human-written, human-reviewed. The residual risk.
2. **Structural-token invariance** — the `noise.STRUCTURAL_FROZEN` subsequence
   (negation, person, tense, modality) must be identical between `find` and
   `replace`, compared after contraction normalisation so `haven't → have not` is
   not falsely flagged. A rule that inserts "not", drops "my" or turns "had" into
   "have" fails here.
3. **Signal-lexicon invariance** — via `lint.lexicon_matches`, a rule may not
   change whether its phrase reads as **its own** signal's language, and may not
   introduce **another** signal's language that `find` did not already carry.

## What the format deliberately cannot do

**There is no pattern language, no capture group and no numeric range.** This is
a limit on purpose.

Varying a measurement looks like the safest possible rewrite and is not. The
fever libraries already encode the ~38.0 °C threshold — 36.5 and 36.8 in the
normal-temperature lines, 38.2 and 39.5 in the fever ones — so sweeping 38.4
across 37.6–41.0 walks a `fever_true` line into saying the patient's temperature
was normal. **Neither mechanical layer can see it**: the fever lexicon holds no
numeric terms and `STRUCTURAL_FROZEN` holds no digits, so both `38.4` and `37.6`
pass layers 2 and 3 unchanged.

Numeric variation is therefore a different *kind* of rule — one needing a
per-label-class safe band and a fourth validation layer asserting the band does
not cross the clinical threshold. It arrives as an explicit decision or not at
all. See
`reports/encoder_training/2026-09-03-paraphrase-flip-diagnostic.md`.

Hedge and certainty rewriting is out for a related reason: `sure`, `certain`,
`positive` and `definitely` are in no lexicon and not in `STRUCTURAL_FROZEN`, so
`"I'm pretty sure" → "I'm pretty certain"` passes both mechanical layers while
moving the axis that *defines* `<signal>_null_hedged` against `<signal>_true`.

Tier C (aspect and opener rewrites) is out of scope for the whole pass: it needs
rules scoped to a *library*, and post-processing cannot express that, because
example text carries no character offsets back to its source fragments.

## Running the pass

```
python -m scripts.synthetic_data.expand \
  --in-dir  data/synthetic/generated/folds \
  --out-dir data/synthetic/generated/folds-expanded \
  --rate 0.5
```

Both directories must be under `data/synthetic/generated/`, and neither may be
the other or nested inside it. The pass refuses a tree that already carries an
`expansion` block (expanding twice compounds in a way no rate describes) or a
`noise` block (both passes multiply surface forms, so one experiment carrying
both is unattributable).

The output tree keeps every filename, `example_id`, `split`, `labels` and `meta`,
so it is a drop-in `--data-dir` or `--test-dir` and every expanded example is
paired with its clean original. Each output sidecar gains an `expansion` block
recording the rate, the clean share, the seed, the rule file and its digest,
per-rule application counts, and realised substitutions per hundred words **by
label and by label mode** — the instrument for DD5. The pass cannot read the
label, so a gap in those rows is a fact about the libraries (a class whose lines
carry fewer matchable phrases), not a label-aware pass, and any report quoting
them must say so.
