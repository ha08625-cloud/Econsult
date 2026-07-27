# Infrastructure, Database & Deployment

**LLM INSTRUCTIONS:** Design decisions, constraints, and gotchas for the hosting, build, database, and migration layers. Read `Dockerfile`, `main.py`, `db.py`, and the Alembic migration files directly for implementation details. For the operational deployment procedure and the authoritative environment variable table, see `docs/deployment_checklist.md` — do not duplicate that content here.

---

## Scope

Railway deployment, multi-stage Docker build, process topology, static file serving, Postgres + psycopg2, Alembic migrations.

**Key files:** `Dockerfile`, `railway.toml`, `main.py`, `app/core/settings.py`, `app/core/wiring.py`, `worker_main.py`, `pdf_worker_main.py`, `deletion_job.py`, `db.py`, `alembic.ini`, `alembic/env.py`, migration files in `alembic/versions/`

---

## Build & Deployment

- **Platform:** Railway. One Docker image, multiple Railway services (see Process Topology below).
- **Dockerfile** is two-stage: Stage 1 (Node 22 slim) builds the Vite frontend; Stage 2 (Python 3.12 slim) is the runtime. The built `frontend/dist` is copied from Stage 1 into the Python image.
- `consultation_outcomes.json` lives at `app/core/` (read by Python) and is copied separately into the frontend build context because `OutcomeScreen.tsx` imports it at build time. If this file moves, both the Python import and the Dockerfile `COPY` must change together.
- `VITE_SENTRY_DSN` is a build argument baked into the frontend bundle at build time. It is not a secret (DSNs are visible in browser traffic). Railway passes service variables as build args automatically.
- The Vite build produces two entry points under `frontend/dist/`: `index.html` (patient form) and `admin-ui/index.html` (admin portal).
- **Static serving:** `main.py` checks whether `frontend/dist` exists on disk at startup. If present, it mounts the entire directory via Starlette `StaticFiles(html=True)` at `/`. If absent (local dev, no build step), static serving is skipped with a log line.
- **Critical ordering constraint:** All API routes must be registered in `main.py` before the static files mount. `StaticFiles` acts as a catch-all and will intercept API requests if mounted first.

---

## Process Topology

Four processes are deployed from the same Docker image, as separate Railway services (a fifth entry point exists but is currently dormant):

| Process | Entry point | Started by |
|---|---|---|
| Web API + static frontend | `uvicorn main:app` | Dockerfile `CMD` (default) |
| Delivery worker | `python worker_main.py` | Railway start command override |
| PDF worker | `python pdf_worker_main.py` | Railway start command override |
| Deletion job (nightly) | `python deletion_job.py` | Railway cron |

A fifth entry point, the MESH dispatcher (`python mesh_worker_main.py`), exists in the codebase but is **not completed and not deployed**. It is the consumer for the `mesh_jobs` queue and only runs once MESH delivery is enabled (requires onboarding with NHS digital, cant be built in isolation). The four processes above are the complete deployed topology today.

Design decisions and constraints:

- **Only the web service runs Alembic migrations** (`alembic_upgrade()` at import time in `main.py`). Workers assume the schema is current. If Railway starts a worker before the web service finishes migrating, the worker fails, exits, and is restarted by Railway until it succeeds. Railway's restart behaviour is the sole, deliberate recovery mechanism for this race.
- **All processes must share the same `MESH_DELIVERY` value.** The web service and PDF worker validate it at startup and refuse to start on any value other than `"0"` (Phase 1a). See `docs/deployment_checklist.md` for the variable table.
- **Start commands live in the Railway UI, not in version control.** `railway.toml` only selects the Dockerfile builder. This is a known configuration-drift risk; `docs/deployment_checklist.md` is the authoritative written record of the required services and their start commands. If a service's start command is changed in Railway, the checklist must be updated.
- No process manager runs inside the container; each Railway service runs exactly one process.

---

## Database

- **Postgres** via **psycopg2**. `db.py` is the only file in the codebase that imports psycopg2.
- `get_conn(database_url)` is a context manager that commits on success and rolls back on failure. It yields the connection; each repository opens its own cursor with `RealDictCursor`.
- `RealDictCursor` returns `RealDictRow` objects which behave as dicts. `dict(row)` at call sites works correctly.
- **Connections are opened per operation — no pooling.** This is acceptable at single-practice scale and keeps `db.py` trivial. Revisit if request volume grows.
- **Every connection carries four timeouts** (constants in `db.py`, overridable per call, no environment variables): `connect_timeout` 5s, `statement_timeout` 10s, `idle_in_transaction_session_timeout` 30s, and TCP keepalives (30/10/3) plus `tcp_user_timeout` 30s. Each covers a different failure and none substitutes for another. In particular `statement_timeout` is enforced by the *server*, so it cannot fire when the server is what disappeared — keepalives are the only client-side bound on that case. That case matters here because every route is `async def` and calls synchronous psycopg2 directly on the event loop thread with a single uvicorn worker, so one connection blocked in `recv()` stalls every concurrent request in the process, not just its own.
- **The 10s `statement_timeout` is a safety valve, not a measured value.** Every web-facing query is a single-row lookup, so it is deliberately loose; it is set where it is because `practice_repository.lock_practice` issues a blocking `SELECT ... FOR UPDATE` that legitimately waits on contention. Tighten it once there is production data on real query latency. `deletion_job.py` overrides it to 2 minutes for its unbounded bulk deletes.
- **Consequence to know about:** contended admin user add/remove now aborts with `QueryCanceled` after 10s instead of blocking indefinitely.
- **Alembic gets `connect_timeout` but deliberately no `statement_timeout`** (`alembic/env.py`). An unreachable database now fails the deploy instead of hanging it, but a migration killed halfway is worse than one that runs long.
- **A timeout raises `psycopg2.errors.QueryCanceled`** (SQLSTATE 57014, an `OperationalError` subclass) and surfaces as a 500, like any other unhandled database error. Mapping it to a 503 would mean translating psycopg2 errors into an application error type inside `db.py`; not done.

