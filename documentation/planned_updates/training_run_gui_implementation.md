# Implementation plan: a local run console for encoder training

Expands `training_run_gui_provisional.md` after review. The provisional plan's
scope and DD1–DD9 stand except where amended below; read it first for *why* the
console exists. This document is the buildable version: it corrects four claims
about the repository that the provisional plan got wrong, settles the five open
questions, and splits the work into four tasks of one chat each.

---

# Scope

**In scope**

- Starting any of a named set of pre-configured runs from a browser page, with a
  small number of catalogue-declared, enumerated parameters (AD3).
- Watching that run's output live, seeing which step of the run is executing, and
  seeing plainly whether it succeeded, failed or was stopped.
- Stopping a run.
- Seeing which files under `reports/` and `models/` the run created or changed.
- Putting those files — plus the run's own log and manifest — on a new GitHub
  branch with one click, and being handed the branch name and a compare link.
- `git pull --ff-only` from the page, guarded against a dirty tree.

**Out of scope, unchanged from the provisional plan**

- Interpreting a result. The console shows that a run finished and where the JSON
  landed, never what the JSON says.
- Queueing, scheduling, run history, dashboards, charts.
- Merging, rebasing, conflict resolution, PR creation (DD7).
- Any change to `scripts/encoder_training/` or `scripts/synthetic_data/`.
- Free-text or numeric parameters. See AD3.

**Key files (new)**

```
scripts/training_gui/__init__.py
scripts/training_gui/runs.json          the catalogue
scripts/training_gui/catalogue.py       load, validate, resolve parameters
scripts/training_gui/runner.py          subprocess execution, log, manifest, lock
scripts/training_gui/gitops.py          the fixed git sequences
scripts/training_gui/server.py          FastAPI app, id-only endpoints
scripts/training_gui/static/index.html  the single page
tools/train-gui.sh
tools/train-gui.bat
tests/test_training_gui.py
```

**Key files (modified)**

`requirements-ml.txt`, `documentation/architecture.md`,
`documentation/file_structure.md`, `documentation/arch_testing.md`,
`documentation/Quickstart.md`.

**Related reading**

