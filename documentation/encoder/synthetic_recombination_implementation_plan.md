# Implementation Plan: Fragment Recombination Script (Proof-of-Concept Run)

## Plan

Build one offline Python tool that turns the fragment libraries in `data/synthetic/` into a
label-first, fragment-split, JSONL training set for a single encoder head (`fever_present`,
condition `urinary_symptoms`).

This is a **proof of concept for the generation pipeline**, not an attempt to produce
clinical-grade training data. The run succeeds if it demonstrates that labels are assigned
before text, that fragments cannot cross the train/val/test boundary, and that the output
schema feeds a multi-head trainer cleanly. It is not expected to produce a trustworthy
accuracy number, and §"Known limits of this run" states plainly why.

Supersedes `synthetic_recombination_plan.md` (provisional). That document's §2 survey of the
libraries is accurate and worth keeping; its counts were re-derived against the files and
all per-file figures check out. Three findings from review changed the design and are folded
in below: cluster-aware splitting (DD4), the length confound that D2 does not close (DD6),
and CI's `data/**` exclusion silently skipping the filler-purity guard (Task 4).

Four tasks, each independently committable with a green test suite. Task 1 is manual data
work and is a hard prerequisite for Tasks 2–4.

---

## Scope

**In scope**

- `data/synthetic/*.txt` — renamed from `.jsonl`, `fever_null` split by sub-class, cluster
  markers added
- `data/synthetic/manifest.json` — explicit library declaration
- `scripts/synthetic_data/` — new package: `normalise.py`, `manifest.py`, `ruleset.py`,
  `recombine.py`, `lint.py`, `__main__.py`
- `tests/test_synthetic_recombination.py` — new unit test file
- `.gitignore` — ignore generated output
- `.github/workflows/tests.yml` — run the new tests on `data/`-only changes
- Docs: `documentation/arch_testing.md` (Test Index row),
  `documentation/file_structure.md` (`scripts/` description)

**Out of scope**

- Any signal other than `fever_present`. No libraries exist for `dysuria_present`,
  `flank_pain_present`, `urinary_frequency_present` or `nocturia_present`, and we cannot
  assert those signals are absent from the filler text — `uti_speculation` mentions cystitis
  and kidney infection. Emitting `null` for an unverified key is inventing a label.
- Intros/outros, temporal/spelling/disfluency variation, variable-length blurbs
  (`Fine_tuning_plan.md` §5.4 — the expansion phase).
- Generating new fragments. The `fever_true.yaml` template expander stays unbuilt and
  unreferenced by the manifest.
- Any training or evaluation code. This plan produces a dataset and stops.
- Anything under `app/`. This is an offline tool with no runtime coupling.
- Manual paraphrase clustering of `fever_true` and `fever_false` — see DD4, those are
  reported by the lint rather than fixed by hand.

---

## Design Decisions

**1. `fever_present` only, and labels are a dict keyed by `answer_key`.**
Output carries `{"fever_present": true|false|null}`, not a flat scalar, so adding heads later
is additive. The trainer contract that must be written down now: **key absent ≠ value null**.
An absent key means "no label for this head, mask its loss"; `null` means "the label for this
head is None". When `fever_present` data is later merged with a `dysuria_present` set, getting
this wrong trains every head to predict null on every other head's data.

**2. Exactly 2 fragments per example, in every class.**
`Fine_tuning_plan.md` §5. Holding the count constant removes fragment *count* as a proxy for
the label. It does not remove length — see DD6.

**3. Label distribution: null 60 / false 25 / true 15, CLI-overridable.**
Matches `Fine_tuning_plan.md` §5.1. Prevalence is a training-time prior; operational cost
asymmetry belongs in the decision threshold at inference, not baked into the dataset.
`null` sub-modes are **structural** (2 filler fragments, no fever fragment) and **ambiguous**
(1 `fever_null` fragment + 1 filler), default 50/50. This ratio is the most consequential knob
in the script: if every `null` were structural, "no fever words → null" is trivially learnable
and the model collapses on the hard confounders.

**4. Splitting is cluster-aware, not text-aware.**
This is the change that most affects what the run is worth.

`fever_null` is not 82 independent fragments. It is **two generation batches over the same
concept list**, reworded — lines 1–44 and 45–82, with parallel block structure (hedged /
metaphor / hedged / third-party / historical) in both halves. Inside the blocks it is
concept-for-concept: third-party 25–34 maps 10/10 onto 63–72, historical 35–44 maps ~8/10 onto
73–82. Examples:

