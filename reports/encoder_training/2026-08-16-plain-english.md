# Six symptoms, six models: what the 2026-08-16 training run found

*Written in plain language on purpose. Every number here comes from the six
`<signal>.arm_b_finetune.json` files in this folder. **Those files are the
authority** — if this document ever disagrees with one of them, the JSON is
right and this is stale. Read this to understand what happened; quote figures
from the JSON.*

---

## 0. What this is all for

A patient types a paragraph describing why they want an appointment. We want
software that reads that paragraph and fills in parts of a form for them.

For each symptom, there are exactly three answers the software can give:

* **`true`** — the patient said they have it.
* **`false`** — the patient said they do **not** have it.
* **`null`** — the patient did not say either way.

`null` is a real answer, not a failure. "The text doesn't mention it" is
information, and it is the *correct* answer most of the time. What we must never
do is guess `true` when the patient didn't say it — that would put a symptom
into a patient's form that they never reported. There is a number for exactly
that later on, and it is the one to care about most.

Each symptom is called a **signal**. Previously we had only ever trained one
signal, fever. This run trained six:

| signal | what the patient is being asked, in effect |
|---|---|
| `fever_present` | Do you have a high temperature? |
| `dysuria_present` | Does it hurt or burn when you wee? |
| `urinary_frequency_present` | Are you weeing more often than normal? |
| `nocturia_present` | Are you getting up in the night to wee? |
| `flank_pain_present` | Do you have pain in your side or back? |
| `haematuria_present` | Is there blood in your wee? |

**Important thing to not misunderstand:** we trained **six separate models**,
one per symptom. We did *not* train one model that answers all six questions.
That is a different and harder job, and it has not been done.

---

## 1. Where the training data comes from, and why that matters

We do not have thousands of real patient submissions to train on. So we wrote
sentences by hand — a few hundred per symptom — and the computer shuffles them
together into fake patient messages.

There are three kinds of hand-written sentence per symptom:

* **`_true` sentences** — plainly saying you have it. *"Going for a wee stings so
  badly it brings tears to my eyes."*
* **`_false` sentences** — plainly saying you don't. *"My urine looks the way it
  always does, plain and yellow."*
* **`_null` confounders** — the tricky ones. Sentences deliberately written to
  *sound* like the symptom while actually meaning "not said". Six families exist
  across the six symptoms, though **no single symptom has all six** — fever,
  nocturia and urinary frequency have five apiece, dysuria four, and flank pain
  and haematuria only three. They exist because they are the mistakes we expected
  the computer to make:

| family | the trap | a real line from the library |
|---|---|---|
| `third_party` | someone **else** has it | *"The baby at nursery who my daughter plays with apparently had a fever last week"* |
| `attribution` | they blame something else | *"I get hot flushes with the menopause, I've had them daily for two years"* |
| `historical` | they had it **before**, not now | *"I had a fever a couple of weeks ago that lasted about three days"* |
| `hedged` | they aren't sure | *"I'm not sure if I have a temperature or not"* |
| `metaphor` | the words aren't literal | *"I've been burning up with anger ever since that argument with my neighbour"* |
| `adjacent`\* | a **different but nearby** symptom | *"When I need to go I have to run for it, there's no warning at all."* |

\* `adjacent` exists for urinary frequency alone, and there is a reason for that
which turns out to matter — see section 8.

**This is the single most important limitation of everything below.** Real
patients did not write these sentences; we did. Everything in this report is a
measurement of how well the model handles *our writing*. That is not the same as
how well it will handle real patients, and section 12 explains why the gap could
be large.

---

## 2. What "Arm A" and "Arm B" mean

We start from a large language model that already knows a lot of English —
`roberta-base`, about 110 million adjustable numbers inside it. Two ways to use
it:

* **Arm A, the "frozen probe".** Leave the big model exactly as downloaded and
  train only a tiny decision-maker that reads its output. Fast and cheap. But the
  big model never learns anything about *our* problem.
* **Arm B, the "fine-tune".** Let the whole 110-million-number model rearrange
  itself around our data. Slower, and produces a ~440MB file per model. But it
  can actually specialise.

Arm A being good enough would have been the cheap, convenient answer. **The
question this run had to settle was whether it is.**

We also run three deliberately-stupid comparisons, so the real numbers have
something to be measured against:

| comparison | what it does | why it's there |
|---|---|---|
| `majority_class` | always says the most common answer, ignoring the text entirely | the floor. Anything at or below this has learned nothing |
| `length_only` | guesses purely from how *long* the message is | a cheat-detector. If this scores well, our fake data has an accidental giveaway in it |
| `tfidf_logreg` | old-fashioned word-counting. Sees which words appear, ignores order and meaning completely | the honest cheap competitor. If a transformer can't beat word-counting, it isn't earning its keep |

---

## 3. The results

Higher is better. `majority_class` scores 43.6% on every row, which is the floor.

| symptom | Arm B (the fine-tune) | Arm A (frozen) | word-counting | how much Arm B added |
|---|---|---|---|---|
| flank pain | **96.0%** | 80.7% | 72.8% | +15.4 |
| dysuria | **94.9%** | 82.4% | 70.5% | +12.5 |
| fever | **92.9%** | 79.0% | 73.6% | +14.0 |
| haematuria | **91.5%** | 82.8% | 74.7% | +8.6 |
| urinary frequency | **85.3%** | 67.8% | 59.9% | +17.5 |
| nocturia | **83.0%** | 70.4% | 64.9% | +12.6 |

Two words in that table need unpacking.

**"Accuracy" here means accuracy on the *decisive* examples only.** About 30% of
the generated messages contain no symptom sentence at all — just filler chat
about the weather and the school run. Those are trivially `null` and every model
gets them right, so leaving them in would flatter everything by about ten points.
They are excluded from the whole table. This is the honest number.

**Every score has an error bar** which I have left out of the table for
readability. Fever's is 92.9% with a range of 90.6% to 95.0%. Roughly: the true
value is very likely somewhere in that band, and two symptoms whose bands overlap
heavily cannot be said to differ. Section 12 explains why these bands are as wide
as they are and why they cannot be narrowed by generating more fake messages.

### The headline

**Unfreezing the model was worth it, every single time.** Arm B beat Arm A by
between 8.6 and 17.5 points on all six symptoms. Statistically this is not close:
when you compare the two models message-by-message on the hardest slice of the
data, the probability of seeing a gap this large by luck runs from about 3 in
100,000 down to numbers with 39 zeros after the decimal point.

The fever result from the previous run — where we only had one symptom to look
at — has now **replicated across five more symptoms**. That is a much stronger
statement than one symptom could ever support. The frozen probe is not good
enough, and now we know that isn't a quirk of fever.

---

## 4. A trap in these reports: word-counting sometimes "wins"

There is a slice of the data called `null_ambiguous`. It is the confounder
sentences from section 1 — the deliberately tricky ones — and it's the slice
where a smart model should prove its worth.

On that slice, dumb word-counting appears to **beat** the fine-tuned model on
three of the six symptoms:

| symptom | word-counting | Arm B |
|---|---|---|
| dysuria | 94.6% | 92.9% |
| haematuria | 93.4% | 93.3% |
| nocturia | 91.1% | 89.2% |

**Do not believe this.** Here is why it happens.

Every single message in that slice has the correct answer `null`. So a model that
simply answers `null` to everything, always, without reading a word, scores
**100%** on it.

And that is very nearly what word-counting is doing. Look at how often each model
correctly identifies a patient who *does* have the symptom:

| symptom | word-counting gets `true` right | Arm B gets `true` right |
|---|---|---|
| urinary frequency | **11.1%** | 65.8% |
| dysuria | **26.4%** | 93.0% |
| nocturia | **38.5%** | 71.1% |
| haematuria | **44.6%** | 86.6% |
| fever | **48.9%** | 87.6% |
| flank pain | **53.5%** | 96.9% |

Word-counting has essentially learned "say `null` and you'll usually be right".
It misses nine out of ten patients who actually have urinary frequency. Its good
score on the tricky slice is a side effect of being useless everywhere else.

**The general rule: never read a score on an all-one-answer slice by itself.**
Always check the model can still say `true` and `false` when it should. The
reports print this warning themselves, right above the table.

---

## 5. The big finding: the mistakes are in the *easy* sentences

This is the part that should change what we do next.

