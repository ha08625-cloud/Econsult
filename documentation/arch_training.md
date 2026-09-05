# Encoder Training Data (Synthetic Generation)

**LLM INSTRUCTIONS:** How the encoder's synthetic training data is built and why
it is built that way. It stays at the level of design decisions, invariants and
data flow; the code is the authority on mechanics and the files in
`reports/encoder_training/` are the authority on every measured number.

Sections 1 to 11 describe the system as it is. **Section 12 is the forward
plan** — each subsection states whether it is built.

---

## Scope

Turning hand-written sentence fragments into a training dataset for the encoder.
Everything here is **offline tooling**. Nothing in this document runs in the
live application, and `app/` never imports any of it.

**Key files:** `scripts/synthetic_data/` (the generator, the lint and the noise
pass), `data/synthetic/` (the fragment libraries),
`tests/test_synthetic_recombination.py`.

**Related:** `arch_encoder_training.md` covers the offline tooling that trains
and evaluates heads against these datasets, and is the document to read for what
any number it produces is worth. `arch_encoder.md` covers the encoder once it is
trained and running. The split between this document and
`arch_encoder_training.md` is at the file boundary: what decides the contents of
a *dataset* is here, what decides the meaning of a *number computed from one* is
there.

---

## 1. Why we generate data at all

The encoder reads a patient's free text and answers one clinical question per
signal — "does this text say the patient has a fever?" — with `true`, `false` or
`null` (not mentioned). Training that needs thousands of labelled texts. We do
not have thousands of real e-consult submissions, and real patient text would
need governance work first, so we write a few hundred fragments by hand and
recombine them.

Everything trained and measured so far covers seven signals of the
`urinary_symptoms` condition. It is a proof of concept for the *pipeline*, not
clinical-grade training data — section 9.

---

## 2. Label first, then text

The generator never writes a sentence and then works out its label. It decides
the label first, then draws only from a pool sorted by hand to match it. Text
can therefore never influence the label, and that invariant is what every other
safety argument in this document rests on. The one step that edits text after
the label is fixed is the noise pass (12.6), which is why it carries a frozen
lexicon.

---

## 3. The fragment libraries

`data/synthetic/` holds plain text files, one fragment per line — a single
clause or sentence a patient might write. The layout is by what a library says
and which condition it belongs to:

```
data/synthetic/
  manifest.json
  filler/                       condition-agnostic, reusable by any condition
  conditions/uti/
    symptoms/<signal>/          the seven signals' libraries
    filler/                     UTI-specific filler
  generated/                    output, git-ignored
```

Nothing in the code keys off the directory — the manifest gives every path
explicitly, so the layout is for humans: "which files carry a dysuria label"
should be answerable by looking. The condition layer answers the same question
one level up, so a second ruleset gets `conditions/<name>/` and inherits the
top-level filler unchanged.

The two filler folders split on **language, not usage**. `tangents`,
`justifiers` and `emotional` contain no condition-specific vocabulary at all, so
they sit at the top. `uti_speculation` and `expectations_uti` are largely
UTI-specific and sit under the condition; they may mention urine infections and
antibiotics but deliberately name no time frame, so they do not collide with the
`recent_uti` libraries.

The filler libraries are verified silent about **all seven** signals by the lint
(section 8), in CI, with no baselined exceptions.

**The manifest is the inventory, not this document.** Every library's path,
signal, polarity and sub-class are in `data/synthetic/manifest.json`, and
`--lint` prints the per-library fragment counts and split coverage (section 8).
What follows is the shape of the collection, which is a design fact and does not
move when a library grows.

| signal | libraries | hard-case axes it carries |
|---|---|---|
| `fever` | 7 | hedged, third-party, historical, metaphor, attribution |
| `nocturia` | 7 | hedged, third-party, historical, metaphor, attribution |
| `urinary_frequency` | 7 | hedged, third-party, historical, metaphor, **adjacent** |
| `dysuria` | 6 | hedged, third-party, historical, metaphor |
| `recent_uti` | 6 | hedged, third-party, historical, **adjacent** |
| `flank_pain` | 5 | hedged, third-party, historical |
| `haematuria` | 5 | hedged, third-party, historical |

