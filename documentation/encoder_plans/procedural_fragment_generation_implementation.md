# Implementation Plan: Procedural declarative multi-symptom fragments (12.1 / 12.3, v1)

**Status: not built. This is the step-2 review-and-correction pass over
`documentation/encoder_plans/procedural_fragment_generation_provisional.md`,
expanded into tasks that can each be handed to a fresh chat.**

Read first: `arch_training.md` sections 2, 3 (cluster markers), 4 (`null_on`),
5, 6, 7, 8, 9 ("What sixty-seven real submissions show"), 12.1, 12.3, 12.5,
12.7, 12.8. Then `scripts/synthetic_data/manifest.py`,
`scripts/synthetic_data/recombine.py` (`build_pools`, `select_fragments`,
`label_vector`) and `scripts/encoder_training/dataset.py`
(`_decisive_fragment`).

**The provisional plan stays on disk unchanged.** Where this document disagrees
with it, this document is the one to build from. The disagreements are listed
under "What changed from the provisional plan", because two of them change what
the ticket costs by a large factor.

---

# Orientation for someone new to this

The encoder reads a patient's free text and answers seven yes/no/not-mentioned
questions about it. It is trained on synthetic data: a few hundred hand-written
sentence fragments, recombined into thousands of examples. The label is decided
*before* the text is drawn, so a label can never be wrong about its own text
(`arch_training.md` section 2).

Every fragment we have makes **exactly one claim**, and every generated example
holds exactly one claim-bearing fragment. The sixty-seven real submissions say
the median patient asserts something about **two** of the six signals in one
message, and the longest asserts all six. So the model has been trained on
roughly the right amount of text with a fraction of the clinical density in it,
and may have learned an unstated one-claim-per-message prior.

Writing multi-claim fragments by hand does not scale: six symptoms with
true/false states is 472 distinct claim combinations at two-to-four symptoms per
sentence, and there are 50 conditions behind this one. **This ticket builds them
procedurally instead**: a small authored inventory of symptom noun phrases, two
sentence frames, and a generator that composes them into fragments whose label
vector is known before the text exists.

The label-first invariant is not weakened by this — it is strengthened. A
procedural fragment's label is not judged from its text at all; the text is
*constructed from* the label.

---

# Plan

Produce a library of declarative multi-symptom fragments —

> "I have had a fever and blood in my wee, but not any pain when I pee."

— each carrying a **per-line label vector** (`fever_present: true`,
`haematuria_present: true`, `dysuria_present: false`, everything else `null`),
and make the recombination engine able to draw one.

Three things have to be true before such a fragment may enter an example:

1. A fragment can *carry* more than one label. Today a fragment's label comes
   from its library's `fragment_type` plus one `signal_key`, which is one value
   for one signal. That is `arch_training.md` 12.3's per-line label vector and
   the JSONL library format, and **it is not built**.
2. The engine's "one decisive fragment" rule generalises correctly to "at most
   one *assertion per signal* per example" — so a fever/dysuria fragment can
   never sit beside a dysuria companion.
3. The new library cannot quietly take over. It is surface-monotone by
   construction (two frames), so if it dominated the decisive draw it would
   trade the one-claim prior for a one-*frame* prior. A share flag, default
   zero, is what stops that.

Then generate two arms, train, and score them on the sixty-seven submissions.

---

# Scope

**In scope**

* A JSONL fragment-library format with a per-line label vector, declared in the
  manifest (`format`), alongside the existing `.txt` format.
* Generalising `build_pools`, `select_fragments` and `label_vector` from
  "a fragment has one signal" to "a fragment has a label vector".
* An authored phrase inventory: for each of six symptom signals, noun and gerund
  phrases in a bare and a negated surface form.
* A frame set: one positive base and one negative base, with the conjunction and
  punctuation engine of the provisional's Phase 2.
* A `build-declarative` subcommand that expands inventory × frames into a
  committed JSONL library, deterministically, with a CI check that regeneration
  is a no-op.
* `--declarative-share`, default `0.0`, inert at zero.
* Lint: inventory purity, per-line vector validation, generated-library
  reporting, and the near-duplicate report's treatment of generated libraries.
* Sidecar and `dataset.py` changes so a multi-signal fragment's provenance is
  readable.
* Two generated arms, trained and scored.

**Out of scope** (and each one is a deliberate deferral, not an oversight)

* Everything the provisional lists as out of scope: adjective frames ("I've been
  feverish"), opener variation ("I've had", "I've got", "Since Tuesday"), null
  states inside a declarative sentence, and round-robin fragment reuse.
* Templating the **filler** libraries (`arch_training.md` 12.7 step 5). It is
  the cheaper, lower-risk use of procedural generation and it is a separate
  ticket. This ticket does not depend on it and does not do it.
* Templating the **clinical single-signal** libraries (12.7 step 8).
* Five- and six-symptom sentences.
* `recent_uti_present` (DD9).
* Migrating the 49 existing `.txt` libraries to JSONL (DD2).
* Fixing `merge-folds` to accept a multi-key tree, and the multi-head training
  that would bank the extra supervision (12.2). See DD18 for what that costs
  this ticket.

---

# What changed from the provisional plan

Nine corrections. The first two are the ones that matter for planning.

**1. The provisional describes the text generator, which is roughly a third of
the work.** Phases 1 to 4 produce strings. Nothing in the current pipeline can
*hold* one of those strings: a fragment's label is `fragment_type` (one of five
words, library-wide) plus one `signal_key`, and there is no field in which "this
line asserts fever true and dysuria false" can be written. That is
`arch_training.md` 12.3, listed at 12.7 **step 7** and explicitly still blocked.
So this ticket is "build 12.3, then use it for one thing", and Tasks 1, 2 and 6
are 12.3. Planning it as "write a sentence templating script" will
underestimate it by about 3×.

