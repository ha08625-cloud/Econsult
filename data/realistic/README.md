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
| `uti1_holdout.labels.tsv` | The hand-labelling worksheet. One row per submission, one column per `send_to_encoder` signal in `data/uti1.json`. |

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

## What this set can and cannot support

Signal coverage is uneven, because it was written as realistic submissions rather
than balanced per signal. Roughly how many submissions contain language relevant
to each signal at all (keyword estimate, not labels):

| signal | submissions touching it |
|---|---|
| `dysuria_present` | ~52 / 67 |
| `urinary_frequency_present` | ~26 / 67 |
| `haematuria_present` | ~16 / 67 |
| `flank_pain_present` | ~14 / 67 |
| `nocturia_present` | ~12 / 67 |
| `fever_present` | ~18 / 67 |
| `recent_uti_present` | ~9 / 67 |

So this set can carry a reasonable statement about `dysuria_present` and only a
weak one about `recent_uti_present`. Note especially that **`fever_present` — the
only head trained so far — is one of the thinner slices.** With the resampling
unit at one submission, 67 observations gives roughly ±9 points at 80% on a
signal every submission speaks to, and considerably worse than that on a slice of
18. Read the per-signal `n` in any report before reading its accuracy.

## The limitation to state in every report that uses this

67 submissions written by one person share that person's voice and that person's
idea of what a patient sounds like. Real submissions vary by age, first language,
literacy, how ill the person feels while typing, and what they think a GP wants
to hear. This is a large improvement on recombinations and it is still not a
random sample of patients.
