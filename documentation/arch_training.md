# Encoder Training Data (Synthetic Generation)

**LLM INSTRUCTIONS:** This document explains, in plain English, how the synthetic
training data for the encoder is built and why it is built that way. It is the
overview. The full detail lives in `documentation/encoder/` — read
`Fine_tuning_plan.md` for the training strategy and
`synthetic_recombination_implementation_plan.md` for the design decisions behind
the generator. Read `scripts/synthetic_data/*.py` for implementation specifics.

Sections 1 to 11 describe the system as it is. **Section 12 is a provisional
plan for work not yet started or agreed** — do not treat it as a description of
current behaviour.

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
single clause or sentence a patient might write.

| Library | Fragments | What it contains |
|---|---|---|
| `fever_true.txt` | 96 | Says the patient has a fever ("I had a high temperature") |
| `fever_false.txt` | 60 | Says the patient does not ("no temperature, I checked") |
| `fever_null_hedged.txt` | 24 | Genuinely uncertain ("I feel a bit off, hard to say") |
| `fever_null_metaphor.txt` | 18 | Fever words used non-clinically ("burning up with embarrassment") |
| `fever_null_thirdparty.txt` | 20 | *Someone else* has a fever ("my son has a temperature") |
| `fever_null_historical.txt` | 20 | A fever, but in the past ("I had one last month") |
| `tangents.txt` | 110 | Filler: irrelevant chat ("the parking here is impossible") |
| `justifiers.txt` | 100 | Filler: why they need an appointment |
| `emotional.txt` | 60 | Filler: worry and feelings |
| `expectations.txt` | 60 | Filler: what they want to happen |
| `uti_speculation.txt` | 40 | Filler: self-diagnosis ("probably just cystitis") |

Two things are worth understanding about this table.

**The four `fever_null` libraries are the hard cases.** They all contain fever
language but none of them means "this patient has a fever right now". A model
that has only seen clear positives and clear negatives will confidently mark
"my son has a fever" as a positive. These four libraries exist to stop that.
They are split into separate files rather than one big one so that we can later
ask "how did the model do specifically on third-party mentions?"

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

Only the `fever_null` libraries carry markers, because only they were written in
a way that produced systematic near-duplicates.

---

## 4. The manifest

`data/synthetic/manifest.json` lists every file that is a real fragment library
and records what each one means (which signal, positive or negative or filler,
which sub-class).

The generator reads this list and **only** this list. It never scans the folder
for `.txt` files. This matters because `data/synthetic/` also contains
`fever_synonyms.jsonl` (scratch notes) and `fever_true.yaml` (an unfinished
template spec). A folder scan would feed both straight into the training text.

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
four cells are currently empty:

```
fever_null_hedged      train 21   val  2   test 0
fever_null_historical  train 16   val  4   test 0
fever_null_metaphor    train 16   val  0   test 1
fever_null_thirdparty  train 16   val  4   test 0
```

This is the guard doing its job rather than a bug. These libraries are only
18–24 fragments each, and after clustering they are 10–14 independent groups, so
a 15% share can round to nothing. An empty cell would mean an entire hard-case
sub-class was invisible during evaluation — the model could be systematically
wrong about third-party fever mentions and nothing would show it.

**The fix is to write more fragments** for those four libraries, ideally to
40–50 each, which is library work rather than a code change. Until then the lint
runs (it deliberately skips the guard) but generation does not.

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

## 12. Provisional: scaling beyond the proof of concept

**Status: none of this is built, and none of it is agreed.** This section is a
provisional plan, written down so it can be reviewed and turned into an
implementation plan later. Everything above section 12 describes the system as
it actually is; everything below describes what we are thinking about. Do not
read this section as a description of current behaviour.

There are three ideas here and they are additive — each one multiplies a
different axis of the dataset, and they compose. Section 12.5 describes the
single mechanism that makes 12.2 to 12.4 safe, and it is the part that most
needs getting right.

### 12.1 Procedural fragment generation

`data/synthetic/fever_true.yaml` is an unfinished sketch of this idea:
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

**This must not be used to clear the section 10 blocker.** Filling the four
empty test cells with template-siblings of the training fragments would make the
guard pass without fixing what the guard is for: it would remove the warning
light rather than the fault, and the resulting evaluation number would be
meaningless. Those four libraries need genuinely new ideas first.

**Start with the filler libraries.** `tangents`, `justifiers`, `emotional`,
`expectations` and `uti_speculation` carry no label weight — their only
requirements are that they contain no signal language and that they are varied
enough not to become a shortcut. Templating them is low risk and immediately
useful, and it would take the lint's cross-split near-duplicate count (currently
43, of which 32 are filler) to zero by construction.

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

Add fragment libraries for the other urinary signals — dysuria, urinary
frequency, and so on — each with its own true, false and ambiguous variants, on
the same pattern as the fever libraries. Twenty or so fragments per variant to
begin with. Then recombine them with the fever fragments.

**The payoff is not more examples, it is more label per example.** Today a
`true` example is one positive fever fragment plus one filler, and the filler
contributes nothing — it is there to stop the model keying on length and to
supply realistic noise. If the second fragment is instead a dysuria fragment
with a known label, the same example now carries two supervised signals:

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

1. Write real fragments for the four blocked `fever_null` libraries and produce
   the proof-of-concept run. This clears section 10 honestly and gives us a
   baseline to compare everything else against.
2. Add label vectors and declared silence (12.5) with the lint check, while
   there is still only one signal and it is cheap to get right.
3. Template the filler libraries (12.1), lowest-risk use of procedural
   generation, and add the templates-per-library and clusters-per-split lint
   reports.
4. Add dysuria and frequency libraries (12.2), which is where the multi-head
   training data actually starts.
5. Multi-symptom and out-of-scope fragments (12.3, 12.4), which need the JSONL
   library format.
6. Template the clinical libraries, once there are enough distinct templates per
   library for the split arithmetic to work.

The spelling-mistake pass can slot in anywhere after step 1, since it is a
post-processing step over finished text and independent of everything else.
