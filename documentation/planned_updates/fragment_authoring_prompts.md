# LLM prompts for the three targeted fever libraries

Drafting prompts for the library work `reports/encoder_training/2026-08-09.md`
identified. One prompt per library, each self-contained so it can be pasted into
a fresh chat with no other context.

**These produce a first draft, not a library.** Read §1 before using them.

---

## 1. What an LLM can and cannot do here

The pipeline's central guarantee is that **the label cannot be wrong about the
text, because the text was chosen to fit the label** (`arch_training.md` §2).
LLM drafting does not break that guarantee — each prompt writes into one named
library with one fixed label, and a fragment that does not fit its library gets
deleted rather than relabelled. That is why every prompt below is "write
fragments that belong in *this* library" and never "write fragments and tell me
what they mean".

Three real risks, in order of how much they matter:

**Idea diversity is what counts, and it is what LLMs are worst at.** Effective
sample size is the number of distinct *clusters*, not fragments. An LLM asked for
forty fragments will cheerfully return forty rewordings of six ideas, and the
library will look 40 healthier while being 6 healthier. Every prompt below
therefore makes the model enumerate its distinct ideas *first*, so you can audit
the list before reading a single fragment. If the idea list has 12 entries, you
have 12 ideas no matter how many lines come out.

**LLM patient-voice is not patient voice.** It is a model's idea of how patients
write, and it converges on a tidy, well-punctuated, mildly formal register. The
prompts push against this and it will still drift. You are the filter.

**Boundary errors are the way wrong labels get in.** Each of these three
libraries sits next to another library where the same sentence would carry a
*different* label. "My mum had a fever" is `null` (third-party); "my mum had a
fever but I never got one" is `false`. Get that wrong and you have a permanently
mislabelled example, which is the one failure mode this pipeline was built to
make impossible. Each prompt states its boundary as a decision test and gives
contrast examples from the neighbouring library.

**Do not use an LLM for the held-out realistic evaluation set.** If the training
fragments and the evaluation set both come from a language model, the evaluation
measures whether the encoder learned that model's idea of a patient. That set has
to be human-written to be worth anything.

**A free experiment while you are here.** These fragments arrive in a known git
commit, so the per-fragment error table can later be split into hand-written and
LLM-drafted clusters and compared. If LLM-drafted clusters are learned as well as
hand-written ones, that is the single largest lever on the 27,500-fragment
problem in `encoder_next_steps.md` §1. If they are learned worse, that is worth
knowing before the approach is used on the other 79 signals.

## 2. House rules every prompt already contains

Repeated here so you can check the output against them:

* Plain text, one fragment per line, no numbering, no bullets, no quotation marks.
* UK English, first person, patient writing to their GP.
* Verbatim style is wanted: missing apostrophes, run-on sentences, no final full
  stop, the odd typo. The live encoder gets raw patient text, so tidy fragments
  train on a tidier world than the one it will meet.
* No urgency or justification language — "I've got three meetings I can't miss",
  "I need a sick note". `arch_training.md` §9 records that ~17% of `fever_true`
  already bundles this and only 8% of `fever_false` does, so it is a live
  shortcut. Do not feed it.
* Two lines that are the same idea reworded get the same `[cNN]` marker, on both.
  Distinct ideas are worth more than tagged pairs, so prefer them.
* Numbering restarts per library and must not collide with existing markers in
  that file — check the last `[cNN]` used before appending. As it stands
  `fever_null_hedged` runs to `[c10]`, and `fever_true` and `fever_false` carry
  **no markers at all**, so a first pair in those files starts at `[c01]`. That
  absence is a known gap rather than a sign there is nothing to tag:
  `arch_training.md` §6 records 3 incidental near-duplicates in `fever_true` and
  1 in `fever_false` that were never hand-tagged because the systematic twinning
  was in the null libraries. If your draft adds paraphrase pairs there, tag them
  — they are exactly the kind that inflate a validation score.

## 3. After the draft, before the commit

1. **Read every line.** Delete anything you would hesitate over. A deleted
   fragment costs nothing; a mislabelled one is permanent.
2. **Check the idea list, not the line count.**
3. `python -m scripts.synthetic_data --lint` — cross-split near-duplicates,
   hedge markers in the positive and negative libraries, split coverage.
4. `python -m scripts.synthetic_data --folds 5 --find-fold-salt` — **new
   fragments change bucket coverage and salt `32` may stop working.** The
   empty-cell guard covers the whole manifest, so this can block generation for
   every signal.
