# Implementation plan: consolidating the training run console

Supersedes P1, P2, P3 (partly) and P6 of
`training_gui_usability_provisional.md`. P4, P5, P7–P10 of that document are
untouched and still open.

---

## Plan

Three changes to the local training run console (`architecture.md` 3.17,
`scripts/training_gui/`), in this order, each a separate task:

1. **Shrink the catalogue and add two composite entries.** Delete the
   single-signal and single-cell training entries nobody used. Add one entry per
   comparison that runs the smoke test, generates every cell that comparison
   needs, trains the comparison and scores it — one button, in sequence.
2. **Make a 26-step run legible** (was P1): a step checklist with per-step
   status and duration, total and current-step elapsed time, and the tab title
   as a status indicator.
3. **Remember the remaining dropdowns** (was P2, reduced): `localStorage` per
   entry id and parameter name. Nothing else.

Tasks 2 and 3 depend on task 1 only for the step labels task 1 introduces.
Task 3 is genuinely small and could be dropped without affecting the rest.

## Scope

**In scope:** `scripts/training_gui/runs.json`, `catalogue.py`, `server.py`
(one shaping function), `static/index.html`, `tests/test_training_gui.py`,
`documentation/Quickstart.md`, `documentation/architecture.md` 3.17.

**Out of scope:**

- `scripts/encoder_training/` and `scripts/synthetic_data/`. Nothing below
  changes a training command's behaviour; it changes which commands the console
  offers and how their progress is displayed.
- `runner.py`. The manifest already carries everything tasks 2 and 3 need
  (`started_at` / `ended_at` per step and per run, and a per-step `status` of
  pending / running / succeeded / failed / skipped). One new *presentational*
  field travels from the catalogue through `server.py`, not from the runner.
- Relaxing the browser-may-only-*name*-a-run rule. The composite entries have
  **no parameters at all**: every argv element in them is a literal committed in
  `runs.json`. This is a tightening, not a relaxation.
- Any interpretation of a result by the console. Task 1 adds a `score-companions`
  step to the composites, but that is the training CLI's own scorer, invoked as a
  step like any other; the console still only shows what the step printed.
- P5 (preflight), P7 (save preview), P8 (run history), P9, P10. Task 1 removes
  most of P5's motivation — see the design decisions.

---

## Design decisions

### DD-A. What gets deleted, and what that costs

Deleted: **`finetune`**, **`decl-finetune`**, **`decl-finetune-all`**,
**`decl-generate-folds`**.

These are the single-arm and single-cell training runs. The honest reason they
go is not that they are slow but that **their output cannot be compared with the
comparison runs' output**. `declarative-compare` computes paired statistics
across cells inside one invocation, because that is the only place the pairing
exists; a `decl-finetune-all` report for one cell is a number that cannot be set
beside another cell's number and called a difference. They were a way to see one
cell run before committing four hours, and after several sweeps that reassurance
is not worth a button.

What is lost, stated plainly: **there is no longer a ~10-minute or ~1-hour GPU
run in the catalogue.** After the smoke test, the next thing that touches the GPU
is a three-to-four-hour comparison. If a driver or wheel change breaks training
in a way `smoke-cuda` does not catch, the console will no longer surface that in
ten minutes. This is a real regression and it is accepted deliberately: the
composite runs the smoke test first, the generation steps take ~25 minutes before
any GPU work starts, and a broken environment shows up in the first training step
of the comparison rather than three hours in.

`decl-generate-folds` (one signal, one cell) goes because
`decl-generate-folds-all` does the same thing for the whole cell at
stdlib speed. There is no case for generating one signal of a cell.

### DD-B. What survives, and why each one earns its place

| Entry | Why it stays |
|---|---|
| `smoke-cuda` | Ten seconds, and the first thing to run after a driver change. Also step 1 of both composites. |
| `score-companions` | Reads a written comparison's reports back with no GPU. Wanted on its own after a run has been saved and pulled onto another machine. **Its committed form is wrong today — see DD-E.** |
| `generate-folds` | Writes the default tree. Consumed by `merge-folds`, not by anything else left in the catalogue. **Open question, see below.** |
| `merge-folds` | The input to joint multi-head training, which is planned and not yet built. **Open question, see below.** |
| `decl-generate-folds-all` | The escape hatch for generating one odd cell without a four-hour run attached. Stdlib, ~1 minute a signal. |
| `decl-compare-2x2` | The escape hatch for re-running the four hours when the cells are already on disk. **Load-bearing — see DD-D.** |
| `decl-compare-register` | Same, for the register arm. |
| `decl-sweep-2x2` **(new)** | The one button. |
| `decl-sweep-register` **(new)** | The one button for the register arm. |