**2. Template ID is the wrong cluster key here, and 12.1 says template ID.** In
12.1's case — templating one library — every expansion of a template shares that
template's *label*, so the template is the idea and hashing on it is right. Here
each expansion carries a *different* label. Hashing on the frame would put every
fragment into one of two clusters and the split would be meaningless. The
cluster key is the asserted label content instead (DD6).

**3. "40 or more templates per library" does not bind here.** That rule
(12.1) exists because templating multiplies surface forms per idea. Here the
frames multiply *labels*, so two frames still generate hundreds of ideas. The
risk the rule protects against — a library that looks richer than its template
count — is real and is handled by capping the library's share of the decisive
draw (DD8) and by reporting frames-per-library in the lint, not by inventing 38
more frames the provisional put out of scope.

**4. `recent_uti_present` is excluded.** It is not a symptom-presence signal; its
label turns on a 30-day window and six written policy rules (`arch_training.md`
section 9 and the manifest's `policy` notes). "I have had a recent urine
infection" is a policy judgement wearing a declarative sentence's clothes. Six
signals, not seven (DD9).

**5. Phase 3 is authoring, not auditing.** "Isolate the noun/gerund variants of
the existing 40 examples into a `v1_declarative` library" reads as extraction.
It has to be authoring: a phrase inventory of short noun and gerund phrases, and
a check that no inventory entry is a library line (DD10). Lifting whole lines
would put train text inside val fragments.

**6. Negation needs a second surface form per phrase.** "I have not had a
fever" works; "I have not had burning when I pee" does not; "I have not had any
burning when I pee" does. The inventory carries a `negated` form per phrase,
defaulting to `"any " + text` and overridable (DD11).

**7. The nocturia / urinary-frequency pair stays undeclared per line.** Those 14
manifest cells are undeclared for a reason (`arch_training.md` section 4) and a
per-line vector does not by itself resolve them. v1 emits *no key* for one of
that pair when only the other is in the sentence (DD14).

**8. Both open questions are answered.** JSONL: yes, for the new library only —
the existing 49 text libraries stay text, because migrating them changes every
`fragment_id` and every golden digest and buys nothing (DD2). Labelling policy:
the inventory admits only phrases whose label is unambiguous under section 9,
which makes the policy a per-*phrase* decision made once, not a per-line one
(DD10). Note the flip side, recorded in DD18: because these fragments are
policy-free by construction, they teach the model nothing about the hard
boundary cases, and must not be read as growth in the hard classes.

**9. Volume has to be capped, and the provisional does not mention volume.**
Full enumeration is ~460 label combinations × 2 clause orders × phrase choices —
tens of thousands of lines against 49 hand-written libraries totalling
2,503 lines. Uncapped, the decisive fragment in a typical example would be a
procedurally generated stiff sentence. DD15 caps it; DD8 controls the mix
independently.

---

# Design decisions

### DD1 — The generated library is a committed build artefact, not a runtime expansion

`build-declarative` writes a file into `data/synthetic/` and that file is
committed. Recombination reads it exactly as it reads any other library.

The alternative — expand templates inside `build_pools` — was rejected on three
grounds. A committed file can be **read by a human**, which is how every other
library in this tree is quality-controlled and the only mechanism that would
catch "I have not had any getting up in the night" before it reaches training
text. It keeps the split machinery untouched: fragments get ids, cluster keys
and split assignments the same way everything else does. And it keeps generation
reproducible without adding a second source of randomness to a generator whose
determinism is pinned by a golden digest.

The cost is that regenerating the library is a deliberate act and a reviewable
diff. That is the point.

### DD2 — A JSONL library format, declared per library, and no migration

The manifest gains an optional `"format"` field on a library entry: `"text"`
(default, current behaviour) or `"jsonl"`. A JSONL library's lines are objects:

```json
{"text": "I have had a fever and blood in my wee, but not any pain when I pee.",
 "labels": {"fever_present": true, "haematuria_present": true,
            "dysuria_present": false, "urinary_frequency_present": null,
            "flank_pain_present": null},
 "cluster": "decl:dysuria-fever+haematuria+",
 "meta": {"frame": "pos_base_mixed", "arity": 3}}
```

`labels` **is** the per-line vector. A signal present with `true`/`false` is
asserted; present with `null` is declared silent on that line; **absent is
undeclared**, exactly as in `null_on` (section 4), and earns no key downstream.
`nocturia_present` is absent above — see DD14.

A JSONL library entry in the manifest declares `fragment_type: "declarative"`
(a new member of `FRAGMENT_TYPES`) and **no** `signal_key` and **no** `null_on`:
both of those are library-level facts and this library's facts are per line.
`parse_manifest` must reject a JSONL library that declares either, and reject a
text library that declares `format: "jsonl"`'s fields, for the reason section 4
gives for not letting a library declare `null_on` for its own signal — two
sources for one value is one that can disagree with itself.

**No migration.** The 49 text libraries stay text. Their `fragment_id` is a hash
of the text and their split is a hash of the cluster key, so a format change
that altered either would move every dataset ever generated. There is no
benefit on offer: a single-signal library's vector is already derivable from
`fragment_type` + `null_on`, which is what `label_vector` does today.

### DD3 — Four states per (line, signal), and `ambiguous` is not one of them

The states are `true`, `false`, `null` (declared silent) and undeclared. The
existing `ambiguous`/`confounder` fragment types — the hard cases that feed
`null_ambiguous` examples — are **library-level** properties of hand-written
libraries and stay that way. A JSONL line never enters the `ambiguous` pool.

This is deliberate and it is a limitation worth stating: procedural declarative
fragments are all easy cases. They cannot produce a hedge, a metaphor or a
third-party attribution, because those are exactly the things a fixed frame
cannot express. `--null-ambiguous-ratio` keeps meaning what it means, and the
hard-case libraries stay the only source of hard cases.

### DD4 — The pools select on the label vector, not on `fragment_type`

`build_pools` currently reads `f.signal_key == signal_key and f.fragment_type in
types`. That becomes a lookup on the fragment's vector:

| the fragment's value for the run's signal | pool |
|---|---|
| `true` | `positive` |
| `false` | `negative` |
| `null` (declared silent) | eligible as a **companion** if it asserts some *other* signal; eligible as filler-equivalent otherwise |
| undeclared | ineligible, as today |

Text libraries derive their vector from `(signal_key, fragment_type)` plus
`null_on`, unchanged, so **every existing pool comes out byte-identical**. This
is the single refactor that has to be got right and it is the one to write a
golden-digest test around before touching (Task 2).

Note what falls out of it for free: a declarative fragment asserting dysuria and
nocturia and declared `null` on fever is a **companion for the fever run that
carries two signals of clinical language**. That is `arch_training.md` 12.8's
"structural nulls should shrink as 12.2 and 12.3 grow", arriving as a side
effect rather than as separate work.

### DD5 — At most one *assertion per signal* per example

Today's rule is "one decisive fragment, and at most one companion per signal"
(`select_fragments`, DD8 of the multi-symptom plan). Generalised: the set of
signals an example's fragments *assert* must have no duplicates.

So the companion draw's exclusion list is no longer `[companion.signal_key]` but
"every signal already asserted by anything chosen", seeded from the decisive
fragment. A fever/dysuria decisive fragment excludes the whole dysuria signal
from the companion draw, not just its own library.

`label_vector`'s `AssertionError` on two assertions stays as the backstop and
must keep firing — it is the only thing standing between an eligibility bug and
a permanently wrong training label. Extend it to iterate a vector rather than a
scalar `signal_key`.

### DD6 — The cluster key is the asserted label content

`cluster` is `"decl:"` followed by every asserted signal in sorted order with
its polarity: `decl:dysuria-fever+haematuria+`. Signals the line is silent or
undeclared on do not appear.

Two lines in one cluster differ only in which phrase was chosen for each symptom
and which comma style the frame used. They are near-duplicates by any reading
and belong in the same split. Two lines in *different* clusters make different
claims, which is the discrimination we want measured rather than leaked.

Roughly 460 clusters at six signals and arity 2–4 (DD15 excludes arity 1), which is a healthier cluster
count than any existing library has and comfortably clears the fold-bucket
guard. Two alternatives were rejected: hashing the frame (two clusters — the
split collapses), and hashing the symptom *set* ignoring polarity (56 clusters,
each holding every polarity variant, so cluster mass is wildly unequal and a
single size-4 cluster can carry several hundred lines into one split).

**Consequence for the lint**, and it is not optional: the cross-split
near-duplicate report compares character similarity within a library.
"I have had a fever and nocturia" against "I have had a fever but not any
nocturia" scores far above the 0.60 threshold and lands in *different* clusters
by design. Left alone, this library would emit thousands of pairs and make the
report unreadable for every other library. DD16.

### DD7 — The frames are label-neutral by construction, and the sidecar proves it

Every frame generates every polarity: the positive base produces all-true
sentences *and* the true-then-false mixed sentences, and the negative base
mirrors it. So frame identity does not correlate with the primary label, in the
same way and for the same reason that companion *count* is drawn blind to the
label mode (`arch_training.md` section 5).

"By construction" is a claim, so it gets a check: the stats sidecar gains
`declarative.frame_by_label_mode`, the exact analogue of
`companions.count_by_label_mode`, and a run whose rows disagree is void rather
than reinterpretable.

The residual risk this does *not* remove: within an example, "but not" is a
perfect cue for a `false` label on whatever follows it. That is a true fact
about English and we are teaching it, but it is being taught by one construction
only. Opener and construction variation is the provisional's out-of-scope list
and the natural v2.

### DD8 — `--declarative-share`, default `0.0`, and at zero the path is skipped

`P` is the probability that the **decisive** fragment is drawn from the
declarative pool rather than from the hand-written pool for the same label,
where both are non-empty.

At `P = 0.0` no draw is made, no randomness is consumed, and the fragments
chosen for a given seed are exactly the ones chosen today — pinned by the
existing golden digest. This is the same shape as `--companion-share` and for
the same reason (DD4 of the multi-symptom plan): a feature that cannot be turned
fully off cannot be compared against its own absence.

The flag exists because the declarative library will be larger than the
hand-written libraries and a uniform draw over a merged pool would make the stiff
frame the *typical* decisive fragment. A share flag decouples "how many lines
were generated" from "how much of the dataset they are", which is the only way
DD15's cap and the register risk stay independently adjustable.

Declarative fragments remain eligible as **companions** at `P = 0` — a fragment
that is `null` on the run's signal was never on the decisive path. If that turns
out to be unwanted the flag needs a second dimension; it is not expected to and
v1 does not add one.

### DD9 — Six signals, not seven: `recent_uti_present` is excluded

Its labelling rule is a 30-day window plus the six policy rules of section 9,
and 20 of the manifest's 24 `policy` pairs are on it. A declarative frame cannot
place an infection inside a window, so every sentence it could generate would
need a policy judgement — which is precisely what the inventory is designed to
exclude (DD10). Excluding it costs arity: 6 signals give 56 symptom sets at
arity 1–4 rather than 98.

### DD10 — The inventory is authored, policy-free, and checked against the libraries

`data/synthetic/conditions/uti/declarative/phrases.json`, keyed by signal:

```json
"dysuria_present": {
  "phrases": [
    {"text": "pain when I pee", "negated": "any pain when I pee"},
    {"text": "burning when I wee", "negated": "any burning when I wee"},
    {"text": "stinging when I pass urine", "negated": "any stinging when I pass urine"}
  ]
}
```

Three rules, all checkable, all in the lint (Task 5):

* **Grammatical:** each phrase is a noun phrase or a gerund phrase that reads
  correctly after both bases. Not machine-checkable; enforced by a fixed
  maximum length (four words, DD11's `negated` excepted) and by review.
* **Policy-free:** a phrase is admitted only if its label under both bases is
  unambiguous under section 9. "feeling hot and cold" is *not* admitted — it is
  one of the six undeclared policies. "a fever" is.
* **Not a library line:** no inventory `text` or `negated` may equal any
  existing library line after `normalise()`. A hard error. This is what keeps
  hand-written train fragments out of generated val fragments; vocabulary
  overlap across splits is unavoidable and always has been, whole-line overlap
  is not.

Aim for 4 to 6 phrases per signal. More than that multiplies surface forms
inside a cluster and buys nothing the split can see.

### DD11 — Negation is a per-phrase surface form

`negated` defaults to `"any " + text` and is written out explicitly for every
phrase anyway, because the default is wrong often enough ("a fever" → "any
fever", not "any a fever") that a silent default would ship broken English. The
generator uses `text` after a positive base and `negated` after "but not" or a
negative base.

### DD12 — Conjunctions and punctuation: the provisional's Phase 2, plus one variant

Kept as written. Length 1 returns the item; length 2 joins with `and`
(positive) or `or` (negative); length 3+ joins all but the last with commas then
the conjunction. Bases are "I have had" and "I have not had", chosen by whether
the sentence opens on the true block or the false block (the provisional's DD4).
Mixed sentences use "…, but not …" and "…, but I have had …".

The one addition: **Oxford comma is a per-line coin flip**, drawn from the
seeded RNG. Patients are inconsistent about it and emitting only one form would
put a punctuation habit into every multi-symptom sentence in the dataset. It
does not change the label, does not change the cluster, and costs one line of
code.

### DD13 — Polarity blocks are grouped by the generator, never by the author

The provisional's DD1 argument is right and the implementation follows it
exactly: sample a symptom set and a polarity for each, then **sort** into a true
block and a false block, then choose which block leads. TFT and FTF are never
generated because the sort makes them unreachable, not because a rule rejects
them. The clause order (T-first or F-first) is a fair coin, so both bases get
comparable mass.

### DD14 — The nocturia / urinary-frequency pair stays undeclared per line

When a line asserts nocturia and does not mention urinary frequency, it emits
**no key** for `urinary_frequency_present`, and vice versa. Section 4 records
why: "up three times in the night for a wee" genuinely asserts both, the
overlap is a per-line fact, and nobody has decided the general rule.

A per-line vector *could* express the decision, and that is the temptation to
resist here: deciding it inside a generator, silently, across hundreds of lines,
is the opposite of how every other labelling decision in this tree was made.
Deciding it is a separate ticket and its natural home is the inventory, where it
would be six phrase-level decisions rather than one blanket one.

Cost: a declarative line mentioning exactly one of the pair is ineligible for
the other's run — not wrongly labelled, just unavailable. Roughly a quarter of
lines are affected for one of the two signals.

### DD15 — Volume is capped and stratified by arity

`build-declarative --target-count N` samples rather than enumerates. The
sampling is stratified: allocate the budget across arities 2, 3 and 4 by a
declared weight, then across clusters within an arity uniformly, then draw
phrases and frame variants inside a cluster. Arity 1 is **excluded** — a
one-symptom declarative sentence is what the hand-written libraries already are,
and worse.

Recommended v1 budget: **1,000 lines**, weighted 0.5 / 0.35 / 0.15 across
arities 2 / 3 / 4. That gives roughly two lines per cluster, which is enough for
the cluster to be a real cluster and few enough that the library does not
dominate a merged pool even before `--declarative-share` is considered.

The realised per-cluster and per-arity counts go in the lint report. A budget so
small that most clusters are empty, or so large that clusters carry a dozen
near-identical siblings, are both visible there.

### DD16 — The near-duplicate report treats generated libraries separately

`cross_split_near_duplicates` gains a library filter, and generated libraries
are reported in their own section with a count and no pair listing.

The report's purpose is to find *unintended* twinning in hand-written libraries
(`arch_training.md` section 3). In a generated library, high character
similarity between different clusters is the expected output of a fixed frame,
carries no information, and would bury the signal in every other library's rows.
Reporting the count separately keeps the fact visible without the noise.

### DD17 — `GENERATOR_VERSION` 4, and what becomes non-comparable

The version goes to 4 in the commit that lands Task 2, because that is where a
fragment's pool membership starts being computed from a vector. Every number in
`arch_training.md` section 10 is already at version 2 or 3; version 4 datasets
are comparable with neither, and each table keeps its own version line.

The golden-digest test is the mechanism that says whether the bump is cosmetic
or real. **Expected: byte-identical output at `--declarative-share 0` with the
declarative library present in the manifest but no signal drawing from it**, and
the test should assert exactly that rather than being updated to whatever comes
out. If it moves, something in DD4's refactor changed a pool, and that is a bug
until proven otherwise.

### DD18 — What this buys, and what it does not

**It buys claim density.** Section 9's measured failure is that no head has seen
a message asserting several things at once. After this, examples exist where one
fragment asserts three. That is the deliverable.

**It does not buy supervision per example unless the multi-key path is used.**
At `--emit-signals primary` — every arm trained so far — a fragment asserting
fever, dysuria and haematuria emits one key and the other two assertions are
thrown away. Banking them needs `--emit-signals all`, which is built and
unmeasured, and `merge-folds`, which refuses a multi-key tree (12.2). That is
out of scope here and it is the obvious next ticket.

**It does not add hard cases.** Everything generated is an easy, unhedged,
canonical claim (DD3). A dataset that grows 30% in line count has not grown 30%
in difficulty, and the lint's per-sub-class counts are where to look before
believing otherwise.

**The standing caveat from 12.7 applies in full.** "Nothing on this list is
worth starting before the real-text set is labelled and scored." The sixty-seven
submissions are on disk and unlabelled; their provenance is unresolved and gates
committing them. If this ticket is built before that, its measurement arm cannot
run and the ticket delivers a capability with no evidence attached. That is a
legitimate choice — the machinery is on the critical path for several later
tickets — but it should be made knowingly rather than discovered at Task 7.

---

# Predictions, recorded before the run

Written down now so the run can disagree with them.

1. **Byte-identical output at `P = 0`.** The golden digest holds after Tasks 1,
   2 and 4. If it does not, DD4's refactor is wrong.
2. **Structural nulls fall further at a given `--companion-share`.** Declarative
   fragments are eligible companions carrying two-to-four signals of clinical
   language each, so filler-only examples per 10,000 drop below the 1,118
   measured at `P_companion = 0.5`.
3. **The invented-symptom rate improves and the `null` recall does not collapse.**
   The 47%–89% false-positive rate on the sixty-seven submissions is the number
   to watch. Prediction: it improves for the signals with the most inventory
   phrases and moves least for `flank_pain_present`.
4. **`false` recall improves most.** Explicit denials are 13% of the real set and
   "but not X" is the construction patients use for them.
5. **Near-duplicate pairs in the *hand-written* libraries do not change at all.**
   If they do, DD16's filter is wrong.
6. **The register risk shows up as a gap between arms at high `P`.** An arm at
   `P = 0.6` scores worse on the sixty-seven than an arm at `P = 0.3`, because
   the frame becomes the typical decisive sentence. If `P = 0.6` wins, DD8's
   whole argument is wrong and that is worth knowing.

---

# Task 1: The JSONL library format and per-line label vectors

## A. State of the world

Nothing in this plan is built. `manifest.py` reads `.txt` libraries only; a
fragment's label for its own signal comes from `LibrarySpec.fragment_type` and
its label for every foreign signal from `LibrarySpec.null_on`. `Fragment` has a
scalar `signal_key` and a scalar `fragment_type`. This task adds the second
format and the vector, and changes no behaviour for existing libraries.

## B. Files and deliverables

* `scripts/synthetic_data/manifest.py` — `FRAGMENT_TYPES` gains `"declarative"`;
  `LibrarySpec` gains `format: str = "text"`; `Fragment` gains
  `labels: Mapping[str, bool | None]` and a `value_for(signal)` accessor
  returning `True` / `False` / `None` / a sentinel for undeclared;
  `parse_manifest` validates the format field and the mutual exclusions of DD2;
  a new `read_jsonl_library` beside `read_library`.
* `data/synthetic/manifest.json` — no change in this task.
* `tests/test_synthetic_recombination.py` — new cases.

**Deliverables:** a manifest that can declare a JSONL library; a `Fragment` that
carries a label vector however it was loaded; and a test asserting that every
existing text library's derived vector is exactly what `label_vector` computes
from `(signal_key, fragment_type, null_on)` today.

## C. Instructions

1. Add `value_for` on `Fragment` **first**, implemented for text libraries only,
   and prove it against the current behaviour before any JSONL exists. Its
   contract: own signal → `FRAGMENT_TYPE_LABELS[fragment_type]`; a signal in
   `null_on` → `None`; anything else → the undeclared sentinel. Use a module
   sentinel object, not `None`, for undeclared — the whole of section 7's
   missing-key-versus-`null` distinction rides on those two being different.
2. Then add `labels` to `Fragment`, populated for text libraries by the same
   derivation, so the two agree by construction.
3. `read_jsonl_library`: one JSON object per line; require `text`, `labels`,
   `cluster`; reject a line whose `labels` names a signal not in the ruleset,
   whose `labels` is empty, or whose `text` is blank after `normalise()`.
   `fragment_id` is `make_fragment_id(library, text)` unchanged. `cluster_id`
   is the line's `cluster`, namespaced `{library}:{cluster}` exactly as a
   `[c01]` marker is. The split comes from `assign_split(cluster_key(...))`,
   untouched.
4. `parse_manifest`: `format` defaults to `"text"`. A `"jsonl"` library must
   declare `fragment_type: "declarative"` and must **not** declare `signal_key`
   or `null_on`. A `"text"` library must not declare `fragment_type:
   "declarative"`. Error messages name the library and the field.
5. `deduplicate` is global and errors on a cross-library duplicate whose
   `fragment_type` disagrees. A declarative line colliding with a hand-written
   one must be an error, not first-wins; check that the existing code path
   reaches that conclusion for the new type and extend it if not.
6. Tests: an existing-libraries vector-equivalence test (the important one); a
   JSONL round trip; each rejection above; and a fragment whose `labels` omits a
   signal returning the undeclared sentinel rather than `None`.

---

# Task 2: The engine — pools, draws, vectors, and `--declarative-share`

## A. State of the world

Task 1 has landed: fragments carry a label vector and JSONL libraries can be
declared, but nothing draws from one. `build_pools` still selects on
`signal_key` and `fragment_type`; `select_fragments` excludes companions by
`signal_key`; `label_vector` reads a scalar `signal_key` per fragment. This task
generalises all three and adds the share flag. No new data yet.

## B. Files and deliverables

* `scripts/synthetic_data/recombine.py` — `build_pools` (DD4), `select_fragments`
  and `_draw_companion` (DD5), `label_vector` (DD5), `GENERATOR_VERSION` → 4,
  `DEFAULT_DECLARATIVE_SHARE = 0.0`, a `declarative` pool on `FragmentPools`,
  and `declarative.frame_by_label_mode` in `build_stats` (DD7).
* `scripts/synthetic_data/__main__.py` — `--declarative-share`.
* `tests/test_synthetic_recombination.py`.

**Deliverables:** `--declarative-share 0.0` produces byte-identical output to
today against the real libraries, pinned by the existing golden digest; at
`P > 0` against a synthetic fixture library, the decisive fragment comes from
the declarative pool at approximately rate `P` and no example ever asserts one
signal twice.

## C. Instructions

1. **Write the byte-identity test before changing anything.** Generate the real
   `fever_present` train split at the current code, digest it, and assert the
   digest after each subsequent step of this task. Prediction 1 is the thing
   this task is most likely to break silently.
2. `build_pools`: replace the two `fragment_type`/`signal_key` reads with
   `value_for(signal_key)` per DD4's table. Keep the filler branch keyed on
   `fragment_type == "filler"` — filler-ness is a library property and stays
   one. Declarative fragments valued `True`/`False` for the run's signal go into
   a **separate** `declarative_positive` / `declarative_negative` pool, not into
   `positive` / `negative`; DD8 needs them separable. Declarative fragments
   valued `None` join the companion pool keyed by *every* signal they assert.
3. `_check_pools`: an empty declarative pool is fine and must not raise —
   `P = 0` and no declarative library at all are both normal states. It raises
   only if `P > 0` and the pool for a required label mode is empty.
4. `select_fragments`: after choosing the label mode, if `P > 0` and the
   matching declarative pool is non-empty, draw a uniform in `[0, 1)` and take
   the decisive fragment from the declarative pool when it is below `P`. Draw
   **nothing** when `P == 0` — the branch is skipped, not taken with probability
   zero, or the RNG stream moves and prediction 1 fails.
5. `_draw_companion`'s exclusion list becomes the set of signals already
   asserted by the chosen fragments, seeded from the decisive fragment's
   asserted set (DD5). The `used_signals` list is already there; it needs to
   start non-empty and to take a set rather than one key.
6. `label_vector`: iterate `fragment.labels` rather than
   `(signal_key, null_on)`. The four-row table in its docstring is unchanged and
   is still the specification — only the source of a fragment's per-signal state
   changes. Keep the two-assertions `AssertionError` and extend its message to
   name the signal and both fragments.
7. `companion_bounds` counts companion *signals*; a declarative companion
   asserting three signals occupies three of them for exclusion purposes but is
   one slot. Check the ceiling arithmetic in `generate()` still holds and adjust
   the message if not — a wrong ceiling here surfaces as a mid-run
   `PoolExhaustedError`, which is exactly what that check exists to prevent.
8. `build_stats`: add `declarative.count_by_label_mode` and
   `declarative.frame_by_label_mode`, reading the frame from the fragment's
   JSONL `meta.frame`. These are the DD7 leak detectors.
9. Tests: golden digest at `P = 0`; the RNG stream unchanged at `P = 0`; a
   fixture declarative library exercising the DD5 exclusion (a fever/dysuria
   decisive fragment must never draw a dysuria companion); `label_vector` on a
   multi-signal fragment; the ceiling check with a three-signal companion.

---

# Task 3: The phrase inventory

## A. State of the world

Tasks 1 and 2 have landed: the pipeline can hold and draw a multi-signal
fragment, and there are none. This task is library work, not code — the
equivalent of writing a fragment library, and it should be reviewed the way one
is.

## B. Files and deliverables

* `data/synthetic/conditions/uti/declarative/phrases.json` — new.
* `documentation/encoder_plans/fragment_authoring_prompts.md` — a section for
  this, if the authoring is LLM-assisted.

**Deliverables:** 4 to 6 phrases per signal for six signals, each with a bare
and a negated surface form, each policy-free, none equal to an existing library
line.

## C. Instructions

1. Signals: `fever_present`, `dysuria_present`, `urinary_frequency_present`,
   `nocturia_present`, `flank_pain_present`, `haematuria_present`. Not
   `recent_uti_present` (DD9).
2. Read the corresponding `_true.txt` library for each signal for vocabulary,
   and then **write phrases rather than extracting lines** (DD10). A phrase is a
   noun or gerund phrase of at most four words that reads correctly in all four
   positions: after "I have had", after "I have not had", after "but not", and
   after "but I have had".
3. Reject any phrase whose label is a judgement call. The six undeclared
   policies in `arch_training.md` section 9 are the list to check against:
   chills with no stated heat, sub-threshold numbers, confident hedges,
   unlateralised lower back, particulate urine, discomfort short of pain. None
   of them may enter the inventory.
4. Vary the register deliberately within a signal — "a fever", "a high
   temperature", "a raised temperature" — but do not chase count. Six phrases
   per signal is the ceiling, not a target.
5. Write `negated` out explicitly for every phrase (DD11) and read all six
   sentences each phrase can appear in, out loud, before committing it.
6. Run the Task 5 lint checks against the inventory before considering it done;
   the whole-line collision check in particular.

---

# Task 4: The generator and its committed output

## A. State of the world

The inventory exists and the engine can consume a JSONL library. This task
writes the expander and the file it produces.

## B. Files and deliverables

* `scripts/synthetic_data/declarative.py` — new: frames, the conjunction engine,
  the sampler.
* `scripts/synthetic_data/__main__.py` — a `--build-declarative` mode alongside
  `--lint` and `--find-fold-salt`, with `--target-count`, `--arity-weights`,
  `--seed`, `--out` and `--check`.
* `data/synthetic/conditions/uti/declarative/declarative_v1.jsonl` — generated
  and committed.
* `data/synthetic/manifest.json` — the library entry.
* `.github/workflows/` — the regeneration check in the existing unit job.
* `tests/test_synthetic_declarative.py` — new.

**Deliverables:** a committed ~1,000-line JSONL library; `--build-declarative
--check` exits non-zero if regenerating would change the committed file; CI runs
it.

## C. Instructions

1. The conjunction engine is the provisional's Phase 2, verbatim, plus DD12's
   Oxford-comma coin flip. Write it as a pure function of
   `(items, is_positive, oxford)` and unit-test it on lengths 1 to 4 in both
   polarities before anything else exists.
2. Two frames, named `pos_base` and `neg_base`, each with a mixed variant
   (`pos_base_mixed`, `neg_base_mixed`). The base is chosen by which polarity
   block leads (DD13), not by which is larger.
3. The sampler, in order: draw an arity from `--arity-weights`; draw that many
   distinct signals uniformly; draw a polarity per signal; **sort into blocks**;
   draw a leading block by fair coin; draw a phrase per signal; draw the Oxford
   flag; render. Everything from one seeded `random.Random`.
4. Compute the line's `labels` per DD2 and DD14: asserted signals take their
   polarity; the other in-scope signals take `null`; the nocturia /
   urinary-frequency partner of an asserted-but-unpartnered signal is **omitted**;
   `recent_uti_present` is always omitted.
5. Compute `cluster` per DD6. Deduplicate on normalised text within the run and
   redraw, capped, rather than emitting a duplicate — `deduplicate()` downstream
   would drop it anyway and the count would then not be the count.
6. Sort the output deterministically before writing (by cluster, then text) so
   the committed file is a stable diff. Write `\n`-terminated UTF-8, no trailing
   whitespace.
7. `--check` regenerates into memory and compares to the file on disk. Wire it
   into CI's unit job. This is what stops the committed library and the inventory
   drifting apart silently, and it is cheap.
8. Manifest entry: `name: "declarative_v1"`, `format: "jsonl"`,
   `fragment_type: "declarative"`, no `signal_key`, no `null_on`.
9. Read fifty lines of the output by hand before committing it, spread across
   arities. This is the last point at which broken English is cheap to fix.

---

# Task 5: The lint

## A. State of the world

The library is generated and committed and the engine can draw from it. Nothing
checks the inventory or reports on the new library, and the near-duplicate
report is about to become unreadable (DD16).

## B. Files and deliverables

* `scripts/synthetic_data/lint.py` — the inventory checks, the generated-library
  report, the near-duplicate filter.
* `tests/test_synthetic_recombination.py`.

**Deliverables:** `python -m scripts.synthetic_data --lint` reports, for every
generated library, its line count, cluster count, frames, and per-arity and
per-cluster distribution; reports its cross-split near-duplicate count as a
single number in its own section; and fails on an inventory phrase that
duplicates a library line.

## C. Instructions

1. `cross_split_near_duplicates` gains a parameter naming the libraries to
   report in full; generated libraries are counted and not listed (DD16). The
   hand-written libraries' output must be **unchanged**, character for character
   — prediction 5.
2. Inventory checks, all hard errors: a phrase longer than four words (bare
   form); a phrase or negated form equal to a library line after `normalise()`;
   a signal outside the ruleset; a signal with fewer than three phrases.
3. Per-signal lexicon check on the inventory, reusing `SIGNAL_LEXICONS`: a
   phrase for signal S that matches *another* signal's lexicon is reported. Not
   an error — the lexicons over-reach by design (section 4's 28 baselined hits)
   — but a phrase that trips another signal's lexicon is one to re-read.
4. The generated library's per-line vectors are checked against its own text
   only to the extent a lexicon can: a line asserting nothing about S that
   matches S's lexicon is reported. This will fire on the nocturia / frequency
   pair by construction (DD14) and those cells should be baselined explicitly, by
   pair, the way `ABSENT_PAIR_BASELINE` is.
5. Add `frames per library` and `clusters per split` to the report for every
   library, generated or not. `arch_training.md` 12.1 asks for exactly this and
   it is the number that stops a templated library looking richer than it is.

---

# Task 6: Downstream — sidecar provenance, `dataset.py`, `merge-folds`

## A. State of the world

Generation works end to end. The training-side loader still assumes a fragment
has one `signal_key`, and it will be handed fragments that have four.

## B. Files and deliverables

* `scripts/synthetic_data/recombine.py` — `_fragment_provenance`.
* `scripts/encoder_training/dataset.py` — `FragmentInfo`, `_decisive_fragment`.
* `scripts/encoder_training/merge.py` — the multi-key refusal message.
* `tests/` — the encoder-training dataset tests.

**Deliverables:** a fold tree generated at `--declarative-share 0.5` loads
without error, and `Example.decisive`, `.library`, `.subclass` and
`.resampling_unit` are correct for an example whose decisive fragment asserts
three signals.

## C. Instructions

1. `_fragment_provenance` writes `signal_key` per fragment. Add a `signals`
   list (every asserted signal) and a `labels` object (the full vector) beside
   it. Keep `signal_key` populated for text libraries so nothing that reads it
   breaks; write it as `null` for declarative fragments and make every consumer
   read `signals`.
2. `FragmentInfo` gains `signals: tuple[str, ...]`. `_decisive_fragment`'s test
   becomes `not is_filler and label_keys & set(signals)` rather than
   `signal_key in label_keys`. Its existing "more than one decisive" error is
   still correct and still fires for the reasons its docstring gives.
3. `resampling_unit` reads `cluster_key`, which a declarative fragment has
   (DD6), so it needs no change — confirm that with a test rather than by
   reading, because it is the number every confidence interval is computed from.
4. `merge.py` refuses a multi-key tree. That refusal is unchanged and correct;
   check its message still reads sensibly now that a *single*-key tree can
   contain multi-signal fragments, and amend it if it implies otherwise.
5. `Example.subclass` is `None` for every declarative fragment. Confirm the
   per-sub-class report tolerates that — structural nulls already produce
   `None`, so it should, but the slice sizes will move.

---

# Task 7: The arms, the run and the report

## A. State of the world

Everything is built and inert at the defaults. Nothing has been measured.

## B. Files and deliverables

* Generated fold trees for Arm 0 and Arm D.
* `reports/encoder_training/<date>.md` and its plain-English companion.
* `documentation/arch_training.md` section 10.

**Deliverables:** two arms trained and scored, on the fold-pooled test set and —
if and only if the sixty-seven submissions are labelled and their provenance
resolved — on the real set, with the predictions above marked held or not.

## C. Instructions

1. **Check the gate first (DD18).** If the sixty-seven are still unlabelled,
   this task produces a fold-pooled comparison only, and the report must say
   that the question the ticket exists to answer has not been asked. Do not
   substitute the fold-pooled number for it; section 9 is explicit that the two
   instruments answer different questions.
2. Arm 0: `--declarative-share 0`, current libraries, five folds, six signals.
   This is the control and it should be byte-identical to the existing version-4
   baseline; assert that rather than assuming it.
3. Arm D: `--declarative-share 0.3`, everything else identical. One flag, one
   difference.
4. If compute allows, a third arm at `P = 0.6` to test prediction 6. It is the
   only arm that can find the register failure, and it is the cheapest
   insurance against shipping it.
5. Score both on the fold-pooled test set per signal, and record the
   invented-symptom rate per signal from the real set if it is available.
6. Write the predictions' outcomes down whatever they say, including
   prediction 6.

---

# Task 8: Documentation

## A. State of the world

Everything else has landed.

## B. Files and deliverables

* `documentation/arch_training.md` — sections 3, 4, 5, 7, 8, 10, 12.1, 12.3,
  12.5, 12.7.
* `documentation/arch_encoder_training.md` — the loader's fragment contract.
* This file — a status line at the top.

## C. Instructions

1. Section 3: the `declarative/` folder in the tree, and what a JSONL library is.
2. Section 4: the `format` field, and that a JSONL library declares neither
   `signal_key` nor `null_on` and why.
3. Section 5: `--declarative-share`, and the fragment-count ceiling arithmetic
   with multi-signal companions.
4. Section 7: the sidecar's `signals` and `labels` per fragment.
5. Section 8: the new reports and the baselined DD14 cells.
6. Section 10: the arms and their numbers, with the version-4 line.
7. Section 12: mark 12.1 and 12.3 built **for the declarative case only**, and
   say plainly what is still not built — templated filler (12.7 step 5),
   templated clinical libraries (step 8), and the multi-key training path that
   would bank the extra supervision (12.2, DD18).
8. Keep the level right: design decisions and data flow, not a restatement of
   the code (`CLAUDE.md`).

---

# Cost

Rough, and the first two lines are where the estimate lives or dies.

| Task | What it is | Size |
|---|---|---|
| 1 | JSONL format, per-line vectors | medium — new format, but contained in `manifest.py` |
| 2 | Engine generalisation | **large** — touches the safety-critical path; the golden digest is the whole test strategy |
| 3 | Phrase inventory | small in code, real editorial effort, needs review |
| 4 | Generator and committed output | medium |
| 5 | Lint | small–medium |
| 6 | Downstream loader | small, easy to forget until a run fails |
| 7 | Arms and measurement | GPU time; gated on the real set |
| 8 | Documentation | small |

Tasks 1, 2 and 6 are `arch_training.md` 12.3 and would be needed by any
multi-symptom work, procedural or hand-written. Tasks 3, 4 and 5 are the
provisional plan. If the ticket has to be cut, cutting 3–5 leaves the per-line
vector machinery, which is the reusable half; cutting 1–2 leaves nothing that
can run.

---

# Open questions for the user

1. **Do we build this before the sixty-seven submissions are labelled?** DD18
   and 12.7 both say the measurement is what makes it an investment rather than
   a guess. Building Tasks 1–6 now and deferring Task 7 is a defensible middle,
   but it means shipping a feature whose default is off and whose value is
   unproven for as long as that lasts.
2. **Is 1,000 lines the right budget (DD15), and is `P = 0.3` the right arm?**
   Both are guesses. `P` is the one that actually decides how much of the
   dataset is stiff, and prediction 6 is the only thing that would catch a bad
   choice.
3. **Should the nocturia / urinary-frequency decision be made here after all
   (DD14)?** Deciding it in the inventory would be six phrase-level judgements
   and would unblock two large libraries as companions. It is a labelling
   decision that moves generated data, so it is being left out rather than made
   quietly — but it is cheaper to make it here than anywhere else.
4. **Templated filler first?** 12.7 sequences it before this (step 5 versus step
   7), it is genuinely lower risk, and it would take the filler near-duplicate
   count to zero. It buys no claim density, which is the measured failure. This
   plan assumes it is a separate ticket and does not wait for it.