We wrote whole families of deliberately-tricky confounder sentences because we
expected them to be where the model would struggle. **They aren't.** The
confounder families mostly score between 90% and 100%. The one that consistently
gives trouble is `hedged` — patients who aren't sure themselves — which sits at
80.9% (nocturia), 84.2% (haematuria) and 84.5% (dysuria). Every other family is
comfortably above 90% almost everywhere.

The mistakes are overwhelmingly on the **plain, obvious `_true` and `_false`
sentences** — the ones nobody thought were hard:

| symptom | share of all mistakes that are on plain `_true`/`_false` sentences |
|---|---|
| urinary frequency | **87%** |
| fever | **73%** |
| nocturia | **72%** |
| haematuria | **66%** |
| flank pain | **59%** |
| dysuria | 39% |

The worst-performing individual libraries in the entire sweep are:

| library | score | what's in it |
|---|---|---|
| `urinary_frequency_true` | **65.8%** | plainly saying "I'm weeing more often" |
| `nocturia_true` | **71.1%** | plainly saying "I'm up in the night to wee" |
| `nocturia_false` | 82.4% | plainly saying "I'm not" |
| `urinary_frequency_false` | 84.1% | plainly saying "I'm not" |

Read that again: the model correctly identifies a straightforward statement of
urinary frequency **two times in three**. Meanwhile it handles the deliberately
devious metaphor sentences at 95%.

### Why this points at the data, not the model

There are two possible explanations when a model makes mistakes, and they lead to
completely different next months:

* **The mistakes are spread thinly everywhere.** That means the method itself is
  too weak → buy a better model.
* **The mistakes are piled onto a short, nameable list of specific sentences.**
  That means the model is fine and *those specific ideas aren't in our training
  data enough* → write more sentences.

It is emphatically the second. For flank pain, **half of all mistakes come from
just 4 sentences** (out of 243), and the ten worst sentences carry 90% of all
errors. For dysuria, half the errors sit on 6 sentences out of 256. Even
nocturia, the most diffuse of the six, concentrates half its errors on 17
sentences out of 351.

If the model were simply too weak, errors would be smeared across hundreds of
sentences. They aren't. **This is a data problem, and we have the list of exactly
which sentences to fix.**

---

## 6. The actual sentences it gets wrong

This is the most useful thing in this document. These are real fragments from our
libraries, with what the model said about them. Each was got wrong **every single
time** it appeared.

**It doesn't understand normal-versus-abnormal counting.** *(urinary frequency)*

> *"Six times yesterday, six times today, same as any other week."*
> Truth: **false**. Model said **true**, 53 times out of 53.

> *"I'm passing urine the usual amount of times a day."*
> Truth: **false**. Model said **true**, 64 times out of 64.

The model sees a number attached to weeing and concludes "frequency". It has not
learned that *six times a day is normal*, or that "the usual amount" means no.
There is no medical reasoning here at all — just pattern matching on the presence
of a count.

**It misses plain statements when they're phrased indirectly.** *(nocturia)*

> *"I passed water twice during the night, which is not like me at all."*
> Truth: **true**. Model said **null** 38 times, **false** twice.

> *"Two of the three trips last night my partner was awake for, so she can vouch
> for it"*
> Truth: **true**. Model said **null**, 48 times out of 48.

Both plainly say the patient got up in the night. Neither uses the word
"nocturia" or an obvious phrase like "getting up at night to wee", so the model
does not connect them.

**It doesn't recognise descriptions by comparison.** *(haematuria)*

> *"It looked like somebody had dropped red dye into the toilet."*
> Truth: **true**. Model said **null**, 60 times out of 60.

A patient describing blood in their urine by what it looked like. This is a whole
family in our library — urine compared to rosé, Ribena, cranberry juice, plum,
red wine — and the model treats the comparison as unrelated to the symptom.

**It gets confused about whose symptom it is when two people are in the
sentence.** *(fever)*

> *"dads forehead is boiling hot but he felt mine and said im cold"*
> Truth: **false**. Model said **true**, 28 times out of 28.

> *"babys forehead is roasting but I took my own with the ear thermometer and its
> 36.5"*
> Truth: **false**. Model said **null**, 30 times out of 30.

Two people, one hot and one not. The model latches onto the hot one. This is
exactly the skill our `third_party` confounders were written to teach — and it
scores 100% on those — but it fails when the same structure appears in a `_false`
sentence instead.