Nine entries, down from eleven, and the two that matter are the two new ones.
Nine is still more than the provisional plan's P3 grouping was written for, but
the grouping is now much less urgent: seven of the nine are escape hatches a
reader can skim past, and the two composites can simply be placed first.

**Open question for you:** with `finetune` gone, nothing in the catalogue
consumes `generate-folds`'s default tree except `merge-folds`, and nothing
consumes `merge-folds`'s merged tree at all. They are two buttons for a training
path that is not yet built. Keeping them means two dead buttons; removing them
means re-adding them when joint multi-head training lands. I lean towards
**keeping them** — they are cheap, correct, and the merged tree is the input to
the next real piece of work — but if you want the catalogue down to seven, these
are the two to cut.

### DD-C. What the composites contain

`decl-sweep-2x2`, in order, 26 steps:

1. `smoke-cuda` — 10 seconds, fails immediately on a broken driver.
2. **24 generation steps** — six signals × the four cells the 2×2 compares
   (`c0.0-d0.0`, `c0.0-d0.3`, `c0.5-d0.0`, `c0.5-d0.3`), each writing to
   `data/synthetic/generated/decl/c{c}-d{d}`. ~25 minutes total, stdlib, no GPU.
3. `declarative-compare` over the four cells — the existing `decl-compare-2x2`
   step, verbatim. ~4 hours.
4. `score-companions --report-dir reports/encoder_training/decl/comparison` —
   seconds, and it means the run ends with the scorecard in the log instead of
   requiring a second button press. See DD-E.

`decl-sweep-register` is the same shape with three cells (`c0.5-d0.0`,
`c0.5-d0.3`, `c0.5-d0.6`), so 1 + 18 + 1 + 1 = 21 steps, and
`--report-dir reports/encoder_training/decl/register`.

Neither composite takes a parameter. The cells are already literals in the
comparison steps, so making them literals in the generation steps too keeps the
whole entry substitution-free.

**The register composite regenerates two cells the 2×2 composite already wrote.**
That is deliberate: the alternative is a hidden dependency ("run the 2×2 first"),
and the generator is deterministic from `(seed, salt, fold, split, shares)`, so
regenerating a cell produces byte-identical files. Twelve wasted minutes on a
three-hour run buys a self-contained entry.

### DD-D. Re-running a composite wastes ~25 minutes, and that is why the bare comparison entries stay

Because generation is deterministic, re-running a composite is *safe* — it
rewrites the same bytes. It is not *free*: ~25 minutes of regeneration on a
four-hour run, every time.

Two mechanisms were considered for skipping generation when the tree is already
there, and both are rejected:

- **A `"skip_if_exists"` per-step field.** New runner behaviour, and it turns a
  presence check into a correctness claim. A tree generated at a different fold
  count, or half-written by a stopped run, passes a presence check and produces a
  comparison against the wrong data — silently, four hours later. This is the
  same caveat P5 carries, but where P5 only *warns*, this would *act*.
- **A `"skip generation" checkbox`.** A boolean the browser sends that changes
  which steps run. It is within the letter of the catalogue rule but against its
  spirit, and it is exactly the control someone leaves ticked by accident.

The accepted answer is simpler and needs no new mechanism: **`decl-compare-2x2`
and `decl-compare-register` stay in the catalogue as bare entries.** If a
composite's comparison fails at hour three, the cells are on disk and the bare
comparison entry re-runs just the training. Deciding whether the cells are good
is a human decision made with the log open, which is the right place for it.

This also removes most of P5's motivation. P5 existed to catch "I forgot to
generate the cell", and the composite makes forgetting impossible for the
one-button path. P5 would still be worth something for the two bare comparison
entries; it is no longer worth an endpoint on its own. Treat P5 as deferred, not
rejected.

### DD-E. `score-companions` is pointed at the wrong directory today

`run_declarative_compare` writes `<signal>.companion_comparison.json` into its
`--report-dir`, which for `decl-compare-2x2` is
`reports/encoder_training/decl/comparison`. The committed `score-companions`
entry passes no `--report-dir`, so it reads `DEFAULT_REPORT_DIR`
(`reports/encoder_training/`) — a directory the declarative comparisons never
write to. **The button as committed cannot score the runs the console actually
performs.** This is a pre-existing bug, not something this plan introduces, and
it is fixed here because task 1 is editing the entry anyway.

