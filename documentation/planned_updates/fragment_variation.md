# Provisional Plan: Fragment Variation and Draw Discipline

**Status:** provisional — output of a discussion chat, not yet reviewed or
expanded into an implementation plan.

**Reading order for the review chat:** `documentation/arch_training.md` first
(this plan assumes all of it), then `scripts/synthetic_data/recombine.py`, then
`documentation/planned_updates/data_augmentation.md` (a competing earlier
proposal — see section 3).

---

## 1. The problem

The generator draws fragments **with replacement**, independently per example
(`recombine.py:283-301`, `rng.choice`). A 10,000-example run at the default mix
therefore shows each fragment many times over:

| Pool | Approx. train fragments | Draws per 10k run | Mean reuse |
|---|---|---|---|
| `fever_true` | ~67 | 1,500 | ~22× |
| `fever_false` | ~42 | 2,500 | **~60×** |
| `fever_null_*` (pooled) | 69 | 3,000 | ~43× |
| fillers (all) | ~259 | 13,000 | ~50× |

Pool sizes are `0.7 ×` the section 3 library counts; the null row uses the real
split figures from section 10. Exact numbers should be taken from the lint's
split-coverage report, not from this table.

Two consequences:

**A 10,000-line dataset carries about 600 sentences.** That is the real
information content. The encoder head sees the same surface strings 20–60 times
each and can key on the exact n-gram — "I had a high temperature" — rather than
on what makes it a positive.

**Reuse is uneven as well as high.** Drawing with replacement makes the numbers
above means, not rates. At a mean of 60, individual `fever_false` fragments will
land anywhere from roughly 45 to 75 times in a single run.

### What this is not

This is a second-order problem. Section 9 of `arch_training.md` lists larger
ones (length leak, urgency leak, two-sentence examples, one signal only) and
section 10 lists the blocker. This plan should be sequenced behind both — see
section 7.

---

## 2. Scope

**In scope**

- Making each fragment's exposure across a run even rather than Poisson-scattered.
- Producing lightly varied second forms of existing fragments so the surface
  string differs where the meaning does not.
- Whatever manifest, lint and split-key changes those two require.

**Out of scope**

- New independent fragment *ideas*. That is the section 10 blocker and separate
  work.
- Any change to the label taxonomy, the two-fragments-per-example rule, or the
  mix defaults.
- Anything inside `app/`. This is offline tooling throughout.

**Explicitly does not unblock the proof-of-concept run.** Variants must land in
the same split as their source (decision D2), so the cluster count of the four
libraries with empty test cells is unchanged, and the empty cells stay empty.
Anyone reading this plan hoping it clears section 10 should stop here.

---

## 3. The competing approach, and the recommendation

`data_augmentation.md` proposes deterministic slot templating — `I {verb}
{adjective} {noun_fever}` expanded with `itertools.product` — and argues it is
superior to an LLM on three grounds: zero hallucination, guaranteed label
safety, and auditability. `data/synthetic/fever_true.yaml` is an unfinished spec
in that shape. Those three arguments are correct as far as they go, and the
label-safety one in particular is the single biggest risk in this whole area.

But templating has a weakness that bears directly on the problem in section 1.
Combinatorial expansion produces *many strings from few skeletons*. Four
templates and six slot lists yield a thousand fragments that share four
syntactic frames. Against a model that is overfitting to surface n-grams, that
is a shallow fix: it varies the words inside the slots and nothing else, and it
introduces a new regularity of its own — templated text is detectably templated.

The variation this plan is after is structural: "my sister had a fever" against
"my brother's been having a fever" differs in person, tense, aspect and
contraction, not just in one slot.

**Provisional recommendation: both, for different jobs.** Templating for the
positive and negative libraries, where the label is carried by a stable phrase
and slot-swapping is safe and cheap to audit. LLM paraphrase for the four
`fever_null` libraries, where the label depends on context — third-party, past
tense, metaphor, hedge — that templates express badly and that most needs real
syntactic range. This is the decision the review chat is most likely to
overturn, and it should be argued rather than inherited.

Either route needs the same human review gate (D3). The routes differ in what
gets reviewed: ~50 slot-list entries for templating, ~600 generated lines for
paraphrase.

---

## 4. Provisional design decisions

**D1 — Variation is regularisation, not data.** Doubling the libraries with
variants adds no new ideas. Effective sample size is unchanged, so the
validation score does not become more trustworthy, and the "200 fragments per
signal" target in `Fine_tuning_plan.md` continues to mean 200 *independent*
ideas. Any post-change reporting that counts variants toward that target is
misreporting.

**D2 — A variant always shares its source's split.** Variants are near-
duplicates by construction, which is exactly the leakage section 6 exists to
prevent. Unlike the hand-written twins, the tool knows the pairing, so the
cluster marker can be emitted automatically. Cluster IDs are already namespaced
per library (`manifest.py:186`), so this needs no new mechanism. A useful side
effect: the same pass can retro-cluster the incidental near-duplicates in
`fever_true` and `fever_false` that section 6 declined to hand-tag.

