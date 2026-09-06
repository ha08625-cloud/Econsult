# Does it matter to the model whether it's your sister or your brother?

*Written in plain language on purpose. Every number here comes from
`reports/encoder_training/swapclass/` — the four `paired_flip_rate_*.json` files
and the thirteen report files beside them. **Those files are the authority** — if
this document ever disagrees with one of them, the report is right and this is
stale. The technical version is `2026-09-05-swap-class-expansion.md`, and the
bounds it is read against were written down before the run in
`2026-09-05-swap-class-preregistration.md`.*

---

## 0. The one-sentence version

We asked whether the model secretly cares about words that carry no medical
meaning — *sister*, *Tuesday*, *nurse* — and after a full night on the GPU the
honest answer is **"a little, maybe, we still can't tell"**.

That is a disappointing result and it is written up as one.

---

## 1. What the worry was

The model learns from a few hundred hand-written sentence fragments, shuffled and
recombined into thousands of training examples. The person who wrote those
fragments had habits — not just about medical words, but about everything.

Last month's run (`2026-09-04`) looked at the medical words: does the model treat
*"fever"* and *"temperature"* as if they meant different things, because the
person writing the examples happened to use one more often in a particular
context? That turned out to be a real but small effect.

This run asks the same question about words that are **completely innocent of
medical meaning**. When an example says *"my sister has a temperature"*, does the
answer change if we make it *"my brother has a temperature"*? It shouldn't. There
is no version of medicine in which the answer depends on which sibling it is. If
the model's answer moves, the model is reading noise.

That is a cleaner question than the fever one, and it is why the ticket existed:
with *fever* versus *temperature* you can at least argue the two words feel
slightly different. With *sister* versus *brother* you cannot argue anything.

---

## 2. What was built

A **swap class**: one hand-written list of words that are interchangeable, plus
one written promise about what the list guarantees. "Adult female relatives" is
one list — *mum, mother, wife, sister, aunt, auntie, girlfriend, missus*. The
software then generates every ordered pair automatically, so eight words become
56 swap rules from one list somebody wrote once.

Sixteen such lists exist, in four groups:

* **referent** — who the submission is about (relatives, in-laws, children);
* **calendar** — days of the week;
* **setting** — *doctor*, *GP*, *nurse*;
* **affect** — *worried*, *concerned*, *anxious*, *nervous*.

Together: **71 words, 320 generated swap rules, from sixteen hand-written lists.**
Last month's approach needed 36 hand-written rules to cover one symptom. These
belong to no symptom at all, so they apply everywhere.

The last group, **affect**, is deliberately treated as a different kind of thing.
Swapping *worried* for *concerned* changes the tone of a sentence in a way
swapping *sister* for *brother* does not, so it was kept in its own arm and is
never used to argue for the others.

---

## 3. What was run, and what it cost

One night. Five versions of the model:

| version | trained on |
|---|---|
| **clean** | the original data, untouched |
| **v1** | last month's fever/temperature rewrites |
| **classes** | the new referent, weekday and clinician swaps |
| **combined** | both sets at once — *this was named the deciding version, in advance* |
| **affect** | the worried/concerned swaps alone |

Thirteen training runs, 65 individual model trainings, two and a half hours. The
batch was launched as one button in the training console and every step passed.

---

## 4. The safety checks, before any result

Three checks had to pass before anything else meant anything, and all three did.

**The batch reproduced last month's run exactly.** Not approximately — the same
74 changed answers out of 3,910, the same 33 afterwards, the same accuracy to four
decimal places. A lot of machinery changed between the two runs, and it was
deliberately built so that the old measurement would come out unchanged. It did.

**The machine is deterministic.** Five of the thirteen trainings were secretly
identical (an awkwardness of the tooling — see §7). All five produced byte-for-byte
identical results, which is a stronger proof that this GPU behaves repeatably than
any single check could be.

**The rule-safety scan passed.** All 356 rules were applied to all 3,506 library
lines and no rule created a medical phrase that wasn't already there.

---

## 5. What the run found

### The deciding version passed its bar

The **combined** version was required, before the night, to disagree with itself
on no more than 1 in 100 of the sentences the swaps changed. It came in at **0.76
in 100**, and the untouched model was at 1.72. So on that measure the swaps do
what they are supposed to: the model that trained on varied vocabulary is less
disturbed when the vocabulary varies.

### But the measurement the ticket existed for came back in the middle

The real question was never "does training on swaps help?" It was: **does the
untouched model care about these words at all?**

Answer: it changes its mind on **14 out of 1,983** sentences where only a
referent, weekday or clinician word moved. That is 0.7%, and the uncertainty
around it runs from 0.2% to 1.7%.

