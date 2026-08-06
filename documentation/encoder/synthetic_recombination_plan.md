# Provisional Plan: Fragment Recombination Script (Test Run)

Status: **provisional** — for review and expansion into an implementation plan.
Scope of this run: `fever_present` only, condition `urinary_symptoms` (`data/uti1.json`).
Reference: `documentation/encoder/Fine_tuning_plan.md` (§2, §5, §6 and the data-structure sections).

---

## 1. Purpose

Build one offline Python tool that turns the hand/LLM-written fragment libraries in
`data/synthetic/` into a label-first, fragment-split, JSONL training set for a single
encoder head.

The point of this run is to **prove the generation pipeline**, not to produce a model
worth trusting. See §8 for what this dataset can and cannot tell us.

### In scope
* Read the existing fragment libraries as plain-text lines.
* Validate `fever_present` against `data/uti1.json` (fail fast if it drifts).
* Deterministic fragment-level train/val/test split.
* Label-first recombination of exactly 2 fragments per example.
* JSONL output with per-head labels and provenance metadata.
* Unit tests that enforce the non-negotiable rules from the fine-tuning plan.

### Out of scope (deliberately)
* Any other signal (`dysuria_present`, `flank_pain_present`, …) — no libraries exist yet.
* Intros/outros, temporal/spelling/disfluency variation, variable-length blurbs
  (`Fine_tuning_plan.md` §5.4 — the expansion phase).
* Generating new fragments, or the `fever_true.yaml` template expander.
* Anything that touches `app/` or runtime code. This is an offline tool.

---

## 2. What is actually in `data/synthetic/` today

I read every file. Findings that shape the design:

### 2.1 The `.jsonl` files are not JSONL
All nine files are **newline-delimited plain text**, one fragment per line. Zero lines
parse as JSON. The extension is actively misleading and will trip up the next person.

**Recommendation:** rename to `.txt`. Cheap now, annoying later. Not a blocker — the
script will read them as text regardless.

### 2.2 Usable fragment counts

| File | Fragments | Role |
|---|---|---|
| `fever_true` | 96 | signal / positive |
| `fever_false` | 60 | signal / negative |
| `fever_null` | 82 (80 unique) | signal / ambiguous + confounder |
| `tangents` | 110 | filler |
| `justifiers` | 100 | filler |
| `emotional` | 60 | filler |
| `expectations` | 60 | filler |
| `uti_speculation` | 40 | filler |
| **filler total** | **370** | |

657 unique fragments overall.

### 2.3 Two files are not fragment libraries
* `fever_synonyms.jsonl` — scratch notes: a partial numbered list (`2. Burning up`,
  `4. Febrile`, …), 7 blank lines, and a stray heading `Fever template wrappers`. If this
  is hoovered up by a filename convention it will inject garbage straight into training text.
* `fever_true.yaml` — a template/synonym spec for a *generator*, not fragments.

This is the main argument for an **explicit manifest** rather than globbing `data/synthetic/*`
(§4.1).

### 2.4 Filler libraries are clean of fever leakage
I grepped all five filler libraries for fever/temperature/shiver/chills/sweat/hot/rigor.
Three incidental hits, none of them thermal:
* `emotional:56` "…worried about me from the photos I sent"
* `expectations:59` "…referred for lithotripsy…"
* `justifiers:82` "…been unemployed for 8 months…"

So filler fragments can safely be assumed `fever_present = null`. **This assumption must be
re-checked whenever a filler library is edited** — §5 proposes a test that does exactly that.

### 2.5 `fever_null` has four distinct sub-classes, and this is valuable
Lines cluster into: **hedged/uncertain** ("might be running warm, hard to tell"),
**metaphorical heat** ("burning up with anger", "hot under the collar"),
**third-party fever** ("my husband's had a fever for three days"), and
**historical fever** ("I had a fever a couple of weeks ago").

All four are correctly `null` under the plan's rules, but they are *very* different failure
modes. Third-party and historical fever are the hard cases — they contain the literal word
"fever" and are exactly where a naive model will produce false positives. If we don't record
which sub-class an example came from, we cannot do the error analysis that is the whole
reason for the test run.

**Recommendation:** split `fever_null` into four files (`fever_null_hedged`,
`fever_null_metaphor`, `fever_null_thirdparty`, `fever_null_historical`) and carry the
sub-class through to output metadata. This is a manual 15-minute edit of an existing file
and it is worth it. (Alternative: sidecar categories file — more machinery, same result.)

