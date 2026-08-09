# Provisional plan: what to do after the fever head

**Status: provisional and not agreed.** This is stage-1 output — the discussion,
the design decisions I think follow from it, and open questions. It is written to
be argued with, then turned into an implementation plan.

**Reads on:** `reports/encoder_training/2026-08-09.md` (the run this responds to),
`arch_training.md` §9–12, `arch_encoder_training.md`.

---

## 1. The arithmetic that should drive this

`fever_present` now works reasonably well on its own recombinations: 83.5%
decisive accuracy, 82.1% macro-F1, and the confounder libraries it was built for
are at 90–94%. That took **344 hand-written fragments across six libraries**, plus
370 filler fragments that are shared and therefore a one-off.

The rulesets declare **84 `send_to_encoder` signal slots across 13 conditions,
80 of them distinct**. Only four signals appear in more than one ruleset
(`fever_present`, `fever_or_unwell`, `injury_related`, `cancer_diagnosis`), so
sharing amortises almost nothing.

At the fever library's standard, 80 signals is **roughly 27,500 hand-written
fragments**. Writing fifty a day, every working day, is over two years — and the
fever libraries were not written at fifty a day, because the thinking is the
expensive part, not the typing.

That is not a schedule. It is a reason to stop and measure two things before
buying any more fragments:

1. **Does the 83.5% survive contact with real patient text?** Every number in
   every report so far is scored on recombinations of the same fragments the
   model trained on. Held-out *clusters* remove memorisation and nothing else.
2. **How does the score depend on library size?** Nobody has measured whether a
   signal needs 344 fragments or 60. The difference between those two answers is
   the difference between a nine-month project and a three-year one.

Both are cheap. Both change what the next year looks like. **Writing more
fragments before either is answered means paying the most expensive activity in
the project at an unknown exchange rate.**

## 2. Something to decide before any of it

**The encoder is not on the critical path to going live.** `encoder_stub` works,
encoder-filled answers never overwrite patient answers, and a patient can answer
every question themselves. What actually stands between this repository and a
live product is on your own production-readiness list: MHRA registration, data
protection, the clinical safety case, SOPs, disclaimers, a tested backup restore,
a deployment runbook.

So there is a prior question, and it is yours rather than mine: **is the next
quarter "live with one practice" or "prove the differentiator works"?** If it is
the former, the encoder should be paused rather than accelerated, and this plan
waits. If it is the latter, §3 and §4 are the cheapest way to find out whether
the approach scales before committing years to it.

Worth having as a decision rather than a default. The encoder is the interesting
part of the system, which is exactly why it is easy to keep working on.

## 3. Ticket A: the held-out realistic evaluation set

**The one the last three tickets have all pointed at.** 60–100 full submissions,
hand-written to read like real patients, labelled by hand, held out permanently.

**Why it is first.** Nothing measured so far is evidence about real patient text.
The test examples are two or three fragments long, carry exactly one supervised
claim plus filler, and come out of the same generator in the same register as the
training data. 83.5% could be 55% on real submissions and no number currently
produced would show it.

**Design decisions I would make:**

* **Label every uti1 signal on each submission, not just fever.** A realistic
  submission naturally mentions several things. The marginal cost at writing time
  is small and it turns a fever evaluation set into a *uti1* evaluation set that
  every future head is scored against. This is the highest-leverage detail in the
  ticket.
* **A signal the writer cannot judge gets its key omitted, not set to `null`.**
  The dataset format already distinguishes missing from `null`, the loader already
  excludes masked examples from scoring, and guessing `null` would invent labels —
  the exact failure the label-first design exists to prevent.
* **Write them without the fragment libraries open.** Ideally in a different
  sitting from any library work, ideally by someone who has not read them. The
  point is text that is *unlike* the recombinations: longer, several symptoms per
  sentence, spelling mistakes, missing punctuation, questions addressed to the GP,
  tangents mid-clause, background the patient thinks is relevant and is not.
* **Never used to select anything.** Not a margin, not a pooling mode, not an
  epoch count, not which fragments to write next. Scored once per candidate model
  and recorded. This will be tempting to break the first time a number is
  disappointing, which is why it goes in writing now.
* **The resampling unit is the submission.** There is no cluster structure, so
  each submission is one independent observation. Eighty submissions gives roughly
  ±9 points at 80% — the same order as the fold-pooled recombination interval, and
  honestly come by.

**Code, and it is modest.** A loader path for hand-written JSONL with no
`.stats.json` sidecar and no fragment provenance, and a `score` subcommand that
runs saved head artefacts against an arbitrary labelled set. The report writer
already accepts any set of predictions; the bootstrap needs to resample
submissions rather than clusters.

**The limitation to write down before we start:** 60–100 submissions written by
one person share that person's voice and that person's idea of what a patient
sounds like. That is a large improvement on recombinations and it is still not a
random sample of patients. It should be stated in every report that uses it.

## 4. Ticket B: the library-size learning curve

**The cheapest experiment in the project and possibly the most consequential.**
Train the Arm B recipe on 12.5%, 25%, 50% and 100% of the fever training clusters
and plot decisive accuracy against training clusters.