The fix: give `score-companions` a `report_dir` parameter with two committed
choices, `reports/encoder_training/decl/comparison` (default) and
`reports/encoder_training/decl/register`. Both are literals in `runs.json`, so
the browser still only names a choice. The composites pass the matching
directory as a literal in their own final step.

### DD-F. Step labels are a new catalogue field, and task 2 needs them

"Step 14 of 26" is not information. A checklist of 26 lines each showing a
300-character command line is not information either. Each step therefore gets a
short human label.

The label is a new optional presentational field on a catalogue entry:

```json
"step_labels": ["CUDA smoke test", "Generate c0.0-d0.0 · fever", ...]
```

Validated in `catalogue.py`: if present it must be a list of non-empty strings
whose length equals the number of steps. Absent, the page falls back to the
step's index. It is presentational only — nothing derived from it reaches an
argv.

The alternative considered and rejected was deriving the label on the page from
the argv (pull out `--signal` and `--out-dir`). That works until a step has
neither, and it puts display logic in the page that has to track flag names in
`scripts/encoder_training/`. A committed label is one more thing to keep in sync,
but the sync failure is cosmetic and the test in task 1 catches a length
mismatch.

### DD-G. P2 shrinks to almost nothing, and its second half is cut

The provisional plan's P2 had two halves. After task 1:

- **Persisting dropdowns** is still worth doing, but there are only three
  dropdowns left in the whole catalogue (`generate-folds`'s signal,
  `decl-generate-folds-all`'s two shares, `score-companions`'s report dir) and
  none of them is on the button you press most days. It is ~20 lines and it stays
  in the plan on that basis, not because it is important.
- **The cross-card "current cell" control is cut entirely.** It existed because
  companion share and declarative share had to be set identically on three cards.
  After task 1 they appear on one card. The control would be a cross-card
  abstraction over a single card.

### DD-H. `runs.json` will roughly double, by hand, and a test guards it

Written out literally, the two composites add ~42 near-identical twenty-element
steps and take `runs.json` from ~18KB to ~33KB. Adding an expansion mechanism to
the catalogue format (a `for_each` over signals, say) would shrink it, and is
rejected: the catalogue's entire security argument is that every argv element is
a literal a human committed, and a loop in the loader is the first crack in that.

The mitigation is a test, not a mechanism. Task 1 extends the existing
`test_the_comparison_entries_point_at_directories_the_sweep_produces` to assert
the property that actually costs four hours when it is wrong: **within each
composite, the set of `--out-dir` values across its generation steps equals the
set of `--cell` values on its comparison step.** A typo in a share (`d0.3` in one
place, `d0.6` in the other) fails that test in CI in under a second, instead of
failing in the fourth hour of a run.

---

## Task 1: Catalogue consolidation

### A. State of the world

The console's catalogue (`scripts/training_gui/runs.json`) offers eleven entries.
In practice one workflow is used: smoke test, then generate the cells, then the
2×2 comparison — three button presses with a manual wait between each, and seven
entries that are never touched. Nothing in this plan has been implemented yet;
this is the first task.

### B. Files and deliverables

| File | Deliverable |
|---|---|
| `scripts/training_gui/runs.json` | Four entries removed, two added, `score-companions` given a parameter, `step_labels` added to the multi-step entries |
| `scripts/training_gui/catalogue.py` | `step_labels` parsed and validated onto `RunEntry` |
| `scripts/training_gui/server.py` | `_entry_json` carries `step_labels` through |
| `tests/test_training_gui.py` | Existing catalogue-shape tests updated; new cell-coverage test; new `step_labels` validation tests |

### C. Instructions

1. **`runs.json` — remove** the entries with ids `finetune`, `decl-finetune`,
   `decl-finetune-all` and `decl-generate-folds`.

2. **`runs.json` — fix `score-companions`.** Add a `report_dir` parameter:

   ```json
   "parameters": [{
     "name": "report_dir",
     "label": "Report directory",
     "choices": ["reports/encoder_training/decl/comparison",
                 "reports/encoder_training/decl/register"],
     "default": "reports/encoder_training/decl/comparison"
   }]
   ```

   and append `"--report-dir", "{report_dir}"` to its single step. Update the
   description to say which comparison's reports it reads.