### 2.6 Two exact duplicates inside `fever_null`
Line 11 == line 55, line 23 == line 61 (the file looks like two generation batches
concatenated). Duplicates are a **leakage hazard**: two copies of the same text could hash
into different splits. The loader must deduplicate on normalised text before splitting.

### 2.7 Some `fever_true` fragments are arguably `null`
Examples currently in `fever_true.jsonl`:
* line 57: "I reckon I've got a bit of a temperature going on, **not sure though**."
* line 58: "**Pretty sure** I'm running warm, keep getting these waves of heat…"

`Fine_tuning_plan.md` §1.2 is unambiguous: *"Ambiguous language maps to None, never to True
or False."* These are hedged, so by the project's own rule they belong in `fever_null`.

No script can fix this — labels are by construction, so a mislabelled fragment is a
permanently poisoned label. **This needs a human review pass over `fever_true` and
`fever_false` before the first real generation run.** I propose the script ships with a
`--lint` mode that flags hedge markers (`not sure`, `pretty sure`, `might`, `maybe`, `I think`,
`hard to tell`, `reckon`, `probably`, `could be`) in the true/false libraries for a human to
adjudicate. It reports; it never relabels.

---

## 3. Design decisions to lock

Each has my recommendation. These are the things that must be settled before code.

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Which signals get labels in the output? | **`fever_present` only.** | We have no libraries for the other five UTI keys and cannot assert they're absent from filler text (`uti_speculation` mentions cystitis and kidney infection). Emitting `null` for unverified keys would be inventing labels. |
| D2 | Fragments per example | **Exactly 2, in every class.** | `Fine_tuning_plan.md` §5. Critically, holding the count constant stops length correlating with label — otherwise `null` examples are shorter and the model learns length, not language. |
| D3 | Label distribution | **null 60 / false 25 / true 15** (plan §5.1), CLI-overridable. | Matches the plan. Prevalence is a training-time prior; operational cost asymmetry should be handled later by the decision threshold, not baked in here. |
| D4 | `null` sub-modes | Split `null` into **structural** (2 filler fragments, no fever fragment) and **ambiguous** (1 `fever_null` fragment + 1 filler), default **50/50**. | If every `null` were structural, "no fever words → null" is trivially learnable and the model collapses on the hard confounders. This ratio is the most important knob in the whole script. |
| D5 | Filler sampling | Pick a **library uniformly, then a fragment within it**. | Uniform over the pooled 370 lets `tangents` (110) outweigh `uti_speculation` (40) 3:1. Category-uniform gives better entropy coverage. |
| D6 | Split method | **Hash-based:** `sha256(normalised_text) % 100` → 0–69 train, 70–84 val, 85–99 test. | Deterministic, needs no stored assignment file, and stays stable as libraries grow. Trade-off: per-library ratios are approximate on small libraries (`fever_false` at 60 might give 8 or 12 val fragments). The alternative — seeded shuffle-and-slice — gives exact ratios but reshuffles every fragment when the library grows. Stability wins. |
| D7 | Library discovery | **Explicit manifest** `data/synthetic/manifest.json`, not globbing. | §2.3 — globbing would swallow `fever_synonyms` and `fever_true.yaml`. A manifest also makes `signal_key`/`fragment_type` declarations reviewable in a diff. |
| D8 | Text assembly | Strip whitespace, add a terminal `.` only if the fragment has no terminal punctuation, join with a single space. Preserve original casing, contractions, and typos. | Typos and lowercase "i" are realistic patient input. `phase_3.md` is explicit that the encoder sees raw text; we shouldn't launder it at generation time either. |
| D9 | Fragment IDs | `{library_name}:{sha1(normalised_text)[:8]}` | Stable if lines are reordered or inserted, which line numbers are not. Provenance survives library edits. |
| D10 | Ruleset validation | Load `data/uti1.json` at startup; assert `fever_present` exists with `answer_type: Boolean` and `send_to_encoder: true`. Abort otherwise. | `Fine_tuning_plan.md` §4.3 ("every answer_key must exist in ruleset") and the project's fail-fast configuration invariant. Makes ruleset drift a loud error, not silent label rot. |

---

## 4. Proposed script shape

### 4.1 Manifest — `data/synthetic/manifest.json`