Each signal carries a `_true` and a `_false` library alongside those. Six filler
libraries complete the set: `tangents` (irrelevant chat), `justifiers` (why they
need an appointment), `emotional` (worry and feelings) and `expectations` (what
they want to happen, in vocabulary any condition's patient could use) at the top
level, plus `uti_speculation` (self-diagnosis) and `expectations_uti` (the same
asks in urinary-tract vocabulary) under the condition.

**Why the axis sets differ is the interesting part**, and each difference is a
decision: `attribution` exists where a patient can plausibly name a non-clinical
cause for the surface facts (heat, night waking) and is *wrong* for
`urinary_frequency`, whose policy makes cause irrelevant (section 9);
`adjacent` exists where a neighbouring complaint is current, first-person and
clinical while saying nothing about this question — a weak stream for frequency,
a non-urinary infection for `recent_uti`; `metaphor` exists only where the
signal's vocabulary has a live non-clinical use, which "blood in the urine" and
"pain in the side" largely do not.

Every symptom is sized; none is still a seed batch. Every decisive and
confounder library sits in or above the 40–50 band, the smallest at 38.

### The null axes, and why they are separate files

The `null` libraries are the hard cases: they carry the signal's vocabulary and
none of them means "this patient has the symptom right now". A model that has
only seen clear positives and negatives marks "my son has a fever" as positive.
They are separate files rather than one pile so that per-sub-class performance
can be measured. Each displaces the claim along a different axis:

| Axis | What is displaced |
|---|---|
| `hedged` | certainty — the patient does not know |
| `thirdparty` | person — it is someone else |
| `historical` | time — it was last month |
| `metaphor` | meaning — the word is not being used clinically |
| `attribution` | cause — the surface facts hold, and the patient names a cause that makes the answer `null` |
| `adjacent` | referent — the complaint is current, first-person and clinical, and is simply not about this question |

`attribution` and `adjacent` are the hardest, and for the same structural
reason: every surface cue points the wrong way. No hedge, no past tense, no
third party — so a model that learned "first person + present tense + topic
vocabulary ⇒ positive" scores well on the other axes and fails these completely.

### Cross-signal silence

A fever run keeps only fragments whose `signal_key` is `fever_present`, plus
filler and — since companions — other signals' fragments that have **declared**
themselves `null` on fever (section 4). Everything else is dropped. Treating
another signal's fragment as filler would silently assert that it says nothing
about fever, which is exactly the guarantee that has to be written down before
it can be relied on.

Both halves of that guarantee now exist: the lint *measures* what every library
says about every foreign signal (section 8) and the manifest lets a library
*declare* it (section 4). What is still missing is per-**line** expression —
`fragment_type` records the polarity of a library's own signal only, so a
library whose lines disagree about a foreign signal cannot be declared at all.
Two known cases, recorded so they are not rediscovered as mysteries:

* Three `flank_pain_false` lines resolve the flank question by contrasting it
  with a urinary one ("it's just uncomfortable when I wee"), asserting dysuria in
  a library that would otherwise be declared silent on it. The pair stays
  **undeclared**, which costs a smaller companion pool rather than a wrong label.
  Rewriting the lines would recover the pool and is a labelling decision that
  moves generated data.
* `filler` carries "blood test" and "blood pressure tablets", and `tangents`
  carries sleep-disturbance lines. Both were resolved as *lexicon too broad*
  rather than as leaks — blood in a vein is not blood in urine, a bad night's
  sleep is not nocturia — and both are in the lint's trap test so a future
  lexicon cannot quietly re-flag them.

**Filler must contain no signal language whatsoever, for any signal.** A filler
fragment can be paired with any label, so fever language in filler makes a "no
fever mentioned" label a lie. That is the one cross-signal claim the lint
enforces as a failure rather than reporting.

### Cluster markers

Some lines start with a tag in square brackets:

```
[c01] My son has had a fever on and off for the past few days
[c01] My daughter's been off school with a temperature up and down for the past few days
```

Those two lines are the same idea written twice. The generator strips the marker
before use — it never reaches a training example — and section 6 uses it to keep
siblings in the same split.

Only the `fever_null` and `dysuria_null` libraries carry markers, because only
they were written in a way that produced systematic near-duplicates. Everywhere
else **effective n is claimed to equal fragment count**, and that claim is not a
measurement.

**A marker is a claim, and a wrong one costs both ways.** Grouping lines that
are not the same idea understates effective n; leaving genuine twins untagged
lets them land on opposite sides of the split, which is the leakage the
mechanism exists to prevent. Growing a library means new *ideas*, not new twins.
The cross-split near-duplicate report (section 8) is the only feedback loop on
this: on the committed tree it runs at 1.7–2.3% for four signals and 7.0–7.4%
for `flank_pain` and `recent_uti`, which are the two most worth re-reading by
hand. The comparison flatters the untagged signals, since `fever` and `dysuria`
appear only as residuals. `recent_uti` reads differently again: every fragment
it holds has to place an infection in time, so all six libraries share the
infection nouns *and* the time markers, and high character similarity between
genuinely distinct ideas is expected there.

**Tagging is asymmetric and the asymmetry is what makes cross-signal rankings
unsafe.** Tagging only ever *reduces* effective n — correctly — so an untagged
library's effective n is an upper bound and every interval computed on it is
narrower than the truth. A signal tagged honestly is penalised; one with no
markers is flattered. The prediction that followed from this was **wrong**: the
2026-08-16 sweep put fully-tagged `dysuria` second of six and the two weakest
signals were both untagged. The asymmetry is real; it is not what separates
these six signals. Tagging the five untagged sets is still outstanding (12.8).

---

## 4. The manifest

`data/synthetic/manifest.json` is where a library's *meaning* lives. Per
library it records the signal, the polarity (`fragment_type`), the hard-case
sub-class, and — the largest part of the file by a wide margin — the 284
`null_on` declarations about the other six signals, 42 of which carry a prose
note (every `policy` pair must; an `absent` pair may). None of that is expressible in a path, and the declarations are the whole
of the multi-symptom safety mechanism.

**Discovery is the manifest, never a glob**, and that is a separate decision
from what the manifest carries. Under a folder scan the failure modes go quiet
in both directions: any `.txt` that lands in the tree becomes training text on
the next run, and renaming `dysuria_null_hedged.txt` silently relabels a library
rather than failing. With the manifest, a file on disk that nobody declared
fails CI and a declared file that is missing stops the run — the same posture as
the four merge guards in section 8, and for the same reason: these faults are
invisible in a diff.

### Two library formats

A library entry carries an optional `format`: `text` (the default, and what all
49 hand-written libraries use) or `jsonl`. The formats differ in **where a
line's label comes from**, and nowhere else — a JSONL library gets its
`fragment_id`, its namespaced cluster and its split from the same functions a
text library does, because a generated library is a committed build artefact and
the split machinery must not be able to tell it apart.

* **`text`** — one fragment per line, optionally cluster-marked. The line's
  label vector is *derived*: the library's own signal takes its value from
  `fragment_type`, every signal it declares `null_on` is `null`, and every other
  signal is undeclared.
* **`jsonl`** — one JSON object per line (`text`, `labels`, `cluster`, optional
  `meta`), and `labels` **is** the vector. `true`/`false` assert, `null` declares
  the line silent, and a signal the object omits is undeclared, exactly as in
  `null_on`. Such a library must declare `fragment_type: "declarative"` and must
  declare neither `signal_key` nor `null_on`: both are library-level statements
  about every line, and these lines each state it for themselves. Two sources for
  one value is one that can disagree with itself.

Both end up in the same `Fragment.labels` field, so nothing downstream has to
know which format a fragment came from; `Fragment.value_for(signal)` returns
`True`/`False`/`None` or the `UNDECLARED` sentinel, and that fourth state is
deliberately not `None` (section 7). `build_pools` reads exactly that, which is
what makes one code path serve both formats: for a text library the vector and
the `(signal_key, fragment_type)` pair are the same fact, so every pool comes out
with the same members it always had. A JSONL line's `meta` is carried onto the
fragment too, because a generated library records its frame there and the stats
sidecar's `declarative.frame_by_label_mode` is the check that frame identity does
not correlate with the label.

**No migration is planned.** A text library's `fragment_id` hashes its text and
its split hashes its cluster key, so re-expressing it as JSONL would move every
dataset ever generated, and its vector is already derivable from what the
manifest states.

### `null_on`: which foreign signals a library is `null` on

For every (library, foreign signal) pair, the library either declares that the
correct label for that signal is `null` on **every** one of its lines, or says
nothing:

| state | meaning | eligible as a companion in that signal's run? |
|---|---|---|
| **declared `null_on`** | `null` on every line, whether or not the line mentions the signal | yes |
| **undeclared** | nobody has decided | **no** |

A library's *own* signal comes from `fragment_type` and may not be declared:
two sources for one value is one that can disagree with itself. There is
consequently **no cross-signal `true`/`false` state** — the pairs that would
want one are per-line facts over libraries whose lines disagree, and per-line
label vectors (12.3) are what would express them.

**Undeclared is the default, and it is not the same as silence.** A closed-world
default would mean adding an eighth signal silently asserted that all 49
existing libraries were silent about it. There is no wildcard and no
manifest-level block either: a shorthand for asserting 250 pairs in bulk is a
shorthand for asserting them without reading them. The lint makes the typing
cheap instead (section 8).

```json
"null_on": {
  "fever_present": {"basis": "absent"},
  "recent_uti_present": {
    "basis": "policy",
    "note": "Names an infection but places none inside the 30-day window ..."
  }
}
```

Keyed by signal rather than a list, so a repeated signal is a duplicate JSON key
inside one object — which the manifest's existing duplicate-key test already
walks the whole file looking for.

**The two bases, and only one of them is checkable.** This is the load-bearing
distinction:

* **`absent`** — the library never mentions the signal. A lexicon can check
  this, so **a hit against an `absent` pair is a failure**, baselined per pair in
  `ABSENT_PAIR_BASELINE`. Filler purity is this same check on the libraries that
  always had to satisfy it.
* **`policy`** — the library *does* talk about the signal and the correct label
  is `null` anyway (`uti_speculation` on `recent_uti_present` is the worked case,
  section 9). **No lexicon can check this**, so the entry requires a `note`
  giving the rule, the lint prints every `policy` pair with its matched-line
  count, and the set is pinned in `POLICY_PAIRS` so adding one is a deliberate
  edit rather than a line in a thousand-line diff.

**Say the limit plainly.** The central safety guarantee of the multi-symptom
work is machine-checked for `absent` pairs and hand-judged for `policy` pairs,
and the lexicons doing the checking catch 59%–91% of their own *positive*
libraries (section 8). Even the checked half is a lower bound.

**What the declaration pass decided.** 300 pairs: **260 `absent`, 24 `policy`,
16 deliberately undeclared**, with a test asserting no pair is in an
unconsidered state. Twenty of the `policy` pairs are on `recent_uti_present`,
whose lexicon deliberately matches infection nouns only beside a recency marker,
so every historical, third-party or non-urinary infection lands exactly where a
`policy` note is for. **Fourteen of the 16 undeclared pairs are the nocturia /
urinary-frequency pair in both directions** — "up three times in the night for a
wee" genuinely asserts both, per line — and the other two are the
`dysuria_true` and `flank_pain_false` single lines above. The 28 baselined
`absent` hits are all lexicon over-reach in three families: a flushed toilet
where the fever lexicon wants a flushed face, a counting word qualifying pain or
colour rather than voiding, and a pain word belonging to a different clause.
Narrowing the lexicons to clear them would cost real recall.

### What the declaration does to generation

* **Filler is filtered rather than trusted.** A filler library reaches a
  non-decisive slot only if it has declared the run's signal. Filler is silent on
  all seven today, so the filter removes nothing and every generated byte is
  unchanged — pinned by the golden-digest test. It stops being free the moment a
  filler library goes undeclared on some signal, and an undeclared one is
  **excluded and named**: the CLI warns, the fragment-count ceiling drops by one
  (section 5), and if fewer than two filler libraries survive, generation refuses
  to start with a `PoolError` naming the library, the signal and the ways to
  resolve it. A pool error whose real cause is three lines of missing JSON must
  not read as a library-size problem.
* **Other signals' fragments are collected instead of dropped**, into the
  companion pool `--companion-share` draws from (section 5).

---

## 5. How one example is built

An example is a handful of fragments joined with a space. How many is drawn from
a weighted mix — by default 50% two-fragment and 50% three-fragment, adjustable
with `--fragment-counts`.

**The mix is identical for every label class, and that is the whole safety
argument.** If `true` examples were longer, the model could learn "long text
means fever" and score well having learned nothing. The count is drawn from one
distribution that never sees the label, and the sidecar reports realised counts
*per label* so the property is checked every run rather than assumed. (Fragment
*length* is a different matter and is not solved — section 9.)

Four kinds of example. Each holds **exactly one decisive fragment** (none, for a
structural null); every other slot is filler, or — at `--companion-share` above
zero — a **companion**, another signal's clinical language declared `null` on
this signal:

| Kind | What it is made of | Label |
|---|---|---|
| `true` | 1 positive fragment + N−1 filler/companion | `true` |
| `false` | 1 negative fragment + N−1 filler/companion | `false` |
| `null_ambiguous` | 1 hard-case fragment + N−1 filler/companion | `null` |
| `null_structural` | 1 filler + N−1 filler/companion | `null` |

Default mix 15% `true`, 25% `false`, 60% `null`, the `null` half splitting 50/50
between the two kinds. All adjustable from the command line.

**Why the two kinds of `null` matter.** A structural null contains no fever
words at all and is trivially easy; an ambiguous one is full of them and still
means `null`. Only structural nulls would teach the trivial rule and fall apart
the first time a patient mentions their child's temperature. The 50/50 default
is the single most consequential setting in the generator.

**Only one decisive fragment, however long the example.** Two positives double
the evidence for one claim and teach nothing new. The consequence is that the
decisive fragment's share of the text shrinks as the count rises — which is the
point, and also why "more is better" is false: past some count each example
still carries one supervised claim, just buried in more noise.

**Fillers within one example always come from different libraries**, or three
`tangents` lines read as three consecutive tangents in one voice. That puts a
hard ceiling on the fragment count: **eligible filler libraries + signals with
at least one eligible companion library** — six plus six today. The generator
checks this up front and refuses to start if the requested maximum exceeds it,
naming both halves. The ceiling counts *sources*, not lines, so splitting one
filler library raises it exactly as writing a new one does (which is what the
`expectations.txt` split did), and an undeclared filler library lowers it.

**The decisive fragment can appear in any position** — the fragments are
shuffled, so "the fever claim is the opening clause" is not learnable.

**Fragments are used verbatim.** Original spelling, casing, typos and
contractions are preserved; the only edit is a full stop where one is missing.
The live encoder receives raw patient text, so cleaning it here would train the
model on a tidier world than the one it will meet. (12.6's noise pass damages
finished text afterwards, and is a separate script.)

### Companions: other symptoms' language in a `null` example

Every `null` example generated before companions paired the absence of the
signal's language with bland, non-clinical filler. No head had ever seen a
message dense with clinical language about another symptom whose correct answer
was still `null`, so **"clinical-sounding text ⇒ not `null`"** was a perfect rule
on our data and a catastrophic one on real text, where the median submission
asserts something about two of the six signals. That failure was measured, not
argued (section 9), and companions are the fix — measured in turn on 2026-08-19
(section 10).

`--companion-share P` is the share of an example's non-decisive slots carrying
another signal's fragment instead of filler. Eligibility is that library's
`null_on` declaration for *this* run's signal and nothing else.

Three properties do the safety work, and the first is easiest to get subtly
wrong:

* **The companion count is drawn over N−1 slots in every label mode**, including
  `null_structural`, whose remaining slot is always filler. A structural null has
  one *more* non-decisive slot than every other mode at the same count, so an
  independent per-slot draw would give structural nulls twice the companions —
  making companion count a proxy for the label pointing the wrong way, *more
  clinical text ⇒ more likely `null`*, which a model can learn without reading
  anything. The bounds are a function of the fragment count and pool sizes alone
  and the draw never sees the label. `companions.count_by_label_mode` in the
  sidecar is the leak detector, and **a run whose rows disagree is void rather
  than reinterpretable**.
* **Which companion is drawn is equally blind** — signal uniformly, then
  library, then fragment. Otherwise companions would skew `true` inside `true`
  examples and "clinical language ⇒ not `null`" would have been replaced by
  "clinical language ⇒ `true`", the same failure wearing a different hat.
* **At most one fragment per signal per example**, and the primary signal's own
  libraries are never eligible as companions: it enters through the decisive slot
  alone, or `null_structural` and `null_ambiguous` collapse into each other.

Companions come from the same split as the example, free of charge — `build_pools`
is split-restricted and the fold hash knows nothing about signals. Stated anyway,
because a fever *test* example holding a dysuria *train* fragment is training
text inside the test set.

**The default is 0.0, and at 0.0 the path is skipped rather than merely quiet.**
No count is drawn, no randomness consumed, and the fragments chosen for a given
seed are exactly the pre-companion ones — pinned by a golden digest.

**`null_structural` at P > 0** keeps its name because it keeps its defining
property, no fragment decisive for this signal, and stops being trivially easy,
which is the point. It also mostly stops being filler-only, so the merge's
deduplication (section 7) fires far less often: measured at `P = 0.5`, the merged
six-signal tree is **1.21×** the size of the `P = 0` one. That is this feature's
compute bill, accepted rather than worked around.

---

## 6. Splitting into train / validation / test

By default fragments are divided ~70/15/15. Fold mode is the opt-in alternative.

The split happens at the **fragment** level, before any example is built: a
fragment assigned to validation is never used in a training example. Splitting
finished examples would put the same fragment on both sides and the validation
score would partly measure memorisation. The assignment is a hash of the
fragment's own text, so adding fragments never moves existing ones — and
fragments sharing a cluster marker are hashed **as a group**, so twins cannot
land on opposite sides (section 3).

### Fold mode

`--folds K --fold i` replaces the bands with K rotations: bucket `i` is test,
`i+1` is validation, the rest train. At `K=5` that is 60/20/20, and **every
cluster is a test cluster in exactly one fold**, so running all five and pooling
predictions makes the whole library the effective test set rather than the
2-to-6-cluster slices a single split leaves. That is what takes a per-sub-class
interval from roughly ±30 points to roughly ±11 — uncertainty falls as 1/√n, and
folds add no new *ideas* at all, so section 9 applies in full.

Three things to know before using it:

**It is opt-in and the default is untouched.** A fold's train share is 60% not
70%, so fold numbers are not comparable to default-band numbers.

**Fold *i*'s validation clusters are fold *i+1*'s test clusters.** Within one
fold that is not leakage; a result *pooled* across folds carries a little
optimism, because each fold's decision margin was tuned on a sibling fold's test
clusters. Nested cross-validation would remove it and is not worth the cost.
**Any report using fold mode has to say so.**

**There is a salt, and it is `"0"`.** It lives in `DEFAULT_FOLD_SALT` and
`test_the_agreed_salt_still_clears_the_real_libraries` re-checks it against the
live manifest every CI run, so a library that grows past the point where the
pinned salt works fails there rather than halfway through a five-fold training
run. The salt exists because the empty-cell guard (section 10) covers the *whole*
manifest, so an unrelated library that fails to populate all K buckets blocks
every run. Which library binds tracks cluster count almost exactly, so the salt
is a proxy for the smallest library measured in *clusters*; the way to loosen it
is to write new ideas there. `--find-fold-salt` searches; do not instead "fix" it
by editing whichever library is currently binding.

Passing the guard remains a floor, not a health signal: seven clusters over five
buckets means some fold's test cell holds exactly one idea.

---

## 7. Output

One JSON object per line:

```json
{
  "example_id": "train-000042",
  "split": "train",
  "text": "I had a high temperature. My neighbour's dealing with some family stuff.",
  "labels": {"fever_present": true},
  "meta": {"label_mode": "true", "fragment_ids": ["fever_true:a1b2c3d4", "tangents:e5f6a7b8"], ...}
}
```

**A missing key and a `null` value mean different things.** `"fever_present":
null` means "we looked, and the text does not say". A *missing* key means "this
dataset says nothing about fever, mask it when scoring". Confusing the two when
datasets are merged would teach every head to answer "not mentioned" to every
question it was not specifically trained on — invisible until the model is
mysteriously bad.

**`--emit-signals all` is where that distinction stops being theoretical.** By
default a record carries one key. At `all` it carries a key for every signal the
example's fragments *jointly* have a known status for:

| the fragments' states on S | result |
|---|---|
| any fragment is **undeclared** on S | **no key for S** |
| exactly one fragment asserts S (its own signal) | key = that fragment's value |
| every fragment is `null_on` S | key = `null` |
| two fragments would assert S | unreachable, and raises if reached |

The first row is read over the whole example, not per fragment: one undeclared
fragment masks the signal even where another asserts it outright, which is the
honest answer rather than a limitation. The last row is a raise rather than a
resolution — two assertions are either redundant or contradictory, and silently
keeping one is how a dataset acquires a wrong label. **Nothing here reads text**:
every contribution is fixed before the fragment is drawn, from `fragment_type`
and `null_on`, so section 2's invariant is untouched.

**It is built and not measured** (12.2): no trained arm uses it, and
`merge-folds` refuses a multi-key tree, so an `--emit-signals all` tree cannot
currently reach joint training.

**How many fragments an example holds is not stored** — it is
`len(meta.fragment_ids)`, and a second copy of one number is one more thing that
can disagree with itself. **`meta.filler_only` is the one derived fact that is**
stored: before companions it was the same statement as `label_mode ==
"null_structural"` and now it is not, and both the merge's deduplication and the
reports need it. It is written at assembly rather than re-derived, because
re-deriving needs the manifest and would go quietly wrong the moment a library
was edited.

### The stats sidecar

Every run writes a `.stats.json` beside the dataset: what was asked for, what
came out, pool sizes, text length per label. It is the first thing to look at
when a run seems wrong, and four blocks exist specifically to police the safety
arguments above:

* `fragment_counts.by_label` / `.by_label_mode` and `token_counts.by_fragment_count`
  — the realised count mix per label, and length grouped by count. If one label
  skews long, fragment count has become a proxy for the label. Nothing downstream
  would surface it: it presents as a fine validation score and a model that does
  not transfer.
* `companions.count_by_label_mode` — **the rows must agree** (section 5), plus
  `label_mix_by_label` for the companions' own polarity, `signals` for which were
  drawn, and `requested.companion_share`.
* `realised.labels_by_signal` — the realised label prior of every head the run
  emits, plus an `absent` count. The decision rule's objective is stated relative
  to argmax (`arch_encoder_training.md` section 8), so a head's prior moves the
  constraint and not only the head, and a head supervised on 4% of the tree looks
  identical to one supervised on all of it once three label counts are normalised.
* `fragments` — for every fragment in the split: `library`, `cluster_key`,
  `fragment_type`, `signal_key`, `signals`, `labels`, `subclass`, `split`.
  **`signals` is the field to read, not `signal_key`.** It is every signal the
  fragment decides — what it asserts, plus its own signal where it has one, so
  an *ambiguous* fragment still counts as its signal's. For a text fragment that
  is exactly `[signal_key]`; a declarative line decides two to four at once and
  has no scalar key, so `signal_key` is `null` on it rather than being made to
  pick one of four. `labels` is the whole per-line vector, including the signals
  the line declares itself silent on, which `signals` cannot express. Without
  this block **nothing in a generated dataset says which fragments are the same
  idea**, and computing effective sample size needs exactly that. Re-reading the libraries at training
  time is rejected because it fails *silently*: edit a library after generating
  and the cluster grouping is quietly wrong, producing confidence intervals that
  are too narrow with nothing raised anywhere.

`folds`, `fold_index` and `split_salt` record the fold configuration, without
which a dataset is uninterpretable — `test` means different clusters under every
triple and nothing in the JSONL says which.

### Reproducibility

Same seed, same libraries, same settings, byte-identical file. Each example gets
its own seed derived from the run seed and its index, so generating 20,000
examples instead of 10,000 appends rather than reshuffling the first 10,000.

### The merged multi-signal tree

`python -m scripts.encoder_training merge-folds` concatenates the per-signal fold
trees into one for joint multi-head training. It lives in
`scripts/encoder_training/merge.py` because it is built on the fold-tree
convention in `dataset.py`.

**Nothing is regenerated**, and that is what makes the comparison readable: the
merged tree's `fever_present` slice *is* the fever tree's slice, example for
example, so joint and single-signal models can be compared pairwise. Filenames
keep the `{signal}.fold{i}.{split}.jsonl` convention with the merged name in the
signal position, so `load_folds` reads it with every existing check applying and
no special case. That is the contract: if the merged output ever needed an escape
hatch in `dataset.py`, the merge would be wrong, not the loader.

**No head gains supervision.** A merged dysuria example carries no
`fever_present` key at all — a mask, not a `null` assertion. Each head sees the
same labelled positions in the same mix it saw alone; what changes is that the
shared encoder is also pulled by five other heads on text that head gets no
gradient from.

**Filler-only examples are kept once.** Because `run_seed` does not depend on the
signal, every tree emits byte-identical filler-only examples; one copy is kept and
labelled `null` for all six. That identity is load-bearing, so the merge asserts
it position for position rather than trusting it — if a signal term ever entered
the seed derivation, six *divergent* null sets would collapse into whichever
arrived first and every head's class prior would shift unnoticed. Labelling one
filler-only example `null` six times is itself a silence assertion about the
filler libraries, which is exactly what the generalised filler lint licenses
(section 8).

**Deduplication is on `meta.filler_only`, not the label mode**, and above
`--companion-share 0` those differ: a structural null that drew a companion holds
language drawn from *this* signal's eligible pool, so it is not the example any
other tree emitted at that index and is kept per signal. The check was **relaxed
rather than deleted** — at share 0 every structural null is still filler-only, so
the guard covers what it always covered.

**Every merged example keeps the id it had in its own tree**, as
`meta.source_ids[signal]`, and a joint model reports predictions for signal S
under that id — which is what keeps paired McNemar against that signal's
single-signal run working untouched. The rejected alternative, teaching the
report layer that two ids are one example, would put that knowledge in the one
module with no way to check it.

Four things the merge refuses outright, each because the failure would otherwise
be silent: sources disagreeing on `generator_version`, on the
`(folds, fold_index, split_salt)` triple, or on `requested.companion_share` — **a
tree that is half Arm 0 and half Arm P loads cleanly, trains cleanly and answers
the question the two arms exist to ask with a dataset that is neither of them**;
two sources describing one `fragment_id` differently; and divergent filler-only
examples. A pre-version-3 tree is refused by name rather than merged on a
default, because a default of zero would be right for it and silently wrong
beside any tree above it. One thing it reports without refusing: a `cluster_key`
shared across libraries, which *deflates* effective sample size — the safe
direction — so it is counted and warned about rather than raised.

---

## 8. The lint

`python -m scripts.synthetic_data --lint` reports on library health without
generating or editing anything. Nine reports, eight of which decide nothing and
change nothing. The ninth, the phrase inventory, is the exception: its rules are
mechanical and **`--lint` exits non-zero on a fault in it**, because the
inventory is composed into a thousand committed lines and a fault there is a
fault in every line that used the phrase.

**Signal language in filler** — the one with real teeth. Any filler fragment
reading as an assertion about one of the seven signals is flagged, grouped by the
signal whose `null` label it would falsify, and a CI test fails on it. Matching
is whole-word only: without that, "hot" matches inside `lithotripsy`, `photos`
and `shot`. **Currently zero hits**, on a per-signal baseline built from
`SIGNAL_LEXICONS` so a new lexicon joins it rather than being silently unchecked.
An entry in that baseline is a claim that a line reads as signal language, is
staying in filler anyway, and that somebody decided so on purpose.

The lexicons come in two shapes and the split is not cosmetic. Fever is a state
with a name, so a **term list** does it — "feverish" in filler is a leak whatever
surrounds it. None of the other six can be named in one word without over- or
under-reaching, so each is an **anchor plus modifier** pair and a fragment must
match one of each:

| signal | anchor | modifier |
|---|---|---|
| `dysuria` | named urination | pain / burning / stinging |
| `urinary_frequency` | named urination | frequency language |
| `nocturia` | named urination | night and getting-up language |
| `flank_pain` | loin / side / back / kidney / ribs | pain |
| `haematuria` | named urination, bowl, pan, sample | blood and urine colours |
| `recent_uti` | infection nouns | diagnosis, treatment and recency markers |

That shape is what lets the check stay quiet about filler's legitimate talk of
urine cultures, kidney scans and broken sleep while firing the moment a line puts
the two halves together. "Blood" is a blood test until it is in urine; "kidney"
is a kidney scan until something hurts; "night" is a bad night's sleep until
someone gets up to wee. All three are real filler lines and all three are in the
trap test.

`recent_uti`'s split is the sharpest, because the question is not "does this line
name an infection" but "does it put one inside the last 30 days". Its recency
modifiers deliberately stop short of "last time", "again" and "I'm prone to
them", every one of which is how `uti_speculation` talks about the past and none
of which places an infection inside the window (section 9).

**The cost is recall against euphemism**, and the measured recall is the guard
against the easy way to make a purity failure go away — narrowing a lexicon until
it matches nothing. Each lexicon matches 59%–91% of its own positive library
(`urinary_frequency` lowest, because that library leans hardest on euphemism;
`dysuria` highest) and 25 to 45 points less of the negative one, since negating a
symptom drops the words that name it. `test_every_lexicon_reaches_most_of_its_own_library`
holds these above 45% and parametrises over the signals that *have* a positive
library, so a new signal joins the guard with no test edit. It is a floor, not a
target.

**Cross-signal language** — the same lexicons asked about *every* library against
every foreign signal. Filler purity and this report are one function called two
ways, so they cannot drift apart. The difference is what a hit *means*, and it is
why this half fails nothing: a filler fragment carrying fever language has one
right answer, while a `nocturia_true` fragment carrying frequency language has
three — leave the pair undeclared, declare it `policy` with a written reason, or
rewrite the lines — and picking between them is a labelling decision. A fragment
is never checked against its own signal's lexicon.

**35 of the 300 pairs match, across 25 of the 49 libraries**, headed by the
nocturia / urinary-frequency pair in both directions. The full grid as it stood
when the report landed, every matched line included, is committed at
`reports/synthetic_data/2026-08-18-cross-signal-grid.md`; a terminal scrollback
is not a place to keep the input to a 300-pair decision pass.

For every pair it finds *nothing* in, the report prints a pasteable declaration.
That is the point of it rather than a convenience — 258 pairs came out silent and
had to be declared by hand, and the alternative to cheap typing is a wildcard.
**A zero is evidence of topical absence at 59%–91% lexicon recall, not proof.**
That caveat earned its keep by a wide margin: **17 of the 258 proposed `absent`
pairs were not absent**, and every one was moved to `policy` by reading the
library rather than by any check firing. Sixteen are on `recent_uti_present`; the
seventeenth is `urinary_frequency_null_adjacent`, which describes urine colour and
is invisible to the haematuria lexicon because none of those colours is blood.
Anyone reading the zero-hit block as a verdict would have written 17 false
`absent` claims, and the `absent` check would have passed on every one.

**Declared `null_on` pairs** — the other side of that decision, and the report is
split in two because the guarantee is. `absent` pairs are re-checked and **a hit
is a failure**, held to `ABSENT_PAIR_BASELINE` (28 baselined hits across 18
pairs, all lexicon over-reach — section 4). `policy` pairs are *listed* with
their matched-line count and note, because no lexicon can check them, so the
claim is visible rather than invisible. Undeclared pairs are listed too; that
list is the cost of every decision deliberately unmade. **The two halves are
printed apart on purpose**: a reader who cannot tell the checked half from the
asserted half has neither.

Filler purity stays separate and slightly stricter, because the two filler pairs
declared `policy` would otherwise stop being checked at all, and filler is paired
with examples of *every* label. A test pins that the two checks differ on exactly
those two pairs.

**A generated library sits outside two of these reports.** The cross-signal grid
and the undeclared-pairs list both exist to drive `null_on` authoring — they put
a lexicon's opinion beside a library-level declaration so a human can decide the
pair — and a JSONL library has no such declaration to decide: every line states
its own vector, and the lexicon language it asserts is the point of it. Rows for
it would read as unconsidered pairs that nobody can ever consider, so it is
excluded from both and the 300-pair arithmetic below is unchanged by its arrival.

**Cross-split near-duplicates** — pairs of similar fragments in different splits,
i.e. section 6's leakage. This is the report that catches a library written as
one sentence frame with the slots swapped, and it caught exactly that in several
first drafts. The fix is always to rewrite the lines as distinct situations, not
to tag them as clusters: tagging records the twinning honestly while leaving
effective n halved. Two caveats on the count: it is **within-library by
construction**, so a library part-written by adapting a sibling signal's scores
clean; and libraries sharing a small vocabulary run high on character similarity
between genuinely distinct ideas, so chasing it to zero is partly chasing noise.

Generated libraries are **excluded from the pair listing** and named in a
section of their own with their line and cluster counts. Two lines of a generated
library share a frame and most of a sentence by construction, so a high character
similarity between two of them is the expected output rather than evidence of
anything — and there are tens of thousands of such pairs in a 1,000-line library,
enough to bury every other library's rows and to cost a minute of wall clock
producing them. The cluster count is the number to read there instead: it is what
the split actually partitions on.

Two faults the report could not see, both of which have happened. **The first is
now checked; the second is not**, and the gap between them is the reason the
token report's header spends a paragraph saying what it is blind to:

* **A token that appears in exactly one library.** "Dysuria" once appeared on 16
  lines of `dysuria_null_metaphor` and nowhere else in the six dysuria libraries —
  a perfect shortcut separating `null` from `true` and `false`. A clinical term
  that lives in one library is a label, not vocabulary. This is what the
  token / label-class association report below now measures.
* **The stylistic form of the same fault, which nothing here catches.** The first
  draft of `haematuria_null_hedged` was written entirely in lowercase with no
  terminal punctuation against uniformly capitalised `true` and `false` sets, so
  casing alone separated the ambiguous class perfectly. Nothing normalises emitted
  text, and a per-token report cannot see a property of a whole line. **Writing
  style is vocabulary**: if one library is written in a register, all of them have
  to be, and that is still checked by reading.

**Token / label-class association** — the check the first of those two was
missing. Each signal's libraries are grouped into three label classes by
`fragment_type` (`positive → true`, `negative → false`, everything else →
`null`), and every token on at least five lines of the signal is ranked by
**skew**: its highest per-line rate across the three classes minus its lowest.
Rates rather than counts, because the classes are different sizes. Two blocks per
signal, printed apart because they are different faults — tokens **confined to
one label class**, which is the dysuria case, and tokens **present in more than
one class but skewed**, which is the weaker form the plan's review found alive in
fever. Filler libraries have no `signal_key` and generated ones state their
labels per line, so neither is in any signal's grouping.

It reports and fails nothing, for the same reason the cross-signal grid does not:
a null sub-class's axis word is *supposed* to be confined to it (`she` and `he`
in third-party, `ago` in historical, `might` in hedged), and separating those from
a fault is a clinical judgement rather than a rule. Three things to know before
reading a short block here as a clean bill of health. **Function words dominate
the ranking by construction** — a rate near 0.5 has the most room to move, so
`was`, `but` and `the` head most blocks, and that is the tense and register
difference between the classes rather than a swappable word. **Negation, tense
and person head the per-signal ranking** on six of the seven signals, and every
one of those tokens is frozen by `noise.STRUCTURAL_FROZEN`. And **skew within the
`null` class is not in the ranking at all**, though it is the largest real finding
in the tree: `fever` is on 41 of 45 `fever_null_historical` lines and 0 of 50
`fever_null_attribution` ones, a within-null spread of 0.911 against a three-class
skew of 0.165. Each row prints its per-library counts underneath for exactly this
reason.

