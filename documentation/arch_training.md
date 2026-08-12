# Encoder Training Data (Synthetic Generation)

**LLM INSTRUCTIONS:** This document explains, in plain English, how the synthetic
training data for the encoder is built and why it is built that way. It is the
overview and stays at the level of design decisions and data flow. Per-library
editorial history is deliberately not here — read the libraries themselves. The
full detail lives in `documentation/encoder/` — read `Fine_tuning_plan.md` for
the training strategy and `synthetic_recombination_implementation_plan.md` for
the design decisions behind the generator. Read `scripts/synthetic_data/*.py`
for implementation specifics.

Sections 1 to 11 describe the system as it is. **Section 12 is work not yet
built, and not yet agreed** — do not treat it as a description of current
behaviour.

---

## Scope

Turning hand-written sentence fragments into a training dataset for the encoder.
Everything here is **offline tooling**. Nothing in this document runs in the
live application, and `app/` never imports any of it.

**Key files:** `scripts/synthetic_data/` (the generator), `data/synthetic/` (the
fragment libraries), `tests/test_synthetic_recombination.py`

**Related:** `arch_encoder_training.md` covers the offline tooling that trains
and evaluates a head against these datasets, and is the document to read for
what any number it produces is worth. `arch_encoder.md` covers what the encoder
does once it is trained and running.

---

## 1. Why we generate data at all

The encoder's job is to read a patient's free text and output a signal for each
clinical question — for example, "does this text say the patient has a fever?"
with the answer `true`, `false`, or `null` (not mentioned).

To train a model to do that, we need thousands of examples of text paired with
the correct answer. We do not have thousands of real e-consult submissions, and
real patient text could not be used for this without a lot of governance work.
So we write a few hundred sentence fragments by hand and recombine them into
thousands of examples.

Everything trained and measured so far covers one signal: `fever_present`, on
the `urinary_symptoms` condition. It is a proof of concept for the *pipeline*,
not an attempt to produce clinical-grade training data — see section 9.

---

## 2. The one idea that matters: label first, then text

This is the most important design decision in the whole pipeline, and everything
else follows from it.

The generator does **not** write a sentence and then work out what its label
should be. It does the opposite:

1. Decide the label — "this example is going to be a `true` example."
2. *Then* pick fragments that are guaranteed to match that label.

The second step can only draw from a pool that was already sorted by hand. A
`true` example draws from the "positive" library, which contains only fragments
that assert a fever. So the label cannot be wrong about the text, because the
text was chosen to fit the label.

Doing it the other way round — generating text and then labelling it — would
mean something has to read the text and judge it, and every mistake that
something makes becomes a permanently wrong label in the training data. Here
that failure mode does not exist. It is not that we check carefully; it is that
there is no point in the process where the text could influence the label.

---

## 3. The fragment libraries

`data/synthetic/` holds plain text files, one fragment per line. A fragment is a
single clause or sentence a patient might write.

The folder is laid out by what a library says rather than by filename
convention:

```
data/synthetic/
  manifest.json
  symptoms/fever/             seven libraries, all about fever_present
  symptoms/dysuria/           six libraries, all about dysuria_present
  symptoms/urinary_frequency/ seven libraries, all about urinary_frequency_present
  symptoms/nocturia/          seven libraries, all about nocturia_present
  symptoms/flank_pain/        five libraries, all about flank_pain_present
  symptoms/haematuria/        five libraries, all about haematuria_present
  filler/                     five libraries, verified silent on fever only (section 9)
  drafts/                     scratch files, deliberately not libraries (section 4)
  generated/                  output, git-ignored
```

Nothing in the code keys off the directory — the manifest gives every library's
path explicitly, so the layout is for humans. It matters as more signals arrive:
"which files carry a dysuria label" should be answerable by looking, not by
reading forty manifest entries.

Note the filler annotation carefully. The filler libraries are verified silent
about **fever** and nothing else — that check is the lint's, and its lexicon is
a fever lexicon. `uti_speculation` mentions cystitis and kidney infection, so
filler is demonstrably *not* silent on every signal. Section 9 explains what
that costs us today and section 12.5 explains what has to exist before the
claim can be made per-signal.

| Library | Fragments | What it contains |
|---|---|---|
| `symptoms/fever/fever_true.txt` | 96 | Says the patient has a fever ("I had a high temperature") |
| `symptoms/fever/fever_false.txt` | 98 | Says the patient does not ("no temperature, I checked") |
| `symptoms/fever/fever_null_hedged.txt` | 73 | Genuinely uncertain ("I feel a bit off, hard to say") |
| `symptoms/fever/fever_null_metaphor.txt` | 55 | Fever words used non-clinically ("burning up with embarrassment") |
| `symptoms/fever/fever_null_thirdparty.txt` | 46 | *Someone else* has a fever ("my son has a temperature") |
| `symptoms/fever/fever_null_historical.txt` | 45 | A fever, but in the past ("I had one last month") |
| `symptoms/fever/fever_null_attribution.txt` | 50 | Hot now, confidently blamed on something that is not a fever ("I get hot flushes with the menopause") |
| `symptoms/dysuria/dysuria_true.txt` | 45 | Says it hurts to pass urine ("it burns when I pee") |
| `symptoms/dysuria/dysuria_false.txt` | 47 | Says it does not ("weeing itself is fine, no stinging") |
| `symptoms/dysuria/dysuria_null_hedged.txt` | 40 | Genuinely uncertain ("might be a slight sting, could be imagining it") |
| `symptoms/dysuria/dysuria_null_historical.txt` | 38 | Painful urination, but in the past |
| `symptoms/dysuria/dysuria_null_metaphor.txt` | 40 | Burn/sting words that are not about passing urine ("my eyes have been stinging with all the pollen") |
| `symptoms/dysuria/dysuria_null_thirdparty.txt` | 46 | *Someone else* has dysuria ("my daughter says it hurts her to wee") |
| `symptoms/urinary_frequency/urinary_frequency_true.txt` | 46 | Says they are passing urine more often than usual ("I'm going every twenty minutes or so") |
| `symptoms/urinary_frequency/urinary_frequency_false.txt` | 46 | Says they are not ("I go about five times a day and that's exactly what I've always done") |
| `symptoms/urinary_frequency/urinary_frequency_null_hedged.txt` | 42 | Genuinely uncertain ("I might be going more often but I've never counted") |
| `symptoms/urinary_frequency/urinary_frequency_null_historical.txt` | 40 | More often, but in the past |
| `symptoms/urinary_frequency/urinary_frequency_null_metaphor.txt` | 44 | Frequency/flow/urinary words used non-clinically ("a wee bit of a worry", "sales have slowed to a trickle") |
| `symptoms/urinary_frequency/urinary_frequency_null_thirdparty.txt` | 44 | *Someone else* is going more often |
| `symptoms/urinary_frequency/urinary_frequency_null_adjacent.txt` | 40 | A different urinary complaint, silent on how often ("the stream is much weaker than it used to be") |
| `symptoms/nocturia/nocturia_true.txt` | 54 | Says they wake in the night to pass urine |
| `symptoms/nocturia/nocturia_false.txt` | 54 | Says they do not ("I sleep right through") |
| `symptoms/nocturia/nocturia_null_hedged.txt` | 47 | Genuinely uncertain |
| `symptoms/nocturia/nocturia_null_metaphor.txt` | 52 | Night, sleep, toilet and "wee" words used non-urinary ("up all night worrying") |
| `symptoms/nocturia/nocturia_null_thirdparty.txt` | 47 | *Someone else* is up at night |
| `symptoms/nocturia/nocturia_null_historical.txt` | 46 | Night voiding, but in the past |
| `symptoms/nocturia/nocturia_null_attribution.txt` | 51 | Woken by something that is not a need to void, and voids incidentally |
| `symptoms/flank_pain/flank_pain_true.txt` | 48 | Says there is pain in the side/back below the ribs |
| `symptoms/flank_pain/flank_pain_false.txt` | 55 | Says there is not |
| `symptoms/flank_pain/flank_pain_null_hedged.txt` | 53 | Genuinely uncertain |
| `symptoms/flank_pain/flank_pain_null_thirdparty.txt` | 47 | *Someone else* has flank pain |
| `symptoms/flank_pain/flank_pain_null_historical.txt` | 40 | Flank pain, but in the past |
| `symptoms/haematuria/haematuria_true.txt` | 45 | Says there is visible blood in the urine |
| `symptoms/haematuria/haematuria_false.txt` | 45 | Says there is not |
| `symptoms/haematuria/haematuria_null_hedged.txt` | 45 | Genuinely uncertain ("looked a bit pink but I ate beetroot yesterday") |
| `symptoms/haematuria/haematuria_null_thirdparty.txt` | 45 | *Someone else* is passing blood |
| `symptoms/haematuria/haematuria_null_historical.txt` | 45 | Blood in the urine, but in the past |
| `filler/tangents.txt` | 110 | Filler: irrelevant chat ("the parking here is impossible") |
| `filler/justifiers.txt` | 100 | Filler: why they need an appointment |
| `filler/emotional.txt` | 60 | Filler: worry and feelings |
| `filler/expectations.txt` | 100 | Filler: what they want to happen — both *what* (tests, drugs, referrals) and *who, how and when* (a named regular GP, phone vs face to face, timing) |
| `filler/uti_speculation.txt` | 40 | Filler: self-diagnosis ("probably just cystitis") |

