# Does the model read the words, or just the vocabulary?

*Written in plain language on purpose. Every number here comes from
`reports/encoder_training/lexical/` — the four report files and
`paired_flip_rate.json`. **Those files are the authority** — if this document
ever disagrees with one of them, the report is right and this is stale. Read this
to understand what happened; quote figures from the reports. The technical
version is `2026-09-04-lexical-variant.md`, and the bounds it is read against
were written down before the run in `2026-09-04-lexical-variant-preregistration.md`.*

---

## 0. The one-sentence version

The problem is real and the fix works, but both are **much smaller than expected**
— and the safety check we built to catch the fix going wrong was pointed at the
wrong data, so it said "fine" while the one instrument that could see real
patients' writing said something more worrying.

---

## 1. What the worry was

The model learns from a few hundred hand-written sentence fragments, recombined
into thousands of training examples. Whoever wrote those fragments had habits.
When they wrote a line meaning *"I have a fever right now"* they tended to reach
for one word; when they wrote *"I had a fever last winter"* they tended to reach
for another.

We measured that back in Task 1 and it was stark. The word **"fever"** appears on
41 of the 45 lines meaning *"that was ages ago"* and on **none** of the 50 lines
meaning *"my mum has one, not me"*. The word **"temperature"** appears on a
quarter of the lines that decide the answer and on **no** "ages ago" line at all.

That is a shortcut sitting in the data waiting to be learned. A model could get
good marks by noticing "the word *temperature* means this one counts, the word
*fever* means it doesn't" — which would work beautifully on our data and fall
apart the moment a real patient used the other word.

**But a shortcut existing in the data is not the same as a model using it.** That
was the open question, and this run asked it directly.

---

## 2. What was built

A script that takes a finished set of training data and swaps words for other
words that mean the same thing — "a fever" ↔ "a temperature" ↔ "a high
temperature", "I've" ↔ "I have". 36 rules, each written and reviewed by hand,
each carrying a written promise that it changes no tense, no person, no
certainty and no denial.

Three things about how it works matter:

* **It swaps in both directions.** "Ages ago" lines over-use *fever*; "this
  counts" lines over-use *temperature*. Flattening that needs both swaps, and a
  naive two-way synonym list would turn "I checked my temperature and it was
  high" into "I checked my fever and it was high".
* **It never sees the answer.** The script cannot apply itself to the "yes"
  examples and not the "no" ones, because nothing in it can tell which is which.
* **It is not turned all the way up.** Rewriting *every* word doesn't flatten the
  bias, it *reverses* it — which was measured while writing the rules. A quarter
  of messages are left completely alone and each remaining opportunity fires 40%
  of the time, so about 39% of messages end up changed.

Then four models were trained: two trained on the original data and two on the
rewritten data, each tested against both. Twenty trainings, about forty minutes.

---

## 3. The main result: does the model change its mind?

Take one message, rewrite the wording, keep the meaning identical, and ask the
model twice. If the two answers differ, one of them is wrong — and you don't need
to know which to know something went wrong. We call that a **flip**.

3,910 of the 10,000 test messages were actually reworded, so those are the only
ones that *can* flip.

| | how often it flips | roughly |
|---|---|---|
| **today's model** | **1.89%** | 1 message in 53 |
| **model trained on reworded text** | **0.84%** | 1 in 119 |

So the fix works — it more than halves the problem. **But look at the size.** We
had written down beforehand that this would count as a success if flips fell by
*5 percentage points*, and they only had 1.89 points to fall from. More on that
mistake in section 6.

### Where the flips go is the real finding

A flip rate is one number and it hides the interesting part. Here is which way
the answers moved:

| the model went from… to… | today's model | reworded-trained |
|---|---|---|
| **"didn't mention it" → "yes, they have it"** | **46** | 10 |
| "didn't mention it" → "no, they denied it" | 13 | 6 |
| "yes" → "didn't mention it" | 7 | 1 |
| everything else | 8 | 16 |

