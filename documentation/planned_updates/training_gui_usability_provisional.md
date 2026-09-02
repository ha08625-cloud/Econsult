# Provisional plan: making the training run console easier to live with

## Scope

Usability work on the local training run console (`architecture.md` 3.17,
`scripts/training_gui/`). It exists because the console is about to be used
tens to low hundreds of times, and the friction that is tolerable on the tenth
run is not tolerable on the hundredth.

**In scope:** the single page (`scripts/training_gui/static/index.html`), the
read-only endpoints in `server.py`, presentational fields in `runs.json`, and
one new read-only endpoint per accepted item.

**Out of scope, deliberately:**

- Anything that interprets a result. The console shows that a run finished and
  where the JSON landed; `reports/encoder_training/README.md` still owns the
  write-up. Nothing below adds a chart, a metric, or a verdict on a number.
- Any change to `scripts/encoder_training/` or `scripts/synthetic_data/`.
- Relaxing DD4: the browser may still only *name* a run. No proposal below
  sends a command, an argument, a path or a branch name from the page. Where an
  item needs a path (P5), the path template is committed in `runs.json` and the
  page sends a catalogue id, exactly as `/api/run` does today.
- Changing the `127.0.0.1` bind. See "What this plan does not fix".

**Key files:** `scripts/training_gui/static/index.html` (most of the work),
`server.py`, `runs.json`, `catalogue.py`, `tests/test_training_gui.py`

**Related:** `documentation/Quickstart.md` (the console's user-facing
instructions — needs updating for whatever is accepted),
`documentation/planned_updates/training_run_gui_provisional.md` and
`..._implementation.md` (the original build; three items below reverse an
explicit exclusion in it, and say so).

---

## What the console is like to use today

The page has four sections: a flat list of all 11 catalogue entries with their
literal command lines expanded, a live log with a one-line status, a
manual-refresh list of changed paths under `reports/` and `models/`, and two git
buttons.

The mismatch with how it is actually used:

- **The runs are long and the page assumes you are watching.** `decl-finetune`
  is ~10 minutes, `decl-finetune-all` ~1 hour, `decl-compare-2x2` ~4 hours. The
  page shows "step 3 of 6" and the current command, and nothing else: no elapsed
  time, no per-step timings, no signal you can notice from another window. For a
  four-hour run the page's entire progress model is one integer.
- **The page is stateless in the ways that cost typing.** Every reload resets
  every dropdown to its default. Working a single sweep cell means re-picking
  companion share and declarative share on two or three separate cards, every
  time.
- **Everything is expanded all the time.** All 11 entries render their
  description and all their command lines at once. `decl-finetune-all` alone
  contributes six near-identical ~300-character lines. The Run button you want
  is usually well below the fold, and the two four-hour runs sit in the same
  undifferentiated list as the ten-second CUDA smoke test.
- **Nothing catches the mistake the catalogue is shaped to allow.** `decl-finetune`
  reads a fold tree that `decl-generate-folds` must have written; `decl-compare-2x2`
  needs all four cells present. Miss that and you find out from a traceback.
- **Only the current run exists.** Every past run's log and manifest is sitting
  in `dev_output/training_gui/`, and none of it is reachable from the page. Start
  a second run and the first one's log is gone from the screen for good.
- **The failure path ends in copy-and-paste.** The documented next move after a
  failed run is to bring the error to a chat. To do that you scroll a 420px log
  box, select by hand, and hope you got the whole traceback.

---

## Proposed changes, ranked by value per unit of work

Each item is independent. P1–P4 are the ones I would do; P5–P8 are worth
discussing; P9–P10 I would probably not do.

### P1. Make a long run legible from across the room — and from the tab bar

The single highest-value change, and mostly page-side.

- **Elapsed time.** Total elapsed beside the verdict, and elapsed for the
  current step. The manifest already carries `started_at`/`ended_at` per step
  and per run, so this is arithmetic on data the page already receives.
- **A step checklist instead of "step 3 of 6".** One line per step showing its
  status (pending / running / succeeded / failed / skipped) and its duration,
  with the signal name visible. For the six-signal runs this turns an integer
  into a picture of where the hour went. `_status_json` already ships the full
  `steps` array; the page just ignores it.
