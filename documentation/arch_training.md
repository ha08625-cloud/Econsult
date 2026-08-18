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
convention, and by which condition it belongs to:

```
data/synthetic/
  manifest.json
  filler/                       condition-agnostic, reusable by any condition
                                four libraries, verified silent on all seven
                                signals (section 8)
  conditions/uti/
    symptoms/fever/             seven libraries, all about fever_present
    symptoms/dysuria/           six libraries, all about dysuria_present
    symptoms/urinary_frequency/ seven libraries, all about urinary_frequency_present
    symptoms/nocturia/          seven libraries, all about nocturia_present
    symptoms/flank_pain/        five libraries, all about flank_pain_present
    symptoms/haematuria/        five libraries, all about haematuria_present
    symptoms/recent_uti/        six libraries, all about recent_uti_present
    filler/                     two libraries, UTI-specific filler
  drafts/                       scratch files, deliberately not libraries (section 4)
  generated/                    output, git-ignored
```

Nothing in the code keys off the directory — the manifest gives every library's
path explicitly, so the layout is for humans. It matters as more signals arrive:
"which files carry a dysuria label" should be answerable by looking, not by
reading forty manifest entries. The condition layer answers the same question
one level up: a second ruleset gets `conditions/<name>/` and inherits the
top-level filler unchanged, rather than having its symptom libraries land in the
same flat pile as UTI's.

The split between the two filler folders is about language, not about which
condition happens to use a library. `tangents`, `justifiers` and `emotional`
contain no condition-specific vocabulary at all (checked: zero lexicon hits
across their 270 lines), so they sit at the top level. `uti_speculation` is
UTI-specific in 36 of its 40 lines and sits under the condition.

`expectations.txt` was the awkward one, and **it has now been split**. It was
left whole for as long as it was because splitting it is **not** dataset-neutral:
`_draw_filler` picks a filler library uniformly and then a fragment within it, so
going from five filler libraries to six changes every generated example and makes
every number on file incomparable. That is why the split waited for a
`GENERATOR_VERSION` bump that regenerated everything anyway, and it landed with
the one that took the version to 3.

The re-read moved **34 of the 100 lines**, not the 26 this section used to
estimate. The rule applied is the language one above — the organ, the
investigation or the drug is specific to the urinary tract — and applying it line
by line catches families the earlier count missed: kidneys and kidney function
("check my creatinine levels", "a scan to check my kidneys aren't damaged"),
renal stones ("an xray to check for stones", "lithotripsy to break it up") and
the named antibiotics beyond trimethoprim (ciprofloxacin, cefalexin). Sixty-six
lines stay in `filler/expectations.txt` — generic tests, generic drugs, and the
whole *who, how and when* half, none of which names a body part at all — and 34
move to `conditions/uti/filler/expectations_uti.txt`.

