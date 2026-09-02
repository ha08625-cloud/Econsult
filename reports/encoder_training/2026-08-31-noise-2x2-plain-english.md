# Typos: does training the model on messy text make it better at reading messy text?

*Written in plain language on purpose. Every number here comes from the
seventeen report files under `reports/encoder_training/noise/`. **Those files are
the authority** — if this document ever disagrees with one of them, the report is
right and this is stale. Read this to understand what happened; quote figures
from the reports. The technical version is `2026-08-31-noise-2x2.md`.*

---

## 0. The one-sentence version

Yes — and by a lot more than the effort it cost. A model trained on clean text
gets **8.5 points worse** when the text it reads is full of typos; a model
trained on typo'd text gets **all of that back**, and loses nothing on clean text
in exchange. And you don't have to guess how messy real messages are: a model
trained on *slightly* messy text handles *very* messy text almost as well as one
trained on it directly.

---

## 1. What the problem was, in one paragraph

The model learns to read patients' free-text messages from a few hundred
hand-written sentence fragments, recombined into thousands of examples. Those
fragments were typed by people concentrating at a keyboard. Real submissions get
typed into a phone at eleven at night by somebody who feels ill. Nobody had ever
checked what that difference costs us — whether "I've had a temprature since
tuesday" still gets read as a fever.

---

## 2. What was changed

A script that takes a finished set of training data and makes a damaged copy of
it: dropped letters, doubled letters, wrong neighbouring key, swapped letters,
missing apostrophes, lost capitals, the odd missing space.

The whole risk of doing this is one sentence: **an edit could change what the
message means.** "hot" is one keystroke from "not". So the script carries a
frozen word list — every negation, person, tense and modality word, plus the
short signal words — and refuses to damage any of them or to produce any of them.
Longer signal words like "temperature" *can* be damaged, because no single typo
turns "temperature" into a denial, and because being able to read "temprature" is
the whole point of the exercise.

Four damaged copies were built from one clean set, identical in every other
respect — same sentence fragments, same groupings, same split into folds:

| | how much damage | notes |
|---|---|---|
| **clean** | none | the control |
| **r03** | 3% of words | |
| **r06** | 6% of words | |
| **r12** | 12% of words | about one word in eight |
| **freezeall** | 6% of words | the cautious version: never damage *any* medical word, not even long ones |

A quarter of the messages in every damaged set are left completely clean, on
purpose — real submissions run from immaculate to unreadable, and a set where
every message is equally mangled is its own kind of unrealistic.

Then thirteen combinations of "trained on X, tested on Y" were run.

---

## 3. The result

Read each row as **one model**, tested against different text.

| the model was trained on… | …and tested on clean text | …and tested on its own messy text |
|---|---|---|
| **clean text** | **93.3%** | 89.0% (r03) · 86.0% (r06) · **84.8%** (r12) |
| r03 (3% damage) | 93.5% | **93.4%** |
| r06 (6% damage) | 93.8% | **92.8%** |
| r12 (12% damage) | 94.3% | **93.3%** |

Three things fall straight out of that table.

**Typos really do cost us.** The top row is the model we have today. Show it text
damaged at 12% and it drops from 93.3% to 84.8%. That was not obvious in advance
— the plan for this work said explicitly that if the drop turned out to be small
we should stop and not build any of this. It isn't small.

**Training on typos fixes it, essentially completely.** Every model tested
against the mess it was trained on scores about 93% — the same as the clean model
on clean text. Nothing is left on the table.

**It's free.** Look down the middle column: the typo-trained models are *not*
worse on clean text. They're a whisker better, which we should read as "no
difference" rather than as a bonus.

**And you don't have to guess the right amount of damage.** This was the one
worry left over: every model above was only tested against the exact mess it was
trained on, and in real life we can't know how typo'd people's messages are. So
we took the model trained on the *lightest* damage (3%) and threw much messier
text at it:

