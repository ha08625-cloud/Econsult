# Token / label-class association in the fragment libraries — 2026-09-03

Output of `python -m scripts.synthetic_data --lint` (token-association section)
against the committed `data/synthetic/` tree. This is Task 1 of the lexical
variant expansion plan and the first of its two gates, so it is committed rather
than left in a terminal scrollback: it is the input to the choice of pilot signal
(DD10), and that choice should be auditable after the fact.

The detail cap is raised for this file. The tool prints the worst
`TOKEN_ASSOCIATION_DETAIL_LIMIT = 12` rows per block; this run prints 40, which
covers every "confined to one class" block in full (the largest is dysuria's 34)
and every row above roughly 0.09 skew in the others. The counts on the block
headings are the true totals either way.

## What this report is

`arch_training.md` section 8 lists two faults the lint could not see, and records
that the first of them reached the libraries: "dysuria" once appeared on 16 lines
of `dysuria_null_metaphor` and nowhere else in the six dysuria libraries, a
perfect shortcut separating `null` from `true` and `false`. It was found by hand.
This report is the mechanical check for that fault, and for the weaker
frequency-skew form of it.

For each signal, every library is grouped into one of three label classes by
`fragment_type` — `positive → true`, `negative → false`, everything else →
`null` — and each token's **per-line rate** is counted in each class. Tokens are
ranked by **skew**: the highest of the three rates minus the lowest, over tokens
on at least five lines of the signal. Two blocks are printed per signal and they
are different faults: tokens **confined to one label class**, and tokens
**present in more than one class but skewed**.

## What this report is not

Four things, restated here because the summary below is short and a short list is
easy to read as a clean bill of health:

1. **It is per-token, so it is blind to style and register.** Section 8's second
   recorded fault — the first draft of `haematuria_null_hedged` written entirely
   in lowercase with no terminal punctuation against uniformly capitalised
   siblings — would not appear anywhere in this file.
2. **Skew *within* the `null` class is not in the ranking.** `null` is up to five
   libraries. A token the historical library leans on and the metaphor one never
   uses has a modest three-class skew and a large one across the sub-classes.
   This is not a footnote: it is where the largest real finding below lives. The
   per-library breakdown printed under every row is what makes it readable.
3. **Function words dominate the ranking by construction.** A rate near 0.5 has
   the most room to move, so `was`, `but`, `a` and `the` sit at the top of most
   blocks. That is the tense and register difference between the classes. It is
   real, and it is not something a vocabulary rule can swap.
4. **A null sub-class's axis word is supposed to be confined to it.** `she` and
   `he` in third-party, `ago` in historical, `might` in hedged. No filter is
   applied, because deciding which confined token is a fault and which is the
   sub-class doing its job is a clinical judgement and does not belong in code.

Filler libraries carry no `signal_key` and are in no signal's grouping.
Generated libraries are excluded too: their lines state their labels one at a
time rather than by `fragment_type`, so there is no class to group them into.

## Summary, by the statistic the plan committed to

| signal | tokens ≥5 lines | confined to one class | top token | skew |
|---|---|---|---|---|
| `haematuria_present` | 105 | 20 | `no` | 0.467 |
| `flank_pain_present` | 130 | 13 | `side` | 0.459 |
| `recent_uti_present` | 126 | 17 | `ago` | 0.455 |
| `dysuria_present` | 139 | 34 | `no` | 0.447 |
| `fever_present` | 265 | 10 | `was` | 0.406 |
| `nocturia_present` | 178 | 19 | `not` | 0.315 |
| `urinary_frequency_present` | 146 | 20 | `i'm` | 0.293 |

**On the plan's statistic, `haematuria_present` ranks top, at 0.467 on `no`.**

**That answer does not survive contact with what the pass is allowed to do, and
saying so is the point of running the gate before building anything.** Every
top-ranked token in that table is one no Tier A or Tier B rule may touch:

* `no` and `not` are negation. DD6 layer 2 freezes them — a rule whose
  `STRUCTURAL_FROZEN` sequence changes fails at load. A `false` library uses `no`
  on 45% of its lines because that is what negating a symptom is.
* `ago` is the historical axis word, `side` is the flank-pain anatomy word, `was`
  is tense, `i'm` is person and tense.

So the ranking answers "which signal's label is most readable off a single
token", and the answer is dominated by tokens whose association with the label
*is* the label. Two narrower readings answer the question the ticket actually
asks, which is where **swappable** vocabulary is doing the separating.

### Reading A — dropping the tokens DD6 layer 2 freezes

| signal | top unfrozen token | skew |
|---|---|---|
| `flank_pain_present` | `side` | 0.459 |
| `recent_uti_present` | `a` | 0.414 |
| `dysuria_present` | `a` | 0.381 |
| `haematuria_present` | `a` | 0.356 |
| `fever_present` | `but` | 0.342 |
| `nocturia_present` | `up` | 0.263 |
| `urinary_frequency_present` | `to` | 0.217 |

Still function words, mostly. This reading moves the ranking around and settles
nothing.

### Reading B — skew *within* the `null` sub-classes

This is caveat (2) above, computed from the same per-library counts the report
body prints. It is the fault the plan's review measured, and the three-class
statistic cannot see it. Ignoring pronouns and function words, the largest
content-word within-null skews are:

| signal | token | within-null skew | per-library |
|---|---|---|---|
| `fever_present` | `fever` | **0.911** | attribution 0/50, hedged 10/73, historical 41/45, metaphor 5/55, thirdparty 36/46 |
| `urinary_frequency_present` | `more` | 0.595 | adjacent 0/40, hedged 25/42, historical 4/40, metaphor 0/44, thirdparty 14/44 |
| `nocturia_present` | `up` | 0.508 | attribution 27/51, hedged 14/47, historical 1/46, metaphor 14/52, thirdparty 6/47 |
| `haematuria_present` | `blood` | 0.489 | hedged 7/45, historical 24/45, thirdparty 29/45 |
| `flank_pain_present` | `pain` | 0.467 | hedged 11/53, historical 27/40, thirdparty 11/47 |

`fever` on 91% of `null_historical` lines and 0% of `null_attribution` ones is
the single largest content-word association in the tree, and it is on the
signal's own name — exactly the vocabulary a Tier B rule exists to swap.

### The fever vocabulary, since it is the case the plan was written around

| token | true (96) | false (98) | hedged (73) | metaphor (55) | thirdparty (46) | historical (45) | attribution (50) | 3-class skew |
|---|---|---|---|---|---|---|---|---|
| `fever` | 17 | 27 | 10 | 5 | 36 | 41 | 0 | 0.165 |
| `temperature` | 22 | 20 | 7 | 1 | 7 | **0** | 0 | 0.173 |
| `hot` | 32 | 23 | 13 | 12 | 0 | 0 | 16 | 0.181 |
| `warm` | 10 | 2 | 17 | 1 | 0 | 0 | 4 | 0.084 |
| `feverish` | 3 | 4 | 4 | 2 | 1 | 1 | 0 | 0.011 |

This reproduces the review's table within a line or two per cell (the small
differences are tokenisation: this report folds edge punctuation and counts
`fevers` separately). The shape the review described is confirmed: **no fever
token is confined to one label class** — the exclusive-token fault is not present
here — while `temperature` is on 21% of decisive lines and no historical line at
all, and `fever` is on 91% of historical lines. A head can learn "temperature ⇒
decisive, fever ⇒ displaced" from that as easily as from a token that lives in
one file.

## Gate 1: does this show enough skew to justify Task 2?

**Yes, and the plan's own reasoning survives.** Not on the headline statistic,
which is dominated by negation, tense and anatomy, but on the within-null
reading, where the largest association in the tree is a signal's own name split
0.911 between two of its own `null` sub-classes.

Two things this does **not** establish, and Task 2 exists because of both:

* That the skew is *learnable*. A measured association in the data is not
  evidence that a trained head uses it. Task 2's paraphrase-flip diagnostic is
  what tests that, and it is allowed to come back negative.
* That expansion is the right fix. Rewriting `fever_null_historical` so that it
  does not use "fever" on 41 of its 45 lines is a library edit, not a
  post-processing pass, and it costs nothing downstream. It is the cheaper answer
  if the flip rate is low.

## Recommended pilot signal (DD10)

**`fever_present`**, which is what the provisional plan assumed and what Task 5
is written against.

DD10 says the pilot is "the top-ranked signal". Read literally against the
statistic the plan specifies, that is `haematuria_present`, whose top token is
the frozen negation word `no` — a signal chosen on a token no rule may rewrite.
Read against the fault the ticket exists to remove, it is `fever_present`, which
carries the largest content-word association in the tree on the one word Tier B
is built to swap. **This is a deviation from a literal reading of DD10 and is
recorded as one rather than papered over.** If the literal reading is preferred,
Task 5's argument changes and nothing else does.

## Full report

Everything below is the tool's output, unedited.