The full output over the committed tree is at
`reports/synthetic_data/2026-09-03-token-label-association.md`, with the
signal-level summary and the two narrower readings that the headline statistic
does not give.

**Hedge markers** — lines in the decisive libraries that sound uncertain, as a
prompt to re-read them. Precision is poor by design (~25%), because many
fragments open with uncertainty and then resolve it. It is a reading list, not a
fault list.

**Split coverage** — how many fragments of each library landed in each split,
flagging any empty cell (section 10). Each cell is printed as **lines over
clusters**, with the library's **frame count** beside it. The cluster is the unit
the split is assigned in, so a cell whose two numbers are far apart holds fewer
ideas than lines; and 12.1 asks for the frame count next to the line count
because a generated library's lines are its frames multiplied by something, and
reading the first without the second is how a library comes to look richer than
it is. A hand-written library shows `-` rather than `1`: "no frames" and "one
frame" are opposite claims about a library.

**What a generated library is made of** — its lines, clusters, arity mix, frame
mix, and the min/median/max lines per cluster. This is what replaces the
near-duplicate pairs it is excluded from. It is also the only place DD15's budget
can be read: one so small that most clusters are empty and one so large that
every cluster carries a dozen near-identical siblings both look like a
four-figure line count and are told apart only here. Today: 1,000 lines, 316
clusters, arities 500/350/150, all four frames used, median 2 lines per cluster.

**Generated vectors against the lexicons** — the one check a lexicon can make on
a *per-line* label vector, and it is one-sided: it can say the text reads as a
signal the vector is silent about, never that the vector is right. An asserted
signal is skipped for the same reason a library is never checked against its own
signal. The two silent states are reported apart because only one of them is a
claim: `null` supervises a head towards "not mentioned" and so is contradicted by
the text, while an *undeclared* signal earns no key and teaches nothing.

**557 of the 1,000 lines hit, and none of them is a labelling fault.** 294 are
the nocturia / urinary-frequency pair reading as each other, which is DD14
arriving exactly where it was predicted: a line naming one of the pair says
nothing about the other, and no lexicon can tell "extra toilet trips" from
"night-time toilet trips". The other 263 are the third family of section 4's
lexicon over-reach — a urinary anchor in one clause pairing with a flank-pain
modifier in another ("blood in my wee … pain in my side") — which a sentence
naming four symptoms makes far likelier than a hand-written line does. The
baseline pins the counts *and* the shape: **every hit is an anchor+modifier
pair**, and a hit where a lexicon names the signal in a word of its own would be
a line whose text asserts what its vector calls silence, which is a wrong label
rather than over-reach. That is the assertion worth keeping; the counts move
whenever the inventory or the budget does.

**The phrase inventory** — the authored input the generated library is composed
from, and the only report here that fails. Four mechanical rules (12.3 DD10): the
signal is a Boolean encoder signal in the ruleset and is not one no frame can
state (`recent_uti_present`); it declares at least three phrases, below which the
phrase becomes a proxy for the cluster; each bare form is at most four words; and
**no form reproduces a hand-written library line verbatim**. The last is the
load-bearing one — vocabulary overlap across splits is unavoidable and always has
been, whole lines are not, and a phrase lifted from a train library would arrive
inside a generated val fragment. The other half of DD10, that the phrase reads
correctly after both bases and that its label is unambiguous under section 9, is
review; no lint can do it.

Its cross-lexicon rows are a report like the others: **10 rows, all of them the
nocturia / urinary-frequency pair in both directions**, which is the same
undecided overlap seen one level further upstream. A row for any other pair is a
phrase to re-read, because a phrase that names two signals labels only one.

### Three guards against a bad merge

The lint reports; these tests fail the build. They exist because several library
tickets landed in quick succession and their merges concatenated conflicting
edits rather than merging them. They run against the committed tree rather than
a fixture.

* **No duplicate JSON keys in the manifest.** `json.load` resolves duplicates
  last-wins, so a fused entry made the first library *silently vanish*. Only an
  `object_pairs_hook` sees it.
* **Every `.txt` on disk is declared in the manifest.** The other half of the
  same fault: `load_fragments` checks only the reverse direction, so a library the
  manifest stops naming quietly stops being training data.
* **Nothing but libraries and the manifest lives in the tree.** A half-written
  library or a scratch list of synonyms sitting in `data/synthetic/` is invisible
  today and adopted by the next tool that globs.

**Two further guards were retired with the per-library table this document used
to carry** — that the table listed every library exactly once and that every
count in it matched its file. Both existed only to keep a duplicate honest, and
the duplicate is gone: the manifest is the inventory and the lint prints the
counts. That is also why `.github/workflows/tests.yml` no longer needs this file
in its `rulesets` path filter.

---

## 9. What this data is and is not worth

Stated plainly, because the numbers this produces are easy to over-read.

**The validation score is a smoke test, not evidence.** Validation holds ~15
distinct positive fragments; every `true` example in it is a recombination of
those 15 sentences, and one unlucky fragment moves the score several points.

**Length may still leak.** Fragment *count* does not vary by label (section 5);
fragment *length* is not controlled at all. `fever_true` runs from 3 words to 98
while the `fever_null` libraries sit in a narrower band. Medians are close, so
this is a tail problem rather than a systematic offset — but a 98-word positive
has no counterpart in the null libraries and the model can notice. The sidecar
reports median and 90th-percentile length per label every run; **if the medians
ever drift apart by more than about 1.5×, length has become a usable proxy**.
Fixing it is library work, not a generator change.

**Urgency language leaks too.** About 17% of `fever_true` fragments bundle the
claim with a justification ("I've got three important meetings I can't miss")
against 8% of `fever_false` and almost none of `fever_null` — exactly the "sounds
urgent, must be positive" shortcut. Pairing with filler washes some of it out;
fixing it properly means splitting those fragments up.