| Batch 1 | Batch 2 |
|---|---|
| 27 "A colleague at work went home with a fever on **Monday** and we share a small office" | 65 "One of my work colleagues went home with a fever on **Tuesday** and we share a small office" |
| 31 "My **husband's** had a fever for about three days now…" | 69 "My **boyfriend's** had a fever for about three days now…" |

Deduplicating on normalised text catches the two *exact* duplicates (11≡55, 23≡61) and nothing
else. Hash-splitting then scatters paraphrase twins independently, so for any pair there is a
~42% chance one lands in train and its twin in val. That is precisely the lexical leakage
fragment-level splitting exists to prevent (`Fine_tuning_plan.md` §6), and it bites hardest on
third-party and historical fever — the two sub-classes that are the entire reason for doing
error analysis. The consequence is that validation would be **biased upward, not merely
noisy**: it would look better than the model deserves.

Therefore: fragments carry an optional `cluster_id`, and the split hashes the **cluster key**
(`cluster_id` if present, else the normalised text). All fragments in a cluster land in the
same split.

Clusters are declared manually, and only for `fever_null`, where the twinning is systematic
and the manual pass is mechanical. `fever_true` (15% of fragments in a near-duplicate pair at
difflib ratio ≥ 0.60) and `fever_false` (12%) are left unclustered: the twinning there is
incidental rather than systematic, and hand-clustering 156 lines is not worth it for a proof
of concept. The lint reports their cross-split near-duplicates so the number is known rather
than assumed. Those measured rates are a **lower bound** — character-level similarity misses
"Monday→Tuesday, husband→boyfriend" rewrites, which is most of them.

**5. Normalisation is defined once, in one function, and pinned by a test.**
It is load-bearing three times over — dedup key, fragment ID (DD8), and split key (DD4) — and
leaving it undefined is how two implementers produce two different datasets. The definition:

1. Unicode NFKC
2. Fold typographic punctuation to ASCII: `U+2018 U+2019` → `'`, `U+201C U+201D` → `"`,
   `U+2013 U+2014` → `-`. NFKC does **not** do this, and the libraries mix `I've` with `I’ve`
   (`fever_true.yaml` and several fragments use curly apostrophes), so without this step the
   same sentence normalises two ways.
3. `casefold()`
4. Collapse all whitespace runs to a single space, then strip
5. Strip trailing `.`, `!`, `?`

Normalisation is used only for keys. It is **never** applied to the emitted text — DD7
preserves the original.

**6. Fragment count is held constant; fragment length is not, and this is a known confound.**
The provisional plan claimed D2 closes the length leak. It only closes half of it. The
libraries have very different length distributions: `fever_true:1` is "I had a fever." (4
words) while `fever_true:94–96` run 90–110 words; `fever_null` is uniformly 10–20 words. So a
`true` example can be 115 words and a `null_structural` one 35, and length still correlates
with the label — through fragment length rather than fragment count.

Decision: **measure it, do not test it**. The stats sidecar reports median and p90 token count
per label class. A hard test asserting the class medians are within some band would fail on
day one against the real libraries and would be muted rather than fixed. If the medians differ
by more than ~1.5×, that is recorded as a known confound in the run notes and is an argument
for rebalancing the libraries, not for changing the script.

Related: `fever_true:78–93` (16 fragments, 17% of the library) bundle a fever claim with an
urgency/justification tail — "I've got three important meetings I can't miss", "I'm taking my
driving test on Thursday". `fever_false:6–10` do the same at 8%; `fever_null` at ~0%. So
expectation language correlates with `true` inside the signal libraries, which is the
"medical-sounding urgency → positive" shortcut `Fine_tuning_plan.md` §4 exists to prevent.
Pairing with the `expectations` and `justifiers` filler libraries washes some of it out. These
fragments are also not atomic — they are signal + filler pre-fused. Left as-is for this run and
recorded as a known confound; stripping the tails is library work, not script work.

**7. Text assembly preserves the fragment verbatim.**
Strip surrounding whitespace, append a terminal `.` only if the fragment ends with no terminal
punctuation, join with a single space. Original casing, contractions, and typos are kept —
`phase_3.md` §3.2.1 is explicit that the encoder receives raw unmodified user input, so
laundering it at generation time would train on a distribution the encoder never sees.

**8. Fragment IDs are `{library}:{sha1(normalised_text)[:8]}`.**
Stable across reordering and insertion, which line numbers are not, so provenance survives
library edits.

