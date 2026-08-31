# Provisional plan: a local run console for encoder training

## Scope

A small local web application that lets a training run be started, watched, and
committed from a browser page instead of from a terminal. It exists to remove
the typing and the copy-paste round trips from a workflow that is about to be
repeated tens to low hundreds of times, not to add any capability the CLI does
not already have.

**In scope**

- Starting any of a named set of pre-configured runs with one click.
- Watching that run's output live, and seeing plainly whether it succeeded.
- Seeing which files under `reports/` and `models/` the run created or changed.
- Putting those files on a new GitHub branch with one click, and being handed
  the branch name and a link.

**Out of scope, deliberately**

- Editing training hyperparameters in the page. Runs are picked from a list, not
  composed. (See DD3 and the open questions.)
- Anything that interprets a result. `reports/encoder_training/README.md` is
  explicit that the tooling computes numbers and refuses to write the
  conclusion, and this console inherits that refusal — it shows that a run
  finished and where the JSON landed, and nothing about what the JSON says.
- Queueing, scheduling, run history, dashboards, charts.
- Merging, rebasing, conflict resolution, PR review. The console pushes a
  branch; everything after that stays in GitHub and in Claude.
- Any change whatsoever to `scripts/encoder_training/` or
  `scripts/synthetic_data/`. If the console needs a behaviour those packages do
  not have, that is a separate ticket.

**Key files (new):** `scripts/training_gui/`, `tools/train-gui.sh`,
`tools/train-gui.bat`, `tests/test_training_gui.py`

**Related:** `documentation/arch_encoder_training.md` (what the runs are),
`reports/encoder_training/README.md` (the canonical four-command run recipe and
the write-up obligations), `documentation/Quickstart.md` (the existing
terminal-based startup instructions this sits beside).

---

## The problem being solved

A training run today is a short fixed sequence of commands —

```
python -m scripts.encoder_training smoke-cuda
python -m scripts.encoder_training generate-folds --folds 5
python -m scripts.encoder_training finetune --folds 5
```

— followed by a git sequence to get the resulting reports onto a branch where
Claude can read them. Neither sequence involves any decisions. Both are
error-prone to type, and both currently cost a chat round trip to produce.
The user runs training on a Windows machine under WSL2/Ubuntu but frequently
reviews results from a phone or a work computer through the browser, which
makes "get the reports onto a branch on GitHub" the actual completion condition
of a run rather than "the files exist on disk".

The console is worth building because of volume. At five runs it would not be;
at a hundred it saves the terminal faff, and more importantly it removes the
class of mistake where a run is done correctly and then lost or mis-committed.

---

## Design Decisions

### DD1 A local web page, not a native desktop application

The console is a FastAPI app serving one HTML page, opened at
`http://127.0.0.1:8765`. It is not Tkinter, not Electron, not a packaged
executable.

Three reasons. FastAPI, uvicorn and pydantic are already pinned in
`requirements.txt`, so the console adds no new dependency and no new packaging
story. A browser page is far less code than a real GUI for the same result, and
the difference is maintenance the project would be carrying for years. And
under WSL2 a browser page is the *only* option that behaves well — a Linux GUI
toolkit inside WSL means WSLg and a class of display problems that have nothing
to do with training.

From the user's side it still behaves like a desktop program: a double-clickable
icon that opens a window. The distinction is internal.

### DD2 The console types commands; it never reimplements them

Every action shells out to the exact command documented in
`reports/encoder_training/README.md` or to a plain `git` invocation. The console
holds no knowledge of folds, arms, signals, margins or metrics, and imports
nothing from `scripts/encoder_training`.

This is the decision that keeps the console cheap. A console that understood
training would have to be updated whenever training changed, and would develop
its own opinions about what a run is; a console that only types stays correct as
long as the commands stay correct. It also means the CLI remains the real
interface — the console is a convenience over it, never a replacement, and
anything the console cannot do can still be done by hand.

Corollary: the page displays the literal command line before running it. Partly
so a failure can be reported precisely, partly so the commands are absorbed by
repetition rather than by study.

### DD3 Runs come from a checked-in catalogue file, not from hardcoded buttons