```jsonc
{
  "version": 1,
  "libraries": [
    { "name": "fever_true",  "file": "fever_true.txt",
      "signal_key": "fever_present", "fragment_type": "positive" },
    { "name": "fever_false", "file": "fever_false.txt",
      "signal_key": "fever_present", "fragment_type": "negative" },
    { "name": "fever_null_hedged", "file": "fever_null_hedged.txt",
      "signal_key": "fever_present", "fragment_type": "ambiguous",
      "subclass": "hedged" },
    { "name": "fever_null_thirdparty", "file": "fever_null_thirdparty.txt",
      "signal_key": "fever_present", "fragment_type": "confounder",
      "subclass": "third_party" },
    // … metaphor, historical …
    { "name": "tangents", "file": "tangents.txt",
      "signal_key": null, "fragment_type": "filler", "category": "irrelevant" }
    // … justifiers, emotional, expectations, uti_speculation …
  ]
}
```

Files present in the directory but absent from the manifest are **ignored** (so
`fever_synonyms` and `fever_true.yaml` cause no harm), and files named in the manifest but
missing from disk are a **hard error**.

### 4.2 Layout

```
scripts/synthetic_data/
    __init__.py
    manifest.py       # load + validate manifest, dedupe, hash-split fragments
    ruleset.py        # D10 validation against data/uti1.json
    recombine.py      # label sampling + fragment selection + assembly
    lint.py           # §2.7 hedge-marker report
    __main__.py       # CLI
tests/test_synthetic_recombination.py
```

Standard library only — `random`, `hashlib`, `json`, `argparse`, `dataclasses`, `pathlib`.
Nothing in `requirements.txt` is needed and nothing should be added.

*(Implementation note to confirm: `tests/` currently imports `app.*` with repo root on
`sys.path`; `scripts.synthetic_data` should import the same way, but verify rather than
assume.)*

### 4.3 Data structures

Mirroring `Fine_tuning_plan.md` §2, minus the fields this run doesn't use:

```python
@dataclass(frozen=True)
class Fragment:
    fragment_id: str          # "fever_true:9c3a1f04"
    text: str
    library: str
    signal_key: str | None
    fragment_type: str        # positive | negative | ambiguous | confounder | filler
    subclass: str | None
    split: str                # train | val | test

@dataclass(frozen=True)
class ExampleSpec:            # label-first, pre-text
    example_id: str
    labels: dict[str, bool | None]
    label_mode: str           # true | false | null_structural | null_ambiguous

@dataclass(frozen=True)
class AssembledExample:
    text: str
    labels: dict[str, bool | None]
    meta: dict
```

### 4.4 Algorithm (per example `i`)

1. `rng = random.Random(f"{seed}|{split}|{i}")` — derived per example, so changing
   `--count` does not reshuffle the examples already generated.
2. Sample the label from D3.
3. If `null`, sample the sub-mode from D4.
4. Select the signal fragment from the split-restricted pool:
   `true` → one `positive`; `false` → one `negative`; `null_ambiguous` → one
   `ambiguous`/`confounder`; `null_structural` → none.
5. Draw filler fragments (D5, without replacement) until the example holds exactly 2
   fragments.
6. Shuffle fragment order — a decisive fragment must be able to sit first or second.
7. Assemble text per D8.
8. Reject exact-duplicate assembled texts; retry up to N times; abort with a clear
   "pool exhausted" error rather than silently emitting fewer examples.

**Never violated:** a `false` or `null` example can never contain a `positive` fragment;
no example contains both `positive` and `negative`; no example contains a decisive fragment
*and* an ambiguous one (plan §5.2).

### 4.5 CLI

```
python -m scripts.synthetic_data \
    --manifest data/synthetic/manifest.json \
    --ruleset  data/uti1.json \
    --signal   fever_present \
    --split    train \
    --count    10000 \
    --seed     42 \
    --dist     null=0.60,false=0.25,true=0.15 \
    --null-ambiguous-ratio 0.5 \
    --out      data/synthetic/generated/fever_present.train.jsonl

python -m scripts.synthetic_data --lint --manifest data/synthetic/manifest.json
```

Same seed + same libraries + same flags ⇒ byte-identical output (plan §4.4).

### 4.6 Output schema — one JSON object per line

```json
{
  "example_id": "train-000123",
  "split": "train",
  "text": "My husband's had a fever for about three days now and it doesn't seem to be going away. I've got a holiday booked next week and I'm worried I won't be well enough to go.",
  "labels": { "fever_present": null },
  "meta": {
    "label_mode": "null_ambiguous",
    "fragment_ids": ["fever_null_thirdparty:1a2b3c4d", "tangents:7f8e9d00"],
    "fragment_subclasses": ["third_party", null],
    "seed": 42,
    "generator_version": 1
  }
}
```

