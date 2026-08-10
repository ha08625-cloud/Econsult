# Encoder Training Data (Synthetic Generation)

**LLM INSTRUCTIONS:** This document explains, in plain English, how the synthetic
training data for the encoder is built and why it is built that way. It is the
overview. The full detail lives in `documentation/encoder/` — read
`Fine_tuning_plan.md` for the training strategy and
`synthetic_recombination_implementation_plan.md` for the design decisions behind
the generator. Read `scripts/synthetic_data/*.py` for implementation specifics.

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

The current work covers exactly one signal: `fever_present`, on the
`urinary_symptoms` condition. It is a proof of concept for the *pipeline*, not
an attempt to produce clinical-grade training data — see section 9.

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
  symptoms/fever/      seven libraries, all about fever_present
  symptoms/dysuria/    four libraries, all about dysuria_present
  symptoms/flank_pain/ four libraries, all about flank_pain_present
  filler/              five libraries, verified silent on fever only (section 9)
  drafts/              scratch files, deliberately not libraries (section 4)
  generated/           output, git-ignored
```

Nothing in the code keys off the directory — the manifest gives every library's
path explicitly, so the layout is for humans. It matters as more signals arrive:
"which files carry a dysuria label" should be answerable by looking, not by
reading nineteen manifest entries.

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
| `symptoms/dysuria/dysuria_true.txt` | 24 | Says it hurts to pass urine ("it burns when I pee") |
| `symptoms/dysuria/dysuria_false.txt` | 47 | Says it does not ("weeing itself is fine, no stinging") |
| `symptoms/dysuria/dysuria_null_hedged.txt` | 16 | Genuinely uncertain ("might be a slight sting, could be imagining it") |
| `symptoms/dysuria/dysuria_null_thirdparty.txt` | 14 | *Someone else* has dysuria ("my daughter says it hurts her to wee") |
| `symptoms/flank_pain/flank_pain_true.txt` | 18 | Says there is pain in the side/back below the ribs ("there's a sharp pain in my back on the right side, below my ribs") |
| `symptoms/flank_pain/flank_pain_false.txt` | 24 | Says there is not ("no pain in my back or sides at all") |
| `symptoms/flank_pain/flank_pain_null_hedged.txt` | 10 | Genuinely uncertain ("maybe some tenderness under my ribs, hard to tell") |
| `symptoms/flank_pain/flank_pain_null_thirdparty.txt` | 14 | *Someone else* has flank pain ("my son says his back hurts under his ribs") |
| `filler/tangents.txt` | 110 | Filler: irrelevant chat ("the parking here is impossible") |
| `filler/justifiers.txt` | 100 | Filler: why they need an appointment |
| `filler/emotional.txt` | 60 | Filler: worry and feelings |
| `filler/expectations.txt` | 100 | Filler: what they want to happen — both *what* (tests, drugs, referrals) and *who, how and when* (a named regular GP, continuity, phone vs face to face, timing) |
| `filler/uti_speculation.txt` | 40 | Filler: self-diagnosis ("probably just cystitis") |

**The dysuria and flank_pain libraries are a seed, not a working set.** They
exist so the multi-signal recombination described in section 12.2 has
something real to be built against. Both are proof-of-concept batches, not
libraries sized for real training — see section 10 for what that means for
split coverage. The generator does not read either symptom's libraries yet:
`build_pools` keeps only fragments whose `signal_key` matches the signal
being generated, plus filler, so a dysuria or flank_pain fragment is dropped
from a `fever_present` run rather than treated as filler. That is the
correct behaviour until the machinery in 12.5 exists — treating them as
filler would silently assert they say nothing about fever, and that
guarantee is not yet written down anywhere the code can check.

They were written to be silent about fever (verified: zero hits against the
lint's fever lexicon) and about the other urinary signals, but "verified by
reading them" is exactly the informal guarantee section 12.5 says has to become
an explicit, checkable declaration before it can be relied on.

Two things are worth understanding about this table.

**The five `fever_null` libraries are the hard cases.** They all contain fever
language but none of them means "this patient has a fever right now". A model
that has only seen clear positives and clear negatives will confidently mark
"my son has a fever" as a positive. These five libraries exist to stop that.
They are split into separate files rather than one big one so that we can later
ask "how did the model do specifically on third-party mentions?"

Each one displaces the fever along a different axis, and the axis is the reason
they are separate files rather than one pile of hard cases:

| Library | What is displaced |
|---|---|
| `hedged` | certainty — the patient does not know |
| `thirdparty` | person — someone else is hot |
| `historical` | time — the fever was last month |
| `metaphor` | meaning — the heat word is not about temperature |
| `attribution` | cause — the patient *is* hot, and says why, and it is not a fever |

`attribution` is the hardest of the five and the only one where every surface
cue points the right way. The patient is genuinely, currently warm; it is
genuinely their own body; there is no hedge to pick up on and no past tense to
notice. The only thing separating "I get hot flushes with the menopause" from a
positive is that the patient has named a cause which is not an infection.
A model that has learned "first person + present tense + heat word ⇒ fever"
scores well on the other four and fails this one completely, which is exactly
why it is worth measuring on its own.

Its families are menopause and HRT, thyroid disease, drug side effects
(amitriptyline, SSRIs, tamoxifen, steroids, hormone therapy), exertion and hot
workplaces, skin conditions that flush or burn (rosacea, sunburn, eczema, heat
rash), food and alcohol triggers, lifelong constitutional heat and
hyperhidrosis, bedding, and pregnancy. Note what these have in common with the
`metaphor` library's ambient-temperature family and how they differ: there,
something *other than the patient* is hot. Here the patient is hot and the
cause is elsewhere. Keeping the two apart is what stops either library becoming
"heat word plus an excuse ⇒ null".

**`expectations` covers two families, and the second was a gap.** The first 60
fragments are all about *what* the patient wants done — a test, a drug, a scan,
a referral. The remaining 40 are about *who they want to see and how*: a named
regular GP who has been dealing with them recently, continuity rather than a
fourth locum, a phone call instead of a face-to-face, a female clinician, a slot
that fits round work. This is among the most common things a real patient writes
in a free-text box and it was absent from every library, so a model trained on
the old set had never seen a clinician's name next to a symptom claim. All the
staff names are invented.

**The filler libraries must contain no fever language whatsoever.** A filler
fragment can be paired with anything, including examples labelled "no fever
mentioned". If a filler fragment mentioned a fever, that example's label would
be a lie. There is an automated check for this — see section 8.

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
they were written in a way that produced systematic near-duplicates.
`fever_null_attribution` carries seven, and they are the one case where the
twinning was deliberate rather than accidental: seven ideas were written twice
on purpose so the library teaches that the same attribution in different
clothes carries the same label. The remaining 36 lines are independent ideas.
That is the trade section 12.1 describes — surface robustness bought at the
cost of effective n — taken knowingly and in small doses.

---

## 4. The manifest

`data/synthetic/manifest.json` lists every file that is a real fragment library
and records what each one means (which signal, positive or negative or filler,
which sub-class).

The generator reads this list and **only** this list. It never scans the folder
for `.txt` files. This matters because `data/synthetic/drafts/` contains
`fever_synonyms.jsonl` (scratch notes) and `fever_true.yaml` (an unfinished
template spec). A folder scan would feed both straight into the training text.
They sit in their own directory to make the distinction obvious, but the
manifest, not the directory, is what keeps them out.

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
example would double the evidence for the same claim and teach nothing new.
The consequence is that the decisive fragment's share of the text shrinks as
the count rises — half the words at two fragments, a fifth at five. That is the
point: harder, more realistic examples. It is also why "more is better" is
false here. Past some count each example still carries exactly one supervised
claim, just buried in more noise, so the supervision per token falls while the
cost of training on it rises.

**Fillers within one example always come from different libraries.** Three
fragments from `tangents` read as three consecutive tangents in the same voice.
This puts a hard ceiling on the count: a structural null at N needs N distinct
filler libraries, and there are five. Four is the practical limit against
today's libraries — at five, every structural null would contain exactly one
fragment from each library and would stop being random in composition. Going
higher wants more filler libraries, not a code change. The generator checks
this up front and refuses to start if the requested maximum exceeds the filler
libraries available.

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
fragment ends without punctuation. The live encoder receives raw, unedited
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
other. In the `fever_null` libraries they are not. Those libraries were written
in two passes over the same list of ideas, so the file contains pairs like:

> "A colleague at work went home with a fever on **Monday** and we share a small office"
> "One of my work colleagues went home with a fever on **Tuesday** and we share a small office"

Those are not two independent fragments. If one lands in train and its twin
lands in validation, the validation score is inflated — the model has effectively
already seen that sentence. Roughly 40% of such pairs would be split that way by
chance.

So fragments sharing a `[c01]` marker are hashed **as a group** and always land
in the same split. The markers were added by hand.

This was only done for the `fever_null` libraries. `fever_true` and
`fever_false` have some incidental near-duplicates too, but not the systematic
twinning, and hand-tagging 156 more lines was not judged worth it for a proof of
concept. Instead the lint reports how many there are, so the number is known
rather than assumed (currently 3 and 1).

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

**There is a salt, and it is `"32"`.** The cluster key is hashed as
`"{salt}:{cluster_key}"`. The salt exists because the empty-cell guard (section
10) covers the *whole* manifest, so a library for an unrelated signal that fails
to populate all five buckets blocks a fever run. Only about 1 integer salt in 40
clears that for every library, and the binding constraints are entirely the
dysuria seed libraries — `dysuria_null_thirdparty` has 7 clusters and
`dysuria_null_hedged` has 8, and both must cover 5 buckets. `--find-fold-salt`
searches for salts that work; do not instead "fix" it by editing dysuria.

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
  broken down by label. These rows should agree with each other and with the
  requested mix. If one label ever skews long, fragment count has become a
  proxy for the label, which is exactly the shortcut the mix is meant to rule
  out. Nothing downstream would surface that on its own; it would present as a
  validation score that looks fine and a model that does not transfer.
* `token_counts.by_fragment_count` — text length grouped by count, alongside
  the existing per-label breakdown. Read them together: a length gap between
  labels that the count mix explains is a different problem from one it does
  not.

Two more blocks make the dataset self-describing:

* `folds`, `fold_index` and `split_salt` — the fold configuration, `null`,
  `null` and `""` in default mode. `test` means a different set of clusters
  under every triple, and nothing in the JSONL says which one produced it, so a
  dataset whose fold configuration was not recorded is uninterpretable.
* `fragments` — for every fragment in the generated split, its `library`,
  `cluster_key`, `fragment_type`, `signal_key`, `subclass` and `split`.

That second block is the one with consequences beyond fold mode. Without it,
**nothing in a generated dataset says which fragments are the same idea, or
which libraries are filler**: `meta.fragment_ids` name the library and the
fragment but `cluster_id` was never written out, and `subclass` is only set on
the ambiguous and confounder libraries, so `fever_true`, `fever_false` and all
five filler libraries are indistinguishable from each other in the JSONL.

Any consumer that wants either — and computing effective sample size (section
10) needs both — would otherwise have to re-read the manifest and the `.txt`
libraries. That is rejected because it fails *silently*: edit a library after
generating and the cluster grouping is quietly wrong, producing confidence
intervals that are too narrow with nothing raised anywhere.

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
introduces fever language. Currently zero hits.

Matching is on whole words only. Without that, "hot" matches inside
`lithotripsy`, `photos` and `shot`, and the check would fail against perfectly
clean data on day one.

**Cross-split near-duplicates** — pairs of similar fragments that ended up in
different splits, i.e. the leakage described in section 6. Currently 53, of
which **zero** are in the `fever_null` libraries, which tells us the manual
clustering pass worked. `fever_null_attribution` contributes zero as well,
which is the check that its seven deliberate twin pairs were tagged correctly:
an untagged pair would show up here. The full breakdown:

| Where | Count | Libraries |
|---|---|---|
| Filler | 39 | `justifiers` 14, `expectations` 10, `tangents` 8, `uti_speculation` 4, `emotional` 3 |
| `flank_pain` seed batch | 9 | `flank_pain_false` 3, `flank_pain_null_thirdparty` 3, `flank_pain_true` 3 |
| `fever` decisive | 5 | `fever_true` 3, `fever_false` 2 |

Filler dominates, and those libraries leak in exactly the same way as the
clinical ones but were never clustered. The `flank_pain` batch is unclustered
for the same reason. The four `fever` hits are the incidental near-duplicates
section 6 records as known and untagged.

**Hedge markers** — lines in the positive and negative libraries that sound
uncertain, as a prompt to re-read them by hand (currently 8). Its precision is poor by design
(about 25%), because many fragments deliberately open with uncertainty and then
resolve it: "I thought maybe I was dehydrated but when I checked I had a
temperature" is correctly labelled positive. The report prints a header saying
so. It is a reading list, not a fault list.

**Split coverage** — how many fragments of each library landed in each split,
flagging any empty cell. See section 10.

---

## 9. What this data is and is not worth

Stated plainly, because the numbers this produces are easy to over-read.

**The validation score is a smoke test, not evidence.** Validation holds 15
distinct positive fragments. Every `true` example in validation is a
recombination of those 15 sentences. One unlucky fragment moves the score
several points. The training plan asks for around 200 fragments per signal; we
have roughly half that for `true` and for `false` alike.

**Length may still leak.** Fragment *count* varies but its distribution does
not vary by label (section 5); fragment *length* is not controlled at all.
`fever_true` fragments run from 3 words to 98, while the `fever_null` libraries
sit inside a narrow band — 8–26 words, widened to 9–40 in `fever_null_metaphor`
and 8–33 in `fever_null_attribution`, which is a dent in the problem rather
than a fix.
The medians are close (16 against 14–17), so this is a tail problem rather than
a systematic offset — but a 98-word positive has no counterpart anywhere in the
null libraries, and the model can notice that. The stats sidecar reports median and 90th-percentile
length per label class on every run; if the medians ever drift apart by more
than about 1.5×, length has become a usable proxy for the label. Read that
against `fragment_counts.by_label` in the same sidecar, which says whether the
count mix could account for the gap. Fixing it means rebalancing the libraries,
not changing the generator.

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
fragments each example is still one supervised claim in more noise. Closing it
properly needs more filler libraries and richer fragments, which is library
work.

**Only `fever_present` is covered.** Nothing here produces labels for dysuria,
flank pain or the other urinary signals, and we deliberately do not emit `null`
for them. We have not verified those signals are absent from the filler text —
`uti_speculation` mentions cystitis and kidney infection — so claiming "no
dysuria mentioned" would be inventing a label.

---

## 10. Current state

The generator, its tests and the lint are complete and merged. **The empty-cell
blocker is cleared and the proof-of-concept run produces output.** Every library
now fills all three of its cells; the lint reports `empty cells: 0`.

The generator refuses to run if any library has zero fragments in any split.
Four cells were empty when this was first written, and after the first
`fever_null` expansion one remained:

```
fever_null_metaphor    train 29   val  0   test 4
```

That was the guard doing its job rather than a bug. Metaphor fragments are
clustered into a small number of independent groups — 26 of them at that point,
none of which happened to hash into the 15% validation band. An empty cell would
have meant an entire hard-case sub-class was invisible during evaluation: the
model could be systematically wrong about metaphorical fever language and
nothing would show it.

**It was fixed by writing 21 more `fever_null_metaphor` fragments** (33 → 55,
26 → 47 clusters), which is library work rather than a code change. The
resulting coverage is `train 43 / val 7 / test 5`.

The fragments were written as genuinely new *ideas* rather than rewordings, for
the reason section 12.1 gives: filling a cell with paraphrase-twins of the
training fragments removes the warning light instead of the fault. The lint
confirms it — `fever_null_metaphor` still contributes zero cross-split
near-duplicates.

They also broaden the library's coverage, which was the more interesting
problem. Every one of the 26 original clusters was the same family: *the patient
is worked up — angry, worried or frantic — described with heat words*. A model
trained on that alone learns "heat word next to an emotion word means null",
which is not the rule we want. The new fragments add four families the library
did not have:

* **Ambient temperature** — the flat, the waiting room, the broken heating, the
  weather. Something is hot or cold, and it is not the patient.
* **Dead-metaphor idioms** — "in hot water", "passed around like a hot potato",
  "a load of hot air", "blowing hot and cold", "no sweat", "burning the candle
  at both ends". The heat word carries no temperature meaning at all.
* **`fever` as a mass noun** — world cup fever, cabin fever, a forum working
  itself into a fever.
* **Hay fever** — a real named condition containing the word "fever" that is not
  a fever. Probably the single hardest confounder in the library.

A side benefit: the metaphor library's length band was 9–27 words, against
`fever_true`'s 3–98 (section 9). It is now 9–40, which narrows that gap slightly
rather than closing it.

**The guard checks every library in the manifest, not just the ones for the
signal being generated.** `load_fragments` runs `check_no_empty_cells` over the
whole manifest before `build_pools` ever filters by `signal_key`, so any one
empty cell blocks generation for *every* signal, not only the one whose library
is unbalanced. This is worth knowing before assuming a run against a different
signal would work once that signal's own libraries are balanced.

The dysuria libraries fill all twelve of their cells. `dysuria_false` has been
expanded to 47 fragments, bringing it into the 40–50 target range. The remaining
libraries (`dysuria_true` 24, `dysuria_null_hedged` 16, `dysuria_null_thirdparty`
14) still sit at intermediate sizes. They need the same 40–50 target as everything
else before any number derived from them means anything.

The flank_pain libraries (10–24 fragments each, a proof-of-concept batch) fill
all twelve of their cells too, for the same reason and with the same caveat as
dysuria above — but here "fills all its cells" is close to hollow.
`flank_pain_true` and `flank_pain_false` have **one** fragment each in test, and
`flank_pain_null_hedged` has **four** in train. The guard passes and nothing
derived from those cells would mean anything. Passing the empty-cell guard is a
floor, not a sign of health; see the effective sample size discussion below.

### The proof-of-concept run

10,000 train / 2,000 val / 2,000 test, at default settings, all three splits
generated without error. The two properties the stats sidecar exists to police
(section 7) both hold on train:

* **Fragment count is not a proxy for the label.** The 2-vs-3 fragment mix is
  within a couple of percent of 50/50 in every label class and every label mode
  — `true` 751/742, `false` 1186/1285, `null_structural` 1527/1537,
  `null_ambiguous` 1501/1471.
* **Length is not a proxy for the label.** Median tokens run 36 (`true`), 39
  (`false`), 35 (`null`) — a spread of about 1.11×, well inside the ~1.5×
  threshold section 9 sets. The 90th percentiles agree (53 / 54 / 47).

Every hard sub-class is visible to evaluation, which the metaphor one was not
before the section 10 expansion. Of the 2,000 validation examples, the number
containing a fragment from each is: `attribution` 194, `metaphor` 139,
`thirdparty` 126, `historical` 105, `hedged` 57. Read those with the next
subsection in hand — the 139 metaphor examples are recombinations of **7**
distinct sentences and the 194 attribution ones of **9**.

Note that adding a fifth hard sub-class *diluted* the other four at a fixed
example count: metaphor was 187 validation examples before `attribution`
existed and is 139 now. The ambiguous pool is drawn from uniformly, so a new
library takes its share from the existing ones rather than adding to them.
Nothing is lost — the metaphor clusters behind those examples are the same 7
either way, and section 10's point is that the clusters are what count — but
anyone comparing example counts across dataset versions needs to know why the
number moved.

Section 9 still applies in full to what these numbers are worth. Nothing here
makes the validation score evidence rather than a smoke test — the datasets are
larger, not the fragment pool behind them.

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

For the `fever_present` splits as they stand **under the default 70/15/15
bands** — fragments first, clusters in bold, because the two differ wherever
manual clustering was done. Fold mode (section 6) produces different cells
entirely; the pooled figures are in the table after this one:

| Library | train | val | test |
|---|---|---|---|
| `fever_true` | 66 / **66** | 15 / **15** | 15 / **15** |
| `fever_false` | 68 / **68** | 19 / **19** | 11 / **11** |
| `fever_null_hedged` | 59 / **50** | 8 / **7** | 6 / **6** |
| `fever_null_historical` | 36 / **29** | 6 / **4** | 3 / **3** |
| `fever_null_metaphor` | 43 / **35** | 7 / **7** | 5 / **5** |
| `fever_null_thirdparty` | 37 / **28** | 7 / **5** | 2 / **2** |
| `fever_null_attribution` | 35 / **28** | 9 / **9** | 6 / **6** |

The consequence is worth stating bluntly, because the five `fever_null`
libraries exist precisely so that per-sub-class performance can be measured
(section 3), and that is the measurement this table undermines. A per-sub-class
score on the test split is computed over **2 to 6 independent ideas**; all five
hard sub-classes together are **18**. A third-party recall figure can only take
the values 0, 0.5 or 1.0. Any such number carries an uncertainty of roughly ±30
percentage points and cannot separate two models.

`fever_null_attribution` has the healthiest cells of the five — 9 validation
clusters and 6 test clusters, against metaphor's 7 and 5 — because it was
written after this table existed and sized against it. Six is still six. It
buys a slightly less useless single-split number, not a usable one; fold mode
below is what makes the sub-class readable.

Note also that the clustering that fixed the leakage in section 6 *reduces*
effective n where it applies — correctly, because it stopped counting the same
idea twice. `fever_null_hedged`'s validation cell is 3 fragments but 2 ideas.

This is a library-size problem, not a splitter problem, and section 9's
prescription applies: the fix is more fragments. Until then, an evaluation that
needs these sub-classes must not read a single 5-sentence slice as though it
were a measurement.

**Fold mode (section 6) is the mitigation, and it is built.** Running all five
folds and pooling the predictions makes every cluster a test cluster exactly
once, so the aggregate test set for a sub-class is its whole library:

| Library | fragments | clusters (the effective n) |
|---|---|---|
| `fever_true` | 96 | **96** |
| `fever_false` | 98 | **98** |
| `fever_null_hedged` | 73 | **63** |
| `fever_null_historical` | 45 | **36** |
| `fever_null_metaphor` | 55 | **47** |
| `fever_null_thirdparty` | 46 | **35** |
| `fever_null_attribution` | 50 | **43** |

Note what that is worth and no more. Effective n rises 7- to 17-fold for the
hard sub-classes, but the error bar does **not** shrink 7- to 17-fold:
uncertainty on a proportion goes as 1/√n, so roughly ±30 points becomes roughly
±8. That is still the difference between a number that can carry a conclusion
and one that cannot — a metaphor recall of 0.6 ±0.08 is a finding, 0.5 ±0.30 is
noise. Folds create no new ideas, so 47 metaphor clusters is still 47 and
section 9 applies unchanged.

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
mix applies identically to every label class and there is deliberately no way
to set it per class; see section 5 for why.

Generate one fold of a five-fold run (section 6). Every fold needs all three
splits, so a full run is fifteen invocations:

```
python -m scripts.synthetic_data \
    --folds 5 --fold 0 --split test --count 2000 \
    --out data/synthetic/generated/fever_present.fold0.test.jsonl
