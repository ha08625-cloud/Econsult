# The realistic held-out evaluation set

67 free-text UTI submissions written to read like real patients. This is the set
`encoder_next_steps.md` §3 (Ticket A) specifies, and it exists to answer one
question that nothing else in this project can: **is any number produced against
the recombined fragment libraries evidence about real patient text?**

Everything measured so far has been scored on recombinations — two or three
fragments, exactly one supervised claim plus filler, drawn from the same
libraries in the same register as the training data. 92.9% there could be 55%
here and no report currently produced would show it.

## The rules, and they are not negotiable

These come from the ticket, and they are written here because the first
disappointing number is when they get broken.

1. **Never used for training.** Not as training data, not as extra examples, not
   "just the ones the model gets wrong". The moment any of these text influences
   any weight, the set stops measuring anything and there is no way to undo it
   short of writing 67 more.
2. **Never used to select anything.** Not a decision margin, not a pooling mode,
   not an epoch count, not a base encoder, not which fragments to write next.
   Every one of those choices is made against the synthetic validation split.
3. **Scored once per candidate model, and the number is recorded.** Including the
   bad ones. A set that only gets reported when it flatters is not a held-out set.
4. **A signal the labeller cannot judge gets its key omitted, not set to `null`.**
   The dataset format distinguishes missing from `null` and the loader excludes
   masked signals from scoring. Guessing `null` invents a label, which is the
   exact failure the label-first design exists to prevent.
5. **The resampling unit is the submission.** There is no cluster structure here,
   so each submission is one independent observation — unlike the synthetic sets,
   where the unit is the fragment cluster.

## Files

| file | what it is |
|---|---|
| `uti1_holdout.source.txt` | **The source of truth.** One submission per line, verbatim. |
| `uti1_holdout.labels.tsv` | The labels. One row per submission, one column per `send_to_encoder` signal in `data/uti1.json`. |
| `uti1_holdout.arbitrate.md` | The 13 cells where the call is genuinely arguable, with the text and the reasoning. Read this first when reviewing. Two of its proposals were overruled and it says which; the TSV is the labels. |

`submission_id` is `holdout-NNNN`, assigned by line order in the source file.
**Do not reorder or insert lines in the source file** — the ids would shift and
every label already recorded would attach to the wrong text. Append only.

The text is verbatim, including spelling mistakes, missing apostrophes, missing
spaces and inconsistent capitalisation (`stingign`, `atrong`, `anyibiotics`,
`wprk`, `ny immune aystem`). That is not sloppiness to be tidied up — it is the
single most important way this set differs from the recombinations, and
correcting it would quietly make the evaluation easier than reality. Only
trailing whitespace was stripped.

## Filling in the worksheet

Four values per cell:

| value | meaning |
|---|---|
| `true` | the text indicates this signal is present |
| `false` | the text indicates this signal is **absent** — an explicit denial, not silence |
| `null` | the text mentions the territory but does not settle it |
| *(blank)* | the labeller cannot judge it; the key is omitted from the dataset entirely |

The distinction that matters most and is easiest to get wrong: **silence is not
`false`.** A submission that never mentions temperature is `null` for
`fever_present`, not `false`. `false` is reserved for "no fever", "no back pain
or fever", "No blood, no fever" — an explicit denial the patient made.

### Why there are no blanks, and when there should be one

**Every one of the 469 cells has a value, and that is the correct state of this
file rather than a sign that `null` quietly absorbed "cannot say".** The
question was left open when the scoring code was planned and was settled by
review on 2026-08-16; the answer is recorded here rather than in a plan because
the plan is not what a future labeller reads.

Three states get confused with each other, and only the third is a blank:

* **Silent.** The text never raises the signal at all. That is `null` — the
  paragraph above says so explicitly, and it is the majority of the file.
* **Raised and unsettled.** The text is about the territory and does not decide
  it: "it doesn't hurt too badly to pee", "blood on the toilet paper". That is
  also `null`, and where the call is *arguable* it is listed in
  `uti1_holdout.arbitrate.md` with the reasoning. Arguable is not the same as
  unjudgeable — an arguable cell was judged, and the arbitration file exists so
  the judgement can be overturned by a person rather than hidden.
* **Unjudgeable.** The labeller cannot decide *and* cannot say the text is
  silent or unsettled either — the sentence is garbled, contradicts itself, or
  turns on clinical knowledge the labeller does not have. That is the blank, and
  no submission here produced one.

Every submission in this set is a UTI-context text written by one person, so
every signal is either plainly raised or plainly silent. A blank becomes likely
the moment that stops being true: a submission that turns out not to be a UTI at
all, or one written by someone whose meaning genuinely cannot be recovered — both
of which are things the "what to write next" section below asks for. The loader
(`scripts/encoder_training/holdout.py`) implements the distinction whether or not
today's file uses it, and refuses to merge a blank into a `null`;
`tests/test_encoder_training_holdout.py::test_no_cell_in_the_real_file_is_omitted`
fails if one appears, so it will be a decision someone makes rather than one that
happens.