**Nearly two thirds of today's model's flips are the same mistake.** Take a line
that means *"my mum had a fever"* or *"I had one last winter"*, change the word
*fever* to *temperature*, and the model starts saying the patient has a fever
right now. That is exactly the shortcut section 1 predicted, caught in the act.
The reworded-trained model cuts it from 46 to 10.

It also shows up in exactly the right places. Broken down by what the message
actually says:

| kind of message | today's model | reworded-trained |
|---|---|---|
| patient reports it | 4.4% | **0.5%** |
| patient is vague / talking about someone else / the past | 2.8% | **0.9%** |
| patient denies it | 1.4% | 1.8% |
| message never mentions the topic at all | **0.0%** | **0.0%** |

That last row is the check that makes the rest trustworthy. Those 1,067 messages
have no fever vocabulary in them — the only thing the script changed was
apostrophes — and neither model changed its mind about a single one. If that
number weren't zero, it would mean a rule was quietly altering meaning and the
whole run would be void.

---

## 4. The catch: it barely costs anything to have the problem

Flips are a count of *changed minds*, not of *wrong answers*. So we also asked:
how much accuracy does today's model actually lose when the wording changes?

**0.21 points.** 93.29% → 93.08%.

That is the number that decides what this ticket is worth. The mistakes the model
makes under rewording very nearly cancel out — for every message it newly gets
wrong, the rewording happens to fix another. The bias is real, it is systematic,
it has a name and a direction, and on our own test data it costs almost nothing.

And the reworded-trained model? It scores about 1.2 points better than today's
model — on *both* kinds of test text equally. Every error bar in this experiment
is about ±2 points wide and all four overlap heavily. **Nothing here is
separated.** A 1.2-point gain that is the same size on rewritten and unrewritten
text looks like ordinary "more variety in training helps a bit", not like a
shortcut being removed.

---

## 5. The part that should give pause

We have 67 real patient submissions, held back and never used to make any
decision. They can't rank two models — the error bar is ±12 points and only 9 of
the 67 are people actually reporting a fever. They are there to catch a *large*
problem. They caught something.

| on the 67 real submissions | today's model | reworded-trained |
|---|---|---|
| overall score | 73.7% | **81.2%** |
| invents a fever nobody mentioned | 23.7% | **9.0%** |
| notices a fever somebody did report | **60.0%** | 42.2% |
| gets the ones that matter right | **76.7%** | 65.6% |

Read the first row and it looks like a win. Read the rest and you see what
actually happened: **the reworded-trained model became more cautious.** It says
"didn't mention it" more often. Since 49 of the 67 submissions *are* "didn't
mention it", that lifts the overall score by 7.5 points while it quietly gets
worse at the thing we actually want.

Both directions matter, and they pull against each other. Inventing a fever out
of nothing dropped from about 12 of 49 cases to about 4 — that is a genuine
improvement on a failure mode this project has tracked since August. But noticing
a real fever fell from about 5 of 9 to about 4 of 9.

**None of this is statistically separated.** Nine submissions, five folds, error
bars wider than the effect. Two things still make it worth taking seriously: the
direction is consistent across four of the five folds, and it is **not** a
side-effect of how the model's confidence dial was set — that dial moved the
*opposite* way, which should have made the model say "yes" more, and it said
"yes" less anyway.

---

## 6. Two things we got wrong before the run, left on the record

Both of these are mistakes in the plan, written before any model was trained.
They're recorded rather than quietly corrected, because a target rewritten after
seeing the result isn't a target.

**We set a target that was impossible to hit.** The success bar was "flips fall
by 5 percentage points". Flips started at 1.89%. They could not have fallen by 5.
That bar came from an earlier experiment that measured flips on *real* patient
writing and found 15.4% — and nobody asked whether our own synthetic test data,
which is built from the same sentence fragments as the training data, could ever
produce a number that big. It can't, and we had already written down the reason
why in the same document, about a different measurement.