Before the run we wrote down two conclusions and which numbers would trigger
them:

* **above ~1%** → the problem is real, extend the swap lists to the other six
  symptoms;
* **below ~0.5%, confidently** → the problem isn't real, **stop**, question
  closed.

0.7% is in the gap between them, and the uncertainty covers both. So neither
conclusion is available. **The night did not answer its own question**, and that
is the pre-registration's fault for leaving a gap, not the run's fault for landing
in it.

One thing is worth holding onto, though. Judged on **accuracy**, the swaps make
no difference whatsoever: the untouched model scores 93.29% on the original test
set and 93.36% after a fifth of it has had its relatives swapped around. A handful
of individual answers move; the model overall is no worse. Both of those are true
at the same time.

### The "worried/concerned" version proved nothing

Four changed answers out of 729 before, zero after. The report file prints a
confidence range of "0.00% to 0.00%" for the zero, and that number is a **maths
artefact, not a result** — if nothing happens, the technique used to estimate
uncertainty has nothing to work with. The honest ceiling is about 1.1%. This arm
is entirely consistent with nothing having happened.

### The thing that most changes how to read the run

Four versions were each a bit *better* than the untouched model on the original
test set — by 1.2, 0.9, 0.2 and 0.1 points. It would be easy to write that up as
"the swaps improve the model slightly."

It shouldn't be. **The version with the most rewriting in it improved the
least.** If those gains were real effects, the version containing both sets of
rules should have been the best; it was almost the worst. Effects that don't add
up and don't line up with how much was changed are what noise looks like. The
pre-registration predicted movement of *nothing* here, and it was right.

This also corrects last month's write-up, which treated its own +1.2 as possibly
meaningful. With four versions to compare instead of one, it clearly isn't.

### Real patient writing: still can't tell us anything

All five versions were scored against the 67 real submissions. The scores range
from 69.9% to 81.2% — but the margin of error on that set is ±12 points, and a
*single* version swings by 30 points depending on which fold of the data it
trained on. The set exists to catch a version that has fallen over completely.
None had. That is all it can say, and it was written down in advance that it would
be all it can say.

---

## 6. So what happens next?

**The rollout was declined**, even though the deciding version passed its bar.

That deserves an explanation, because it is the opposite of what the pass rule
said to do. Three reasons:

1. The version that passed contains **both** sets of rules, and last month's
   fever rules did about 80% of the rewriting in it. Nothing in this run
   separates what the new swaps contributed from what the old rules did.
2. The measurement that would justify extending the swap lists to six more
   symptoms is the indeterminate one.
3. The only sign of benefit is the one §5 explains away.

Extending the lists to six more symptoms is many hours of careful hand-authoring,
and there is no evidence yet that it would buy anything.

**What is proposed instead** is a cheap follow-up that closes the question rather
than re-asking it. The problem is that only 1,983 sentences changed, so the
measurement is made of 14 events. Turning the rewriting rate up roughly doubles
the sentences it touches, using the same lists and the same night, and the
untouched model doesn't need retraining to be measured again. If the number is
still around 0.7% with a tighter range, the question closes as "no" and the swap
lists stay where they are.

Nothing built in this ticket is wasted or needs rebuilding — sixteen lists, the
loader, the safety checks and the tests are all committed and working. The only
open decision is whether to write more of them.

---

## 7. Honest limitations

* **Everything rests on 14 changed answers** in the main measurement, and four in
  the affect one. That is a small number to hang a decision on, which is precisely
  why the decision being made is "measure it better", not "adopt" or "abandon".
* **Sixteen written promises are the safety net.** Each list carries a
  hand-written promise that swapping within it changes nothing medically. No
  automatic test reads one. If a promise is wrong it is wrong dozens of times
  over. Two mechanical checks used to sit behind these promises; a change in this
  ticket removed one of them for these lists deliberately, so what stands behind
  them now is a person having read them, plus a scan that checks no rule
  *manufactures* medical language.
* **A quirk of the tooling wasted about 50 minutes.** Scoring one model against
  five different test sets requires five separate training runs, so the untouched
  model was trained five identical times. It bought the determinism check in §4,
  which is some consolation.
* **The versions each chose their own confidence threshold**, and they chose very
  different ones. Some of the difference between versions in this report is that
  choice rather than anything the model learned. Nobody had noticed this before;
  it needs fixing before the next comparison.
* **Nothing here is evidence about real patients.** 67 hand-written submissions
  by one person, with a ±12 point margin, cannot rank five models and were not
  used to.
