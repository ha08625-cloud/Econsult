# One encoder, six symptoms: what the 2026-08-17 comparison found

*Written in plain language on purpose. Every number here comes from the six
`<signal>.joint_comparison.json` files in this folder. **Those files are the
authority** — if this document ever disagrees with one of them, the JSON is right
and this is stale. Read this to understand what happened; quote figures from the
JSON.*

*Reads on from `2026-08-16-plain-english.md`, which trained six separate models,
one per symptom. Sections 0 and 1 of that document — what the three answers mean,
where the training sentences come from — apply here unchanged and are not
repeated.*

---

## 0. The one-sentence version

Training one model to answer all six questions at once made it **better on our
made-up test messages and much worse on real ones** — so much worse that on real
patient text it now scores below a model that answers "the patient didn't say" to
everything. The good number and the bad number have the same cause, and we know
what it is.

---

## 1. What was actually tested

Until now we had six separate models, one per symptom, each having read only its
own symptom's training messages. The obvious next question is whether they would
be *better* if one model read all six symptoms' messages at once — not to deploy
it that way, but because "whose symptom is this", "when did it happen" and "is
this literal" are not symptom-specific skills, and a model that practised them
six times over might get better at all of them.

Three versions of each symptom's model were trained, so that a difference could
be attributed to something:

| | what it read during training | messages per pass | **labelled examples for this symptom** |
|---|---|---|---|
| **A1** | only this symptom's messages | 10,000 | 10,000 |
| **A2** | only this symptom's messages, shuffled together 4.5× more ways | 44,680 | 44,680 |
| **A3** | **all six symptoms' messages** | 44,680 | 10,000 |

The last column is the important one. **A3 gets no extra teaching about fever.**
A dysuria message carries a dysuria answer and no fever answer at all, and the
software treats a missing answer as "don't grade this one" rather than as "the
answer is `null`". So the fever part of A3 saw exactly the same 10,000 graded
fever examples that A1 saw. The only thing that changed is that the shared reading
machinery underneath it was also being pulled around by five other symptoms.

A2 exists to catch the boring explanation. A3 does 4.5× as much work per pass as
A1 simply because there are more messages, and more work can improve a model all
by itself. A2 does the same extra work on one symptom only, so if A3 improves and
A2 improves just as much, the improvement was never about the other five symptoms.

**A1 against A3 is the comparison**, and it is measured message by message on
exactly the same test messages. A2 is measured separately and cannot be compared
message-by-message to anything, because its test messages are different messages.

---

## 2. On our made-up test messages, one model for six symptoms wins

Accuracy on the *decisive* messages — the ones that actually contain a sentence
about the symptom. Higher is better.

| symptom | A1 (six separate models) | A2 (more of the same) | **A3 (one model, six symptoms)** | A1 → A3 |
|---|---|---|---|---|
| nocturia | 83.0% | 88.0% | **92.3%** | **+9.3** |
| haematuria | 91.5% | 92.8% | **94.9%** | +3.4 |
| dysuria | 94.9% | 95.3% | **98.1%** | +3.2 |
| flank pain | 96.0% | 95.5% | **97.8%** | +1.8 |
| urinary frequency | 85.3% | 84.5% | **86.2%** | +0.9 |
| fever | 92.9% | 93.8% | 93.5% | +0.6 |

Four of the six improved by an amount that is not luck. Compared message by
message, A3 gets 900 messages right that A1 gets wrong on nocturia against 269 the
other way; 363 against 129 on haematuria; 313 against 115 on dysuria. Fever is a
dead heat — 245 each way, which is about as null a result as a comparison can
produce.

**A2 shows most of this is genuinely about the other symptoms.** On five of six
signals, doing 4.5× more work on one symptom alone bought between −0.8 and +1.3
points — nothing. Nocturia is the exception: A2 got +5.0 there, so about half of
nocturia's +9.3 is just "more training", and only the other half is the other
symptoms. Everywhere else, the gain is not explained by extra work.

If this were the whole story it would be a clean win, and the next line of this
document would recommend training this way from now on.

---

## 3. On real patient text, the same model falls apart

We hold 67 hand-written realistic submissions permanently aside. They select
nothing, they are scored once per candidate model, and the number is recorded
whether it is good or bad. This is the only measurement in the project that speaks
to text a patient might actually write.

