# Encoder Training Data (Synthetic Generation)

**LLM INSTRUCTIONS:** This document explains, in plain English, how the synthetic
training data for the encoder is built and why it is built that way. It is the
overview. The full detail lives in `documentation/encoder/` — read
`Fine_tuning_plan.md` for the training strategy and
`synthetic_recombination_implementation_plan.md` for the design decisions behind
the generator. Read `scripts/synthetic_data/*.py` for implementation specifics.

---

## Scope

Turning hand-written sentence fragments into a training dataset for the encoder.
Everything here is **offline tooling**. Nothing in this document runs in the
live application, and `app/` never imports any of it.

**Key files:** `scripts/synthetic_data/` (the generator), `data/synthetic/` (the
fragment libraries), `tests/test_synthetic_recombination.py`

**Related:** `arch_encoder.md` covers what the encoder does once it is trained.

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
single clause or sentence a patient might write. The tree is organised by what
a library is *about*, not by filename convention:

```
data/synthetic/
  manifest.json
  symptoms/fever/      the six fever libraries
  symptoms/dysuria/    the four dysuria libraries
  filler/              the five signal-free libraries
  scratch/             working notes, not training data
```

`symptoms/<signal>/` is one folder per clinical signal. `filler/` holds
fragments that speak to no signal at all. `scratch/` holds
`fever_synonyms.jsonl` and `fever_true.yaml`, which are notes and an unfinished
spec — they are not libraries and the manifest does not list them.

| Library | Fragments | What it contains |
|---|---|---|
| `symptoms/fever/fever_true.txt` | 96 | Says the patient has a fever ("I had a high temperature") |
| `symptoms/fever/fever_false.txt` | 60 | Says the patient does not ("no temperature, I checked") |
| `symptoms/fever/fever_null_hedged.txt` | 42 | Genuinely uncertain ("I feel a bit off, hard to say") |
| `symptoms/fever/fever_null_metaphor.txt` | 33 | Fever words used non-clinically ("burning up with embarrassment") |
| `symptoms/fever/fever_null_thirdparty.txt` | 46 | *Someone else* has a fever ("my son has a temperature") |
| `symptoms/fever/fever_null_historical.txt` | 45 | A fever, but in the past ("I had one last month") |
| `symptoms/dysuria/dysuria_true.txt` | 14 | Says it hurts to pass urine ("it really stings when I pee") |
| `symptoms/dysuria/dysuria_false.txt` | 12 | Says it does not ("no pain when I pee at all") |
| `symptoms/dysuria/dysuria_null_hedged.txt` | 8 | Genuinely uncertain ("couldn't tell you if it's painful exactly") |
| `symptoms/dysuria/dysuria_null_thirdparty.txt` | 8 | *Someone else* has it ("my daughter says it stings when she wees") |
| `filler/tangents.txt` | 110 | Filler: irrelevant chat ("the parking here is impossible") |
| `filler/justifiers.txt` | 100 | Filler: why they need an appointment |
| `filler/emotional.txt` | 60 | Filler: worry and feelings |
| `filler/expectations.txt` | 60 | Filler: what they want to happen |
| `filler/uti_speculation.txt` | 40 | Filler: self-diagnosis ("probably just cystitis") |

**The dysuria libraries are a shape probe, not a dataset.** They exist so the
multi-signal work in section 12 has something concrete to be designed against —
40-odd fragments against the ~200-per-signal the training plan asks for. They
are deliberately free of fever language (checked by the lint's filler-purity
lexicon), so that a fever fragment and a dysuria fragment could eventually sit
in the same example. Nothing generates from them today: `--signal` takes exactly
one signal, so a run for `fever_present` drops every dysuria fragment on the
floor and vice versa.

Two things are worth understanding about this table.

**The `*_null` libraries are the hard cases.** Each one is full of its signal's
vocabulary while meaning "not this patient, not now". A model that has only seen
clear positives and clear negatives will confidently mark "my son has a fever"
as a positive. These libraries exist to stop that. They are split by sub-class
rather than lumped into one file so that we can later ask "how did the model do
specifically on third-party mentions?"

**The filler libraries must contain no fever language whatsoever.** A filler
fragment can be paired with anything, including examples labelled "no fever
mentioned". If a filler fragment mentioned a fever, that example's label would
be a lie. There is an automated check for this — see section 8.

The same will have to be true of dysuria language, and it currently is **not**:
`filler/expectations.txt` asks for urine tests and cystoscopies, and every line
of `filler/uti_speculation.txt` names cystitis or a bladder infection. That is
harmless while only `fever_present` is generated, and it is the first thing
multi-signal generation trips over — see section 12.

### Cluster markers

Some lines start with a tag in square brackets:

```
[c01] My son has had a fever on and off for the past few days
[c01] My daughter's been off school with a temperature up and down for the past few days
```