**The one design point that decides whether it means anything: only the training
pool shrinks.** Subsampling happens *after* split assignment, so validation and
test hold the same clusters at every point on the curve. Otherwise each point is
scored against a different test set and the curve measures nothing.

**What the shape tells us:**

* Still climbing at 100% → more fragments per signal is the right investment, and
  the curve says roughly how many buy how much.
* Plateaued well before 100% → the fever library is already past the point of
  diminishing returns, more fragments are not the answer, and the method has to
  change rather than the data. That would be the most important finding available
  right now.

**Prediction, recorded so it can be scored** (the last plan wasted its prediction
by not scoring it; this one should not): I expect the curve to be **still
climbing at 100%**, because the 2026-08-09 error analysis found the residual
sitting on ideas the libraries barely cover. I also expect the marginal return per
cluster to have fallen a lot between 50% and 100%.

**Second experiment, same machinery, one flag apart:** leave one confounder
library out of training entirely and test on it. Train with no
`fever_null_metaphor`, score metaphor. This asks whether the model needs examples
of *every* confounder family or generalises across them — the scaling question in
miniature, on the good data rather than the thin dysuria seed. I expect it to do
badly, and if it does not, that is a much cheaper future than §1 implies.

**Cost:** four points × five folds × ~2 minutes, plus the leave-one-out run.
Under an hour of GPU and a small generator flag.

## 5. Ticket C: the targeted library work, once A and B report

This is what `2026-08-09.md` recommended, and I would now **hold it until A and B
land** rather than start it. It is the most expensive thing on the list in human
terms, and A and B between them say whether it is aimed correctly.

Unchanged in content when it does start:

1. **30–40 contrastive negatives** — "someone else, or some other time, had a
   fever; I do not now". The single largest error family, and `fever_false` has
   almost no coverage of it. Cluster-tag them; they will produce near-duplicates
   by construction.
2. **Non-vocabulary positives** — fever asserted through idiom, thermometer
   readings, physical description with no fever word. The model has memorised a
   lexicon.
3. **Grow `fever_null_hedged`** — 32 clusters, the smallest confounder library,
   the worst-performing at 75.6%, and the widest interval in the table.
4. **Leave metaphor, historical, third-party and attribution alone.** 90–94% and
   not where the loss is.

## 6. Decide now, cheaply: does `EncoderOutput` permit partial output?

`EncoderOutput.validate_against` requires the output keys to match the ruleset's
`send_to_encoder` signals **exactly**. `uti1.json` declares seven, so no encoder
can be wired in until all seven heads exist. There is currently no incremental
path at all: every ruleset is all-or-nothing, and at 80 signals that is 13 big
bangs.

Two options:

1. **Permit a subset.** `encoder_mapping` treats an absent key as "no signal
   offered", which is already the missing-vs-`null` semantics the training data
   uses. Small change, and it converts the blocker into "ship the fever head, add
   heads as libraries land". `fever_present` appears in `uti1` and `ear_pain`, so
   the first head would cover two rulesets.
2. **Keep exact match** and require full per-ruleset coverage before anything
   ships.

**I would take option 1**, and I would decide it before Ticket C rather than
after, because it changes what "finished" means for every library. It is also the
one item here that is nearly free.

The safety argument is unaffected either way: encoder output never overwrites a
patient answer, and a signal the encoder does not offer is simply a question the
patient answers themselves — which is exactly today's behaviour with the stub.

## 7. Suggested order

| | Work | Cost | What it decides |
|---|---|---|---|
| 1 | **D** — the contract decision | An afternoon | What "finished" means per ruleset |
| 2 | **B** — the learning curve | An hour of GPU, small flag | Whether 80 signals is affordable at all |
| 3 | **A** — the realistic evaluation set | Days of careful human writing, modest code | Whether any number so far is evidence |
| 4 | **C** — targeted library work | Weeks of human writing | Held until A and B report |

B before A only because B is nearly free and can run while A is being written. If
only one gets done, **do A**.

## 8. Open questions

1. **Live-with-one-practice or prove-the-encoder?** (§2.) Everything else is
   downstream of this.
2. **Who writes the realistic submissions?** One person's voice is a real
   limitation. Is there anyone else — clinical or not — who could write twenty of
   the eighty without reading the libraries first?
3. **Is 80 signals the right target, or should some questions stop being
   `send_to_encoder`?** A signal the patient can answer in one tap may not be
   worth 344 fragments. Nobody has audited the 80 for which ones the encoder
   actually earns its keep on.
4. **Does the contract change need the safety case revisiting**, given the system
   is a registered class I device? Probably not, since it narrows rather than
   widens what the encoder may assert — but it is the kind of thing that should
   be asked before it is done, not after.
5. **Should Ticket B's curve be run on a second signal too?** Dysuria's seed
   libraries are 14–24 fragments, so a curve on them would be mostly noise. But
   "does the curve look the same for a different signal" is the question that
   licenses generalising from fever to the other 79.