The available runs live in `scripts/training_gui/runs.json`: a list of entries,
each with an id, a human-readable name, a one-line description, and an ordered
list of argument vectors to execute.

This is the load-bearing decision for whether the console stays useful. The
eleven subcommands in `scripts/encoder_training/__main__.py` and the recent
history of one-off experiment shapes — `--companion-share`, `--base-models`,
the noise 2×2 sweep, `joint-compare` across three fold trees — say clearly that
the set of runs is not fixed and will keep growing. If the buttons were written
into the page, every new experiment would need a code change, which is a chat
plus a terminal plus a pull, which is the faff this exists to remove.

With a catalogue file, adding an experiment is adding four lines to one JSON
file. It is still a chat and still a `git pull`, and that should be stated
honestly rather than designed away: **roughly one in three new experiments will
need a new catalogue entry before it can be run from the console.** What the
catalogue buys is that the change is trivial and reviewable rather than a code
edit to a running application.

The page therefore also carries an "Update from GitHub" button that runs
`git pull` on the current branch and reloads the catalogue, so the pull is not
itself a reason to open a terminal.

### DD4 The browser can name a run; it cannot compose one

The HTTP endpoint that starts a run takes a catalogue **id**, never a command
string or a list of arguments. Commands are looked up in the catalogue and
executed with `subprocess` using an argument list — no shell, no interpolation
of anything the browser sent.

The console is, by its nature, a program that runs commands on the machine. That
is fine when the set of commands is fixed and checked into the repository, and
not fine if the page can post arbitrary text. Constraining it this way means the
worst case for a bug or a stray browser tab is "one of the runs already in the
catalogue was started", which is recoverable.

For the same reason the server binds `127.0.0.1` only and has no authentication.
It is not a service; it is a local tool with a browser for a front end. If WSL2's
localhost forwarding turns out not to reach a `127.0.0.1` bind from the Windows
browser, the fallback is binding the WSL interface — but that changes the
security posture and should be a conscious decision at implementation time, not
a default.

### DD5 One run at a time, logged to disk, survivable

A run takes about twenty minutes for a five-fold fine-tune and considerably
longer for the comparison sweeps. Three consequences:

- **Only one run executes at a time.** A second Run click while a run is active
  is refused with a message, not queued. Two `finetune` processes on one 12GB
  card would fail in a confusing way, and a queue is a feature nobody has asked
  for yet.
- **Output is written to a log file** under `dev_output/training_gui/` (already
  gitignored) as it arrives, and the page streams from that file. Closing the
  browser, sleeping the laptop, or reloading the tab does not lose the log and
  does not kill the run. Reopening the page reattaches to whatever is running.
- **Exit status is shown loudly and simply** — a green "finished" or a red
  "failed", with the last part of the output and the path to the full log.

### DD6 The git button does a narrow, fixed, non-destructive sequence

One button, "Save this run to a branch". It runs, in order:

1. `git fetch origin`
2. `git checkout -b <generated-branch-name> origin/main`
3. `git add` on `reports/` and `models/` only — never `-A`, never a path the
   user typed
4. `git commit` with a message naming the run and the date
5. `git push -u origin <branch>`

Then it displays the branch name in large text and a link to the GitHub compare
page for that branch, which is what gets pasted into a Claude session from the
phone.

What it deliberately does **not** do: merge, rebase, force-push, resolve a
conflict, amend, or continue past a failed step. Any git command that exits
non-zero stops the sequence and shows the raw error. Those are the situations
where a wrong automatic action is expensive and a human decision is cheap, and
the honest answer at that point is "bring this error to Claude".

Branching from `origin/main` rather than from the current branch is deliberate:
each run is an independent piece of evidence, and stacking runs on each other
makes them harder to review separately.

### DD7 No pull request creation in v1

Pushing a branch needs only the git credentials the machine already has.
Creating a pull request needs a GitHub token, a credential store, and an error
surface of its own. A pushed branch plus a compare link is enough to start a
Claude review from a phone, so the token work is deferred until it is shown to
be needed.

### DD8 The console lives under `scripts/`, and `app/` never learns of it