Those two lines are the same idea written twice. The `[c01]` marker says so. The
generator strips the marker before using the text — it never appears in any
training example. Section 6 explains what the markers are for.

Only the `fever_null` libraries carry markers, because only they were written in
a way that produced systematic near-duplicates. The dysuria libraries were
written line by line without a second reworded pass, so they have no twins to
tag.

---

## 4. The manifest

`data/synthetic/manifest.json` lists every file that is a real fragment library
and records what each one means (which signal, positive or negative or filler,
which sub-class).

The generator reads this list and **only** this list. It never scans the tree
for `.txt` files. This matters because `data/synthetic/scratch/` contains
`fever_synonyms.jsonl` (working notes) and `fever_true.yaml` (an unfinished
template spec). A folder scan would feed both straight into the training text.
The subfolder layout is a convenience for people, not a rule the loader
enforces: each entry's `file` is just a path relative to the manifest, and the
only constraint is that it must resolve to somewhere inside the manifest's own
directory.

Files on disk but missing from the manifest are ignored. Files in the manifest
but missing from disk stop the run with an error.

---

## 5. How one example is built

Every example is exactly **two fragments** joined with a space. Always two, in
every label class.

That is deliberate. If `true` examples had three fragments and `null` examples
had one, the model could learn "long text means fever" and score well on our
data while having learned nothing about fever. Holding the count constant
removes that shortcut. (Fragment *length* is a different matter and is not
solved — see section 9.)

There are four kinds of example:

| Kind | What it is made of | Label |
|---|---|---|
| `true` | 1 positive fragment + 1 filler | `true` |
| `false` | 1 negative fragment + 1 filler | `false` |
| `null_ambiguous` | 1 hard-case fragment + 1 filler | `null` |
| `null_structural` | 2 fillers, from two different libraries | `null` |

By default the mix is 15% `true`, 25% `false`, 60% `null`, and the `null` half
splits 50/50 between the two kinds above. All of these are adjustable from the
command line.

**Why the two kinds of `null` matter.** A `null_structural` example contains no
fever words at all, so it is trivially easy — "no fever words, therefore null".
A `null_ambiguous` example is full of fever words and still means null. If we
only produced the structural kind, the model would learn the trivial rule and
then fall apart the first time a real patient mentions their child's
temperature. The 50/50 default is the single most consequential setting in the
generator.

**The decisive fragment can appear first or second.** The two fragments are
shuffled, so the model cannot learn "the fever claim is always the opening
clause".

**Fragments are used verbatim.** Original spelling, casing, typos and
contractions are all preserved. The only change is adding a full stop if a
fragment ends without punctuation. The live encoder receives raw, unedited
patient text, so cleaning it up here would train the model on a tidier world
than the one it will meet.

---

## 6. Splitting into train / validation / test

Training data is divided three ways: ~70% to train on, ~15% to check progress
against (validation), ~15% held back for a final honest score (test).

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

**Every run also writes a `.stats.json` sidecar** next to the dataset: what was
asked for, what actually came out, the pool sizes, and the text length breakdown
per label. It is the first thing to look at when a training run seems wrong.

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
different splits, i.e. the leakage described in section 6. Currently 43, of
which **zero** are in the `fever_null` libraries, which tells us the manual
clustering pass worked. Most are in the filler libraries (`justifiers` 14,
`expectations` 10, `tangents` 8), which leak in exactly the same way and were
not clustered.

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
have roughly half that for `true` and a third for `false`.

**Length may still leak.** Fragment *count* is fixed at two, but fragment
*length* is not. `fever_true` fragments run from 3 words to 98, while the
`fever_null` libraries all sit inside a narrow 9–27 word band. The medians are
close (16 against 17–19), so this is a tail problem rather than a systematic
offset — but a 98-word positive has no counterpart anywhere in the null
libraries, and the model can notice that. The stats sidecar reports median and
90th-percentile length per label class on every run; if the medians ever drift
apart by more than about 1.5×, length has become a usable proxy for the label.
Fixing it means rebalancing the libraries, not changing the generator.

**Urgency language leaks too.** About 17% of `fever_true` fragments bundle the
fever claim with a justification — "I've got three important meetings I can't
miss". Only 8% of `fever_false` and almost none of `fever_null` do. That is
exactly the "sounds urgent, must be positive" shortcut we are trying to prevent.
Pairing with filler washes some of it out. Properly fixing it means splitting
those fragments up, which is library work.

**The examples are about two sentences long.** Real submissions are longer and
messier. A model trained only on this will meet a different distribution in
production. Expanding to variable-length, multi-clause blurbs is a later phase.