**9. Split bands are 70/15/15 by cluster-key hash: `sha256(cluster_key) % 100` → 0–69 train,
70–84 val, 85–99 test.**
Deterministic, needs no stored assignment file, stays stable as libraries grow. The trade-off
is that per-library ratios are approximate on small libraries — `fever_false` at 60 fragments
gives a val count that is binomial(60, 0.15), so 5 or 14 are both plausible. Accepted, with a
guard: **every (library, split) cell must be non-empty or the loader aborts**. With
`uti_speculation` at 40 fragments the test split gets ~6, and a `fever_null` sub-class at ~20
fragments could plausibly get 0 or 1 in val. A silent empty cell would make a whole sub-class
invisible to evaluation; a loud one is a five-second fix.

**10. Library discovery is an explicit manifest, never a glob.**
`data/synthetic/` contains two files that are not fragment libraries: `fever_synonyms.jsonl`
is scratch notes (a partial numbered list, blank lines, a stray "Fever template wrappers"
heading) and `fever_true.yaml` is a generator spec. A filename-convention glob would inject
both straight into training text. Files on disk but absent from the manifest are ignored;
files in the manifest but absent from disk are a hard error.

**11. Ruleset validation at startup.**
Load `data/uti1.json`, assert `fever_present` exists with `answer_type: "Boolean"` and
`send_to_encoder: true`, abort otherwise. Confirmed present at `data/uti1.json:40–42`.
`Fine_tuning_plan.md` §4.3 requires every `answer_key` to exist in the ruleset, and the project
treats configuration drift as a fail-fast error rather than something to tolerate.

**12. Determinism: per-example seeds, and never iterate an unordered collection.**
`rng = random.Random(f"{seed}|{split}|{i}")` derives a seed per example, so changing `--count`
does not reshuffle already-generated examples. Python seeds `Random` from a string via SHA-512,
not `hash()`, so this is stable across processes and unaffected by `PYTHONHASHSEED` — but that
guarantee is void the moment sampling iterates a `set` or an insertion-order-dependent dict.
**Rule: every collection sampled from is a sorted list.** This is the standard way a
"deterministic" generator silently stops being one.

**13. Standard library only.**
`random`, `hashlib`, `json`, `argparse`, `dataclasses`, `pathlib`, `re`, `unicodedata`,
`difflib`. Nothing is added to `requirements.txt`. This keeps the tool runnable in the
`ruleset-validation` CI job, which installs only `requirements.txt` and `pytest`.

**14. Dataset sizes: train 10,000 / val 1,500 / test 1,500.**
Val and test are small because the fragment pools bound them. The binding constraint is `false`
in val: ~9 val positive-negative fragments × ~55 val filler fragments × 2 orderings = ~990
unique texts, against 375 requested at 25% of 1,500. That is 38% saturation, which the
duplicate-rejection loop absorbs comfortably. At 2,000 it would be 50% and retries start
biting, which silently distorts the realised label distribution. Train is nowhere near
saturated: ~67 × ~259 × 2 ≈ 34,700 for `true` against 1,500 requested.

Generating 100k instead of 10k would add recombination, not language.

---

## Known limits of this run

State these in the run notes; they are the honest reading of what the output is worth.

- **The validation number is a smoke test, not evidence.** With 96 `fever_true` fragments at
  70/15/15, val holds ~14 distinct positive fragments and ~9 negative. Every "true" example in
  val is a recombination of those 14 lexical items. One unlucky fragment moves the score
  several points. `Fine_tuning_plan.md` §4.1 asks for ~200 fragments per signal; we are at
  roughly half for `true` and a third for `false`.
- **Even with cluster-aware splitting, `fever_true`/`fever_false` near-duplicates leak.** DD4
  clusters `fever_null` only. The lint reports the residual cross-split pairs; read that number
  before reading the accuracy.
- **Two-fragment examples are ~2 sentences.** Production free text is longer and messier, so a
  model trained on this meets a distribution shift at inference. That is what
  `Fine_tuning_plan.md` §5.4 exists to fix. This run's model must not be pointed at real text
  and judged.
- **Length and expectation-language confounds are present and unmitigated** (DD6).

---

## Task 1: Library hygiene

**A. State of the world.** Nothing has been built. `data/synthetic/` holds nine `.jsonl` files
that contain no JSON — every line is plain text, one fragment per line — plus a YAML generator
spec. This task is manual data work with no code, and it is a hard prerequisite for Tasks 2–4
because the manifest and cluster markers it produces are the loader's input. Parts of it need
clinical judgement and must not be guessed.

**B. Files and deliverables.**