```

`--fold` defaults to 0 and the salt defaults to `32`, but neither may be given
without `--folds` — `--fold 3` on its own would silently generate the default
70/15/15 split, and salting the default bands would move the split of every
dataset generated so far. `--folds` must be at least 3: at two folds the test
and validation buckets consume everything and there is nothing left to train on.

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

**Status: none of this is built.** Everything above section 12 describes the
system as it actually is; everything below describes what we are thinking about.
Do not read this section as a description of current behaviour.

Everything here is additionally **not agreed** — it is a provisional plan,
written down so it can be reviewed and turned into an implementation plan later.

There are three ideas and they are additive — each one multiplies a different
axis of the dataset, and they compose. Section 12.5
describes the single mechanism that makes 12.2 to 12.4 safe, and it is the part
that most needs getting right.

### 12.1 Procedural fragment generation

`data/synthetic/drafts/fever_true.yaml` is an unfinished sketch of this idea:
hand-written sentence templates with slots (`I {verb} {adjective} {synonym}`),
plus lists of values for each slot, expanded into fragments automatically. The
`fever_synonyms.jsonl` scratch notes are working towards the same thing. Neither
file is read by anything — see section 4.

**The idea is sound, but only if the unit of work and the unit of splitting both
become the template rather than the fragment.**

The trap is that templating multiplies *surface forms*, not *ideas*, and the
train/val/test split is keyed on ideas. Section 6 exists precisely because
near-duplicate fragments landing on opposite sides of the split inflate the
validation score, and cross-multiplying a template's slots is a machine for
producing near-duplicates. If "I have a high fever" lands in train and "I've got
a really high fever" lands in validation, validation is measuring memorisation.

The arithmetic in the draft YAML makes the point. Its eight templates expand to
about 87 distinct strings, against a declared `target_count` of 800 — so most
strings would be emitted nine or ten times over. Worse, 87 strings is still only
eight ideas. Splitting those eight at 70/15/15 puts roughly **one template in
validation**. Section 9 already describes the current validation set as a smoke
test rather than evidence; done naively, this would shrink the real sample size
while making the fragment count look ten times healthier.

So the rules for adopting it are:

**Templates are the diversity unit, and there need to be a lot of them.** Aim
for 40 or more per library, not 8. This does not reduce how much thinking the
libraries cost — writing 40 good templates is about as much work as writing 40
good fragments. What it buys is 15 to 20 surface forms per unit of thought
instead of one, and it teaches the model that the same claim in different
clothes carries the same label. That is a real gain, but it is a gain in surface
robustness, not in coverage of ideas.

**Emit the template ID as a cluster marker.** If the generator writes ordinary
library lines prefixed `[t04] ...`, the existing loader in
`scripts/synthetic_data/manifest.py` strips the marker and hashes on the cluster
key, so all siblings of a template land in the same split automatically. No
change to the splitter or to `recombine.py` is needed. The hand-tagged `[c01]`
markers and machine-emitted template IDs are the same mechanism.

**This must never be used to fill an empty split cell.** Filling one with
template-siblings of the training fragments would make the guard pass without
fixing what the guard is for: it would remove the warning light rather than the
fault, and the resulting evaluation number would be meaningless. The section 10
cells were cleared with genuinely new ideas for exactly this reason, and any
future empty cell has to be cleared the same way.

**Start with the filler libraries.** `tangents`, `justifiers`, `emotional`,
`expectations` and `uti_speculation` carry no label weight — their only
requirements are that they contain no signal language and that they are varied
enough not to become a shortcut. Templating them is low risk and immediately
useful, and it would take the lint's cross-split near-duplicate count (currently
53, of which 39 are filler) to zero by construction.

**The draft YAML needs restructuring before it is implementable.** Slot values
are declared per synonym but consumed by templates with different grammatical
requirements, so they collide: `adjective` holds `"a high"`, which works in
`I {verb} {adjective} {synonym}` and produces "I've been feeling a high, like I
have a fever" in the `experiential` template. Slots need per-template scoping or
role-carrying names. Contraction joining (`I` + `'ve had`) needs handling too.