`documentation/arch_encoder_training.md` section 10 (the run recipes),
`reports/encoder_training/README.md` (the committed-report contract and the
write-up obligations), `reports/encoder_training/2026-08-31-noise-2x2.md` (what a
real experiment's command matrix actually looks like).

---

# Corrections to the provisional plan

These are findings from the review; each one changes an instruction below.

**C1 — the one-way dependency guard is already in place, in another file.**
`test_app_never_imports_the_offline_tooling` lives in
`tests/test_encoder_training_dataset.py`, not `tests/test_wiring.py`, and it
rejects any import matching `scripts` or `scripts.*`. `scripts/training_gui/` is
covered the moment it exists. DD8 needs no new test. The stale pointer also
appears in `requirements-ml.txt`'s header comment and is corrected in Task 1.

**C2 — the console is a new dependency for the training environment.**
`requirements-ml.txt` and `arch_encoder_training.md` section 10 both state the
training environment needs `requirements-ml.txt` alone and that
`requirements.txt` is not required for a run. FastAPI and uvicorn are pinned for
`app/`, in a different environment. DD1's "adds no new dependency" is true of the
repository and false of the machine. Settled by AD1.

**C3 — the catalogue cannot say `python`.** Bare `python` is whatever the
launcher's PATH holds; a vector that names an interpreter can silently run
training against the wrong environment, which surfaces as a `SyntaxError` in
`recombine.py` or a missing-torch traceback rather than as a configuration
error. Settled by AD2.

**C4 — a run is usually much larger than the README recipe.**
`finetune --folds 5` trains one signal (`DEFAULT_SIGNAL = "fever_present"`). The
2026-08-31 noise sweep was thirteen fine-tune cells plus four baseline cells,
seventeen report directories, each with its own `--data-dir` / `--test-dir` /
`--report-dir`. Runs are therefore multi-step and multi-hour. Settled by AD4.

---

# Design Decisions

DD1–DD9 of the provisional plan carry over. The amendments and additions are
numbered AD (amended decision) to keep them distinct.

### AD1 The console runs in the training environment, and that environment gains FastAPI

The console must launch training subprocesses in the environment that has torch,
so the simplest correct arrangement is one environment for both: the ML
environment additionally holds `fastapi` and `uvicorn`.

`requirements-ml.txt` therefore gains a short, clearly fenced block pinning
`fastapi` and `uvicorn` at **exactly** the versions `requirements.txt` pins, with
a comment in each file pointing at the other. A unit test asserts the two files
agree on those pins, because a silent drift here is the kind of thing that is
discovered during a run rather than before one.

Rejected alternatives: a stdlib `http.server` console (removes the coupling, but
is materially more code for four endpoints and one page, and the project already
knows FastAPI); a third requirements file (a third file to keep in step, for two
pins).

The launcher preflights the import and, if FastAPI is missing, prints the exact
`pip install` line and exits. Failing fast with the remedy is the whole point.

### AD2 The catalogue holds module invocations, never interpreters

A catalogue vector is the argument list **after** the interpreter, and its first
element must be `-m`. The runner builds the real command as:

```
[sys.executable, "-u", *vector]
```

`sys.executable` is the interpreter the console itself is running under, which by
AD1 is the training environment. `-u` is not cosmetic: without unbuffered output
a twenty-minute step shows nothing in the log until it ends, which defeats the
live view.

The catalogue loader **rejects** any vector whose first element is not `-m`, which
mechanically excludes `python`, `python3`, an absolute interpreter path, `git`,
and everything else. Git commands are `gitops.py`'s business and are not in the
catalogue.

### AD3 Parameters are allowed, and are enumerated by the catalogue entry

Settles open question 2, in favour of allowing them.

The evidence is one-sided: eleven subcommands, a `--signal` default of
`fever_present` on nearly all of them, a thirteen-cell noise sweep in the last
month, `--companion-share`, `--base-models`, `--arm0-dir` / `--armp-dir`. Without
parameters the catalogue is either one entry per cell or a code change per
experiment, and a code change per experiment is the faff the console exists to
remove.

A catalogue entry may declare parameters. Each declaration carries a `name`, a
`label`, an explicit list of allowed `choices` (strings), and a `default` that
must be one of them. The page renders each as a dropdown. Vectors contain
`{name}` placeholders, substituted textually.

DD4's property is preserved exactly. The browser sends a catalogue id and, per
parameter, one string; the server accepts it only if it is an exact match for a
member of that entry's declared `choices`. Every value that can ever reach a
command line is therefore a string checked into the repository, so the worst case
for a bug or a stray tab remains "a command already in the catalogue ran".
Substitution inside a longer element (`data/synthetic/generated/{tree}`) is
allowed for the same reason — the substituted text is not user input in any
meaningful sense.

**No numeric fields and no free text.** A numeric field is free text plus a
validator, and the validator is where this decision would go wrong.

### AD4 A run is an ordered list of steps, aborts on the first failure, and can be stopped

Following C4:

- The page shows **step i of N** with the literal command line of the current
  step, not merely "running".
- A non-zero exit **aborts the remaining steps**. Continuing past a failed step
  produces a report tree that loads cleanly and means nothing, which is the exact
  failure mode `generate-folds` was scripted to avoid.
- There is a **Stop** button. A seventeen-cell sweep is hours long and the
  alternative to a Stop button is hunting a PID.
- Every step's argv, exit code, start and end time is recorded in the run
  manifest (AD5).

### AD5 A run writes a manifest, and the manifest and log are committed with the reports

The provisional plan puts logs in `dev_output/`, which is gitignored, and commits
only `reports/` and `models/`. The branch reviewed from a phone would then hold
the reports but not the commands that produced them, their exit codes, or the
commit the code was at.

The runner writes, beside the log in `dev_output/training_gui/`, a
`manifest.json` holding: run id, catalogue id and name, resolved parameter
values, each step's argv and exit code and timings, the overall status, and
`git rev-parse HEAD` captured **at run start**.

The git step copies both files to `reports/training_runs/<run_id>/` and commits
them alongside the reports. `reports/training_runs/` is a new directory
deliberately separate from `reports/encoder_training/`, whose README defines what
is committed there; console artefacts do not belong in that table.

This is metadata about an execution, not knowledge about training, so DD2 holds.

### AD6 A run branch is based on the commit the run was produced by

Settles open question 4, against `origin/main`.

A report is only interpretable next to the code that produced it, and new
experiments routinely exist on a branch before they are merged — the noise sweep
cites its own two commits as part of the record. So the branch is cut from the
sha the manifest recorded at run start, not from `origin/main`. When the machine
is on an up-to-date `main` the two are identical; when it is not, the difference
is between a readable branch and one whose reports were produced by code it does
not contain.

The commit message names that sha, the catalogue entry and the date. If the sha
is not on the remote the push fails, and that failure is shown raw and not worked
around — it is the correct answer, and it means "push your code branch first".

### AD7 The git sequence is guarded before it starts

DD6's sequence is otherwise unchanged (fetch, checkout -b, add the two path
prefixes, commit, push, stop on any non-zero exit, never merge/rebase/force/amend).
Two guards are added because `git checkout -b <new> <sha>` aborts with "local
changes would be overwritten" whenever the current branch differs from the base
in a file that is locally modified — which is the normal state after a run on a
feature branch:

