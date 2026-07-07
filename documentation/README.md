# Econsult

A patient-facing online consultation system for a single GP practice. Patients
answer a structured, condition-specific questionnaire; the system applies
deterministic clinical safety rules, generates a PDF summary, and delivers it
to the practice. Includes an admin portal for practice staff.

## Stack

- **Backend:** Python 3.12, FastAPI, Postgres (psycopg2), Alembic migrations
- **Frontend:** React + TypeScript, built with Vite (two entry points: patient
  form and admin portal)
- **Hosting:** Railway, single Docker image (multi-stage Node + Python build)
- **Email delivery:** Mailgun HTTP API or SMTP
- **Error reporting:** Sentry (optional)

## Repository layout

| Path | Purpose |
|---|---|
| `main.py` | FastAPI entry point (web service) |
| `worker_main.py` | Delivery worker entry point |
| `pdf_worker_main.py` | PDF generation worker entry point |
| `deletion_job.py` | Nightly data-retention cron script |
| `app/` | All Python application code (models, services, repositories, routers) |
| `alembic/` | Database migrations |
| `frontend/` | Patient UI (`src/`) and admin UI (`admin-ui/src/`) |
| `data/` | Condition ruleset JSON files (clinical logic lives here, not in code) |
| `scripts/` | One-time management commands (e.g. `create_admin_user.py`) |
| `docs/` | Architecture documentation and operational guides |
| `sandbox/` | Local-only NHS MESH sandbox (never deployed) |
| `tests/` | Python test suite (frontend tests live next to their components) |

See `docs/file_structure.md` for the full annotated layout.

## Architecture documentation

Start with `docs/architecture.md`. It is the hub document: it states the
project-wide invariants (the rules that must never be violated) and routes to
domain-specific "spoke" documents in `docs/`. Read the invariants section
before writing any code.

## Prerequisites

- Python 3.12
- Node 20 or later
- Postgres 15 or later (two databases: one for the running app, one for
  integration tests — never the same one)
- `psql` or another Postgres client

## Local setup

1. Clone the repository and install dependencies:

   ```
   pip install -r requirements.txt -r requirements-dev.txt pytest httpx
   cd frontend && npm ci && cd ..
   ```

2. Install the git hook that runs ruff automatically on every commit
   (one-time, per clone):

   ```
   make hooks-install
   ```

3. Create a `.env` file in the project root (not committed). The Makefile
   loads it automatically. At minimum, set `DATABASE_URL` (your local dev
   database) and `TEST_DATABASE_URL` (a separate local test database). The
   full list of variables the app requires at startup is in
   `docs/deployment_checklist.md` — the app fails fast with a clear error
   message for each missing one, so you can also iterate from the errors.

4. Run migrations and seed the dev database (practice record + first admin
   user):

   ```
   python -m alembic upgrade head
   python scripts/create_admin_user.py you@example.com --create-practice
   ```

5. Run the backend:

   ```
   uvicorn main:app --reload
   ```

   Note: in local dev the built frontend is not served by the backend
   (`frontend/dist` does not exist), so run the Vite dev server separately:

   ```
   cd frontend && npm run dev
   ```

## Running tests

```
make test               # Python unit tests + frontend Vitest (no database)
make test-integration   # Python integration tests (requires TEST_DATABASE_URL)
make test-all           # Everything
```

Integration tests refuse to run unless `TEST_DATABASE_URL` is set. This is a
deliberate guardrail — see `docs/arch_testing.md` for the two-database rule
before touching test configuration.

CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same targets plus a
TypeScript type check on every push and pull request.

## Deployment

Deployment is to Railway via the Dockerfile. Follow
`docs/deployment_checklist.md` step by step for a new environment — the
application validates its configuration at startup and refuses to boot if
anything is missing.

The system runs as multiple Railway services from the same image: the web
service (`main.py`), the delivery worker, the PDF worker, and a nightly cron
for `deletion_job.py`.

## Key things to know before contributing

- **Clinical meaning lives only in the JSON rulesets** in `data/`, never in
  code. The engine interprets them deterministically.
- **Fail-fast is a design rule, not an accident.** Missing configuration must
  abort startup. Do not add defaults or silent fallbacks to required settings.
- **Module boundaries are enforced by convention.** `docs/file_structure.md`
  ends with a banned-imports list. Violating it is a design failure even if
  the code works.
- **Database writes to JSONB columns** must wrap dicts in
  `psycopg2.extras.Json()` — see `docs/arch_infrastructure.md` for this and
  other data quirks.