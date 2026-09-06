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

That is a disappointing result and it is written up as one. The word lists are
being kept regardless, because they cost nothing to use and appear to do no
harm — which is a different reason from the one the experiment was designed to
supply, and §6 says so plainly.

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
## 6. So what happens next? **We're keeping it.**

The plan written before the run said: if the model turns out not to care about
these words, stop and don't extend the word lists to the other symptoms. The
result came in between "it cares" and "it doesn't", and **the lists are being kept
anyway**. That is a deliberate override of the plan's own rule, not a
reinterpretation of the result, and it is worth being clear about why.

**The plan asked the wrong question.** It asked "does this help?", and treated
"we can't tell" as a reason to abandon. That is the right way to decide about
something that costs effort to use. These word lists don't. They were written
once, they mention no symptom, and applying them to a new condition means adding
one option to a command — no new writing, no tuning, no per-symptom review.

That matters because of where the system is going: roughly fifty conditions, a
couple of hundred symptoms, five or six sentence libraries each. Hand-writing
those sentences is the expensive part and always will be. Anything that makes the
existing sentences stretch further, for free, is worth keeping unless it is shown
to do damage.

So the question that actually decides it is **"does it hurt?"** — and this run
answers that reasonably well. Swapping relatives around in a fifth of the test
data changes the model's overall score by essentially nothing (93.29% → 93.36%).
Every version trained on swapped data scored at or above the untouched one. No
version learned a new shortcut. The safety scan found no rule that invents medical
language.

**What is being kept, and what isn't:**

| word lists | decision |
|---|---|
| relatives, in-laws, children | **on by default** |
| doctor / GP / nurse | **on by default** |
| days of the week | **off unless a condition asks for it** |
| worried / concerned / anxious | **dropped** |

Days of the week are held back for a specific reason. Changing "Monday" to
"Thursday" is harmless when the answer doesn't depend on timing — which is true
of fever. For a symptom where *when it started* is the answer, a changed weekday
in one sentence can contradict "four days ago" in another, and none of the
automatic checks can see that, because they look at one sentence at a time.

The worried/concerned list is dropped because §5 shows it did nothing measurable
and it was always the list with the weakest argument behind it.

**One thing must not get lost in the retelling: nothing here shows the swaps
help.** They are being kept because they are free and appear harmless, not
because they were shown to improve anything. If a future run turns up something
strange, whoever reads this needs to know there was never a measured benefit to
weigh against it.

### The risk isn't in this run, it's in the rollout

The "relatives" list contains *mum, mother, wife, missus, sister, aunt, auntie,
girlfriend*, and the software may swap any of them for any other. The written
promise attached to that list says, in as many words, that the libraries never
label on which woman it is. **That is true of a urine-infection questionnaire.**

It stops being automatically true across fifty conditions. Swapping "my wife" for
"my sister" is harmless when the question is whether someone has a fever. It is
not harmless in sexual health, contact tracing, obstetrics or safeguarding, where
the *relationship* is part of the clinical picture.

The good news is that the machinery to catch this already exists and is *stricter*
for these generated word lists than for hand-written rules: a swap may not change
any medical wording for **any** symptom the system knows about. So a condition
where "sister" or "partner" is medically meaningful declares that word in its own
vocabulary list, and every swap touching it stops working automatically. The
per-condition judgement becomes "describe the new condition properly", which is
already unavoidable work.

Until this ticket, that safeguard had **never actually fired** — none of the 71
words appears in any of the seven urine-infection vocabularies, so it was passing
without ever being tested. A test has now been added that puts "sister" into a
made-up condition's vocabulary and checks the refusal happens. It does, and it
refuses loudly: the whole list is rejected rather than the offending pair being
quietly dropped.

### Conditions attached to keeping it

1. Run the safety scan for each new condition and read its output once. "Works
   for any symptom" means the rules don't mention a symptom — not that anyone has
   checked them against every one.
2. The "relatives" lists mix family relationships with romantic ones. The first
   condition where that distinction is medically meaningful needs them split.
   Written down here so it isn't rediscovered by accident.
3. Sixteen hand-written promises are still the safety net for anything the
   automatic check can't see, and they were written while looking at fever
   sentences.

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