1. Refuse if `git status --porcelain` reports anything outside `reports/` and
   `models/`, listing the offending paths.
2. Refuse if `HEAD` no longer matches the sha the manifest recorded, saying the
   repository moved since the run.

The "Update from GitHub" button (open question 3) uses `git fetch origin` then
`git pull --ff-only`, and refuses on **any** dirty tree — including a tree dirty
only with fresh reports, where the message is "save this run to a branch first"
and lists the paths. Being clever about pulling around uncommitted reports is how
a run gets lost.

### AD8 The console recovers its own state, and never adopts an orphan

State lives in a single file, `dev_output/training_gui/state.json`, holding the
active run id and the child PID. On startup, and on every status read, a state
claiming `running` whose PID is not alive is rewritten to `interrupted` — a
status the page shows as such, distinct from failed.

Killing the console kills the run (the child is started in its own process group
and stopped with it). Closing the *browser* does not, which is the property DD5
actually needs.

---

# Task 1: The catalogue and the runner

## A. State of the world

Nothing exists yet. This task builds the two modules that know how to turn a
catalogue id into a running subprocess, and the catalogue itself. No HTTP, no
git, no page — those are Tasks 2 and 3.

Read `training_run_gui_provisional.md` DD2–DD5 and AD1–AD5 above before starting.

## B. Files and deliverables

New:
- `scripts/training_gui/__init__.py` — empty package marker.
- `scripts/training_gui/runs.json` — the catalogue (five entries, below).
- `scripts/training_gui/catalogue.py` — load, validate, resolve.
- `scripts/training_gui/runner.py` — execution, log, manifest, lock, stop.
- `tests/test_training_gui.py` — unit tests for both, plus the pin-parity test.

Modified:
- `requirements-ml.txt` — the AD1 pins block; fix the stale
  `tests/test_wiring.py` pointer in its header to
  `tests/test_encoder_training_dataset.py` (C1).
- `requirements.txt` — one comment line beside the fastapi/uvicorn pins noting
  that `requirements-ml.txt` mirrors them and a test asserts it.

## C. Instructions

**`catalogue.py`**