```
  For each signal, every library is grouped into one of three label classes by fragment_type --
  positive->true, negative->false, everything else->null -- and each token's *per-line rate* is
  counted in each class: lines containing the token over lines in the class. Rates, not counts:
  the three classes are different sizes and raw counts mislead. Tokens are ranked by 'skew': the
  highest of the three rates minus the lowest, taken over tokens on at least 5 lines of the
  signal. A token whose skew is large is one a head can read the label off, whatever the
  sentence around it says.
  Four things this report cannot see or does not rank, none of which is a reason to read a short
  list here as a clean bill of health:
  (1) It is per-token, so it is blind to multi-token style and register. Section 8's second
  recorded fault -- one library written entirely in lowercase with no terminal punctuation
  against uniformly capitalised siblings -- would not appear here at all.
  (2) Skew *within* the null class is not in the ranking. null is five libraries for some
  signals, and a token used by the historical library and not the metaphor one has a modest
  three-class skew and a large one across the sub-classes. That is what the per-library
  breakdown on each row is for; read it, do not trust the rank alone.
  (3) High-frequency function words dominate the ranking by construction, because a rate near
  0.5 has the most room to move. 'was', 'but', 'a' and 'the' at the top of a block are the tense
  and register difference between the classes, which is real but is not a vocabulary swap anyone
  can make.
  (4) The axis word of a null sub-class is *supposed* to be confined to it -- 'she' and 'he' in
  third-party, 'ago' in historical, 'might' in hedged. Expect them at the top of the first
  block. No filter is applied, because deciding which confined token is a fault and which is the
  sub-class doing its job is a clinical judgement and does not belong in code.
  Filler libraries carry no signal_key and so are in no signal's grouping. Generated libraries
  are excluded too: their lines state their labels one at a time rather than by fragment_type,
  so there is no class to group them into.

  dysuria_present: 139 tokens on 5+ lines (true 45, false 47, null 164 lines)
    confined to one label class: 34
      token                skew  lines    true   false    null
      urination           0.128      6   0.000   0.128   0.000
        dysuria_false 6/47
      she                 0.110     18   0.000   0.000   0.110
        dysuria_null_thirdparty 18/46
      he                  0.098     16   0.000   0.000   0.098
        dysuria_null_thirdparty 16/46
      something           0.085     14   0.000   0.000   0.085
        dysuria_null_hedged 9/40  dysuria_null_historical 2/38  dysuria_null_metaphor 2/40
        dysuria_null_thirdparty 1/46
      wees                0.085     14   0.000   0.000   0.085
        dysuria_null_thirdparty 14/46
      has                 0.073     12   0.000   0.000   0.073
        dysuria_null_metaphor 7/40  dysuria_null_thirdparty 5/46
      stung               0.073     12   0.000   0.000   0.073
        dysuria_null_historical 8/38  dysuria_null_metaphor 4/40
      out                 0.067     11   0.000   0.000   0.067
        dysuria_null_hedged 2/40  dysuria_null_historical 4/38  dysuria_null_metaphor 3/40
        dysuria_null_thirdparty 2/46
      weed                0.067     11   0.000   0.000   0.067
        dysuria_null_historical 9/38  dysuria_null_thirdparty 2/46
      her                 0.061     10   0.000   0.000   0.061
        dysuria_null_hedged 1/40  dysuria_null_metaphor 1/40  dysuria_null_thirdparty 8/46
      ago                 0.055      9   0.000   0.000   0.055
        dysuria_null_historical 9/38
      whether             0.055      9   0.000   0.000   0.055
        dysuria_null_hedged 8/40  dysuria_null_metaphor 1/40
      back                0.049      8   0.000   0.000   0.049
        dysuria_null_historical 5/38  dysuria_null_metaphor 2/40  dysuria_null_thirdparty 1/46
      from                0.049      8   0.000   0.000   0.049
        dysuria_null_hedged 1/40  dysuria_null_historical 2/38  dysuria_null_metaphor 2/40
        dysuria_null_thirdparty 3/46
      might               0.049      8   0.000   0.000   0.049
        dysuria_null_hedged 8/40
      say                 0.049      8   0.000   0.000   0.049
        dysuria_null_hedged 3/40  dysuria_null_thirdparty 5/46
      burned              0.043      7   0.000   0.000   0.043
        dysuria_null_historical 4/38  dysuria_null_metaphor 3/40
      sure                0.043      7   0.000   0.000   0.043
        dysuria_null_hedged 6/40  dysuria_null_thirdparty 1/46
      they                0.043      7   0.000   0.000   0.043
        dysuria_null_historical 4/38  dysuria_null_metaphor 3/40
      work                0.043      7   0.000   0.000   0.043
        dysuria_null_hedged 1/40  dysuria_null_metaphor 4/40  dysuria_null_thirdparty 2/46
      actually            0.037      6   0.000   0.000   0.037
        dysuria_null_hedged 6/40
      his                 0.037      6   0.000   0.000   0.037
        dysuria_null_metaphor 2/40  dysuria_null_thirdparty 4/46
      says                0.037      6   0.000   0.000   0.037
        dysuria_null_thirdparty 6/46
      tell                0.037      6   0.000   0.000   0.037
        dysuria_null_hedged 6/40
      went                0.037      6   0.000   0.000   0.037
        dysuria_null_hedged 1/40  dysuria_null_historical 3/38  dysuria_null_metaphor 2/40
      before              0.030      5   0.000   0.000   0.030
        dysuria_null_hedged 2/40  dysuria_null_historical 3/38
      bit                 0.030      5   0.000   0.000   0.030
        dysuria_null_hedged 4/40  dysuria_null_metaphor 1/40
      hard                0.030      5   0.000   0.000   0.030
        dysuria_null_hedged 5/40
      she's               0.030      5   0.000   0.000   0.030
        dysuria_null_thirdparty 5/46
      we                  0.030      5   0.000   0.000   0.030
        dysuria_null_historical 1/38  dysuria_null_metaphor 1/40  dysuria_null_thirdparty 3/46
      week                0.030      5   0.000   0.000   0.030
        dysuria_null_hedged 1/40  dysuria_null_historical 2/38  dysuria_null_metaphor 1/40
        dysuria_null_thirdparty 1/46
      were                0.030      5   0.000   0.000   0.030
        dysuria_null_historical 1/38  dysuria_null_metaphor 4/40
      what                0.030      5   0.000   0.000   0.030
        dysuria_null_hedged 2/40  dysuria_null_metaphor 1/40  dysuria_null_thirdparty 2/46
      years               0.030      5   0.000   0.000   0.030
        dysuria_null_historical 5/38
    present in more than one label class but skewed: 105
      token                skew  lines    true   false    null
      no                  0.447     23   0.000   0.447   0.012
        dysuria_false 21/47  dysuria_null_hedged 1/40  dysuria_null_thirdparty 1/46
      a                   0.381     77   0.444   0.064   0.329
        dysuria_false 3/47  dysuria_null_hedged 16/40  dysuria_null_historical 18/38
        dysuria_null_metaphor 12/40  dysuria_null_thirdparty 8/46  dysuria_true 20/45
      my                  0.297     80   0.111   0.170   0.409
        dysuria_false 8/47  dysuria_null_hedged 2/40  dysuria_null_historical 13/38
        dysuria_null_metaphor 17/40  dysuria_null_thirdparty 35/46  dysuria_true 5/45
      pain                0.243     34   0.244   0.298   0.055
        dysuria_false 14/47  dysuria_null_hedged 5/40  dysuria_null_thirdparty 4/46
        dysuria_true 11/45
      or                  0.234     22   0.000   0.234   0.067
        dysuria_false 11/47  dysuria_null_hedged 11/40
      i                   0.219    131   0.689   0.489   0.470
        dysuria_false 23/47  dysuria_null_hedged 34/40  dysuria_null_historical 24/38
        dysuria_null_metaphor 12/40  dysuria_null_thirdparty 7/46  dysuria_true 31/45
      and                 0.217     70   0.267   0.106   0.323
        dysuria_false 5/47  dysuria_null_hedged 5/40  dysuria_null_historical 10/38
        dysuria_null_metaphor 15/40  dysuria_null_thirdparty 23/46  dysuria_true 12/45
      any                 0.213     11   0.000   0.213   0.006
        dysuria_false 10/47  dysuria_null_hedged 1/40
      it                  0.196     73   0.311   0.128   0.323
        dysuria_false 6/47  dysuria_null_hedged 15/40  dysuria_null_historical 20/38
        dysuria_null_metaphor 5/40  dysuria_null_thirdparty 13/46  dysuria_true 14/45
      the                 0.188     92   0.422   0.234   0.378
        dysuria_false 11/47  dysuria_null_hedged 15/40  dysuria_null_historical 16/38
        dysuria_null_metaphor 24/40  dysuria_null_thirdparty 7/46  dysuria_true 19/45
      all                 0.170     16   0.000   0.170   0.049
        dysuria_false 8/47  dysuria_null_hedged 4/40  dysuria_null_historical 2/38
        dysuria_null_metaphor 1/40  dysuria_null_thirdparty 1/46
      when                0.163    111   0.378   0.319   0.482
        dysuria_false 15/47  dysuria_null_hedged 31/40  dysuria_null_historical 14/38
        dysuria_null_metaphor 4/40  dysuria_null_thirdparty 30/46  dysuria_true 17/45
      been                0.156     25   0.156   0.000   0.110
        dysuria_null_hedged 3/40  dysuria_null_metaphor 10/40  dysuria_null_thirdparty 5/46
        dysuria_true 7/45
      i've                0.149     26   0.222   0.085   0.073
        dysuria_false 4/47  dysuria_null_hedged 5/40  dysuria_null_historical 1/38
        dysuria_null_metaphor 5/40  dysuria_null_thirdparty 1/46  dysuria_true 10/45
      it's                0.139     41   0.267   0.128   0.140
        dysuria_false 6/47  dysuria_null_hedged 17/40  dysuria_null_metaphor 3/40
        dysuria_null_thirdparty 3/46  dysuria_true 12/45
      for                 0.136     44   0.200   0.064   0.195
        dysuria_false 3/47  dysuria_null_hedged 5/40  dysuria_null_historical 10/38
        dysuria_null_metaphor 9/40  dysuria_null_thirdparty 8/46  dysuria_true 9/45
      time                0.134     15   0.156   0.021   0.043
        dysuria_false 1/47  dysuria_null_hedged 2/40  dysuria_null_historical 3/38
        dysuria_null_metaphor 1/40  dysuria_null_thirdparty 1/46  dysuria_true 7/45
      every               0.133      8   0.133   0.000   0.012
        dysuria_null_metaphor 1/40  dysuria_null_thirdparty 1/46  dysuria_true 6/45
      had                 0.131     28   0.044   0.021   0.152
        dysuria_false 1/47  dysuria_null_hedged 2/40  dysuria_null_historical 12/38
        dysuria_null_metaphor 3/40  dysuria_null_thirdparty 8/46  dysuria_true 2/45
      was                 0.128     22   0.000   0.021   0.128
        dysuria_false 1/47  dysuria_null_hedged 5/40  dysuria_null_historical 10/38
        dysuria_null_metaphor 3/40  dysuria_null_thirdparty 3/46
      completely          0.128      7   0.000   0.128   0.006
        dysuria_false 6/47  dysuria_null_hedged 1/40
      normal              0.128     10   0.000   0.128   0.024
        dysuria_false 6/47  dysuria_null_hedged 4/40
      not                 0.127     17   0.022   0.149   0.055
        dysuria_false 7/47  dysuria_null_hedged 7/40  dysuria_null_metaphor 2/40  dysuria_true
        1/45
      stinging            0.126     36   0.044   0.128   0.171
        dysuria_false 6/47  dysuria_null_hedged 6/40  dysuria_null_historical 6/38
        dysuria_null_metaphor 5/40  dysuria_null_thirdparty 11/46  dysuria_true 2/45
      in                  0.119     28   0.089   0.021   0.140
        dysuria_false 1/47  dysuria_null_hedged 2/40  dysuria_null_historical 8/38
        dysuria_null_metaphor 9/40  dysuria_null_thirdparty 4/46  dysuria_true 4/45
      passing             0.117     25   0.178   0.149   0.061
        dysuria_false 7/47  dysuria_null_hedged 3/40  dysuria_null_historical 3/38
        dysuria_null_thirdparty 4/46  dysuria_true 8/45
      weeing              0.114     37   0.178   0.064   0.159
        dysuria_false 3/47  dysuria_null_hedged 6/40  dysuria_null_historical 13/38
        dysuria_null_thirdparty 7/46  dysuria_true 8/45
      urine               0.112     36   0.222   0.170   0.110
        dysuria_false 8/47  dysuria_null_hedged 9/40  dysuria_null_historical 1/38
        dysuria_null_thirdparty 8/46  dysuria_true 10/45
      sharp               0.111      6   0.111   0.000   0.006
        dysuria_null_historical 1/38  dysuria_true 5/45
      to                  0.110     62   0.178   0.170   0.280
        dysuria_false 8/47  dysuria_null_hedged 13/40  dysuria_null_historical 13/38
        dysuria_null_metaphor 9/40  dysuria_null_thirdparty 11/46  dysuria_true 8/45
      got                 0.110     19   0.000   0.021   0.110
        dysuria_false 1/47  dysuria_null_historical 3/38  dysuria_null_metaphor 10/40
        dysuria_null_thirdparty 5/46
      i'm                 0.107     35   0.089   0.064   0.171
        dysuria_false 3/47  dysuria_null_hedged 14/40  dysuria_null_metaphor 4/40
        dysuria_null_thirdparty 10/46  dysuria_true 4/45
      go                  0.107     19   0.156   0.085   0.049
        dysuria_false 4/47  dysuria_null_hedged 7/40  dysuria_null_metaphor 1/40  dysuria_true
        7/45
      there's             0.106     18   0.089   0.149   0.043
        dysuria_false 7/47  dysuria_null_hedged 6/40  dysuria_null_metaphor 1/40  dysuria_true
        4/45
      pass                0.101     19   0.156   0.064   0.055
        dysuria_false 3/47  dysuria_null_hedged 7/40  dysuria_null_historical 1/38
        dysuria_null_thirdparty 1/46  dysuria_true 7/45
      doesn't             0.100      8   0.044   0.106   0.006
        dysuria_false 5/47  dysuria_null_hedged 1/40  dysuria_true 2/45
      without             0.100      7   0.022   0.106   0.006
        dysuria_false 5/47  dysuria_null_hedged 1/40  dysuria_true 1/45
      is                  0.097     38   0.200   0.213   0.116
        dysuria_false 10/47  dysuria_null_hedged 6/40  dysuria_null_historical 1/38
        dysuria_null_metaphor 2/40  dysuria_null_thirdparty 10/46  dysuria_true 9/45
      me                  0.096     31   0.044   0.128   0.140
        dysuria_false 6/47  dysuria_null_hedged 4/40  dysuria_null_historical 3/38
        dysuria_null_metaphor 11/40  dysuria_null_thirdparty 5/46  dysuria_true 2/45
      going               0.093     10   0.111   0.043   0.018
        dysuria_false 2/47  dysuria_null_metaphor 3/40  dysuria_true 5/45
      ... and 65 more, counted above but not shown

  fever_present: 265 tokens on 5+ lines (true 96, false 98, null 269 lines)
    confined to one label class: 10
      token                skew  lines    true   false    null
      thought             0.062      6   0.062   0.000   0.000
        fever_true 6/96
      kept                0.052      5   0.052   0.000   0.000
        fever_true 5/96
      cant                0.045     12   0.000   0.000   0.045
        fever_null_hedged 12/73
      every               0.033      9   0.000   0.000   0.033
        fever_null_attribution 2/50  fever_null_hedged 1/73  fever_null_historical 2/45
        fever_null_metaphor 4/55
      who                 0.026      7   0.000   0.000   0.026
        fever_null_attribution 1/50  fever_null_hedged 2/73  fever_null_thirdparty 4/46
      mentioned           0.022      6   0.000   0.000   0.022
        fever_null_metaphor 1/55  fever_null_thirdparty 5/46
      months              0.022      6   0.000   0.000   0.022
        fever_null_attribution 1/50  fever_null_historical 4/45  fever_null_metaphor 1/55
      only                0.019      5   0.000   0.000   0.019
        fever_null_hedged 1/73  fever_null_historical 2/45  fever_null_metaphor 1/55
        fever_null_thirdparty 1/46
      our                 0.019      5   0.000   0.000   0.019
        fever_null_attribution 1/50  fever_null_metaphor 3/55  fever_null_thirdparty 1/46
      working             0.019      5   0.000   0.000   0.019
        fever_null_attribution 1/50  fever_null_historical 1/45  fever_null_metaphor 3/55
    present in more than one label class but skewed: 255
      token                skew  lines    true   false    null
      was                 0.406     92   0.510   0.153   0.104
        fever_false 15/98  fever_null_attribution 6/50  fever_null_hedged 4/73
        fever_null_historical 12/45  fever_null_metaphor 4/55  fever_null_thirdparty 2/46
        fever_true 49/96
      but                 0.342    129   0.312   0.520   0.178
        fever_false 51/98  fever_null_attribution 1/50  fever_null_hedged 43/73
        fever_null_historical 1/45  fever_null_metaphor 1/55  fever_null_thirdparty 2/46
        fever_true 30/96
      i                   0.294    289   0.833   0.653   0.539
        fever_false 64/98  fever_null_attribution 28/50  fever_null_hedged 49/73
        fever_null_historical 42/45  fever_null_metaphor 17/55  fever_null_thirdparty 9/46
        fever_true 80/96
      with                0.223     87   0.073   0.296   0.190
        fever_false 29/98  fever_null_attribution 9/50  fever_null_hedged 3/73
        fever_null_historical 11/45  fever_null_metaphor 8/55  fever_null_thirdparty 20/46
        fever_true 7/96
      felt                0.220     49   0.250   0.173   0.030
        fever_false 17/98  fever_null_hedged 8/73  fever_true 24/96
      normal              0.198     32   0.031   0.224   0.026
        fever_false 22/98  fever_null_attribution 3/50  fever_null_hedged 4/73  fever_true 3/96
      at                  0.193     56   0.031   0.224   0.115
        fever_false 22/98  fever_null_attribution 7/50  fever_null_hedged 3/73
        fever_null_historical 2/45  fever_null_metaphor 7/55  fever_null_thirdparty 12/46
        fever_true 3/96
      that                0.192     64   0.083   0.276   0.108
        fever_false 27/98  fever_null_attribution 4/50  fever_null_hedged 6/73
        fever_null_historical 12/45  fever_null_metaphor 7/55  fever_true 8/96
      to                  0.190     91   0.292   0.102   0.197
        fever_false 10/98  fever_null_attribution 5/50  fever_null_hedged 15/73
        fever_null_historical 7/45  fever_null_metaphor 15/55  fever_null_thirdparty 11/46
        fever_true 28/96
      a                   0.188    258   0.448   0.449   0.636
        fever_false 44/98  fever_null_attribution 22/50  fever_null_hedged 38/73
        fever_null_historical 43/45  fever_null_metaphor 22/55  fever_null_thirdparty 46/46
        fever_true 43/96
      the                 0.183    202   0.323   0.357   0.506
        fever_false 35/98  fever_null_attribution 38/50  fever_null_hedged 33/73
        fever_null_historical 10/45  fever_null_metaphor 34/55  fever_null_thirdparty 21/46
        fever_true 31/96
      hot                 0.181     96   0.333   0.235   0.152
        fever_false 23/98  fever_null_attribution 16/50  fever_null_hedged 13/73
        fever_null_metaphor 12/55  fever_true 32/96
      just                0.178     60   0.240   0.061   0.115
        fever_false 6/98  fever_null_attribution 4/50  fever_null_hedged 25/73
        fever_null_metaphor 1/55  fever_null_thirdparty 1/46  fever_true 23/96
      it                  0.175     82   0.312   0.153   0.138
        fever_false 15/98  fever_null_attribution 9/50  fever_null_hedged 15/73
        fever_null_historical 6/45  fever_null_metaphor 6/55  fever_null_thirdparty 1/46
        fever_true 30/96
      temperature         0.173     57   0.229   0.204   0.056
        fever_false 20/98  fever_null_hedged 7/73  fever_null_metaphor 1/55
        fever_null_thirdparty 7/46  fever_true 22/96
      fever               0.165    136   0.177   0.276   0.342
        fever_false 27/98  fever_null_hedged 10/73  fever_null_historical 41/45
        fever_null_metaphor 5/55  fever_null_thirdparty 36/46  fever_true 17/96
      like                0.164     40   0.135   0.194   0.030
        fever_false 19/98  fever_null_attribution 3/50  fever_null_hedged 2/73
        fever_null_metaphor 3/55  fever_true 13/96
      temp                0.153     21   0.010   0.163   0.015
        fever_false 16/98  fever_null_hedged 4/73  fever_true 1/96
      in                  0.136     58   0.031   0.102   0.167
        fever_false 10/98  fever_null_attribution 14/50  fever_null_hedged 7/73
        fever_null_historical 9/45  fever_null_metaphor 11/55  fever_null_thirdparty 4/46
        fever_true 3/96
      haven't             0.135     17   0.010   0.143   0.007
        fever_false 14/98  fever_null_hedged 2/73  fever_true 1/96
      if                  0.135     46   0.010   0.061   0.145
        fever_false 6/98  fever_null_attribution 1/50  fever_null_hedged 28/73
        fever_null_historical 2/45  fever_null_metaphor 2/55  fever_null_thirdparty 6/46
        fever_true 1/96
      about               0.134     40   0.042   0.000   0.134
        fever_null_attribution 5/50  fever_null_hedged 3/73  fever_null_historical 7/45
        fever_null_metaphor 19/55  fever_null_thirdparty 2/46  fever_true 4/96
      time                0.133     30   0.000   0.133   0.063
        fever_false 13/98  fever_null_attribution 3/50  fever_null_hedged 1/73
        fever_null_historical 5/45  fever_null_metaphor 7/55  fever_null_thirdparty 1/46
      up                  0.127     66   0.219   0.092   0.134
        fever_false 9/98  fever_null_attribution 8/50  fever_null_hedged 11/73
        fever_null_historical 2/45  fever_null_metaphor 12/55  fever_null_thirdparty 3/46
        fever_true 21/96
      fine                0.115     15   0.010   0.122   0.007
        fever_false 12/98  fever_null_hedged 2/73  fever_true 1/96
      had                 0.112    111   0.312   0.276   0.201
        fever_false 27/98  fever_null_attribution 4/50  fever_null_hedged 5/73
        fever_null_historical 24/45  fever_null_metaphor 3/55  fever_null_thirdparty 18/46
        fever_true 30/96
      no                  0.102     20   0.010   0.112   0.030
        fever_false 11/98  fever_null_attribution 1/50  fever_null_hedged 5/73
        fever_null_metaphor 2/55  fever_true 1/96
      so                  0.101     85   0.115   0.163   0.216
        fever_false 16/98  fever_null_attribution 13/50  fever_null_hedged 36/73
        fever_null_historical 1/45  fever_null_metaphor 6/55  fever_null_thirdparty 2/46
        fever_true 11/96
      for                 0.098     56   0.115   0.051   0.149
        fever_false 5/98  fever_null_attribution 11/50  fever_null_hedged 7/73
        fever_null_historical 7/45  fever_null_metaphor 9/55  fever_null_thirdparty 6/46
        fever_true 11/96
      need                0.097     13   0.104   0.010   0.007
        fever_false 1/98  fever_null_thirdparty 2/46  fever_true 10/96
      completely          0.092     12   0.000   0.092   0.011
        fever_false 9/98  fever_null_attribution 1/50  fever_null_hedged 1/73
        fever_null_metaphor 1/55
      have                0.091     46   0.052   0.143   0.100
        fever_false 14/98  fever_null_attribution 5/50  fever_null_hedged 13/73
        fever_null_historical 1/45  fever_null_metaphor 5/55  fever_null_thirdparty 3/46
        fever_true 5/96
      of                  0.091     55   0.062   0.153   0.126
        fever_false 15/98  fever_null_attribution 9/50  fever_null_hedged 7/73
        fever_null_historical 6/45  fever_null_metaphor 6/55  fever_null_thirdparty 6/46
        fever_true 6/96
      has                 0.089     32   0.000   0.082   0.089
        fever_false 8/98  fever_null_attribution 3/50  fever_null_hedged 1/73
        fever_null_metaphor 5/55  fever_null_thirdparty 15/46
      this                0.086     45   0.125   0.153   0.067
        fever_false 15/98  fever_null_attribution 2/50  fever_null_hedged 4/73
        fever_null_historical 2/45  fever_null_metaphor 8/55  fever_null_thirdparty 2/46
        fever_true 12/96
      warm                0.084     34   0.104   0.020   0.082
        fever_false 2/98  fever_null_attribution 4/50  fever_null_hedged 17/73
        fever_null_metaphor 1/55  fever_true 10/96
      since               0.084     28   0.094   0.010   0.067
        fever_false 1/98  fever_null_attribution 6/50  fever_null_historical 2/45
        fever_null_metaphor 6/55  fever_null_thirdparty 4/46  fever_true 9/96
      actually            0.083     18   0.083   0.000   0.037
        fever_null_hedged 8/73  fever_null_metaphor 2/55  fever_true 8/96
      and                 0.083    182   0.458   0.378   0.375
        fever_false 37/98  fever_null_attribution 33/50  fever_null_hedged 19/73
        fever_null_historical 7/45  fever_null_metaphor 23/55  fever_null_thirdparty 19/46
        fever_true 44/96
      all                 0.082     44   0.104   0.153   0.071
        fever_false 15/98  fever_null_attribution 5/50  fever_null_hedged 3/73
        fever_null_historical 3/45  fever_null_metaphor 7/55  fever_null_thirdparty 1/46
        fever_true 10/96
      ... and 215 more, counted above but not shown

  flank_pain_present: 130 tokens on 5+ lines (true 48, false 55, null 140 lines)
    confined to one label class: 13
      token                skew  lines    true   false    null
      fine                0.182     10   0.000   0.182   0.000
        flank_pain_false 10/55
      after               0.093     13   0.000   0.000   0.093
        flank_pain_null_hedged 1/53  flank_pain_null_historical 12/40
      ago                 0.086     12   0.000   0.000   0.086
        flank_pain_null_hedged 1/53  flank_pain_null_historical 11/40
      say                 0.064      9   0.000   0.000   0.064
        flank_pain_null_hedged 6/53  flank_pain_null_thirdparty 3/47
      whether             0.064      9   0.000   0.000   0.064
        flank_pain_null_hedged 9/53
      says                0.057      8   0.000   0.000   0.057
        flank_pain_null_hedged 2/53  flank_pain_null_thirdparty 6/47
      couldnt             0.043      6   0.000   0.000   0.043
        flank_pain_null_hedged 6/53
      he                  0.043      6   0.000   0.000   0.043
        flank_pain_null_thirdparty 6/47
      severe              0.043      6   0.000   0.000   0.043
        flank_pain_null_historical 6/40
      infection           0.036      5   0.000   0.000   0.036
        flank_pain_null_historical 5/40
      loin                0.036      5   0.000   0.000   0.036
        flank_pain_null_historical 5/40
      might               0.036      5   0.000   0.000   0.036
        flank_pain_null_hedged 5/53
      son                 0.036      5   0.000   0.000   0.036
        flank_pain_null_historical 1/40  flank_pain_null_thirdparty 4/47
    present in more than one label class but skewed: 117
      token                skew  lines    true   false    null
      side                0.459     86   0.604   0.145   0.350
        flank_pain_false 8/55  flank_pain_null_hedged 14/53  flank_pain_null_historical 17/40
        flank_pain_null_thirdparty 18/47  flank_pain_true 29/48
      the                 0.383     77   0.583   0.200   0.271
        flank_pain_false 11/55  flank_pain_null_hedged 11/53  flank_pain_null_historical 8/40
        flank_pain_null_thirdparty 19/47  flank_pain_true 28/48
      i                   0.348    102   0.167   0.400   0.514
        flank_pain_false 22/55  flank_pain_null_hedged 31/53  flank_pain_null_historical 38/40
        flank_pain_null_thirdparty 3/47  flank_pain_true 8/48
      sides               0.322     31   0.042   0.364   0.064
        flank_pain_false 20/55  flank_pain_null_hedged 4/53  flank_pain_null_historical 1/40
        flank_pain_null_thirdparty 4/47  flank_pain_true 2/48
      right               0.315     30   0.333   0.018   0.093
        flank_pain_false 1/55  flank_pain_null_hedged 3/53  flank_pain_null_historical 7/40
        flank_pain_null_thirdparty 3/47  flank_pain_true 16/48
      no                  0.309     20   0.000   0.309   0.021
        flank_pain_false 17/55  flank_pain_null_hedged 2/53  flank_pain_null_thirdparty 1/47
      on                  0.281     47   0.417   0.145   0.136
        flank_pain_false 8/55  flank_pain_null_hedged 6/53  flank_pain_null_historical 3/40
        flank_pain_null_thirdparty 10/47  flank_pain_true 20/48
      left                0.250     22   0.250   0.000   0.071
        flank_pain_null_hedged 2/53  flank_pain_null_historical 5/40  flank_pain_null_thirdparty
        3/47  flank_pain_true 12/48
      a                   0.248     72   0.333   0.109   0.357
        flank_pain_false 6/55  flank_pain_null_hedged 20/53  flank_pain_null_historical 23/40
        flank_pain_null_thirdparty 7/47  flank_pain_true 16/48
      had                 0.217     53   0.083   0.127   0.300
        flank_pain_false 7/55  flank_pain_null_hedged 2/53  flank_pain_null_historical 28/40
        flank_pain_null_thirdparty 12/47  flank_pain_true 4/48
      or                  0.216     25   0.021   0.236   0.079
        flank_pain_false 13/55  flank_pain_null_hedged 10/53  flank_pain_null_historical 1/40
        flank_pain_true 1/48
      in                  0.212    109   0.521   0.309   0.479
        flank_pain_false 17/55  flank_pain_null_hedged 14/53  flank_pain_null_historical 29/40
        flank_pain_null_thirdparty 24/47  flank_pain_true 25/48
      nothing             0.200     16   0.000   0.200   0.036
        flank_pain_false 11/55  flank_pain_null_hedged 3/53  flank_pain_null_thirdparty 2/47
      her                 0.164     26   0.000   0.055   0.164
        flank_pain_false 3/55  flank_pain_null_thirdparty 23/47
      to                  0.160     40   0.146   0.055   0.214
        flank_pain_false 3/55  flank_pain_null_hedged 9/53  flank_pain_null_historical 7/40
        flank_pain_null_thirdparty 14/47  flank_pain_true 7/48
      my                  0.158    213   0.979   0.927   0.821
        flank_pain_false 51/55  flank_pain_null_hedged 42/53  flank_pain_null_historical 30/40
        flank_pain_null_thirdparty 43/47  flank_pain_true 47/48
      back                0.156    101   0.417   0.527   0.371
        flank_pain_false 29/55  flank_pain_null_hedged 18/53  flank_pain_null_historical 12/40
        flank_pain_null_thirdparty 22/47  flank_pain_true 20/48
      and                 0.151     78   0.292   0.436   0.286
        flank_pain_false 24/55  flank_pain_null_hedged 13/53  flank_pain_null_historical 2/40
        flank_pain_null_thirdparty 25/47  flank_pain_true 14/48
      its                 0.148     17   0.167   0.018   0.057
        flank_pain_false 1/55  flank_pain_null_hedged 7/53  flank_pain_null_thirdparty 1/47
        flank_pain_true 8/48
      under               0.146     17   0.146   0.000   0.071
        flank_pain_null_hedged 4/53  flank_pain_null_thirdparty 6/47  flank_pain_true 7/48
      his                 0.136     20   0.000   0.018   0.136
        flank_pain_false 1/55  flank_pain_null_thirdparty 19/47
      but                 0.129     21   0.000   0.055   0.129
        flank_pain_false 3/55  flank_pain_null_hedged 13/53  flank_pain_null_historical 3/40
        flank_pain_null_thirdparty 2/47
      so                  0.129     19   0.000   0.018   0.129
        flank_pain_false 1/55  flank_pain_null_hedged 17/53  flank_pain_null_thirdparty 1/47
      it                  0.128     59   0.292   0.164   0.257
        flank_pain_false 9/55  flank_pain_null_hedged 20/53  flank_pain_null_historical 5/40
        flank_pain_null_thirdparty 11/47  flank_pain_true 14/48
      down                0.128     14   0.146   0.018   0.043
        flank_pain_false 1/55  flank_pain_null_hedged 1/53  flank_pain_null_historical 2/40
        flank_pain_null_thirdparty 3/47  flank_pain_true 7/48
      any                 0.127      8   0.000   0.127   0.007
        flank_pain_false 7/55  flank_pain_null_hedged 1/53
      pain                0.121     75   0.229   0.273   0.350
        flank_pain_false 15/55  flank_pain_null_hedged 11/53  flank_pain_null_historical 27/40
        flank_pain_null_thirdparty 11/47  flank_pain_true 11/48
      are                 0.120      9   0.021   0.127   0.007
        flank_pain_false 7/55  flank_pain_null_hedged 1/53  flank_pain_true 1/48
      at                  0.117     21   0.167   0.109   0.050
        flank_pain_false 6/55  flank_pain_null_hedged 4/53  flank_pain_null_historical 1/40
        flank_pain_null_thirdparty 2/47  flank_pain_true 8/48
      ribs                0.115     29   0.208   0.109   0.093
        flank_pain_false 6/55  flank_pain_null_hedged 6/53  flank_pain_null_thirdparty 7/47
        flank_pain_true 10/48
      has                 0.110     22   0.062   0.018   0.129
        flank_pain_false 1/55  flank_pain_null_hedged 3/53  flank_pain_null_thirdparty 15/47
        flank_pain_true 3/48
      kidneys             0.109      8   0.000   0.109   0.014
        flank_pain_false 6/55  flank_pain_null_hedged 1/53  flank_pain_null_historical 1/40
      with                0.109     20   0.000   0.109   0.100
        flank_pain_false 6/55  flank_pain_null_hedged 1/53  flank_pain_null_historical 8/40
        flank_pain_null_thirdparty 5/47
      now                 0.104      6   0.104   0.000   0.007
        flank_pain_null_hedged 1/53  flank_pain_true 5/48
      all                 0.103     18   0.083   0.145   0.043
        flank_pain_false 8/55  flank_pain_null_hedged 5/53  flank_pain_null_thirdparty 1/47
        flank_pain_true 4/48
      be                  0.100     15   0.000   0.018   0.100
        flank_pain_false 1/55  flank_pain_null_hedged 11/53  flank_pain_null_historical 1/40
        flank_pain_null_thirdparty 2/47
      me                  0.095     23   0.167   0.091   0.071
        flank_pain_false 5/55  flank_pain_null_hedged 4/53  flank_pain_null_thirdparty 6/47
        flank_pain_true 8/48
      feel                0.095      9   0.021   0.109   0.014
        flank_pain_false 6/55  flank_pain_null_hedged 2/53  flank_pain_true 1/48
      this                0.095     10   0.042   0.109   0.014
        flank_pain_false 6/55  flank_pain_null_hedged 1/53  flank_pain_null_thirdparty 1/47
        flank_pain_true 2/48
      ache                0.094     30   0.167   0.073   0.129
        flank_pain_false 4/55  flank_pain_null_hedged 3/53  flank_pain_null_historical 9/40
        flank_pain_null_thirdparty 6/47  flank_pain_true 8/48
      ... and 77 more, counted above but not shown

  haematuria_present: 105 tokens on 5+ lines (true 45, false 45, null 135 lines)
    confined to one label class: 20
      token                skew  lines    true   false    null
      no                  0.467     21   0.000   0.467   0.000
        haematuria_false 21/45
      for                 0.185     25   0.000   0.000   0.185
        haematuria_null_hedged 4/45  haematuria_null_historical 14/45
        haematuria_null_thirdparty 7/45
      his                 0.163     22   0.000   0.000   0.163
        haematuria_null_thirdparty 22/45
      any                 0.156      7   0.000   0.156   0.000
        haematuria_false 7/45
      back                0.104     14   0.000   0.000   0.104
        haematuria_null_hedged 1/45  haematuria_null_historical 13/45
      her                 0.089     12   0.000   0.000   0.089
        haematuria_null_thirdparty 12/45
      so                  0.081     11   0.000   0.000   0.081
        haematuria_null_hedged 10/45  haematuria_null_thirdparty 1/45
      days                0.067      9   0.000   0.000   0.067
        haematuria_null_hedged 2/45  haematuria_null_historical 5/45  haematuria_null_thirdparty
        2/45
      years               0.067      9   0.000   0.000   0.067
        haematuria_null_historical 9/45
      saw                 0.052      7   0.000   0.000   0.052
        haematuria_null_hedged 4/45  haematuria_null_historical 2/45  haematuria_null_thirdparty
        1/45
      know                0.044      6   0.000   0.000   0.044
        haematuria_null_hedged 6/45
      might               0.044      6   0.000   0.000   0.044
        haematuria_null_hedged 6/45
      one                 0.044      6   0.000   0.000   0.044
        haematuria_null_hedged 1/45  haematuria_null_historical 2/45  haematuria_null_thirdparty
        3/45
      be                  0.037      5   0.000   0.000   0.037
        haematuria_null_hedged 5/45
      friend              0.037      5   0.000   0.000   0.037
        haematuria_null_thirdparty 5/45
      pinkish             0.037      5   0.000   0.000   0.037
        haematuria_null_hedged 2/45  haematuria_null_historical 2/45  haematuria_null_thirdparty
        1/45
      reddish             0.037      5   0.000   0.000   0.037
        haematuria_null_hedged 3/45  haematuria_null_historical 1/45  haematuria_null_thirdparty
        1/45
      said                0.037      5   0.000   0.000   0.037
        haematuria_null_hedged 1/45  haematuria_null_thirdparty 4/45
      she                 0.037      5   0.000   0.000   0.037
        haematuria_null_thirdparty 5/45
      tinge               0.037      5   0.000   0.000   0.037
        haematuria_null_hedged 4/45  haematuria_null_historical 1/45
    present in more than one label class but skewed: 85
      token                skew  lines    true   false    null
      a                   0.356     85   0.200   0.156   0.511
        haematuria_false 7/45  haematuria_null_hedged 20/45  haematuria_null_historical 28/45
        haematuria_null_thirdparty 21/45  haematuria_true 9/45
      red                 0.333     57   0.467   0.133   0.222
        haematuria_false 6/45  haematuria_null_hedged 10/45  haematuria_null_historical 10/45
        haematuria_null_thirdparty 10/45  haematuria_true 21/45
      was                 0.326     60   0.178   0.044   0.370
        haematuria_false 2/45  haematuria_null_hedged 19/45  haematuria_null_historical 15/45
        haematuria_null_thirdparty 16/45  haematuria_true 8/45
      my                  0.289    114   0.422   0.311   0.600
        haematuria_false 14/45  haematuria_null_hedged 17/45  haematuria_null_historical 35/45
        haematuria_null_thirdparty 29/45  haematuria_true 19/45
      and                 0.267     48   0.133   0.400   0.178
        haematuria_false 18/45  haematuria_null_hedged 6/45  haematuria_null_historical 9/45
        haematuria_null_thirdparty 9/45  haematuria_true 6/45
      had                 0.267     46   0.044   0.044   0.311
        haematuria_false 2/45  haematuria_null_hedged 8/45  haematuria_null_historical 18/45
        haematuria_null_thirdparty 16/45  haematuria_true 2/45
      i                   0.230    115   0.533   0.333   0.563
        haematuria_false 15/45  haematuria_null_hedged 36/45  haematuria_null_historical 38/45
        haematuria_null_thirdparty 2/45  haematuria_true 24/45
      the                 0.222     91   0.556   0.333   0.378
        haematuria_false 15/45  haematuria_null_hedged 21/45  haematuria_null_historical 12/45
        haematuria_null_thirdparty 18/45  haematuria_true 25/45
      but                 0.222     35   0.022   0.022   0.244
        haematuria_false 1/45  haematuria_null_hedged 33/45  haematuria_true 1/45
      is                  0.222     26   0.178   0.267   0.044
        haematuria_false 12/45  haematuria_null_hedged 3/45  haematuria_null_thirdparty 3/45
        haematuria_true 8/45
      in                  0.207    107   0.311   0.511   0.519
        haematuria_false 23/45  haematuria_null_hedged 11/45  haematuria_null_historical 31/45
        haematuria_null_thirdparty 28/45  haematuria_true 14/45
      nothing             0.200     17   0.022   0.222   0.044
        haematuria_false 10/45  haematuria_null_hedged 5/45  haematuria_null_historical 1/45
        haematuria_true 1/45
      of                  0.200     46   0.289   0.089   0.215
        haematuria_false 4/45  haematuria_null_hedged 8/45  haematuria_null_historical 10/45
        haematuria_null_thirdparty 11/45  haematuria_true 13/45
      went                0.178     19   0.178   0.000   0.081
        haematuria_null_hedged 3/45  haematuria_null_historical 5/45  haematuria_null_thirdparty
        3/45  haematuria_true 8/45
      bowl                0.156     13   0.178   0.044   0.022
        haematuria_false 2/45  haematuria_null_hedged 3/45  haematuria_true 8/45
      normal              0.156     12   0.022   0.178   0.022
        haematuria_false 8/45  haematuria_null_hedged 3/45  haematuria_true 1/45
      today               0.156     10   0.156   0.067   0.000
        haematuria_false 3/45  haematuria_true 7/45
      when                0.156     35   0.222   0.067   0.163
        haematuria_false 3/45  haematuria_null_hedged 4/45  haematuria_null_historical 12/45
        haematuria_null_thirdparty 6/45  haematuria_true 10/45
      after               0.148     23   0.067   0.000   0.148
        haematuria_null_hedged 2/45  haematuria_null_historical 11/45
        haematuria_null_thirdparty 7/45  haematuria_true 3/45
      clear               0.148      9   0.022   0.156   0.007
        haematuria_false 7/45  haematuria_null_hedged 1/45  haematuria_true 1/45
      to                  0.148     31   0.156   0.022   0.170
        haematuria_false 1/45  haematuria_null_hedged 9/45  haematuria_null_historical 5/45
        haematuria_null_thirdparty 9/45  haematuria_true 7/45
      all                 0.141     15   0.044   0.178   0.037
        haematuria_false 8/45  haematuria_null_hedged 3/45  haematuria_null_historical 1/45
        haematuria_null_thirdparty 1/45  haematuria_true 2/45
      that                0.141     23   0.000   0.089   0.141
        haematuria_false 4/45  haematuria_null_hedged 9/45  haematuria_null_historical 8/45
        haematuria_null_thirdparty 2/45
      bright              0.133     11   0.133   0.000   0.037
        haematuria_null_hedged 1/45  haematuria_null_historical 1/45  haematuria_null_thirdparty
        3/45  haematuria_true 6/45
      last                0.133     19   0.022   0.000   0.133
        haematuria_null_hedged 2/45  haematuria_null_historical 9/45  haematuria_null_thirdparty
        7/45  haematuria_true 1/45
      like                0.133     12   0.156   0.044   0.022
        haematuria_false 2/45  haematuria_null_hedged 2/45  haematuria_null_historical 1/45
        haematuria_true 7/45
      out                 0.133     12   0.133   0.000   0.044
        haematuria_null_hedged 2/45  haematuria_null_historical 1/45  haematuria_null_thirdparty
        3/45  haematuria_true 6/45
      urine               0.133     55   0.289   0.156   0.259
        haematuria_false 7/45  haematuria_null_hedged 4/45  haematuria_null_historical 16/45
        haematuria_null_thirdparty 15/45  haematuria_true 13/45
      dark                0.111     16   0.133   0.022   0.067
        haematuria_false 1/45  haematuria_null_hedged 5/45  haematuria_null_historical 2/45
        haematuria_null_thirdparty 2/45  haematuria_true 6/45
      its                 0.111     11   0.044   0.133   0.022
        haematuria_false 6/45  haematuria_null_hedged 2/45  haematuria_null_historical 1/45
        haematuria_true 2/45
      looks               0.111      6   0.022   0.111   0.000
        haematuria_false 5/45  haematuria_true 1/45
      or                  0.111     10   0.000   0.111   0.037
        haematuria_false 5/45  haematuria_null_hedged 3/45  haematuria_null_historical 2/45
      toilet              0.111     12   0.133   0.067   0.022
        haematuria_false 3/45  haematuria_null_hedged 2/45  haematuria_null_historical 1/45
        haematuria_true 6/45
      blood               0.111    101   0.400   0.511   0.444
        haematuria_false 23/45  haematuria_null_hedged 7/45  haematuria_null_historical 24/45
        haematuria_null_thirdparty 29/45  haematuria_true 18/45
      yellow              0.104      7   0.022   0.111   0.007
        haematuria_false 5/45  haematuria_null_hedged 1/45  haematuria_true 1/45
      been                0.096     26   0.156   0.178   0.081
        haematuria_false 8/45  haematuria_null_hedged 5/45  haematuria_null_thirdparty 6/45
        haematuria_true 7/45
      not                 0.096      8   0.022   0.111   0.015
        haematuria_false 5/45  haematuria_null_hedged 2/45  haematuria_true 1/45
      this                0.096     10   0.111   0.067   0.015
        haematuria_false 3/45  haematuria_null_hedged 2/45  haematuria_true 5/45
      came                0.089      8   0.089   0.000   0.030
        haematuria_null_hedged 2/45  haematuria_null_historical 2/45  haematuria_true 4/45
      end                 0.089      5   0.089   0.000   0.007
        haematuria_null_hedged 1/45  haematuria_true 4/45
      ... and 45 more, counted above but not shown

  nocturia_present: 178 tokens on 5+ lines (true 54, false 54, null 243 lines)
    confined to one label class: 19
      token                skew  lines    true   false    null
      went                0.062     15   0.000   0.000   0.062
        nocturia_null_attribution 1/51  nocturia_null_hedged 4/47  nocturia_null_historical 6/46
        nocturia_null_metaphor 3/52  nocturia_null_thirdparty 1/47
      be                  0.045     11   0.000   0.000   0.045
        nocturia_null_hedged 4/47  nocturia_null_historical 3/46  nocturia_null_metaphor 2/52
        nocturia_null_thirdparty 2/47
      got                 0.045     11   0.000   0.000   0.045
        nocturia_null_attribution 2/51  nocturia_null_hedged 3/47  nocturia_null_historical 1/46
        nocturia_null_metaphor 5/52
      work                0.041     10   0.000   0.000   0.041
        nocturia_null_attribution 3/51  nocturia_null_hedged 3/47  nocturia_null_metaphor 3/52
        nocturia_null_thirdparty 1/47
      you                 0.041     10   0.000   0.000   0.041
        nocturia_null_hedged 7/47  nocturia_null_metaphor 2/52  nocturia_null_thirdparty 1/47
      might               0.037      9   0.000   0.000   0.037
        nocturia_null_hedged 8/47  nocturia_null_thirdparty 1/47
      whether             0.037      9   0.000   0.000   0.037
        nocturia_null_hedged 7/47  nocturia_null_metaphor 1/52  nocturia_null_thirdparty 1/47
      i'll                0.033      8   0.000   0.000   0.033
        nocturia_null_attribution 5/51  nocturia_null_metaphor 3/52
      tell                0.033      8   0.000   0.000   0.033
        nocturia_null_hedged 7/47  nocturia_null_thirdparty 1/47
      anyway              0.029      7   0.000   0.000   0.029
        nocturia_null_attribution 2/51  nocturia_null_hedged 3/47  nocturia_null_historical 1/46
        nocturia_null_metaphor 1/52
      he                  0.029      7   0.000   0.000   0.029
        nocturia_null_hedged 2/47  nocturia_null_metaphor 1/52  nocturia_null_thirdparty 4/47
      door                0.025      6   0.000   0.000   0.025
        nocturia_null_attribution 1/51  nocturia_null_hedged 1/47  nocturia_null_metaphor 2/52
        nocturia_null_thirdparty 2/47
      he's                0.025      6   0.000   0.000   0.025
        nocturia_null_attribution 1/51  nocturia_null_hedged 1/47  nocturia_null_thirdparty 4/47
      tablets             0.025      6   0.000   0.000   0.025
        nocturia_null_hedged 1/47  nocturia_null_historical 2/46  nocturia_null_thirdparty 3/47
      gone                0.021      5   0.000   0.000   0.021
        nocturia_null_attribution 1/51  nocturia_null_hedged 1/47  nocturia_null_metaphor 3/52
      next                0.021      5   0.000   0.000   0.021
        nocturia_null_hedged 1/47  nocturia_null_metaphor 2/52  nocturia_null_thirdparty 2/47
      shift               0.021      5   0.000   0.000   0.021
        nocturia_null_attribution 1/51  nocturia_null_historical 1/46  nocturia_null_metaphor
        3/52
      sure                0.021      5   0.000   0.000   0.021
        nocturia_null_hedged 5/47
      us                  0.021      5   0.000   0.000   0.021
        nocturia_null_attribution 1/51  nocturia_null_metaphor 2/52  nocturia_null_thirdparty
        2/47
    present in more than one label class but skewed: 159
      token                skew  lines    true   false    null
      not                 0.315     31   0.037   0.352   0.041
        nocturia_false 19/54  nocturia_null_hedged 6/47  nocturia_null_metaphor 4/52
        nocturia_true 2/54
      up                  0.263    117   0.519   0.500   0.255
        nocturia_false 27/54  nocturia_null_attribution 27/51  nocturia_null_hedged 14/47
        nocturia_null_historical 1/46  nocturia_null_metaphor 14/52  nocturia_null_thirdparty
        6/47  nocturia_true 28/54
      to                  0.241    119   0.500   0.259   0.321
        nocturia_false 14/54  nocturia_null_attribution 17/51  nocturia_null_hedged 21/47
        nocturia_null_historical 9/46  nocturia_null_metaphor 10/52  nocturia_null_thirdparty
        21/47  nocturia_true 27/54
      for                 0.233     83   0.426   0.241   0.193
        nocturia_false 13/54  nocturia_null_attribution 10/51  nocturia_null_hedged 4/47
        nocturia_null_historical 12/46  nocturia_null_metaphor 10/52  nocturia_null_thirdparty
        11/47  nocturia_true 23/54
      my                  0.218    138   0.222   0.352   0.440
        nocturia_false 19/54  nocturia_null_attribution 23/51  nocturia_null_hedged 11/47
        nocturia_null_historical 28/46  nocturia_null_metaphor 13/52  nocturia_null_thirdparty
        32/47  nocturia_true 12/54
      night               0.216    120   0.500   0.444   0.284
        nocturia_false 24/54  nocturia_null_attribution 13/51  nocturia_null_hedged 8/47
        nocturia_null_historical 12/46  nocturia_null_metaphor 15/52  nocturia_null_thirdparty
        21/47  nocturia_true 27/54
      a                   0.202    107   0.259   0.148   0.350
        nocturia_false 8/54  nocturia_null_attribution 13/51  nocturia_null_hedged 14/47
        nocturia_null_historical 22/46  nocturia_null_metaphor 18/52  nocturia_null_thirdparty
        18/47  nocturia_true 14/54
      no                  0.185     18   0.000   0.185   0.033
        nocturia_false 10/54  nocturia_null_attribution 1/51  nocturia_null_hedged 2/47
        nocturia_null_metaphor 4/52  nocturia_null_thirdparty 1/47
      twice               0.185     27   0.185   0.000   0.070
        nocturia_null_attribution 2/51  nocturia_null_hedged 5/47  nocturia_null_historical 5/46
        nocturia_null_thirdparty 5/47  nocturia_true 10/54
      i'm                 0.183     70   0.352   0.185   0.169
        nocturia_false 10/54  nocturia_null_attribution 22/51  nocturia_null_hedged 11/47
        nocturia_null_metaphor 6/52  nocturia_null_thirdparty 2/47  nocturia_true 19/54
      needing             0.171     25   0.204   0.111   0.033
        nocturia_false 6/54  nocturia_null_hedged 2/47  nocturia_null_historical 3/46
        nocturia_null_thirdparty 3/47  nocturia_true 11/54
      awake               0.167     29   0.167   0.000   0.082
        nocturia_null_attribution 11/51  nocturia_null_hedged 2/47  nocturia_null_historical
        2/46  nocturia_null_metaphor 4/52  nocturia_null_thirdparty 1/47  nocturia_true 9/54
      three               0.167     27   0.204   0.037   0.058
        nocturia_false 2/54  nocturia_null_attribution 2/51  nocturia_null_hedged 1/47
        nocturia_null_historical 4/46  nocturia_null_metaphor 1/52  nocturia_null_thirdparty
        6/47  nocturia_true 11/54
      been                0.146     58   0.204   0.278   0.132
        nocturia_false 15/54  nocturia_null_attribution 4/51  nocturia_null_hedged 10/47
        nocturia_null_metaphor 12/52  nocturia_null_thirdparty 6/47  nocturia_true 11/54
      so                  0.134     41   0.056   0.019   0.152
        nocturia_false 1/54  nocturia_null_attribution 15/51  nocturia_null_hedged 15/47
        nocturia_null_historical 2/46  nocturia_null_metaphor 5/52  nocturia_true 3/54
      every               0.130     15   0.130   0.000   0.033
        nocturia_null_historical 4/46  nocturia_null_metaphor 1/52  nocturia_null_thirdparty
        3/47  nocturia_true 7/54
      four                0.130     18   0.148   0.019   0.037
        nocturia_false 1/54  nocturia_null_attribution 4/51  nocturia_null_historical 2/46
        nocturia_null_metaphor 1/52  nocturia_null_thirdparty 2/47  nocturia_true 8/54
      had                 0.130     26   0.037   0.167   0.062
        nocturia_false 9/54  nocturia_null_attribution 3/51  nocturia_null_hedged 2/47
        nocturia_null_historical 5/46  nocturia_null_metaphor 4/52  nocturia_null_thirdparty
        1/47  nocturia_true 2/54
      with                0.130     43   0.019   0.148   0.140
        nocturia_false 8/54  nocturia_null_attribution 12/51  nocturia_null_hedged 3/47
        nocturia_null_historical 1/46  nocturia_null_metaphor 14/52  nocturia_null_thirdparty
        4/47  nocturia_true 1/54
      i                   0.130    180   0.463   0.593   0.506
        nocturia_false 32/54  nocturia_null_attribution 42/51  nocturia_null_hedged 40/47
        nocturia_null_historical 18/46  nocturia_null_metaphor 18/52  nocturia_null_thirdparty
        5/47  nocturia_true 25/54
      it                  0.126     69   0.093   0.204   0.218
        nocturia_false 11/54  nocturia_null_attribution 8/51  nocturia_null_hedged 19/47
        nocturia_null_historical 10/46  nocturia_null_metaphor 7/52  nocturia_null_thirdparty
        9/47  nocturia_true 5/54
      getting             0.123     20   0.148   0.111   0.025
        nocturia_false 6/54  nocturia_null_attribution 1/51  nocturia_null_hedged 3/47
        nocturia_null_thirdparty 2/47  nocturia_true 8/54
      on                  0.115     41   0.037   0.037   0.152
        nocturia_false 2/54  nocturia_null_attribution 12/51  nocturia_null_hedged 2/47
        nocturia_null_historical 12/46  nocturia_null_metaphor 6/52  nocturia_null_thirdparty
        5/47  nocturia_true 2/54
      bed                 0.113     29   0.167   0.130   0.053
        nocturia_false 7/54  nocturia_null_attribution 3/51  nocturia_null_hedged 2/47
        nocturia_null_historical 1/46  nocturia_null_metaphor 1/52  nocturia_null_thirdparty
        6/47  nocturia_true 9/54
      now                 0.113     13   0.130   0.037   0.016
        nocturia_false 2/54  nocturia_null_hedged 1/47  nocturia_null_historical 1/46
        nocturia_null_metaphor 1/52  nocturia_null_thirdparty 1/47  nocturia_true 7/54
      if                  0.111     26   0.019   0.130   0.074
        nocturia_false 7/54  nocturia_null_attribution 1/51  nocturia_null_hedged 14/47
        nocturia_null_metaphor 2/52  nocturia_null_thirdparty 1/47  nocturia_true 1/54
      it's                0.111     23   0.148   0.037   0.053
        nocturia_false 2/54  nocturia_null_attribution 3/51  nocturia_null_hedged 4/47
        nocturia_null_metaphor 2/52  nocturia_null_thirdparty 4/47  nocturia_true 8/54
      sleep               0.111     34   0.111   0.185   0.074
        nocturia_false 10/54  nocturia_null_attribution 3/51  nocturia_null_hedged 5/47
        nocturia_null_historical 3/46  nocturia_null_metaphor 6/52  nocturia_null_thirdparty
        1/47  nocturia_true 6/54
      that                0.111     32   0.037   0.148   0.091
        nocturia_false 8/54  nocturia_null_attribution 6/51  nocturia_null_hedged 5/47
        nocturia_null_historical 5/46  nocturia_null_metaphor 5/52  nocturia_null_thirdparty
        1/47  nocturia_true 2/54
      until               0.111      7   0.000   0.111   0.004
        nocturia_false 6/54  nocturia_null_metaphor 1/52
      wee                 0.111     42   0.185   0.074   0.115
        nocturia_false 4/54  nocturia_null_attribution 3/51  nocturia_null_hedged 1/47
        nocturia_null_historical 5/46  nocturia_null_metaphor 9/52  nocturia_null_thirdparty
        10/47  nocturia_true 10/54
      this                0.105     31   0.130   0.167   0.062
        nocturia_false 9/54  nocturia_null_attribution 1/51  nocturia_null_hedged 3/47
        nocturia_null_historical 2/46  nocturia_null_metaphor 8/52  nocturia_null_thirdparty
        1/47  nocturia_true 7/54
      was                 0.101     49   0.056   0.148   0.156
        nocturia_false 8/54  nocturia_null_attribution 4/51  nocturia_null_hedged 6/47
        nocturia_null_historical 16/46  nocturia_null_metaphor 6/52  nocturia_null_thirdparty
        6/47  nocturia_true 3/54
      wake                0.097     17   0.037   0.130   0.033
        nocturia_false 7/54  nocturia_null_attribution 2/51  nocturia_null_hedged 3/47
        nocturia_null_historical 2/46  nocturia_null_metaphor 1/52  nocturia_true 2/54
      toilet              0.095     53   0.222   0.185   0.128
        nocturia_false 10/54  nocturia_null_attribution 10/51  nocturia_null_hedged 3/47
        nocturia_null_historical 10/46  nocturia_null_thirdparty 8/47  nocturia_true 12/54
      and                 0.093    138   0.370   0.463   0.383
        nocturia_false 25/54  nocturia_null_attribution 47/51  nocturia_null_hedged 14/47
        nocturia_null_historical 6/46  nocturia_null_metaphor 15/52  nocturia_null_thirdparty
        11/47  nocturia_true 20/54
      about               0.093     22   0.093   0.000   0.070
        nocturia_null_attribution 3/51  nocturia_null_hedged 1/47  nocturia_null_historical 3/46
        nocturia_null_metaphor 6/52  nocturia_null_thirdparty 4/47  nocturia_true 5/54
      at                  0.093     79   0.259   0.167   0.230
        nocturia_false 9/54  nocturia_null_attribution 21/51  nocturia_null_hedged 5/47
        nocturia_null_historical 5/46  nocturia_null_metaphor 10/52  nocturia_null_thirdparty
        15/47  nocturia_true 14/54
      is                  0.093     30   0.037   0.130   0.086
        nocturia_false 7/54  nocturia_null_attribution 1/51  nocturia_null_hedged 6/47
        nocturia_null_metaphor 3/52  nocturia_null_thirdparty 11/47  nocturia_true 2/54
      nothing             0.093     10   0.000   0.093   0.021
        nocturia_false 5/54  nocturia_null_hedged 3/47  nocturia_null_historical 1/46
        nocturia_null_metaphor 1/52
      ... and 119 more, counted above but not shown

  recent_uti_present: 126 tokens on 5+ lines (true 44, false 44, null 168 lines)
    confined to one label class: 17
      token                skew  lines    true   false    null
      no                  0.227     10   0.000   0.227   0.000
        recent_uti_false 10/44
      tested              0.182      8   0.000   0.182   0.000
        recent_uti_false 8/44
      nothing             0.136      6   0.000   0.136   0.000
        recent_uti_false 6/44
      checked             0.114      5   0.000   0.114   0.000
        recent_uti_false 5/44
      or                  0.083     14   0.000   0.000   0.083
        recent_uti_null_hedged 13/44  recent_uti_null_historical 1/42
      might               0.065     11   0.000   0.000   0.065
        recent_uti_null_hedged 11/44
      could               0.060     10   0.000   0.000   0.060
        recent_uti_null_hedged 8/44  recent_uti_null_thirdparty 2/40
      infected            0.060     10   0.000   0.000   0.060
        recent_uti_null_adjacent 10/42
      chest               0.048      8   0.000   0.000   0.048
        recent_uti_null_adjacent 8/42
      sure                0.042      7   0.000   0.000   0.042
        recent_uti_null_hedged 7/44
      couple              0.036      6   0.000   0.000   0.036
        recent_uti_null_adjacent 1/42  recent_uti_null_hedged 2/44  recent_uti_null_historical
        2/42  recent_uti_null_thirdparty 1/40
      few                 0.036      6   0.000   0.000   0.036
        recent_uti_null_hedged 3/44  recent_uti_null_historical 1/42  recent_uti_null_thirdparty
        2/40
      bit                 0.030      5   0.000   0.000   0.030
        recent_uti_null_hedged 5/44
      felt                0.030      5   0.000   0.000   0.030
        recent_uti_null_hedged 5/44
      if                  0.030      5   0.000   0.000   0.030
        recent_uti_null_hedged 5/44
      mild                0.030      5   0.000   0.000   0.030
        recent_uti_null_hedged 5/44
      whether             0.030      5   0.000   0.000   0.030
        recent_uti_null_hedged 5/44
    present in more than one label class but skewed: 109
      token                skew  lines    true   false    null
      ago                 0.455    110   0.659   0.205   0.429
        recent_uti_false 9/44  recent_uti_null_adjacent 30/42  recent_uti_null_hedged 17/44
        recent_uti_null_historical 15/42  recent_uti_null_thirdparty 10/40  recent_uti_true
        29/44
      a                   0.414    168   0.705   0.318   0.732
        recent_uti_false 14/44  recent_uti_null_adjacent 27/42  recent_uti_null_hedged 31/44
        recent_uti_null_historical 32/42  recent_uti_null_thirdparty 33/40  recent_uti_true
        31/44
      and                 0.327     72   0.477   0.500   0.173
        recent_uti_false 22/44  recent_uti_null_adjacent 14/42  recent_uti_null_hedged 4/44
        recent_uti_null_historical 8/42  recent_uti_null_thirdparty 3/40  recent_uti_true 21/44
      the                 0.280    103   0.614   0.455   0.333
        recent_uti_false 20/44  recent_uti_null_adjacent 15/42  recent_uti_null_hedged 10/44
        recent_uti_null_historical 16/42  recent_uti_null_thirdparty 15/40  recent_uti_true
        27/44
      days                0.273     39   0.318   0.045   0.137
        recent_uti_false 2/44  recent_uti_null_adjacent 11/42  recent_uti_null_hedged 6/44
        recent_uti_null_thirdparty 6/40  recent_uti_true 14/44
      have                0.250     35   0.068   0.318   0.107
        recent_uti_false 14/44  recent_uti_null_adjacent 3/42  recent_uti_null_hedged 14/44
        recent_uti_null_historical 1/42  recent_uti_true 3/44
      for                 0.250     58   0.341   0.091   0.232
        recent_uti_false 4/44  recent_uti_null_adjacent 17/42  recent_uti_null_hedged 3/44
        recent_uti_null_historical 10/42  recent_uti_null_thirdparty 9/40  recent_uti_true 15/44
      since               0.232     15   0.023   0.250   0.018
        recent_uti_false 11/44  recent_uti_null_thirdparty 3/40  recent_uti_true 1/44
      been                0.227     22   0.000   0.227   0.071
        recent_uti_false 10/44  recent_uti_null_adjacent 1/42  recent_uti_null_hedged 7/44
        recent_uti_null_thirdparty 4/40
      not                 0.227     29   0.000   0.227   0.113
        recent_uti_false 10/44  recent_uti_null_hedged 15/44  recent_uti_null_historical 2/42
        recent_uti_null_thirdparty 2/40
      infection           0.222    134   0.705   0.500   0.482
        recent_uti_false 22/44  recent_uti_null_adjacent 13/42  recent_uti_null_hedged 16/44
        recent_uti_null_historical 25/42  recent_uti_null_thirdparty 27/40  recent_uti_true
        31/44
      clear               0.182      9   0.000   0.182   0.006
        recent_uti_false 8/44  recent_uti_null_hedged 1/44
      never               0.182      9   0.000   0.182   0.006
        recent_uti_false 8/44  recent_uti_null_historical 1/42
      about               0.159     45   0.205   0.045   0.202
        recent_uti_false 2/44  recent_uti_null_adjacent 13/42  recent_uti_null_hedged 10/44
        recent_uti_null_historical 4/42  recent_uti_null_thirdparty 7/40  recent_uti_true 9/44
      all                 0.159     13   0.000   0.159   0.036
        recent_uti_false 7/44  recent_uti_null_hedged 2/44  recent_uti_null_historical 2/42
        recent_uti_null_thirdparty 2/40
      my                  0.159     88   0.295   0.455   0.327
        recent_uti_false 20/44  recent_uti_null_adjacent 11/42  recent_uti_null_hedged 4/44
        recent_uti_null_historical 17/42  recent_uti_null_thirdparty 23/40  recent_uti_true
        13/44
      of                  0.159     45   0.273   0.114   0.167
        recent_uti_false 5/44  recent_uti_null_adjacent 7/42  recent_uti_null_hedged 7/44
        recent_uti_null_historical 8/42  recent_uti_null_thirdparty 6/40  recent_uti_true 12/44
      at                  0.144     31   0.227   0.159   0.083
        recent_uti_false 7/44  recent_uti_null_adjacent 4/42  recent_uti_null_hedged 4/44
        recent_uti_null_historical 2/42  recent_uti_null_thirdparty 4/40  recent_uti_true 10/44
      one                 0.140     19   0.091   0.182   0.042
        recent_uti_false 8/44  recent_uti_null_hedged 2/44  recent_uti_null_historical 5/42
        recent_uti_true 4/44
      i                   0.140    150   0.682   0.659   0.542
        recent_uti_false 29/44  recent_uti_null_adjacent 18/42  recent_uti_null_hedged 42/44
        recent_uti_null_historical 30/42  recent_uti_null_thirdparty 1/40  recent_uti_true 30/44
      but                 0.139     40   0.045   0.159   0.185
        recent_uti_false 7/44  recent_uti_null_hedged 30/44  recent_uti_null_historical 1/42
        recent_uti_true 2/44
      had                 0.137     91   0.250   0.341   0.387
        recent_uti_false 15/44  recent_uti_null_adjacent 8/42  recent_uti_null_hedged 29/44
        recent_uti_null_historical 12/42  recent_uti_null_thirdparty 16/40  recent_uti_true
        11/44
      has                 0.136     16   0.023   0.159   0.048
        recent_uti_false 7/44  recent_uti_null_thirdparty 8/40  recent_uti_true 1/44
      tablets             0.136     12   0.136   0.000   0.036
        recent_uti_null_adjacent 2/42  recent_uti_null_historical 2/42
        recent_uti_null_thirdparty 2/40  recent_uti_true 6/44
      weeks               0.136     46   0.227   0.091   0.190
        recent_uti_false 4/44  recent_uti_null_adjacent 11/42  recent_uti_null_hedged 12/44
        recent_uti_null_thirdparty 9/40  recent_uti_true 10/44
      urine               0.131     40   0.250   0.205   0.119
        recent_uti_false 9/44  recent_uti_null_hedged 4/44  recent_uti_null_historical 9/42
        recent_uti_null_thirdparty 7/40  recent_uti_true 11/44
      there               0.129     15   0.068   0.159   0.030
        recent_uti_false 7/44  recent_uti_null_historical 5/42  recent_uti_true 3/44
      said                0.124     11   0.068   0.136   0.012
        recent_uti_false 6/44  recent_uti_null_adjacent 1/42  recent_uti_null_thirdparty 1/40
        recent_uti_true 3/44
      on                  0.114     37   0.205   0.091   0.143
        recent_uti_false 4/44  recent_uti_null_adjacent 9/42  recent_uti_null_hedged 3/44
        recent_uti_null_historical 7/42  recent_uti_null_thirdparty 5/40  recent_uti_true 9/44
      is                  0.114     10   0.000   0.114   0.030
        recent_uti_false 5/44  recent_uti_null_hedged 3/44  recent_uti_null_historical 1/42
        recent_uti_null_thirdparty 1/40
      treated             0.114     18   0.136   0.023   0.065
        recent_uti_false 1/44  recent_uti_null_adjacent 6/42  recent_uti_null_historical 3/42
        recent_uti_null_thirdparty 2/40  recent_uti_true 6/44
      last                0.096     55   0.136   0.227   0.232
        recent_uti_false 10/44  recent_uti_null_adjacent 4/42  recent_uti_null_hedged 12/44
        recent_uti_null_historical 8/42  recent_uti_null_thirdparty 15/40  recent_uti_true 6/44
      an                  0.094     24   0.136   0.159   0.065
        recent_uti_false 7/44  recent_uti_null_adjacent 8/42  recent_uti_null_hedged 3/44
        recent_uti_true 6/44
      with                0.091     31   0.136   0.045   0.137
        recent_uti_false 2/44  recent_uti_null_adjacent 1/42  recent_uti_null_hedged 2/44
        recent_uti_null_historical 9/42  recent_uti_null_thirdparty 11/40  recent_uti_true 6/44
      three               0.091     36   0.205   0.114   0.131
        recent_uti_false 5/44  recent_uti_null_adjacent 7/42  recent_uti_null_hedged 8/44
        recent_uti_null_historical 3/42  recent_uti_null_thirdparty 4/40  recent_uti_true 9/44
      after               0.091     13   0.091   0.000   0.054
        recent_uti_null_adjacent 2/42  recent_uti_null_hedged 1/44  recent_uti_null_historical
        5/42  recent_uti_null_thirdparty 1/40  recent_uti_true 4/44
      every               0.091      5   0.000   0.091   0.006
        recent_uti_false 4/44  recent_uti_null_historical 1/42
      in                  0.091     32   0.091   0.182   0.119
        recent_uti_false 8/44  recent_uti_null_adjacent 3/42  recent_uti_null_hedged 2/44
        recent_uti_null_historical 10/42  recent_uti_null_thirdparty 5/40  recent_uti_true 4/44
      it                  0.091     49   0.136   0.227   0.196
        recent_uti_false 10/44  recent_uti_null_adjacent 4/42  recent_uti_null_hedged 27/44
        recent_uti_null_thirdparty 2/40  recent_uti_true 6/44
      up                  0.091     18   0.091   0.000   0.083
        recent_uti_null_adjacent 1/42  recent_uti_null_hedged 3/44  recent_uti_null_historical
        5/42  recent_uti_null_thirdparty 5/40  recent_uti_true 4/44
      ... and 69 more, counted above but not shown

  urinary_frequency_present: 146 tokens on 5+ lines (true 46, false 46, null 210 lines)
    confined to one label class: 20
      token                skew  lines    true   false    null
      when                0.110     23   0.000   0.000   0.110
        urinary_frequency_null_adjacent 9/40  urinary_frequency_null_hedged 1/42
        urinary_frequency_null_historical 12/40  urinary_frequency_null_metaphor 1/44
      she's               0.057     12   0.000   0.000   0.057
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 11/44
      with                0.057     12   0.000   0.000   0.057
        urinary_frequency_null_adjacent 1/40  urinary_frequency_null_historical 2/40
        urinary_frequency_null_metaphor 6/44  urinary_frequency_null_thirdparty 3/44
      never               0.052     11   0.000   0.000   0.052
        urinary_frequency_null_adjacent 5/40  urinary_frequency_null_hedged 3/42
        urinary_frequency_null_historical 1/40  urinary_frequency_null_metaphor 1/44
        urinary_frequency_null_thirdparty 1/44
      he's                0.038      8   0.000   0.000   0.038
        urinary_frequency_null_metaphor 2/44  urinary_frequency_null_thirdparty 6/44
      know                0.033      7   0.000   0.000   0.033
        urinary_frequency_null_adjacent 1/40  urinary_frequency_null_hedged 3/42
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 2/44
      might               0.033      7   0.000   0.000   0.033
        urinary_frequency_null_hedged 7/42
      whether             0.033      7   0.000   0.000   0.033
        urinary_frequency_null_hedged 7/42
      years               0.033      7   0.000   0.000   0.033
        urinary_frequency_null_historical 7/40
      away                0.029      6   0.000   0.000   0.029
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_metaphor 4/44
        urinary_frequency_null_thirdparty 1/44
      don't               0.029      6   0.000   0.000   0.029
        urinary_frequency_null_adjacent 1/40  urinary_frequency_null_hedged 4/42
        urinary_frequency_null_thirdparty 1/44
      he                  0.029      6   0.000   0.000   0.029
        urinary_frequency_null_metaphor 2/44  urinary_frequency_null_thirdparty 4/44
      his                 0.029      6   0.000   0.000   0.029
        urinary_frequency_null_metaphor 2/44  urinary_frequency_null_thirdparty 4/44
      tell                0.029      6   0.000   0.000   0.029
        urinary_frequency_null_hedged 5/42  urinary_frequency_null_metaphor 1/44
      there               0.029      6   0.000   0.000   0.029
        urinary_frequency_null_adjacent 2/40  urinary_frequency_null_hedged 1/42
        urinary_frequency_null_historical 1/40  urinary_frequency_null_metaphor 1/44
        urinary_frequency_null_thirdparty 1/44
      they                0.029      6   0.000   0.000   0.029
        urinary_frequency_null_historical 5/40  urinary_frequency_null_thirdparty 1/44
      couldn't            0.024      5   0.000   0.000   0.024
        urinary_frequency_null_hedged 3/42  urinary_frequency_null_historical 1/40
        urinary_frequency_null_metaphor 1/44
      her                 0.024      5   0.000   0.000   0.024
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_thirdparty 4/44
      she                 0.024      5   0.000   0.000   0.024
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 4/44
      tablets             0.024      5   0.000   0.000   0.024
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_historical 2/40
        urinary_frequency_null_thirdparty 2/44
    present in more than one label class but skewed: 126
      token                skew  lines    true   false    null
      i'm                 0.293     46   0.370   0.283   0.076
        urinary_frequency_false 13/46  urinary_frequency_null_hedged 10/42
        urinary_frequency_null_metaphor 2/44  urinary_frequency_null_thirdparty 4/44
        urinary_frequency_true 17/46
      no                  0.217     20   0.022   0.239   0.038
        urinary_frequency_false 11/46  urinary_frequency_null_adjacent 3/40
        urinary_frequency_null_hedged 5/42  urinary_frequency_true 1/46
      to                  0.217     86   0.413   0.196   0.276
        urinary_frequency_false 9/46  urinary_frequency_null_adjacent 16/40
        urinary_frequency_null_hedged 14/42  urinary_frequency_null_historical 4/40
        urinary_frequency_null_metaphor 6/44  urinary_frequency_null_thirdparty 18/44
        urinary_frequency_true 19/46
      my                  0.214    108   0.196   0.283   0.410
        urinary_frequency_false 13/46  urinary_frequency_null_adjacent 10/40
        urinary_frequency_null_hedged 9/42  urinary_frequency_null_historical 15/40
        urinary_frequency_null_metaphor 14/44  urinary_frequency_null_thirdparty 38/44
        urinary_frequency_true 9/46
      as                  0.203     16   0.065   0.217   0.014
        urinary_frequency_false 10/46  urinary_frequency_null_hedged 1/42
        urinary_frequency_null_historical 1/40  urinary_frequency_null_metaphor 1/44
        urinary_frequency_true 3/46
      it                  0.187     60   0.087   0.065   0.252
        urinary_frequency_false 3/46  urinary_frequency_null_adjacent 14/40
        urinary_frequency_null_hedged 15/42  urinary_frequency_null_historical 11/40
        urinary_frequency_null_metaphor 6/44  urinary_frequency_null_thirdparty 7/44
        urinary_frequency_true 4/46
      not                 0.174     17   0.000   0.174   0.043
        urinary_frequency_false 8/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 6/42  urinary_frequency_null_metaphor 1/44
        urinary_frequency_null_thirdparty 1/44
      i                   0.158    117   0.370   0.261   0.419
        urinary_frequency_false 12/46  urinary_frequency_null_adjacent 21/40
        urinary_frequency_null_hedged 21/42  urinary_frequency_null_historical 33/40
        urinary_frequency_null_metaphor 9/44  urinary_frequency_null_thirdparty 4/44
        urinary_frequency_true 17/46
      every               0.152     27   0.152   0.000   0.095
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_historical 6/40
        urinary_frequency_null_metaphor 3/44  urinary_frequency_null_thirdparty 10/44
        urinary_frequency_true 7/46
      that                0.143     34   0.000   0.087   0.143
        urinary_frequency_false 4/46  urinary_frequency_null_adjacent 4/40
        urinary_frequency_null_hedged 8/42  urinary_frequency_null_historical 10/40
        urinary_frequency_null_metaphor 7/44  urinary_frequency_null_thirdparty 1/44
      same                0.138     11   0.022   0.152   0.014
        urinary_frequency_false 7/46  urinary_frequency_null_historical 1/40
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 1/44
        urinary_frequency_true 1/46
      times               0.138     17   0.152   0.152   0.014
        urinary_frequency_false 7/46  urinary_frequency_null_hedged 1/42
        urinary_frequency_null_thirdparty 2/44  urinary_frequency_true 7/46
      the                 0.130    145   0.500   0.370   0.500
        urinary_frequency_false 17/46  urinary_frequency_null_adjacent 18/40
        urinary_frequency_null_hedged 10/42  urinary_frequency_null_historical 22/40
        urinary_frequency_null_metaphor 31/44  urinary_frequency_null_thirdparty 24/44
        urinary_frequency_true 23/46
      how                 0.124     15   0.043   0.152   0.029
        urinary_frequency_false 7/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 2/42  urinary_frequency_null_historical 1/40
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 1/44
        urinary_frequency_true 2/46
      in                  0.123     41   0.043   0.087   0.167
        urinary_frequency_false 4/46  urinary_frequency_null_adjacent 6/40
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_historical 13/40
        urinary_frequency_null_metaphor 8/44  urinary_frequency_null_thirdparty 7/44
        urinary_frequency_true 2/46
      often               0.122     39   0.196   0.217   0.095
        urinary_frequency_false 10/46  urinary_frequency_null_hedged 9/42
        urinary_frequency_null_historical 4/40  urinary_frequency_null_metaphor 2/44
        urinary_frequency_null_thirdparty 5/44  urinary_frequency_true 9/46
      always              0.121      9   0.022   0.130   0.010
        urinary_frequency_false 6/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_metaphor 1/44  urinary_frequency_true 1/46
      usual               0.119     17   0.065   0.152   0.033
        urinary_frequency_false 7/46  urinary_frequency_null_hedged 4/42
        urinary_frequency_null_thirdparty 3/44  urinary_frequency_true 3/46
      trips               0.116     11   0.043   0.130   0.014
        urinary_frequency_false 6/46  urinary_frequency_null_hedged 3/42  urinary_frequency_true
        2/46
      i've                0.115     44   0.239   0.152   0.124
        urinary_frequency_false 7/46  urinary_frequency_null_adjacent 5/40
        urinary_frequency_null_hedged 12/42  urinary_frequency_null_historical 1/40
        urinary_frequency_null_metaphor 7/44  urinary_frequency_null_thirdparty 1/44
        urinary_frequency_true 11/46
      was                 0.112     30   0.022   0.022   0.133
        urinary_frequency_false 1/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_historical 22/40
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 3/44
        urinary_frequency_true 1/46
      minutes             0.109     17   0.109   0.000   0.057
        urinary_frequency_null_historical 3/40  urinary_frequency_null_metaphor 2/44
        urinary_frequency_null_thirdparty 7/44  urinary_frequency_true 5/46
      normal              0.109     14   0.022   0.130   0.033
        urinary_frequency_false 6/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 3/42  urinary_frequency_null_historical 1/40
        urinary_frequency_null_thirdparty 2/44  urinary_frequency_true 1/46
      so                  0.109     18   0.109   0.000   0.062
        urinary_frequency_null_adjacent 1/40  urinary_frequency_null_hedged 9/42
        urinary_frequency_null_historical 1/40  urinary_frequency_null_metaphor 1/44
        urinary_frequency_null_thirdparty 1/44  urinary_frequency_true 5/46
      started             0.109     17   0.130   0.022   0.048
        urinary_frequency_false 1/46  urinary_frequency_null_adjacent 3/40
        urinary_frequency_null_hedged 2/42  urinary_frequency_null_historical 2/40
        urinary_frequency_null_thirdparty 3/44  urinary_frequency_true 6/46
      a                   0.104     84   0.261   0.196   0.300
        urinary_frequency_false 9/46  urinary_frequency_null_adjacent 13/40
        urinary_frequency_null_hedged 8/42  urinary_frequency_null_historical 17/40
        urinary_frequency_null_metaphor 15/44  urinary_frequency_null_thirdparty 10/44
        urinary_frequency_true 12/46
      any                 0.104      7   0.022   0.109   0.005
        urinary_frequency_false 5/46  urinary_frequency_null_metaphor 1/44
        urinary_frequency_true 1/46
      going               0.104     55   0.217   0.261   0.157
        urinary_frequency_false 12/46  urinary_frequency_null_hedged 8/42
        urinary_frequency_null_historical 13/40  urinary_frequency_null_metaphor 1/44
        urinary_frequency_null_thirdparty 11/44  urinary_frequency_true 10/46
      it's                0.102     28   0.174   0.109   0.071
        urinary_frequency_false 5/46  urinary_frequency_null_adjacent 3/40
        urinary_frequency_null_hedged 7/42  urinary_frequency_null_metaphor 4/44
        urinary_frequency_null_thirdparty 1/44  urinary_frequency_true 8/46
      toilet              0.100     34   0.196   0.109   0.095
        urinary_frequency_false 5/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 4/42  urinary_frequency_null_historical 3/40
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 11/44
        urinary_frequency_true 9/46
      had                 0.093     27   0.043   0.022   0.114
        urinary_frequency_false 1/46  urinary_frequency_null_adjacent 2/40
        urinary_frequency_null_hedged 3/42  urinary_frequency_null_historical 15/40
        urinary_frequency_null_metaphor 3/44  urinary_frequency_null_thirdparty 1/44
        urinary_frequency_true 2/46
      be                  0.090     20   0.022   0.000   0.090
        urinary_frequency_null_adjacent 2/40  urinary_frequency_null_hedged 13/42
        urinary_frequency_null_historical 3/40  urinary_frequency_null_thirdparty 1/44
        urinary_frequency_true 1/46
      again               0.087      7   0.087   0.000   0.014
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 2/44
        urinary_frequency_true 4/46
      is                  0.087     20   0.043   0.130   0.057
        urinary_frequency_false 6/46  urinary_frequency_null_adjacent 2/40
        urinary_frequency_null_hedged 2/42  urinary_frequency_null_metaphor 5/44
        urinary_frequency_null_thirdparty 3/44  urinary_frequency_true 2/46
      like                0.087     12   0.087   0.000   0.038
        urinary_frequency_null_adjacent 3/40  urinary_frequency_null_hedged 4/42
        urinary_frequency_null_metaphor 1/44  urinary_frequency_true 4/46
      twenty              0.087      9   0.087   0.000   0.024
        urinary_frequency_null_historical 2/40  urinary_frequency_null_thirdparty 3/44
        urinary_frequency_true 4/46
      and                 0.083     83   0.217   0.217   0.300
        urinary_frequency_false 10/46  urinary_frequency_null_adjacent 6/40
        urinary_frequency_null_hedged 2/42  urinary_frequency_null_historical 16/40
        urinary_frequency_null_metaphor 16/44  urinary_frequency_null_thirdparty 23/44
        urinary_frequency_true 10/46
      day                 0.080     14   0.109   0.065   0.029
        urinary_frequency_false 3/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 1/42  urinary_frequency_null_historical 3/40
        urinary_frequency_null_thirdparty 1/44  urinary_frequency_true 5/46
      go                  0.078     22   0.130   0.109   0.052
        urinary_frequency_false 5/46  urinary_frequency_null_adjacent 1/40
        urinary_frequency_null_hedged 5/42  urinary_frequency_null_historical 2/40
        urinary_frequency_null_metaphor 1/44  urinary_frequency_null_thirdparty 2/44
        urinary_frequency_true 6/46
      twice               0.077      7   0.087   0.022   0.010
        urinary_frequency_false 1/46  urinary_frequency_null_metaphor 2/44
        urinary_frequency_true 4/46
      ... and 86 more, counted above but not shown```
