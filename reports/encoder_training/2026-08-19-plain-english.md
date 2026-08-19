# Teaching the model to say "they didn't mention it": what the 2026-08-19 run found

*Written in plain language on purpose. Every number here comes from the six
`<signal>.companion_comparison.json` files in this folder. **Those files are the
authority** — if this document ever disagrees with one of them, the JSON is right
and this is stale. Read this to understand what happened; quote figures from the
JSON. The technical version is `2026-08-19.md`.*

*Reads on from `2026-08-17-plain-english.md`, which found the problem this run
was built to fix. Its sections 0 and 1 — what the three answers mean, where the
training sentences come from — apply unchanged and are not repeated.*

---

## 0. The one-sentence version

The fix worked, and by more than we expected: the model now invents symptoms
**35 times instead of 191** across the same 402 real-text answers, and it is the
first model in this project to do better on real messages than a model that
answers "the patient didn't say" to everything. It paid for this with a small
amount of detection almost everywhere — and with **a lot** on one symptom,
"going more often", which it now misses more than half the time.

---

## 1. What the problem was, in one paragraph

Every training message where the answer was "the patient didn't mention it" was
padded with **bland chit-chat** — the weather, the school run, work. So the model
had never seen a message full of medical language whose correct answer was still
"didn't mention it". On real submissions, where people describe two or three
symptoms at once, it read the medical language and answered "yes" to symptoms
nobody had raised. On 2026-08-17 it did this on 47%–89% of the questions where
the patient had said nothing, and scored 39.1% overall against 66.7% for a model
that said nothing at all.

---

## 2. What was changed

One thing. Training messages can now borrow sentences from *other* symptoms'
libraries instead of chit-chat — so a fever question can arrive attached to a
message full of urinary symptoms, with the fever answer still "didn't mention
it".

Two versions of the training data were built, identical in every respect except
this:

| | padding in each message | messages per fold |
|---|---|---|
| **Arm 0** (the control) | chit-chat only, exactly as before | 44,680 |
| **Arm P** | half the padding slots drawn from other symptoms | 54,410 |

A third version, **Arm C**, is free: it is Arm 0's trained model with only its
*confidence dial* re-adjusted, using Arm P's data to set it. No retraining. It
exists to answer "could we have got this by turning a knob instead of rebuilding
the data?"

**The success criteria were written down before any of this was trained**, so
they could be scored rather than argued about afterwards.

---

## 3. The result

**"Invents it"** — how often the model answered "yes" about a symptom the
submission never mentioned. Lower is better. The right-hand column is what the
percentages are actually made of, because some of these slices are small.

| symptom | Arm 0 | **Arm P** | improvement | actual messages |
|---|---|---|---|---|
| fever | 84% | **4%** | −80 points | ~41 → ~2 of 49 |
| flank pain | 88% | **18%** | −70 | ~46 → ~9 of 53 |
| blood in urine | 80% | **13%** | −68 | ~45 → ~7 of 56 |
| getting up at night | 69% | **20%** | −49 | ~40 → ~11 of 58 |
| pain passing urine | 73% | **24%** | −49 | ~8 → ~3 of 11 |
| going more often | 25% | **7%** | −19 | ~10 → ~3 of 41 |
| **all six** | | | | **~191 → ~35 of 268** |

Five of the six improved by more than the 20 points we said in advance would
count as success; we needed four. Compared message by message, **Arm 0 is the
better model on none of the thirty fold-by-fold comparisons.**

And the headline number:

> **Arm P gets 81.0% of real answers right. Arm 0 gets 36.5%. A model that
> replied "the patient didn't say" to everything would get 66.7%.**

No model in this project has been above that floor before. We explicitly did not
expect this one to be either — clearing it was written down as a bonus, not as
the target.

---

## 4. What it cost

The worry with a fix like this is obvious: a model can stop inventing symptoms by
simply going quiet, and a model that answers "didn't mention it" to everything
would score 66.7% and look like a triumph on the table above.

**That is not what happened.** On the messages where the patient *did* describe a
symptom, Arm P is still answering, and answering about as well as before:

| symptom | reads it right: Arm 0 → **Arm P** | how many messages that is |
|---|---|---|
| fever | 84% → **83%** | 18 |
| pain passing urine | 83% → **81%** | 56 |
| flank pain | 90% → **81%** | 14 |
| blood in urine | 100% → **82%** | 11 |
| getting up at night | 87% → **76%** | 9 |
| **going more often** | **71% → 41%** | **26** |

Read the right-hand column before the middle one. Blood in urine "falling 18
points" is **two messages out of eleven** — being at 11 out of 11 was never a
number that was going to stay put. Flank pain and getting up at night are about
one message each. Fever is a fifth of a message: noise.

**Going more often is the real one.** Eight of the 26 people who reported it are
now missed. That is not a rounding artefact and it is not something the success
criteria could see.

Put the whole thing together across all 402 answers: Arm P gets **192 more
"didn't mention it" answers right** and **13 fewer "yes/no" answers right**, and
8 of those 13 losses are that one symptom.