**D3 — Generation is an authoring aid; nothing enters a library unreviewed.**
The pipeline's strongest property (section 2) is that no model reads text and
assigns a label. An LLM rewriting "my son has a fever" into "I've had a fever"
silently converts a `null_thirdparty` into a `true`, and the mislabel is
permanent. `fever_null_metaphor` is the sharpest case — "burning up with
embarrassment" paraphrases into something literal very easily. So: the tool
writes candidates to a staging file, a human reads them, accepted lines are
committed to the `.txt` library. No LLM call ever runs as part of generation.

**D4 — Apply across all libraries in the same proportion, or not at all.**
Generated text has a register: tidier punctuation, fewer typos, more consistent
grammar than the hand-written fragments. Applied evenly that is harmless noise.
Applied only to the small `fever_null` libraries — which is the tempting move,
since they are the ones that need help — register becomes a label signal, and we
have hand-built the same shortcut as the urgency leak in section 9. This
constrains the section 3 recommendation and may be an argument for templating
everywhere.

**D5 — Register is preserved, like everything else.** Section 5 keeps fragments
verbatim because the live encoder meets raw patient text. Variants must keep the
lowercase openings, the missing apostrophes, the run-ons. This is a prompt and
review-criteria problem, and it is the thing spot-checks should look for first.

**D6 — Draw discipline is a deterministic permutation, not a mutable flag.**
Every example currently gets its own seed from `(seed, split, index)`
(`recombine.py:367`), which is what makes a 20k run append cleanly to a previous
10k run. A mutated "used" marker on the fragment would work but makes the
property hard to see. The equivalent is a seeded permutation per pool plus a
cycle position: fragment `i` of the cycle is `perm[i % len(pool)]`, reshuffled
per lap.

**D7 — Draw discipline respects the existing two-level filler structure.**
`_draw_filler` picks a library uniformly and *then* a fragment
(`recombine.py:273-284`), deliberately, so `uti_speculation` (40) is not drowned
by `tangents` (110). Round-robin must apply within each library, not across a
flattened filler pool, or it silently reverses that decision. Note that
`pools.ambiguous` is a single flat pool and so already uses the opposite
convention; whether that is intended is an open question below.

---

## 5. Open questions for the review chat

1. **Template, paraphrase, or both?** Section 3 recommends both, split by
   library. D4 pushes against splitting by library. These are in tension and the
   review chat has to resolve it.
2. **How many variants per source fragment?** One doubles the library and halves
   reuse. Two or three flatten it further but push the cluster further from
   independence and multiply the review burden.
3. **Where do variants live?** Appended to the existing `.txt` files, or a
   parallel `*_variants.txt` per library with its own manifest entry? Separate
   files make provenance obvious and make an A/B run trivial; one file keeps the
   library concept simple.
4. **How is provenance recorded?** The cluster marker links a variant to its
   source, but nothing distinguishes hand-written from generated. Worth a
   manifest field or a marker convention if we ever want to measure the two
   separately.
5. **Is the `pools.ambiguous` flattening (D7) intended?** It makes
   `fever_null_hedged` (21 in train) draw more often than `metaphor` (16). Given
   that these four sub-classes exist precisely to be evaluated separately, the
   filler convention may be the right one here too. Separate from this plan but
   surfaced by it.
6. **How do we know it worked?** Without a measurement this is faith. The
   cheapest honest check is a held-out set of hand-written fragments never seen
   in any form during training, scored before and after. Needs the PoC run to
   exist first.

---

## 6. Rough task shape

Sizing is a guess; the implementation plan should re-cut these.

**Task 1 — Draw discipline.** Permutation-cycle drawing per pool, respecting
D6 and D7. Self-contained, no library changes, shippable independently of
everything else in this plan. Touches `recombine.py`,
`tests/test_synthetic_recombination.py`. Determinism and append-safety tests are
the main deliverable alongside the change itself.

**Task 2 — Variation authoring tool.** A new offline script that reads a
library, produces candidate variants (template expansion and/or LLM call per the
section 3 decision), and writes a staging file with source-line provenance. Runs
by hand, never from the generator. If it makes an LLM call it needs a dependency
and a key, which is a first for this tooling and should be checked against the
"standard library only" note in section 11.

**Task 3 — Library regeneration and review.** Run Task 2 across the libraries,
read every candidate line, commit the accepted ones with cluster markers. This
is the bulk of the wall-clock time and it is not a coding task.

**Task 4 — Lint, manifest and docs.** Cross-split near-duplicate counts will
move sharply (they should stay at zero for clustered libraries — that is the
check that D2 was implemented correctly). Update `arch_training.md` sections 3,
6 and 8, and the `fever_true.yaml` scratch file's status either way.

---

## 7. Sequencing

Behind two things:

1. **Write more independent fragments** for the four libraries with empty test
   cells (section 10). That unblocks the proof-of-concept run; this plan does
   not. An LLM is useful there too, under the same review gate as D3, but asked
   for *new ideas* rather than rewrites.
2. **Do the proof-of-concept run.** There are currently no measurements at all,
   so there is no baseline against which any of this can be shown to help — see
   open question 6.

Task 1 is the exception and could be done at any point; it is small, isolated,
and does not depend on the library work.
