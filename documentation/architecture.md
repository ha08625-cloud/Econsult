

---

## 10. Visibility Semantics

* All questions are shown after free text and encoder run
* No questions are suppressed or hidden

However:
* Visibility rules are still part of the engine design
* Future versions may activate them without refactor
* Explicit answers persist even if visibility changes later.


## Section 12 — Practice Configuration Architecture

### 12.1 Design principles

* Composition, not merging — Practice-specific content occupies a distinct slot,
  never overwrites or merges with clinical content
* Clinical engine untouched — All practice configuration is handled in the
  presentation layer; form_logic, safety_engine, encoder_mapping etc. remain
  unaware of practice identity
* Condition registry remains immutable — Practice-specific data is fetched at
  request time from the database, not baked into startup state
* Graceful degradation — Missing signposting means "show nothing", not "crash"
* Narrow scope — Practices can only configure signposting, not safety warnings,
  labels, or clinical content

### 12.3 Data flow

The universal safety warning is fetched separately from condition presentation,
before condition selection, so it can be shown on the first screen the patient
sees. The two fetches serve different purposes and are deliberately kept apart.

**Pre-session safety gate (Screen 0):**
1. Patient accesses the form via the practice's website
2. GET /safety-warning called — returns the universal safety warning constant
3. Frontend renders the warning and requires checkbox confirmation before proceeding
4. Patient cannot continue until they confirm the warning does not apply to them

**Condition presentation (Screen 2):**
1. Patient selects a condition on Screen 1
2. GET /conditions/{id}/presentation called
3. presentation_service composes response:
   a. Fetches condition presentation from registry (immutable, in-memory)
   b. Fetches practice signposting from database using practice_id from app.state
   c. Returns composed dict (universal_safety_warning field still present for
      API backwards compatibility but is not displayed by the frontend here)
4. Frontend renders condition label, free_text_prompt, and practice_signposting

### 12.3 Data flow

1. Patient accesses the form via the practice's website
2. GET /conditions/{id}/presentation called
3. presentation_service composes response:
   a. Fetches condition presentation from registry (immutable, in-memory)
   b. Fetches practice signposting from database using practice_id from app.state
   c. Adds universal safety warning constant
   d. Returns composed dict
4. Frontend renders all three information types in distinct UI sections

## Section 13 — Frontend Error Handling

### 13.1 Design principles

* Patient input is never destroyed by a recoverable error
* Error classification happens at the API boundary, not in component logic
* Only genuinely unrecoverable situations escalate to a fatal screen
* Error messages are written for patients, not developers

### 13.2 Error classification

Two error states exist in the frontend:

**fatalError** — replaces the current screen entirely. Reserved for:
- Condition list fails to load on first visit (the form cannot be shown at all without this)
- Invalid internal state (e.g. EDIT screen reached without a runtime_id — should never occur in normal use)

**screenError** — displays an inline message on the current screen without disturbing any state. Used for all recoverable failures: network errors, 5xx responses, and 4xx responses on form submission endpoints. The patient can read the message and try again with their answers intact.

`screenError` is cleared automatically on every screen transition and cleared immediately when the patient begins editing after a failure.

### 13.3 ApiError class (api.ts)

All fetch calls are wrapped to throw `ApiError` rather than a plain `Error`. `ApiError` carries:
- `message` — the HTTP status string or "Network failure"
- `status: number | null` — the HTTP status code, or null for network-level failures where no response was received

This allows `friendlyErrorMessage(e)` to branch on status code and produce specific patient-facing text.

### 13.4 Error messages by status

| Condition | Message shown to patient |
|---|---|
| 409 | "Please check you do not have this form open in another tab. If you do, close the other tab and try again." |
| 5xx | "The server encountered a problem. Please try again in a moment." |
| Network failure (status null) | "Could not reach the server. Please check your internet connection and try again." |
| Any other error | "Something went wrong. Please try again." |

A 409 on a form endpoint means a session version conflict. The most likely cause in a single-patient deployment is the form being open in multiple tabs simultaneously.

### 13.5 What is and is not recoverable

| Screen | Failure point | Recovery |
|---|---|---|
| Screen 0 — loading safety warning | Fetch fails | Inline error with Try again button; no state to lose |
| Screen 1 — loading conditions | Fetch fails | Fatal — form cannot be shown without condition list |
| Screen 2 — loading presentation | Fetch fails | Inline error with Back and Try again buttons; condition selection preserved |
| Screen 2 — submitting free text | initForm fails | Inline error; free text preserved in state |
| Screen 3 — submitting answers | updateForm fails | Inline error; all answers preserved in editableAnswers |
| Screen 4 — final submit | finishForm fails | Inline error; review screen intact, patient can retry |

## Section 14 — Safety Gate

### 14.1 Purpose

Existing online consultation systems display a universal safety warning on
the first page the patient sees, before they have selected a condition or
begun filling in any form. This is the established NHS pattern and exists
for a clear reason: a patient experiencing a medical emergency should be
redirected to 999 or A&E before they have invested time filling in a form.

Displaying the warning after condition selection, as this system originally
did, is the wrong order. The patient has already spent time on the form.
Moving it to the first screen ensures no patient in an emergency proceeds
further than the first page.