`scripts/training_gui/` sits alongside `scripts/encoder_training/` and
`scripts/synthetic_data/` as offline tooling. Nothing in `app/` imports it,
nothing in it is installed by the Dockerfile, and `tests/test_wiring.py`'s
existing one-way dependency assertion is extended to cover it.

It may import FastAPI, which is a production dependency, but that is the
direction that is already allowed — offline tooling may use production
libraries, production code may not use offline tooling.

### DD9 What the console does not remove

Stated here so the expectation is set before the work starts rather than after.

`reports/encoder_training/README.md` is explicit that a run worth keeping owes a
dated write-up discharging six obligations — the paired comparison read, the
per-fragment error table read before any conclusion, a verdict on each recorded
prediction, the conclusion in the ticket's terms, the limitations restated, and
the next ticket named. None of that is automatable and none of it is in scope.

The console saves roughly ten minutes of mechanical work per run and the
mistakes that come with it. It does not save the hour of thinking that makes the
run worth having. Over a hundred runs that is still a clearly worthwhile trade,
and it is a smaller claim than "this automates training".

The console also does not remove the terminal entirely: installing
`requirements-ml.txt` on a fresh machine, and anything that goes wrong at a
level below the console, still needs one.

---

## Shape of the thing

```
scripts/training_gui/
    runs.json          the catalogue (DD3)
    catalogue.py       load and validate runs.json
    runner.py          subprocess execution, log file, single-run lock (DD5)
    gitops.py          the fixed git sequence (DD6)
    server.py          FastAPI app, id-only endpoints (DD4)
    static/index.html  the single page
tools/
    train-gui.sh       activates the conda env, starts uvicorn, opens the browser
    train-gui.bat      Windows shortcut that calls train-gui.sh through wsl.exe
```

The Windows `.bat` is what makes this feel like a desktop program: it can be
pinned to the taskbar or put on the desktop, and double-clicking it starts the
console inside WSL2 and opens the browser on the Windows side. Without it the
user still needs one terminal command to launch, which would undercut most of
the point.

The page has four regions: the catalogue of runs with Run buttons; the live log;
the changed-files panel; the git panel with the branch button and the resulting
branch name and link.

---

## Testing approach

The catalogue loader, the git sequence assembly, and the runner's state machine
are stdlib-level logic and get ordinary unit tests in
`tests/test_training_gui.py` — including that a browser-supplied id which is not
in the catalogue is rejected, and that a failing step aborts the git sequence
rather than continuing.

Nothing tests that a real training run works; that is
`scripts/encoder_training`'s business and it is already covered. The console's
tests should not need a GPU, torch, or a network, and should run in CI's
existing unit job.

---

## Open questions for the review chat

1. **Which runs go in the initial catalogue?** The obvious ones are the four
   commands from the reports README, but the current experimental frontier is
   the noise and companion sweeps. Picking five or six entries that cover the
   next month's actual work is worth doing deliberately rather than defaulting
   to the documented examples.

2. **Should the catalogue allow a small number of typed parameters?** DD3 says
   runs are picked, not composed, which means a sweep over noise rates needs
   either one catalogue entry per rate or a code change. A single constrained
   exception — a numeric field or a dropdown declared *by the catalogue entry
   itself*, with allowed values listed — would cover most sweeps without opening
   the door DD4 closes. It is the largest genuine design question here and it
   should be settled before implementation, not bolted on.

3. **Does `git pull` in the "Update from GitHub" button need a dirty-tree
   guard?** Almost certainly yes — refuse to pull with uncommitted changes and
   say so — but the exact behaviour when reports exist but are uncommitted is
   worth deciding explicitly, since that is the normal state right after a run.

4. **Is `origin/main` always the right base for a run branch?** It is while runs
   are independent. If a sweep is ever a series of dependent runs it would be
   wrong, and it is worth knowing now whether that case is coming.

5. **Chunking of the implementation.** The natural split is four tasks —
   catalogue and runner, git operations, the FastAPI app and page, then the
   launchers and documentation — which is one chat each. Whether the git work is
   large enough to deserve its own task or belongs with the runner is a judgement
   for the implementation plan.