A note on the planned spelling-mistake pass: it has the same character as
templating. It makes the text harder and more realistic, which is worth doing,
but it adds no diversity of ideas. Neither templating nor typos should be
allowed to make a dataset *look* richer than its template count says it is. The
lint should report templates per library and clusters per split alongside the
raw fragment counts, so the two numbers are always visible together.

### 12.2 Multi-signal libraries

**Partial status: the dysuria libraries exist (section 3), the engine work does
not.** The fragments are written and declared in the manifest; nothing reads
them yet. Everything below is still the plan.

Add fragment libraries for the other urinary signals — dysuria, urinary
frequency, and so on — each with its own true, false and ambiguous variants, on
the same pattern as the fever libraries. Twenty or so fragments per variant to
begin with. Then recombine them with the fever fragments.

**The payoff is not more examples, it is more label per example.** Today a
`true` example is one positive fever fragment plus one or more fillers, and the
fillers contribute nothing — they are there to supply realistic noise. That is
also the ceiling on the variable fragment count in section 5: longer examples
currently mean more unlabelled filler, not more supervision. If those extra
fragments were instead dysuria fragments with known labels, the same example
would carry two supervised signals:

```json
"labels": {"fever_present": true, "dysuria_present": false}
```

The output format already anticipates this (section 7): `labels` is a dictionary
specifically so that separately-built datasets can merge. Doing it inside a
single run is the same idea one step earlier.