| File | Deliverable |
|---|---|
| `data/synthetic/*.jsonl` | Renamed to `.txt` via `git mv` (8 library files) |
| `data/synthetic/fever_null.jsonl` | Split into four sub-class files, cluster markers added |
| `data/synthetic/fever_synonyms.jsonl`, `fever_true.yaml` | Left untouched, absent from manifest |
| `data/synthetic/manifest.json` | New — the explicit library declaration |
| `data/synthetic/fever_true.txt` | Two lines adjudicated (see C4) |
| `.gitignore` | `data/synthetic/generated/` added |

**C. Instructions.**

**C1 — Rename.** `git mv` each of the eight library files from `.jsonl` to `.txt`:
`emotional`, `expectations`, `fever_false`, `fever_null`, `fever_true`, `justifiers`,
`tangents`, `uti_speculation`. The extension is actively misleading — zero lines parse as JSON
— and it will trip up the next person. Leave `fever_synonyms.jsonl` and `fever_true.yaml`
alone; they are excluded by the manifest, not by their names.

**C2 — Split `fever_null` by sub-class.** The four sub-classes are contiguous blocks, so this
is a cut-and-paste job, not a reading job. Line ranges in the current file:

| Sub-class | Batch 1 lines | Batch 2 lines | Total | New file |
|---|---|---|---|---|
| hedged / uncertain | 1–5, 16–24 | 45–49, 58–62 | 24 | `fever_null_hedged.txt` |
| metaphorical heat | 6–15 | 50–57 | 18 | `fever_null_metaphor.txt` |
| third-party fever | 25–34 | 63–72 | 20 | `fever_null_thirdparty.txt` |
| historical fever | 35–44 | 73–82 | 20 | `fever_null_historical.txt` |

All four are correctly `null` under `Fine_tuning_plan.md` §1.2, but they are very different
failure modes. Third-party and historical contain the literal word "fever" and are exactly
where a naive model produces false positives. Carrying the sub-class through to output metadata
is what makes error analysis possible.

Delete `fever_null.txt` once the four files exist. The two exact duplicates (old lines 11≡55 in
metaphor, 23≡61 in hedged) can be left in — the loader dedupes them — but removing them by hand
while the file is open is tidier.

**C3 — Add cluster markers to the four `fever_null` files.** Prefix twinned lines with
`[cNN] `, using the same tag for both members of a pair:

```
[c03] A colleague at work went home with a fever on Monday and we share a small office
[c03] One of my work colleagues went home with a fever on Tuesday and we share a small office
```

Tags are scoped per file, so `c03` in `fever_null_hedged.txt` is unrelated to `c03` in
`fever_null_thirdparty.txt`. Lines with no marker are singleton clusters — leave untagged
anything with no twin. The pairing follows batch order: after C2, each file holds its batch-1
items then its batch-2 items, and item *k* of batch 1 generally pairs with item *k* of batch 2.
Verify each pair by eye rather than trusting position — the historical block diverges around
old lines 40 and 78.

Expect roughly 35 pairs across the four files. This is the DD4 fix and it is the single most
valuable 20 minutes in the plan; without it, val is silently a paraphrase of train.

**C4 — Adjudicate two `fever_true` lines.** This needs the user's clinical-language judgement,
not Claude's. `Fine_tuning_plan.md` §1.2 says ambiguous language maps to None, never to True or
False. Two current `fever_true` entries are hedged:

- line 57: "I reckon I've got a bit of a temperature going on, **not sure though**."
- line 58: "**Pretty sure** I'm running warm, keep getting these waves of heat washing over me."

Recommendation: move both to `fever_null_hedged.txt`. Line 58 is genuinely arguable — "pretty
sure" reads closer to assertion than hedge in colloquial English — so it is the user's call.
Labels are by construction, so a mislabelled fragment is a permanently poisoned label; no
downstream code can repair it.

Lines 28, 34 and 96 also contain hedge markers and should **stay** `true`. They are the
deliberate "I assumed it was something else but I checked and I had a temperature" confounders
that `Fine_tuning_plan.md` §2 explicitly asks for — hedge language that gets resolved. Same for
`fever_false` 9, 25 and 35, which are explicit negations wrapped in hedged framing.