- `load_catalogue(path) -> tuple[RunEntry, ...]`, raising `CatalogueError` with a
  message naming the offending entry on any violation. Validate:
  - ids unique, non-empty, `[a-z0-9-]+` only;
  - `name` and `description` non-empty strings;
  - `steps` a non-empty list of non-empty argv lists of strings;
  - **every step's first element is exactly `-m`** (AD2);
  - each declared parameter has `name` (identifier-ish), `label`, `choices` (a
    non-empty list of unique strings), and `default` ∈ `choices`;
  - every `{placeholder}` appearing in any step is a declared parameter, and
    every declared parameter appears in at least one step. Both directions —
    an undeclared placeholder is a crash at run time and an unused parameter is
    a dropdown that does nothing.
- `resolve(entry, values: Mapping[str, str]) -> tuple[list[str], ...]`:
  - every declared parameter is either present in `values` or takes its default;
  - a value not in that parameter's `choices` raises `CatalogueError`;
  - an unknown key in `values` raises `CatalogueError` (do not ignore it);
  - substitute `{name}` textually in every element, and return the argv lists.
- `command_line(argv) -> str` for display: the literal line the user would type,
  prefixed with `python -u`. Display only; never parsed back.

**`runner.py`**

- Paths: `dev_output/training_gui/` created on demand;
  `<run_id>.log`, `<run_id>.manifest.json`, `state.json`. `run_id` is
  `<YYYYMMDD-HHMMSS>-<entry id>`.
- `start(entry, values) -> RunHandle`: refuses with `RunnerBusy` if a run is
  active (AD8's liveness check first, so a stale state file does not wedge the
  console). Captures `git rev-parse HEAD` before the first step.
- Execution: for each resolved step, `subprocess.Popen([sys.executable, "-u",
  *argv], cwd=<repo root>, stdout=PIPE, stderr=STDOUT, start_new_session=True)`.
  Stream bytes to the log file as they arrive, flushing so a reader sees them.
  Write a banner line before each step containing the command line. On a non-zero
  exit, record it and stop; do not run later steps.
- `stop()`: `os.killpg` with SIGTERM, then SIGKILL after a short grace; final
  status `stopped`.
- Status values: `idle`, `running`, `succeeded`, `failed`, `stopped`,
  `interrupted`. Manifest is rewritten on every step boundary and at the end, so
  a crash leaves a truthful record.
- `read_log(offset) -> (text, next_offset)` — byte offset in, byte offset out.
  The page polls this (Task 3), so it must be cheap and must not hold the file.
- `changed_paths()` — `git status --porcelain -- reports models`, parsed into
  path plus status letter, untracked included.

**`runs.json` — the five initial entries** (open question 1):

1. `smoke-cuda` — `["-m", "scripts.encoder_training", "smoke-cuda"]`. One step,
   ten seconds, and the thing that must never be skipped on this machine.
2. `generate-folds` — `["-m", "scripts.encoder_training", "generate-folds",
   "--folds", "5", "--signal", "{signal}"]`, with `signal` declared over the six
   trained signals.
3. `merge-folds` — `["-m", "scripts.encoder_training", "merge-folds", "--folds",
   "5"]`.
4. `finetune` — Arm B for one signal: `["-m", "scripts.encoder_training",
   "finetune", "--folds", "5", "--signal", "{signal}", "--base-model",
   "{base_model}"]`, `base_model` declared over `roberta-base` (default),
   `emilyalsentzer/Bio_ClinicalBERT`, `bert-base-uncased`.
5. `score-companions` — `["-m", "scripts.encoder_training",
   "score-companions"]`. Stdlib, no GPU, and the cheapest possible end-to-end
   check that the console can run something real.

`--base-model roberta-base` is spelled out in entry 4 on purpose:
`DEFAULT_BASE_MODEL` is Bio_ClinicalBERT, and `arch_encoder_training.md` section
10 records that omitting the flag produces a run that succeeds, reports nothing
unusual, and yields numbers that cannot be read beside any committed report.
Baking it into the catalogue is one of the clearer things the console buys.