### 14.2 Implementation

**New endpoint:** `GET /safety-warning`
- No authentication required
- No condition ID required
- No session required
- Returns `{"universal_safety_warning": "..."}` from the
  `UNIVERSAL_SAFETY_WARNING` constant in `presentation_service.py`
- The constant remains in exactly one place; this endpoint exposes it
  without duplicating it

**Frontend gate (Screen 0 — SAFETY_WARNING):**
- Warning text is fetched on mount via `getSafetyWarning()`
- A checkbox labelled "I confirm that none of the above apply to me" must
  be ticked before the Continue button is enabled
- While the checkbox is unticked, a red hint message reads:
  "If any of the above apply to you, please call 999 or go to A&E
  immediately. Do not use this form."
- Fetch failures show an inline error with a Try again button; no state
  is lost because no session exists yet at this point

### 14.3 Safety principle

The Continue button being disabled — rather than showing a warning and
allowing the patient to proceed anyway — is deliberate. A patient having
a heart attack should have no path to submitting an online form. The gate
is a hard block, not an advisory.

The checkbox confirmation creates a moment of active acknowledgement. The
patient must read the warning and make a positive declaration before the
form is accessible. This matches the pattern used by established NHS online
consultation platforms.

### 14.4 What did not change

- `UNIVERSAL_SAFETY_WARNING` constant location: still in `presentation_service.py`
- `GET /conditions/{id}/presentation` still returns `universal_safety_warning`
  in its response for API backwards compatibility, but the frontend no longer
  displays it there
- No changes to any clinical engine module
- No database changes

## Section 15 — Deployment

### 15.1 Platform

The application is deployed on Railway (railway.app). Railway provides a
single-server cloud environment that clones the GitHub repository, runs the
build script, and starts the server process. Deployments are triggered
automatically on every push to the main branch.

The original Nixpacks builder was replaced with a Dockerfile in March 2026
after Railway migrated to Railpack (their Nixpacks successor). Railpack
failed to generate a build plan for this project's mixed Python/Node
structure without a clear error message. A Dockerfile was the recommended
solution and gives complete control over the build environment.

railway.toml now contains only `builder = "DOCKERFILE"`. The Nixpacks
phase configuration it previously contained is no longer valid and has
been removed.

### 15.2 Build process

Stage 1 (frontend-build): Node 22 image. Installs npm dependencies from
frontend/package.json and runs npm run build, producing frontend/dist/.

Stage 2 (runtime): Python 3.12-slim image. Installs Python dependencies
from requirements.txt, copies app/, data/, and the built frontend/dist/
from stage 1. Starts uvicorn via the Dockerfile CMD.

The Vite build produces two entry points:
- dist/index.html — patient-facing form
- dist/admin-ui/index.html — admin portal

Both are served by the existing StaticFiles mount at / in main.py.
The previous admin/ directory (CDN-based standalone page) has been deleted.

### 15.3 Static file serving

In production, FastAPI serves the built frontend directly. On startup,
`main.py` checks whether `frontend/dist/assets` exists on disk. If it does,
it mounts the assets directory and registers a catch-all route that returns
`index.html` for all unmatched paths. This allows the React app to handle
its own client-side routing.

This check is filesystem-based, not DEV_MODE-based. In local development,
`frontend/dist` does not exist (the developer runs Vite separately), so
static file serving is automatically skipped. No code change is required
when switching between local and production environments.

The admin portal (backend/admin/index.html) is a standalone CDN-based page served 
by FastAPI's StaticFiles at /admin-portal. It is not part of the Vite build pipeline 
and must not be placed inside the frontend/ directory, which Vite processes on build.

The admin portal (admin-ui) is built by Vite as a second entry point and
output to dist/admin-ui/. It is served at /admin-ui/ by the same
StaticFiles mount as the patient form. The previous standalone
admin/index.html served at /admin-portal has been removed.

### 15.4 Database

The database is Postgres, managed by Railway as an add-on service.
The connection string is injected into the application as `DATABASE_URL`.
The previous SQLite approach (`runtime.db`, `DB_PATH`) has been removed.

All four repositories (RuntimeStateRepository, PracticeRepository, SubmissionRepository, AvailabilityRepository) accept database_url: str in their constructors.

#### Schema migrations (Alembic)

Schema migrations are managed by Alembic. `alembic_upgrade()` in
`app/core/db.py` runs `alembic upgrade head` at application startup,
applying any pending migrations before the application serves requests.
If a migration fails, the application fails to start. This is correct
behaviour — a failed migration must prevent startup.

Configuration:
- `alembic.ini` at the project root contains no secrets. The database URL
  is injected at runtime by `alembic/env.py` reading `DATABASE_URL` from
  the environment.
- `alembic/env.py` sets `target_metadata = None` (no SQLAlchemy ORM models).
  The advisory lock is enabled by default and must not be disabled.
- Migration files live in `alembic/versions/`. Each file contains
  `upgrade()` and `downgrade()` functions.