- **Tab title and favicon as the status indicator.** `document.title` becomes
  `▶ 3/6 · decl-finetune-all` while running and `✅ Succeeded` / `❌ Failed`
  when it ends, with a matching favicon dot. This is what makes an hour-long run
  watchable from a browser you have tabbed away from.
- **A finish signal.** The Notification API (permission asked on first use, and
  only then) and/or a short sound when a run reaches a terminal status, both
  behind a checkbox that remembers itself. Off by default is defensible; I would
  default the tab title on and the notification off.

*Design decision needed:* whether the finish signal is worth a browser
permission prompt at all, or whether the tab title alone is enough. I lean
towards shipping the tab title and favicon first and adding notifications only
if the tab title turns out not to be enough.

*Effort:* page only, no new endpoints. Small.

### P2. Remember what was selected

Persist every dropdown's value in `localStorage`, keyed by entry id and
parameter name, and restore it on load. Values are still validated against the
committed `choices` before use — an unknown stored value falls back to the
default, so a catalogue edit cannot resurrect a stale choice.

Optionally a **"cell" control at the top of the declarative section** that sets
companion share and declarative share on every `decl-*` card at once, since in
practice those two values move together across three cards. This is the bigger
of the two and I would treat it as a separate decision: it introduces a
cross-card control, which is a genuine complication to a page whose current
virtue is that each card is self-contained.

*Effort:* localStorage is trivial. The cell control is small but is a real UI
concept, not a tweak.

### P3. Group and collapse the catalogue

- Group the entries into declared sections (`"group"` becomes a presentational
  field in `runs.json`): **Checks** (smoke-cuda, score-companions), **Data**
  (generate-folds, merge-folds, decl-generate-folds\*), **Training**
  (finetune, decl-finetune\*), **Comparisons** (decl-compare-\*). Order within a
  group stays the catalogue's order.
- Collapse the command lines behind a disclosure, expanded by default for
  single-step entries and collapsed for multi-step ones. The commands stay one
  click away and stay literal — showing the exact command was a deliberate
  design decision and this does not reverse it, it stops six 300-character
  duplicates from burying the rest of the page.
- Show the **estimated duration as a badge** (`~10s`, `~1h`, `~4h`), promoted
  out of the prose descriptions into a declared `"duration_hint"` field. It is
  already written in every description; putting it in a field makes it scannable
  and lets P6 use it.

*Effort:* page plus two optional presentational fields in `runs.json` and their
validation in `catalogue.py`. Small-to-medium, mostly mechanical.

### P4. Copy the log

A **Copy log** button (and a **Copy the failing step's output** button when a
run fails, which is the part you actually want). The documented end of a failed
run is "bring the error to a chat", and the page currently makes that a manual
selection in a scrolling box. Also worth: an expand control on the log box, so a
traceback can be read without a 420px viewport.

*Effort:* page only. Trivial. Highest value-to-effort ratio in the list after P1.

### P5. Warn before a run that cannot succeed

Add an optional declared `"requires"` to a catalogue entry: a list of path
templates, substituted from the same parameters as the steps
(`data/synthetic/generated/decl/c{companion_share}-d{declarative_share}`). A new
read-only `GET /api/preflight?id=…&<parameters>` answers whether each resolved
path exists. The page shows a green tick or an amber "the fold tree for this
cell has not been generated" next to the Run button, and updates as the
dropdowns change.

This stays inside DD4: the template is committed, the browser sends a catalogue
id and choice-validated parameters, and the endpoint returns booleans. It does
not accept or return a path the browser supplied.

*Honest caveat:* it is a presence check, not a validity check. A tree generated
at the wrong fold count or from stale fragments passes it. It catches "I forgot
to generate the cell", which is the actual repeated mistake, and nothing else —
and it must not be described on the page as anything stronger than that.

*Effort:* one endpoint, one catalogue field with validation, page wiring, tests.
Medium. The largest item here.

### P6. Confirm before starting or stopping a long run

