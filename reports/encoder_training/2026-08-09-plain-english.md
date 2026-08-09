# Plain-English version of `2026-08-09.md`

*This is a translation, not a second opinion. Every number here comes from
`2026-08-09.md`, which in turn comes from `fever_present.arm_b_finetune.json`.
If this document and that one ever disagree, that one is right. Read this to
understand what happened; quote figures from the original.*

---

## 0. What was even being tested

We want a model that reads a patient's free-text description and decides whether
they are saying **"I have a fever" (`true`)**, **"I do not have a fever"
(`false`)**, or **"I haven't said either way" (`null`)**. That single yes/no/silent
judgement is called a **signal**, and this run only trained one of them
(`fever_present`).

There was one open question. A pre-trained medical language model already knows a
lot about English. Two ways to use it:

* **Arm A — the "frozen probe".** Leave the big model exactly as it came, and
  train only a small classifier that reads its output. Cheap and fast, but the
  big model never learns anything about *our* problem.
* **Arm B — the "fine-tune".** Let the whole 110-million-parameter model adjust
  itself to our data. Slower, ~440MB of weights, but it can actually specialise.

If Arm A had been good enough, that would have been the easy answer. The ticket
was: is it?

And behind that, a bigger question. When Arm B still gets things wrong, is that
because **the method is too weak** (→ we need better/bigger models) or because
**the training data doesn't contain the ideas it is failing on** (→ we need to
write more example sentences)? Those two need completely different next months,
so it matters which one it is.

---

## 1. The answer, in one paragraph

Unfreezing the model was worth a lot — about **12 points** of accuracy. So Arm A
really was holding things back, and if we'd stopped there we'd have concluded the
data was worse than it is.

But the remaining mistakes are not a general fog of confusion. They are piled up
on a **small, nameable list of sentences** — half of all errors come from just
**17 sentences** out of 394. That shape says: not a model problem. A data problem.

And they are piled up in the **wrong place**. We had written four libraries of
deliberately tricky "sounds like a fever but isn't" sentences, expecting those to
be the hard part. They turned out fine. **71% of the errors are on the supposedly
easy sentences** — plain "I have a fever" and plain "I don't have a fever".

So: **the next month is writing more example sentences for the easy classes**, not
buying a bigger model.

---

## 2. The headline table, translated

| model | what it actually is |
|---|---|
| `majority_class` | Always guesses the most common answer. A floor — anything worse than this is broken. |
| `length_only` | Guesses purely from how long the sentence is. A cheat-detector: if this scores well, the data has an accidental giveaway in it. |
| `tfidf_logreg` | Old-school "bag of words" — counts which words appear, ignores order and meaning entirely. The honest cheap competitor. |
| `arm_a_probe` | The frozen model. |
| `arm_b_finetune` | The full fine-tune. **The thing we're actually evaluating.** |

The scores (higher is better):

| model | accuracy on the real decisions | macro-F1 |
|---|---|---|
| `majority_class` | 43.6% | 20.2% |
| `length_only` | 44.1% | 22.1% |
| `tfidf_logreg` | 70.0% | 66.5% |
| `arm_a_probe` | 71.6% | 68.0% |
| **`arm_b_finetune`** | **83.5%** | **82.1%** |

Two bits of jargon in that table:

* **"decisive"** means we've thrown away the easy cases — the examples where the
  patient obviously said nothing about fever at all. Those are trivially right and
  they pad the score. The original report shows an "overall" column too (Arm B:
  88.4%), which is the flattering number. **Use the decisive one.**
* **macro-F1** is accuracy that refuses to be gamed by ignoring a rare class. A
  model that gets the common answer right and the rare answers always wrong has
  decent accuracy and terrible macro-F1. Arm B's two numbers being close together
  (83.5 / 82.1) means it isn't cheating that way.

**The one genuinely reassuring line is `length_only` at 44.1%** — barely above the
"always guess the same thing" floor of 43.6%. We were worried the model might be
picking up on the fact that our hand-written "yes fever" sentences are longer than
our "no fever" ones. This measures that worry directly, and the answer is that
there's almost nothing there to exploit.

---

## 3. "Did it cheat?" — the negative controls

Before believing any of the above, you check the pipeline isn't secretly scoring
itself. The test is deliberately absurd: **scramble the training answers at
random**, train again, and see what happens.

A model that has genuinely learned nothing should:

1. still be able to **memorise** the nonsense (because it has 110M parameters and
   memorising is easy), *and*
2. score **no better than chance** on the real test set.

Arm B did both — memorised the scramble almost perfectly, then scored 60.1–60.8%
on test, which is exactly "always guess the common answer". Both halves matter.
Passing only the first would mean the test was broken; passing only the second
would mean training was broken.

Separately, the code checks on every single run that no sentence and no group of
related sentences ever appears in both the training set and the test set. If it
did, the model would be marked on homework it had already seen.

**Verdict: clean.**

---

## 4. The trap in the results (this bit is important)

There is one row in the original report that, read alone, says **bag-of-words
beats the expensive transformer** — 94.9% vs 89.1% — on `null_ambiguous`, which
is precisely the slice this whole ticket was aimed at. If you quote one number
from this report and it's that one, you'll reach the wrong conclusion.