**C5 — Write `data/synthetic/manifest.json`.** One entry per library. `signal_key` is `null`
for filler. `fragment_type` is one of `positive | negative | ambiguous | confounder | filler`.

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
    { "name": "fever_null_metaphor", "file": "fever_null_metaphor.txt",
      "signal_key": "fever_present", "fragment_type": "confounder",
      "subclass": "metaphor" },
    { "name": "fever_null_thirdparty", "file": "fever_null_thirdparty.txt",
      "signal_key": "fever_present", "fragment_type": "confounder",
      "subclass": "third_party" },
    { "name": "fever_null_historical", "file": "fever_null_historical.txt",
      "signal_key": "fever_present", "fragment_type": "confounder",
      "subclass": "historical" },

    { "name": "tangents", "file": "tangents.txt",
      "signal_key": null, "fragment_type": "filler", "category": "irrelevant" },
    { "name": "justifiers", "file": "justifiers.txt",
      "signal_key": null, "fragment_type": "filler", "category": "justification" },
    { "name": "emotional", "file": "emotional.txt",
      "signal_key": null, "fragment_type": "filler", "category": "emotional" },
    { "name": "expectations", "file": "expectations.txt",
      "signal_key": null, "fragment_type": "filler", "category": "expectation" },
    { "name": "uti_speculation", "file": "uti_speculation.txt",
      "signal_key": null, "fragment_type": "filler", "category": "self_diagnosis" }
  ]
}
```

Strip the `//` comments — the loader uses `json.load`, not JSON5.

Note on `uti_speculation`: it is safe filler for *this* head (no fragment carries a fever
claim), but "Reckon I've got another kidney infection coming on" stops being neutral the moment
`flank_pain_present` gets a head. The `category` tag exists so it can be reclassified then.

**C6 — Add `data/synthetic/generated/` to `.gitignore`.** Generated datasets are large and
regenerable; committing them adds noise to every diff. `.gitignore` currently has no `data/`
entries, so this is a new line.

**C7 — Expected counts after this task**, for checking the work. Non-blank lines:
`fever_true` 96 (94 if C4 moves both), `fever_false` 60, the four `fever_null` files 24/18/20/20
(82 total, 80 after dedup), `tangents` 110, `justifiers` 100, `emotional` 60, `expectations` 60,
`uti_speculation` 40. Filler total 370. Grand total 608 non-blank, 606 unique.

(The provisional plan's "657 unique fragments overall" was arithmetic drift — it equals
608 + 51 non-blank lines of `fever_synonyms` − 2 duplicates, i.e. it accidentally counted the
scratch file it correctly excludes elsewhere. The per-file table in that document is correct.)

---

## Task 2: Loader and splitter

**A. State of the world.** Task 1 is complete: `data/synthetic/` holds eleven `.txt` libraries,
a `manifest.json`, and cluster markers on the `fever_null` files. No Python exists yet. This
task builds the read-and-split half of the tool — everything up to but not including
recombination.

**B. Files and deliverables.**

| File | Deliverable |
|---|---|
| `scripts/synthetic_data/__init__.py` | New, empty |
| `scripts/synthetic_data/normalise.py` | New — `normalise(text) -> str`, the DD5 definition |
| `scripts/synthetic_data/manifest.py` | New — `Fragment` dataclass, manifest load/validate, dedup, cluster-aware split |
| `scripts/synthetic_data/ruleset.py` | New — DD11 validation against `data/uti1.json` |
| `tests/test_synthetic_recombination.py` | New — normalisation, split, manifest, ruleset, dedup cases |

**C. Instructions.**

**C1 — `normalise.py`.** Implement DD5 exactly, in that order, as a single function. This is
the only place normalisation is defined; nothing else may reimplement it. Keep it dependency-free
(`unicodedata`, `re`).

**C2 — `manifest.py` data structure.**

```python
@dataclass(frozen=True)
class Fragment:
    fragment_id: str          # "fever_true:9c3a1f04"
    text: str                 # verbatim, cluster marker stripped
    library: str
    signal_key: str | None
    fragment_type: str        # positive | negative | ambiguous | confounder | filler
    subclass: str | None
    category: str | None
    cluster_id: str | None    # "fever_null_thirdparty:c03", or None
    split: str                # train | val | test
```

**C3 — Loading.** For each manifest entry, read the declared file as text. Skip blank lines.
Strip a leading cluster marker matching `^\[([A-Za-z0-9_]+)\]\s+` into `cluster_id`, namespaced
as `{library}:{tag}`; the remainder is the verbatim `text`. Build `fragment_id` per DD8 from
`sha1(normalise(text))`.

**C4 — Manifest validation.** Each of these raises with a message naming the offending entry:

- a file named in the manifest is missing from disk
- `fragment_type` is not in the permitted set
- two entries share a `name`
- a `signal_key` is non-null on a `filler` entry, or null on a non-`filler` entry
- a library resolves to zero non-blank lines

Files on disk but absent from the manifest are ignored silently — that is the whole point of
DD10, and `fever_synonyms.jsonl` and `fever_true.yaml` must cause no harm.

