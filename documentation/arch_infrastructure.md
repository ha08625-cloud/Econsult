# Infrastructure, Database & Deployment

**LLM INSTRUCTIONS:** Design decisions, constraints, and gotchas for the hosting, build, database, and migration layers. Read `Dockerfile`, `main.py`, `db.py`, and the Alembic migration files directly for implementation details.

---

## Scope

Railway deployment, multi-stage Docker build, static file serving, Postgres + psycopg2, Alembic migrations, environment variables, and service topology.

**Key files:** `Dockerfile`, `main.py`, `worker_main.py`, `pdf_worker_main.py`, `deletion_job.py`, `db.py`, `alembic.ini`, `alembic/env.py`, migration files in `alembic/versions/`

---

## Build, Deployment & Service Topology

- **Platform:** Railway. The application uses a multi-service deployment model driven from a single shared Docker image.
- **Service Topology:** While there is only one Dockerfile, the Railway environment must be configured (via the Railway UI, not `railway.toml`) to run four distinct services using custom start commands:
  1. **Web Service:** `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}` (Handles HTTP, static files, and DB migrations).
  2. **Delivery Worker:** `python worker_main.py` (Background SMTP/Mailgun delivery).
  3. **PDF Worker:** `python pdf_worker_main.py` (Background PDF generation).
  4. **Deletion Cron Job:** `python deletion_job.py` (Scheduled task for data retention enforcement).
- **Dockerfile** is two-stage: Stage 1 (Node 22 slim) builds the Vite frontend; Stage 2 (Python 3.12 slim) is the runtime. The built `frontend/dist` is copied from Stage 1 into the Python image.
- The Vite build produces two entry points under `frontend/dist/`: `index.html` (patient form) and `admin-ui/index.html` (admin portal).
- **Static serving:** `main.py` checks whether `frontend/dist` exists on disk at startup. If present, it mounts the entire directory via Starlette `StaticFiles(html=True)` at `/`. If absent (local dev, no build step), static serving is silently skipped.
- **Critical ordering constraint:** All API routes must be registered in `main.py` before the static files mount. `StaticFiles` acts as a catch-all and will intercept API requests if mounted first.

---

## Database

- **Postgres** via **psycopg2**. `db.py` is the only file in the codebase that imports psycopg2.
- `get_conn(database_url)` is a context manager that commits on success and rolls back on failure. It yields the connection; each repository opens its own cursor with `RealDictCursor`.
- `RealDictCursor` returns `RealDictRow` objects which behave as dicts. `dict(row)` at call sites works correctly.

### Critical Data Quirks — Do Not Violate

- **JSONB writes:** psycopg2 does not automatically adapt Python dicts to JSONB. All write paths for JSONB columns (`state_json`, `clinical_output_json`, `audit_output_json`, `provider_events`) must wrap dicts in `psycopg2.extras.Json()`. Read paths receive plain dicts naturally and need no unwrapping.
- **`signposting_json` misnomer:** The `signposting_json` column in `practice_signposting` stores a plain HTML string, not JSON. Do not attempt to parse it as JSON. The column name is a legacy artefact.
- **`nh3` / DOMPurify sync:** The `SIGNPOSTING_PURIFY_CONFIG` in `frontend/src/constants.ts` must exactly match the `nh3` allowlist in `practice_repository.py`. If they diverge, content the admin can save will not render as expected on the patient side.
- **`nh3` link constraint:** The `rel` attribute on `<a>` tags is reserved by `nh3`. Do not pass `rel` through the attributes dict — `nh3` will panic.

---

## Migrations (Alembic)

- `alembic_upgrade()` in `main.py` (via `db.py`) runs `alembic upgrade head` at application startup. A migration failure must halt the web service startup — this is correct behaviour.
- **Migration Race Condition:** Only the FastAPI web service runs migrations. The background workers (`worker_main.py`, `pdf_worker_main.py`) assume the schema is up to date. If Railway starts a worker before the web service completes its migration run, the worker will fail querying the database, exit, and be restarted by Railway. This restart behaviour is the sole and acceptable recovery mechanism for this race.
- **No automated rollback.** Rollbacks are manual: `alembic downgrade -1` against the live database.
- Migration files live in `alembic/versions/`. Check these files directly for the current schema.

Current migrations:
- `0001_initial_schema.py` — complete baseline schema.
- `0002_user_management_cascade.py` — `ON DELETE CASCADE` on `admin_sessions.user_id` FK; `admin_users.last_login` nullable `TIMESTAMPTZ`.
- `0003_webhook_tracking.py` — `provider_message_id` and `provider_events` on `delivery_jobs`; extended status check constraint; `webhook_tokens` replay protection table.
- `0004_password_auth.py` — transitions authentication state for password-based auth.

---

## Startup Validation (Fail-Fast)

`_validate_startup()` in `main.py` runs at import time and aborts if:

- `PRACTICE_ID` env var is missing
- The practice record does not exist in the database (must be manually seeded via SQL/scripts before deployment)
- The database contains more than one practice (single-tenant invariant)
- The practice record has no email configured
- `SMTP_*` / `EMAIL_FROM` vars are missing (or `MAILGUN_API_KEY` + `MAILGUN_DOMAIN` are not set as the Mailgun alternative)
- `MAILGUN_API_KEY` is set but `MAILGUN_SIGNING_KEY` is not set
- `ALLOWED_ADMIN_DOMAINS` is missing
- `MESH_DELIVERY` is not explicitly set to exactly `"0"` or `"1"`
- The database contains no admin users for the practice

---

## Testing Constraint

Integration tests require a dedicated Postgres database to ensure isolation. A dedicated test database is provisioned on Railway with guardrails to prevent accidental mutation of the production database during test runs (refer to `arch_testing.md` for specific execution details).

---

## Required Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Always | Postgres connection string (injected by Railway) |
| `PRACTICE_ID` | Always | Practice identifier |
| `MESH_DELIVERY` | Always | `"0"` for email delivery path, `"1"` for MESH path. |
| `WORKER_POLL_INTERVAL_SECONDS` | Always (Delivery Worker) | Seconds to sleep when the delivery queue is empty. |
| `PDF_WORKER_POLL_INTERVAL_SECONDS` | Always (PDF Worker) | Seconds to sleep when the PDF queue is empty. |
| `ALLOWED_ADMIN_DOMAINS` | Always | Comma-separated list of permitted admin email domains (e.g. `nhs.net,gov.uk`) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` | Production only | Email delivery (SMTP path) |
| `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `EMAIL_FROM` | Production only (Mailgun path) | Mailgun HTTP API delivery |
| `MAILGUN_SIGNING_KEY` | Required when `MAILGUN_API_KEY` is set | Mailgun webhook HMAC signing key — used to verify inbound delivery signals |
| `ADMIN_URL` | Always | Used to generate absolute links back to the admin portal in email alerts |
| `MESH_RECIPIENT_MAILBOX_ID` | Required if `MESH_DELIVERY=1` | The destination practice mailbox for the MESH integration |
| `DATA_DIR` | Optional | Path to condition JSON directory (Defaults to `./data`) |
| `PORT` | Optional | Injected by Railway; uvicorn binds to this (Defaults to `8000`) |
| `SENTRY_DSN` | Optional | If set, Sentry error reporting is enabled |