**Claim density, not length, is the gap to real text.** The 67 real submissions
run 9 to 80 words with a median of 39 and a default example is 28 to 42, so
length is not the problem. The median real submission asserts something about
**two** of the six signals; every generated example carries **exactly one**
decisive claim by construction. Companions put other signals' language into the
non-decisive slots and closed most of the resulting failure (section 10), but
they add no second *supervised* claim — that is 12.2 and 12.3.

**Cross-signal labels are only half honest.** `--emit-signals all` can emit a key
per signal, but only where every fragment in the example is declared. The
undeclared pairs (section 4) are masks rather than `null`s, and no per-line
mechanism exists, so a `true` or `false` about a foreign signal is still
inexpressible (12.3, 12.5).

### The accuracy ceiling is not the same for every library

A model scoring 70% on one library and 95% on another has not necessarily failed
on the first: some patient text does not contain enough information for a
competent clinician either. That principle is right, and most of what currently
*looks* like irreducible ambiguity is not.

**`null` is already the answer for "the text does not say"**, so a fragment that
leaves the clinical question open still has a determinate correct label and the
model can be held to a high standard on it. `fever_null_hedged` states the
patient's own uncertainty outright; 70% there would be a model failure, not a
ceiling.

**The genuine ambiguity is at the `true`/`null` boundary and is settled by
policy.** "I was burning up and sweating a lot" is `true`; "i feel like im
roasting on the inside but when i touch my forehead its perfectly cool" is
`null`. The clinical content is the same and what separates them is whether the
patient volunteered doubt. So the fever libraries encode a rule — *unhedged
first-person present subjective heat counts as `true`* — that is load-bearing on
hundreds of fragments and recorded nowhere else.

Two signals have their policy written down properly, and both were written
*before* the run that measured them, which is the pattern to follow:

**`urinary_frequency_present`.** (1) The comparison is against the patient's own
baseline, not a population norm — "I've always gone twice an hour and that hasn't
changed" is `false`. (2) Cause is irrelevant: if the trips have gone up the
answer is `true` whatever caused it, which is why an `attribution` library is
wrong for this signal. We label the `encoder_prompt`'s question, not the
clinician's inference from it. (3) Adjacent urinary complaints — urgency,
hesitancy, weak stream, incomplete emptying — are `null`, not `true`: they travel
with frequency clinically and say nothing about it textually. Rules 2 and 3 cut
against clinical instinct, which is exactly why they are worth having in writing.

**`recent_uti_present`**, labelled against the `encoder_prompt` verbatim — *does
the response indicate the patient has had a urine infection in the last 30
days?* — in six rules, each of which a real submission forces:

1. **A suspected current infection is `null`.** "I reckon it's another UTI" is a
   guess about the episode that brought them here. This does the most work,
   because self-diagnosis is the commonest way patients talk about UTIs.
2. **Treatment is a proxy for diagnosis.** "I finished a course of nitrofurantoin
   ten days ago" is `true` with no diagnosis stated.
3. **The axis is the 30-day window, not the tense.** "I had one last year" is
   `null`, **not `false`**. This is the rule most often got wrong by instinct,
   because past tense reads as a denial and is not one. A `historical` fragment
   needs a time marker that actually clears 30 days; a vague one belongs in
   `hedged`.
4. **`false` needs an explicit denial spanning the window**, written as distinct
   *situations* — a negative culture, a clear dipstick, a routine check — because
   forty rewordings of "haven't had one in N weeks" is two clusters, not forty
   fragments.
5. **Non-urinary infections are the hard confounder and get their own library.**
   An infection noun, a diagnosis, a treatment and a recent date all present, and
   the answer is `null` because none of it is a *urine* infection.
6. **Recurrence without a window marker is `null`** — "I'm prone to them", "like
   last time".

Read against those rules **all forty `uti_speculation` lines are `null`**, and
the pair it forms with `recent_uti_present` is a `policy` declaration rather than
a leak. The same reading applies to `expectations`, three of whose four
antibiotic lines name no window at all.

**A low number has three explanations, not one**, and the failure mode to guard
against is filing the first and third under the second:

* **Undeclared policy** — the library is inconsistent about a recurring case
  because nobody decided it. This *presents* as irreducible ambiguity and is
  fixable by writing the rule down.
* **Irreducible ambiguity** — the policy is decided and this fragment still sits
  on the line. Further work is waste.
* **Model or library weakness** — the answer is determinate and the model gets it
  wrong. This is what training and more fragments are for.

So: **an expected ceiling below the general target is declared per library, in
writing, before the run that measures it.** A ceiling asserted after a
disappointing report is not a ceiling, it is an excuse. The honest way to
establish one is a second labeller working from the text alone, blind to the
file. No ceiling is declared for any library today, and there is no manifest
field for one — this records the position, not a mechanism.

One consequence runs the other way. **A high score on an ambiguous boundary is
worse news than a low one.** If `true` versus `null` is decided by whether the
patient volunteered doubt, a model at 95% has learned to detect volunteered doubt
— a discourse cue, not a clinical one — and will carry that into real
submissions, where the cue and the fact come apart.

### What sixty-seven real submissions show

Sixty-seven UTI free-text submissions are the held-out evaluation set, and are
now the instrument every real-text number in section 10 comes from.
**`data/realistic/README.md` is the authority on what the set is, the rules it
is used under, its label distribution and its limitations** — including the
label provenance and the one-person voice, both of which bound every number
scored on it. What follows is only what *reading* the submissions says about the
libraries: the cheaper half of their value, available before any model touched
them, and recorded nowhere else.

**The class prior was a good bet.** Hand-labelling fever gives roughly 9 `true`,
9 `false`, 49 `null` — 13/13/73 against the generator's 15/25/60. Explicit
denials are genuinely common: patients volunteer "no fever", "no blood in my
urine", "no back pain" unprompted, which is what the `false` class was a bet on.

**Six labelling policies the libraries never declared.** Every one is the
*undeclared policy* case above, not a ceiling: chills with no stated heat (the
libraries make a chills word evidence *against* a fever; real patients use it
for); a number below the clinical threshold the patient calls a fever; confident
hedges ("im pretty sure ive got a fever now" — split across `true` and `hedged`
today, which is what undeclared looks like); unlateralised "lower back", which
six submissions use and the flank libraries silently require laterality for;
particulate urine ("dark specks"), which the haematuria red/pink-versus-dark rule
says nothing about; and discomfort short of pain, for which the dysuria libraries
have no stated floor.

**A composite the libraries never produce.** One submission carries a past fever
and a present one in a single sentence. No fragment anywhere holds both, because
each library holds one claim — so the contrast the `historical` axis exists to
teach is never shown in the form patients actually write it.

**Two filler families that do not exist.** *What the patient has already tried* —
cranberry sachets, D-mannose, paracetamol, a just-finished antibiotic course —
appears in about half the submissions; the nearest libraries are about what they
*want*. *Relevant history and risk factors* — pregnancy, diabetes, stones,
recurrent UTIs — appears in about a quarter against two such lines in all six
filler libraries. Neither can simply be written as filler, because lines like "I
finished a course of nitrofurantoin ten days ago for a urine infection" carry
signal language and would make every label they were paired with a lie: they
belong in the `_null_historical` libraries or behind a declaration. **The lint
would not stop either line** — both are historical claims about an infection
rather than a symptom, so they match no anchor-modifier pair. It guards against
drift in libraries already judged clean; it is not a substitute for judging a new
one.

**The set is not written in one register.** It splits into three blocks by
punctuation and contraction habits, and sixty of the sixty-seven sit in a tidier
register than the libraries deliberately aim at. That creates no label shortcut,
because register does not track the label; it creates a coverage problem, and an
aggregate number over the whole set is a number about the tidy register.

**It is a validity instrument, not a precision one, and it does not replace the
held-out fragment split.** Sixty-seven texts and no mechanism makes more, so
fold mode cannot widen them; the per-signal intervals are wide enough
(`arch_encoder_training.md` section 11 has the half-widths) that it cannot rank
two models and must not be used to select anything. What it can do is show that
83.5% is really 55%, which is the question that matters most and which nothing
else answers. The fold-pooled test set asks the different question — does the
model generalise to *ideas* it has not seen, in the register it was trained on —
and is the only instrument with the effective n to answer it per sub-class. Run
both.

**One of the README's limitations changed status here.** Three of six signals
have no `false` submission anywhere in the set, so their decisive accuracy *is*
`true` recall. That used to narrow a result; since 2026-08-19 it blocks reading
one, and writing those submissions is the standing next ticket.

---

## 10. Current state

**Numbers live in `reports/encoder_training/`, not here.** Each run's JSON files
are the authority, the dated markdown beside them is the write-up, and this
section records only what is true of the *data* and what is outstanding.
Generator versions are not comparable with each other: version 3 split
`expectations.txt` in two, which changes every `_draw_filler` outcome and
therefore every generated example, and added `meta.filler_only` and the companion
draw. **Every measurement before 2026-08-19 was made at version 2 and is history
rather than a comparator.** Version 4 computes pool membership from a fragment's
label vector and adds `--declarative-share`; both are inert at the default, and
a version-4 default run's *content* is identical to a version-3 one — only
`meta.generator_version` moves. It is still a different version line, because a
dataset whose pools were computed a different way is not comparable on the
strength of one manifest happening to make them agree.

### What exists

* Generator, lint, noise pass and tests: complete and merged. Every library fills
  all three of its cells (`empty cells: 0`).
* Libraries for all seven signals, and five-fold datasets for all seven at
  fever's recipe — 10,000/2,000/2,000, `15/25/60`, `--null-ambiguous-ratio 0.5`,
  base seed 42, salt 0, no `PoolExhaustedError` anywhere.
* Both companion arms at version 3 (Arm 0 at `--companion-share 0.0`, Arm P at
  0.5, identical in everything else), each merged into a six-head `joint6` tree.
* One generated library — `declarative_v1`, 1,000 multi-symptom lines across 316
  clusters, built from an authored phrase inventory (12.3). It is committed, in
  the manifest and drawn from only above `--declarative-share 0`. **Measured at
  0.3 on 2026-09-02 and not recommended** — see the four-cell entry below.
  `--declarative-share` remains 0.0 by default and nothing shipped draws from it.
* Six trained heads. `recent_uti_present` has libraries and a fold tree but **no
  trained head**, and `EncoderOutput.validate_against` requires all seven keys —
  so nothing produced so far is deployable.

**The generator refuses to run if any library has zero fragments in any split**,
and the guard covers every library in the manifest, not just the signal being
generated: one empty cell blocks generation for *every* signal. An empty cell
means a hard-case sub-class is invisible during evaluation — the model could be
systematically wrong about it and nothing would show. **An empty cell must be
cleared with genuinely new ideas, never rewordings**, which is how
`fever_null_metaphor` and `dysuria_null_metaphor` were cleared; both also turned
out to be one idea repeated (*the patient is worked up, described with heat
words*), and were fixed by replacing clusters rather than adding fragments.

Note that adding a hard sub-class *dilutes* the others at a fixed example count —
the ambiguous pool is drawn from uniformly — so a moved example count across
dataset versions has an explanation before it has a problem.

### Fragment count and cluster count come apart

Cluster count is what matters. Tagged coverage, per signal, over the whole
library (version-independent — the `expectations.txt` split moved lines between
two *filler* libraries only):

| signal | libraries | tagged lines / total | untagged libraries |
|---|---|---|---|
| `dysuria` | 6 | 148 / 256 (58%) | `true`, `false` |
| `fever` | 7 | 89 / 463 (19%) | `true`, `false` |
| `urinary_frequency` | 7 | 0 / 302 | all 7 |
| `nocturia` | 7 | 0 / 351 | all 7 |
| `flank_pain` | 5 | 0 / 243 | all 5 |
| `haematuria` | 5 | 0 / 225 | all 5 |
| `recent_uti` | 6 | 0 / 256 | all 6 |

The five untagged signals' effective n equals their fragment count **by claim,
not by measurement** (section 3), so their intervals are narrower than the truth.
The evaluation report computes this table per run and prints the warning above
its own headline.

### What the four measured runs established about the data

Full results and caveats are in the reports; these are the findings that are
facts about the *data* rather than about a model.

**2026-08-16, six single-signal heads (version 2).** Errors land on the clear
`_true`/`_false` libraries, not on the deliberately-hard `null` confounders,
which mostly sit at 0.90–1.00 recall — the 2026-08-09 fever finding replicating
across five more symptoms. `urinary_frequency_true` (65.8%) and `nocturia_true`
(71.1%) are the two worst libraries in the sweep, and TF-IDF is worst on exactly
that pair too, so **`nocturia` and `urinary_frequency` are a hard pair in the
signals rather than in the encoder**. The working hypothesis is that they are
near-synonyms — "going a lot" against "going a lot at night" — which is also why
`urinary_frequency` is the one library set that needed an `adjacent` class.

**2026-08-17, three-arm joint comparison (version 2).** Joint training helps on
recombinations and is catastrophic on real text: it improved the synthetic
`null → true` rate on four of six signals while multiplying the same rate on the
67 submissions by 3× to 24×, scoring **39.1%** across the 402 real answers
against **66.7%** for replying `null` to everything. That is the failure
companions were built for, measured rather than argued, and it made multi-symptom
recombinations the critical path rather than an option. Two smaller facts: 4.5×
the recombinations of the same clusters buys −0.8 to +1.3 points, so joint
training's gains are not gradient steps; and the near-synonym ambiguity resolved
**in nocturia's favour at urinary frequency's expense**.

**2026-08-19, the companion run (version 3, the current baseline).** Arm 0 and
Arm P as above, plus Arm C — Arm 0's trained heads with every margin re-selected
on Arm P's validation split, no retraining. **The numbers are in
`reports/encoder_training/2026-08-19.md` and the six
`*.companion_comparison.json` files beside it**; the declared threshold is
re-scorable from the JSON with `score-companions`. Five findings are facts about
the *data* rather than about a model, and the design above now rests on them:

* **Companions fixed the failure they were specified for.** The real-text
  `null → true` cell — inventing a symptom the patient never mentioned — falls by
  a large margin on five of six signals, at a small cost in decisive cells. Arm P
  is the first model on file to beat the all-`null` floor on real text, which was
  recorded in advance as a bonus and explicitly not the success condition.
* **The negative control passing is the good outcome, not a weak result.** The
  synthetic test set cannot contain the failure companions were built to fix, so
  a large synthetic gain would have meant a new shortcut rather than a removed
  one. Nothing moved. That is the second time on file that the 67 submissions
  have seen something no amount of generated data could.
* **It is not a collapse to `null`, and the guard could not have told us that.**
  Two thirds of the real-text cells are `null`, so guard and primary criterion are
  driven by the same cells and a silent arm would clear both. Decisive-cell
  accuracy is what rules it out: it holds on five of six signals while `null`
  recall rises sharply everywhere.
* **`urinary_frequency` absorbed the entire cost** — the only signal to miss the
  bar and the only one to lose real detection, badly enough that it is not usable
  for that question. This is the second consecutive run in which the near-synonym
  pair resolves in nocturia's favour at urinary frequency's expense — 2026-08-17
  through joint training, this one through companions. The cause is structural:
  those 14 pairs are undeclared (section 4), so the two signals draw the fewest
  companions from each other and each head has never seen the other's language at
  any label. **Per-line expression is what this needs** (12.3), or the
  library-level assertion 12.9 proposes.