**C5 — Deduplication.** Dedupe on `normalise(text)` **globally**, not per library. There are
currently zero cross-library duplicates, so global dedup is a no-op today — but a future
collision between, say, `fever_null_hedged` and `tangents` would be one text carrying two
conflicting labels. If the same normalised text appears in two libraries with different
`fragment_type`, **raise** rather than silently keeping one. Within a single library, keep the
first occurrence. The two known `fever_null` duplicates collapse here if C2 of Task 1 left them
in.

**C6 — Cluster-aware split.** Compute `cluster_key = cluster_id or normalise(text)`, then
`sha256(cluster_key.encode()).hexdigest()` → take the integer of the first 8 hex chars `% 100`
→ 0–69 `train`, 70–84 `val`, 85–99 `test`. Every fragment sharing a cluster key therefore lands
in the same split. Do not use Python's `hash()` — it is salted per process.

**C7 — Empty-cell guard.** After splitting, assert every (library, split) pair has at least one
fragment. Raise naming the empty cells. Per DD9 this is the accepted cost of hash-based
splitting made loud instead of silent.

**C8 — `ruleset.py`.** Load the ruleset JSON, find the question whose `answer_key` matches the
requested signal, assert `answer_type == "Boolean"` and `send_to_encoder is True`. Raise a
clear error naming the signal and the ruleset path otherwise. Do not import from `app/` — this
is an offline tool and must not couple to runtime wiring; reading the JSON directly is correct
here even though `app/services/engine/ruleset.py` also parses these files.

**C9 — Tests** in `tests/test_synthetic_recombination.py`. No `pytestmark` — these are pure
unit tests with no database. Cover:

1. **Normalisation** — curly and straight apostrophes normalise identically; case, trailing
   whitespace and trailing `.`/`!`/`?` are folded; two genuinely different sentences do not
   collide.
2. **Split disjointness** — no `fragment_id` appears in more than one split
   (`Fine_tuning_plan.md` §6, Rule 4).
3. **Cluster cohesion** — all fragments sharing a `cluster_id` land in the same split. Build a
   synthetic two-member cluster in-test; do not rely on the real data having one in an
   interesting position.
4. **Split stability** — adding a fragment to a library does not move any existing fragment's
   split.
5. **Manifest validation** — missing file, unknown `fragment_type`, duplicate `name`, and
   `signal_key`/`fragment_type` disagreement each raise.
6. **Ruleset validation** — a signal absent from the ruleset raises; a signal present but with
   `send_to_encoder: false` raises. Use a synthetic in-test ruleset dict, not `data/uti1.json`,
   so the test validates the rule rather than the committed data.
7. **Deduplication** — identical text in one library collapses to one fragment; the same text
   in two libraries with different `fragment_type` raises.
8. **Empty-cell guard** — a library small enough to leave a split empty raises.

**C10 — Import path.** `tests/` currently imports `app.*` and works because the `Makefile` and
CI both invoke `python -m pytest`, which puts the working directory on `sys.path`.
`scripts.synthetic_data` imports the same way — `scripts/` has no `__init__.py` and does not
need one (PEP 420 namespace packages). Verified, not assumed. Note that bare `pytest` (without
`-m`) would break both `app` and `scripts` imports equally; that is pre-existing and out of
scope here.

**C11 — Check before finishing.** Typecheck/lint the new files and run only this test file:
`ruff check scripts/ tests/test_synthetic_recombination.py && ruff format --check scripts/ tests/test_synthetic_recombination.py`
then `python -m pytest tests/test_synthetic_recombination.py -v`. CI's unit job is the real
gate. Do not run the full suite or `npm run build`.

---

## Task 3: Recombiner, CLI and output

**A. State of the world.** Tasks 1 and 2 are complete: libraries are clean and manifested, and
`manifest.py` yields a deduplicated, cluster-split list of `Fragment` objects validated against
`data/uti1.json`. This task adds label-first recombination, the CLI, the JSONL writer and the
stats sidecar.

**B. Files and deliverables.**

| File | Deliverable |
|---|---|
| `scripts/synthetic_data/recombine.py` | New — label sampling, fragment selection, text assembly |
| `scripts/synthetic_data/__main__.py` | New — argparse CLI, JSONL + stats writer |
| `tests/test_synthetic_recombination.py` | Extended — determinism, invariants, distribution |

**C. Instructions.**

**C1 — Data structures.**