This is additive with 12.1 in the strong sense. Templating multiplies surface
forms within an idea; new signal libraries add genuinely independent ideas, so
cluster diversity actually rises. Sixty new labelled fragments across three
signals is a modest addition to the raw pool but roughly triples the training
signal each example carries.

It also lets the encoder be trained multi-head from one dataset rather than one
dataset per head, which is where we want to end up anyway.

**The constraint this introduces** is that we may only emit a label for a signal
when *every* fragment in the example has a known status for it. That is what
section 12.5 is about, and it is not optional — section 9 records that we
currently refuse to emit `null` for uncovered signals precisely because
`uti_speculation` mentions cystitis and kidney infection, and inventing a "no
dysuria mentioned" label there would be a lie.

### 12.3 Multi-symptom fragments

Fragments that assert more than one signal in a single clause: "I had a fever
and it's been burning when I urinate."

These are closer to how patients actually write than anything currently in the
libraries. Every clinical fragment we have makes exactly one claim, and a model
trained only on that may learn an unstated "one symptom per clause" prior that
real submissions will break immediately.

The caveat is the important part: **these cannot be recombined freely.** Pairing
"I had a fever and burning when I urinate" with a pure `fever_false` fragment
produces an example whose two halves contradict each other, and no single label
is correct. The compatibility check in 12.5 is what makes this safe.