Here's why it's fake. Every single example in `null_ambiguous` has the answer
`null`. So a model that just says "null, null, null, null" forever scores **100%**
on it. Bag-of-words is closer to doing that than Arm B is: it says `null` 7,533
times when the true count is 6,040. It buys its score on this slice by being
badly over-cautious everywhere else — it only catches 47% of real fevers. Arm B
catches 81%.

They're making different trade-offs, so comparing them on an all-one-answer slice
is meaningless.

On the slice where both answers actually occur, Arm B beats bag-of-words by
**13.5 points**, and the statistical test on that comparison is about as
conclusive as such tests get.

**One more finding worth holding onto:** Arm A — the cheap frozen version —
**does not reliably beat bag-of-words at all**. If we'd only built Arm A, the
honest write-up would have read "a transformer is no better than word-counting
here", and that would have been **false**. Building both arms is the only reason
we know that.

---

## 5. Where the mistakes actually are

Accuracy per library of sentences:

| library | what's in it | accuracy |
|---|---|---|
| `fever_false` | plain "I don't have a fever" | 78.1% |
| `fever_true` | plain "I have a fever" | 81.0% |
| `fever_null_hedged` | "I'm not sure if I've got a temperature" | 75.6% |
| `fever_null_thirdparty` | someone *else* had a fever | 90.5% |
| `fever_null_metaphor` | "hot under the collar", figures of speech | 92.0% |
| `fever_null_historical` | had a fever, but ages ago | 92.1% |
| `fever_null_attribution` | quoting what someone told them | 94.0% |

The bottom four are the ones we designed to be traps. **They're now the model's
strongest area.** The two "easy" ones at the top are the worst. That inversion is
the single most useful thing this run produced.

Reading the actual failing sentences, they fall into three families:

**(a) A negation wrapped around a positive.** The model reads the first half and
stops thinking.

> "My mum was really poorly with a fever last week and I was caring for her but I
> never got one myself"

The sentence contains a real fever — just not this patient's. Five sentences of
this shape are wrong **every single time** they appear.

**(b) A fever described without the word "fever".**

> "Thermometer said I was cooking, way above normal."

The model has memorised a vocabulary rather than a concept. No fever word, no
detection.

**(c) A fever buried under the patient explaining why they need an appointment.**

> "I keep getting these hot flushes and my partner says I'm on fire, I can't
> function properly and I've got three important meetings I can't miss."

We predicted this "urgency language" would be a problem, but predicted it would
make positives *easier* to spot. It does the opposite — the urgency drowns the
symptom.

**And one honest caveat:** `fever_null_hedged` at 75.6% is the weakest of the four
trap libraries, but it's also our smallest library, so that number could really be
anywhere from about 60% to 89%. It fails in both directions at once, which is what
"genuinely hasn't seen enough examples" looks like. It needs more data before it
needs a diagnosis.

---

## 6. What to do next

**Write more sentences. Specifically:**

1. **30–40 new "contrastive negative" sentences** — "someone else had a fever /
   I had one before, but I don't now". Biggest error family, near-zero coverage.
2. **Fever described without fever words** — idiom, thermometer readings, physical
   description.
3. **Grow the "hedged" library.** Smallest and weakest.
4. **Leave metaphor, historical, third-party and attribution alone.** They're at
   90–94%. Effort there is wasted.

**Do not buy a bigger model.** The errors are concentrated on ideas that are barely
present in the training data, and no amount of parameters invents examples that
were never written.

---

## 7. What this number is NOT

**83.5% is not a claim about real patients.**

Everything above was scored on sentences assembled by recombining a few hundred
hand-written fragments. Holding some fragments back for testing proves the model
didn't just memorise them — and nothing more than that. The test sentences are
still short (median 36 tokens — roughly, words), still contain exactly one clear claim plus filler,
still written in the same voice by the same people.

Real e-consult submissions are longer, messier, and cover several things at once.
**We have not measured performance on anything like that.** The gap is unknown, and
it is not small.

So the genuinely important next ticket — bigger than any of the library work — is:
**write 60–100 realistic full submissions by hand, deliberately unlike the
generated ones, label them by hand, and never let any training decision touch
them.** Until that exists, none of this is evidence about production behaviour.

## 8. Three other things worth knowing before quoting this

**The sample size is 349, not 7,022.** The test set has 7,022 examples, but they're
recombinations of only **349 distinct hand-written ideas**. Seeing the same idea
100 times doesn't make you 100 times more confident about it. Every error bar in
the report is calculated on the 349, which is the honest way round.

**Each per-library figure carries roughly ±8 points.** Running five folds bought
us about a 3× improvement on that error bar — enough to make the numbers usable,
not enough to make them precise. "92.0%" means "probably somewhere in the
mid-80s to high-90s".

**The results are mildly flattered.** One tuning knob per fold was chosen using a
neighbouring fold's test data. The fully rigorous fix was judged not worth the
compute for a single number, but it means the true figure is a touch below the
reported one.

**Arm B is less consistent than Arm A.** Across the five folds it scored 93.7%,
84.9%, 92.7%, 85.2%, 85.5%. That ~8-point swing is real, and it's a reason to
treat any single-fold number with suspicion.

**And it only does one signal.** `fever_present` alone. The live system's contract
requires all seven signals declared in `data/uti1.json` before a real encoder can
be plugged in. This work is a proof that the approach can work — it is not a
component that can be shipped.