Migration workflow:
1. Write a new migration file in `alembic/versions/`.
2. Run `alembic upgrade head` locally against a test database to verify.
3. Push to main. Railway deployment runs migrations automatically at startup.

Rollback procedure:
To roll back a migration in production, run `alembic downgrade -1` (or to
a specific revision) manually against the live database, then redeploy the
older code version. There is no automated rollback mechanism. The
`downgrade()` functions in each migration file exist for this purpose.

Concurrent startup limitation:
Running migrations at application startup works for a single-developer,
single-instance deployment. If two Railway instances start simultaneously
(e.g. during a deployment overlap), concurrent migration attempts could
conflict. Alembic's default advisory lock mitigates this, but the behaviour
under contention is not well-documented for all Postgres configurations.
This is acceptable for now and must be revisited before scaling.

The initial migration (`0001_initial_schema.py`) uses `CREATE TABLE IF NOT
EXISTS` as a one-time concession because the database predates Alembic.
Future migrations must not use `IF NOT EXISTS`.

The previous `init_database()` function has been replaced by
`alembic_upgrade()`. `init_database()` is retained as deprecated in
`app/core/db.py` until `alembic_upgrade()` is confirmed working on Railway,
then it will be deleted.

JSONB columns: `state_json` (runtime_state_versions),
`clinical_output_json`, and `audit_output_json` (submission_records)
are stored as JSONB. psycopg2 does not automatically adapt plain Python
dicts to JSONB — all write paths wrap dicts in `psycopg2.extras.Json()`
explicitly. Read paths receive Python dicts directly from psycopg2 — no
`json.loads()` call is needed or correct.

### 15.4.1 signposting_json column format

The signposting_json column in practice_signposting stores a plain HTML
string. The column name is a legacy misnomer from the original
list-of-strings design. Do not assume the column contains JSON.

nh3 API constraint: the rel attribute on <a> tags is reserved by nh3
and injected automatically (default: 'noopener noreferrer'). Do not pass
rel through the attributes dict — nh3 will panic at runtime. The correct
call is:

    nh3.clean(
        raw,
        tags={...},
        attributes={"a": {"href", "target"}},
        url_schemes={"http", "https"},
    )

DOMPurify allowlist: SIGNPOSTING_PURIFY_CONFIG is defined once in
frontend/src/constants.ts and imported by both App.tsx and the admin
portal (admin-ui/src/SignpostingEditor.tsx). It must match the nh3
allowlist in practice_repository.py exactly. If the allowlist changes,
update both constants.ts and practice_repository.py.

### 15.4.2 Test database

Known gap: the repository integration tests (`tests/test_repositories.py`)
run against the same Railway Postgres instance as the deployed application.
There is no dedicated test database. Each test generates unique IDs and
cleans up rows in a finally block, but a buggy test could corrupt or delete
live data.

This is acceptable for a single-developer project at this stage. A
dedicated test database must be provisioned before a second developer joins
or before any real patient data is stored.

To run the tests locally, set `TEST_DATABASE_URL` in your `.env` file to
the `DATABASE_PUBLIC_URL` value from the Railway Postgres service dashboard
(the external-facing URL, not the internal `DATABASE_URL`). This file must
not be committed to version control.

    python -m tests.test_repositories

Migration 0002 (0002_availability_table.py):
Creates the practice_availability table with columns: practice_id (PK,
references practices), is_active (boolean, default false),
weekly_open_days (TEXT[], default '{}'), open_time (TIME, default '08:00'),
close_time (TIME, default '18:30'), closed_message (TEXT, nullable).
Includes a CHECK constraint on weekly_open_days using the Postgres <@
(contained by) operator to assert that every element is one of the seven
valid day abbreviations. This makes the database self-defending against
invalid values regardless of how the data is written. Application-layer
validation in availability_service.py still runs first and produces a
better error message for the caller; the constraint is the backstop.

### 15.5 Environment variables

The following environment variables must be set in the Railway dashboard:

| Variable        | Purpose                                                                  |
|-----------------|--------------------------------------------------------------------------|
| PRACTICE_ID     | Practice identifier, must match seeded record                            |
| DATABASE_URL    | Postgres connection string, injected automatically by Railway            |
| DEV_MODE        | Set to 1 to skip SMTP and ADMIN_TOKEN checks                             |
| DATA_DIR        | Path to condition JSON directory (data)                                  |
| PORT            | Injected by Railway. uvicorn binds to this port. Do not hardcode 8000.   |

DB_PATH has been removed. It was the SQLite file path and is no longer used.

PRACTICE_NAME and PRACTICE_EMAIL are optional. If not set, PRACTICE_NAME
defaults to the value of PRACTICE_ID and PRACTICE_EMAIL defaults to
demo@demo.net.

Local development requires a `.env` file (not committed to version control)
containing `TEST_DATABASE_URL` for running repository integration tests.

### 15.6 Current deployment mode

The hosted demo runs with DEV_MODE=1. This means:
- No emails are sent on form submission
- Admin endpoints accept any non-empty bearer token
- SMTP environment variables are not required

This is intentional for a demonstration deployment. DEV_MODE must be
removed and SMTP variables configured before the app is used for any
real clinical submissions.