Every symptom is sized now; none is still a seed batch. All the decisive and
confounder libraries sit at or above the 40–50 band.

### The null axes, and why they are separate files

The `null` libraries are the hard cases. They all contain the signal's
vocabulary but none of them means "this patient has the symptom right now". A
model that has only seen clear positives and clear negatives will confidently
mark "my son has a fever" as a positive. These libraries exist to stop that, and
they are separate files rather than one pile so that per-sub-class performance
can be measured.

Each one displaces the claim along a different axis:

| Axis | What is displaced |
|---|---|
| `hedged` | certainty — the patient does not know |
| `thirdparty` | person — it is someone else |
| `historical` | time — it was last month |
| `metaphor` | meaning — the word is not being used clinically |
| `attribution` | cause — the surface facts hold, and the patient names a cause that makes the answer `null` |
| `adjacent` | referent — the complaint is current, first-person and clinical, and is simply not about this question |

`attribution` and `adjacent` are the hardest, and for the same structural
reason: every surface cue points the wrong way. There is no hedge, no past
tense and no third party, so a model that has learned "first person + present
tense + topic vocabulary ⇒ positive" scores well on the other axes and fails
these completely.

**Which axes exist is per-signal, and the differences are design decisions, not
oversights.**

* **fever** has all five of `hedged`, `thirdparty`, `historical`, `metaphor`,
  `attribution`, and is the only fully covered signal.
* **urinary_frequency** swaps `attribution` for `adjacent`. Frequency is a
  *rate*, not a disease: a patient going more often because of water tablets or
  hot weather still **is** going more often, so an attribution library would be
  labelling `true` fragments `null`. Those fragments live in
  `urinary_frequency_true` on purpose.
* **nocturia** keeps all five, but its `attribution` axis is the *reason for
  waking* rather than the cause of the urine, because the clinical definition of
  nocturia is waking **because** of the need to void. Waking to void is `true`
  whatever the patient blames it on; woken by something else and voiding
  incidentally is `null`; the same sentence with an explicit denial attached is
  `false` and lives in `nocturia_false`.
* **flank_pain** covers three axes — `hedged`, `thirdparty`, `historical`. It
  has no `metaphor` library (the available idioms are not phrasings a patient
  plausibly uses about their own body) and no `attribution` library, which is a
  real gap: musculoskeletal flank pain with a named cause is common and has
  nowhere to live.
* **haematuria** covers `hedged`, `thirdparty` and `historical`. Its boundary
  rule is that **red or pink urine is `true`, dark/brown/tea-coloured urine is
  not** (concentrated urine, bilirubin and rifampicin all look like that, and
  the text does not say the patient saw blood), and that **blood in the urine is
  `true`, blood on the toilet paper is not** (paper blood may be vaginal, rectal
  or perineal in origin). It has no `metaphor` library and no `attribution`
  library. **`attribution` is the gap that matters, and unlike for
  urinary_frequency the axis genuinely transfers**: beetroot, rifampicin, a red
  toilet block or blood from a period all leave the surface facts intact while
  making the answer something other than `true`, exactly as fever's named causes
  do. Its raw material is the confidently-attributed half of `hedged` plus the
  colour lines the boundary rule keeps out of `true`.

  Two rules follow from the boundary rule and apply to the null libraries. A
  `thirdparty` or `historical` fragment must read as decisively `true` if the
  person or the tense is changed and nothing else — "my sister's lad had tea
  coloured pee" is `null` twice over and so measures nothing. And a fragment
  that never mentions blood or urine is not a haematuria fragment under any
  label: seventeen `hedged` drafts were flank pain with no urinary content, and
  are parked in `drafts/` rather than labelled.

A signal covering fewer axes measures a model against a narrower set of
confounders, so its numbers are not comparable sub-class for sub-class with
fever's.

### Cross-signal silence

The generator does not read other symptoms' libraries in a fever run:
`build_pools` keeps only fragments whose `signal_key` matches the signal being
generated, plus filler. A dysuria fragment is dropped from a `fever_present` run
rather than treated as filler. That is the correct behaviour until the machinery
in 12.5 exists — treating them as filler would silently assert they say nothing
about fever, and that guarantee is not written down anywhere the code can check.

The libraries were written to be silent about the other signals, but that is a
manual reading and it has drifted more than once. Two known exceptions are
recorded here so they are not rediscovered as mysteries:

* Three `flank_pain_false` lines resolve the flank question by contrasting it
  against a urinary one ("it's just uncomfortable when I wee"), which asserts
  `dysuria_present: true` in a library that will eventually be declared silent
  on dysuria. Left in place because rewriting them is a labelling decision.
* `filler` carries "blood test" and "blood pressure tablets", and `tangents`
  carries sleep-disturbance lines. Neither is a wrong label under the structural
  null rules, but both show that the filler libraries are only checked against a
  *fever* lexicon.

**The filler libraries must contain no fever language whatsoever.** A filler
fragment can be paired with anything, including examples labelled "no fever
mentioned", so fever language in filler would make that example's label a lie.
There is an automated check for this — see section 8. Section 12.5 is what would
generalise it to every signal.

### Cluster markers

Some lines start with a tag in square brackets:

```
[c01] My son has had a fever on and off for the past few days
[c01] My daughter's been off school with a temperature up and down for the past few days
```

Those two lines are the same idea written twice. The `[c01]` marker says so. The
generator strips the marker before using the text — it never appears in any
training example. Section 6 explains what the markers are for.

Only the `fever_null` and `dysuria_null` libraries carry markers, because only
they were written in a way that produced systematic near-duplicates. Every other
library was written as independent ideas, so **effective n equals fragment count
there and half of it in the twin-tagged `dysuria_null` libraries** (section 10).
`fever_null_attribution` carries seven deliberate twin pairs, which is surface
robustness bought knowingly at the cost of effective n.

**A marker is a claim, and a wrong one costs both ways.** Grouping two lines
that are not the same idea understates effective n while doing nothing about the
real twinning. Leaving genuine twins in separate clusters lets them land on
opposite sides of the split, which is the leakage the mechanism exists to
prevent. The cross-split near-duplicate report in section 8 is the only feedback
loop on this, so a library that contributes to it is worth re-reading by hand
rather than re-tagging by eye. Growing a library means new *ideas*, not new
twins.

---

## 4. The manifest

`data/synthetic/manifest.json` lists every file that is a real fragment library
and records what each one means (which signal, positive or negative or filler,
which sub-class).

The generator reads this list and **only** this list. It never scans the folder
for `.txt` files. This matters because `data/synthetic/drafts/` contains scratch
notes, an unfinished template spec, and fragments written for the wrong signal
(`flank_pain_cause_hedged.txt`), all of which a folder scan would feed straight
into the training text — and the last of those would look entirely plausible on
the way past. They sit in their own directory to make the distinction
obvious, but the manifest, not the directory, is what keeps them out.

Files on disk but missing from the manifest are ignored. Files in the manifest
but missing from disk stop the run with an error.

---

## 5. How one example is built

Every example is a handful of fragments joined with a space. How many is drawn
per example from a weighted mix — by default 50% two-fragment examples and 50%
three-fragment ones, adjustable with `--fragment-counts`.

**The mix is identical for every label class, and that is the whole safety
argument.** If `true` examples had three fragments and `null` examples had one,
the model could learn "long text means fever" and score well on our data while
having learned nothing about fever. The count is therefore drawn from one
distribution that never sees the label, and the stats sidecar reports the
realised counts *per label* so the property is checked on every run rather than
assumed. (Fragment *length* is a different matter and is not solved — see
section 9.)

There are four kinds of example. Each holds **exactly one decisive fragment**
(none, for a structural null); every additional fragment is filler:

| Kind | What it is made of | Label |
|---|---|---|
| `true` | 1 positive fragment + N−1 filler | `true` |
| `false` | 1 negative fragment + N−1 filler | `false` |
| `null_ambiguous` | 1 hard-case fragment + N−1 filler | `null` |
| `null_structural` | N fillers, all from different libraries | `null` |

By default the mix is 15% `true`, 25% `false`, 60% `null`, and the `null` half
splits 50/50 between the two kinds above. All of these are adjustable from the
command line.

**Only one decisive fragment, however long the example.** Two positives in one
example would double the evidence for the same claim and teach nothing new. The
consequence is that the decisive fragment's share of the text shrinks as the
count rises — half the words at two fragments, a fifth at five. That is the
point: harder, more realistic examples. It is also why "more is better" is false
here. Past some count each example still carries exactly one supervised claim,
just buried in more noise, so the supervision per token falls while the cost of
training on it rises.

**Fillers within one example always come from different libraries.** Three
fragments from `tangents` read as three consecutive tangents in the same voice.
This puts a hard ceiling on the count: a structural null at N needs N distinct
filler libraries, and there are five. Four is the practical limit against
today's libraries. Going higher wants more filler libraries, not a code change.
The generator checks this up front and refuses to start if the requested maximum
exceeds the filler libraries available.

**Why the two kinds of `null` matter.** A `null_structural` example contains no
fever words at all, so it is trivially easy — "no fever words, therefore null".
A `null_ambiguous` example is full of fever words and still means null. If we
only produced the structural kind, the model would learn the trivial rule and
then fall apart the first time a real patient mentions their child's
temperature. The 50/50 default is the single most consequential setting in the
generator.

**The decisive fragment can appear in any position.** The fragments are
shuffled, so the model cannot learn "the fever claim is always the opening
clause".

**Fragments are used verbatim.** Original spelling, casing, typos and
contractions are all preserved. The only change is adding a full stop if a
fragment ends without punctuation. (Section 12.6 proposes a separate pass that
would damage the finished text afterwards; nothing does that today.) The live encoder receives raw, unedited
patient text, so cleaning it up here would train the model on a tidier world
than the one it will meet.

---

## 6. Splitting into train / validation / test

By default, training data is divided three ways: ~70% to train on, ~15% to check
progress against (validation), ~15% held back for a final honest score (test).
Fold mode, below, is the opt-in alternative.

The split happens at the **fragment** level, before any examples are built. A
fragment assigned to validation is never used in a training example. If we split
the finished examples instead, the same fragment would appear on both sides, and
the validation score would partly measure memorisation.

The assignment is a hash of the fragment's own text, so it is stable: adding new
fragments to a library never moves the existing ones between splits.

### Why cluster markers exist

Hashing the text works only if the fragments are genuinely different from each
other. Where a library was written in two passes over the same list of ideas it
contains near-identical pairs, and if one lands in train and its twin lands in
validation, the validation score is inflated. Roughly 40% of such pairs would be
split that way by chance.

So fragments sharing a `[c01]` marker are hashed **as a group** and always land
in the same split. The markers were added by hand, and only to the libraries
that needed them (section 3). `fever_true` and `fever_false` have some
incidental near-duplicates that were not judged worth hand-tagging; the lint
reports how many there are so the number is known rather than assumed.

### Fold mode

`--folds K --fold i` replaces the bands above with K rotations. Each cluster is
hashed into one of K buckets instead of one of 100 bands; bucket `i` becomes
test, bucket `i+1` becomes validation, and the rest become train. At `K=5` that
is 60/20/20, and **every cluster is a test cluster in exactly one fold**, so
running all five and pooling the predictions makes the whole library the
effective test set rather than the 2-to-5-cluster slices a single split leaves
behind (see section 10).

This is what makes a per-sub-class number readable. Pooled over five folds, the
hard sub-classes have 32 to 47 test clusters behind them rather than 2 to 6,
which takes a per-sub-class interval from roughly ±30 points to roughly ±8.
Uncertainty falls as 1/√n, so the interval does not narrow by the same factor as
the count — and folds add no new *ideas* at all, so section 9 still applies in
full.

Three things are worth knowing before using it.

**It is opt-in and the default is untouched.** Without `--folds`, the split is
byte-identical to what it has always been. A fold's train share is 60% rather
than 70%, so fold numbers are not directly comparable to the section 10 tables.

**Fold *i*'s validation clusters are fold *i+1*'s test clusters.** Within a
single fold that is not leakage — each fold trains its own model and never sees
its own test bucket. But a result pooled across folds carries a little optimism,
because each fold's decision threshold was tuned on a sibling fold's test
clusters. Nested cross-validation would remove it and is not worth the cost for
one number per fold. Any report using fold mode has to say so.

**There is a salt, and it is `"0"`.** The value lives in one place —
`DEFAULT_FOLD_SALT` in `scripts/synthetic_data/__main__.py` — and
`test_the_agreed_salt_still_clears_the_real_libraries` re-checks it against the
live manifest on every CI run, so a library that grows past the point where the
pinned salt works fails there rather than halfway through a five-fold training
run. Read the constant, not this sentence, if the two ever disagree.

The cluster key is hashed as `"{salt}:{cluster_key}"`. The salt exists because
the empty-cell guard (section 10) covers the *whole* manifest, so a library for
an unrelated signal that fails to populate all K buckets blocks a fever run.
Which library binds tracks cluster count almost exactly, and it is currently the
twin-tagged `dysuria_null` libraries, whose cluster count is half their fragment
count. That is the honest reading of the salt as a health signal: it is a proxy
for the smallest library measured in *clusters*, and the way to loosen it is to
write new ideas for whichever library is smallest by that measure.
`--find-fold-salt` searches for salts that work; do not instead "fix" it by
editing whichever library is currently binding.

Passing the guard remains a floor, not a health signal. Seven clusters spread
over five buckets means some fold's test cell holds exactly one idea.

---

## 7. Output

The generator writes one JSON object per line:

```json
{
  "example_id": "train-000042",
  "split": "train",
  "text": "I had a high temperature. My neighbour's dealing with some family stuff.",
  "labels": {"fever_present": true},
  "meta": {"label_mode": "true", "fragment_ids": ["fever_true:a1b2c3d4", "tangents:e5f6a7b8"], ...}
}
```

Two points about this shape.

**`labels` is a dictionary, not a single value.** Today it holds one key. When
we later train a model that handles fever *and* dysuria *and* flank pain at
once, each dataset contributes its own key and they merge without any change to
the format.

**A missing key and a `null` value mean different things.** `"fever_present":
null` means "we looked, and the text does not say". A *missing* `fever_present`
key would mean "this dataset says nothing about fever, ignore it when scoring".
Confusing the two when datasets are merged would teach every part of the model
to answer "not mentioned" to every question it was not specifically trained on.
This is written down here because it is the kind of mistake that is invisible
until the model is mysteriously bad.

**How many fragments an example holds is not stored.** It is
`len(meta.fragment_ids)` and nothing else. A second copy of the same number is
one more thing that can disagree with itself.

**Every run also writes a `.stats.json` sidecar** next to the dataset: what was
asked for, what actually came out, the pool sizes, and the text length breakdown
per label. It is the first thing to look at when a training run seems wrong.

Two blocks in it exist specifically to police section 5's safety argument:

* `fragment_counts.by_label` and `.by_label_mode` — the realised count mix
  broken down by label. If one label ever skews long, fragment count has become
  a proxy for the label, which is exactly the shortcut the mix is meant to rule
  out. Nothing downstream would surface that on its own; it would present as a
  validation score that looks fine and a model that does not transfer.
* `token_counts.by_fragment_count` — text length grouped by count, alongside the
  per-label breakdown. Read them together: a length gap between labels that the
  count mix explains is a different problem from one it does not.

Two more blocks make the dataset self-describing:

* `folds`, `fold_index` and `split_salt` — the fold configuration. `test` means
  a different set of clusters under every triple, and nothing in the JSONL says
  which one produced it, so a dataset whose fold configuration was not recorded
  is uninterpretable.
* `fragments` — for every fragment in the generated split, its `library`,
  `cluster_key`, `fragment_type`, `signal_key`, `subclass` and `split`.

That second block is the one with consequences beyond fold mode. Without it,
**nothing in a generated dataset says which fragments are the same idea, or
which libraries are filler**. Any consumer that wants either — and computing
effective sample size (section 10) needs both — would otherwise have to re-read
the manifest and the `.txt` libraries. That is rejected because it fails
*silently*: edit a library after generating and the cluster grouping is quietly
wrong, producing confidence intervals that are too narrow with nothing raised
anywhere.