Two numbers per symptom. **"Reads it right"** is accuracy on the submissions where
the patient did say something about that symptom. **"Invents it"** is how often the
model answered `true` when the patient never mentioned the symptom at all — the
cell that would put a symptom into a patient's form that they never reported.

| symptom | reads it right: A1 → A3 | **invents it: A1 → A3** |
|---|---|---|
| fever | 61% → **89%** | 17% → **82%** (40 of 49 submissions) |
| flank pain | 84% → **93%** | 53% → **89%** (47 of 53) |
| haematuria | 75% → **100%** | 22% → **79%** (44 of 56) |
| nocturia | 40% → **76%** | 2% → **58%** (33 of 58) |
| urinary frequency | 47% → **79%** | 5% → **47%** (19 of 41) |
| dysuria | 79% → **84%** | 45% → 67% (7 of 11) |

Joint training made every symptom better at reading what the patient *did* say —
several of them dramatically better — and made every symptom worse, mostly far
worse, at recognising that a symptom was never mentioned.

Put the two together across all 402 answers it was asked for:

> **A3 gets 39.1% of real answers right. A model that replied "the patient didn't
> say" to every single question would get 66.7%.**

On real submissions, the six-symptom model is substantially worse than doing
nothing at all. The separate models are not good either — A1 manages 74.6% on
fever's 67 answers against 73.1% for saying nothing — but they are not below the
floor.

**None of this is visible in our made-up test set.** There, A3's invented-symptom
rate is 0.58%–2.53%, and *better* than A1's on four of the six symptoms. The same
model, the same measurement, on real text: 47%–89%. This is precisely the failure
the held-out set exists to catch, and nothing else in the project can see it.

---

## 4. Why both results are true at once

There is one mechanism behind both halves, and it was written down as a prediction
before the run.

Every made-up `null` message for a symptom pairs *the absence of that symptom's
language* with **bland, non-clinical filler** — chat about the weather, the school
run, work. The model has therefore never once seen a message that is dense with
clinical language about some *other* symptom and whose correct answer is still
`null`. In the merged training data a dysuria message is invisible to the fever
part of the model, so it never gets told "this is full of symptom talk and the
fever answer is still `null`".

Meanwhile the shared reading machinery is being trained by six symptoms at once to
make symptom language as prominent as possible.

The result is a **symptom-language detector with six read-out dials**. When a
patient does describe a symptom, it is excellent — hence the whole of the "reads it
right" column. When a patient describes *other* symptoms and is silent about this
one, it fires anyway. Real submissions are dense with other symptoms: dysuria is
present in 56 of the 67.

The individual sentences show it plainly. These got worse going from A1 to A3, and
the count is how many times each was answered wrongly:

> *"I always get warm and flushed the week before my period, it's like clockwork"*
> — correct answer `null`. Wrong **0 → 19** times.

> *"My flushes are worst in the evening, it's the change, my mum was exactly the
> same at my age"* — correct answer `null`. Wrong **0 → 17** times.

> *"Going for a wee about as often as I ever do."* — correct answer `false`. Wrong
> **8 → 121** times.

The first two are the `attribution` family — the patient explaining the symptom
away as something else. Fever's score on that family fell from 96.3% to 80.5%, and
it is the entire reason fever's hardest slice got worse while its headline stayed
flat. The third is a plain statement of "no", which the six-symptom model now reads
as a "yes" fifteen times more often than the single-symptom model did.

**Joint training does not cause this problem; it amplifies one that was already
there.** The fix is not to abandon joint training. It is to build training
messages that mix symptoms together and label all six, so that "this text is full
of clinical language and the answer is still `null`" becomes something the model
is actually taught. That work is already specified — multi-symptom recombinations,
`arch_training.md` 12.5 — and this run is the evidence that it is not optional.

---

## 5. The nocturia / urinary frequency pair

The two weakest symptoms are "I'm weeing more often" and "I'm getting up in the
night to wee". They are close to synonyms, they are the two the older word-counting
baseline is worst on, and joint training is the first thing that forces one model
to hold them apart. We predicted a large effect here in either direction.

We got both directions at once. **Nocturia gained the most of any symptom (+9.3),
and urinary frequency gained almost nothing (+0.9)** — and urinary frequency's
`adjacent` family, the sentences written specifically to describe a *nearby but
different* urinary symptom, fell from 94.7% to 81.8%. Nocturia's hardest family
went the other way, 80.9% → 95.6%.