**We put the safety check on the wrong data.** We knew in advance that a model
could cheat this test by simply answering "didn't mention it" to everything —
that scores a flip rate of zero. So we added a guard: the model isn't allowed to
get worse at the messages that matter. It passed comfortably; on our synthetic
data the reworded-trained model got *better* at those.

Then section 5 happened. On real patients' writing the reworded model did become
more cautious, and it did get worse at the messages that matter — by 11 points.
**The guard we built specifically to catch that behaviour was measuring somewhere
the behaviour doesn't show up.** That's the most useful thing this run taught us,
and it applies to any guard of this shape we build in future.

---

## 7. The predictions we made before the run, scored

| what we predicted | what happened |
|---|---|
| **Flips fall by at least 5 points** | **Not met** — and it was never possible. Fell 1.05 points, from 1.89% to 0.84%. |
| **The model doesn't get worse at the messages that matter** | **Held** on synthetic data (it got 1.2 points better). Did **not** hold on the 67 real submissions. |
| **Nothing should move on our own test data** | **Roughly held.** Everything moved by 1.2 points or less and nothing is separated. |
| **The data set does not get bigger** | **Held, mechanically.** Same 10,000 messages, same 417 underlying ideas. One sentence written twelve ways is one idea. |
| **The 67 real submissions are a sanity check, not a scoreboard** | **Held, and they earned their keep** — they're the only place anything visible happened. |

---

## 8. What these numbers are not

* **This is one symptom.** Everything here is fever. Nothing was done for the
  other six.
* **The data set did not get bigger and cannot be described as having done so.**
  Rewording a sentence twelve ways does not create twelve ideas. Both sets hold
  exactly the same 10,000 messages built from the same 417 underlying ideas, and
  the error bars are set by that 417, not by the 10,000.
* **The four models can't be compared properly.** Because of how the tool is
  built, each of the four ran as its own separate job and wrote its own separate
  report, which means we can only compare them through overlapping error bars
  rather than message-by-message. That would have been the sharper test and it
  isn't available. Worth fixing before anyone runs this again.
* **The rewriting rate wasn't tuned.** The setting used was read off the data
  beforehand as a sensible guess. Nobody tried a range of them.
* **The 36 promises are the residual risk.** Each rule carries a hand-written
  promise that it doesn't change meaning, and no automated test reads one. Two
  mechanical checks sit behind them and both passed, but what ultimately stands
  behind those promises is a person having read them.

---

## 9. What to do next

1. **Don't roll this out to the other six symptoms.** The accuracy case is 0.21
   points on our own data and unmeasurable on real writing. Extending a piece of
   machinery across six symptoms on a result that isn't separated is how a
   project ends up with a component nobody can later evaluate.
2. **Keep the finding, though.** "Change one word and the model starts inventing
   fevers, 46 times out of 74" is worth knowing, and the same shape shows up in
   the real-submission numbers. It's the strongest evidence yet that the concern
   in section 1 is about the model and not just about the data.
3. **The blocker is measurement, not method.** Every target in this experiment
   was set against test data that — by our own argument — cannot contain the
   problem we were hunting. The only instrument that saw anything was 67
   submissions with a ±12-point error bar. **More real, hand-labelled patient
   writing is the prerequisite for spending more time here**, not more synthetic
   experiments.
4. **Rewrite the safety check.** Any future guard against "the model went quiet"
   has to be measured where going quiet is visible.

The honest summary: we suspected the model was reading our writing habits rather
than what patients actually said, and we caught it doing exactly that, in a
specific and nameable way. Then we found the habit costs almost nothing on our own
test data, that the fix's benefit can't be told apart from noise, and that on real
patients' writing the fix may have made the model more timid in a way our safety
check was built to catch and couldn't see. The mechanism is confirmed. The case
for acting on it is not.