Using P3's `duration_hint`: a confirm dialog on Run for anything over (say) 30
minutes, naming the run and the resolved parameters, and a confirm on **Stop**
whenever a run is active. Stop is currently a single unguarded click that can
throw away three hours.

*Effort:* trivial, but it depends on P3's field to avoid nagging on the
ten-second runs.

### P7. Say whether Save will work, before it is clicked

A read-only extension of `/api/changes` (or a sibling endpoint) that runs the
same two guards `save_run_to_branch` already applies — nothing dirty outside
`reports/` and `models/`, and HEAD unmoved since the run's recorded commit — and
returns them as booleans. The page shows either "ready to save: 12 changed paths"
or the specific reason it will refuse. The logic exists in `gitops.py`; this
exposes it before the click rather than after.

Also worth showing the **current HEAD sha and branch** in the page header, since
"did I remember to Update from GitHub" is currently unanswerable from the page.

*Effort:* small, but it duplicates guard logic unless the guards in `gitops.py`
are factored into functions both paths call. Do it that way or not at all —
two copies of the guards drifting apart is worse than no preview.

### P8. A short run history

List the last ~20 runs from the manifests already sitting in
`dev_output/training_gui/`: id, entry name, parameters, status, duration; click
one to load its log read-only into the log panel. A new
`GET /api/runs` and `GET /api/runs/{run_id}/log`, both read-only, both taking a
run id the server itself listed (validated against the manifests on disk, not
treated as a path).

**This reverses an explicit exclusion** — the original provisional plan put "run
history" out of scope alongside queueing and dashboards. I think that exclusion
was right for the first build and is wrong now: the files exist, nothing new is
computed, and after a day of sweep cells "what did I run this morning and did it
pass" is a real question the page refuses to answer. But it is your call, and it
is the item most likely to grow if it is not held to exactly this shape.

*Effort:* two endpoints, a panel, path-safety tests. Medium.

### P9. Tidy the changed-files panel

Group by directory with counts, and auto-refresh while a run is going rather
than only at the end. Minor; the panel is not where the friction is.

### P10. Replace `alert()` with an inline error banner

Cosmetic. Worth doing while touching the page for something else, not worth a
task of its own.

---

## What this plan does not fix

**You still cannot watch a run from your phone.** The console binds `127.0.0.1`
and has no authentication, by design — that is what makes "no auth" acceptable.
The cost is that an hour-long run is invisible from anywhere but the machine it
is on, and P1's tab title does not change that. Making it reachable from the
LAN is a security decision (bind, auth, and the fact that the page can start
GPU jobs), not a usability tweak, and it should be its own discussion if you
want it. The current workaround — save the run to a branch and read the reports
on GitHub from anywhere — is the design's answer, and it only works once the run
has finished.

**The console still cannot tell you whether a run was worth having.** Nothing
above interprets a number, and P5's preflight is a presence check that will
happily wave through a stale tree.

---

## Suggested order

1. **P1 + P4 + P10** together: one page-only change, no endpoints, no catalogue
   changes, no new tests beyond the page. This is most of the day-to-day relief.
2. **P3 + P2 (localStorage only) + P6**: presentational catalogue fields and the
   layout. One task.
3. **P5**: the preflight endpoint. One task, the only one with real new
   server-side behaviour to test.
4. **P7, P8, P9, P2 (the cell control)**: individually, if still wanted after
   living with 1–3.

Stages 1 and 2 are where the value is concentrated. I would deliberately stop
after them and see what still annoys you before committing to 3 and 4.

---

## Open questions

1. **P8 (run history)** — accept the reversal of the original exclusion, or hold
   the line?
2. **P1 finish signal** — tab title only, or browser notifications too?
3. **P2 cell control** — is a cross-card "current cell" selector worth the
   complication, or is remembering each card's own dropdowns enough?
4. **P5 preflight** — worth an endpoint, given it only catches the forgotten
   generate step?
5. Is there friction you hit that is not on this list? The list is what I can
   see from the code and the docs; some of it is inference about how the page
   feels after the fiftieth run rather than observation.