Practically, a multi-symptom fragment cannot have its label implied by which
file it lives in, which is how single-signal libraries work today. It needs a
label vector per line. The likely shape is a JSONL library format alongside the
existing plain-text one, with the manifest declaring which format each library
uses — the manifest already declares `fragment_type` and `subclass` per library,
so `format` fits naturally.

### 12.4 Out-of-scope symptom mentions

Fragments that mention a symptom outside the ruleset entirely: "I had a fever
and a cough." Patients do this often enough that its complete absence is itself
unrealistic.

These are cheap because they are label-neutral — a cough affects no signal the
encoder has a head for, so such a fragment behaves like filler that happens to
sit next to a clinical claim. The one rule is that an out-of-scope mention must
be genuinely silent on every signal in the ruleset. "A cough" is safe; something
like "a burning feeling in my chest" is not, if it could be read against a
burning-related signal. Same check as everything else in 12.5.

A secondary benefit: these put clinical language in more places, which mildly
counteracts the urgency-language leak described in section 9.

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
"silent". Single-signal text libraries get theirs from the manifest for free; the
multi-symptom libraries of 12.3 carry theirs per line.

**Combination is validated on the vector, not the primary signal.** Two
fragments may be combined only if, for every signal, they do not assert
different things. Silent-plus-asserted is fine and yields the assertion.
Silent-plus-silent yields `null`. Asserted-plus-asserted is fine if they agree
and forbidden if they do not.