```python
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

`ExampleSpec` exists before any text is chosen. That ordering is the point — it is what makes
label leakage structurally impossible rather than merely avoided.

**C2 — Per-example algorithm.** For example index `i` in a split:

1. `rng = random.Random(f"{seed}|{split}|{i}")` (DD12).
2. Sample the label from the distribution (DD3).
3. If `null`, sample the sub-mode using `--null-ambiguous-ratio`.
4. Select the signal fragment from the split-restricted pool: `true` → one `positive`;
   `false` → one `negative`; `null_ambiguous` → one `ambiguous` or `confounder`;
   `null_structural` → none.
5. Draw filler fragments until the example holds exactly 2. Filler sampling picks a **library
   uniformly, then a fragment within it** — pooling all 370 would let `tangents` (110) outweigh
   `uti_speculation` (40) by 3:1 and lose entropy coverage. For `null_structural`, the two
   fillers must come from **two different libraries**; otherwise a meaningful share of examples
   are two tangents in a row, which reads oddly and narrows the distribution for no gain.
6. Shuffle fragment order — a decisive fragment must be able to sit first or second.
7. Assemble text per DD7.
8. Reject exact-duplicate assembled texts (compare on `normalise`d text); retry up to 50 times,
   then abort with a "pool exhausted" error naming the split and label mode. Never silently
   emit fewer examples than requested, and never silently skew the distribution.

**Filler pools are split-restricted too.** Step 4 restricts the signal pool; step 5 must apply
the same restriction. Filler leakage across splits is exactly as damaging as signal leakage.

**C3 — Invariants that must hold by construction, not by check-after.** A `false` or `null`
example can never contain a `positive` fragment. No example contains both a `positive` and a
`negative`. No example contains a decisive fragment *and* an ambiguous/confounder one for the
same signal (`Fine_tuning_plan.md` §5.2). Structure the selection so these are unrepresentable,
then test them anyway.

**C4 — CLI.**

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
```

Reject a `--dist` that does not sum to 1.0 (within float tolerance) or names an unknown label.
Same seed + same libraries + same flags ⇒ byte-identical output (`Fine_tuning_plan.md` §4.4).
Per DD14 the three runs are `--split train --count 10000`, `--split val --count 1500`,
`--split test --count 1500`.

**C5 — Output schema**, one JSON object per line:

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

JSON `null` maps to Python `None`. No sentinel strings, ever. Write with
`json.dumps(..., ensure_ascii=False)` and `\n` line endings so the byte-identical guarantee is
not platform-dependent.

**C6 — Stats sidecar** at `<out>.stats.json`, written alongside every run. It is the first
thing anyone reaches for when a training run looks wrong. Record:

- realised label counts and sub-mode counts, against requested
- fragment-pool size per library per split
- duplicate-rejection count and max retries hit
- **median and p90 whitespace-token count per label class** (DD6 — the length confound is
  reported here or it is invisible)
- seed, generator version, manifest path, resolved distribution

**C7 — Tests** (extending the Task 2 file):

9. **Determinism** — same seed twice ⇒ byte-identical output.
10. **Seed independence across counts** — the first 100 examples of a `--count 100` run equal
    the first 100 of a `--count 1000` run.
11. **No `positive` fragment in a non-`true` example**, and no `negative` in a non-`false` one.
12. **No example mixes a decisive fragment with an ambiguous/confounder one** for the same
    signal.
13. **Exactly 2 fragments in every example, in every class** — the DD2 guard.
14. **Filler pools are split-restricted** — every `fragment_id` in a `val` example belongs to
    the `val` split.
15. **Label distribution** — assert **exact realised counts** for a fixed seed, not a
    statistical tolerance. The pipeline is deterministic by construction, so a tolerance is both
    weaker and flakier than a golden number. If the counts change, that is a real behaviour
    change and the test should say so.
16. **Pool exhaustion raises** rather than under-emitting — construct a tiny synthetic manifest
    and request more examples than the space holds.

Build tests 9–16 against a small synthetic manifest written to `tmp_path`, not against
`data/synthetic/`. Tests that depend on the real libraries break every time the user edits a
fragment, which is a bad trade for a dataset that is meant to grow.

**C8 — Check before finishing.** Same targeted check as Task 2 C11.

---

## Task 4: Lint mode, filler purity and CI wiring

**A. State of the world.** Tasks 1–3 are complete: the tool loads, splits, recombines and
writes, with tests covering determinism and the label invariants. This task adds the reporting
mode that keeps the libraries honest as they grow, plus the CI change that makes the guard
actually run.

**B. Files and deliverables.**

| File | Deliverable |
|---|---|
| `scripts/synthetic_data/lint.py` | New — hedge-marker, near-duplicate and filler-purity reports |
| `scripts/synthetic_data/__main__.py` | Extended — `--lint` flag |
| `tests/test_synthetic_recombination.py` | Extended — filler purity test |
| `.github/workflows/tests.yml` | `ruleset-validation` job also runs this test file |
| `documentation/arch_testing.md` | Test Index row |
| `documentation/file_structure.md` | `scripts/` description updated |