* **Margin re-selection captured a small share of Arm P's gain**, so the
  training-data change did the work and Arm C was not a substitute — but it is
  free, and no future margin should be selected on a validation split in which
  this failure cannot occur.

**What 2026-08-19 does not establish**, beyond the standing limits above: every
margin in it was selected on a sibling fold's test clusters, so no absolute
figure is a deployment estimate; `P = 0.5` was chosen on the claim density of the
real corpus and **not swept**, deliberately — sweeping it against the 67 would be
selection on the holdout; and the register gap is untouched, because companions
do not change register.

**2026-09-02, the declarative 2×2 (version 4, six single-signal heads).** Four
cells at `--companion-share` 0.0/0.5 × `--declarative-share` 0.0/0.3, six signals,
five folds, one `declarative-compare` invocation. **The numbers are in the six
`*.declarative_comparison.json` files under
`reports/encoder_training/decl/comparison/`**, the write-up is
`2026-09-02-declarative.md` and its plain-English companion, and the run record is
`reports/training_runs/20260902-125946-decl-compare-2x2/`. Four findings are facts
about the *data* or the *pipeline* rather than about a model:

* **Declarative fragments make the invented-symptom rate worse.** Real-text
  `null -> true` rose in 6/6 signals from cell A to cell B and rose-or-held in 6/6
  from C to D, by up to 33.9 points. The prediction was that it would improve, and
  would move least for `flank_pain_present`; it moved most, upward. The cause is
  established, but cell R at 0.6 (run `20260902-174947-decl-compare-register`,
  reports under `reports/encoder_training/decl/register/`) constrains it: the
  damage is **front-loaded**, roughly 85% of it arriving with the first 0.3 and
  the curve then flattening. DD8's register argument predicts the opposite —
  harm scaling as the frame comes to dominate decisive text — so it fits the
  curve poorly. A shortcut learned once the pattern is present at all, and then
  saturating, fits it better; the candidate is claim density, since a `true`
  example whose decisive sentence asserts three symptoms teaches "dense symptom
  language → `true`" and real submissions are dense. Suggestive, not settled.
* **The synthetic test set cannot see it.** On recombinations the same metric sits
  at 1–4.4% in every cell and points D *better* than C on four of six signals,
  against five of six worse on real text. This is the 2026-08-19 finding arriving
  from the other side: a failure the synthetic set cannot contain is a failure it
  cannot see returning. Read the holdout section of these reports or read nothing.
* **The margin selector is now a larger effect than the treatments.** Per-fold
  margins span more than half the 0.0–0.9 range in 20 of 24 cells, and the margin
  is mechanically the lever on `null -> true`. Each cell selects on its own
  validation split, which the treatment changed. **Until this is addressed, no
  cross-arm real-text comparison in this pipeline is trustworthy, including those
  already committed.** 2026-08-19's closing note — that no future margin should be
  selected on a split in which the failure cannot occur — is this problem,
  recorded and not yet acted on.
* **Everything `declarative_v1` emits is an easy case, measured.** It scores
  **100.0%** with an exactly diagonal confusion matrix in every cell that draws
  from it, and contributes roughly a quarter of the effective clusters in those
  cells. DD3 as a number: a dataset that grew in line count has not grown in
  difficulty, and a pooled accuracy that rises when the library is added is partly
  reading its own free examples.

One result outside the ticket's scope and larger than it, and **strengthened by
the register run**: with cell C as reference, TF-IDF *beats* the fine-tune on
three of six signals (p = 0.021, 2.6e-09, 6.8e-11) and ties the rest, the
fine-tune winning none. In the 2×2, whose reference cell had no companions, the
fine-tune won two — so the better the data gets at suppressing invention, the
less a transformer adds on the hard slice. The 2×2 figures: **on
`null_ambiguous`, a fully fine-tuned `roberta-base` is indistinguishable from
`tfidf_logreg`** —
every point estimate within 2.2 points, McNemar p ≥ 0.36 on three of six signals,
and TF-IDF ahead on one of the three that separate. By the reports' own decision
rule that is the library-bottleneck reading of the encoder question. Arm A was
skipped in this run, so the rule's frozen-probe comparator is missing and the
result needs one confirming run before it is acted on.

**What 2026-09-02 does not establish:** predictions 1, 2, 5 and 6 are unscored.
The fold trees were generated in a console run that was not saved to a branch, so
the `.stats.json` sidecars needed for the byte-identity and filler-only-null
checks were never committed and `data/synthetic/generated/` is gitignored; the
lint was not run. Cell R **has** since been run (see the bullet above and
section 12 of the write-up); predictions 1, 2 and 5 remain unscored. Cell C is
**not** a replication of Arm P —
those arms are six-head `joint6` models and these are single-signal heads, which
2026-08-17 already shows is worth 3× to 24× on this metric, so the whole gap has
an explanation that has nothing to do with the version bump.

### Outstanding

1. **Fix the margin selector** — 2026-09-02 shows it varying more between folds of
   one cell than the treatments being measured vary from each other, on a
   criterion unrelated to real-text invention. This now blocks trustworthy
   measurement of everything below it.
2. **Fix `urinary_frequency`** — 12.9 first, since it may be a library-level
   assertion rather than the per-line format of 12.3.
3. **Write the missing `false` submissions** for the three signals that have
   none.
4. **Fold companion-bearing validation into the standard recipe regardless of
   arm** — Arm C's 16% costs nothing but a re-selection.
5. **Train a `recent_uti_present` head**, without which nothing is deployable.
6. **Re-run or retire the outstanding A1/A2/A3 sweep** — its datasets are version
   2 and non-comparable.
7. **Tag the five untagged library sets**, prioritised by the near-duplicate
   rates in section 3.

### Effective sample size: count clusters, not examples

**This subsection is the canonical statement of the point**; other documents
cross-refer to it rather than restating it. The one deliberate exception is the
evaluation report, which reproduces it in full because it is read standalone.

The easiest way to over-read anything this pipeline produces is to quote an
example count. **The effective sample size of any evaluation slice is the number
of distinct clusters behind it, not the number of examples.** Ten thousand
examples built from 66 training fragments is 66 ideas seen many times. Clusters
rather than fragments, because tagged siblings are one idea written twice and
always land in the same split.

**Under the default 70/15/15 bands this makes per-sub-class numbers unreadable.**
A 15% slice of a 40-to-70-fragment library is 2 to 6 clusters per hard
sub-class. A recall figure computed on 2 clusters can only take the values 0, 0.5
or 1.0, carries roughly ±30 points, and cannot separate two models.

**Fold mode is the mitigation and it is built.** Pooling five folds makes every
cluster a test cluster exactly once, so a sub-class's aggregate test set is its
whole library rather than the ~15% of it a single split holds — 19 to 63 clusters
today against a two-to-nine-cluster slice. Note what that is worth and no more:
effective n rises about sevenfold, and uncertainty goes as 1/√n, so an interval
near ±30 points comes down to roughly ±11. That is the difference between a
number that can carry a conclusion and one that cannot. **The `eff n` printed
beside every slice in the report is the authority**; the cluster range above is
the current libraries' size, not a property of the method, and it moves whenever
one is tagged or grown. Folds create no new
ideas, so section 9 applies unchanged and this remains a library-size problem
whose real fix is more fragments.

---

## 11. Running it

`--help` is the authority on flags; what follows is the shape of a run and the
constraints that are not obvious from a help string.

```
# one split
python -m scripts.synthetic_data --split train --count 10000 \
    --out data/synthetic/generated/fever_present.train.jsonl

# one fold of a five-fold run (every fold needs all three splits)
python -m scripts.synthetic_data --folds 5 --fold 0 --split test --count 2000 \
    --out data/synthetic/generated/fever_present.fold0.test.jsonl

# with companions, and with a key per entitled signal
python -m scripts.synthetic_data --split train --count 10000 \
    --companion-share 0.5 --emit-signals all --out ...

# rebuild the generated declarative library from the phrase inventory,
# and the check CI runs (regenerates in memory, writes nothing, exits 1 on drift)
python -m scripts.synthetic_data --build-declarative
python -m scripts.synthetic_data --build-declarative --check

# reports, no output: library health, and a salt search
python -m scripts.synthetic_data --lint
python -m scripts.synthetic_data --folds 5 --find-fold-salt

# merge one arm's per-signal fold trees into the joint tree
python -m scripts.encoder_training merge-folds \
    --data-dir data/synthetic/generated/arm0 --folds 5

# damage a finished tree (12.6); filenames and ids are preserved
python -m scripts.synthetic_data.noise --in-dir <tree> --out-dir <tree>-noisy \
    --rate 0.02 --seed 42

# paraphrase a finished tree (12.10); filenames and ids are preserved, so every
# expanded example is paired with its clean original by example_id
python -m scripts.synthetic_data.expand --in-dir <tree> --out-dir <tree>-expanded \
    --rate 0.4 --clean-share 0.25 --seed 42

# check a rule file against the library lint; reads the libraries, writes nothing
python -m scripts.synthetic_data.expand --dry-run-lint --signal fever_present

# one cell of 12.10's 2x2, writing the decisions the flip rate is paired from
python -m scripts.encoder_training finetune --signal fever_present --folds 5 \
    --data-dir <clean tree> --test-dir <expanded tree> \
    --predictions models/encoder-lexical/clean-trained-expanded-test.predictions.json

# the read-out: one flip rate per arm, plus the pre-registered accuracy guard
python -m scripts.encoder_training paired-flip-rate --signal fever_present --folds 5 \
    --clean-dir <clean tree> --expanded-dir <expanded tree> \
    --arm clean_trained <clean-test predictions> <expanded-test predictions> \
    --guard-baseline <clean/clean report> --guard-arm <expanded/clean report> \
    --guard-bound 0.02
```

The whole of that last sequence is one button in the training console
(`lexical-expansion-2x2`), which is where it should be run from: every path in it
is a literal, and a cell pointed at the wrong tree does not fail, it silently
compares a tree with itself.

**The constraints worth knowing.** The generator validates its own flags and
refuses to start rather than failing partway through a 10,000-example run —
`--help` and the error messages are the authority on the rules. What is not
obvious from a help string is *why* they exist:

* **There is deliberately no per-label-class version of `--fragment-counts` or
  `--companion-share`.** Both are the safety argument of section 5: a mix that
  differed by class would make length or companion density a proxy for the
  label.
* **`--companion-share` above zero refuses a split with no eligible library**
  rather than quietly producing the zero-share dataset under a non-zero flag.
  Read `companions.count_by_label_mode` afterwards — that is the check, not an
  optional extra.
* **`--fold` and the salt require `--folds`.** `--fold 3` alone would silently
  generate the default bands, and salting the default bands would move the split
  of every dataset generated so far.
* **`--emit-signals` defaults to `primary`** and is byte-identical to the
  pre-flag generator. `all` produces a tree nothing downstream consumes yet.
* **An arm is 105 invocations** (seven signals × five folds × three splits) and
  the two arms differ in `--companion-share` and in **nothing else** — same seed,
  counts, fold triple, salt and libraries. If anything else differs the
  comparison is not readable and there is no way to recover it after the fact.
  The merge enforces the agreement it can (section 7).
* The generator checks at startup that the signal exists in the ruleset as a
  Boolean marked `send_to_encoder`. A dataset for a signal no head consumes is
  wasted effort, and configuration drift is a fail-fast error everywhere in this
  system.
* Output goes to the git-ignored `data/synthetic/generated/`. The datasets are
  large and exactly reproducible from libraries plus a seed, so there is no
  reason to commit them. The generator uses the standard library only.

**Dependency direction.** `scripts/encoder_training/` reads the JSONL and its
sidecar and **nothing else** — never the manifest, never the `.txt` libraries.
That is what section 7's `fragments` block is for, and why it is not optional: a
consumer re-reading the libraries at training time would compute cluster
groupings from files that may have changed since generation, and would be wrong
*silently*.

---

## 12. Beyond the proof of concept

Each subsection states where it stands. The ideas are additive — each multiplies
a different axis of the dataset — except 12.6, which multiplies surface forms
only and adds no ideas at all.

### 12.1 Procedural fragment generation — not built

Hand-written templates with slots (`I {verb} {adjective} {synonym}`) expanded
into fragments. `documentation/encoder_plans/procedural_fragment_generation_implementation.md`
is the plan of record.

**Read that plan for what it now covers, not for what this subsection says.** It
was rescoped to build 12.1 and 12.3 together — procedurally generated
*multi-symptom* fragments — and two of the rules below deliberately do not bind
there: the cluster key is the asserted label content rather than the template ID
(because each expansion carries a different label, so hashing the frame would
collapse a library into two clusters), and the 40-templates-per-library floor is
replaced by a cap on a library's share of the decisive draw. The rules below
remain right for the case they were written for — templating one library whose
lines all share a label, which is where this should start.

**The idea is sound only if the unit of work and the unit of splitting both
become the template rather than the fragment.** Templating multiplies *surface
forms*, not ideas, and the split is keyed on ideas: cross-multiplying slots is a
machine for producing near-duplicates. The arithmetic is what settles it: eight
templates expanding to 800 strings is still eight ideas, which at 70/15/15 puts
roughly **one template in validation**.

So: aim for 40+ templates per library rather than 8 (writing 40 good templates
costs about what 40 good fragments cost; what it buys is 15–20 surface forms per
unit of thought). **Emit the template ID as a cluster marker** — machine-emitted
IDs and hand-tagged `[c01]` markers are the same mechanism, so no change to the
splitter is needed. **Start with the filler libraries**, which carry no label
weight. And **never use it to fill an empty split cell** (section 10): that
removes the warning light rather than the fault. The lint reports frames per
library alongside lines and clusters (section 8), so a dataset cannot *look*
richer than its frame count says it is; that half is built and applies to any
templated library that follows.

**A second, different mechanism has been proposed under this heading and is
planned separately**: expanding the *existing* library lines by swapping parts
of them out ("fever" for "temperature", "I've had" for "I have had") rather than
authoring new templates. It shares the surface-forms-not-ideas arithmetic above,
but its purpose is decorrelating vocabulary from label — the fault section 8
records twice and cannot check for — rather than volume, so it is measured
differently and sequenced differently.
`documentation/encoder_plans/lexical_variant_expansion_implementation.md` is
the plan of record; the provisional plan and the review that corrected it sit
beside it. **The mechanism is not what the provisional plan proposed.** Editing
a library line changes its cluster key -- `cluster_key` is `cluster_id or
normalise(text)` -- and therefore its split, so expanding the libraries
repartitions the data silently. It is built instead as post-processing over the
generated JSONL, in this section's own shape (12.6): no library file is touched,
no split moves, the generator stays byte-identical, and every expanded example
is paired by `example_id` with its clean original, which is what makes the
decision metric a paired statistic. Two gates come before any of it -- a
per-token label-association lint report and a paraphrase-flip diagnostic -- and
both are designed to be allowed to fail.

### 12.2 Multi-signal libraries — built, not measured

The libraries exist for all seven signals and `--emit-signals all` emits a key
per signal (section 7). What has not happened is any *use*: no arm reads a
multi-key tree and `merge-folds` refuses one.

**The payoff is not more examples, it is more label per example** — and it is
also the ceiling on the variable fragment count, since longer examples currently
mean more unlabelled filler rather than more supervision.