3. **`runs.json` — add `decl-sweep-2x2`.** Id `decl-sweep-2x2`, no `parameters`.
   Name it something that reads as the main event ("The 2x2 declarative sweep,
   end to end"). The description must state: ~4.5 hours; that it regenerates the
   four cells every time even if they are already on disk; and that
   `decl-compare-2x2` is the entry to use if the cells exist and only the
   training needs repeating.

   Its `steps`, in order:
   - `["-m", "scripts.encoder_training", "smoke-cuda"]`
   - For each cell in `c0.0-d0.0`, `c0.0-d0.3`, `c0.5-d0.0`, `c0.5-d0.3`, and
     for each signal in `fever_present`, `dysuria_present`, `flank_pain_present`,
     `haematuria_present`, `nocturia_present`, `urinary_frequency_present`
     (24 steps): copy the corresponding step from the existing
     `decl-generate-folds-all` entry with `{companion_share}` and
     `{declarative_share}` replaced by that cell's literal values. Cell-major
     order, signals in the order above.
   - The single step from the existing `decl-compare-2x2` entry, verbatim.
   - `["-m", "scripts.encoder_training", "score-companions", "--report-dir",
     "reports/encoder_training/decl/comparison"]`

   `recent_uti_present` is not one of the six and must not appear.

4. **`runs.json` — add `decl-sweep-register`.** Same shape, cells `c0.5-d0.0`,
   `c0.5-d0.3`, `c0.5-d0.6`, the `decl-compare-register` step verbatim, and
   `--report-dir reports/encoder_training/decl/register` on the final step.
   21 steps. Its description says it regenerates two cells `decl-sweep-2x2` also
   writes, and that this is deliberate and harmless because generation is
   deterministic.

5. **`runs.json` — `step_labels`.** Add to `decl-sweep-2x2`,
   `decl-sweep-register` and `decl-generate-folds-all`. Labels are short and
   scannable: `"CUDA smoke test"`, `"Generate c0.0-d0.0 · fever_present"`, …,
   `"Compare the four cells (~4h)"`, `"Score the companion thresholds"`. For
   `decl-generate-folds-all`, the cell is a parameter, so label by signal alone.

6. **`catalogue.py`.** Add `step_labels: tuple[str, ...] = ()` to `RunEntry`.
   In `_parse_entry`, parse `item.get("step_labels")`: absent or `None` gives
   `()`; otherwise it must be a list of non-empty strings whose length equals
   `len(steps)`, and anything else raises `CatalogueError` naming the entry, in
   the style of the surrounding validators. Add a paragraph to the module
   docstring saying the field is presentational and never reaches an argv.

7. **`server.py`.** In `_entry_json`, add `"step_labels": list(entry.step_labels)`.
   No other change.

8. **`tests/test_training_gui.py`.**
   - `test_the_committed_catalogue_loads`: update the expected id list to the
     nine ids, in catalogue order.
   - `test_every_declarative_cell_writes_to_its_own_directories`: the loop over
     `("decl-generate-folds-all", "decl-finetune-all")` becomes
     `("decl-generate-folds-all",)`. Keep the docstring's reasoning; drop the
     sentence about `finetune`.
   - `test_the_comparison_entries_point_at_directories_the_sweep_produces`:
     keep as is for the two bare comparison entries.
   - `test_the_declarative_sweep_scores_the_real_text_holdout`: the entry tuple
     becomes `("decl-compare-2x2", "decl-compare-register", "decl-sweep-2x2",
     "decl-sweep-register")`.
   - `test_the_declarative_sweep_covers_the_six_trainable_signals`: the entry
     tuple becomes `("decl-generate-folds-all",)`; add a separate assertion for
     the composites, where `--signal` appears 24 and 18 times respectively — six
     distinct signals per cell, `recent_uti_present` absent.
   - `test_the_committed_catalogue_names_the_base_model_explicitly`: `finetune`
     is gone. Rewrite it against `decl-compare-2x2` — assert `--base-model` is
     present and its value is `roberta-base`. The `base_model` parameter
     assertions go with the entry.
   - **New** `test_each_composite_generates_exactly_the_cells_it_compares`: for
     each of the two composites, collect the `--out-dir` values across its steps
     and the `--cell` values on its comparison step and assert the two sets are
     equal and non-empty. This is DD-H's guard and the most valuable test in the
     task.
   - **New** `test_each_composite_starts_with_the_smoke_test`: step 1 of each
     composite is exactly `("-m", "scripts.encoder_training", "smoke-cuda")`.
   - **New** `test_the_composites_take_no_parameters`: both have empty
     `parameters`, so no browser-supplied string reaches them at all.
   - **New** `test_score_companions_reads_a_directory_the_comparisons_write`:
     every choice of `score-companions`'s `report_dir` parameter appears as a
     `--report-dir` value on some comparison entry. This is DD-E's guard.
   - **New**, near the other `catalogue.py` validation tests: a `step_labels`
     whose length does not match the step count is rejected; a non-list is
     rejected; an empty-string label is rejected; an absent field yields `()`.

9. **Check:** `pytest tests/test_training_gui.py` and a typecheck on the two
   changed Python files. Do not run the full suite; CI's unit job is the gate.

---

## Task 2: Make a 26-step run legible (was P1)

### A. State of the world

Task 1 is complete: the catalogue is nine entries, the two composites are 26 and
21 steps, and every entry carries `step_labels` where it has more than one step.
The page still renders progress as the single string "step 14 of 26" plus the
current command line, which for the composites is close to useless. All the data
this task needs is already in `/api/status` and ignored by the page.

### B. Files and deliverables

| File | Deliverable |
|---|---|
| `scripts/training_gui/static/index.html` | Step checklist, elapsed times, tab title and favicon as status |
| `scripts/training_gui/server.py` | `_status_json` also carries the entry's `step_labels` (read-only shaping) |
| `tests/test_training_gui.py` | One test that `/api/status` carries `step_labels` for a run of a labelled entry |

No new endpoints. No `runner.py` change.

### C. Instructions

1. **`server.py`.** `_status_json` currently takes only the manifest. Give it
   access to the catalogue entry (the manifest records `entry_id`) so it can add
   `"step_labels": [...]`, falling back to `[]` when the entry is unknown or
   unlabelled. Keep this a pure shaping function — look the entry up in the
   `entries` dict `create_app` already builds and pass the labels in, rather than
   loading the catalogue inside the function.

2. **`index.html` — the step checklist.** Replace the `#step` one-liner with a
   list rendered from `status.steps`, one row per step:
   `<label> · <status> · <duration>`. Status is the step's own `status` field
   (pending / running / succeeded / failed / skipped) rendered as a glyph and a
   colour reusing the existing `--good` / `--bad` / `--muted` tokens. Duration is
   `ended_at - started_at`, or `now - started_at` for the running step, or blank
   for a pending one. Label is `step_labels[i]` falling back to `step N`.

   Twenty-six rows is a lot of page. Collapse succeeded steps into a single
   summary row ("18 steps succeeded · 24m") with a disclosure that expands them,
   and always show the running step, any failed step, and the next few pending
   ones. Keep the current command line visible below the list, as now.

3. **`index.html` — elapsed times.** Beside the verdict: total elapsed, from the
   manifest's `started_at` to `ended_at` or now. Beside the running step: its own
   elapsed. Format as `4h 12m` / `24m 03s` / `03s`. This is arithmetic on
   timestamps the page already receives; parse them as ISO 8601 and be careful
   that a still-running step has `ended_at: null`.

4. **`index.html` — tab title and favicon.** While running, `document.title` is
   `▶ 14/26 · The 2x2 declarative sweep`; on a terminal status it becomes
   `✅ Succeeded · <entry name>` or `❌ Failed · <entry name>`; idle restores
   `Encoder training console`. Swap the `<link rel="icon">` href between three
   inline data-URI SVG dots (neutral / running / good / bad) at the same time.
   Note that the current favicon is deliberately `data:,` to avoid a 404 — keep
   the data-URI approach rather than adding files.

5. **Not in this task:** browser notifications and the finish sound. The
   provisional plan left this open; the answer is that the tab title ships first
   and notifications are only worth a permission prompt if the tab title turns
   out not to be enough. Revisit after a sweep or two.

6. **Optional, and cheap while the page is open (was P4):** a **Copy log**
   button and a **Copy the failing step's output** button, and an expand control
   on the 420px log box. A 26-step run makes both more valuable, not less, since
   the failing step's output is now buried much deeper. Add them if the task has
   room; they are page-only and have no tests.

7. **Check:** `pytest tests/test_training_gui.py`. The page itself has no test
   harness — verify it by hand against a running console, or against a
   two-step fake run.

---

## Task 3: Remember the remaining dropdowns (was P2, reduced)

### A. State of the world

Tasks 1 and 2 are complete. Three dropdowns remain in the whole catalogue:
`generate-folds`'s signal, `decl-generate-folds-all`'s two shares, and
`score-companions`'s report directory. Every reload resets all three to their
committed defaults. This task is small on purpose — see DD-G for why what
remains of P2 is worth this much and no more.

### B. Files and deliverables

| File | Deliverable |
|---|---|
| `scripts/training_gui/static/index.html` | Dropdown values persisted in `localStorage` and restored on load |

No server change, no catalogue change, no test.

### C. Instructions

1. In `renderCatalogue`, after building each `<select>`, read
   `localStorage.getItem("traingui:" + entry.id + ":" + parameter.name)`.
   **Validate it against `parameter.choices` before using it** — an unknown
   stored value falls back to `parameter.default`, so editing the catalogue
   cannot resurrect a choice that no longer exists. Then set `select.value`.

2. In the existing `select.onchange`, write the new value under the same key
   before calling `renderCommands(entry)`.

3. Wrap both the read and the write in `try`/`catch`. `localStorage` throws in a
   private window and on a browser configured to block site data, and a console
   that fails to render its catalogue because a convenience feature threw is a
   much worse outcome than one that forgets a dropdown.

4. **Explicitly not in this task:** the cross-card "current cell" control from
   the provisional plan's P2. It is cut — see DD-G.

5. **Check:** by hand. Pick a non-default value, reload, confirm it survived;
   then edit a `choices` list in `runs.json` to drop that value, reload, and
   confirm the dropdown falls back to the default rather than showing a stale one.

---

## Task 4: Documentation

### A. State of the world

Tasks 1–3 are complete. `Quickstart.md` describes a workflow of picking
parameters and pressing Run on individual entries, and `architecture.md` 3.17
lists the console's key files and invariants. Neither mentions the composites.

### B. Files and deliverables

| File | Deliverable |
|---|---|
| `documentation/Quickstart.md` | The "Start the training run console" section rewritten around the one-button path |
| `documentation/architecture.md` | 3.17 updated: the composite entries and the no-parameter tightening |
| `documentation/planned_updates/training_gui_usability_provisional.md` | A header noting which items this plan superseded |

### C. Instructions

1. **`Quickstart.md`.** Rewrite the paragraph beginning "On the page:" to lead
   with the composite: press one button, it runs the smoke test, generates the
   cells, trains the comparison and scores it, and takes about four and a half
   hours. Then say the bare comparison entry is what to use if the cells are
   already on disk and only the training needs repeating. Keep the existing
   Stop / Save / Update paragraph and the "what the console does not do"
   paragraph unchanged — both are still exactly right.

2. **`architecture.md` 3.17.** In **Invariants**, strengthen the second bullet:
   the browser can name a run and, for the composite sweeps, supplies no string
   at all. In **Scope**, mention that the catalogue's main entries run a
   comparison end to end from smoke test to scorecard. Do not restate the step
   lists — they are in `runs.json` and will drift.

3. **`training_gui_usability_provisional.md`.** Add two lines at the top: which
   items this plan superseded (P1, P2, P3 in part, P6), which are cut (P2's cell
   control), which are deferred with reduced motivation (P5), and which are
   untouched (P4, P7–P10).

4. **Check:** none beyond reading it back.

---

## Open questions

1. **`generate-folds` and `merge-folds`** — keep them as two buttons for a
   training path that is not yet built, or cut the catalogue to seven entries and
   re-add them when joint multi-head training lands? (DD-B)
2. **Losing the short GPU run.** After task 1 the shortest thing that trains
   anything is three hours. Is `smoke-cuda` plus the composite's first training
   step enough of an early-failure signal, or do you want a deliberately tiny
   "train one signal, one fold" entry kept purely as a canary? (DD-A)
3. **P6's confirm dialog.** The provisional plan wanted a confirm before starting
   anything over 30 minutes and before Stop. With the composite as the main
   button, a confirm on Run would fire on the press you make most often, which is
   how confirms get clicked through. I would ship **only** the confirm on Stop
   (which can throw away four hours) and drop the confirm on Run. Agreed?
4. **`score-companions` as a step.** It is the training CLI's scorer, not the
   console's, but it does put a scored verdict at the end of the console's log
   for the first time. If that reads as the console interpreting a result to you,
   say so and it comes out of the composites and stays a separate button. (DD-E)
