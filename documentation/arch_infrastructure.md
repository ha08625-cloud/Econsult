# Infrastructure, Database & Deployment

**LLM INSTRUCTIONS:** Design decisions, constraints, and gotchas for the hosting, build, database, and migration layers. Read `Dockerfile`, `main.py`, `db.py`, and the Alembic migration files directly for implementation details.

---

## Scope

Railway deployment, multi-stage Docker build, static file serving, Postgres + psycopg2, Alembic migrations, environment variables.

**Key files:** `Dockerfile`, `main.py`, `db.py`, `alembic.ini`, `alembic/env.py`, migration files in `alembic/versions/`

---

## Build & Deployment

- **Platform:** Railway, single-container deployment.
- **Dockerfile** is two-stage: Stage 1 (Node 22 slim) builds the Vite frontend; Stage 2 (Python 3.12 slim) is the runtime. The built `frontend/dist` is copied from Stage 1 into the Python image.
- The Vite build produces two entry points under `frontend/dist/`: `index.html` (patient form) and `admin-ui/index.html` (admin portal).
- **Static serving:** `main.py` checks whether `frontend/dist` exists on disk at startup. If present, it mounts the entire directory via Starlette `StaticFiles(html=True)` at `/`. If absent (local dev, no build step), static serving is silently skipped. `DEV_MODE` does not control this — it only controls email delivery behaviour and cookie security flags.
- **Critical ordering constraint:** All API routes must be registered in `main.py` before the static files mount. `StaticFiles` acts as a catch-all and will intercept API requests if mounted first.
- The server process is started directly with `uvicorn` via the Dockerfile `CMD` — no process manager.

---

## Database

- **Postgres** via **psycopg2**. `db.py` is the only file in the codebase that imports psycopg2.
- `get_conn(database_url)` is a context manager that commits on success and rolls back on failure. It yields the connection; each repository opens its own cursor with `RealDictCursor`.
- `RealDictCursor` returns `RealDictRow` objects which behave as dicts. `dict(row)` at call sites works correctly.

### Critical Data Quirks — Do Not Violate

- **JSONB writes:** psycopg2 does not automatically adapt Python dicts to JSONB. All write paths for JSONB columns (`state_json`, `clinical_output_json`, `audit_output_json`) must wrap dicts in `psycopg2.extras.Json()`. Read paths receive plain dicts naturally and need no unwrapping.
- **`signposting_json` misnomer:** The `signposting_json` column in `practice_signposting` stores a plain HTML string, not JSON. Do not attempt to parse it as JSON. The column name is a legacy artefact.
- **`nh3` / DOMPurify sync:** The `SIGNPOSTING_PURIFY_CONFIG` in `frontend/src/constants.ts` must exactly match the `nh3` allowlist in `practice_repository.py`. If they diverge, content the admin can save will not render as expected on the patient side.
- **`nh3` link constraint:** The `rel` attribute on `<a>` tags is reserved by `nh3`. Do not pass `rel` through the attributes dict — `nh3` will panic.

---

## Migrations (Alembic)

- `alembic_upgrade()` in `db.py` runs `alembic upgrade head` at application startup. A migration failure must halt startup — this is correct behaviour.
- **No automated rollback.** Rollbacks are manual: `alembic downgrade -1` against the live database.
- Migration files live in `alembic/versions/`. Check these files directly for the current schema.

---

## Startup Validation (Fail-Fast)

`_validate_startup()` in `main.py` runs at import time and aborts if:

- `PRACTICE_ID` env var is missing
- The database contains more than one practice (single-tenant invariant)
- The practice record has no email configured
- `SMTP_*` / `EMAIL_FROM` vars are missing and `DEV_MODE` is not set
- `INITIAL_ADMIN_EMAIL` or `ALLOWED_ADMIN_DOMAINS` are missing and `DEV_MODE` is not set

If the practice record does not exist, startup **seeds it** using `PRACTICE_NAME` and `PRACTICE_EMAIL` env vars (defaulting to `demo@demo.net`). This handles Railway deployments where the database starts empty on each container restart.

---

## Testing Constraint

Repository tests currently run against a live Postgres instance via the `TEST_DATABASE_URL` env var in `.env`. There is no test isolation from the deployed database. A dedicated test database must be provisioned before any real patient data is stored or before a second developer joins.

---

## Required Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Always | Postgres connection string (injected by Railway) |
| `PRACTICE_ID` | Always | Practice identifier |
| `DATA_DIR` | Always | Path to condition JSON directory (`data/`) |
| `PORT` | Always | Injected by Railway; uvicorn binds to this |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` | Production only | Email delivery |
| `INITIAL_ADMIN_EMAIL` | Production only | Email address of the first admin user, seeded on first startup |
| `ALLOWED_ADMIN_DOMAINS` | Production only | Comma-separated list of permitted admin email domains (e.g. `nhs.net,gov.uk`) |
| `DEV_MODE` | Dev only | Set to `1` to skip SMTP checks and use console delivery; sets cookies without `Secure` flag for plain HTTP |
| `PRACTICE_NAME`, `PRACTICE_EMAIL` | Optional | Used to seed practice record on first startup |
| `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` | Optional | If set, Mailgun HTTP API is used instead of SMTP |
| `SENTRY_DSN` | Optional | If set, Sentry error reporting is enabled |