**Why measuring it has not been paid for.** A trained arm at `--emit-signals all`
is five more fold-trainings and would not be comparable to the companion arms on
the metric that matters: a companion head's realised prior is roughly 2/2/95
against the primary head's 15/25/60, and the decision rule maximises macro-F1
*subject to a `null → true` rate no worse than argmax's* — so moving the prior
moves the constraint as well as the head, and a rule that suppresses `true`
because argmax already almost never says it would score as a win for reasons
unrelated to reading the text. The question a multi-key arm can answer is "does
more label per example buy training efficiency?", which is not the question
companions were built to answer.

### 12.3 Multi-symptom fragments — built and measured, not recommended

Fragments asserting more than one signal in a clause: "I had a fever and it's
been burning when I urinate." These are closer to how patients write than
anything in the libraries, every one of which makes exactly one claim.

**They cannot be recombined freely.** Pairing one with a pure `fever_false`
fragment produces an example whose halves contradict each other and no single
label is correct. And a multi-symptom fragment cannot have its label implied by
which file it lives in, which is how every library works today: it needs a label
vector per line — a JSONL library format alongside the plain-text one, with the
manifest declaring which format each library uses. **This is what the
nocturia / urinary-frequency pair is waiting on** (section 10), unless 12.9 is
right that a library-level assertion covers it.

**The format and the draw now both exist** (section 4). The manifest can declare
a `jsonl` library, its lines carry per-line vectors, every fragment exposes one,
and since generator version 4 a fragment's *pool* is decided by that vector
rather than by its `(signal_key, fragment_type)` pair. A declarative line
asserting the run's signal goes into a `declarative_positive` /
`declarative_negative` pool held apart from the hand-written one, and
`--declarative-share` is the probability that a `true` or `false` example's
decisive fragment comes from there. It defaults to 0.0, the draw is skipped
entirely at that value, and the generated content of a default run is unchanged
— checked against the golden digest and against the real libraries.

Two rules come with it. A declarative line that is `null` on the run's signal is
an eligible **companion** at any share, filed under every signal it asserts; and
no example may assert one signal twice, so the companion draw now excludes every
signal the decisive fragment asserts rather than only its own. `null_ambiguous`
never draws a declarative fragment: a fixed frame cannot produce a hedge, so
everything generated is an easy case and the hard-case libraries stay the only
source of hard ones.

**The generator now exists too**, and so does the library it writes:
`data/synthetic/conditions/uti/declarative/declarative_v1.jsonl`, 1,000 lines
across 316 clusters.

**It was measured on 2026-09-02 at `--declarative-share 0.3`, in a 2×2 against
`--companion-share`, and the result was negative** (section 10): the real-text
invented-symptom rate rose in every signal, at both companion shares, by up to
33.9 points. The share stays at its 0.0 default and nothing draws from the
library. The paragraph above about `null_ambiguous` never drawing a declarative
fragment now has a measurement behind it as well as an argument —
`declarative_v1` scores 100.0% with an exactly diagonal confusion matrix in every
cell that contains it, so the library adds volume and claim density and no
difficulty whatever.

`scripts/synthetic_data/declarative.py` composes it out of two things:

* **An authored phrase inventory**,
  `data/synthetic/conditions/uti/declarative/phrases.json`, keyed by signal.
  Each phrase carries a bare and a negated surface form, because the obvious
  derivation ships broken English — "a fever" negates to "any fever", not "any a
  fever". Six signals; `recent_uti_present` is excluded, because its label turns
  on a 30-day window and the section 9 policy rules and no frame here can place
  an infection inside one. A phrase is admitted only if its label is unambiguous
  under section 9, which makes the labelling policy a per-*phrase* decision made
  once rather than a per-line one — and is also why nothing generated here is a
  hard case.
* **Two sentence bases**, "I have had …" and "I have not had …", each with a
  mixed variant ("…, but not …" / "…, but I have had …"). The symptoms in a
  sentence are sorted into a true block and a false block, so an interleaved
  "A, but not B, and C" is unreachable by construction rather than by a rule
  rejecting it; which base opens the sentence is decided by which block leads,
  drawn on a fair coin, so the frame does not follow from the label.

**A line's label is drawn before its text exists.** The sampler draws an arity,
then that many distinct signals, then a polarity for each, then a phrase for
each, then the leading block and the Oxford comma — all from one seeded
`random.Random`, in a fixed order. The vector is computed from the drawn
polarities: asserted signals take theirs, every other in-scope signal is `null`,
and the nocturia / urinary-frequency partner of an asserted-but-unmentioned
signal is **omitted** rather than nulled, because whether one of that pair says
anything about the other is exactly the question section 4 leaves undecided.

**The cluster key is the asserted label content** — `decl:dysuria-fever+haematuria+`
— not the frame. Two lines in one cluster differ only in phrasing and comma
style, which is what a cluster is for; hashing the frame instead would collapse
the whole library into two clusters and make its split meaningless. That is the
rule of 12.1 that deliberately does not bind here.

**Volume is capped and stratified by arity**, `--target-count 1000` split
0.5 / 0.35 / 0.15 across two-, three- and four-symptom sentences. Uncapped
enumeration is tens of thousands of lines against 2,503 hand-written ones, which
would make a stiff generated sentence the *typical* decisive fragment. The cap
and `--declarative-share` are separate knobs on purpose: one is how much text
exists, the other is how much of a dataset it is.

**The library is a committed build artefact, not a runtime expansion.**
`--build-declarative` writes it and the file is reviewed and committed;
`--build-declarative --check` regenerates in memory and fails if the committed
file differs, and CI runs that in both the unit job and the data-only job. The
round trip through disk is what lets a human read the sentences before they
become training text, and it keeps ids, clusters and splits flowing through the
same machinery as every other library.

**What it does not buy.** At `--emit-signals primary` a line asserting three
signals still emits one key and the other two assertions are discarded; banking
them needs `--emit-signals all` and a `merge-folds` that accepts a multi-key tree
(12.2). And nothing generated here is a hard case, so a dataset that grows in
line count has not grown in difficulty.

One caveat on the DD7 leak check. `declarative.frame_by_label_mode` cannot show
*equal* rows for the decisive slot, and should not be read as if it could: a
`neg_base` line asserts nothing true, so it can never be the decisive fragment of
a `true` example. What the rows can show is the mixed frames drifting apart, and
that the negative base is not carrying the whole `false` class on its own.

### 12.4 Out-of-scope symptom mentions — not built

Fragments mentioning a symptom outside the ruleset: "I had a fever and a cough."
Cheap, because they are label-neutral — such a fragment behaves like filler
sitting next to a clinical claim. The one rule is that the mention must be
genuinely silent on every signal in the ruleset: "a cough" is safe, "a burning
feeling in my chest" is not. A secondary benefit is putting clinical language in
more places, which mildly counteracts section 9's urgency-language leak.

### 12.5 Label vectors and declared silence — built at library level

The mechanism 12.2 to 12.4 need. The manifest carries `null_on` (section 4), the
lint checks the half a lexicon can check (section 8), and `--emit-signals all`
composes the vector (section 7). The per-line vector is now **expressible** — a
`jsonl` library's lines each carry one, and a text library's is derived from
`fragment_type` plus `null_on` so the two agree by construction — and it is now
what the pipeline reads end to end. Pool selection, the one-assertion-per-signal
rule and `label_vector` all read the vector, and so does the training loader:
the sidecar's `signals` list is what decides which fragment is decisive for a
head, in place of the scalar `signal_key` a declarative line does not have.
Cross-signal `true`/`false` therefore reaches an example, but only through a
declarative library — a text library's vector still states one assertion, which
is what its `fragment_type` means.

Combination is validated on the vector rather than the primary signal: silent
plus asserted yields the assertion, silent plus silent yields `null`, and the
built version is stricter in one place and narrower in another — *undeclared*
plus anything yields no key at all, and asserted-plus-asserted is not permitted
even where the two agree, because a library-level declaration cannot establish
that two lines agree. The label-first invariant survives, and that is the point:
we still choose the target vector first, then filter each pool down to compatible
fragments, then draw. Filtering before drawing rather than drawing and rejecting
also keeps generation deterministic and avoids quietly skewing the mix.

### 12.6 Random character-level errors — built and measured

`scripts/synthetic_data/noise.py` damages a finished tree: dropped and doubled
letters, keyboard-neighbour substitutions, transpositions, dropped spaces,
missing apostrophes, folded case. The libraries' error profile is whatever a
handful of authors produced while concentrating, which is much cleaner than what
a patient types into a phone at eleven at night.
`documentation/encoder_plans/random_error_generation_implementation.md` is the
plan of record and carries the operation list, the rejected alternatives and the
task breakdown; `reports/encoder_training/2026-08-31-noise-2x2.md` and its
plain-english twin are the results of record and carry every number.

**It is post-processing over the JSONL, not a generator flag.** The generator
stays byte-identical, so every dataset generated so far is still reproducible;
one generation run yields both a clean and a noisy tree from identical fragments,
which is what the experiment needs; and deduplication keeps operating on clean
text, so damage can never be what makes two identical examples look distinct. It
works on a **directory with filenames preserved**, because the training tooling
locates data by `--data-dir` plus a fixed filename pattern.

**The label-safety question is the whole of the risk.** This is the one step that
edits text after the label is fixed, so for the first time a mechanical step
could make text stop matching its label: one substitution turns `hot` into `not`,
and the null axes hang on short words like `my`, `his`, `had` and `was`. The
decision is a **frozen lexicon enforced in both directions** — never damage a
frozen token and never *produce* one, redrawing up to three times and then
leaving the word alone. It is built from structural words (negation, person,
tense, modality) plus the signal's own vocabulary out of `SIGNAL_LEXICONS`, which
is why it covers all seven signals.

The lexicon is **two lists, not one**, and the distinction is what makes the pass
worth running. Signal words of five characters or fewer are frozen, because a
single edit inside a short word is proportionally enormous and that is where the
flip risk lives. Signal words of six or more are damageable once — no
single-character edit turns `temperature` into a negation, and being able to read
`temprature` is the headline claim the exercise tests. **Shape-preserving
operations are exempt from the frozen rule entirely**: dropping an apostrophe or
folding case cannot change which word a token is, so `dont` and `Ive` are
reachable, and those are the cheapest and most realistic operations there are.
Space deletion carries its own rule — **never delete a space adjacent to a frozen
token**, in either direction — so `no fever` stays two words while `on the toilet
again` may weld freely. Rejection is tested against the lexicon only and
**nothing in that test can see the label**.

**The edit rate is not equal by label, and the sidecar measures it rather than
assuming it.** The `noise` block reports edits per hundred words by label and by
label mode on every run. The earlier claim that equality holds *by construction*
was too strong and is withdrawn: the lexicon guarantees no rejection is
label-aware, but it cannot equalise aggregate rates, because the three classes
are made of different words. `null` examples are filler carrying no signal
vocabulary, so nothing is refused and they take the most damage — measurably, in
20 of 20 fold files. What matters is the weaker and sufficient property, which
holds: `true` and `false` show no consistent ordering, so the two classes that
must be separated on evidence carry no density difference. Three pre-registered
checks confirm the trained models do not exploit the gap; they are scored in the
2026-08-31 report. The rate is per *word*, not per example, and a share of
examples is left completely clean, because a dataset where every example carries
the same error density is its own kind of unrealistic.

**The experiment has been run and it is positive.** A 2×2 with a rate sweep,
fifteen cells over five folds on `fever_present`: clean plus three damage rates,
each model scored against its own tree and the clean one via `--test-dir`. Cells
are (train tree × test tree) and training depends only on the training tree, so
this is **twenty training runs and forty evaluations**, not one run per cell — the
arithmetic that bought a rate sweep instead of paying twice for four cells. Noise
creates no clusters, so effective n is identical in every cell and a gain can only
ever mean robustness to damaged surface, never better coverage.

A clean-trained model loses **8.5 points** of decisive accuracy on text damaged at
12% per word (93.3% → 84.8%). A rate-matched model recovers essentially all of it
(93.3%) and costs nothing on clean text. Nothing degrades across the rates tested,
so the finding is "noise helps" rather than "a little noise helps". The failure
damage causes has a direction worth knowing: decisive recall drains into `null` —
`true` recall falls 90.5% → 65.3% while `null → true` *falls* — so a typo'd
message is silently dropped rather than misread.

**The rate transfers, which is what makes the result usable.** A model trained at
3% recovers 97% of the damage done at 6% and 87% of that done at 12% — text four
times messier than it ever saw. The inoculation is to damage in general rather
than to a damage level, so the rate does not have to be guessed right, which
matters because the real rate in patient submissions is unmeasured. The small
decay appears when the test rate exceeds the training rate, so **train at the top
of the plausible range rather than the middle**: it costs nothing on clean text
(the r12-trained model is the best of the five there) and covers more of it.

**`--freeze-signal-vocabulary` was measured, not asserted.** The conservative
variant (`all`, freezing every signal word) damages a clean-trained model by an
identical amount and recovers less of it — 91.7% against `short`'s 92.8%, and
lower on clean text too. Intervals overlap, so this is "no reason to prefer
`all`" rather than a win, which is enough: **`short` stays the default.**

**What it is worth, stated the way section 9 states things.** It **adds no ideas
and effective sample size is unchanged**: sixty-six fragments damaged four ways
is sixty-six ideas, and the noisy tree carries the same `fragments` provenance
block with the same cluster keys, so the honest count still comes from there.
What it buys is robustness to surface damage, which the run now shows is real and
free. The limit on its value is unchanged and is now the argument for the next
generator: the free-text box is a plain `<textarea>` with browser spellcheck on,
over a phone keyboard with autocorrect, so a large share of the nonword typos
this pass generates would never reach us, and the errors that *survive* that
filter are disproportionately **real-word** errors — autocorrect substitutions,
homophones, a dropped word. Character-level damage is the cheap half of the
problem and should be described that way. The cheapest operations — missing
apostrophes and casing — are the ones most worth having, and section 8 already
records a case where casing alone separated a whole library perfectly.

**Migration.** The frozen lexicon is hard-coded in `noise.py` and the pass guards
on "a non-empty lexicon exists for this signal". Both come out at 12.5 / step 3,
when the lexicon moves into the manifest; two lists in two modules drifting apart
is the outcome that guard exists to postpone, not to prevent.

### 12.7 Random autocorrect errors

Still needs thinking about.  Robustness to random noise is good but in reality phones autocorrect rather than leaving spelling errors, so we should aim to introduce this error pattern too

### 12.8 Order of work

**Section 10's "Outstanding" is the live list**; this subsection is only what
the order depends on. Steps 1 to 5 of the original sequence — the blocked
`fever_null` libraries and the proof-of-concept run, fold mode and the sidecar
provenance block, library-level label vectors and declared silence, companions
and the two-arm measurement, and the random-error pass — are all built. The
companion step is the one the list existed to reach.

Section 10's outstanding items come first — fixing `urinary_frequency` and
writing the missing `false` submissions both block reading a result. After
those, the forward plan runs in the order its dependencies force:

1. **Adopt a noised training tree** (12.6), at the top of the plausible damage
   range rather than the middle. The sweep and its transfer cells are positive
   and the cost on clean text is nil. What it still wants is one non-fever signal
   as confirmation, because fever's two decisive libraries are the project's only
   untagged ones and its intervals are therefore the most flattered in the set.
2. Template the filler libraries (12.1). The templates-per-library half of the
   lint report is already built as frames-per-library (section 8). Note this does *not* raise the fragment-count ceiling: that counts
   *sources*, not their size (section 5).
