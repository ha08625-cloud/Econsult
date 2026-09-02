# Did the generated sentences help? No — they made the main problem worse

*Written in plain language on purpose. Every number here comes from the six
report files under `reports/encoder_training/decl/comparison/`. **Those files are
the authority** — if this document ever disagrees with one of them, the report is
right and this is stale. Read this to understand what happened; quote figures
from the reports. The technical version is `2026-09-02-declarative.md`.*

---

## 0. The one-sentence version

We generated a thousand extra training sentences by machine, mixed them in at
30%, and the model got **worse** at the one thing we most need it to stop doing —
claiming a patient mentioned a symptom when they never did. Worse on all six
symptoms, both times we checked. Along the way the run turned up something more
important that nobody was looking for: on the hard cases, a 110-million-parameter
model is no better than a piece of maths from the 1970s.

---

## 1. What the problem is, in one paragraph

The model reads a patient's free-text message and answers, for each symptom,
"yes", "no", or "not mentioned". The failure that matters most is the third one
going wrong in the confident direction: the patient wrote nothing about a fever,
and the model fills in "yes, fever". That puts a symptom into a clinical record
that the patient never reported. We call it the invented-symptom rate, and it is
the number every one of these experiments is really about.

## 2. What was tried

The training data is built by recombining a few hundred hand-written sentence
fragments. Somebody has to write each one, so the library grows slowly.

The idea being tested: write down a list of symptom *phrases* and a list of
sentence *frames*, and let a script combine them into a thousand new sentences
automatically — "I've had burning when I wee and a temperature since Tuesday".
Cheap, and each one mentions several symptoms at once, which the hand-written
fragments mostly don't.

A dial called `--declarative-share` controls how much of the training data comes
from those generated sentences. This run tested it at 0% and 30%.

## 3. What was measured, and why it took four cells

There was already a working fix for the invented-symptom problem, from an earlier
run: **companions** — putting other symptoms' language into examples where the
answer is "not mentioned". So the honest question isn't "do the generated
sentences help?" but "do they help *on top of the fix we already have*?"

Hence four training runs per symptom:

| | no companions | with companions |
|---|---|---|
| **no generated sentences** | **A** — the control | **C** — what we ship today |
| **30% generated sentences** | **B** | **D** — the one that decides it |

Six symptoms, four cells, five repeats each: 120 models, four hours on one GPU.
The whole thing ran cleanly in one go.

## 4. The result

Here is the invented-symptom rate — the share of messages where the model claimed
a symptom the patient never raised. **Lower is better.**

| symptom | A | B | C | **D** |
|---|---|---|---|---|
| pain passing urine | 52.7% | 54.5% | 3.6% | **12.7%** |
| fever | 23.7% | 45.7% | 0.0% | **0.4%** |
| flank pain | 45.7% | 70.9% | 9.1% | **29.8%** |
| blood in urine | 29.3% | 63.2% | 9.3% | **13.2%** |
| night-time weeing | 0.7% | 14.1% | 0.3% | **0.3%** |
| weeing often | 5.9% | 23.4% | 4.4% | **5.9%** |

Read it left to right in pairs. **A to B** (no companions, add generated
sentences): worse on all six. **C to D** (with companions, add generated
sentences): worse on five, unchanged on one.

Flank pain is the clearest: the fix takes it from 45.7% down to 9.1%, and the
generated sentences push it back up to 29.8% — undoing more than half the gain.

We had written down in advance what we expected: the rate would *improve*, and
would move *least* for flank pain, because flank pain has the fewest phrases in
the new inventory. It moved the most, in the wrong direction. That is a
prediction failing about as cleanly as a prediction can.

## 5. "But D scores better than C on a lot of other things"

It does, and this is the part most likely to be misread, so it's worth being
careful.

On the messages where the patient *did* say something, D is much more accurate
than C — for fever, 90% against 49%. That looks like a big win.

The catch is what C is doing. **C has mostly stopped answering.** For fever,
flank pain and blood in urine, C says "not mentioned" almost every time. That
scores brilliantly on the two-thirds of cases where "not mentioned" is right, and
terribly on the third where the patient actually said something.

D answers more often. So it gets more of the real answers right, *and* it invents
more symptoms. Those are the same behaviour seen from two sides — a model turning
a dial towards "speak up", not a model that reads better. Adding up all 67
messages, D beats C on four symptoms, ties on one, and loses on flank pain.

That's not nothing. But it isn't evidence that the generated sentences taught the
model anything, and it isn't what the ticket set out to buy.

## 6. Two ways the numbers flatter the new sentences

**The new sentences mark their own homework.** When you add generated sentences
to the training data, they also land in the *test* data. And the model gets them
**100% right — every single one, in every cell.** They are, by design, simple
unambiguous statements: "I have a fever and burning when I wee." No hedging, no
metaphor, nobody quoting their daughter. So a chunk of the apparent accuracy
improvement is just easy questions being added to the exam.

Take those questions back out and D's advantage over C shrinks from about 1½–4
points to under 3, and for one symptom it disappears entirely.

**The "not mentioned" test doesn't contain the problem.** On our machine-built
test set, the invented-symptom rate is 1–4% everywhere and D looks slightly
*better* than C. On the 67 real messages it is 0.3–30% and D is clearly worse.
The two disagree about which direction things moved. This is the third time on
record that the real messages have shown something the generated data cannot —
worth remembering next time a result looks good on the synthetic set alone.

## 7. The thing nobody was looking for

Every model in this project gets compared against some deliberately dumb
baselines, to check it's earning its keep. One of them is TF-IDF — essentially
"count which words appear, fit a straight line". No understanding of grammar, no
sense of who a sentence is about, and it dates from the 1970s.

