# Provisional Plan: Multi-signal recombination

**Status: discussion output, not agreed.** This is stage 1 of the workflow — design decisions and
a provisional task breakdown, for review and expansion into an implementation plan.

Implements `arch_training.md` sections 12.2 and 12.5. The dysuria fragment libraries already exist
(`data/synthetic/symptoms/dysuria/`, 72 fragments) and are declared in the manifest, but nothing
reads them: `build_pools` keeps only fragments matching the single signal being generated, plus
filler. This plan is the engine work that makes them usable.

---

## Scope

**In scope**

- `data/synthetic/manifest.json` — a manifest-level signal list and a `silent_on` declaration per library
- `scripts/synthetic_data/manifest.py` — label vectors on `Fragment`, exhaustive silence validation
- `scripts/synthetic_data/recombine.py` — slot-based assembly, per-signal target sampling, vector-filtered pools
- `scripts/synthetic_data/lint.py` — per-signal lexicons, generalised purity check
- `scripts/synthetic_data/__main__.py` — per-signal distributions, `--signal` removed
- `tests/test_synthetic_recombination.py`, `documentation/arch_training.md`

**Out of scope**

- Multi-symptom fragments (12.3) and out-of-scope mentions (12.4). Both need a per-line JSONL
  library format. DD-C keeps the door open for them; nothing here builds it.
- Procedural fragment generation (12.1).
- Expanding the dysuria libraries past their current 14–24 fragments (see open question 3).

---

## Design decisions

### DD-A: Four states per signal, not three

Every (fragment, signal) pair is in one of four states: **true**, **false**, **null**, **silent**.

The distinction that does the work is `null` vs `silent`. A `fever_null_thirdparty` fragment
("my son has a temperature") is *not silent* about fever — it is full of fever language and asserts
that you cannot conclude a fever. A `tangents` fragment is silent: it says nothing either way.

Combination is a join over those states:

| | silent | true | false | null |
|---|---|---|---|---|
| **silent** | silent | true | false | null |
| **true** | true | true | ✗ | ✗ |
| **false** | false | ✗ | false | ✗ |
| **null** | null | ✗ | ✗ | null |

An example whose fragments are all silent on a signal emits `null` for it. Anything marked ✗ is a
forbidden combination.

This is not a new rule. It is exactly the invariant `recombine.py` already enforces structurally —
"a `false` example cannot contain a positive fragment, no example holds both a positive and a
negative, and no example holds a decisive fragment alongside an ambiguous one" — restated so it
generalises past one signal.

### DD-B: Silence is declared exhaustively and validated

The manifest gains a top-level signal list, and every library must account for **every** signal in
it: its own via the existing `signal_key` + `fragment_type`, the rest via a new `silent_on` array.
If the union does not equal the declared signal set, the manifest fails to load.

```json
{
  "version": 2,
  "signals": ["fever_present", "dysuria_present"],
  "libraries": [
    { "name": "fever_true", "file": "symptoms/fever/fever_true.txt",
      "signal_key": "fever_present", "fragment_type": "positive",
      "silent_on": ["dysuria_present"] },
    { "name": "tangents", "file": "filler/tangents.txt",
      "signal_key": null, "fragment_type": "filler",
      "silent_on": ["fever_present", "dysuria_present"] }
  ]
}
```

**Adding a signal therefore invalidates every library until a human adjudicates it.** That is the
feature, not a cost to be engineered away. Section 2's architecture is "there is no point in the
process where the text could influence the label"; its dual is "there is no point where an unstated
assumption silently becomes a label". A default of "silent unless declared" would make the default
the lie.

The bill: 2 signals × 15 libraries = 30 cells today, of which the 5 filler libraries are trivial.
At the ruleset's full 7 encoder signals it is roughly 130 cells. Real work, and visible.

### DD-C: `fragment_type` stays; the vector is derived from it

`signal_key` + `fragment_type` + `silent_on` → vector. No existing manifest field changes meaning
and no existing test fixture needs rewriting.

It also leaves 12.3 a clean seam: a JSONL library carries a per-line vector that overrides the
library default, and everything downstream of `Fragment` is already vector-shaped.

### DD-D: Fixed slots, not a fixed pair

Today: exactly 2 fragments in every example, so fragment count cannot proxy the label.

Generalised: exactly **K** fragments in every example, K constant for a run. Each signal whose
target is not structural-null claims one slot; every remaining slot takes filler.

**Default K = (number of signals) + 1.**

At 1 signal K = 2, which is today's behaviour exactly — one clinical slot plus one filler, or two
fillers from different libraries for a structural null. The existing fever dataset is unchanged.

At 2 signals K = 3, which guarantees at least one filler slot in every example. That guarantee is
the reason for the `+1`. With K = 2 and 2 signals, an example whose signals are both decisive would
have no filler at all, so the presence of filler would correlate with how many heads are non-null —
a structural shortcut of precisely the kind the fixed fragment count exists to prevent.

Cost: examples get longer and the per-label length statistics shift. Section 9 wants longer, messier
text, so the direction is right, but this is a real change to the dataset's character.

### DD-E: Signals are sampled independently

Each signal gets its own `{true, false, null}` distribution and its own structural/ambiguous ratio,
sampled independently. The target vector is assembled from those draws before any fragment is
touched.