3. Multi-symptom and out-of-scope fragments (12.3, 12.4), which need the JSONL
   library format. The multi-symptom half is now **built but unmeasured**: the
   library exists and no arm draws from it, so what remains here is a
   `--declarative-share` sweep scored on the 67 submissions, and 12.4.
4. Use `--emit-signals all` (12.2), and template the clinical libraries once
   there are enough distinct templates per library for the split arithmetic.

**The step numbers changed** when the completed steps came off this list. Plans
written against the old numbering map on as: old step 5 (templated filler) is
item 2, old step 7 (multi-symptom and out-of-scope fragments) is item 3, and old
step 8 (templated clinical libraries) is item 4. Anything cited as an old step 1
to 4 is built.

**Writing the `true`/`null` labelling policy down (section 9) belongs with any
library work**, not after it. It is the same kind of work as declared silence —
turning a guarantee that lives in the author's head into something declared per
library — and it has to come before any per-library ceiling is declared, because
until the policy exists there is no way to tell an irreducible ceiling from an
inconsistency. The six policies the real submissions land on are the concrete
list to start from: they are not hypothetical gaps, they are cases patients
produce.

**What has changed about the order.** The list used to say nothing on it was
worth starting before the real-text set was scored, because no number said
whether generated data was where the limit is. That has now been answered twice —
2026-08-17 said the data was the limit, 2026-08-19 said a data change fixed it —
so the constraint on the remaining steps is compute and attention rather than
missing evidence. What has not changed is that the 67 submissions are the only
instrument that has ever detected either failure, and every step above is
measured against them.

### 12.8 Two things that surprise people

`documentation/encoder_plans/` holds the plans of record for the steps above;
`multi_symptom_recombination_implementation.md` is the companion ticket's.
Section 10 says what exists and what is outstanding. Two consequences of the
design are worth stating because they are counter-intuitive from here.

**Joint training on merged single-signal datasets needs *no* part of 12.5.**
`fold_bucket` is a pure hash of the cluster key and salt with no knowledge of
signals, so cluster disjointness survives concatenation; and each example still
carries only its own signal's key, which section 7 defines as "no claim, mask
the loss" rather than as a `null` assertion. No silence is declared, so none
needs checking. **The exception is the structural nulls**: labelling one
filler-only example `null` for six signals *is* a silence assertion about the
filler libraries, and the generalised filler lint is what makes it checkable.
Note what that licenses — the filler *libraries* are silent, which is exactly the
guarantee the union needs, and it says nothing about whether a *signal* library
is silent about the others.

**Structural nulls should shrink as 12.2 and 12.3 grow.** They are the least
realistic example type in the dataset: patients rarely submit free text with no
clinical content at all. Companions have already moved most of them off
filler-only text; a dysuria sentence labelled `fever_present: null` is a better
structural null than any filler-only recombination, because it is a null *with
clinical language in it*.

### 12.9 The nocturia / urinary-frequency pair may not need 12.3

Section 4 files the 14 undeclared pairs under "per-line facts a library-level
field cannot state" and points at 12.3. **That may be over-estimating the work**,
on a clinical claim not previously written down here:

> All nocturia is urinary frequency. Not all urinary frequency is nocturia.

If that holds, every line of `nocturia_true` asserts
`urinary_frequency_present: true` — a property of the whole library, wanting a
**library-level cross-signal assertion** alongside `null_on` rather than the
per-line JSONL format. The remaining 13 pairs are ordinary `policy` declarations:
denying or hedging night waking says nothing about daytime frequency, and going
often does not imply going at night.

Two things make this worth acting on rather than recording:

**The undeclared pair is a loss mask, not just a smaller companion pool.**
Section 7's missing-key rule means the `urinary_frequency` head has never seen a
training example containing night-time voiding language at *any* label, and the
nocturia head has never seen a frequency one. Nocturia's ~300 lines are also the
one large pool `urinary_frequency` could not draw companions from — a candidate
explanation for its being the signal that gained least from companions and the
only one to pay a real detection cost (section 10).

**The asymmetry is the point and must not be rounded off.** Only `nocturia_true`
asserts, and only `true`. `nocturia_false` and the five `nocturia_null_*`
libraries stay `null` on urinary frequency. The contrapositive —
`urinary_frequency_false` entailing nocturia `false` — is forced by the rule, is
the riskiest inference in the set, and is deliberately not assumed.

The risk is its own: collapsing the two heads onto the same text could destroy
the frequency-without-nocturia discrimination that motivates the change
(overactive bladder presents with frequency and rarely nocturia; UTI usually with
both). The 67 submissions can measure it — 22 are `urinary_frequency` `true` with
nocturia not `true` — so **any run doing this must declare a bound on that cell
before it trains**.
`planned_updates/urinary_frequency_nocturia_labelling.md` is the provisional
plan, and it is provisional: two unresolved labelling decisions and a diagnostic
step that could retire most of it.

### 12.10 Lexical variant expansion — measured, and not adopted on this evidence