| the 3%-trained model, reading… | it scores | a model trained on that exact mess scores |
|---|---|---|
| 6% damage (twice what it trained on) | **93.1%** | 92.8% |
| 12% damage (four times) | **92.2%** | 93.3% |

At twice the damage it's as good as the model built for it. At four times it's
1.1 points behind — a hint that the gap widens with distance, but small, and the
error bars overlap. Against the 84.8% an untrained model manages on that text,
it's recovering 87% of the loss from an inoculation four times lighter.

So the fix is to messy text in general, not to one particular level of mess.
That's what makes it usable. One practical steer falls out of it: since the small
gap appears when the *test* text is messier than the training text, err on the
side of training with **more** damage than you expect. That costs nothing — the
12% model is the best of all five on clean text.

And a fourth thing that we expected to go the other way: **more damage doesn't
start hurting.**

---

## 4. What it cost, and what the failure actually looks like

This is the part worth understanding properly, because the *shape* of the failure
matters more than its size.

When today's clean-trained model reads a typo'd message, it doesn't get the
answer wrong. **It stops answering.**

| what the message says | clean text | 12% damage |
|---|---|---|
| patient reports a fever → model finds it | 90.5% | **65.3%** |
| patient denies a fever → model reads the denial | 94.4% | **81.4%** |
| patient says nothing → model wrongly says "yes" | 2.4% | **1.1%** |

Damage pushes everything towards "the patient didn't mention it". So the model
never invents a fever out of a typo — that rate actually *improves* — it just
quietly fails to notice one. At 12% damage it's missing a third of the people who
told us they had a fever.

Of the two ways this could go wrong, that's the better one: a form that's missing
something is safer than a form that's made something up. But it is still a real
loss, and it's invisible — nothing about the output says "I couldn't read this".
A model trained on the mess gets fever detection back to 85.7% and denials to
96.5%.

**One thing to be careful about:** on the slice of the test set we normally watch
most closely (the tricky "didn't mention it" cases), the clean model appears to
get *better* under damage — 93.8% up to 96.9%. That's not real. A model that
answers "didn't mention it" more often automatically scores better on the cases
where "didn't mention it" is the right answer. That number is an artefact here
and shouldn't be quoted from these runs.

---

## 5. Was the cautious version better?

When this was designed there was one genuinely debatable decision: whether to
allow the script to damage long medical words like "temperature", or to protect
every medical word. Protecting everything is safer but means the model never
learns to read "temprature", which is the headline thing we're trying to fix. The
cautious version was built as a fifth data set so the question could be settled
by measurement instead of argument.

| | the version we shipped | the cautious version |
|---|---|---|
| how much it damages today's model | 86.0% | 86.2% — **the same** |
| how much a trained model gets back | **92.8%** | 91.7% |
| on clean text | **93.8%** | 93.0% |

The first row is the important one: the cautious version's damage is *just as
harmful*, it just lands on different words. So protecting the medical vocabulary
doesn't make the text easier — it only makes the model worse at recovering from
it.

The gap is small and the error bars overlap, so this isn't "we proved the
shipped version is better". It's "there is no reason to prefer the cautious one",
which is enough: the shipped default stays, and the decision is now measured
rather than asserted.

---

## 6. The check that could have made all this meaningless

The frozen word list protects negations and short medical words, which means
those words never get damaged. But messages whose answer is "didn't mention it"
are made of ordinary chit-chat with no protected words in them — so **they take
more damage than the other messages do.** We measured this and it's real: the
"didn't mention it" messages are the most damaged group in all 20 training files.

If the model noticed that, it could learn "lots of typos ⇒ the answer is didn't
mention it", which is a shortcut, not reading, and the whole run would have been
void rather than merely disappointing.

It didn't. Three separate checks, all agreed in advance:

* A model trained on messy text and tested on messy text doesn't *beat* the clean
  baseline — it only matches it. If it were harvesting the shortcut it would score
  higher than a model can legitimately score.