One sidecar covers one split, and every entry keeps its own `split`, so merging
a fold's three sidecars gives the whole library unambiguously.

### Reproducibility

The same seed, the same libraries and the same settings produce a byte-identical
file. Each example gets its own seed derived from the run seed and its index, so
generating 20,000 examples instead of 10,000 does not reshuffle the first
10,000 — it appends to them.

---

## 8. The lint

`python -m scripts.synthetic_data --lint` reports on library health without
generating anything. It never edits a fragment. Four reports:

**Fever language in filler** — the one with real teeth. Any filler fragment
containing a fever word is flagged. This is enforced by a test that runs against
the real libraries in CI, so it fails if someone edits a filler library and
introduces fever language. Currently zero hits. Matching is on whole words only:
without that, "hot" matches inside `lithotripsy`, `photos` and `shot`.

**Cross-split near-duplicates** — pairs of similar fragments that ended up in
different splits, i.e. the leakage described in section 6. This is the report
that earns its keep: it is what catches a library written as one sentence frame
with the slots swapped out, and it caught exactly that in the first drafts of
several libraries. The fix is always to rewrite the lines as distinct
situations, not to tag them as clusters — tagging records the twinning honestly
while leaving effective n halved.

Two caveats on reading the count. It is **within-library by construction**, so a
library part-written by adapting a sibling signal's library scores clean. And
libraries whose fragments share a small vocabulary (the flank_pain anatomy
words, or a historical library's time markers) run higher on character
similarity between genuinely distinct ideas, so chasing the count to zero by
rewording is partly chasing noise. Rewrite for distinct *ideas*, then read
whatever the count settles at.

A related fault the report cannot see is a **token that appears in exactly one
library**: the word "dysuria" once appeared on 16 lines of
`dysuria_null_metaphor` and nowhere else in the six dysuria libraries, which is
a perfect shortcut separating `null` from `true` and `false`. A clinical term
that lives in one library is a label, not vocabulary — it has to be seeded
across the true, false and null libraries together or not used at all.

The same fault has a **stylistic** form the report cannot see either, and it is
easier to introduce by accident: the first draft of `haematuria_null_hedged` was
written entirely in lowercase with no terminal punctuation, against a `true` and
`false` set that were uniformly capitalised. Nothing normalises emitted text —
`normalise.py` is used for keys only, deliberately — so casing alone separated
the ambiguous class perfectly. Writing style is vocabulary: if one library is
written in a register, all of them have to be.

**Hedge markers** — lines in the positive and negative libraries that sound
uncertain, as a prompt to re-read them by hand. Its precision is poor by design
(about 25%), because many fragments deliberately open with uncertainty and then
resolve it: "I thought maybe I was dehydrated but when I checked I had a
temperature" is correctly labelled positive. It is a reading list, not a fault
list.

**Split coverage** — how many fragments of each library landed in each split,
flagging any empty cell. See section 10.

### Four guards against a bad merge

The lint reports; these four tests fail the build, and they exist because
several library tickets landed in quick succession and their merges concatenated
conflicting edits rather than merging them. They live in
`tests/test_synthetic_recombination.py` and run against the committed tree
rather than any fixture.

* **No duplicate JSON keys in the manifest.** A merge fused two library entries
  into one object. `json.load` resolves duplicate keys last-wins, so the first
  library *silently vanished* rather than raising. Only an `object_pairs_hook`
  sees it.
* **Every `.txt` on disk is declared in the manifest.** The other half of the
  same fault. `load_fragments` checks only the reverse direction, so a library
  the manifest stops naming quietly stops being training data.
* **The section 3 table lists every library exactly once**, and its set of paths
  matches the manifest. A merge once left flank_pain in the table twice, with
  different counts in each block, and a reader has no way to tell which is live.
* **Every count in that table matches its file.** These are per-library totals
  that only a merged tree can compute, so they go stale *on merge* rather than
  in the PR that moved them — which is why review does not catch it.

`documentation/arch_training.md` is in the `rulesets` path filter in
`.github/workflows/tests.yml` for the third and fourth of these. Without it the
workflow's `'!**/*.md'` exclusion means a PR that rewrites the table runs no job
at all.

---

## 9. What this data is and is not worth

Stated plainly, because the numbers this produces are easy to over-read.

**The validation score is a smoke test, not evidence.** Validation holds 15
distinct positive fragments. Every `true` example in validation is a
recombination of those 15 sentences. One unlucky fragment moves the score
several points. The training plan asks for around 200 fragments per signal; we
have roughly half that for `true` and for `false` alike.

**Length may still leak.** Fragment *count* varies but its distribution does not
vary by label (section 5); fragment *length* is not controlled at all.
`fever_true` fragments run from 3 words to 98, while the `fever_null` libraries
sit inside a much narrower band. The medians are close, so this is a tail
problem rather than a systematic offset — but a 98-word positive has no
counterpart anywhere in the null libraries, and the model can notice that. The
stats sidecar reports median and 90th-percentile length per label class on every
run; if the medians ever drift apart by more than about 1.5×, length has become
a usable proxy for the label. Fixing it means rebalancing the libraries, not
changing the generator.

**Urgency language leaks too.** About 17% of `fever_true` fragments bundle the
fever claim with a justification — "I've got three important meetings I can't
miss". Only 8% of `fever_false` and almost none of `fever_null` do. That is
exactly the "sounds urgent, must be positive" shortcut we are trying to prevent.
Pairing with filler washes some of it out. Properly fixing it means splitting
those fragments up, which is library work.

**The examples are still short.** Two or three sentences by default, against
real submissions that are longer and messier still. The variable fragment count
narrows that gap rather than closing it, and it cannot close it on its own: the
count ceiling is the number of filler libraries (section 5), and past a few
fragments each example is still one supervised claim in more noise.

**One dataset carries one signal.** A run emits the key for the signal it was
asked for and nothing else. `fever_present` and `nocturia_present` both have
libraries complete enough to generate from, and `dysuria_present` and
`urinary_frequency_present` too, but a fever dataset carries no dysuria or
nocturia key and vice versa — we deliberately do not emit `null` for the signals
a run did not cover. Doing so would require knowing the filler is silent about
them, and we do not (section 3). Claiming "no dysuria mentioned" on that basis
would be inventing a label. Section 12.5 is the mechanism that would let one
example carry several keys honestly, and it is not built.

### The accuracy ceiling is not the same for every library

A model that scores 70% on one library and 95% on another has not necessarily
failed on the first. Some patient text does not contain enough information for a
competent clinician to answer the question either, and no amount of training
extracts an answer the text does not hold. Where that is so, the ceiling sits
below 100% permanently.

That principle is right, but most of what currently *looks* like irreducible
ambiguity is not, and two distinctions keep it honest.

**`null` is already the answer for "the text does not say".** Section 7 defines
it that way. So a fragment that leaves the clinical question open still has a
determinate correct label, and a model can be held to a high standard on it.
`fever_null_hedged` is the clearest case: nearly every line states the patient's
own uncertainty outright, the right answer is `null`, and 70% there would be a
model failure rather than a ceiling. The same holds for the other hard
sub-classes — each displaces the claim along an axis the text makes explicit.

**The genuine ambiguity is at the `true`/`null` boundary, and it is settled by
policy.** `fever_true` holds "I was burning up and sweating a lot";
`fever_null_hedged` holds "i feel like im roasting on the inside but when i
touch my forehead its perfectly cool". The clinical content is the same; what
separates them is whether the patient volunteered their own doubt. The fever
libraries therefore encode a rule — *unhedged first-person present subjective
heat counts as `true`* — that is defensible, load-bearing on hundreds of
fragments, and **recorded nowhere else**.

For `urinary_frequency_present` the equivalent policy was written down before
any run measured it, which is the pattern to follow for every future signal:

1. **The comparison is against the patient's own baseline, not a population
   norm.** "I've always gone twice an hour and that hasn't changed" is `false`.
2. **Cause is irrelevant to the answer.** If the trips have gone up, the answer
   is `true`, whatever caused it. This is what makes an `attribution` library
   wrong for this signal. We are labelling the `encoder_prompt`'s question, not
   the clinician's inference from it, and the ruleset is where that inference
   belongs.
3. **Adjacent urinary complaints are `null`, not `true`.** Urgency, hesitancy, a
   weak stream and incomplete emptying travel with frequency clinically and say
   nothing about it textually.

Rules 2 and 3 both cut against clinical instinct, which is exactly why they are
worth having in writing: without them the next person to add fragments sorts by
feel, and the inconsistency grows with the library.

That distinction changes what to do about a low number, and there are three
cases, not one:

* **Undeclared policy.** The library is inconsistent about a recurring case
  because nobody decided it. This *presents* as irreducible ambiguity and is
  not. It is fixable by writing the rule down, and it has to be.
* **Irreducible ambiguity.** The policy is decided and this particular fragment
  still sits on the line. The ceiling is real and permanent and further work on
  it is waste.
* **Model or library weakness.** The answer is determinate and the model gets it
  wrong anyway. This is what training and more fragments are for.

The failure mode to guard against is filing the first and third under the
second. "That one is just ambiguous" is available as an explanation for every
error and is unfalsifiable after the fact, which would destroy the question
`arch_encoder_training.md` section 1 exists to answer.

So the rule is that **an expected ceiling below the general target is declared
per library, in writing, before the run that measures it.** A ceiling asserted
after a disappointing report is not a ceiling, it is an excuse. The honest way to
establish one is to measure it: have a second person label a sample of that
library's fragments from the text alone, blind to the file they came from, and
take the agreement rate. Until that measurement exists a declared ceiling is an
assertion, and should be written as one. No ceiling is declared for any library
today.

One consequence runs the other way and is counter-intuitive. **A high score on
an ambiguous boundary is worse news than a low one.** If `true` versus `null` is
decided by whether the patient volunteered doubt, then a model scoring 95% has
learned to detect volunteered doubt — a discourse cue, not a clinical one — and
will carry that straight into real submissions, where the cue and the clinical
fact come apart. It would show in the per-fragment error table
(`arch_encoder_training.md` section 8) as errors concentrated on exactly those
fragments where the cue and the label disagree.

Nothing in the pipeline enforces any of this today. There is no per-library
ceiling field in the manifest and no second-labeller agreement measurement. This
subsection records the position, not a mechanism.

### What sixty-seven real submissions show

Sixty-seven UTI free-text submissions have arrived for the held-out evaluation
set that `planned_updates/encoder_next_steps.md` Ticket A specifies. They are
not labelled yet and nothing has been scored against them. What follows is what
*reading* them says about the libraries — available before any model touches
them, and the cheaper half of their value.

**Length was not the gap; claim density is.** The bullet above says the examples
are still short. On length that is now measurably wrong: the real submissions run
9 to 69 words with a median of 38, and a default two-or-three-fragment example is
28 to 42. What separates them is how much clinical content sits in those words.
The median real submission asserts something about **two** of the six signals and
the longest about all six, while every generated example carries **exactly one**
decisive claim by construction (section 5). So a model trained on this data has
seen roughly the right amount of text and a fraction of the clinical density in
it, and may have learned an unstated one-claim-per-submission prior. That is
section 12.3's argument, now with evidence attached rather than asserted.

**The class prior was a good bet.** Hand-labelling fever across the sixty-seven
gives roughly 9 `true`, 9 `false` and 49 `null` — 13/13/73 against the
generator's 15/25/60 default. Explicit denials are genuinely common: patients
volunteer "no fever", "no blood in my urine", "no back pain" unprompted, which is
the thing the `false` class was a bet on.

**Six labelling policies the libraries never declared, all landed on.** Every one
of these is section 9's *first* case — undeclared policy — and not a ceiling:

* **Chills with no stated heat.** Two submissions say only "feeling hot and cold"
  or "chills". `fever_true` has four chills lines and every one pairs chills with
  an explicit heat claim; `fever_false` has ten, all denials. As the libraries
  stand, a chills word is evidence *against* a fever. Real patients use it as
  evidence for.
* **A number below the clinical threshold that the patient calls a fever.** "a
  mild fever of 37.9°C". Two numeric temperatures exist across ~460 fever
  fragments and both are unambiguously high.
* **Confident hedges.** "im pretty sure ive got a fever now" hedges, and asserts a
  conclusion rather than a sensation, so the section 9 rule (*unhedged
  first-person present subjective heat counts as `true`*) does not reach it.
  `fever_true` holds one such line and `fever_null_hedged` two — split across
  labels, which is what undeclared looks like.
* **Unlateralised "lower back".** Six submissions say it. All three
  `flank_pain_true` lines using the phrase qualify it — "on one side", "and
  sides", "and side" — and all three `flank_pain_false` lines pair it with ribs.
  The library therefore has a rule (lower back counts only with laterality or a
  rib reference) that nobody wrote down, and real patients mostly do not
  lateralise.
* **Particulate urine.** "dark specks in it". The haematuria boundary rule
  (section 3) settles red/pink against dark/brown, and says nothing about this.
* **Discomfort short of pain.** "It doesn't hurt too badly to pee", "There isn't
  much pain, just a strange irritation and discomfort right at the end of
  peeing". The dysuria libraries have no stated floor.

**A composite the libraries never produce.** One submission carries a past fever
and a present one in a single sentence — "last year i was hospitalised with a
severe kidney infection ... with a raging fever and im pretty sure ive got a
fever now". No fragment anywhere holds both, because each library holds one
claim, so the contrast the `historical` axis exists to teach is never shown in
the form patients actually write it.

**Two filler families that do not exist.** *What the patient has already tried*
— cranberry sachets, sodium citrate, D-mannose, paracetamol, ibuprofen, extra
fluids, a pharmacist visit, a just-finished antibiotic course — appears in about
half the submissions; the nearest library is `expectations`, which is about what
they *want*, and 11 of its lines touch treatment at all. *Relevant history and
risk factors* — pregnancy, diabetes, kidney stones, recurrent UTIs, male sex,
age, a previous admission — appears in about a quarter; there are two such lines
across all five filler libraries.

Neither can simply be written as filler, and the reason is section 8's check
working correctly: "I finished a course of nitrofurantoin ten days ago for a
urine infection" and "last year I was hospitalised with a kidney infection" carry
signal language, so as filler they would make every label they were paired with a
lie. They belong either in the `_null_historical` libraries or behind section
12.5's declared silence. Two new filler libraries would also raise the
fragment-count ceiling of section 5 from four to six, which is the only way that
ceiling moves.

**The set is not written in one register.** It splits into three blocks by
punctuation and contraction habits: seven submissions with missing apostrophes in
71% of lines and terminal punctuation in 14%, then forty at 5% and 92%, then
twenty at 0% and 100% with a near-uniform three-sentence shape. Section 8's
principle — *writing style is vocabulary* — applies to an evaluation set as much
as to a library. Here it creates no label shortcut, because register does not
track the label; it creates a coverage problem, because sixty of the
sixty-seven sit in a tidier register than the libraries deliberately aim at, and
the seven that do not are too few to score on their own. **Record each
submission's provenance so the strata can at least be reported apart**, and treat
an aggregate number over the whole set as a number about the tidy register.

**What it can and cannot measure.** The resampling unit is the submission and
there is no cluster structure, so sixty-seven independent observations give
roughly ±11 points at 80% for one overall decisive figure. Ticket A's ±9 assumed
eighty. Per signal it is far thinner — about 9 fever positives, 9 haematuria
positives, 6 flank positives — so any per-signal recall from this set carries
something like ±30 points. That is section 10's problem again, and **fold mode
cannot fix it here**: there are sixty-seven texts and no mechanism makes more.

So it is a *validity* instrument, not a *precision* one. It can show that 83.5%
is really 55%, which is the question that matters most and which nothing else
answers. It cannot rank two models, and per Ticket A it must not be used to
select anything.

**It does not replace the held-out fragment split, and swapping one for the other
would be a mistake.** The two answer different questions. The fold-pooled
recombination test set asks whether the model generalises to *ideas* it has not
seen, in the register it was trained on, and it is the only instrument with
enough effective n to say anything per sub-class. The real set asks whether that
register and that claim density transfer at all. Dropping the first leaves a
single sixty-seven-item number with no sub-class resolution and no way to tell a
library problem from a model one — which is the question
`arch_encoder_training.md` section 1 exists to answer. Run both.

**Provenance is unresolved and gates committing the corpus.** Section 1's reason
for generating data at all is that real patient text needs governance work first.
Whether these submissions are real patient text, clinician-written, or generated
decides both what they are worth as evidence and whether they may live in this
repository, and it has to be recorded per submission before they are used.

---

## 10. Current state

The generator, its tests and the lint are complete and merged. Every library
fills all three of its cells, the lint reports `empty cells: 0`, and the
proof-of-concept `fever_present` run produces output.

**The generator refuses to run if any library has zero fragments in any split**,
and the guard checks every library in the manifest, not just the ones for the
signal being generated: `load_fragments` runs `check_no_empty_cells` over the
whole manifest before `build_pools` filters by `signal_key`. So one empty cell
blocks generation for *every* signal. An empty cell means a hard-case sub-class
is invisible during evaluation — the model could be systematically wrong about
it and nothing would show.

**An empty cell must be cleared with genuinely new ideas, never with
rewordings.** Filling one with paraphrase-twins of the training fragments
removes the warning light instead of the fault. That is how the one blocked
library (`fever_null_metaphor`) was cleared, and the same expansion fixed a more
interesting problem: every original cluster in it was the same family (*the
patient is worked up, described with heat words*), which teaches "heat word next
to an emotion word ⇒ null". The families added — ambient temperature, dead-
metaphor idioms, `fever` as a mass noun, hay fever — are what makes it a library
rather than one idea. `dysuria_null_metaphor` had the identical fault and was
fixed the same way, by replacing clusters rather than adding fragments.

**Fragment count and cluster count come apart, and cluster count is what
matters.** The four twin-tagged `dysuria_null` libraries have roughly half their
fragment count in clusters (19–28 apiece). Every fever library except `true` and
`false` is partly tagged. The urinary_frequency, nocturia, flank_pain and
haematuria libraries carry no markers at all, so their effective n equals their
fragment count — 40 to 55 apiece.

**Nothing has been trained on anything but `fever_present`.** The training
tooling (`arch_encoder_training.md`) is single-signal and wired to
`fever_present`, so the other five signals' libraries are input that nothing yet
consumes. A `haematuria_present` run does now start, and its three null
libraries are what made it possible: `_check_pools` requires a non-empty
ambiguous/confounder pool, so with only `true` and `false` it exited whatever
`--null-ambiguous-ratio` was set to. That guard was right — every `null` example
would otherwise have been a structural one, and those all share a single
resampling unit, so the run would have produced a dataset whose entire `null`
class was a handful of ideas seen thousands of times.

### The proof-of-concept run

10,000 train / 2,000 val / 2,000 test, at default settings, all three splits
generated without error. The two properties the stats sidecar exists to police
(section 7) both hold on train: the 2-vs-3 fragment mix is within a couple of
percent of 50/50 in every label class, and median token counts across labels
span about 1.11×, well inside the ~1.5× threshold section 9 sets.

Every hard sub-class is visible to evaluation. Of the 2,000 validation examples,
the number containing a fragment from each ranges from 57 (`hedged`) to 194
(`attribution`) — but those 194 examples are recombinations of **9** distinct
sentences, which is the point of the next subsection.

Note that adding a fifth hard sub-class *dilutes* the other four at a fixed
example count: the ambiguous pool is drawn from uniformly, so a new library
takes its share from the existing ones rather than adding to them. Nothing is
lost, but anyone comparing example counts across dataset versions needs to know
why the number moved.

### Effective sample size: count fragments, not examples

**This subsection is the canonical statement of the point.** Other documents —
notably `planned_updates/encoder_training_poc_implementation.md` — cross-refer
to it rather than restating the argument. Keep it that way; the one deliberate
exception is the evaluation report, which reproduces it in full because it is
read standalone by people who have not read these docs.

The single easiest way to over-read anything this pipeline produces is to quote
an example count. **The effective sample size of any evaluation slice is the
number of distinct clusters behind it, not the number of examples.** Ten
thousand examples built from 66 training fragments is 66 ideas seen many times.

Clusters rather than fragments, because section 6's whole point is that
`[c01]`-tagged siblings are one idea written twice. They always land in the same
split, so they are one observation, not two.

**Under the default 70/15/15 bands this makes per-sub-class numbers unreadable.**
A 15% slice of a 40-to-70-fragment library is a handful of ideas: for
`fever_present` the test cells hold **2 to 6 clusters** per hard sub-class, 18
across all five. A third-party recall figure computed on 2 clusters can only
take the values 0, 0.5 or 1.0, carries an uncertainty of roughly ±30 percentage
points, and cannot separate two models. Every other signal is in the same range
under the default bands. Note also that clustering *reduces* effective n where it
applies — correctly, because it stopped counting the same idea twice.

**Fold mode (section 6) is the mitigation, and it is built.** Running all five
folds and pooling the predictions makes every cluster a test cluster exactly
once, so the aggregate test set for a sub-class is its whole library — 35 to 63
clusters for the `fever_null` libraries, 40 to 55 for the untagged ones.

Note what that is worth and no more. Effective n rises 7- to 17-fold for the
hard sub-classes, but the error bar does **not** shrink 7- to 17-fold:
uncertainty on a proportion goes as 1/√n, so roughly ±30 points becomes roughly
±8. That is still the difference between a number that can carry a conclusion
and one that cannot — a metaphor recall of 0.6 ±0.08 is a finding, 0.5 ±0.30 is
noise. Folds create no new ideas, so section 9 applies unchanged, and this
remains a library-size problem whose real fix is more fragments.

---

## 11. Running it

Generate one split:

```
python -m scripts.synthetic_data \
    --split train --count 10000 \
    --out data/synthetic/generated/fever_present.train.jsonl
```

Change how long the examples are:

```
python -m scripts.synthetic_data \
    --split train --count 10000 \
    --fragment-counts 2=0.4,3=0.4,4=0.2 \
    --out data/synthetic/generated/fever_present.train.jsonl
```

The weights must sum to 1.0, every count must be at least 2, and the largest
count may not exceed the number of filler libraries — the generator refuses to
start otherwise, rather than failing partway through a 10,000-example run. The
mix applies identically to every label class and there is deliberately no way to
set it per class; see section 5 for why.

Generate one fold of a five-fold run (section 6). Every fold needs all three
splits, so a full run is fifteen invocations:

```
python -m scripts.synthetic_data \
    --folds 5 --fold 0 --split test --count 2000 \
    --out data/synthetic/generated/fever_present.fold0.test.jsonl
```

`--fold` defaults to 0 and the salt defaults to `0` (section 6), but neither may
be given without `--folds` — `--fold 3` on its own would silently generate the
default 70/15/15 split, and salting the default bands would move the split of
every dataset generated so far. `--folds` must be at least 3: at two folds the
test and validation buckets consume everything and there is nothing left to
train on.

Find the salts that populate every bucket of every library, which is what has to
be re-run whenever a library grows:

```
python -m scripts.synthetic_data --folds 5 --find-fold-salt
```

Like `--lint`, it generates nothing and needs no `--split`, `--count` or
`--out`. It sweeps integer salts up to `--salt-search-limit` (default 1000).

Report on library health:

```
python -m scripts.synthetic_data --lint
```

`--lint` honours `--folds`/`--fold` too, so the split-coverage and cross-split
near-duplicate reports describe the fold you are about to generate rather than
the default bands.

The manifest, ruleset and signal default to `data/synthetic/manifest.json`,
`data/uti1.json` and `fever_present`. The generator checks at startup that the
signal actually exists in the ruleset as a Boolean question marked
`send_to_encoder` — a dataset for a signal no encoder head consumes is wasted
effort, and configuration drift is treated as a fail-fast error everywhere else
in this system too.

Output goes to `data/synthetic/generated/`, which is git-ignored. The datasets
are large and exactly reproducible from the libraries plus a seed, so there is
no reason to commit them.

The tool uses the Python standard library only, and adds nothing to
`requirements.txt`.

### The training tooling

`scripts/encoder_training/` consumes what the generator produces: five-fold
generation, the baselines, the two training arms, the decision rule and the
evaluation report. **It has its own spoke — `arch_encoder_training.md` — and
that is where its design decisions live.** The two documents split at the file
boundary: everything that decides what a *dataset* contains is here, everything
that decides what a *number computed from it* means is there.

The one thing worth knowing from this side is the direction of the dependency.
The training tooling reads the JSONL and its `.stats.json` sidecar and nothing
else — never the manifest, never the `.txt` libraries. That is what section 7's
`fragments` provenance block is for, and it is why the block is not optional: a
consumer that re-read the libraries at training time would compute cluster
groupings from files that may have changed since the dataset was generated, and
it would be wrong *silently*.

---

## 12. Provisional: scaling beyond the proof of concept

**Status: none of this is built, and none of it is agreed.** Everything above
section 12 describes the system as it actually is; everything below is a
provisional plan, written down so it can be reviewed and turned into an
implementation plan later.

The ideas below are additive — each one multiplies a different axis of the
dataset, and they compose. Section 12.5 describes the single mechanism that
makes 12.2 to 12.4 safe, and it is the part that most needs getting right.
Section 12.6 is the exception to "additive": it multiplies surface forms only
and adds no new ideas at all, which is the whole of what it is and is not worth.

### 12.1 Procedural fragment generation

`data/synthetic/drafts/fever_true.yaml` is an unfinished sketch of this idea:
hand-written sentence templates with slots (`I {verb} {adjective} {synonym}`),
plus lists of values for each slot, expanded into fragments automatically.
Neither draft file is read by anything — see section 4.

**The idea is sound, but only if the unit of work and the unit of splitting both
become the template rather than the fragment.**

The trap is that templating multiplies *surface forms*, not *ideas*, and the
train/val/test split is keyed on ideas. Cross-multiplying a template's slots is
a machine for producing near-duplicates, which is exactly what section 6 exists
to stop landing on opposite sides of the split. The draft YAML makes the point:
its eight templates expand to about 87 distinct strings against a declared
`target_count` of 800, and 87 strings is still only eight ideas — which at
70/15/15 puts roughly **one template in validation**.

So the rules for adopting it are:

**Templates are the diversity unit, and there need to be a lot of them.** Aim
for 40 or more per library, not 8. This does not reduce how much thinking the
libraries cost — writing 40 good templates is about as much work as writing 40
good fragments. What it buys is 15 to 20 surface forms per unit of thought, and
it teaches the model that the same claim in different clothes carries the same
label. That is a gain in surface robustness, not in coverage of ideas.

**Emit the template ID as a cluster marker.** If the generator writes ordinary
library lines prefixed `[t04] ...`, the existing loader strips the marker and
hashes on the cluster key, so all siblings of a template land in the same split
automatically. No change to the splitter or to `recombine.py` is needed. The
hand-tagged `[c01]` markers and machine-emitted template IDs are the same
mechanism.

**This must never be used to fill an empty split cell** (section 10). It would
remove the warning light rather than the fault.

**Start with the filler libraries.** They carry no label weight — their only
requirements are that they contain no signal language and that they are varied
enough not to become a shortcut. Templating them is low risk and would take the
lint's filler near-duplicate count to zero by construction.

**The draft YAML needs restructuring before it is implementable.** Slot values
are declared per synonym but consumed by templates with different grammatical
requirements, so they collide. Slots need per-template scoping or role-carrying
names, and contraction joining needs handling.

The random-error pass in 12.6 has the same character: it makes the text harder
and more realistic, which is worth doing, but adds no diversity of ideas.
Neither templating nor typos should be allowed to make a dataset *look* richer
than its template count says it is, so the lint should report templates per
library and clusters per split alongside the raw fragment counts.

### 12.2 Multi-signal libraries

**Partial status: the libraries for six signals exist (section 3), the engine
work does not.** A single-signal run against any of them produces a valid
dataset; what does not exist is any way for *one* example to carry more than one
key.

**The payoff is not more examples, it is more label per example.** Today a
`true` example is one positive fever fragment plus fillers, and the fillers
contribute nothing but realistic noise. That is also the ceiling on the variable
fragment count in section 5: longer examples currently mean more unlabelled
filler, not more supervision. If those extra fragments were instead dysuria
fragments with known labels, the same example would carry two supervised
signals:

```json
"labels": {"fever_present": true, "dysuria_present": false}
```

The output format already anticipates this (section 7). It also lets the encoder
be trained multi-head from one dataset rather than one dataset per head, which
is where we want to end up anyway.

**The constraint this introduces** is that we may only emit a label for a signal
when *every* fragment in the example has a known status for it. That is what
section 12.5 is about, and it is not optional.

### 12.3 Multi-symptom fragments

Fragments that assert more than one signal in a single clause: "I had a fever
and it's been burning when I urinate."

These are closer to how patients actually write than anything currently in the
libraries. Every clinical fragment we have makes exactly one claim, and a model
trained only on that may learn an unstated "one symptom per clause" prior that
real submissions will break immediately.

The caveat is the important part: **these cannot be recombined freely.** Pairing
one with a pure `fever_false` fragment produces an example whose two halves
contradict each other, and no single label is correct. The compatibility check
in 12.5 is what makes this safe.

Practically, a multi-symptom fragment cannot have its label implied by which
file it lives in, which is how single-signal libraries work today. It needs a
label vector per line — likely a JSONL library format alongside the existing
plain-text one, with the manifest declaring which format each library uses.

### 12.4 Out-of-scope symptom mentions

Fragments that mention a symptom outside the ruleset entirely: "I had a fever
and a cough." Patients do this often enough that its complete absence is itself
unrealistic.

These are cheap because they are label-neutral — such a fragment behaves like
filler that happens to sit next to a clinical claim. The one rule is that an
out-of-scope mention must be genuinely silent on every signal in the ruleset. "A
cough" is safe; "a burning feeling in my chest" is not. Same check as everything
else in 12.5. A secondary benefit: these put clinical language in more places,
which mildly counteracts the urgency-language leak described in section 9.

### 12.5 What makes 12.2 to 12.4 safe: label vectors and declared silence

All three of the above need one mechanism, and it is a direct generalisation of
the principle in section 2 rather than a departure from it.

**Every library declares what it is silent about.** A `fever_true` fragment
asserts `fever_present: true` and is guaranteed to say nothing about dysuria,
frequency, or any other signal. That guarantee is currently implicit and
unwritten; it needs to become an explicit field in the manifest, because once
other signals exist we are relying on it to decide which labels we are entitled
to emit. Section 7's distinction between a missing key and a `null` value is
exactly what a silence declaration controls: silence on a signal earns a `null`,
absence of a declaration earns no key at all.

**Every fragment therefore has a label vector**, most of whose entries are
"silent". Single-signal text libraries get theirs from the manifest for free;
the multi-symptom libraries of 12.3 carry theirs per line.

**Combination is validated on the vector, not the primary signal.** Two
fragments may be combined only if, for every signal, they do not assert
different things. Silent-plus-asserted is fine and yields the assertion.
Silent-plus-silent yields `null`. Asserted-plus-asserted is fine if they agree
and forbidden if they do not.

**The label-first invariant survives, and this is the point.** We still choose
the target label vector first, then filter each pool down to the fragments
compatible with it, then draw. We never generate text and inspect it. Filtering
the pool before drawing, rather than drawing and rejecting, also keeps
generation deterministic and avoids quietly skewing the mix.

**The lint gains a corresponding check.** Today it verifies that filler contains
no fever language (section 8). Generalised, it verifies that every library is
actually silent about everything it claims to be silent about, across all
signals in the ruleset. That check should run in CI against the real libraries
in the same way the current one does, because a library that quietly stops being
silent is a source of permanently wrong labels and nothing else would catch it.

### 12.6 Random character-level errors

Everything above section 12 preserves fragments verbatim (section 5). That is
right for the libraries — a hand-written fragment already carries whatever
spelling and casing its author typed — but it means the dataset's error profile
is whatever a handful of authors happened to produce while concentrating, which
is a great deal cleaner than what a patient types into a phone at eleven at
night.

The idea is a small script that reads a finished dataset and writes a second one
with random single-character damage: drop a letter, double one, replace one with
a keyboard neighbour, transpose two adjacent letters, drop a space, drop an
apostrophe or a terminal full stop. Transposition and doubling are not in the
original sketch and belong there — "teh" and "temperatureature" are two of the
most common real typing errors, and both are free once the machinery exists.
Keyboard adjacency rather than a uniform random letter is likewise nearly free
(a thirty-line QWERTY neighbour map) and much closer to what a real slip looks
like.

**It is a post-processing pass over the JSONL, not a change to the generator.**
Four reasons, and the third is the one that decides it. The generator stays
byte-identical, so every dataset generated so far is still reproducible. The
pass can be unit-tested against fixed input strings with no manifest, no pools
and no ruleset. One generation run yields both a clean and a noisy dataset from
identical fragments, which is exactly what the experiment below needs and what a
flag inside the generator would make awkward. And deduplication (`generate`'s
`seen` set) keeps operating on clean text, so damage can never be what makes two
otherwise-identical examples look distinct.

Command shape, mirroring the existing tool:

```
python -m scripts.synthetic_data.noise \
    --in  data/synthetic/generated/fever_present.train.jsonl \
    --out data/synthetic/generated/fever_present.train.noisy.jsonl \
    --rate 0.02 --seed 42
```

**Reproducibility on the generator's terms.** Per-example RNG seeded from
`"{noise_seed}|{example_id}"` — keyed on the ID, not the line number — so
noising a 20,000-line file leaves the first 10,000 lines identical to noising
the 10,000-line one, matching section 7. Same input, same seed, same rate gives
a byte-identical file.

#### The label-safety question is the whole of the risk

Section 2's guarantee is that nothing in the pipeline lets the text influence
the label. A pass that edits text *after* the label is fixed inverts that: for
the first time, a mechanical step can make text stop matching its label. Most
edits are harmless — "temperatuer" is still a fever claim to a human and to a
subword model. A few are not:

* one substitution turns `hot` into `not`, and `not` into `hot`;
* `no` is two characters, so any edit inside it is proportionally enormous — "no
  temperature, I checked" becomes "on temperature, I checked";
* dropping a space welds a negation to its neighbour ("nofever"), which is a
  single unknown token to the tokenizer, so the negation can become effectively
  invisible while the label still says `false`;
* the null axes hang on short words too. `my son` → `my sun` is still
  third-party, but any hit on `my`, `his`, `had` or `was` is a coin flip on
  whether the axis the fragment exists to teach survives at all.

Three ways to handle this, and the recommendation is the third.

1. **Accept it and quantify it.** At a 2% per-word rate the damage lands in a
   two-character negation rarely, and roughly uniformly across labels. This is
   defensible, but it leaves permanently wrong labels in the data with nothing
   recording which ones — the exact failure mode section 2 exists to make
   impossible.
2. **Only edit words of five characters or more.** Simple and it protects almost
   everything that matters. It is also unrealistic in a *directional* way: real
   typists hit short words too, so the model would learn that short words are
   always spelled correctly, which is a new artefact traded for an old one.
3. **Declare a protected lexicon and enforce it both ways.** Never edit a token
   in the protected list, and never *produce* a protected token from an
   unprotected one — redraw if an edit would. The list is negation, person,
   tense and modality words plus the signal vocabulary, and half of it already
   exists as `lint.FEVER_LEXICON` for the filler-purity check. This keeps
   section 2's argument intact in spirit: the edits that could change the answer
   are excluded by construction rather than judged to be rare after the fact.

Option 3 has a cost worth naming rather than discovering. The protected list is
**per signal**, and only fever's exists today. A missing or thin list for another
signal fails silently — the pass runs, the output looks fine, and the label noise
is invisible. That is the same shape of problem as 12.5's declared silence, and
the two want the same home: a lexicon field in the manifest, next to the silence
declaration, rather than two lists drifting apart in two modules.

#### The rate must not vary by label, and the sidecar must prove it

This is section 5's fragment-count argument in a new place. The pass is applied
blind to the label, so equality holds by construction — but "by construction" is
also true of the fragment-count mix, and that is measured on every run anyway.
The noisy dataset's sidecar gains a `noise` block: edits per hundred words by
label, by label mode, and the realised tally by operation. If error density ever
tracks the label, the model learns "misspelt ⇒ fever" and every number
downstream of it is worthless, and nothing else in the pipeline would show it.

Two details follow from this. The rate is **per word, not per example**, so it
cannot introduce any correlation with the label beyond the length one section 9
already describes. And **a share of examples should be left completely clean**:
real submissions run from immaculate to unreadable, and a dataset where every
example carries the same error density is its own kind of unrealistic.

#### Which splits get noised is an experimental decision

This is the part most easily got wrong. Noising all three splits and reading one
number cannot answer whether the pass helped: noise makes the test set harder at
the same time as it makes the training set richer, and those move the number in
opposite directions. What answers it is a 2×2 — train on clean and on noisy,
evaluate each against a clean test set and a noisy one:

* noisy-trained vs clean-trained on the **noisy** test set — does training on
  damaged text buy robustness to damaged text? This is the claim being made.
* noisy-trained vs clean-trained on the **clean** test set — does it cost
  anything on text that is fine?

Four training runs against one fold configuration, all four sharing the same
generated data, which is the practical reason the pass is post-processing. How
that is run and reported is `arch_encoder_training.md`'s territory; it is noted
here so the script is built in a shape that permits it rather than one that
forces noise on every split at generation time.

#### What it is worth

Stated the same way as section 9, because this is easy to over-read.

**It adds no ideas, and effective sample size is unchanged.** Sixty-six training
fragments damaged four ways is still sixty-six ideas (section 10). The noisy
dataset carries the same `fragments` provenance block with the same cluster keys,
and the honest count still comes from there.

**There are two reasons the honest outcome may be "no measurable benefit".**
First, a subword tokenizer shatters a misspelt word into pieces carrying little
of the original meaning, so above some rate this is training on noise rather
than on harder text. That rate exists and finding it is part of the experiment,
not something to guess — which is an argument for sweeping two or three rates
rather than picking one.

Second, and more awkward: the free-text box in `frontend/src/screens/EditScreen.tsx`
is a plain `<textarea>` with browser spellcheck left on, and on a phone with
autocorrect on top of that. A large share of the nonword typos this pass
generates would never reach us, because the red squiggle or the autocorrect
catches them first. The errors that *survive* that filter are disproportionately
**real-word** errors — autocorrect substitutions, homophones, the wrong "there",
a dropped word — and those are a different generator entirely, and probably the
more valuable one. Character-level damage is the cheap half of the problem, and
it should be described that way rather than as "making the data realistic".

**The cheapest operations are the ones most worth having.** Missing apostrophes
and casing — "im", "ive", "dont", "cant", all-lowercase, no terminal
punctuation — are extremely common in real free text, cannot produce a different
protected word, and survive spellcheck on most phones because they are what the
keyboard produces. Section 8 already records a case where casing alone separated
a whole library perfectly. These should be the first operations built, not a
footnote to the letter-level ones.

#### Scope boundary

The script never touches `data/synthetic/`. It reads and writes only under
`data/synthetic/generated/`, which is git-ignored. Fragment IDs, cluster keys and
the `fragments` provenance block pass through unchanged — they describe the
fragments, and the fragments are not what was edited. The `token_counts` blocks
*are* recomputed, because deleting a space changes a word count and a sidecar has
to describe the file sitting next to it.

### 12.7 Sequencing

Rough order, on the grounds that each step should leave the pipeline in a state
where the numbers it produces can be trusted:

1. ~~Write real fragments for the blocked `fever_null` libraries and produce the
   proof-of-concept run.~~ **Done** — see section 10.
2. ~~Fold mode and the sidecar provenance block.~~ **Done** — see sections 6, 7
   and 10. It came first because it was the only change on this list the encoder
   training ticket was blocked on.
3. Add label vectors and declared silence (12.5) with the lint check, while
   there is still only one trained signal and it is cheap to get right.
4. Template the filler libraries (12.1), lowest-risk use of procedural
   generation, and add the templates-per-library and clusters-per-split lint
   reports. Note this does *not* raise the fragment-count ceiling: that ceiling
   is the *number* of filler libraries, not their size (section 5), so new
   filler libraries are what raises it.
5. Engine changes for multi-signal examples (12.2). **The library half is
   already done** for six signals; the engine changes that would let one example
   carry several keys are step 3's job and are deliberately not being attempted
   before it. Haematuria still needs at least one confounder library before it
   can generate at all.
6. Multi-symptom and out-of-scope fragments (12.3, 12.4), which need the JSONL
   library format.
7. Template the clinical libraries, once there are enough distinct templates per
   library for the split arithmetic to work.

**The random-error pass (12.6) is independent of all of the above** — it is
post-processing over finished text and touches no other module — so it can slot
in anywhere after step 1. Two things pull on where it actually goes. If the
protected-lexicon option is taken, it wants the manifest field that step 3
introduces, so it either follows step 3 or ships fever-only against a
hand-written list and stays fever-only until step 3 lands. And its apostrophe
and casing operations are cheap, safe and independent of the lexicon question
entirely, so they can go first and on their own.

**Writing down the `true`/`null` labelling policy (section 9) belongs with step
3.** Both are the same kind of work — turning a guarantee that currently lives
in the author's head into something declared per library and checkable — and it
has to come before any per-library accuracy ceiling is declared, because until
the policy exists there is no way to tell an irreducible ceiling from an
inconsistency. The six policies the real submissions land on (section 9) are the
concrete list to start from: they are not hypothetical gaps, they are cases
patients produce.

**Nothing on this list is worth starting before the real-text set is labelled and
scored.** Every step here buys more or better generated data, and no number
produced so far says whether generated data is where the limit is. Ticket A in
`planned_updates/encoder_next_steps.md` is what makes this list either an
investment or an expensive way to improve a score that does not transfer.