5. Regenerate the folds, rerun `finetune`, and write the run up against the
   prediction in §7 below.
6. Update the library sizes in `arch_training.md` §3 and §10, and
   `FEVER_LIBRARY_CLUSTERS` in `scripts/encoder_training/report.py` — the
   coverage tests in `tests/test_encoder_training_baselines.py` will fail until
   you do, which is deliberate.

---

## 4. Prompt A — contrastive negatives for `fever_false`

*Target: 30–40 fragments. The largest single error family; every one of the five
worst-performing fragments in the last run was of this kind and the model got
each of them wrong on 100% of its examples.*

```
I am building a hand-written dataset that teaches a model to read a patient's
free-text message to their GP and decide whether the patient is saying they have
a fever. Every fragment goes into a library whose label is fixed in advance, and
your job is to write fragments that belong in one specific library. If a
fragment does not clearly belong there, leave it out rather than adjusting what
it means.

THE LIBRARY: fever_false. Label: FALSE — this patient is saying they do NOT have
a fever in this current illness.

WHAT I NEED, SPECIFICALLY. The library already has 60 straightforward negatives
("My temperature has been normal the whole time"). What it has almost none of is
the CONTRASTIVE negative: a sentence that mentions a real fever belonging to
someone else, or to another time, and then denies one for this patient now. A
model trained without these learns "fever words present, therefore positive" and
gets every one of them wrong.

Examples of the shape I want, all correctly labelled FALSE:
  My mum was really poorly with a fever last week and I was caring for her but I never got one myself
  Back when I caught that bug going round the office I felt like I was on fire, but I've not had anything like that with this
  I know what it's like when I get a temperature because I go all clammy and weird, and that definitely hasn't happened

THE BOUNDARY, AND IT IS THE WHOLE TASK. Two neighbouring libraries carry the
label NULL, not FALSE:
  - Someone ELSE has a fever, with no statement about the writer's own
    temperature now  ->  NULL, belongs elsewhere.
    e.g. "My son has had a fever on and off for the past few days and I wanted
    to check if I should be concerned"
  - The writer had a fever in the PAST, with no statement about now  ->  NULL,
    belongs elsewhere.
    e.g. "I had a fever a couple of weeks ago that lasted about three days"

THE DECISION TEST, apply it to every line you write: delete the denial clause.
If what remains says nothing about THIS writer's temperature during THIS
illness, then the fragment is a null and you must not write it. A fragment
qualifies only if it contains an explicit denial of the writer's own fever now.

VARY THESE AXES so that the fragments are distinct ideas rather than rewordings:
  - who the other person is: partner, child, parent, colleague, whole household,
    someone at the school gate, a patient the writer nursed
  - what the other time was: a bug going round last winter, flu years ago, the
    day after a vaccination, a previous infection, childhood
  - the form of the denial: thermometer checked, partner felt their forehead,
    "nothing like that this time", "I'd know because I always get the shakes",
    "I've been fine in that respect"
  - how certain the denial is — but keep it a denial. If it becomes "I'm not
    sure", it is a different library and you must not write it.

STYLE:
  - UK English, first person, writing to their GP.
  - One fragment per line. No numbering, no bullets, no quotation marks, no
    commentary.
  - Real patient register: missing apostrophes, run-on sentences, no final full
    stop, the occasional typo. Do not polish.
  - NO urgency or justification language. No "I can't afford time off", no "I
    need a sick note", no "I have an important meeting". This is a known
    shortcut in the data and I am trying to remove it, not add to it.
  - LENGTH BUDGET, and please respect it: this construction is naturally long
    and the library's existing median is 20 words. Keep at least a third of your
    fragments under 15 words, and none over 40. If negatives become
    systematically longer than the other libraries, sentence length becomes a
    clue to the label and the dataset gets worse rather than better.
  - If two of your lines are the same idea reworded, prefix BOTH with the same
    marker: [c01], [c02] and so on. Prefer distinct ideas.

OUTPUT IN TWO PARTS:
  1. First, a numbered list of the distinct IDEAS you are going to write, one
     short phrase each. I will check this list for repetition before reading the
     fragments.
  2. Then the fragments, one per line, nothing else.

Write 35.
```

## 5. Prompt B — non-vocabulary positives for `fever_true`

*Target: 30–40 fragments. The model has memorised a lexicon; positives that do
not use it are read as `null`.*