### Critical Data Quirks — Do Not Violate

- **JSONB writes:** psycopg2 does not automatically adapt Python dicts to JSONB. All write paths for JSONB columns (`state_json`, `clinical_output_json`, `audit_output_json`, `provider_events`) must wrap dicts in `psycopg2.extras.Json()`. Read paths receive plain dicts naturally and need no unwrapping.
- **`signposting_json` misnomer:** The `signposting_json` column in `practice_signposting` stores a plain HTML string, not JSON. Do not attempt to parse it as JSON. The column name is a legacy artefact.
- **`nh3` / DOMPurify sync:** The `SIGNPOSTING_PURIFY_CONFIG` in `frontend/src/constants.ts` must exactly match the `nh3` allowlist in `practice_repository.py`. If they diverge, content the admin can save will not render as expected on the patient side.
- **`nh3` link constraint:** The `rel` attribute on `<a>` tags is reserved by `nh3`. Do not pass `rel` through the attributes dict — `nh3` will panic.

---

## Migrations (Alembic)

- `alembic_upgrade()` in `db.py` runs `alembic upgrade head` at application startup (web service only). A migration failure must halt startup — this is correct behaviour.
- **No automated rollback.** Rollbacks are manual: `alembic downgrade -1` against the live database.
- Migration files live in `alembic/versions/`. Check these files directly for the current schema.

Current migrations:
- `0001_initial_schema.py` — complete baseline schema.
- `0002_user_management_cascade.py` — `ON DELETE CASCADE` on `admin_sessions.user_id` FK; `admin_users.last_login` nullable `TIMESTAMPTZ`.
- `0003_webhook_tracking.py` — `provider_message_id` and `provider_events` on `delivery_jobs`; extended status check constraint; `webhook_tokens` replay protection table.
- `0004_password_auth.py` — password columns on `admin_users` (`hashed_password`, `failed_password_attempts`, `password_locked_until`, `password_changed_at`); `admin_password_reset_tokens` table.
- `0005_mesh_schema.py` — `mesh_jobs` table (outbound MESH delivery queue, one row per MESH-enabled submission); `is_fallback` boolean on `delivery_jobs`. Applied by `alembic upgrade head` like every other migration; the schema objects sit dormant until MESH is enabled in a later phase.

---

## Startup Validation (Fail-Fast)

Validation runs at import time in `main.py` and aborts with a `RuntimeError` on any failure. It is split by what each check needs:

**Environment variables — `app/core/settings.py`** (`load_web_settings()`, no database access):

- `DATABASE_URL`, `PRACTICE_ID`, `ALLOWED_ADMIN_DOMAINS` must be set
- `EMAIL_FROM` must be set
- A complete email path must be present: a complete Mailgun configuration (`MAILGUN_API_KEY` + `MAILGUN_DOMAIN`) or a complete SMTP configuration (`SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD`)
- `MAILGUN_SIGNING_KEY` must be set when the Mailgun path is selected (otherwise webhook signature verification would be impossible)
- `MESH_DELIVERY` must be present and exactly `"0"` or `"1"`; `"1"` is rejected in Phase 1a (no defaulting is permitted)

`EmailSettings.delivery_mode` is the single predicate that decides Mailgun vs SMTP: it returns `"mailgun"` only for a complete Mailgun configuration. A **partial** Mailgun configuration (one of `MAILGUN_API_KEY` / `MAILGUN_DOMAIN` but not both) is treated as not-Mailgun: if SMTP is complete the deployment falls through to SMTP and logs a warning so the demotion is visible in Railway logs; if SMTP is incomplete, startup aborts. This deliberately replaced two inconsistent legacy predicates that could select a broken Mailgun path at send time.

**Database state — `app/core/wiring.py`** (`run_deployment_checks`, inside `build_container`):

- The practice record must exist (**no automatic seeding** — insert it manually before first startup; see `docs/deployment_checklist.md`)
- The practice record must have a non-empty email
- The database must contain exactly one practice (single-tenant invariant)
- At least one admin user must exist (created via `scripts/create_admin_user.py`)

The only row the application inserts automatically at startup is the **default availability row** (`availability_repo.init_availability`), created if absent after all checks pass. The practice record and first admin user are never auto-created.

The practice name used in generated PDFs is captured once at startup. If it is changed via the admin interface, the running web service uses the old name until the next restart.

---

## Environment Variables

The authoritative environment variable table — including which variables each Railway service requires — lives in `docs/deployment_checklist.md`. It is not duplicated here.

Design notes only:

- `MESH_DELIVERY` deliberately has **no default**. A deployment that has not made an explicit choice must abort, per the Fail-Fast Configuration project invariant.
- `DATA_DIR` and `PORT` have code-level defaults (`./data` and `8000` respectively) and are effectively optional outside Railway; Railway injects `PORT`.

---

## Testing

The two-database rule, `TEST_DATABASE_URL` guardrails, and the CI exception (ephemeral Postgres container) are documented in `docs/arch_testing.md`. A dedicated test database is provisioned on Railway; integration tests never run against the deployed database locally.