**Tests** (`tests/test_training_gui.py`, no integration marker):

- the committed `runs.json` loads and validates;
- each rejection path above, one test each, asserting on the message;
- `resolve` substitutes correctly, applies defaults, rejects a value outside
  `choices`, and rejects an unknown key;
- a vector whose first element is `python` is rejected (AD2);
- the runner runs a two-step fake entry built in the test — `["-m", "json.tool",
  ...]` or `["-c", ...]`-free equivalents that are stdlib, instant, and need no
  GPU or network — and reaches `succeeded`, with both steps in the manifest;
- a failing first step leaves the second **unrun** and status `failed`;
- a second `start()` while running raises `RunnerBusy`;
- a `state.json` naming a dead PID is reported `interrupted`, not `running`;
- `requirements.txt` and `requirements-ml.txt` pin identical fastapi and uvicorn
  versions (AD1).

Then: typecheck/lint the touched files and run this one test file. Do not run the
full suite or `npm run build`.

---

# Task 2: Git operations

## A. State of the world

Task 1 is complete: `catalogue.py` and `runner.py` exist, a run produces a log
and a manifest under `dev_output/training_gui/`, and `runner.changed_paths()`
reports what moved under `reports/` and `models/`. Nothing yet puts any of it on
GitHub. No HTTP layer exists yet.

Read AD5, AD6 and AD7 above, and DD6 in the provisional plan, before starting.

## B. Files and deliverables

New:
- `scripts/training_gui/gitops.py`.

Modified:
- `tests/test_training_gui.py` — a git section.

## C. Instructions

`gitops.py` runs `git` through `subprocess.run` with an argv list, `cwd` at the
repo root, capturing stdout and stderr. Every function returns a structured
result — the ordered list of steps attempted, each with its argv, exit code and
captured output — so the page can show exactly where a sequence stopped.

**`save_run_to_branch(manifest) -> GitResult`**

Guards first, before any mutating command (AD7):

1. `git status --porcelain` — refuse if anything is dirty outside `reports/` and
   `models/`, naming the paths.
2. `git rev-parse HEAD` — refuse if it differs from the manifest's recorded sha,
   saying the repository moved since the run.

Then, stopping on the first non-zero exit:

1. `git fetch origin`
2. `git checkout -b <branch> <manifest sha>` — branch name
   `training/<YYYY-MM-DD>-<run id>`, which is unique by construction because the
   run id carries a timestamp.
3. Copy `<run_id>.log` and `<run_id>.manifest.json` into
   `reports/training_runs/<run_id>/` (AD5).
4. `git add -- reports models` — the two literal prefixes, never `-A`, never a
   path from the browser.
5. `git commit -m <message>` — subject `training run: <entry name> (<date>)`;
   body lists the base sha, the resolved parameter values, and each step's
   command line with its exit code. If `git commit` reports nothing to commit,
   surface that as a plain "this run changed nothing" rather than as an error.
6. `git push -u origin <branch>`

On success return the branch name and a compare URL.

**`compare_url(remote_url, branch)`** — derive
`https://github.com/<owner>/<repo>/compare/<branch>?expand=1` from
`git remote get-url origin`, handling both `git@github.com:owner/repo.git` and
`https://github.com/owner/repo(.git)`. Return `None` for anything else rather
than guessing; the page then shows the branch name alone.

**`update_from_github() -> GitResult`** — `git status --porcelain`; refuse on any
dirty tree, with the "save this run to a branch first" message when the dirt is
confined to `reports/` and `models/`. Then `git fetch origin` and
`git pull --ff-only`.

**Tests** — no network and no real repository mutation. Inject the command runner
(a callable taking argv and returning exit code plus output) so the tests assert
on **assembled argv and sequencing**:

- the happy path issues exactly the six commands, in order, with the manifest's
  sha as the checkout base (AD6);