* Typo-trained models don't over-use the "didn't mention it" answer on messy text.
* And the sharpest one, which only became available with these results: a model
  that had learned "typos ⇒ didn't mention it" would go looking for typos on
  clean text, find none, and then *under*-use that answer. It doesn't. All three
  typo-trained models sit right on the correct number.

One honest correction comes out of this. The design document claimed the damage
rate would be equal across the three answers "by construction". That was too
strong, and it should be corrected: the word list guarantees the *script* can't
see the answer when it decides what to damage, but it can't make the rates equal,
because the three kinds of message are made of different words. The weaker claim
is the true one, and it's sufficient — crucially, "yes" and "no" messages show no
difference from each other, and those are the two the model has to tell apart.

---

## 7. The predictions we made before the run, scored

| what we predicted | what happened |
|---|---|
| **Typo-trained/typo-tested won't beat clean/clean** | **Held.** The four matched results span 0.6 points: 93.3, 93.4, 92.8, 93.3. |
| **Typo-trained models won't over-use "didn't mention it" on messy text** | **Held.** Within 1.6% of the correct count, and one of the three under-uses it. |
| **If the drop from typos is small, stop — there's nothing to buy** | **Did not fire.** The drop is 8.5 points. |
| **Past some damage level, training on typos stops helping** | **Did not happen** anywhere up to 12%. |
| **Open at the time: does one damage level cover another?** | **Answered, and favourably.** A 3%-trained model recovers 97% of the loss at 6% damage and 87% at 12%. |

---

## 8. What these numbers are not

* **This is one symptom.** Everything here is fever. The other six have the word
  lists built but have never been trained on damaged text.
* **These aren't real typos.** The script makes mechanical single-character
  errors. The actual box people type into is a plain text box with browser
  spellcheck on, on a phone with autocorrect on top — so most of the nonsense
  words this script produces would be fixed before they ever reached us. The
  errors that *survive* that filter are mostly real-word errors: autocorrect
  changing a word to a different real word, homophones, dropped words. Those are
  a different piece of work and, on this evidence, the more valuable one. **This
  run measures the cheap half of the problem.**
* **The 67 real-text submissions cannot be read here at all.** They look like
  they're saying something — invented-symptom rates of 24%, 11%, 25%, 14% across
  the four models — and they aren't. The variation *between the five folds of a
  single model* is bigger than any difference between models (the clean model's
  five folds run from 5 to 26 out of 49), there's no pattern, and the slice is 18
  cases with an error bar of ±23 points. Do not quote those numbers.
* **The damage rates aren't measurements.** 3%, 6% and 12% were picked to span a
  plausible range. Nobody has measured how typo'd real submissions actually are.
* **Every model here is flattered slightly** by how its confidence dial was set,
  in the same way every run in this project is. It applies equally to all thirteen
  cells, so it doesn't explain any of the gaps above.

---

## 9. What to do next

1. **Start training on damaged text, and pick a damage level at the top of what
   you think is realistic rather than the middle.** Training heavy costs nothing
   on clean text and covers more of the range, and nothing measured here argues
   for the middle.
2. **Keep the shipped setting** (damage long medical words, protect short ones).
   Section 5 settles it.
3. **Confirm it on one other symptom before rolling it out to all six.** Fever's
   two decisive libraries are the only ones in the project with no grouping
   markers at all, which makes its numbers the most flattered in the set. One
   more symptom would tell us this is about typos rather than about fever.
4. **Think seriously about the real-word error generator.** The typos this run
   handles are largely the ones spellcheck already catches. The ones that reach
   us are the ones it doesn't.
5. **Record software versions in the run artefacts.** The comparability of this
   entire sweep currently rests on somebody having written the version number in
   a commit message.

The honest summary: we asked whether the model was losing anything to messy
typing, found that it was losing a good deal, found that the fix is cheap and
costs nothing, found that the way it fails is to go quiet rather than to guess
wrong, and found that one setting of the fix covers a range of mess four times
wider than it was trained on. The remaining doubt is not about the mechanism —
it's that all of this is one symptom, and the typos we generate are largely the
ones a phone's spellcheck would have caught anyway.