---

## 5. Could we have got this for free?

Partly. Arm C — the same old model with only its confidence dial re-adjusted —
captured **16%** of the improvement, and scored 37.5% overall against Arm 0's
36.5%.

So: rebuilding the training data is what did the work, and the cheap fix was not
a substitute. But 16% for free is not nothing, and there is no good reason for
any future model to have its dial set on data where this failure cannot occur.
That is a small change to the standard recipe and it should just be made.

One curiosity: the two symptoms where the dial helped most (getting up at night,
going more often) are the two where the data change helped least. Where the
retraining moved the model a long way, there was nothing left for the dial to do.

---

## 6. The check that could have made all this meaningless

If the borrowed sentences had turned up more often in messages whose answer was
"yes" than in messages whose answer was "didn't mention it", the model could have
learned "lots of borrowed medical text ⇒ the answer is yes" — the same shortcut
in a different hat — and the entire run would have been void rather than merely
disappointing.

It didn't. Across all 35 training files, the number of borrowed sentences per
message differs between the three answer types by at most **0.024**, against an
average of 0.75 borrowed sentences per message. This was checked before anything
was trained and again before any score was read.

**And on our own made-up test messages, almost nothing changed** — the invented-
symptom rate moved by at most 0.6 points on any symptom. That is the result we
wanted. Our made-up test set cannot contain this problem, so a big improvement
*there* would have meant we had introduced some new shortcut, not fixed the old
one. It stayed flat. This is now the second time the 67 hand-written submissions
have shown us something no amount of generated data could.

---

## 7. The predictions we made before the run, scored

| what we predicted | what happened |
|---|---|
| **20+ points better at not inventing symptoms, on 4 of 6** | **Held.** 5 of 6. |
| **Overall accuracy on real text won't get worse** | **Held**, by 44.5 points. |
| **Our made-up test set will barely move** | **Held.** At most 0.6 points. |
| **The confidence dial alone captures a meaningful share** | **16%** — meaningful, and small. The data change is what mattered. |
| **"Going more often" and "getting up at night" will resist** | **Half held.** Getting up at night didn't resist at all (−49 points). Going more often resisted on both counts — the only symptom to miss the bar, and the only one to lose real detection. |

Four of five held outright. The fifth held for exactly one of its two symptoms,
and the symptom it held for is the one now in trouble.

---

## 8. What these numbers are not

* **The 67 submissions were written by us and labelled by us.** They are
  *hand-written realistic* submissions, not real patient messages. Where they came
  from is still unresolved and still the thing stopping us committing them to the
  repository. The person who wrote the labels and the model could share a blind
  spot, and nothing here would show it.
* **Every model here has been flattered slightly by how its confidence dial was
  set** — each of the five folds had its dial tuned on another fold's test
  messages. This applies equally to both arms, so it doesn't explain the gap
  between them, but it does mean 81% is not a number to expect from a deployed
  system.
* **The slices are small.** 67 submissions, and the per-symptom parts of them run
  from 9 to 58. Section 4's table answers "did it go quiet" — which it can — and
  should not be read as a ranking of the six symptoms, which it cannot support.
* **Three symptoms have no "the patient explicitly denies it" example anywhere in
  the 67**, so for those three we cannot tell whether Arm P's handling of "no"
  survived. It's now blocking a real question rather than just narrowing one.
* **Every earlier number in the project is no longer comparable.** The data
  generator changed version, which changes every generated message, which is why
  Arm 0 had to be retrained from scratch as the control rather than read off the
  2026-08-17 run.
* **Nothing here is connected to anything.** This is a six-symptom model, the form
  declares seven, and the seventh has no trained answer.

---

## 9. What to do next

1. **Fix "going more often".** It is the one place this run made things
   meaningfully worse at the model's actual job, and a model that catches 41% of
   the people reporting a symptom is not usable for that symptom. It is also the
   second consecutive run where this symptom absorbed the cost of its confusion
   with "getting up at night" — the two are near-synonyms and we still cannot
   write a training sentence that says something about both at once. That
   capability is specified (per-line labels) and out of scope until now; this run
   is the argument for bringing it forward.
2. **Write the missing "denial" submissions.** Already the standing next ticket.
   A third of the evidence in section 4 doesn't exist because those examples
   don't exist.
3. **Set every future model's confidence dial on data that contains this
   failure.** Free, and worth a sixth of the improvement.
4. **Don't go looking for a better setting of the borrowing rate by testing
   candidates against the 67 submissions.** The rate was picked in advance on
   stated grounds precisely so that this result would mean something. Tuning it
   against the held-out set would spend the one instrument we have.

The honest summary: we predicted a mechanism, built for it, and the mechanism was
right — the model was never inventing symptoms because it was a bad model, it was
inventing them because we had never once shown it a medical-sounding message
whose answer was "they didn't mention it". Showing it some fixed 82% of the
problem in one run. The bill came due on one symptom, and that is the next
ticket.