So the model did learn to separate them, and it appears to have resolved the
ambiguity in nocturia's favour at urinary frequency's expense. Counting sentences
rather than percentages: nocturia has 66 sentences that improved against 30 that
got worse; urinary frequency is 41 against 38, a wash.

---

## 6. The predictions we made before the run, scored

Recorded in the report headers before any of this was trained, per the house rule
that a ceiling asserted after a disappointing number is an excuse.

| what we predicted | what happened |
|---|---|
| **A1 → A2 will be worth little or nothing** | **Held on five of six** (−0.8 to +1.3). Failed on nocturia, where it was worth +5.0. |
| **A1 → A3 on fever: within 2–3 points, probably undetectable** | **Held on the headline** — +0.6, and a dead-even 245/245 message-by-message. But it missed a real *regression* on fever's hardest slice, which we did not anticipate. |
| **Nocturia and urinary frequency: a large effect is plausible either way** | **Held for nocturia** (+9.3, the largest movement in the sweep). **Did not hold for urinary frequency** (+0.9). |
| **The real-text score will drop a lot, and joint training won't fix it** | **Held, and understated it.** Not only did joint training fail to fix it, it made it several times worse. |

Three of four held. The one that missed — fever being undetectable — missed by
looking at the wrong number: the headline was exactly as predicted and the damage
was one slice down.

---

## 7. What we checked, and one check we skipped

**The sabotage tests were run for the word-counting comparisons and scored at the
floor**, as they must. **They were not re-run for the six-symptom models in this
sweep** — it would have doubled a thirteen-model run, and the same check passed on
the same datasets on 2026-08-16. The reports say so in their headers. It is a
legitimate saving and it is worth knowing it was made.

**The made-up test messages are still cleanly separated from the training ones.**
Every hand-written sentence is used for training or for testing and never both,
and where we wrote two versions of one idea both go to the same side. The loader
checks this on every run and refuses to proceed otherwise.

**The joint model was compared against the separate models on identical test
messages**, matched one to one — not two scores side by side. A2 could not be
compared that way and the reports record it as untestable rather than leaving a
blank a reader might mistake for "no difference".

---

## 8. What these numbers are not

* **67 submissions is a small sample.** The real-text figures carry roughly ±12
  points overall and ±23 or worse per symptom. That is wide enough that the small
  differences should be ignored — and far too narrow to explain a gap between 39%
  and 67%.
* **The realistic submissions were written by us and labelled by us.** The labeller
  and the model share an architecture and could share a blind spot, which would
  flatter the score in a way no amount of statistics would reveal.
* **Three symptoms have no "patient explicitly denies it" example anywhere in the
  67.** A model that never answers `false` is not penalised on them.
* **The made-up test set's error bars are set by how many *ideas* we wrote, not how
  many messages we generated.** Roughly 200–420 independent ideas per symptom.
  Generating more messages does not narrow them.
* **Four of the six symptoms' sentence libraries are not yet grouped into "these
  two lines are the same idea"**, so their error bars are narrower than the truth
  and cross-symptom rankings should be read loosely.
* **Nothing here is connected to anything.** No model in this sweep is wired into
  the live system, and a six-symptom model could not be even if we wanted it: the
  form declares seven symptoms and `recent_uti_present` has no training sentences
  and therefore no answer.

---

## 9. What to do next

1. **Do not treat the six-symptom model as the better model.** Its win on our own
   made-up data is real and it is not the number that decides anything.
2. **Build the multi-symptom training messages** (`arch_training.md` 12.5 / ticket
   6). This run turned "we think there may be a shortcut where clinical-sounding
   text implies not-`null`" into a measurement, and the shortcut is enormous. This
   is now the critical path, and every future comparison is hard to interpret
   until it exists.
3. **Re-think the safety rule on top of the model.** Each model carries a rule
   whose job is to hold down the invented-symptom rate, and its setting is chosen
   on made-up validation data where that failure barely occurs. On real text the
   setting matters enormously — nocturia's folds where the rule was set loosely
   invented the symptom 44–51 times out of 58, and the two folds where it was set
   tightly, 13–15 times. We are tuning the safety dial against a measurement that
   cannot see the danger.
4. **Write more realistic submissions, especially explicit denials.** Already the
   standing next ticket; this run raises its priority.

The honest summary: joint training works, on the thing we can measure, and the
thing we can measure is not the thing that matters. The 67 real submissions cost a
few days to write and have now twice told us something no amount of generated data
could. That is the argument for writing more of them.