On the *hard* cases — where the patient hedges ("might be a bit warm"), or uses a
metaphor, or is talking about somebody else, or about last year — here is how our
110-million-parameter fine-tuned transformer compares against it:

| symptom | word-counting | our model |
|---|---|---|
| pain passing urine | 94.1% | 94.0% |
| fever | 93.0% | 93.8% |
| flank pain | 91.7% | 93.7% |
| blood in urine | 93.9% | 91.9% |
| night-time weeing | 90.2% | 89.6% |
| weeing often | 92.8% | 95.0% |

They are the same. Three of the six differences are statistically
indistinguishable; of the three that do separate, word-counting wins one.

This is the question the whole encoder project was set up to answer — **is the
thing holding us back the model, or the data?** — and the reports have a written
rule for reading it. By that rule, this is the *data* answer. If a big model
can't beat word-counting on the only cases that need a big model, the limit isn't
the model. It's that there aren't enough genuinely different hard examples for it
to learn from — and the reports even name which fragments the errors pile up on.

One honest caveat: this run skipped one of the comparison arms to save time, so
the rule's exact left-hand side is missing. It should be re-run before anyone
acts on this. But it is much the most interesting thing in the run, and it has
nothing to do with the flag being tested.

## 8. A wrinkle worth knowing about: the confidence dial

Every trained model has a threshold — how confident it must be before it will
answer "yes" instead of "not mentioned". It's picked automatically, once per
repeat, and it is *directly* the dial that controls the invented-symptom rate.

Across the 24 combinations in this run, that threshold jumps around wildly: five
repeats of the *same* setup can pick 0.0, 0.0, 0.75, 0.55 and 0.65. It varies
more between repeats of one cell than the cells vary from each other.

Which means a real share of the difference we're attributing to "generated
sentences" is really "the threshold picker landed somewhere else this time". This
isn't specific to this experiment — it affects every comparison the pipeline
makes, including ones already written up. It was flagged as a worry back in
August; this run is the evidence that it now matters more than the things we're
trying to measure.

## 9. Two other things found

**A reporting bug.** The section comparing pairs of models had a sentence that
said which one came out ahead — and it was computing the winner backwards
whenever the second model was the worse one. All six of the important comparisons
in this run were affected, and each read as an endorsement of the arm that had
actually got worse. Fixed, with a test covering both directions, and the six
reports regenerated from their own stored data (no retraining needed). The older
August reports have the same wording but were never wrong, because in those the
result genuinely went the other way.

**A comparison that was never going to work.** The run sheet expected cell C to
reproduce the numbers from the August companion run, as a free sanity check. It
doesn't — every number is far lower. That's not a problem with either run: the
August models were *one model handling all six symptoms*, and these are *six
separate models, one per symptom*. We already know from an earlier experiment
that the combined model is much worse at exactly this. So the check compared two
different things and its result should not be reported as a finding in either
direction.

## 10. What we think should happen next

1. **Don't turn the generated-sentence dial on.** It made the main number worse,
   everywhere.
2. **Fix the confidence-threshold picker first.** Right now it adds more noise
   than most of the effects we're trying to measure, which makes every comparison
   less trustworthy than it looks.
3. ~~Run the 60% version anyway.~~ **Done, and it was worse** — see section 11.
4. **Follow up the word-counting result properly.** If it holds with the missing
   arm included, the next month of work is writing better hard examples by hand,
   not tuning models.
5. **Save the data-generation step too**, not just the training step. Two of the
   six predictions couldn't be scored at all, because the files needed to check
   them were never kept.

None of this makes the generated-sentence machinery wasted work — it's built,
it's tested, it's off by default, and the ability to generate multi-symptom
sentences is on the path for later tickets. It just doesn't buy what this ticket
hoped it would buy, and the honest thing is to say so.


---

## 11. The 60% version, and the surprise in it

We ran it. At 60% generated sentences the model invents symptoms *more* than at
30% on four of the six symptoms, holds level on one, and improves slightly on
one. So the prediction we wrote down in advance was right in direction.

But the interesting part is *how much* worse, because it is much less than you'd
expect. Going from 0% to 30% made things worse by about 36 points added up
across the six symptoms. Going from 30% to 60% — the same size step again —
cost only another 6½. Roughly **85% of the damage arrives with the first spoonful**,
and adding more barely changes anything.

That matters, because it tells us *why* this is happening, which the earlier run
couldn't.

The explanation we'd written down was about **register**: the worry that a
machine-made sentence sounds different from a patient, and that if enough of the
training data sounds that way the model stops recognising real patients. If that
were the cause, 60% should be much worse than 30% — that's the point where the
machine-made voice takes over. It isn't.

The other explanation fits better. The generated sentences each mention several
symptoms at once, and they're used in examples labelled "yes". So the model
quietly learns a shortcut: *lots of symptom words in the message → answer yes*.
Real patients' messages are full of symptom words. Once the model has picked that
habit up, it has picked it up — pouring in more examples of it doesn't make the
habit much stronger. A habit that saturates looks exactly like this curve.

We're not certain. It's six symptoms and one run, and one symptom moved the wrong
way for both explanations. But it's the better-supported of the two, and it's a
different problem from the one we thought we had.

**One more thing worth seeing.** At 60%, a third of the test questions are the
machine-generated sentences themselves — and the model gets **100% of them
right**, as it does in every version. So the scores on our own test set reach the
highest numbers this project has ever recorded, on exactly the models that behave
worst on real patient messages. If you looked only at the headline table, you
would pick the worst model in the run as the best one. That is worth remembering
every time a synthetic score looks good.

And the word-counting comparison from section 7 got *stronger*, not weaker: with
the better training data in place, plain word-counting now beats our
110-million-parameter model on three of the six symptoms and ties the rest. The
model doesn't win a single one.