**It doesn't handle "I would tell you if..." constructions.** *(flank pain)*

> *"I'd tell you if my back hurt because that's always where I feel things first,
> and it doesn't this time."*
> Truth: **false**. Model said **null**, 52 times out of 52.

**It has learned that "burn" means dysuria, wherever the burning is.**
*(dysuria)*

> *"I get a burning in my chest after anything spicy, the pharmacist reckons it's
> indigestion"*
> Truth: **null**. Model said **true**, 32 times out of 32.

> *"My calves burn going up the stairs at work now..."*
> Truth: **null**. Model said **true**, 25 times out of 25.

These two are the *opposite* failure to all the others — over-triggering rather
than under-triggering — and they are the kind that ends up in the safety number
in section 9.

---

## 7. Where the fixes go

Reading the failures above, they cluster into a small number of themes. In rough
order of how much they'd buy:

1. **Normal quantities stated as numbers.** *"Six times a day"*, *"twice a
   night"*, *"the usual amount"*. Affects frequency and nocturia — our two worst
   symptoms — and it is the single biggest hole.
2. **Symptoms described by comparison rather than named.** The red-dye-in-the-
   toilet family for haematuria.
3. **Two people in one sentence, in `_false` sentences.** We taught this in the
   confounders and not in the plain classes.
4. **Conditional and hypothetical phrasings.** *"I'd tell you if..."*
5. **Body-part discipline for burning/pain words.** The model needs `null`
   examples of burning that isn't urinary, and there are apparently not enough.
6. **Genuine uncertainty.** The one confounder family that is still weak
   (`hedged`, at 81–85% on three symptoms) — patients who don't know themselves
   whether they have it. This is the only item on this list that is confounder
   work rather than clear-class work.

---

## 8. Why frequency and nocturia are the hard pair

They are last and second-to-last, and by a clear margin. Two observations.

**First, this is not the model's fault.** Dumb word-counting is *also* worst on
exactly those two symptoms (59.9% and 64.9%, against 70–75% everywhere else).
When both the sophisticated method and the crude method struggle on the same two
symptoms, the difficulty is in the symptoms, not the method.

**Second, the likely reason is that they are near-synonyms of each other.**
Urinary frequency is "weeing a lot". Nocturia is "weeing a lot, at night". Almost
any sentence about one is a plausible sentence about the other, and the
difference often rests on a single word. Supporting this: urinary frequency is
the **only** symptom whose library set needed an `adjacent` confounder family —
sentences about a nearby-but-different symptom — because whoever wrote it ran
into this problem by hand.

**This is a hypothesis, not a finding.** Nothing in this run tests it. The
obvious test is to look at what the two models actually confuse things *for*, and
that has not been done.

---

## 9. The number that matters for patient safety

Everything above is about accuracy. This is about harm.

**`null → true`** counts the times the model invented a symptom — the patient did
not say they had it, and the model said they did. If that reaches a real form,
the patient sees a symptom they never reported already filled in on their behalf.

| symptom | invented-symptom rate |
|---|---|
| fever | 1.34% |
| flank pain | 1.51% |
| urinary frequency | 1.94% |
| haematuria | 2.33% |
| dysuria | 3.49% |
| **nocturia** | **4.04%** |

Nocturia is three times fever's rate. Dysuria is more than twice it, and section 6
shows why — it fires on chest burning and calf burning.

Two things to be clear about:

* Every model here has a **decision rule** on top of it whose stated job is to
  keep this number no worse than it would otherwise be. These figures are already
  after that rule.
* **No head from this run is connected to anything.** Nothing here is in the live
  system, and per the project's rules a model's output can never overwrite an
  answer a patient typed themselves. But "1 in 25 messages gets a symptom
  invented" is not a number to take to a safety review, and nocturia and dysuria
  need work before anyone proposes using them.

---

## 10. How we know these numbers aren't fake

Three independent checks, all passed.

**The sabotage test.** For every symptom, we trained an extra model on
**deliberately scrambled** answers — the messages kept, the correct answers
shuffled into the wrong order. A model trained on nonsense must score like random
guessing. All six scored 43.6%, which is exactly the floor. If any had scored
well, it would mean the model was finding some accidental giveaway rather than
reading the text, and everything in this report would be void.

