# Econsult Quick Start

## Prerequisites
- Backend dependencies installed in the `econsult` conda environment
- Node dependencies installed (`frontend/node_modules` exists)
- `.env` file exists in project root (see reference below)

## Start the backend

From project root, in terminal 1:

```bash
export $(cat .env | xargs) && uvicorn main:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Note: `main.py` is now at the project root. There is no `PYTHONPATH` override needed.

## Start the frontend

From project root, in terminal 2:

```bash
cd frontend && npm run dev
```

Expected output:
```
VITE v7.3.1  ready in ~124ms
➜  Local: http://localhost:5173/
```

## Open in browser

| Interface | URL |
|-----------|-----|
| Patient form | http://localhost:5173/ |
| Practice admin | http://localhost:5173/admin-ui/ |

The Vite dev server proxies `/admin` requests to port 8000 automatically.

Admin token: any non-empty bearer token in DEV_MODE (ADMIN_TOKEN not set)

## Start the training run console (offline tooling)

Nothing to do with the app above. This is the local console for the encoder
training runs documented in `arch_encoder_training.md` section 10, and it runs in
the ML environment (`requirements-ml.txt`), not the `econsult` one.

From Windows: double-click (or pin to the taskbar) `tools\train-gui.bat`.

From a WSL/Linux shell:

```bash
tools/train-gui.sh
```

Either way the script finds the repository root from its own path, activates the
training conda environment, checks FastAPI is importable, serves the console on
http://127.0.0.1:8765/ and opens a browser at it.

| What it says | What to do |
|---|---|
| `fastapi and uvicorn are not importable in this environment` | `pip install -r requirements-ml.txt` in the training environment |
| `could not activate the 'econsult-ml' conda environment` | Warning only. If yours is named differently, `export TRAIN_GUI_CONDA_ENV=<name>` (or start the script from that environment) |
| `127.0.0.1:8765 is already in use` | A console is probably already running — open the URL, or stop the other one |
| `could not open a browser` | Go to the printed URL yourself |

Closing the terminal (or the window `train-gui.bat` opened) stops the console
**and** any run it started. Closing the browser tab does not.

The two entries at the top of the page are the whole declarative sweep in one
button each: they run the CUDA smoke test, generate every cell the comparison
needs, train the comparison and score its companion thresholds, in sequence.
Each begins with a ten-second CUDA smoke test and then a three-minute training
canary — one signal, one fold, on a one-fold tree of its own — so a machine that
cannot actually run a backward pass fails about three minutes in rather than
after the twenty-five minutes of generation that would otherwise come first. The
same canary is a button of its own (**Training canary**), which is what to press
after a driver or wheel change.

They take no parameters, and they regenerate their cells every time even when
those cells are already on disk — about 25 minutes on a run of three to four
hours, in exchange for an entry with no hidden prerequisite. Everything below
them is an escape hatch for repeating one of those steps on its own: if a
comparison fails after the cells are written, the bare `compare` entry re-runs
just the training.

On the page: pick a run's parameters from its dropdowns, press **Run**, and watch
the log. A checklist shows every step by name with its own status and duration —
succeeded steps collapse behind one summary row, and the running step, any failed
step and the next few to come are always in view — beside the total elapsed time
and the literal command line running now. The tab title and its dot carry the same
state, so a sweep can be left in a background tab. **Copy log** and **Copy the
failing step's output** put either on the clipboard for a chat; **Expand** gives
the log the height of the window. **Stop** asks for confirmation, naming the run
and how long it has been going, because it is the one button that throws away
hours. A failed step aborts the rest of the run. When it finishes, "Save this run to
a branch" commits what it wrote under `reports/` and `models/`, plus that run's log
and manifest, to a new branch cut from the commit the run was produced by, and
hands you the branch name and a compare link. **Update from GitHub** does a
`git fetch` and a `git pull --ff-only`, and refuses on any dirty tree — including
one dirty only with a run's fresh reports, which is a prompt to save that run to a
branch first.

What the console does **not** do: it never interprets a result — the sweeps end
with a scoring step, but that is the training CLI scoring its own criterion as a
subprocess, and the console does nothing with the output but show it. It does not
touch the write-up obligations in `reports/encoder_training/README.md`. It saves
the mechanical minutes per run and the mis-commits that come with them; it does
not make a run worth having.

## .env reference

```
DEV_MODE=1
PRACTICE_ID=summertown_health_centre
DATABASE_URL=postgresql://user:password@host/dbname
DATA_DIR=data
```

`PRACTICE_NAME` and `PRACTICE_EMAIL` are optional. If the practice record does not
exist in the database, it will be seeded automatically from these values on first
startup. If they are not set, the practice ID is used as the name and
`demo@demo.net` is used as the email.

## Useful checks

Verify backend is up:
```bash
curl http://localhost:8000/healthz
```

Verify a submission was recorded (requires psql or a Postgres client):
```bash
psql $DATABASE_URL -c "SELECT submission_id, delivery_status FROM submission_records ORDER BY submitted_at DESC LIMIT 5"
```