```
I am building a hand-written dataset that teaches a model to read a patient's
free-text message to their GP and decide whether the patient is saying they have
a fever. Every fragment goes into a library whose label is fixed in advance, and
your job is to write fragments that belong in one specific library. If a
fragment does not clearly belong there, leave it out rather than adjusting what
it means.

THE LIBRARY: fever_true. Label: TRUE — this patient is saying they have, or have
had, a fever during this current illness.

WHAT I NEED, SPECIFICALLY. The library already has 96 fragments and nearly all of
them announce the fever in so many words: "I had a fever", "I had a high
temperature", "I was feverish". A model trained on those learns a vocabulary
rather than a meaning, and then misreads exactly the sentences real patients
write. What I need are positives where the claim is carried by IDIOM, by a
MEASUREMENT, or by PHYSICAL DESCRIPTION.

Examples of the shape I want, all correctly labelled TRUE:
  Came down with something Tuesday night, been like a hot water bottle ever since
  Thermometer said I was cooking, way above normal
  38.9 on the ear thermometer this morning and it hasn't come down

HARD CONSTRAINT: do not use the words "fever", "feverish", "temperature",
"febrile" or "pyrexia" anywhere. Those are precisely the words the model is
leaning on. Other words are allowed, but a fragment whose whole content is "I
felt hot and shivery" adds nothing — the library has that idea many times over.

THE BOUNDARY, AND IT IS THE WHOLE TASK. Two neighbouring libraries carry the
label NULL, not TRUE:
  - Heat words used with no bodily-temperature meaning  ->  NULL.
    e.g. "My blood's been boiling thinking about the parking situation"
  - Genuine uncertainty about whether there is a fever  ->  NULL.
    e.g. "My wife said I felt warm when she touched my forehead but I felt
    normal to me"

THE DECISION TEST, apply it to every line you write: would a GP reading this one
sentence and nothing else conclude that the patient is telling them they ran a
fever during this illness? If the honest answer is "probably" or "it depends",
it is a null and you must not write it. Only write the ones where the answer is
plainly yes.

A specific trap: someone else's observation counts as a positive ONLY if the
writer accepts it as established. "My wife said I was roasting and the
thermometer agreed" is TRUE. "My wife said I felt warm but I felt fine" is NULL
and belongs in a different library.

VARY THESE AXES so that the fragments are distinct ideas rather than rewordings:
  - thermometer readings, in and out of context: a number with no units, a
    number the writer clearly thinks is high, "it was reading way over", a
    forehead scanner, an ear thermometer, the reading going up and down
  - household and physical idiom: hot water bottle, radiator, furnace, kettle,
    oven, "cooking", "roasting", "poached"
  - physical consequences with no temperature word: soaked through the sheets,
    changed the bedding twice, teeth chattering, couldn't stop shaking,
    dressing gown wringing wet, had to sit in front of the fan
  - another person's observation that the writer accepts as fact
  - understatement and vagueness that is still an assertion: "definitely running
    something", "I was cooking last night, no question"

STYLE:
  - UK English, first person, writing to their GP.
  - One fragment per line. No numbering, no bullets, no quotation marks, no
    commentary.
  - Real patient register: missing apostrophes, run-on sentences, no final full
    stop, the occasional typo. Do not polish.
  - NO urgency or justification language. No "I can't afford time off", no "I
    need a sick note", no "I have an important meeting". This is a known
    shortcut in the data and I am trying to remove it, not add to it.
  - LENGTH BUDGET: mostly 5 to 25 words. Nothing over 35. The library already
    contains one 98-word fragment and it is one the model gets wrong every time;
    I do not need another.
  - If two of your lines are the same idea reworded, prefix BOTH with the same
    marker: [c01], [c02] and so on. Prefer distinct ideas.

OUTPUT IN TWO PARTS:
  1. First, a numbered list of the distinct IDEAS you are going to write, one
     short phrase each. I will check this list for repetition before reading the
     fragments.
  2. Then the fragments, one per line, nothing else.

Write 35.
```

## 6. Prompt C — growing `fever_null_hedged`

*Target: 30–40 fragments. 32 clusters today, the smallest confounder library, the
worst-performing at 75.6% and the widest interval in the table.*