- a non-zero `git fetch` stops the sequence: no `checkout`, no `commit`, no
  `push` is attempted, and the raw error is in the result;
- the same for a failed `push`, which must be the last thing attempted;
- a dirty path outside `reports/` blocks the whole sequence, with the path in the
  message;
- a `HEAD` that no longer matches the manifest blocks it;
- `update_from_github` refuses a reports-only dirty tree with the branch-button
  message, and uses `--ff-only` when it proceeds;
- `compare_url` for both remote forms and `None` for a third;
- `git add` is called with `--  reports models` and never with `-A`. This one is
  worth an explicit test because it is the assertion that keeps a stray file out
  of a run branch.

Then: lint the touched files and run this one test file.

---

# Task 3: The FastAPI app and the page

## A. State of the world

Tasks 1 and 2 are complete: the catalogue loads and validates, the runner
executes a multi-step run to a log and a manifest and can be stopped, and
`gitops.py` performs the guarded branch sequence and the guarded pull. Nothing
serves any of it. This task adds the HTTP layer and the single page; it adds no
new behaviour beyond wiring, and no new knowledge of training.

Read DD4, AD3 and AD8 before starting.

## B. Files and deliverables

New:
- `scripts/training_gui/server.py`
- `scripts/training_gui/static/index.html`