**C. Instructions.**

**C1 — Hedge-marker report.** Flag lines in the `positive` and `negative` libraries containing
any of: `not sure`, `pretty sure`, `might`, `maybe`, `i think`, `hard to tell`, `reckon`,
`probably`, `could be`. It reports; it **never** relabels.

Be honest in the output about what this is. Run against the current libraries it flags eight
lines — `fever_true` 28, 34, 57, 58, 96 and `fever_false` 9, 25, 35 — of which only 57 and 58
look genuinely mislabelled. That is ~25% precision, because the deliberate confounders in these
libraries are *built out of* hedge language that then gets resolved ("I thought maybe I was
dehydrated but when I checked I had a temperature"). Print a one-line header saying so, so
nobody automates on the output or treats a long list as a crisis.

**C2 — Near-duplicate report.** For each library, compare all normalised-text pairs with
`difflib.SequenceMatcher(...).ratio()` and report pairs ≥ 0.60 **that fall in different
splits** — those are the ones that damage validation (DD4). Report the count per library and
the total, and print the worst 10 with their ratio, split assignment and text.

Expect it to find pairs in `fever_true` and `fever_false`, which DD4 deliberately leaves
unclustered. `fever_null` should report close to zero once Task 1's cluster markers are in
place; a non-trivial count there means a twin pair was missed in Task 1 C3 and should be
tagged. This report is the feedback loop on that manual pass.

`SequenceMatcher` on 96 fragments is ~4,500 comparisons per library — fast enough that no
optimisation is warranted.

**C3 — Filler purity check.** Screen every `filler` fragment against a fever lexicon:
`fever`, `febrile`, `temperature`, `feverish`, `shiver`, `chills`, `sweats`, `hot`, `warm`,
`burning up`, `pyrexia`, `rigor`, `clammy`, `flushed`, `boiling`, `freezing`. Any hit is
reported as a suspected leak.

**Match on word boundaries** (`\b…\b`), case-insensitively. Naive substring matching hits
`photos` (→ "hot") in `emotional:56` and `shot` (→ "hot") in `justifiers:82`, so the check
fails on day one against clean data if this is skipped. Both are already known incidental hits.

The current filler libraries are clean: three incidental matches across all five, none thermal
(`emotional:56` "worried about me from the photos I sent", `justifiers:82` "unemployed for 8
months", `expectations:59` "referred for lithotripsy"). Whatever the final lexicon produces on
the clean libraries is the allowlist baseline — record those specific `fragment_id`s in the test
so a *new* hit fails while the known three do not.

**C4 — Test 17, filler purity.** This one runs against the **real** `data/synthetic/` libraries,
unlike tests 9–16. That is deliberate: its entire purpose is to fail when someone edits a filler
library and reintroduces fever language, which cannot be caught by a synthetic fixture. Assert
that the set of lexicon hits equals the recorded baseline exactly.

**C5 — CI wiring.** `.github/workflows/tests.yml` splits changes into `code` (`'**'` minus
`**/*.md` minus `data/**`) and `rulesets` (`data/**`). A PR that only edits a filler library is
therefore a `data/`-only change: it runs `ruleset-validation` and **skips the unit job** — so
test 17, the guard whose only job is to catch exactly that edit, would not run.

Fix: add this test file to the `ruleset-validation` job, which already covers `data/**` and
already installs enough (the new code is stdlib-only per DD13):

```yaml
      - name: Validate committed rulesets
        run: python -m pytest tests/test_data_rulesets.py -v

      - name: Validate synthetic fragment libraries
        run: python -m pytest tests/test_synthetic_recombination.py -v
```

The unit job continues to run the whole file on code changes. The overlap on a PR touching both
is the workflow's existing intended behaviour, not a new inefficiency.

**C6 — Documentation.** Add a Test Index row to `documentation/arch_testing.md` under "Python
unit tests" — the maintenance rule at the top of that file makes it the single source of truth
for what each test file covers, and it is the only place test files are described. Note in the
row that test 17 reads the real `data/synthetic/` tree while the rest use synthetic fixtures,
and that the file is also run by the `ruleset-validation` CI job.

Update the `scripts/` line in `documentation/file_structure.md` — currently "One-time management
commands for deployment and administration", which no longer covers an offline dataset
generator.

**C7 — Check before finishing.** Same targeted check as Task 2 C11, plus run the lint against
the real libraries once (`python -m scripts.synthetic_data --lint --manifest
data/synthetic/manifest.json`) and paste its summary counts into the commit message. That
output is the run's baseline record of library health.