**Only `fever_present` is covered.** Nothing here produces labels for dysuria,
flank pain or the other urinary signals, and we deliberately do not emit `null`
for them. We have not verified those signals are absent from the filler text —
`uti_speculation` mentions cystitis and kidney infection — so claiming "no
dysuria mentioned" would be inventing a label.

---

## 10. Current state and the open blocker

The generator, its tests and the lint are complete and merged. **The proof-of-
concept run has not been produced yet**, because of one data problem.

The generator refuses to run if any library has zero fragments in any split, and
three cells are currently empty:

```
fever_null_metaphor      train 29   val  0   test  4
dysuria_null_hedged      train  6   val  2   test  0
dysuria_null_thirdparty  train  5   val  0   test  3
```

This is the guard doing its job rather than a bug. These libraries are small —
33 fragments for `fever_null_metaphor`, 8 each for the two dysuria ones — and
after clustering they are fewer independent groups still, so a 15% share can
round to nothing. An empty cell would mean an entire hard-case sub-class was
invisible during evaluation: the model could be systematically wrong about
third-party mentions and nothing would show it.

Note the guard is global, not per signal. The two dysuria cells block a
`fever_present` run even though no dysuria fragment can reach a fever example —
`build_pools` filters them out by `signal_key`. That is a real wrinkle the
multi-signal work has to resolve; see section 12.

**The fix is to write more fragments** for those libraries, ideally to 40–50
each, which is library work rather than a code change. Until then the lint runs
(it deliberately skips the guard) but generation does not.

---

## 11. Running it

Generate one split:

```
python -m scripts.synthetic_data \
    --split train --count 10000 \
    --out data/synthetic/generated/fever_present.train.jsonl
```

Report on library health:

```
python -m scripts.synthetic_data --lint
```

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

---

## 12. Combining signals (not built)

The dysuria libraries exist so this section can be written against something
real. **No code supports multi-signal generation yet.** This is the open design
question, recorded here so the next planning pass does not have to rediscover
it.

The goal: one example whose text carries a fever claim *and* a dysuria claim,
labelled `{"fever_present": true, "dysuria_present": true}`. That is what the
encoder actually meets in production — a patient writes one blurb covering
several symptoms — and it is the point of the `labels` dictionary in section 7.

### The blocker is data, not code

Section 2's guarantee is that the label cannot be wrong about the text, because
the text was chosen to fit the label. Extending that to two signals extends what
must be guaranteed about *every* fragment in the example, not just the decisive
one. To emit `{"fever_present": true, "dysuria_present": null}`, the fever
fragment and its partner must both be silent on dysuria. Right now that is not
true of the filler libraries: `expectations` asks for urine tests and bladder
cameras, and all 40 lines of `uti_speculation` name cystitis or a bladder
infection. Pair one with a fever positive, call it "no dysuria mentioned", and
the label is a lie of exactly the kind section 2 exists to make impossible.

So the honest ordering is: clean the libraries first, change the engine second.
Anything else produces a dataset that looks fine and teaches the wrong thing.

### What changes in the engine

Roughly in dependency order:

1. **Silence becomes a declaration.** A library says which signals it is known
   to be silent on. The generator emits `null` for a signal only when every
   fragment in the example declares silence on it, and omits the key otherwise
   — which is the "absent key means mask this head" contract from section 7,
   finally load-bearing rather than aspirational.
2. **The lint's lexicon becomes per-signal.** `FEVER_LEXICON` is one hardcoded
   tuple today. It becomes a lexicon per signal, and filler purity is checked
   against all of them. The CI test currently asserts an empty baseline; the
   dysuria baseline will not be empty on day one, so it needs either a
   populated baseline or the library clean-up above done first.
3. **The empty-cell guard becomes per-run.** It is global today, which is why
   two small dysuria libraries currently block a `fever_present` run that cannot
   reach a dysuria fragment (section 10). It should check only the libraries
   feeding the signals being generated.
4. **Fragment count needs re-deciding, now rather than later.** It is pinned at
   two so that count cannot proxy the label (section 5). Two signals still fit —
   two decisive fragments and no filler — but three do not, and changing the
   constant later invalidates every dataset generated before it. Pinning it at
   `signals + 1` or a flat four, padding unused slots with filler, keeps the
   invariant and stops the question recurring per signal.
5. **The label distribution becomes joint.** `--dist` covers one signal's
   three-way split. Two signals is nine cells. Sampling each signal
   independently is the simple option, but at current settings it makes
   `true/true` about 2% of examples — and fever-with-dysuria is precisely the
   clinically interesting combination. Deliberately over-sampling it is
   defensible, but it distorts the prior and would have to be written down.
6. **`--signal` becomes `--signals`,** the ruleset check runs over each, and
   `GENERATOR_VERSION` is bumped.

Splitting needs no change: splits are assigned per fragment and `build_pools`
filters by split before anything else, so a train fever fragment can never be
combined with a validation dysuria fragment.