Labels are a **dict keyed by `answer_key`**, not a flat scalar, so adding heads later is
additive. JSON `null` maps to Python `None` — no sentinel strings, ever.

A `<name>.stats.json` sidecar should record realised label counts, sub-mode counts,
fragment-pool sizes per split, and duplicate-rejection count. Cheap, and it is the first
thing anyone will want when a training run looks wrong.

---

## 5. Tests (`tests/test_synthetic_recombination.py`, unit — no DB, no integration marker)

1. **Determinism** — same seed twice ⇒ identical output.
2. **Seed independence across counts** — first 100 of a 100-run == first 100 of a 1000-run.
3. **Split disjointness** — no `fragment_id` appears in more than one split (plan §6, Rule 4).
4. **No positive fragment in a non-`true` example**, and vice versa (Rule 2).
5. **No example mixes decisive and ambiguous fragments for the same signal** (§5.2).
6. **Fragment count is exactly 2 in every example, in every class** (D2 — this is the
   length-leak guard).
7. **Label distribution within tolerance** of the requested distribution.
8. **Filler purity** — every filler fragment is screened against a fever lexicon; failure
   means someone edited a filler library and reintroduced leakage (§2.4).
9. **Manifest validation** — missing file, unknown `fragment_type`, and duplicate `name`
   each raise.
10. **Ruleset validation** — a signal absent from `data/uti1.json` raises (D10).
11. **Deduplication** — the two known `fever_null` duplicates collapse to one fragment.

Per the project test obligation: no `pytestmark` needed (pure unit), and
`docs/arch_testing.md` should get a one-line mention of the new test file.

---

## 6. Suggested task breakdown

* **Task 1 — Library hygiene (manual, no code).** Rename `.jsonl` → `.txt`; split
  `fever_null` into its four sub-class files; human review pass on the hedged `fever_true`
  entries flagged in §2.7; write `manifest.json`.
* **Task 2 — Loader + splitter.** `manifest.py`, `ruleset.py`, dedup, hash-split. Tests 3,
  9, 10, 11.
* **Task 3 — Recombiner + CLI + output.** `recombine.py`, `__main__.py`, stats sidecar.
  Tests 1, 2, 4, 5, 6, 7.
* **Task 4 — Lint mode + filler purity guard.** `lint.py`. Test 8.

Task 1 is a prerequisite for the rest and needs the user's clinical judgement, not Claude's.

---

## 7. Open questions

1. **`fever_null` sub-class split (§2.5)** — worth the manual edit? I think clearly yes, but
   it is your file.
2. **Hedged `fever_true` entries (§2.7)** — do you agree they should move to `fever_null`?
   This is a clinical-language call.
3. **`uti_speculation` as filler** — "Reckon I've got another kidney infection coming on"
   carries no fever claim, so it is a safe `null` for *this* head. But when
   `flank_pain_present` gets a head, that library stops being neutral. Keep it in the filler
   pool for now, tagged so it can be reclassified later?
4. **Output location** — `data/synthetic/generated/` (gitignored) or outside the repo? These
   files are large and regenerable; committing them adds noise. I lean gitignored.
5. **Split ratios** — 70/15/15 assumed. Confirm.

---

## 8. Honest assessment of what this run will tell us

**It will prove:** the pipeline is deterministic, labels are assigned before text, fragments
do not cross splits, and the output schema feeds a multi-head trainer cleanly. That is real
and worth having.

**It will not produce a trustworthy accuracy number.** With 96 `fever_true` fragments and a
70/15/15 split, the validation set contains roughly **14 distinct positive fragments**. Every
"true" example in validation is a recombination of those 14 lexical items. A validation score
computed over 14 unique phrasings is noise — one unlucky fragment moves it several points.
The same applies to `false` (~9 val fragments).

The fine-tuning plan's own §4.1 says ~200 fragments per signal. We are at roughly half that
for `true`, a third for `false`. **Treat any metric from this run as a smoke test, not
evidence.** Before drawing conclusions about model quality we need the libraries up to ~200
per bucket per signal, and more than one signal.

Two further limits worth stating plainly:

* **Two-fragment examples are ~2 sentences.** Production free text is longer and messier.
  A model trained only on this will meet a distribution shift at inference. That is expected
  and is what `Fine_tuning_plan.md` §5.4 exists to fix — but it means this run's model must
  not be pointed at real text and judged.
* **Combinatorial volume is not information.** The train split can yield >100k unique texts
  from ~430 fragments. Generating 100k examples instead of 10k adds recombination, not new
  language. 10k is the right size for this run; a bigger number would only buy false
  confidence.