**Both halves needed their own declaration, and neither inherited the parent's.**
The shared half keeps `recent_uti_present` at basis `policy`: eight of its 66
lines still ask for antibiotics or a check for infection, and none of them dates
one inside the window. The UTI half is `policy` on the same signal for a
different reason — **the lexicon finds nothing in it at all**, so it would have
passed as `absent`, and six of its lines plainly discuss a urine infection and
its treatment ("I had trimethoprim last time", "ciprofloxacin ... what worked
last time", "a urine culture ... to identify the bug"). Declaring `absent` there
would have recorded the lexicon's silence as a fact about the text, which is the
one thing section 4's two bases exist to keep apart.

The filler libraries are verified silent about **all seven** signals — that
check is the lint's (section 8), it runs in CI, and it currently passes with no
baselined exceptions.

**That sentence used to carry a caveat about the seventh signal, and the caveat
is now discharged.** `recent_uti_present` had no libraries, so it had no lexicon
and nothing checked it, and this section predicted that whoever closed the gap
would inherit a `uti_speculation` "full of lines that assert it outright" and
needing rewriting or relabelling. **That prediction was wrong**, and section 9's
labelling policy is why: read against its rules, self-diagnosis ("I reckon it's
another UTI, I'm prone to them") is a guess rather than a diagnosis, recurrence
with no window marker says nothing about the last 30 days, and "I had one last
year" places an infection explicitly outside it. Not one of `uti_speculation`'s
forty lines asserts a urine infection inside the window, the filler-purity check
returns zero for `recent_uti_present` alongside the other six, and the library
needed no edit at all. What it needed was a declaration, and it has one: the
manifest declares the pair `null_on` with basis `policy` and the note quotes the
rules (section 4). It is not a leak and it never was.

| Library | Fragments | What it contains |
|---|---|---|
| `conditions/uti/symptoms/fever/fever_true.txt` | 96 | Says the patient has a fever ("I had a high temperature") |
| `conditions/uti/symptoms/fever/fever_false.txt` | 98 | Says the patient does not ("no temperature, I checked") |
| `conditions/uti/symptoms/fever/fever_null_hedged.txt` | 73 | Genuinely uncertain ("I feel a bit off, hard to say") |
| `conditions/uti/symptoms/fever/fever_null_metaphor.txt` | 55 | Fever words used non-clinically ("burning up with embarrassment") |
| `conditions/uti/symptoms/fever/fever_null_thirdparty.txt` | 46 | *Someone else* has a fever ("my son has a temperature") |
| `conditions/uti/symptoms/fever/fever_null_historical.txt` | 45 | A fever, but in the past ("I had one last month") |
| `conditions/uti/symptoms/fever/fever_null_attribution.txt` | 50 | Hot now, confidently blamed on something that is not a fever ("I get hot flushes with the menopause") |
| `conditions/uti/symptoms/dysuria/dysuria_true.txt` | 45 | Says it hurts to pass urine ("it burns when I pee") |
| `conditions/uti/symptoms/dysuria/dysuria_false.txt` | 47 | Says it does not ("weeing itself is fine, no stinging") |
| `conditions/uti/symptoms/dysuria/dysuria_null_hedged.txt` | 40 | Genuinely uncertain ("might be a slight sting, could be imagining it") |
| `conditions/uti/symptoms/dysuria/dysuria_null_historical.txt` | 38 | Painful urination, but in the past |
| `conditions/uti/symptoms/dysuria/dysuria_null_metaphor.txt` | 40 | Burn/sting words that are not about passing urine ("my eyes have been stinging with all the pollen") |
| `conditions/uti/symptoms/dysuria/dysuria_null_thirdparty.txt` | 46 | *Someone else* has dysuria ("my daughter says it hurts her to wee") |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_true.txt` | 46 | Says they are passing urine more often than usual ("I'm going every twenty minutes or so") |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_false.txt` | 46 | Says they are not ("I go about five times a day and that's exactly what I've always done") |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_null_hedged.txt` | 42 | Genuinely uncertain ("I might be going more often but I've never counted") |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_null_historical.txt` | 40 | More often, but in the past |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_null_metaphor.txt` | 44 | Frequency/flow/urinary words used non-clinically ("a wee bit of a worry", "sales have slowed to a trickle") |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_null_thirdparty.txt` | 44 | *Someone else* is going more often |
| `conditions/uti/symptoms/urinary_frequency/urinary_frequency_null_adjacent.txt` | 40 | A different urinary complaint, silent on how often ("the stream is much weaker than it used to be") |
| `conditions/uti/symptoms/nocturia/nocturia_true.txt` | 54 | Says they wake in the night to pass urine |
| `conditions/uti/symptoms/nocturia/nocturia_false.txt` | 54 | Says they do not ("I sleep right through") |
| `conditions/uti/symptoms/nocturia/nocturia_null_hedged.txt` | 47 | Genuinely uncertain |
| `conditions/uti/symptoms/nocturia/nocturia_null_metaphor.txt` | 52 | Night, sleep, toilet and "wee" words used non-urinary ("up all night worrying") |
| `conditions/uti/symptoms/nocturia/nocturia_null_thirdparty.txt` | 47 | *Someone else* is up at night |
| `conditions/uti/symptoms/nocturia/nocturia_null_historical.txt` | 46 | Night voiding, but in the past |
| `conditions/uti/symptoms/nocturia/nocturia_null_attribution.txt` | 51 | Woken by something that is not a need to void, and voids incidentally |
| `conditions/uti/symptoms/flank_pain/flank_pain_true.txt` | 48 | Says there is pain in the side/back below the ribs |
| `conditions/uti/symptoms/flank_pain/flank_pain_false.txt` | 55 | Says there is not |
| `conditions/uti/symptoms/flank_pain/flank_pain_null_hedged.txt` | 53 | Genuinely uncertain |
| `conditions/uti/symptoms/flank_pain/flank_pain_null_thirdparty.txt` | 47 | *Someone else* has flank pain |
| `conditions/uti/symptoms/flank_pain/flank_pain_null_historical.txt` | 40 | Flank pain, but in the past |
| `conditions/uti/symptoms/haematuria/haematuria_true.txt` | 45 | Says there is visible blood in the urine |
| `conditions/uti/symptoms/haematuria/haematuria_false.txt` | 45 | Says there is not |
| `conditions/uti/symptoms/haematuria/haematuria_null_hedged.txt` | 45 | Genuinely uncertain ("looked a bit pink but I ate beetroot yesterday") |
| `conditions/uti/symptoms/haematuria/haematuria_null_thirdparty.txt` | 45 | *Someone else* is passing blood |
| `conditions/uti/symptoms/haematuria/haematuria_null_historical.txt` | 45 | Blood in the urine, but in the past |
| `conditions/uti/symptoms/recent_uti/recent_uti_true.txt` | 44 | Says a urine infection was diagnosed or treated inside the last 30 days ("I finished a course of nitrofurantoin ten days ago") |
| `conditions/uti/symptoms/recent_uti/recent_uti_false.txt` | 44 | Denies one across the whole window ("the sample I handed in last week came back clear") |
| `conditions/uti/symptoms/recent_uti/recent_uti_null_hedged.txt` | 44 | Uncertain whether it was an infection, or certain it was and vague about when ("I had a water infection a while back but I honestly could not tell you when") |
| `conditions/uti/symptoms/recent_uti/recent_uti_null_historical.txt` | 42 | An infection with a time marker that clears 30 days, and no denial of the window |
| `conditions/uti/symptoms/recent_uti/recent_uti_null_thirdparty.txt` | 40 | *Someone else* had one |
| `conditions/uti/symptoms/recent_uti/recent_uti_null_adjacent.txt` | 42 | A recent, diagnosed, antibiotic-treated infection that is not urinary ("the dentist put me on antibiotics for an abscess about ten days ago") |
| `filler/tangents.txt` | 110 | Filler: irrelevant chat ("the parking here is impossible") |
| `filler/justifiers.txt` | 100 | Filler: why they need an appointment |
| `filler/emotional.txt` | 60 | Filler: worry and feelings |
| `filler/expectations.txt` | 66 | Filler: what they want to happen, in vocabulary any condition's patient could use — generic tests and drugs ("a blood test", "antibiotics", "a CT scan") and *who, how and when* (a named regular GP, phone vs face to face, timing) |
| `conditions/uti/filler/uti_speculation.txt` | 40 | Filler: self-diagnosis ("probably just cystitis") |
| `conditions/uti/filler/expectations_uti.txt` | 34 | Filler: the same asks in urinary-tract vocabulary — urine culture, cystoscopy, PSA, trimethoprim, kidney stones |

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

  Two rules follow from the haematuria boundary rule and apply to its null
  libraries. A
  `thirdparty` or `historical` fragment must read as decisively `true` if the
  person or the tense is changed and nothing else — "my sister's lad had tea
  coloured pee" is `null` twice over and so measures nothing. And a fragment
  that never mentions blood or urine is not a haematuria fragment under any
  label: seventeen `hedged` drafts were flank pain with no urinary content, and
  are parked in `drafts/` rather than labelled.

* **recent_uti** covers `hedged`, `thirdparty`, `historical` and `adjacent`,
  and its axes are displaced from the *window* rather than from a symptom,
  because the question is about an event in the last 30 days rather than about
  how the patient feels now. `historical` therefore has a sharper job here than
  anywhere else: it is not "the symptom was in the past" but "the infection is
  far enough back to be outside the window and the text does not say whether
  there has been one since", which is why a vague time marker is a `hedged`
  fragment rather than a `historical` one (section 9, rule 3). `hedged` carries
  both kinds of doubt the signal admits — doubt about whether it was an
  infection at all, and doubt about when. `adjacent` is the confounder the whole
  set is built around: a recent, diagnosed, antibiotic-treated infection that is
  simply not urinary, where every surface cue points to `true`. There is no
  `metaphor` library (nobody uses "water infection" figuratively) and no
  `attribution` library (a diagnosed infection stays a diagnosed infection
  whatever the patient blames it on, so attribution has nothing to displace).

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

**The measurement now exists, and the declaration does not yet.** The lint's
cross-signal report (section 8) asks the filler-purity question of every library
rather than only of filler: for each of the 293 (library, foreign signal) pairs
it prints how many of the library's lines read as that signal's language, and
proposes a pasteable `null_on` declaration for every pair where it finds none.
**35 pairs across 25 libraries have at least one match.** That report is
evidence and a triage list; the manifest field it proposes, and the per-pair
decisions behind it, have since landed — see section 4 for the field and for what
the declaration pass decided. `build_pools` filters filler by the declaration
and collects other signals' declared fragments into a companion pool, which
`--companion-share` draws from (section 5). At the default share of zero nothing
draws from it and every generated choice is what it was.

The libraries were written to be silent about the other signals, but that is a
manual reading and it has drifted more than once. Two known exceptions are
recorded here so they are not rediscovered as mysteries:

* Three `flank_pain_false` lines resolve the flank question by contrasting it
  against a urinary one ("it's just uncomfortable when I wee"), which asserts
  `dysuria_present: true` in a library that was a candidate to be declared
  silent on dysuria. Left in place because rewriting them is a labelling
  decision.
  **The lint finds this** — `flank_pain_false` matches the dysuria lexicon
  on 2 of its 55 lines — but finding it is not the same as making the claim
  checkable. The pair is a *per-line* fact over a library whose lines disagree,
  and `fragment_type` records the polarity of the library's own signal only, so
  there is no field a foreign signal's value could be read from. Per-line label
  vectors (12.3) are what would express it. **The declaration pass resolved the
  pair as *undeclared*** (section 4), which is the honest state rather than a
  workaround: `flank_pain_false` cannot be used as a companion in a dysuria run,
  which costs a smaller pool rather than a wrong label. Rewriting the two lines
  is the option that would recover the pool, and it is still a labelling
  decision — and one that moves generated data, so it did not belong in the
  commit that added the declarations.
* `filler` carries "blood test" and "blood pressure tablets", and `tangents`
  carries sleep-disturbance lines. Neither is a wrong label under the structural
  null rules. Both were flagged as candidate leaks when the lint was generalised
  and both were resolved as *lexicon too broad* rather than as leaks: blood in a
  vein is not blood in urine, and a bad night's sleep is not nocturia. They are
  in the lint's trap test now, so a future lexicon cannot quietly re-flag them.

**The filler libraries must contain no signal language whatsoever, for any of
the seven signals.** A filler fragment can be paired with anything,
including examples labelled "no fever mentioned", so fever language in filler
would make that example's label a lie — and the same holds for each urinary
signal. There is an automated check for all seven — see section 8. What is still
missing is 12.5: the lint now *measures* what every signal library says about
the other six, but nothing lets a library **declare** it, so the generator has
nothing in the manifest it can rely on. Measuring is done; declaring is the next
ticket.

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

**The "written as independent ideas" claim is load-bearing and has not been
tested.** It is what licenses reading the `urinary_frequency`, `nocturia`,
`flank_pain` and `haematuria` numbers at face value, and the near-duplicate
report (fold 0, ratio ≥ 0.6, which its own docstring calls a lower bound) gives
some evidence against it:

| signal | cross-split near-dup pairs | lines | rate |
|---|---|---|---|
| `recent_uti` | 19 | 256 | 7.4% |
| `flank_pain` | 17 | 243 | 7.0% |
| `nocturia` | 8 | 351 | 2.3% |
| `fever` | 8 | 463 | 1.7% |
| `dysuria` | 6 | 256 | 2.3% |
| `urinary_frequency` | 6 | 302 | 2.0% |
| `haematuria` | 5 | 225 | 2.2% |

`fever` and `dysuria` are *residuals* — their hand-tagged twins are forced into
the same split and cannot appear here at all — while the four untagged signals
are raw, so the comparison flatters the untagged ones. `flank_pain` at 7% most
deserves a re-read. By inspection some untagged libraries do carry families that
read as one idea: `haematuria_true` describes urine colour by comparison to a
drink five times (rosé, ribena, cranberry, plum, red wine).

`recent_uti` tops the table and is the one row to read differently. Every
fragment it holds has to place an infection somewhere in time, so all six
libraries share the infection nouns *and* the time markers, and that is exactly
the combination section 8 names as the case where character similarity runs high
between genuinely distinct ideas. The libraries were written against the count:
the first drafts of `historical`, `thirdparty` and `adjacent` each ran at three
to five times the tree's normal within-library rate on one sentence frame apiece,
and were rewritten as varied structures rather than tagged as clusters. 7.4% is
where it settled. Whether the residue is frame or vocabulary is not something
the report can settle, so this signal's absolute numbers are an upper bound by
at least as much as the other untagged signals'.

Until that is fixed, **the four untagged signals will post better numbers than
fever partly for reasons that have nothing to do with the symptom, and `dysuria`
will post worse ones because it is the only library set honestly clustered
throughout.** Tagging them is a ticket
(`planned_updates/multi_symptom_training_expansion.md`, "what comes next"),
prioritised by this table. It changes no code and invalidates no design; it only
means those four signals' absolute numbers are upper bounds until it lands.

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

### `null_on`: which foreign signals a library is `null` on

The manifest field the multi-symptom work runs on. For every (library, signal)
pair where the signal is **not** the library's own, the library either declares
that the signal is `null` on every one of its lines, or says nothing:

| state | meaning | eligible as a companion in that signal's run? |
|---|---|---|
| **declared `null_on`** | the correct label for this signal is `null` on **every** line, whether or not the line mentions it | yes |
| **undeclared** | nobody has decided | **no** |

For the library's own signal the value comes from `fragment_type`, exactly as it
always has. That is the only place a `true` or a `false` can come from, and it
is why a library may not declare `null_on` for its own signal: two sources for
one value is one that can disagree with itself.

**There is no cross-signal `true`/`false` state, and there cannot be one yet.**
`fragment_type` is the polarity of the library's *own* signal, so there is no
field a foreign signal's value could be read from — and the pairs that would
want one are per-*line* facts over libraries whose lines disagree. Three of
`flank_pain_false`'s 55 lines assert dysuria and 52 do not; a library-level field
cannot say that. Per-line label vectors (section 12.3) are what would express it.

**Undeclared is the default, and it is not the same as silence.** A closed-world
default — "silent about everything I do not name" — would mean adding an eighth
signal silently asserted that all 49 existing libraries were silent about it.
`uti_speculation` is the standing evidence for why that is unsafe: it had no
lexicon and nothing checked it for as long as `recent_uti_present` had no
libraries, and a library nobody has read against a signal is not a library that
is silent on it. There is no wildcard and no manifest-level default block
either, for the same reason: a shorthand for asserting 250 pairs in bulk is a
shorthand for asserting them without reading them. The lint makes the typing
cheap instead (section 8).

The declaration is an object keyed by signal:

```json
"null_on": {
  "fever_present": {"basis": "absent"},
  "recent_uti_present": {
    "basis": "policy",
    "note": "Names an infection but places none inside the 30-day window ..."
  }
}
```

Keyed rather than a list because a repeated signal is then a duplicate JSON key
inside one object, which `test_the_manifest_has_no_duplicate_json_keys` already
walks the whole manifest looking for. A list would need its own check.

#### The two bases, and why only one of them is checkable

This is the load-bearing distinction and it is easy to lose.

* **`basis: "absent"`** — the library never mentions the signal at all. This is
  the half a lexicon can check, so **a lexicon hit against an `absent` pair is a
  failure**, baselined per pair in `ABSENT_PAIR_BASELINE` exactly as filler
  purity is baselined per signal. The pre-existing filler-purity check is this
  same check applied to the libraries that always had to satisfy it.
* **`basis: "policy"`** — the library *does* talk about the signal and the
  correct label is `null` anyway. `uti_speculation` on `recent_uti_present` is
  the worked case: forty lines name an infection and none of them places one
  inside the 30-day window (section 9). **No lexicon can check this.** So a
  `policy` entry requires a `note` giving the rule that makes the label `null`,
  the lint prints every `policy` pair with its matched-line count beside the
  note, and the set of them is pinned in `POLICY_PAIRS` so that adding one is a
  deliberate edit rather than a line in a thousand-line manifest diff.

**Say the limit plainly.** The central safety guarantee of the multi-symptom
work is machine-checked for `absent` pairs and hand-judged for `policy` pairs,
and the lexicons doing the checking catch 59%–91% of their own *positive*
libraries and 25 to 45 points less of the negative ones (section 8). Even the
checked half is a lower bound. Under-claiming that here is what stops it being
discovered as a surprise later.

#### What the declaration pass decided

300 pairs: **260 `absent`, 24 `policy`, 16 deliberately undeclared.** Every pair
is in one of the three states; none is in an unconsidered one, and a test asserts
that. (The pass itself decided 293 across 48 libraries; splitting
`expectations.txt` in two added the seven cells of a 49th and moved one of them
from `absent` to `policy`.)

The 24 `policy` pairs are 20 on `recent_uti_present` plus four others, and the
shape is expected rather than unlucky. That lexicon deliberately matches the
infection nouns every library reaches for while its recency modifiers stop short
of "last time", "again" and "I'm prone to them" — so a historical, third-party or
non-urinary infection lands in exactly the cell a `policy` note is for.
`expectations_uti` is the one `policy` pair no lexicon put there: it matches
nothing, and it is declared `policy` anyway because six of its lines discuss a
urine infection and its treatment (section 3).

The 16 undeclared pairs are the cost of every decision deliberately left unmade,
and 14 of them are the **nocturia / urinary-frequency pair in both directions**.
"Up three times in the night for a wee" genuinely asserts both signals; the
assertion is a per-line fact; and there is no state above that can express it. It
was predicted to resist and it resists. The other two are the same fault in
single lines: `dysuria_true` carries "I've been waking up at night because weeing
is so painful", and `flank_pain_false` carries "My sides feel fine, it's just
uncomfortable when I wee" — the leak this document has recorded in section 3
since the lint was generalised. Both stay undeclared. Rewriting those two lines
would resolve them and buy two large libraries as companions; it is a labelling
decision and it moves generated data, so it is not made here.

The 28 baselined `absent` hits are all lexicon over-reach and they fall into
three families, each of which is the lexicon working as designed rather than
failing: a **flushed toilet** where the fever lexicon wants a flushed face (6
lines, all haematuria); a **counting word** — "times", "more", "constantly",
"all day" — qualifying the pain or the colour rather than how often the patient
goes (13 lines); and a **pain word** belonging to another clause than the urinary
anchor it was paired with (7 lines). Narrowing the lexicons to clear these would
cost real recall, since "flushed" is how patients describe a fever and "more" is
how they describe frequency.

#### What the declaration does to generation

`build_pools` now does two things it did not:

* **Filler is filtered rather than trusted.** A filler library reaches a
  non-decisive slot only if it has declared the run's signal `null_on`. Filler
  has been silent on all seven signals since the lint started checking, so today
  the filter removes nothing and every generated byte is unchanged — verified
  against the real libraries and pinned by the golden-digest test. It stops being
  free the moment a filler library goes undeclared on some signal.
* **Other signals' fragments are collected instead of dropped.** They used to be
  dropped because asserting a `dysuria_present` positive says nothing about
  `fever_present` was library work nobody had done. The declaration is that work.
  `--companion-share` draws from this pool (section 5); at its default of zero
  nothing does, and a test asserts that no companion fragment reaches any
  generated example at that setting.

An undeclared filler library is **excluded and named**, not silently dropped: it
lowers the fragment-count ceiling for that signal, the CLI prints a warning, and
if the exclusion leaves fewer than the two distinct filler libraries a structural
null needs, generation refuses to start with a `PoolError` naming the library, the
signal, and the three ways to resolve the pair. A pool error whose real cause is
three lines of missing JSON must not read as a library-size problem.

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
(none, for a structural null); every remaining slot is filler, or — at
`--companion-share` above zero — a **companion**: another signal's clinical
language, declared `null` on this signal in the manifest (section 4):

| Kind | What it is made of | Label |
|---|---|---|
| `true` | 1 positive fragment + N−1 filler/companion | `true` |
| `false` | 1 negative fragment + N−1 filler/companion | `false` |
| `null_ambiguous` | 1 hard-case fragment + N−1 filler/companion | `null` |
| `null_structural` | 1 filler + N−1 filler/companion | `null` |

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
sources. Without companions those sources are filler libraries and there are
six, so five is the practical limit and going higher wants more filler
libraries rather than a code change. It was five and four until
`expectations.txt` was split in two (section 3) — a reminder that the ceiling
counts *sources* and not lines, so dividing one library raises it exactly as
writing a new one does.

**Companions raise that ceiling too, and they are the first thing other than a
filler library that ever has.** One fragment per signal (below), so the ceiling
becomes *eligible filler libraries + signals with at least one eligible companion
library* — six plus six against today's tree. The generator checks this up front
and refuses to start if the requested maximum exceeds what the split can serve,
naming both halves. **The ceiling moves down as well**: an *undeclared* filler
library lowers it for that signal by one, which is why the refusal names it
(section 4), and a signal with no eligible companion library at all contributes
nothing to the second half of the sum.

### Companions: other symptoms' language in a `null` example

Every `null` example generated before this paired the absence of the signal's
language with bland, non-clinical filler. No head had ever seen a message dense
with clinical language about another symptom whose correct answer was still
`null`, so **"clinical-sounding text ⇒ not `null`"** was a perfect rule on our
data and a catastrophic one on real text, where the median submission asserts
something about two of the six signals. The measured cost is section 9's:
the joint model invents symptoms patients never mentioned 47%–89% of the time.

`--companion-share P` is the fix. `P` is the share of an example's non-decisive
slots that carry a fragment from another signal's library instead of filler.
Eligibility is that library's `null_on` declaration for *this* run's signal and
nothing else (section 4) — an undeclared pair contributes nothing, which costs a
smaller pool rather than a wrong label.

Three properties do the safety work, and the first is the one easiest to get
subtly wrong:

* **The companion count is drawn over N−1 slots in every label mode**, including
  `null_structural`, whose remaining slot is always filler. A structural null has
  one *more* non-decisive slot than every other mode at the same count, so an
  independent per-slot draw would give structural nulls twice the companions at
  the default count of two. Companion count would then be a proxy for the label
  pointing the wrong way — *more clinical text ⇒ more likely `null`* — which a
  model can learn without reading anything, and which would flatter this feature
  for exactly the wrong reason. The equalisation is by construction: the bounds
  are a function of the fragment count and the pool sizes alone, and the draw
  never sees the label. `companions.count_by_label_mode` in the sidecar is the
  leak detector, and a run whose rows disagree is void rather than
  reinterpretable.
* **Which companion is drawn is equally blind.** Signal uniformly, then library
  within it, then fragment — none of it seeing the label mode. Otherwise
  companions would be disproportionately `true` in `true` examples and we would
  have replaced "clinical language ⇒ not `null`" with "clinical language ⇒
  `true`", which is the same failure wearing a different hat.
* **At most one fragment per signal per example.** Two would either agree,
  doubling the evidence for one claim and teaching nothing, or disagree — and no
  single emitted label could describe that. The primary signal's own libraries
  are never eligible as companions at all: it enters an example through the
  decisive slot alone, or `null_structural` and `null_ambiguous` collapse into
  each other and `--null-ambiguous-ratio` stops meaning anything.

Companions come from the same split as the example, free of charge: `build_pools`
is split-restricted and the fold hash knows nothing about signals. Stated anyway,
because the failure is subtle — a fever *test* example holding a dysuria *train*
fragment is training text inside the test set.

**The default is 0.0, and at 0.0 the path is skipped rather than merely quiet.**
No count is drawn, no randomness is consumed, and the fragments chosen for a
given seed are exactly the ones the pre-companion generator chose — pinned by a
golden digest over the text, labels and fragment ids. The record's `meta` gained
`filler_only` and the generator version went to 3 in the same commit, so the
*bytes* moved; nothing the generator *chose* did.

**What `null_structural` means at P > 0.** It keeps the name because it keeps its
defining property — no fragment decisive for this signal — and it stops being
trivially easy, which is the point. It also stops being filler-only, so the
merge's structural-null deduplication (section 7) barely fires and the merged
tree grows by roughly 1.5×. That is this feature's compute bill, and it is
accepted rather than worked around.

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

**`--emit-signals all` is where that distinction stops being theoretical.** By
default a record carries one key, for the signal the run asked for. At
`--emit-signals all` it carries a key for every signal the example's fragments
*jointly* have a known status for, decided per signal S over the whole example:

| the fragments' states on S | result |
|---|---|
| any fragment is **undeclared** on S | **no key for S** |
| exactly one fragment asserts S (its own signal) | key = that fragment's value |
| every fragment is `null_on` S | key = `null` |
| two fragments would assert S | unreachable, and raises if reached |

Three things to read off that table.

* **The first row is read over the whole example, not per fragment.** One
  undeclared fragment masks the signal even when another fragment is asserting
  it outright — a dysuria positive next to a filler library nobody has read
  against dysuria earns no dysuria key. That is the honest answer: the
  undeclared fragment might be saying something about dysuria too, and no
  library-level field can say it is not.
* **The last row is a raise, not a resolution.** Two assertions for one signal
  are either redundant or contradictory, and silently keeping one of them is how
  a dataset acquires a wrong label. Section 5's one-fragment-per-signal rule
  makes it unreachable; the raise is what turns "unreachable" into something
  verified rather than assumed.
* **Nothing here reads text.** A fragment's contribution to every signal is
  fixed before it is drawn — its own signal's value from `fragment_type`, every
  other signal's from its library's `null_on` declaration (section 4) — so the
  vector is composed from facts the manifest already stated. The label-first
  invariant of section 2 is untouched, and the primary key is cross-checked
  against the spec that was decided before any fragment existed.

**It is built and not measured.** No trained arm uses it, and `merge-folds`
refuses a tree whose records carry more than their own signal's key, so an
`--emit-signals all` tree cannot currently reach joint training. The flag exists
so the mechanism is written, tested and documented; what it would buy — more
label per example, and therefore training efficiency — is a question of its own
and is not the one companions were built to answer.

**How many fragments an example holds is not stored.** It is
`len(meta.fragment_ids)` and nothing else. A second copy of the same number is
one more thing that can disagree with itself.

**`meta.filler_only` is the one derived fact that *is* stored.** True when every
fragment in the example is filler. Before companions this was the same statement
as `label_mode == "null_structural"`; at `--companion-share` above zero it is
not, and both the merge's structural-null deduplication and the reports need to
know which examples are still filler-only. It is written once at assembly rather
than re-derived from `fragment_ids`, because re-deriving it needs the manifest
and would go quietly wrong the moment a library was edited.

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
* `companions` — the same policing for the companion draw, and the block to read
  first on any run with `--companion-share` above zero:
  * `count_by_label` and `count_by_label_mode` — how many companions each
    example held. **The `by_label_mode` rows must agree with each other.** If
    they do not, the companion count has become a proxy for the label and the
    run is void rather than reinterpretable (section 5). Nothing downstream
    would surface it: it would present as a validation score that looks fine and
    a model that does not transfer, which is the shape of the failure companions
    exist to remove.
  * `label_mix_by_label` — the companions' *own* polarity, per primary label
    class. The same question asked of which companion rather than how many: a
    skew here means "clinical language ⇒ `true`" replaced "clinical language ⇒
    not `null`".
  * `signals` — which foreign signals were drawn, and how often.
  * `requested.companion_share` records the flag, and `split_pool_sizes.companion`
    records what was eligible to draw from.
* `realised.labels_by_signal` — the realised label prior of every head the run
  emits, plus an `absent` count for the examples that carried no key for it at
  all. At `--emit-signals primary` this is one row equal to `realised.labels`.
  It exists because the decision rule's objective is stated *relative to argmax*
  (`arch_encoder_training.md` section 8), so a head's prior moves the constraint
  and not only the head; a prior that has to be inferred from the flags is a
  prior nobody checks. `absent` is the second half of it — a head supervised on
  4% of the tree and a head supervised on all of it look identical once the
  three label counts are normalised.

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

### The merged multi-signal tree

`python -m scripts.encoder_training merge-folds` reads the six per-signal fold
trees and writes a seventh beside them, for joint multi-head training.
`scripts/encoder_training/merge.py` is where it lives — not in
`scripts/synthetic_data/`, because it is built on the fold-tree convention in
`dataset.py`, and `encoder_training` already imports from `synthetic_data`
rather than the other way round.

**Nothing is regenerated.** The merge is a concatenation, and that is what makes
the comparison it exists for readable: the merged tree's `fever_present` slice
*is* the fever tree's own slice, example for example, so a joint model and a
single-signal model can be compared pairwise on it. Filenames follow the same
`{signal}.fold{i}.{split}.jsonl` convention with the merged name (`joint6` by
default) in the signal position, so `load_folds(dir, "joint6", folds=5)` reads it
with every existing check applying and no special case anywhere. That is the
contract: if the merged output ever needed a new escape hatch in `dataset.py`,
the merge would be wrong, not the loader.

**No head gains supervision.** A merged dysuria example carries a dysuria label
and no `fever_present` key at all — which is a *mask*, not a `null` assertion,
exactly as above. The fever head sees the same 10,000 labelled positions in the
same 15/25/60 mix it saw alone; what changes is that the shared encoder is also
pulled by five other heads on text the fever head gets no gradient from. Filling
those absent keys with `null` would be a different and much larger ticket — 12.5,
and then 12.2–12.4.

**The filler-only examples are kept once.** Because `run_seed` does not depend on
the signal, all six trees emit byte-identical filler-only examples; one copy is
kept and labelled `null` for all six. Same gradients, 25% fewer forward passes at
`--companion-share 0`, and each head keeps its own mix. That identity is the
load-bearing assumption, so the merge asserts it position for position on
`example_id`, `text` and `meta.fragment_ids` rather than trusting it — if a
signal term ever entered the seed derivation, six *divergent* null sets would
collapse into whichever arrived first, every head's class prior would shift, and
nothing downstream would notice. The union is only *sound* because the
generalised filler lint (section 8) holds the filler libraries silent about all
six signals; see 12.8.

**What it deduplicates on is `meta.filler_only`, not the `null_structural` label
mode**, and above `--companion-share 0` those are different sets. A structural
null that drew a companion holds another signal's language drawn from *this*
signal's eligible pool, so it is not the example any other tree emitted at that
index: it is kept per signal like any other owned example, keeps its
`null_structural` mode, and supervises only its own head. What still
deduplicates is the filler-only remainder, which falls towards nothing as the
share rises — so the merged tree grows by roughly 1.5×, which is the companion
feature's compute bill (section 5).

The check was **relaxed rather than deleted**, and the distinction matters: at
`--companion-share 0` every structural null is still filler-only, so the guard
covers exactly what it always covered. Deleting it would put back the failure it
was written for.

That the filler-only remainder still lines up position for position above zero
is checked, not assumed. It holds on the committed libraries because the
companion *count* draw consumes the same number of random values in every
signal's run — `min(fragment_count − 1, eligible companion signals)`, and every
signal has more eligible companion signals than the largest fragment count — so
an example that drew no companion is the example that drew none in every other
tree too. If that ever stops being true the merge raises rather than quietly
keeping one tree's copy.

**Every merged example keeps the id it had in its own tree.** Six trees all
number from `train-000000`, so the merged record gets a fresh `example_id` —
`{signal}:{original}`, or `shared:{original}` for a deduplicated structural null —
and a `meta.source_ids` map from signal to the id that example had in that
signal's own tree. A structural null carries all six; a fever example carries
one. **When a joint model reports predictions for signal S it reports them under
`meta.source_ids[S]`**, which is what keeps paired McNemar against that signal's
single-signal run working untouched. The rejected alternative was teaching the
report layer that two ids are the same example, which would put that knowledge in
the one module with no way to check it.

Four things the merge refuses outright, each because the failure would otherwise
be silent: sources that disagree on `generator_version`, on the
`(folds, fold_index, split_salt)` triple, or on `requested.companion_share` — a
merged tree that is half Arm 0 and half Arm P loads cleanly, trains cleanly and
answers the question the two arms exist to ask with a dataset that is neither of
them; two sources describing one `fragment_id` with a different `cluster_key`,
`fragment_type` or `split` (a dict union would first-win that); and divergent
filler-only examples. A tree generated before `GENERATOR_VERSION` 3 carries
neither `meta.filler_only` nor `requested.companion_share` and is refused by name
rather than merged on a default, because a default of zero would be right for
such a tree and silently wrong beside any tree generated above it. One thing it reports
without refusing: a `cluster_key` shared by fragments from more than one library.
Tagged clusters are namespaced `{library}:{tag}` and cannot collide, but untagged
ones fall back to the normalised text, which is not library-qualified — so
identical text in two libraries becomes one resampling unit. That *deflates*
effective sample size rather than inflating it, which is the safe direction, so
it is counted, listed in the merged sidecar's `merged_from` block and warned about
on stderr rather than treated as an error.

The merged sidecar carries everything `REQUIRED_STATS_KEYS` asks for, plus a
`signals` list, a `realised.labelled_by_signal` block (which should match each
source tree's own realised counts exactly, since the merge adds no supervision),
and `merged_from` — the sources with their signals, example counts, seeds and
`companion_share`, the arm's own `companion_share`, the filler-only tally, and
the collision list.

---

## 8. The lint

`python -m scripts.synthetic_data --lint` reports on library health without
generating anything. It never edits a fragment. Six reports:

**Signal language in filler** — the one with real teeth. Any filler fragment
that reads as an assertion about one of the seven signals with a lexicon is
flagged, grouped by the signal whose `null` label it would falsify. This is
enforced by a test that runs against the real libraries in CI, so it fails if
someone edits a filler library and introduces symptom language. Matching is on
whole words only: without that, "hot" matches inside `lithotripsy`, `photos` and
`shot`.

**Currently zero hits, on a per-signal baseline** (`FILLER_PURITY_BASELINE` in
`tests/test_synthetic_recombination.py` is a dict of empty sets, one per
lexicon, and it is built from `SIGNAL_LEXICONS` so a new lexicon joins it
rather than being silently unchecked — `recent_uti_present` did, and filler is
silent about it too). An entry
in that baseline is a claim that a line reads as signal language, is staying in
filler anyway, and that somebody decided that on purpose.

The seven lexicons come in two shapes, and the split is not cosmetic. Fever is a
state with a name, so a **term list** does it: "feverish" in filler is a leak
whatever surrounds it. None of the other six can be named in one word without
over- or under-reaching, so each is an **anchor plus modifier** pair and a
fragment must match one of each:

| signal | anchor | modifier |
|---|---|---|
| `dysuria` | named urination | pain / burning / stinging |
| `urinary_frequency` | named urination | frequency language |
| `nocturia` | named urination | night and getting-up language |
| `flank_pain` | loin / side / back / kidney / ribs | pain |
| `haematuria` | named urination, bowl, pan, sample | blood and urine colours |
| `recent_uti` | infection nouns (uti, cystitis, water/urine/bladder/kidney infection) | diagnosis, treatment and recency markers |

`recent_uti_present` is the seventh, added with the cross-signal report below
and ahead of its libraries. It joined the recall guard the moment they landed
and with no test edit at all, because
`test_every_lexicon_reaches_most_of_its_own_library` parametrises over the
signals that *have* a positive library in the live manifest rather than over a
hand-maintained list with an exemption to remember to remove. It scores 68%, in
the middle of the other six.

Its split is the sharpest of the seven, because the question is not "does this
line name an infection" but "does it put one inside the last 30 days". The
anchor half alone is the commonest thing said in these libraries:
`uti_speculation` names an infection on nearly every one of its 40 lines and,
under the section 9 policy, asserts a recent one on none of them. So the recency modifiers deliberately stop
short of "last time", "last year", "again" and "I'm prone to them" — every one
of those is how that library talks about the past, none of them places an
infection inside the window, and the labelling policy those libraries are
written against makes all of them `null` (section 9). Three lines in the whole tree match: an antibiotics-in-March line in
`dysuria_null_historical`, a third-party UTI in `flank_pain_null_thirdparty`,
and a ten-years-ago treatment in `haematuria_null_historical`. All three name an
infection *and* its treatment, which is exactly what the lexicon is for, and all
three are still `null` on the 30-day window — which is the shape of a `policy`
decision rather than a leak.

That shape is what lets the check stay quiet about filler's entirely legitimate
talk of urine cultures, kidney scans and broken sleep while still firing the
moment a line puts the two halves together. "Blood" is a blood test until it is
in urine; "kidney" is a kidney scan until something hurts; "night" is a bad
night's sleep until someone gets up to wee. All three of those are real filler
lines and all three are in the trap test.

The cost is recall against euphemism. The anchors are *named* urination only —
a bare "go" is excluded, because "going on", "go to work" and "get back to
normal" are ordinary filler English, and pairing "go" with a pain word made a
draft of the lint fire on "family issues that have been dragging on". So a line
that says "I'm going every twenty minutes" names no anchor and is not matched.
What each lexicon catches in its own `positive` library, on the committed tree:

| signal | matched | rate |
|---|---|---|
| `dysuria` | 41/45 | 91% |
| `fever` | 86/96 | 90% |
| `haematuria` | 39/45 | 87% |
| `flank_pain` | 40/48 | 83% |
| `nocturia` | 38/54 | 70% |
| `recent_uti` | 30/44 | 68% |
| `urinary_frequency` | 27/46 | 59% |

`urinary_frequency` is low because that library leans hardest on euphemism, not
because its lexicon is weaker. `recent_uti` sits mid-table for a different
reason: about a third of its positive library is the treatment-proxy family
(section 9, rule 2), and "I have just come off a week of antibiotics for
cystitis" carries both halves while "I finished a course of nitrofurantoin ten
days ago" names no infection at all and is invisible to the lexicon by design. The `negative` libraries run 25 to 45 points
lower across the board, because negating a symptom drops the words that name it
("no blood at all" keeps neither half). `test_every_lexicon_reaches_most_of_its_own_library`
holds these above 45%, which is a guard against a lexicon quietly narrowed until
it matches nothing — the easy way to make a filler-purity failure go away, and
the one that leaves the check dead. It is a floor, not a target: a library that
grows in a new register will move these numbers and that is normal.

**Cross-signal language** — the same lexicons, asked about *every* library
against every signal that is not its own, rather than about filler alone. Filler
purity and this report are one function (`signal_language_hits`) called two
ways, so the two can never drift apart; a test asserts that the filler rows of
the grid are exactly what the filler-purity report returns.

The difference is what a hit *means*, and it is why this half fails nothing.
A filler fragment carrying fever language has one right answer. A
`nocturia_true` fragment carrying urinary-frequency language has three, and
picking between them is a labelling decision rather than a bug:

* **Leave the pair undeclared.** That library cannot be used as a companion in
  that signal's run. Free, honest, and the right default — a smaller pool is a
  smaller dataset, not a wrong one.
* **Declare it `null_on` anyway, with a written reason.** For lines that mention
  the signal and are genuinely `null` on it, like the three `recent_uti` matches
  above.
* **Rewrite the lines**, where a line is incidentally impure.

A fragment is never checked against its own signal's lexicon: that is the
lexicon working, and the recall guard above is where it is measured.

**35 of the 300 pairs match, across 25 of the 49 libraries.** The head of the
list is the nocturia / urinary-frequency pair, which is not a lint fault — "up
three times in the night for a wee" genuinely asserts both — and is the pair
predicted to resist any library-level declaration:

| library | signal | matched | rate |
|---|---|---|---|
| `nocturia_null_thirdparty` | `urinary_frequency_present` | 9/47 | 19% |
| `nocturia_true` | `urinary_frequency_present` | 8/54 | 15% |
| `nocturia_false` | `urinary_frequency_present` | 6/54 | 11% |
| `dysuria_null_hedged` | `urinary_frequency_present` | 5/40 | 12% |
| `urinary_frequency_false` | `nocturia_present` | 5/46 | 11% |
| `nocturia_null_historical` | `urinary_frequency_present` | 4/46 | 9% |
| `recent_uti_null_hedged` | `dysuria_present` | 4/44 | 9% |

The `recent_uti_null_hedged` row is the seventh signal's only real contribution
and it is intrinsic rather than sloppy: a library about *was that an infection or
not* reaches for the symptom that raised the question, so "I felt a sting when I
went to the loo last fortnight but I was using new bath salts" carries dysuria
language while being `null` on dysuria (past tense) and `null` on
`recent_uti_present` (unresolved). It is a candidate for a `policy` declaration
rather than for a rewrite.

The remaining 28 pairs run at 1 to 3 lines each; the report prints all 293 rows,
worst first, with the matched lines under each. The full grid as it stood when
the report landed, every matched line included, is committed at
`reports/synthetic_data/2026-08-18-cross-signal-grid.md` — it is the input to
the per-pair declaration pass, and a terminal scrollback is not a place to keep
that.

For every pair it finds *nothing* in, it prints a pasteable manifest
declaration. That is the point of the report rather than a convenience: 258 pairs
came out silent and had to be declared by hand, and the alternative to making the
typing cheap is a wildcard — which is a shorthand for asserting the pairs without
reading them. **A zero is evidence of topical absence at 59%–91% lexicon recall,
not proof**, and the report says so above the block: a human still confirms the
library's subject matter before committing a declaration, which is one judgement
per pair rather than per line.

That caveat earned its keep, and by a wide margin. **17 of the 258 pairs the
block proposed as `absent` were not absent**, and every one of them was moved to
`policy` by reading the library rather than by any check firing. Sixteen are on
`recent_uti_present`, whose lexicon matches infection nouns only when a recency
marker sits beside them — so `uti_speculation`'s forty suspicions, `expectations`'
ten antibiotic requests, and every historical, third-party or non-urinary
infection across the fever, dysuria, nocturia, flank-pain and haematuria
libraries all came back silent while plainly being *about* the signal. The
seventeenth is `urinary_frequency_null_adjacent`, which describes urine colour
("really dark orange", "sort of murky") and is silent to the haematuria lexicon
because none of those colours is blood.

Two thirds of the `policy` declarations, in other words, exist in pairs the lint
called clean. Anyone reading the zero-hit block as a verdict rather than as a
typing aid would have written 17 false `absent` claims, and the `absent` check
would have passed on every one of them.

**Declared `null_on` pairs** — the other side of that decision, once it has been
made, and the report split in two because the guarantee is. `absent` pairs are
re-checked against the same lexicons and **a hit is a failure**, held to
`ABSENT_PAIR_BASELINE` in CI: currently 28 baselined hits across 18 pairs, all of
them lexicon over-reach (section 4 names the three families). `policy` pairs are
*listed* with their matched-line count and their note, because no lexicon can
check them — so "4 of `recent_uti_null_hedged`'s 44 lines read as dysuria
language and we decided all 44 are `null` on it" is a visible standing claim
rather than an invisible one. Undeclared pairs are listed too; that list is the
cost of every decision deliberately unmade.

The two halves are printed apart and labelled on purpose. A reader who cannot
tell the checked half from the asserted half has neither, and collapsing them
into one report is how the checked half quietly stops being checked.

**Filler purity stays a separate and slightly stricter check.** It is not
replaced by the `absent` check, because the two filler pairs declared `policy`
(`uti_speculation` and `expectations` on `recent_uti_present`) would stop being
checked at all, and filler is paired with examples of *every* label — so a filler
line that acquires signal language is worth catching even where the declaration
would tolerate it. A test pins that the two differ on exactly those two pairs.

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
count ceiling is the number of filler libraries plus the number of eligible
companion signals (section 5), and past a few fragments each example is still
one supervised claim in more noise.

**One dataset carries one signal.** A run emits the key for the signal it was
asked for and nothing else. `fever_present` and `nocturia_present` both have
libraries complete enough to generate from, and `dysuria_present` and
`urinary_frequency_present` too, but a fever dataset carries no dysuria or
nocturia key and vice versa — we deliberately do not emit `null` for the signals
a run did not cover. Doing so needs *every* fragment in an example to be known
silent about the signals being claimed, and we are only half way there: section
8's lint now establishes it for the filler libraries, but a `true` or `false`
example also carries a signal fragment, and no signal library declares what it
says about the other five (section 3's `flank_pain_false` lines are a live
counter-example). Claiming "no dysuria mentioned" on that basis would still be
inventing a label. Section 12.5 is the mechanism that would let one example
carry several keys honestly, and it is not built. The one case that does not
need it is the structural nulls, which are filler and nothing else — see 12.8.

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

For `recent_uti_present` the same was done. This policy is recorded **before the
six libraries were finished and before any of them was labelled against it** —
four drafts existed when it was written and were revised to meet it, which is
the order that makes a policy a policy rather than a rationalisation of whatever
the fragments happened to say. The question the libraries are labelled against
is the `encoder_prompt` in `data/uti1.json`, verbatim:

> *Does the response indicate the patient has had a urine infection in the last
> 30 days?*

Six rules, every one of which a real submission forces:

1. **A suspected current infection is `null`.** "I reckon it's another UTI, I'm
   prone to them" is a patient's guess about the episode that brought them here,
   and a *suspected* infection is not a *had* one. `null` unless the text says it
   was diagnosed or treated. This is the rule that does the most work, because
   self-diagnosis is the commonest way patients talk about UTIs.
2. **Treatment is a proxy for diagnosis.** "I finished a course of nitrofurantoin
   ten days ago" is **`true`** with no diagnosis stated: an antibiotic given for
   a urine infection inside the window *is* the diagnosis. Section 9's real-
   submission reading found this family — what the patient has already tried —
   in about half the submissions and in no library at all, so it is covered
   deliberately here rather than incidentally.
3. **The axis is the 30-day window, not the tense.** "I had one last year" is
   `null`, **not `false`** — it says nothing at all about the last 30 days. This
   is the rule most likely to be got wrong by instinct, because past tense reads
   as a denial and is not one. A `historical` fragment therefore needs a time
   marker that actually clears 30 days ("in the spring", "three months ago",
   "when I was pregnant with my first"); a vague one ("a while back", "a few
   months ago, maybe") does not settle the window and belongs in `hedged`.
4. **`false` needs an explicit denial that spans the window**, and it must be
   genuinely varied. "I've never had a water infection", "not for years", "the
   sample they sent off last week came back clear" all work; a past infection on
   its own does not (rule 3). Forty rewordings of "haven't had one in N weeks"
   is two clusters, not forty fragments (section 3), so `false` is written as
   distinct *situations* — a negative culture, a clear dipstick, a partner's
   infection nobody caught, a routine check at an annual review.
5. **Non-urinary infections are the hard confounder and get their own library.**
   "I had thrush last month and got antibiotics for it", "I was treated for a
   chest infection in July". An infection noun, a diagnosis, a treatment and a
   recent date are all present, every surface cue points to `true`, and the
   answer is `null` because none of it is a *urine* infection. This is the
   `adjacent` axis, and it is the single library most worth having, on the same
   reasoning that makes `attribution` and `adjacent` the hardest axes for every
   other signal. Six libraries, therefore, not five.
6. **Recurrence without a window marker is `null`.** "I'm prone to them", "it
   always comes back", "like last time", "I've had them before and this feels
   similar" are all about a pattern rather than a date, and none of them places
   an infection inside the last 30 days.

**Rules 1, 3 and 6 have a consequence for `uti_speculation`, and it runs the
opposite way to what section 3 says above.** Read against these rules, all forty
of its lines are `null`. Every one of them is either suspicion about the episode
that brought the patient in (rule 1) or recurrence with no window marker
(rule 6), and the one line that names a date at all — line 28's "I reckon it's a
kidney infection, I had one last year" — puts it explicitly outside the window
(rule 3). **Not one line asserts a
urine infection inside 30 days.** The sentence in section 3 calling it "full of
lines that assert it outright" predates this policy and is wrong under it;
`uti_speculation` needs neither rewriting nor relabelling, and the pair it forms
with `recent_uti_present` is a `null_on` declaration with basis `policy` rather
than a leak. That declaration is now in the manifest (section 4).

The same reading applies to `expectations`, which carries four lines about
previous antibiotics. Three of them — "I had trimethoprim last time and it didn't
touch it", "Can I try a different antibiotic as trimethoprim doesn't seem to help
me anymore" and "because it always comes back" — name no window and are `null`
under rules 3 and 6. Only "I think I need stronger antibiotics this time as the
last lot didn't clear it properly" arguably implies a recently-treated episode,
and that is one line out of a hundred, not a library that needs rewriting.


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
half the submissions; the nearest libraries are `expectations` and
`expectations_uti`, which are about what they *want*, and 11 of their 100 lines
touch treatment at all. *Relevant history and
risk factors* — pregnancy, diabetes, kidney stones, recurrent UTIs, male sex,
age, a previous admission — appears in about a quarter; there are two such lines
across all six filler libraries.

Neither can simply be written as filler: "I finished a course of nitrofurantoin
ten days ago for a urine infection" and "last year I was hospitalised with a
kidney infection" carry signal language, so as filler they would make every label
they were paired with a lie. They belong either in the `_null_historical`
libraries or behind section 12.5's declared silence. Note that section 8's lint
would *not* stop either line: both are historical claims about an infection
rather than about a symptom, so they match no anchor-modifier pair. The lint is a
guard against drift in libraries already judged clean, not a substitute for
judging a new one. Two new filler libraries would also raise the
fragment-count ceiling of section 5 by two. There are two other ways that
ceiling moves and no more: companions, which add a source per eligible foreign
signal, and splitting an existing filler library, which is what the
`expectations.txt` split did for one.

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

**Every measured number below was produced at `GENERATOR_VERSION` 2, and the
generator is now at 3.** Nothing here is comparable with anything generated after
the bump, and the difference is not cosmetic: version 3 splits `expectations.txt`
in two, which takes filler from five libraries to six and therefore changes every
`_draw_filler` outcome and every generated example, and it adds
`meta.filler_only` and the companion draw. A regenerated Arm 0 baseline at
version 3 is what these tables have to be re-measured against before any of them
can be quoted beside a companion run; until that exists, read the rows below as
history rather than as the control. Each table carries its own version line for
the same reason.

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
matters.** Measured coverage, per signal, over the whole library:

Library sizes, so version-independent — the split moved lines between two
*filler* libraries and touched no signal library.

| signal | libraries | tagged lines / total | untagged libraries |
|---|---|---|---|
| `dysuria` | 6 | 148 / 256 (58%) | `true`, `false` |
| `fever` | 7 | 89 / 463 (19%) | `true`, `false` |
| `urinary_frequency` | 7 | 0 / 302 | all 7 |
| `nocturia` | 7 | 0 / 351 | all 7 |
| `flank_pain` | 5 | 0 / 243 | all 5 |
| `haematuria` | 5 | 0 / 225 | all 5 |

The four `dysuria_null` libraries are tagged throughout (three at 100%,
`metaphor` at 60%); every fever library except `true` and `false` is partly
tagged, 27–48%. The other four signals carry no markers at all, so their
effective n equals their fragment count by default.

**That default is a claim, not a measurement, and it is asymmetric.** Tagging
only ever *reduces* effective n — correctly, by stopping one idea being counted
twice — so an untagged library's eff n is an **upper bound** and every interval
computed on it is narrower than the truth. A signal tagged throughout is
therefore penalised for being honest, and one with no markers is flattered by
default. See section 12.8 for why this makes a cross-signal ranking unsafe to
read at face value and why it does not touch a fever-versus-fever comparison.
The evaluation report computes this table per run and prints the warning above
its own headline (`arch_encoder_training.md` section 8).

**The prediction that followed from this was wrong, and the record says so.**
The expansion plan predicted the four untagged signals would post *better*
numbers than fever for reasons unrelated to the symptom, and that `dysuria`
would post *worse* because it is the only honestly-clustered set. The
2026-08-16 runs came out the other way: `dysuria` placed second of six, and the
two weakest signals — `nocturia` and `urinary_frequency` — are both 0% tagged.
The asymmetry above is real and still means an untagged interval is narrower
than the truth; what it is not is the thing that separates these six signals.
Differences in what the `_true` libraries contain swamp it.

**All six signals now generate a full five-fold dataset at fever's recipe.**
10,000/2,000/2,000, `15/25/60`, `--null-ambiguous-ratio 0.5`, base seed 42, salt
0 — 15 files each, no `PoolExhaustedError` anywhere, including the two the
expansion plan expected to be awkward. Dysuria and haematuria both reach 10,000
comfortably; haematuria's three null sub-classes are enough to keep the
ambiguous pool populated at that size. Duplicate rejections run higher on the
thinner libraries (roughly 160–200 per 10,000 train examples against fever's
~100), which is the pool doing its job rather than a problem.

**All six signals have now been trained**, one head each, Arm B at
`roberta-base` on the datasets above (2026-08-16). No code change was needed;
`--signal` was already a flag on every command. Decisive accuracy, pooled over
five folds:

Measured on `GENERATOR_VERSION` 2 datasets (2026-08-16).

| signal | eff n | Arm B | Arm A | TF-IDF | `null→true` | errors on `_true`/`_false` |
|---|---|---|---|---|---|---|
| `flank_pain` | 243 | 96.0% | 80.7% | 72.8% | 1.51% | 59% |
| `dysuria` | 182 | 94.9% | 82.4% | 70.5% | 3.49% | 39% |
| `fever` | 418 | 92.9% | 79.0% | 73.6% | 1.34% | 73% |
| `haematuria` | 225 | 91.5% | 82.8% | 74.7% | 2.33% | 66% |
| `urinary_frequency` | 302 | 85.3% | 67.8% | 59.9% | 1.94% | 87% |
| `nocturia` | 351 | 83.0% | 70.4% | 64.9% | 4.04% | 72% |

`reports/encoder_training/2026-08-16-plain-english.md` is the write-up. Three
things from it belong here because they are facts about *the data*, not about
the models:

**The 2026-08-09 fever finding replicates across five more symptoms.** Errors
land on the clear `_true`/`_false` libraries, not on the deliberately-hard
`null` confounders that were written to be the difficult part. The confounder
libraries mostly sit at 0.90–1.00 recall. The last column above is the statement
of it, and `urinary_frequency_true` at 65.8% and `nocturia_true` at 71.1% are
the two worst libraries in the sweep.

**Section 10's own cluster-tagging prediction did not hold** — see the note
below the coverage table. Dysuria, the only fully-tagged signal, came second;
the two weakest signals are both fully untagged. Tagging is not what separates
these six.

**`nocturia` and `urinary_frequency` are genuinely the hard pair, and it is not
a model problem.** TF-IDF is also worst on exactly those two, so the difficulty
is in the signals rather than in the encoder. The working hypothesis is that the
two are near-synonyms of each other — "going a lot" against "going a lot at
night" — which is also why `urinary_frequency` is the only library set that
needed an `adjacent` confounder class. Untested.

**The three-arm joint comparison ran on 2026-08-17, and its result inverts
depending on which test set you read.** Six signals, three arms each: A1 (that
signal alone, 10k), A2 (that signal alone at 4.5× the recombinations) and A3 (one
encoder, six heads, the merged tree). Reports are
`<signal>.joint_comparison.json`; the write-up is
`reports/encoder_training/2026-08-17-plain-english.md`.

Measured on `GENERATOR_VERSION` 2 datasets (2026-08-17).

| signal | A1 | A2 | A3 | A1→A3 paired | `null→true`, synthetic | `null→true`, **real text** |
|---|---|---|---|---|---|---|
| `nocturia` | 83.0% | 88.0% | **92.3%** | A3, p=7e-80 | 4.04% → 2.52% | 2% → **58%** |
| `haematuria` | 91.5% | 92.8% | **94.9%** | A3, p=8e-27 | 2.33% → 1.61% | 22% → **79%** |
| `dysuria` | 94.9% | 95.3% | **98.1%** | A3, p=3e-22 | 3.49% → 1.34% | 45% → **67%** |
| `flank_pain` | 96.0% | 95.5% | **97.8%** | A3, p=3e-07 | 1.51% → 0.58% | 53% → **89%** |
| `urinary_frequency` | 85.3% | 84.5% | 86.2% | A3, p=0.034 | 1.94% → 2.53% | 5% → **47%** |
| `fever` | 92.9% | 93.8% | 93.5% | **245/245, p=1.0** | 1.34% → 2.40% | 17% → **82%** |

Four facts from it belong here because they are facts about *the data*:

**Joint training helps on recombinations and is catastrophic on real text.** A3
improves the decisive slice on four of six signals and improves the synthetic
`null→true` rate on four of six — while multiplying the same rate on the 67 real
submissions by 3× to 24×. Across all 402 real answers A3 scores **39.1%**, against
**66.7%** for replying `null` to everything. This is the failure mode 12.5 was
written to prevent, now measured rather than argued: every `null` example for a
signal pairs the absence of that signal's language with *bland non-clinical*
filler, so no head is ever taught that dense clinical language about another
symptom is still `null` for it — and six heads sharing an encoder make symptom
language maximally salient. **Multi-symptom recombinations are therefore the
critical path, not an option.**

**A2 does its job and mostly rules out the boring explanation.** 4.5× the
recombinations of the same clusters buys −0.8 to +1.3 points on five of six
signals, so A3's gains are not explained by gradient steps. Nocturia is the
exception at +5.0, so roughly half of its +9.3 is volume.

**The near-synonym hypothesis held, asymmetrically.** Joint training resolved the
`nocturia`/`urinary_frequency` ambiguity in nocturia's favour: nocturia's `hedged`
recall 80.9% → 95.6% and 66 fragments improved against 30 worsened, while
`urinary_frequency`'s `adjacent` recall — the class that exists *because* of this
pair — fell 94.7% → 81.8%, at 41 improved against 38 worsened.

**Fever's headline hid a regression.** +0.6 overall and a dead-even 245/245 paired
count, but `null_ambiguous` moved against A3 (p=1e-06), driven entirely by
`attribution` falling 96.3% → 80.5%. A headline can be null while the slice the
libraries exist for moves.

The `haematuria_present` run starts at all only because of its three null
libraries: `_check_pools` requires a non-empty
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
count may not exceed the number of distinct sources the split can serve — filler
libraries, plus eligible companion signals when `--companion-share` is above zero
— and the generator refuses to start otherwise, rather than failing partway
through a 10,000-example run. The mix applies identically to every label class
and there is deliberately no way to set it per class; see section 5 for why.

Put other symptoms' language into the non-decisive slots (section 5):

```
python -m scripts.synthetic_data \
    --split train --count 10000 \
    --companion-share 0.5 \
    --out data/synthetic/generated/fever_present.train.jsonl
```

`--companion-share` defaults to 0.0, and at 0.0 the whole path is skipped: the
fragments chosen for a given seed are exactly the ones chosen before companions
existed. Above zero, a run whose split has no library declared `null_on` this
signal refuses to start rather than quietly producing the zero-share dataset
under the non-zero flag. There is no per-class version of this knob either, and
for the same reason: a companion share that varied by label would make clinical
language a proxy for the label. Read `companions.count_by_label_mode` in the
sidecar afterwards (section 7) — that is the check, not an optional extra.

Emit a label for every signal the example is entitled to one for, rather than
only the run's own (section 7):

```
python -m scripts.synthetic_data \
    --split train --count 10000 \
    --companion-share 0.5 --emit-signals all \
    --out data/synthetic/generated/fever_present.train.jsonl
```

`--emit-signals` defaults to `primary`, which is byte-identical to what the
generator emitted before the flag existed. `all` is built and not measured: no
trained arm uses it and `merge-folds` refuses a multi-key tree, so it produces a
dataset nothing downstream currently consumes. Read
`realised.labels_by_signal` in the sidecar afterwards — a companion head's prior
is nothing like the primary head's, and the decision rule is sensitive to that.

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

Generate a whole arm. Seven signals x five folds x three splits is 105
invocations, and the two arms differ in `--companion-share` and in **nothing
else** — same seed, same counts, same fold triple, same salt, same libraries. If
anything else differs the comparison is not readable and there is no way to
recover it after the fact:

```
for signal in fever_present dysuria_present urinary_frequency_present \
              nocturia_present flank_pain_present haematuria_present \
              recent_uti_present; do
  for fold in 0 1 2 3 4; do
    for split in train:10000 val:2000 test:2000; do
      python -m scripts.synthetic_data \
        --signal "$signal" --folds 5 --fold "$fold" \
        --split "${split%%:*}" --count "${split##*:}" \
        --companion-share 0.0 \
        --out "data/synthetic/generated/arm0/${signal}.fold${fold}.${split%%:*}.jsonl"
    done
  done
done
```

Arm P is the same loop with `--companion-share 0.5` and a different output
directory. Then merge each arm's tree separately:

```
python -m scripts.encoder_training merge-folds \
    --data-dir data/synthetic/generated/arm0 --folds 5
```

The merge refuses to mix arms — the sources have to agree on
`requested.companion_share` as well as on `generator_version` and the fold triple
(section 7) — so pointing it at a directory holding both would fail rather than
produce a tree that is half of each.

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

**Status: mostly not built, and each subsection says where it stands.** This
section started as "none of this is built"; 12.2 and the library-level half of
12.5 have since shipped, and their headers say so. Everything above section 12
describes the system as it actually is; everything below is a provisional plan
except where a subsection states otherwise, written down so it can be reviewed
and turned into an implementation plan later.

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

**Status: built and not measured.** The libraries for all seven signals exist
(section 3), and `--emit-signals all` now emits a key per signal from one run
(section 7). What has not happened is any *use* of it: no trained arm reads a
multi-key tree, `merge-folds` refuses one, and the payoff below is therefore
still a prediction rather than a measurement.

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
section 12.5 is about, it is not optional, and it is now enforced — section 7's
table is that rule.

**What measuring it would cost, and why it has not been paid.** A trained arm at
`--emit-signals all` is five more fold-trainings, and it would not be comparable
to the companion arms on the metric that matters. A companion head's realised
prior is roughly 2/2/95 (measured on the real libraries at
`--companion-share 0.5`) against the primary head's 15/25/60, and the decision
rule maximises macro-F1 *subject to a `null → true` rate no worse than argmax's*
— so moving the prior moves the constraint as well as the head, and a rule that
suppresses `true` because argmax already almost never says it would score as a
win for reasons unrelated to reading the text. The question a multi-key arm can
actually answer is "does more label per example buy training efficiency?", which
is a different question from the one companions exist to answer.

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

**Status: built for library-level declarations, not for per-line ones.** The
manifest carries `null_on` (section 4), the lint checks the half of it a lexicon
can check (section 8), and `--emit-signals all` emits the vector (section 7).
What is *not* built is the per-line label vector 12.3 needs — so cross-signal
`true`/`false` is still inexpressible, and the paragraphs below describe the end
state rather than today.

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
"silent". Single-signal text libraries get theirs from the manifest for free —
**this half is built**; the multi-symptom libraries of 12.3 would carry theirs
per line, and that half is not.

**Combination is validated on the vector, not the primary signal.** Two
fragments may be combined only if, for every signal, they do not assert
different things. Silent-plus-asserted is fine and yields the assertion.
Silent-plus-silent yields `null`. Asserted-plus-asserted is fine if they agree
and forbidden if they do not.

Section 7's table is the built version of this, and it is stricter in one place
and narrower in another. Stricter: *undeclared*-plus-anything yields no key at
all, because an undeclared library is not a silent one (section 4).
Narrower: asserted-plus-asserted is not permitted even when the two agree — one
fragment per signal per example (section 5) makes it unreachable, and the
generator raises rather than resolving it, because a library-level declaration
cannot establish that two lines agree.

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

**It works on a directory and preserves filenames**, which is not an arbitrary
choice. `scripts/encoder_training/` locates its data by `--data-dir` plus the
fixed pattern `{signal}.fold{i}.{split}.jsonl` (`dataset.FOLD_FILENAME`), so a
noisy dataset written as `...train.noisy.jsonl` beside the clean one would be
invisible to it, while a noisy *tree* with unchanged filenames is reachable by
pointing `--data-dir` at it and changing nothing else. That is the whole
integration, and it is what makes the 2×2 below cheap to run.

```
python -m scripts.synthetic_data.noise \
    --in-dir  data/synthetic/generated/folds \
    --out-dir data/synthetic/generated/folds-noisy-r02 \
    --rate 0.02 --seed 42
```

Every file in the input directory is copied through, damaged, and written with
its name intact, sidecar included — `dataset._read_stats` refuses to load a
dataset with no sidecar beside it, so emitting the JSONL alone would produce a
tree that fails at training time rather than at noising time.

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

**The decision is a declared protected lexicon, enforced in both directions.**
Never edit a token that is in the protected list, and never *produce* a
protected token from an unprotected one — an edit that would is discarded and
redrawn. The list is negation, person, tense and modality words plus the signal
vocabulary, and half of it already exists as `lint.FEVER_LEXICON` for the
filler-purity check. This is what keeps section 2's argument intact in spirit:
the edits that could change the answer are excluded by construction rather than
judged to be rare after the fact.

Two alternatives were considered and rejected, recorded because both look
cheaper and one of them keeps coming back. **Accepting the label noise and
quantifying it** — at a 2% per-word rate the damage lands inside a two-character
negation rarely, and roughly uniformly across labels — is defensible arithmetic,
but it leaves permanently wrong labels in the data with nothing recording which
ones, which is the exact failure mode section 2 exists to make impossible.
**Editing only words of five characters or more** protects almost everything
that matters with no lexicon at all, but it is unrealistic in a *directional*
way: real typists hit short words too, so the model would learn that short words
are always spelled correctly. That is a new artefact traded for an old one.

**The redraw must not be able to skew anything.** An edit is rejected only on the
protected-token test, which does not know the label, so rejection rates can vary
by *word*, never by class. Where an example's draw is rejected repeatedly the
pass moves on rather than looping — the word simply goes unedited, and the
realised edit rate reported in the sidecar drops slightly below the requested
one. That gap is telemetry, not a bug, and is worth printing.

#### The protected list is per signal, and the pass is fever-only until 12.5

Only fever's vocabulary exists today. A missing or thin list for another signal
fails **silently** — the pass runs, the output looks fine, and the label noise is
invisible in exactly the way section 2 is built to prevent. So the pass ships
with a hand-written fever list now, and:

**It refuses to run on any dataset whose signal is not `fever_present`.** The
signal comes from the dataset's own `.stats.json` sidecar, and a mismatch is a
startup error, not a warning. This is the same fail-fast posture as the
generator's check that the signal exists in the ruleset as a `send_to_encoder`
Boolean (section 11): a dataset that is quietly under-protected is worse than no
dataset, because nothing downstream would ever show it.

The hand-written list is therefore explicitly a **stopgap with a migration
target**. It has the same shape as 12.5's declared silence — a per-library
guarantee that currently lives in the author's head — and wants the same home: a
lexicon field in the manifest, added by step 3 of the sequencing, at which point
the hard-coded list and the signal guard both come out. Two lists in two modules
drifting apart is the outcome to avoid, and the guard is what stops that
happening by accident in the meantime.

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

#### The 2×2 is part of the work, not a follow-up

This is the part most easily got wrong. Noising all three splits and reading one
number cannot answer whether the pass helped: noise makes the test set harder at
the same time as it makes the training set richer, and those move the number in
opposite directions. A single post-noise score is uninterpretable, so **shipping
the script without the experiment would produce a knob nobody can decide whether
to turn.** The experiment is therefore in scope for the same ticket.

What answers it is a 2×2 — train on clean and on noisy, evaluate each against a
clean test set and a noisy one:

* noisy-trained vs clean-trained on the **noisy** test set — does training on
  damaged text buy robustness to damaged text? This is the claim being made.
* noisy-trained vs clean-trained on the **clean** test set — does it cost
  anything on text that is fine?

Four training runs against one fold configuration, all four sharing the same
generated data, which is the practical reason the pass is post-processing rather
than a generator flag.

Three constraints on reading the result, all of which follow from things already
in this document.

**It must be the same fold configuration across all four cells**, and fold mode
(section 6) rather than the default bands, or the per-sub-class numbers are the
2-to-6-cluster slices section 10 says cannot separate two models. Twenty
training runs, then, not four — five folds × four cells — which is the real cost
of this and should be understood before starting.

**The comparison is at fixed effective n, and that is what makes it readable.**
Noise creates no new clusters (section 10), so all four cells rest on exactly
the same ideas. That is unusually clean as experiments here go: the only thing
that varies is surface form. It also caps what a win can mean — a gain is
robustness to damaged surface, never better coverage of the clinical space.

**A rate sweep, not a single rate.** There is a rate above which this actively
hurts (see below), and one run cannot find it. Two or three rates — say 1%, 2%
and 5% — is the minimum that distinguishes "noise helps" from "a little noise
helps and more does not", and those are different findings.

How the runs are driven and reported is `arch_encoder_training.md`'s territory
and that document is where the numbers get written up; what belongs here is that
the script must be shaped to allow it, which means never forcing noise on every
split and always leaving the clean dataset on disk beside the noisy one.

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
3. ~~Add label vectors and declared silence (12.5) with the lint check, while
   there is still only one trained signal and it is cheap to get right.~~
   **Done for library-level declarations** — see sections 4, 7 and 8. Per-*line*
   vectors (12.3) are not built, so cross-signal `true`/`false` is still
   inexpressible and the nocturia / urinary-frequency pair is still undeclared.
4. ~~Companions: draw a non-decisive slot from another signal's declared-`null`
   library instead of filler.~~ **Built** — `--companion-share`, sections 5 and
   7, on top of step 3's declarations. It is the step this whole list existed to
   reach: it is the only one that puts another symptom's clinical language into
   an example whose label is still `null`, which is the property section 9's
   real-text failure says the data has never had. Inert at its default of zero,
   and the merge was relaxed to deduplicate on `meta.filler_only` rather than on
   the label mode so that a structural null carrying a companion is kept per
   signal (section 7). **What remains is measuring it**: two arms at
   `GENERATOR_VERSION` 3 plus a margin-reselection arm, and until they are
   trained and scored on the 67 submissions this step has bought nothing that
   has been demonstrated.
5. Template the filler libraries (12.1), lowest-risk use of procedural
   generation, and add the templates-per-library and clusters-per-split lint
   reports. Note this does *not* raise the fragment-count ceiling: that ceiling
   counts *sources* — filler libraries and eligible companion signals — not
   their size (section 5), so new filler libraries and new declared companion
   pairs are what raise it, and splitting an existing filler library in two
   raises it as surely as writing a new one does.
6. Engine changes for multi-signal examples (12.2). **Built** — `--emit-signals
   all` emits the several keys, on top of step 3's declarations. What remains is
   *using* it: `merge-folds` refuses a multi-key tree and no arm trains on one,
   so the payoff is still unmeasured (12.2).
7. Multi-symptom and out-of-scope fragments (12.3, 12.4), which need the JSONL
   library format. This is what the nocturia / urinary-frequency pair is waiting
   on: their 14 undeclared cells (section 4) are per-*line* facts and no
   library-level field can express them.
8. Template the clinical libraries, once there are enough distinct templates per
   library for the split arithmetic to work.

**The random-error pass (12.6) is independent of everything above it** — it is
post-processing over finished text and imports nothing from the generator — so
it can slot in anywhere after step 1, and it deliberately does not wait for step
3. It ships with a hand-written fever lexicon and a hard refusal to run on any
other signal, and step 3 is where that hard-coded list moves into the manifest
and the refusal comes out. Sequencing it that way is a decision to pay for the
guard rather than to wait.

Nor does it depend on the training tooling growing anything: `--data-dir`
already points the runs at an arbitrary tree, which is why 12.6 writes whole
directories with filenames preserved. The 2×2 is twenty runs against tooling
that exists, so the constraint on when to start is compute and attention, not a
missing capability anywhere on this list.

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

### 12.8 The multi-symptom expansion, and what it is waiting on

`planned_updates/multi_symptom_training_expansion.md` is the plan of record for
getting from one trained signal to six. It splits into three unblocked tasks and
four that are not, and the split is worth knowing because it is not where it
first appears.

**Unblocked today, no dependency on 12.5:**

1. **Folder restructure — landed.** A condition layer under `data/synthetic/`:
   condition-agnostic filler at the top, `conditions/uti/{symptoms,filler}/`
   below it. See the section 3 tree. It was dataset-neutral in fact, not only in
   principle: `fever_present` and `haematuria_present` train splits regenerated
   at the same flags after the move came out byte-identical, sidecars included.
   Nothing in the generator keys off a path, only off a library's manifest
   `name`. The one thing it did *not* do at the time was split
   `expectations.txt`; that waited for a `GENERATOR_VERSION` bump and **landed
   with the bump to 3**, moving 34 of its 100 lines to
   `conditions/uti/filler/expectations_uti.txt` (section 3).
2. **Generalise the filler lint to every signal — landed.** This is 12.5's
   *lint* half and nothing else: no manifest schema change, no label vectors.
   It is separable because it checks a guarantee we already rely on rather than
   declaring a new one, and everything after it depends on filler being silent
   about all six signals rather than only about fever. Section 8 has the
   lexicon shapes and the measured recall; the answer on the committed tree is
   that filler is clean for all six, with no baselined exceptions.
3. **Six single-signal runs.** No code change at all — `--signal` is already a
   flag on every subcommand and has only ever been passed one value.

**Landed since:** the realistic held-out evaluation (section 9, scored on every
Arm B fold), the **merge tool** (`merge-folds`, described at the end of
section 7), and **joint multi-head training** itself: `train.py` separates
"which dataset" (`--dataset`) from "which heads" (`--signals`), each head's
margin is selected independently, and one shared DD6 epoch-selection criterion
— the unweighted mean of every head's own validation macro-F1 — picks the
epoch every head is scored at. `arch_encoder_training.md` section 4b is the
design; `planned_updates/joint_multi_head_training_implementation.md` task 3
is the instructions it was built from. **Task 4 has landed too**: `joint-compare`
loads three fold trees in one invocation — A1 (the signal alone), A2 (the same
clusters, ~4.5× the recombinations) and A3 (joint) — and writes one report per
signal holding all three. A1 against A3 is the paired comparison, because A3's
slice for a signal *is* that signal's own examples under their own ids; A2 pairs
with nothing and comes back as a **recorded** untestable pair rather than as a
missing row, which is what stops "could not be tested" being read as "no
difference found". `arch_encoder_training.md` section 4c has the arm table and
the sentence about what no arm isolates. What is still outstanding is the sweep
itself (task 5), which needs a GPU and the A2 datasets generating.

**Landed since that was written:** the multi-symptom recombinations themselves —
the `null_on` declaration pass (section 4), `--companion-share` (section 5),
`--emit-signals all` (section 7) and the seventh signal's libraries (sections 3
and 9). What is still outstanding is the *measurement*: the two arms have to be
generated, trained and scored before any of it is worth anything.

**Still blocked:** per-line label vectors (12.3), and cluster-tagging the four
untagged library sets.

**The one thing that surprises people about the merge.** Joint training on
merged single-signal datasets needs *no* part of 12.5. `fold_bucket` is a pure
hash of the cluster key and salt with no knowledge of signals, so cluster
disjointness survives concatenation; and because each example still carries only
its own signal's key, the other five heads see a *missing* key, which section 7
already defines as "no claim, mask the loss" rather than as a `null` assertion.
No silence is declared, so none needs checking.

The exception is the structural nulls, and it is the reason task 2 above comes
first. Because `run_seed` does not depend on the signal, six per-signal runs emit
**byte-identical structural nulls, example-for-example** — the only text they
share. Merging them means either keeping six copies of each, or keeping one and
labelling it `null` for all six signals. The second is strictly better (same
gradients, 25% fewer forward passes, and each head keeps exactly the 15/25/60
mix it trained on alone), but labelling one filler-only example `null` six times
*is* a silence assertion about the filler libraries. Task 2 above is what makes
that assertion checkable, and it now holds: zero hits across all six signals.
The merge tool takes the second option and asserts the byte-identity rather than
trusting it; the end of section 7 has the shape it writes. Note what the lint
does and does not license — it says the filler *libraries* are silent, which is
exactly the guarantee the structural-null union needs, and says nothing about
whether a *signal* library is silent about the other five. That
second question is 12.5's, and the `flank_pain_false` lines in section 3 are the
known counter-example waiting for it.

**Structural nulls should shrink as 12.2 and 12.3 grow.** They are the least
realistic example type in the dataset: patients rarely submit free text with no
clinical content at all. A dysuria sentence labelled `fever_present: null` is a
better structural null than any filler-only recombination, because it is a null
*with clinical language in it* — which is the case section 9's real submissions
are full of and the current filler mostly is not.