## How it is scored, and where the rules are enforced

`scripts/encoder_training/holdout.py` loads this file and computes the numbers;
`arch_encoder_training.md` section 11 is the design. Two of the rules above are
enforced by construction rather than by anyone remembering them:

* **Rule 2 (selects nothing)** is enforced by the call order. Each fold model is
  scored here *after* its decision margin has been chosen on the synthetic
  validation split and *after* the synthetic test split has been scored, so by
  the time this set is opened there is nothing left for it to influence. The
  order lives in one function, `train.select_then_score`, so that a unit test
  can assert the sequence rather than a reader having to trust it.
* **Rule 5 (the submission is the resampling unit)** is enforced by the
  bootstrap: a submission's six or seven cells carry one unit id and resample
  together.

**Rule 3 (scored once per candidate model, and the number is recorded, including
the bad ones)** is not something code can enforce. What the code does is make
skipping visible: the run either scores the set or is told `--no-holdout`, and
the report prints which. A number is recorded per fold in the model's metadata
sidecar and per model in the evaluation report.

The negative controls are deliberately *not* scored here. A model fitted on
permuted labels is not a candidate model, and 67 submissions are too few to
spend confirming that it is bad.

## Provenance of the labels

**The labels were proposed by Claude and reviewed by the maintainer.** They were
not produced independently of the models being scored. This is a real limitation
and it belongs in every report that uses this set: the labeller and the model
share an architecture and could in principle share a blind spot, which would
inflate the score in a way no amount of resampling would reveal. It is not fatal
— every arguable cell was surfaced for arbitration in `uti1_holdout.arbitrate.md`
and the plain readings are plain — but the set is weaker evidence than one
labelled by a clinician who had never seen the fragment libraries.

## What this set can and cannot support

Labelled distribution, from `uti1_holdout.labels.tsv`. **The decisive column is
the one that bounds anything** — `null` examples are the ones a model scores by
answering "no information", which the majority-class baseline does perfectly.

| signal | true | false | null | decisive |
|---|---|---|---|---|
| `dysuria_present` | 56 | 0 | 11 | **56** |
| `urinary_frequency_present` | 26 | 0 | 41 | **26** |
| `fever_present` | 9 | 9 | 49 | **18** |
| `flank_pain_present` | 7 | 7 | 53 | **14** |
| `haematuria_present` | 9 | 2 | 56 | **11** |
| `nocturia_present` | 9 | 0 | 58 | **9** |
| `recent_uti_present` | 2 | 4 | 61 | **6** |

*Two cells of this table were stale until 2026-08-16 and are corrected above.
The `urinary_frequency_present` and `recent_uti_present` rows were written from
the labels as first proposed; the maintainer then revised two of them --
`holdout-0003` urinary frequency `true` -> `null`, and `holdout-0004` recent UTI
`false` -> `null` -- and the summary was not recounted. The TSV is the labels,
so the TSV was right and the table was wrong.
`tests/test_encoder_training_holdout.py::test_the_readme_distribution_table_matches_the_labels_file`
now recounts it on every commit, because this table is quoted in reports.*

Two things follow, and both are more limiting than the raw count of 67 suggests.

**Three signals have no `false` examples at all.** `dysuria_present`,
`urinary_frequency_present` and `nocturia_present` are all-`true` where they are
decisive. A model that never predicts `false` on those signals is not penalised
anywhere in this set, so a high score on them says only that positives are
recognised. Nothing here measures whether an explicit denial is read correctly —
which was the single largest error family in the synthetic evaluation.

**`fever_present` is the best-balanced slice and still the smallest useful one.**
9 `true` against 9 `false` is exactly the shape needed to catch the failure mode
that matters, and 18 observations gives roughly ±20 points. That is enough to
detect a catastrophe — a model that scored 92.9% on recombinations landing near
chance on real text would be unmissable — and nowhere near enough to separate two
models, or to justify a decimal place. Any report that puts a fever number from
this set next to a recombination number must print both `n`s beside them.

Writing more submissions is the fix, and the shortage is specific rather than
general: what is missing is **explicit denials** ("no burning", "I'm not going
more often than usual", "no waking at night") and submissions where the patient
is describing something that turns out not to be a UTI at all.

## The limitation to state in every report that uses this

67 submissions written by one person share that person's voice and that person's
idea of what a patient sounds like. Real submissions vary by age, first language,
literacy, how ill the person feels while typing, and what they think a GP wants
to hear. This is a large improvement on recombinations and it is still not a
random sample of patients.