The scrambled models *did* drive their training error to almost zero — they
memorised the nonsense. That is expected and correct. Memorising the training set
while scoring at chance on unseen data is precisely what a working sabotage test
looks like.

**The cheat-detector.** The `length_only` model, which sees only how long a
message is, scored 43.6–46.9% — essentially the floor everywhere. Message length
does not give away the answer.

**The repeat test.** Fever was retrained from scratch in this run and produced
**92.9%, with an error band of 90.6% to 95.0%** — identical to three decimal
places to the fever figure recorded weeks earlier under the same settings. The
pipeline is reproducible.

**Separately: nothing was memorised across the train/test boundary.** Every
sentence is used for either training or testing, never both, and where we wrote
two versions of the same idea both go to the same side. The loading code checks
this on every run and refuses to proceed if it's violated.

---

## 11. A prediction we made in advance, and got wrong

Before this run, the plan recorded a prediction. Writing predictions down before
looking is how you avoid explaining afterwards why whatever happened was what you
expected.

**The prediction.** Some of our libraries are hand-marked to show when two
sentences are really the same idea written twice. Fever and dysuria are marked;
the other four are not at all. Marked libraries are honest about having fewer
genuinely distinct ideas, so we predicted:

* the four unmarked symptoms would post **better** scores for bookkeeping reasons
  rather than real ones, and
* **dysuria would look worst**, being the only fully-marked one — penalised for
  its own honesty.

**What happened.** Dysuria came **second of six** at 94.9%. The two worst
symptoms, nocturia and urinary frequency, are both completely unmarked — exactly
the ones that were supposed to be flattered.

**The verdict: did not hold, and in the opposite direction.**

The underlying concern is still real — an unmarked library's error bars genuinely
are narrower than the truth, and this run's reports now print that warning
automatically at the top of every page. What's now measured is that this effect
is **small compared to how good the underlying sentences are**. Differences in
what's actually written in the `_true` libraries swamp it completely.

---

## 12. What these numbers are not

**These are not results about real patients.** Every message scored here was
assembled by our own generator from a few hundred sentences we wrote ourselves.
Testing on unseen sentences removes the risk of the model having memorised
answers, and that is *all* it removes. The test messages are still short, still
built by the same program, from the same libraries, in the same voice. Nothing
here tells you what happens when a real patient writes three rambling paragraphs.

**"10,000 training examples" is a misleading number, and it is the easiest thing
here to over-read.** They are shuffles of a few hundred hand-written sentences.
Ten thousand messages built from 250 sentences is 250 ideas seen many times, not
10,000 pieces of evidence. The error bars are computed over the count of
*distinct ideas*, which ranges from 182 (dysuria) to 418 (fever). **Generating
more messages would not narrow them by a hair.** Only writing more sentences
would.

**One symptom at a time.** Six separate models, six separate 440MB files. The
live system's rules require a single model that answers all seven of the
ruleset's questions at once, and the seventh (`recent_uti_present`) has no
training sentences at all. Nothing here can be plugged in.

**A small optimism in the pooled figures.** For fiddly reasons about how the data
is split five ways, each model's final settings were tuned on data that was
another model's test data. The effect is small, it's documented, and the
alternative costs more than it's worth — but the numbers are very slightly
flattering.

**One symptom's results wobble more than the rest.** Urinary frequency scored
between 82.0% and 93.4% depending on which fifth of the data was held back. Treat
its 85.3% as the shakiest number in the table.

---

## 13. What to do next

**Write more `_true` and `_false` sentences.** Not more confounders — those are
working. Start with `urinary_frequency_true` and `nocturia_true`, and cover the
five themes in section 7. Section 6 names the specific sentences that fail; that
list is the brief.

**Do not buy a bigger model.** Nothing in this run suggests the method is the
constraint. The errors are concentrated and nameable, which is the signature of a
data problem, and a larger model would learn the same gaps faster.

**Test the frequency/nocturia confusion hypothesis** from section 8 before
writing sentences for either, since the answer changes what to write.

**Then: the thing that actually decides whether any of this is real.** Write
60–100 realistic full patient messages by hand, deliberately unlike anything the
generator produces. Label them by hand. Lock them away and never let them
influence a training decision. Until that exists, **every number in this document
is a measurement of how well our models handle our own writing**, and no more
than that — however good the numbers look.