The alternative — a joint distribution reflecting how fever and dysuria actually co-occur in UTI —
is the wrong thing to want. If the training set encodes that correlation, the encoder can learn to
predict fever from dysuria language, and it will be confidently wrong on exactly the patients who
break the correlation. Independent sampling makes the signals statistically orthogonal, so each
head has to read its own evidence.

At the current defaults this puts ~16% of examples in the both-signals-decisive class.

### DD-F: Filter the pools, then draw

For each slot, restrict the pool to fragments compatible with the target vector, then draw. Never
draw and reject.

Draw-and-reject would over-sample whichever fragments are compatible with the most target vectors,
quietly skewing the mix in a way nothing downstream could detect, and would make the per-example
seed no longer determine the output.

Until 12.3 lands, every clinical library asserts exactly one signal and is silent on the rest, so
the join reduces to "the fragment in signal *s*'s slot asserts the target state for *s* and is
silent everywhere else". Implement the join anyway — the reduction is a property of the current
libraries, not of the design.

### DD-G: `--signal` is removed

Generation covers every signal the manifest declares and emits one key per signal. Ruleset
validation runs over all of them at startup.

The section 7 contract is unchanged: an absent key means "no label for this head, mask its loss",
a `null` value means "the label is null". A signal outside the manifest's list gets no key.

### DD-H: The purity check becomes co-occurrence matching, and its weakness is documented

**A phrase lexicon does not work for dysuria.** Measured against the real libraries: `burning` is
shared vocabulary. 21 fever fragments contain it ("I was burning up"), as do the dysuria positives
("burning when I pee"). The fever lexicon dodges this with the `burning up` bigram; dysuria has no
equivalent bigram that covers its surface forms.

Requiring **a pain token and a urination token in the same fragment** does work. Measured:

- **0 false positives** across all six fever libraries and all five filler libraries
- **57/72 recall** on the dysuria libraries

The 15 misses are a single failure mode — euphemism, where the urination is implied and never named:
"it's uncomfortable and stingy when I go", "no stinging or soreness when I go", "there might be a
slight sting when I go".

So the generalised check is a **strong negative guard and a weak positive one**: it will not falsely
accuse a clean library, but a library could acquire euphemistic dysuria language and pass. It must
be documented that way, in the same spirit as the hedge report's precision header, so a green check
is never read as proof of silence.

This has a consequence for DD-B worth stating plainly: **the lexicon is a backstop, not the source
of truth.** Silence is declared by a human and spot-checked by the lint. The declaration is what the
labels rest on.

---

## Open questions for review

1. **K = N+1, or keep K = 2?** DD-D argues for N+1. Keeping 2 is less churn and leaves the fever
   length statistics alone, at the cost of accepting the filler-presence leak and capping the design
   at 2 simultaneously-asserted signals forever.

2. **Does the single-signal proof-of-concept run happen first?** Section 12.6 step 1 says produce it
   before anything else, to have a baseline. It is still blocked on one empty cell
   (`fever_null_metaphor/val`), which is a handful of fragments' worth of library work. Doing it
   first means the multi-signal numbers have something to be compared against; skipping it means we
   never learn what the single-signal pipeline was worth.

3. **Do the dysuria libraries get expanded to 40–50 per variant before or after the engine work?**
   They fill all twelve of their split cells today, but at 14–24 fragments that is fragile — one
   reworded fragment can empty a cell. The engine can be built and tested against them as they are;
   no number produced from them means anything until they grow.

4. **Should `silent_on` validation cover all 7 encoder signals, or only the 2 we generate?** Only
   generating 2 means only 2 need adjudicating, and an absent key already means "mask this head".
   Declaring all 7 now front-loads ~100 cells of adjudication for signals with no libraries yet.
   Recommendation: declare only what we generate, and let DD-B's exhaustiveness check make the bill
   visible when a signal is added.

---

## Provisional task breakdown

**Task 1 — Manifest: signal list, `silent_on`, label vectors.** `parse_manifest` reads the
top-level `signals` list and validates each library's declaration is exhaustive against it.
`Fragment` gains a `vector: dict[str, State]`. Existing single-signal behaviour must be preserved
when the manifest declares one signal.

**Task 2 — Recombine: slots and vector-filtered pools.** Replace `FragmentPools`'s per-signal
fields with per-(signal, state) pools plus filler. Replace `sample_label_mode`/`labels_for_mode`
with per-signal target sampling and the DD-A join. Replace `select_fragments`'s four hard-coded
modes with slot assignment. `meta.label_mode` becomes per-signal.

**Task 3 — Lint: per-signal lexicons and the generalised purity check.** A lexicon registry keyed
by signal; co-occurrence matching for dysuria (DD-H); the purity check runs every library against
every signal it declares silence on. The CI test that currently pins filler purity to an empty
baseline generalises to the same shape.

**Task 4 — CLI and stats.** Remove `--signal`; per-signal `--dist`; per-signal sections in the
stats sidecar; `K` reported and validated.

**Task 5 — Documentation.** `arch_training.md` sections 5, 7, 8 and 12 rewritten for what has
actually been built; 12.2 and 12.5 move above the section 12 line.