**The label-first invariant survives, and this is the point.** We still choose
the target label vector first, then filter each pool down to the fragments
compatible with it, then draw. We never generate text and inspect it. Filtering
the pool before drawing, rather than drawing and rejecting, also keeps
generation deterministic and avoids quietly skewing the mix — a
draw-and-reject loop would silently over-sample whichever fragments happen to be
compatible with the most vectors.

**The lint gains a corresponding check.** Today it verifies that filler contains
no fever language (section 8). Generalised, it verifies that every library is
actually silent about everything it claims to be silent about, across all signals
in the ruleset. That check should run in CI against the real libraries in the
same way the current one does, because a library that quietly stops being silent
is a source of permanently wrong labels and nothing else would catch it.

### 12.6 Sequencing

Rough order, on the grounds that each step should leave the pipeline in a state
where the numbers it produces can be trusted:

1. ~~Write real fragments for the blocked `fever_null` libraries and produce the
   proof-of-concept run.~~ **Done** — see section 10. This cleared the empty-cell
   guard honestly and gives us a baseline to compare everything else against.
2. ~~Fold mode and the sidecar provenance block.~~ **Done** — see sections 6, 7
   and 10. It came before everything below because it was the only change on
   this list the encoder training ticket was blocked on, and its effect is on
   how honestly the numbers can be read rather than on what the dataset
   contains.
3. Add label vectors and declared silence (12.5) with the lint check, while
   there is still only one signal and it is cheap to get right.
4. Template the filler libraries (12.1), lowest-risk use of procedural
   generation, and add the templates-per-library and clusters-per-split lint
   reports. This is also what raises the fragment-count ceiling: the ceiling is
   the *number* of filler libraries, not their size (section 5), so templating
   existing ones does not help — new ones do.
5. Add dysuria and frequency libraries (12.2), which is where the multi-head
   training data actually starts. The dysuria libraries are written; the
   engine changes that would let anything read them are step 3's job, and
   deliberately are not being attempted before it.
6. Multi-symptom and out-of-scope fragments (12.3, 12.4), which need the JSONL
   library format.
7. Template the clinical libraries, once there are enough distinct templates per
   library for the split arithmetic to work.

The spelling-mistake pass can slot in anywhere after step 1, since it is a
post-processing step over finished text and independent of everything else.