`scripts/synthetic_data/expand.py` rewrites a finished tree with directional,
scoped, literal substitutions, so that the *choice of word* stops carrying the
label. `documentation/encoder_plans/lexical_variant_expansion_implementation.md`
is the plan of record; `reports/synthetic_data/2026-09-03-token-label-association.md`
(the skew) and `reports/encoder_training/2026-09-03-paraphrase-flip-diagnostic.md`
(the flip rate, and the decision to proceed on a Judgement reading) are the two
gates it was built through, and
`reports/encoder_training/2026-09-04-lexical-variant.md` is the result, read
against the pre-registration committed beside it, with
`2026-09-04-lexical-variant-plain-english.md` as the standalone version for a
reader who has not read this document.
`lexical_variant_expansion_v2_provisional.md` is what happens next: the fever
rules move the surface vocabulary by a measured 10.8%, which is why extending
them to six more signals (v1's Task 7) is **abandoned rather than pending**, and
signal-agnostic swap classes reach far more surface from a dozen word lists
instead of thirty-six rules. *(The first draft of that plan quoted 25.8% for six
entity classes. That figure is void: it was computed without applying DD6 layer
2, which freezes `mum`, `wife`, `partner`, `son` and eight other referents and
therefore refuses 61% of the referent sites those classes were counting. Revision
2 of the plan owns the layer-2 change and re-measures the ceiling; until it does,
no reachable-n-gram figure for the classes is quotable.)*

**The short version, so it is not reconstructed from the tables below.** The
mechanism the pass targets is real and the pass removes it: under paraphrase the
clean-trained head flips on 1.9% of changed pairs and **46 of its 74 flips are
`null -> true`** -- displaced fever language read as decisive once the word
changes, which is precisely the fault section 8 and Task 1 describe -- and the
expanded-trained head cuts that to 10 flips out of 33. What the pass does *not*
buy is accuracy: the clean head loses **0.21 decisive points** moving to the
expanded test tree, every interval in the 2x2 overlaps, and the four cells cannot
be compared by McNemar because each is its own report. **The pass is therefore
not extended to the other six signals on this evidence** (Task 7 does not
happen). Rolling machinery across six signals on an unseparated 1.2-point gain is
how a project acquires a component it cannot later evaluate.

**Three things this run established that outlive the decision.**

* **A pre-registered bound can be unmeetable, and saying so is the discipline.**
  The 5-point flip-rate bound was anchored on Task 2's 15.4% over *real*
  submissions; the synthetic test split is drawn from the same libraries as the
  training split and cannot produce a rate of that size. The observed baseline was
  1.89%, so the bound was impossible before a model was trained. It is recorded as
  "not met" and left unedited.
* **The real-text decisive slice cannot establish a harm of this size, in either
  direction.** *(Corrected 2026-09-05. The first version of this bullet claimed
  the synthetic guard had failed to see a real harm, and read a noise draw as a
  signal.)* The expanded arm's real-text decisive accuracy fell 11.1 points while
  its synthetic decisive accuracy rose 1.2 and the guard held. That looks like a
  guard measuring in the wrong place until it is set beside 12.6, which ran the
  same instrument over four arms built by a different augmentation: real-text
  decisive came out 76.7% (clean), 76.7% (r03), 78.9% (r06) and **64.4%** (r12),
  the last a 12.3-point drop on an arm 12.6 concluded was beneficial and
  harmless. Eighteen decisive cells with a +/-23-point half-width and a per-arm
  fold sd of 10-20 points cannot separate an 11-point difference from nothing.
  The lesson is about the instrument, not the guard: a real-text slice this small
  is a validity check and never an effect size, which is what `holdout.py` has
  said all along.
* **The instrument that saw something was the one that cannot rank.** Every bound
  was written against a tree that, by DD8's own argument, cannot contain the
  failure being targeted; the 67 submissions moved and are worth +/-12 points.
  Closing that gap -- a real-text measurement with power -- is the prerequisite
  for spending more GPU here, not more synthetic cells.

The rest of this subsection describes the pass and its measurement as built.

**The fault it targets is a frequency skew, not an exclusive token.** Section 8
records two cases where surface form separated a label class perfectly, both
caught by hand and neither catchable by any check we have. The exclusive-token
shape is now fixed in the libraries; the skew shape is not. `fever` sits on 41 of
45 `fever_null_historical` lines and on 0 of 50 `fever_null_attribution` ones;
`temperature` sits on a quarter of the decisive lines and on no historical line
at all. A model can learn "temperature implies decisive, fever implies displaced"
from that as easily as from a token that appears in exactly one file.

**It is post-processing over the JSONL, for 12.6's reasons plus one of its own.**
`manifest.cluster_key` is `cluster_id or normalise(text)`, so editing a library's
text moves an untagged line's cluster key and therefore its split. A
library-level expander would silently repartition the data and the two arms of
the experiment would stop being comparable. Touching no library file means no
cluster key moves, no split moves, the generator stays byte-identical, the golden
digest holds, the decisive draw is untouched — and every expanded example is
**paired by `example_id`** with its clean original, which is what makes the
decision metric a paired statistic over `--test-dir` rather than a bespoke
corpus. The cost is that a rule cannot be scoped to a *library*: the example text
carries no offsets back to its source fragments, which is what puts aspect and
opener rewrites (Tier C) out of scope.

**It adds no ideas and no effective sample size.** The expanded tree holds
*exactly* as many examples as the clean one. No report may quote an example count
from it as growth. What it buys is the removal of a measured fault, and that is
the only claim available.

**The label-safety question is the whole of the risk, and it is bounded by three
layers**, all of which run when the rule file *loads*:

1. a **declared invariant** on every rule — human-written, human-reviewed, and
   the residual risk;
2. **structural-token invariance** — the sequence of `noise.STRUCTURAL_FROZEN`
   tokens must survive the swap, compared after contraction normalisation so
   `haven't → have not` is not falsely flagged;
3. **signal-lexicon invariance** — the swap may not change whether the phrase
   reads as its own signal, and may not introduce another signal's language that
   the source phrase did not have. This is the per-rule form of "re-run the lint
   over the expanded tree": cheaper, and precise about which rule is at fault.

`STRUCTURAL_FROZEN` is imported from `noise.py` rather than copied — two lists in
two modules drifting apart is the outcome that import exists to prevent.

**Rules are directional, and both directions are usually needed.** Flattening the
fever table needs `fever → temperature` *and* `temperature → fever`, because
`null_historical` over-uses the first exactly as `fever_true` over-uses the
second. Each direction is a separate rule with its own invariant and its own
review; neither implies the other, and a symmetric synonym bag turns "I checked
my temperature and it was high" into "I checked my fever and it was high".
Matching is **whole-word only**, because section 8 already records why: "hot"
appears inside `lithotripsy`, `photos` and `shot`.

**The pass cannot be applied to one label class and not another.** Rules are
scoped to a signal and applied to whole example text with no sight of the label,
so the trap of a partial pass manufacturing exactly the shortcut it exists to
remove is closed by construction rather than by a scope check. The realised
substitution density is measured per label and per label mode anyway, and a gap
there is telemetry about the *libraries* — a class whose lines contain fewer
matchable phrases — rather than evidence of a label-aware pass.

**Two rule kinds are deliberately out of reach**, both found while reading the
Task 2 result, and both are cases where a plausible rule passes layers 2 and 3
and only the human-written invariant stands:

* **Numbers.** No lexicon holds a numeric term and `STRUCTURAL_FROZEN` holds no
  digits, so `38.4 → 37.6` passes both mechanical layers while walking a
  `fever_true` line into saying the temperature was normal — the fever libraries
  encode the ~38.0 threshold in their values. The rule format is literal
  `find`/`replace` strings and **cannot express a numeric range at all**, which
  is the point: numeric variation needs a per-label-class safe band and a fourth
  validation layer, and must arrive as an explicit decision.
* **Certainty adjectives.** `sure`, `certain`, `positive` and `definitely` are in
  no lexicon and not in `STRUCTURAL_FROZEN`, whose modality block stops at
  `probably`/`possibly`. So `"I'm pretty sure" → "I'm pretty certain"` passes both
  layers while moving the axis that *defines* `fever_null_hedged` against
  `fever_true`. Hedge and certainty rewriting is Tier C and out of scope; the
  separate small fix worth making regardless is adding those adjectives to
  `STRUCTURAL_FROZEN`, which is documented to protect modality and currently does
  not.

**A rule can be individually harmless and still manufacture a hit**, which is
what `--dry-run-lint` exists to catch. Layer 3 asks whether a *phrase* changes
signal; a lexicon match needing an anchor and a modifier can be completed by a
swap that carries neither on its own, so `playing up → aching` passes the load
check and then turns "my back has been playing up" — a filler line silent on
flank pain — into flank-pain language. The mode loads the committed libraries
(`check_cells=False`, the lint's own posture), applies every rule
**unconditionally** rather than at `--rate` because the worst case is what a dry
run wants, and diffs `lint.filler_lexicon_hits` and `lint.cross_signal_cells`
against the same two over the originals. Each rule is run alone and then the
whole file is run at once, so a hit that only appears when two rules meet is
attributed to the combination rather than to either rule. A **new** hit of
either kind is a hard failure — including a cross-signal one, which the ordinary
report only reports, because an existing hit is a labelling decision somebody
made and a new one was manufactured by a rule. **Removed** hits are printed and
are not failures: a rule that makes an existing hit disappear has changed what
that library says and wants reading. The mode reads the libraries and writes
nothing. It lives in `expand.py` rather than `lint.py` because the lint's
contract is that it reports on the tree *as committed*; only fragments a rewrite
actually changes are passed to the reports, which is exact (an untouched line
produces untouched hits) and keeps the whole run to a couple of seconds.

**Expansion and the noise pass do not run together.** Both multiply surface
forms, so running them in one experiment makes the result unattributable, and
`expand.py` refuses a tree carrying a `noise` block. If they are ever combined
the order is **expand then noise**: paraphrase first, damage the final surface
second.

**Where the files live.** Rule files are `data/expansion/<signal>.rules.json`
and swap-class files are `data/expansion/classes/<group>.classes.json`, both
deliberately outside `data/synthetic/`, which a test guards as holding nothing
but the fragment libraries and the manifest. `data/expansion/README.md` is what a
rule author reads.

**A run selects which rule files apply, and that selection *is* the arm.**
`--rules {signal,classes,both}` picks the kinds and `--class-groups` picks the
groups; the five arms of the v2 experiment are five invocations of those two
flags and nothing else. Rules from the selected files are concatenated with no
precedence between them — `match_sites` prefers the longest `find` and breaks a
tie by weight, so a hand-written rule and a class rule compete at a shared site
exactly as two hand-written rules do. Three properties are load-time failures
rather than defaults: a named class group with no file, a selection that leaves
a signal with **no rules at all** (an untouched tree written under a name that
says "expanded" is the one silent no-op an arm comparison cannot see), and a
missing `<signal>.rules.json` *when and only when* `--rules` asks for one — a
classes-only arm runs against a signal that has no rule file, which is the whole
point of a class belonging to no signal.

**A class rule moves a person, not a word, and the substitution path knows the
difference.** Per-site independence is right for a word and wrong for a
referent: 40 of 2,506 library lines already carry two, and recombination is
where the exposure actually is. So at a site whose candidate rules *all* carry
an `origin` — every one of them generated from a class file — `expand_example`
memoises the **decision** rather than the target: once a source word has been
drawn for in an example, every later occurrence of it takes the same outcome and
spends no coin of its own. Memoising only the replacement would not be enough,
because the rate coin fires per site and *before* the substitution, so the
second mention would still lose its own coin and leave "my sister … my wife".
Targets are then drawn **injectively within the class**: a candidate whose
replacement is already committed in this example, or already standing in the
source text as another member of the same class, is excluded before the weighted
draw, and a site that empties is skipped and counted as `class_collision`.
Injectivity is scoped to the class and not to the rule set, because `fever →
temperature` firing three times in a line is not a fault at all while `Monday …
Tuesday` both landing on `Friday` is the same fault as the referent one. Both
behaviours are gated on `origin` rather than on a flag, and that gate is what
lets the `v1` arm reproduce 2026-09-04 byte for byte: memoising a repeat removes
a draw and therefore moves the RNG stream, and an anchor whose stream moves is
not an anchor. The sidecar's `expansion.realised.sites` block reports
`memoised` beside `found` and `applied`, because that number is also the size of
the bug the memo prevents.

**The library statistics a rule author decides from are committed code.**
`scripts/synthetic_data/class_stats.py` counts candidate swap-class members over
`data/synthetic/**/*.txt` — occurrences, lines carrying one and lines carrying
more than one, which members `noise.STRUCTURAL_FROZEN` holds frozen, which match
a signal lexicon, and the determiner sitting directly before each occurrence. It
prints and never asserts: it is the instrument authoring decisions are made
against, not a gate, and the gate stays `--dry-run-lint` plus the committed-file
tests. The reason it exists is that the v2 plan's hand-quoted statistics did not
reproduce (referent occurrences ~25% low, healthcare ~20% high), and a table with
no reproducible provenance cannot tell a library edit from a counting error.
Section 4 is the **reachable n-gram ceiling**: distinct n-grams the libraries
hold against the number reachable if every member site took every value of its
class. It is an upper bound rather than a forecast — a real run draws at
`--rate` and leaves `--clean-share` alone — and it replaces revision 1's
uncommitted `+25.8%`. As committed, the sixteen classes reach **+36.8%** distinct
4-grams (referent alone +27.1%, calendar +4.5%, affect +2.4%, setting +1.1%).

**What is actually authored, and what was dropped.** Sixteen classes in four
group files expand to 320 rules from 71 members. Three of the provisional's
candidate lists are not there and each omission is evidence rather than taste:
the healthcare **place** class, because a third of `surgery`'s occurrences are
the operation sense; the healthcare **encounter** class, because `appointment`
is the only member that occurs and the libraries write "an appointment" at eight
sites, where every consonant-initial target is broken English; and `other half`,
which the loader refuses outright as a vowel-initial multi-word member. Members
dropped for the same class of reason: `uncle` (the male class has one "a father"
site), `carer` ("I'm a carer for a lady" survives no swap), `youngest`/`eldest`
(number-ambiguous, so no truthful `number` can be declared for a class holding
them), and `mummy`/`daddy` (a register an adult referent is not written in).

**Compound members exist to shadow, not only to swap.** Twenty-five library
lines spell an in-law relationship, and `match_sites` bounds a whole word on
non-word characters, so the bare `mother` matches inside "my mother-in-law" and
`referent.adult_female` would rewrite the line to "my wife-in-law" — broken
English that moves no lexicon term, so `--dry-run-lint` exits 0 on it. Listing
the compounds as members of their own classes fixes it *because a longer find
wins at a site*: those sites move into a class where every swap is well formed.
The hyphenated and unhyphenated spellings are separate classes and must be,
because layer 2 reads `mother-in-law` as one token and `mother in law` as three,
so the two do not produce the same sequence and no single class may hold both.
The hyphenated forms are therefore `PERSON_CLASSES` keys in their own right,
without which they would produce an empty sequence and pass layer 2 vacuously
rather than fail closed.

**The combined dry-run variant rotates its tie-break.** `rewrite_exhaustively`
breaks a tie at a site by lowest rule id, so a class of *n* members — whose
*n*−1 rules all share a `find` — would have exactly one target exercised by the
whole-file pass and *n*−2 never seen. `dry_run_lint` now runs
`combined_rotations(rules)` whole-file passes, rotating which tied rule wins.
That is *n*−1 passes for a class and **one** for a hand-written rule file, which
keeps a rule file's report byte-identical, label included.

**The rate is load-bearing, and 1.0 is wrong** — measured while authoring the
`fever_present` rules (`reports/synthetic_data/2026-09-04-fever-expansion-rules.md`).
Applying every rule at every site does not flatten a vocabulary association, it
*inverts* it: `temperature`'s decisive-minus-displaced gap runs +0.140 at p = 0
through zero at p ≈ 0.30 to −0.298 at p = 1, where p = (1 − `clean_share`) ×
`rate`. The `DEFAULT_CLEAN_SHARE` docstring anticipates this; the sweep is the
measurement of it. A rule set therefore has an operating point rather than a
switch, and it has to be found per signal from the library statistics before any
model is trained.

**A rule set can be label-blind and still unbalanced.** DD5 closes the trap of a
pass applied to one label class and not another; it does not close a rule set
that happens to cover the phrasing one class uses and not the other's. The
generated `declarative_v1` library states a negative frame as "not had *any
fever*" and "not *a high temperature*", where the positive frame says "had *a
fever*"; a first draft of the fever rules rewrote the negative frame's
temperature phrasing and not its `any fever`, manufacturing a true/false
vocabulary gap of 0.218 at p = 1 where the library had 0.014. The remedy is a
rule for the quantified form, and the general lesson is that a rule set must be
read against the *frames* that carry the labels, not only against the hand-written
libraries. Note also that `declarative_v1` is invisible to the token-association
lint, which excludes generated libraries because their labels are per line.

**How the 2x2 is measured, and why it is twenty trainings rather than ten.** The
experiment is four cells of `train tree × test tree` — clean/clean is the
baseline, clean/expanded asks whether the fault reaches the model at all,
expanded/clean is the guard, expanded/expanded is the robustness cell. Training
depends only on the training tree, so ten trainings would suffice for the
*models*; it does not suffice for the *CLI*, because `--test-dir` is a single
`Path` rather than a repeatable one, so each cell is its own `finetune` and each
trains its own five folds. Four cells × five folds = twenty, roughly forty
minutes of GPU. Teaching `--test-dir` to repeat would save about twenty minutes
and cost a change to the evaluation path; that is not a trade worth making for
one experiment, and what matters is that the pre-registration and the time
estimate both say twenty.

**The decision metric is a paired flip rate, computed post hoc from written
predictions.** No process holds both of an arm's scorings, so each cell writes
its per-example decisions with `finetune --predictions` and
`paired-flip-rate` pairs two of those files by `example_id`.
Three properties of the statistic are load-bearing and each is pinned by a test
in `tests/test_encoder_training_flip.py`:

* **The denominator is the changed pairs.** An example the pass left alone is
  byte-identical on both sides and cannot flip; including it would lower every
  arm's rate by exactly the unchanged share, which is a property of
  `--clean-share` rather than of a model.
* **The resampling unit is the decisive fragment's cluster.** Ten thousand test
  examples sit on a few hundred clusters (section 10); resampling examples would
  report an interval several times too narrow.
* **Ids are qualified by fold.** The generator numbers examples per split, so
  `test-000017` names one example in each of five folds and an unqualified
  pairing would compare four fifths of the tree against the wrong row.

**The guard is scored in the same invocation, because the flip rate alone can be
gamed.** A head that answers `null` to everything has a flip rate of zero, and
two thirds of the test tree is `null`, so the pre-registered bound is on
*decisive-cell* accuracy on the **clean** test tree — the only place the two arms
are scored on identical text. `paired-flip-rate` exits non-zero when it fails.
This is the same instrument section 10 records the companion run needing, for the
same reason.

**The reports say which tree they were scored against.** `_expansion_header`
records the `expansion` block — rate, clean share, seed, the selected class
groups, and **one entry per rule file** with its sha256 — for both the training
tree and, where `--test-dir` is set, the test tree. One entry per file rather
than one block for "the" rule file is forced by the arm selection above: several
files are concatenated before the pass sees them, so the files are all that
survives. Rate and seed reproduce a tree only in combination with every rule
file that was on disk at the time, and those files are hand-edited between runs.
Read against the wrong tree, "clean-trained, expanded test" and "clean-trained,
clean test" are the same sentence.

**The whole sequence is one catalogue entry**, `lexical-expansion-2x2` in
`scripts/training_gui/runs.json`: smoke test, generate, expand, `--dry-run-lint`,
four `finetune` calls, `paired-flip-rate`. `runner.py` stops on the first failing
step, so putting the rule check *inside* the sequence is what makes it a guard
rather than a thing to remember — after the last training step it would only tell
you what the forty minutes had been spent on. No console code changed; the
catalogue already admits `-m` module invocations with literal arguments, which is
all this needs. The swap-class batch of 12.10b is the same shape one size
up, `swap-class-batch`: five arms, thirteen `finetune` invocations and four
`paired-flip-rate` calls, because `--test-dir` is a single path and an arm scored
against two test trees therefore trains its folds twice. `tests/test_training_gui.py` asserts the four cells' `--data-dir`
and `--test-dir` values are exactly the two trees the generate and expand steps
write, in all four combinations — the cheap check that catches a cell pointed at
the wrong tree in CI rather than in a report that silently compared a tree with
itself.

**The bounds are committed before the first run**, in
`reports/encoder_training/2026-09-04-lexical-variant-preregistration.md`: a flip
rate falling by at least 5 points, a decisive-accuracy guard of 0.02, and DD8's
explicit statement that the expected movement on the clean synthetic test set is
*nothing* — because that set is drawn from the same libraries under the same
vocabulary and so cannot contain the failure being targeted. A large synthetic
gain there is evidence of a new shortcut rather than a removed one.

### 12.11 What comes after augmentation — provisional plan only, nothing built

`documentation/encoder_plans/beyond_augmentation_provisional.md` is the plan of
record and is at stage 1: design decisions argued, task list a shape, nothing
built and nothing measured.

**It exists because four dataset changes have now been measured against the same
instrument and only one of them moved a real-text number.** Companions changed
what an example is *made of* and bought 36.5% → 81.0%; the declarative library,
the noise pass and the lexical variant pass each changed how an idea is
*written*, and their real-text effects are respectively negative, nil on clean
text, and inside every interval. The three sentences this document already
carries — 12.3's "a dataset that grows in line count has not grown in
difficulty", 12.6's and 12.10's "adds no ideas and effective sample size is
unchanged" — are that table stated one pass at a time. **The surface-forms
family is worked out, and the swap-class batch of 12.10b is its fifth member.**

Six things the plan proposes, each independent: a real-text corpus split into a
frozen holdout and a *dev* set that decisions may legitimately be made against
(which is what makes §10's Outstanding item 1 fixable rather than merely
recorded); freezing the margin at a pre-registered constant in the meantime,
which costs absolute accuracy and buys readable arm comparisons; an authoring
loop that mines ideas from real text rather than asking a model to invent them;
domain-adaptive pretraining, the one model-side lever needing no labels; a
**question-conditioned** model, measured by a leave-one-signal-out cell, which is
the only proposal that changes the arithmetic of the 165 distinct
`encoder_prompt` wordings across the committed rulesets; and an LLM ceiling
reading on the 67 submissions, which bounds all of the above.

Nothing in it is evidence yet. It is recorded here so that the next augmentation
ticket is a decision rather than a default.

## 13. How experiments are batched

**This section exists because the scarce resource is not what the plans assume.**
Most plans in `documentation/encoder_plans/` sequence a cheap experiment in front
of an expensive one and call the first a gate: run the small thing, read it,
decide whether the big thing is worth paying for. That is the right instinct when
GPU time is the constraint. It is the wrong instinct here, and the numbers say
why.

**The arithmetic.** `arch_encoder_training.md` records roughly **two minutes per
fold on a 12GB card**. The lexical-variant 2×2 is twenty fold-trainings — about
forty minutes. GPU access is one or two nights a week, and a night is about eight
hours, which is **roughly 240 fold-trainings, or twelve times the whole 2×2**.

So compute is not the constraint. **Nights are.** A thirty-minute gate does not
cost thirty minutes; it costs a week, because the decision it produces cannot be
acted on until the next night. That inverts the usual calculus completely.

**The rule that follows.**

> **A gate that needs a GPU runs *inside* the same batch as the thing it gates,
> not in front of it.** What is forfeited is the option of not spending GPU that
> was going spare anyway. What is bought back is a week of calendar per gate.
>
> **A gate that does not need a GPU still runs first.** The lint, the
> token-association report, `expand.py --dry-run-lint`, rate sweeps over library
> text, library statistics, the threshold arithmetic — these cost seconds, they
> change *what gets authored*, and no amount of GPU repairs an unauthored rule or
> a rule set that inverts the association it was meant to flatten.

**Three consequences worth stating, because they change how a plan is written.**

* **Design a night to be arm-rich rather than sequential.** A night must contain
  no decision point that a human has to be awake for. If step 7 depends on
  reading step 6, either fold both readings into one report or run both arms and
  read them in the morning. The composite catalogue entries in
  `scripts/training_gui/runs.json` are the mechanism: a whole sweep is one
  parameterless press, and adding an arm is a catalogue edit rather than a code
  change.
* **Put the cheap failure at the front.** A wasted night should fail in minute
  five, not hour eight. The composites already open with `smoke-cuda` and
  `train-canary` for this reason; an experiment that has a *known* cell — one
  whose value is fixed by deterministic generation and untouched by the change
  under test — should reproduce that cell early rather than discover in the
  read-out that the pipeline moved.
* **The discipline that replaces gating is pre-registration, and it gets more
  important, not less.** A gate used to limit how many comparisons a run could
  make. Twelve arms in one night, read afterwards, will produce a winner by noise
  if the winner is chosen post hoc. So the pre-registration must name the
  **decision arm** and its bounds before the night, and say explicitly which arms
  are exploratory. That is the price of dropping the gate, and it is a real one.

**What this does not license.** It is not an argument for running more arms than
can be interpreted, and it is not an argument against the CPU gates — the two
that came before the lexical variant pass, a per-token label-association lint
report and a paraphrase-flip diagnostic, were both cheap and both designed to be
allowed to fail, and that is exactly the shape a gate should have. It is an
argument against spending a week of calendar to save forty minutes of a resource
that is sitting idle.