```
I am building a hand-written dataset that teaches a model to read a patient's
free-text message to their GP and decide whether the patient is saying they have
a fever. Every fragment goes into a library whose label is fixed in advance, and
your job is to write fragments that belong in one specific library. If a
fragment does not clearly belong there, leave it out rather than adjusting what
it means.

THE LIBRARY: fever_null_hedged. Label: NULL — the patient is genuinely uncertain,
and the text does not establish whether there is a fever or not.

WHAT I NEED, SPECIFICALLY. This is the smallest and worst-performing library in
the set: 42 fragments covering 32 distinct ideas, and a model trained on them
gets a quarter of them wrong, split roughly evenly between guessing yes and
guessing no. That split is what genuine uncertainty should look like when there
are too few examples of it. I need more ideas, and in particular more KINDS of
uncertainty.

Examples of what is already there:
  I'm not sure if I have a temperature or not
  Sometimes I feel hot but I don't know if it's just me
  I haven't used a thermometer but my forehead feels a bit warm

KINDS OF UNCERTAINTY I WANT MORE OF — these are the axes to vary, and several
are barely represented:
  - no thermometer in the house, so no way to check
  - a borderline reading the writer cannot interpret: "it said 37.6, I don't
    know if that counts"
  - conflicting evidence: someone else says they feel warm, the writer feels fine
    (or the reverse)
  - it comes and goes, so they cannot tell whether it is real
  - confounded by the environment: just came in from the cold, the office is
    boiling, slept under a heavy duvet
  - confounded by activity: just walked up the stairs, just got out of the bath,
    been rushing around
  - confounded by medication: took paracetamol a few hours ago so cannot tell
    what is underneath it
  - confounded by something they already have: hot flushes, anxiety, a hangover,
    a warm room at work — where the writer explicitly says they cannot tell
    which it is
  - a reading taken at the wrong moment, or a thermometer they do not trust
  - simply not having paid attention until now

THE BOUNDARY, AND IT IS THE WHOLE TASK. The uncertainty must not resolve. The
moment the fragment settles the question in either direction it belongs in a
different library:
  - "I wasn't sure so I checked and it was 38.5"  ->  that is a positive, do not
    write it.
  - "I wondered if I was warm but my temperature was normal"  ->  that is a
    negative, do not write it.

One more boundary. If the writer confidently attributes the heat to a known
non-fever cause and is NOT uncertain about it — "I get hot flushes with the
menopause, I've had them daily for two years" — that belongs in a different
library again. It only belongs here if they say they cannot tell which it is.

THE DECISION TEST, apply it to every line you write: could a GP reading this one
sentence and nothing else answer yes or no? If they could, it does not belong
here.

STYLE:
  - UK English, first person, writing to their GP.
  - One fragment per line. No numbering, no bullets, no quotation marks, no
    commentary.
  - Real patient register: missing apostrophes, run-on sentences, no final full
    stop, the occasional typo. Do not polish.
  - NO urgency or justification language. No "I can't afford time off", no "I
    need a sick note", no "I have an important meeting".
  - LENGTH BUDGET, and this one matters more than usual: the existing fragments
    in this library run from 8 to 20 words, which is the narrowest band of any
    library in the dataset — narrow enough that sentence length is itself a clue
    to the label. Please write across a much wider spread: a handful under 10
    words, a handful between 25 and 45, the rest in between.
  - If two of your lines are the same idea reworded, prefix BOTH with the same
    marker. This library already uses markers up to [c10], so start at [c11].
    Prefer distinct ideas.

OUTPUT IN TWO PARTS:
  1. First, a numbered list of the distinct IDEAS you are going to write, one
     short phrase each. I will check this list for repetition before reading the
     fragments.
  2. Then the fragments, one per line, nothing else.

Write 35.
```

## 7. Prediction, recorded before the work

So the next run can be scored against it rather than rationalised, as
`arch_encoder_training.md` asks:

* **`fever_false` recall rises most**, from 78.1%. It is the largest error pool
  and the gap is a specific construction rather than a general weakness.
* **`fever_true` recall rises modestly**, from 81.0%. Non-vocabulary positives
  are a genuinely harder problem than contrastive negatives — there is no cue to
  learn, only a wider notion of what counts as an assertion.
* **`fever_null_hedged` improves least in accuracy but most in interval width**,
  because the library is small enough that adding 35 fragments moves the
  effective n from 32 clusters to roughly 60 and roughly halves the uncertainty
  on that row. An unchanged point estimate with a much narrower interval would be
  a good outcome, not a null result.
* **Overall decisive accuracy ends between 85% and 89%**, up from 83.5%.
* **`null → true` gets worse before it gets better.** The contrastive negatives
  contain assertions of fever, so a model that half-learns them will produce more
  confident `true` predictions on truly-`null` text. Watch that cell — it is the
  one that invents a symptom into a patient's form — and be ready for the
  decision rule to have to work harder.