Modified:
- `tests/test_training_gui.py` — an HTTP section using `fastapi.testclient`
  (`httpx` is installed in CI's unit job).

## C. Instructions

**`server.py`** — `create_app(runner, catalogue, gitops) -> FastAPI`, with the
collaborators injected so the tests can drive fakes. A module-level `app` built
from the real ones for uvicorn. Endpoints, all JSON except the first:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/` | the static page |
| GET | `/api/catalogue` | entries: id, name, description, parameter declarations, and the rendered command lines at current defaults |
| POST | `/api/run` | body `{"id": str, "parameters": {str: str}}`. 404 unknown id, 400 bad parameter, **409 if a run is active**, 202 on start |
| GET | `/api/status` | status, run id, entry name, step index and count, current command line, per-step exit codes |
| GET | `/api/log?offset=N` | `{"text": ..., "next_offset": ...}` |
| POST | `/api/stop` | stops the active run; 409 if none |
| GET | `/api/changes` | `runner.changed_paths()` |
| POST | `/api/save-branch` | `gitops.save_run_to_branch`; returns branch, compare URL, and the step-by-step result |
| POST | `/api/update` | `gitops.update_from_github` |

No endpoint accepts a command, an argument, a path or a branch name from the
browser (DD4). Bind `127.0.0.1` only, no authentication. If WSL2's localhost
forwarding turns out not to reach the bind from the Windows browser, binding the
WSL interface is a **conscious follow-up decision**, not a default to add
pre-emptively.

**`static/index.html`** — one file, plain HTML/CSS/JS, no build step and no
framework. Four regions:

1. **Runs** — one row per catalogue entry: name, description, a dropdown per
   declared parameter, the literal command line(s) that will run (updating as the
   dropdowns change), and a Run button. Run buttons disable while a run is active.
2. **Live log** — polls `/api/log?offset=` every second, appends, and follows the
   tail unless the user has scrolled up. Above it: the status line — the step
   number and total, the current command, and a large, unmissable result when the
   run ends. Green for succeeded, red for failed, neutral for stopped and
   interrupted. Beside it, a Stop button while running.
3. **Changed files** — the `reports/`/`models/` list, refreshed after a run ends
   and on demand.
4. **Git** — "Save this run to a branch" and "Update from GitHub". On success the
   branch name in large text plus the compare link. On failure the raw output of
   the step that failed, with no interpretation and no offer to retry
   differently — the honest response at that point is to bring the error to a
   chat.

Reloading the page must reattach to a running run: all state comes from
`/api/status` and `/api/log`, and the page holds nothing across a reload but the
log offset it re-derives from zero.

**Tests** — `TestClient` against fake collaborators, no subprocesses:

- `GET /api/catalogue` returns every committed entry with its parameters;
- `POST /api/run` with an unknown id → 404, and the fake runner was never called;
- with a parameter value outside `choices` → 400, runner never called;
- with a valid body → 202, and the runner received the **resolved argv**;
- `POST /api/run` while the fake reports a run active → 409;
- `GET /api/log?offset=` passes the offset through and returns the next offset;
- `POST /api/stop` with nothing running → 409;
- `POST /api/save-branch` surfaces a failed step's raw output and does not
  invent a success.

The id-rejection tests matter at this layer specifically, not only in
`catalogue.py`: DD4's guarantee is a property of the HTTP boundary.

Then: lint the touched files and run this one test file.

---

# Task 4: Launchers and documentation

## A. State of the world

Tasks 1–3 are complete: `python -m uvicorn scripts.training_gui.server:app
--host 127.0.0.1 --port 8765` serves a working console, and
`tests/test_training_gui.py` covers the catalogue, the runner, the git sequences
and the HTTP boundary. What is missing is the double-clickable launch that makes
this feel like a desktop program rather than one more thing to type, and the
documentation obligations this repository carries for a new subsystem.

## B. Files and deliverables

New:
- `tools/train-gui.sh`
- `tools/train-gui.bat`

Modified:
- `documentation/architecture.md` — a new capability entry in section 3.
- `documentation/file_structure.md` — the `scripts/` entry (currently lines
  28–30) and a `tools/` entry.
- `documentation/arch_testing.md` — `tests/test_training_gui.py` recorded as a
  unit test file (the CLAUDE.md test-maintenance obligation).
- `documentation/Quickstart.md` — how to start the console.

## C. Instructions

**`tools/train-gui.sh`** — `set -euo pipefail`; `cd` to the repository root
derived from the script's own path, not from the caller's working directory;
activate the training conda environment; **preflight** `python -c "import
fastapi, uvicorn"` and, on failure, print the exact `pip install -r
requirements-ml.txt` line and exit non-zero (AD1); start uvicorn on
`127.0.0.1:8765`; open the browser. Under WSL2 the browser is the Windows one, so
prefer `wslview`/`explorer.exe` and fall back to printing the URL rather than
failing. Refuse to start if the port is already bound, and say that the console
is probably already running.

**`tools/train-gui.bat`** — a one-liner calling `wsl.exe -- <path>/train-gui.sh`,
pinnable to the taskbar. This is what makes the whole thing feel like a program;
without it the user still opens a terminal, which undercuts most of the point.

**Documentation.** The architecture entry should be short and should route rather
than duplicate: scope (a local console that types the documented commands),
the key files, and the two invariants that matter to anyone reading it later —
the console never imports `scripts/encoder_training`, and the browser can name a
run but never compose one. Say plainly, in the entry or in the Quickstart, what
DD9 already says: the console saves the mechanical minutes and the mis-commits;
it does not touch the write-up obligations in
`reports/encoder_training/README.md`, and it does not make a run worth having.

Then: lint, and run `tests/test_training_gui.py` once more as the final check.
Leave the full suite to CI.

---

# What is deliberately not decided here

- **Binding the WSL interface instead of `127.0.0.1`.** Only if the loopback bind
  turns out to be unreachable from the Windows browser, and then as its own
  decision with its own note about the security posture (DD4).
- **Pull request creation.** Deferred until a pushed branch plus a compare link
  is shown to be insufficient (DD7).
- **A queue, or more than one run at a time.** Two `finetune` processes on one
  12GB card fail confusingly, and nobody has asked for a queue (DD5).
- **Detecting a training run started from a terminal.** The console's single-run
  lock covers only runs the console started; a run launched by hand can still
  contend for the GPU. Accepted, and worth one line on the page rather than
  machinery.
