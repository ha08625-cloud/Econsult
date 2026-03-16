# Infrastructure, Database & Deployment Architecture

**DOMAIN RULES:** This document covers the hosting environment, database constraints, migrations, and static file serving.

## 1. Environment & Build Constraints
* **Platform:** Deployed on Railway using a multi-stage `Dockerfile` (Stage 1: Node 22 frontend build; Stage 2: Python 3.12-slim runtime).
* **Static Serving:** FastAPI serves the Vite-built frontend directly. 
  * The Vite build produces two entry points: `dist/index.html` (Patient Form) and `dist/admin-ui/index.html` (Admin Portal).
  * FastAPI checks for `frontend/dist/assets` on disk at startup. If present, it mounts the directory and routes unmatched paths to `index.html` for client-side routing.

## 2. Database & Migrations (Postgres + Alembic)
* **Migrations at Startup:** `alembic_upgrade()` runs `alembic upgrade head` at application startup. Any migration failure MUST halt startup.
* **Rollbacks:** There is no automated rollback. Rollbacks are manual via `alembic downgrade -1` against the live DB.
* **Integration Tests:** Repository tests (`tests/test_repositories.py`) currently run against a live Postgres instance via the `TEST_DATABASE_URL` `.env` variable. 

## 3. Critical Data Quirks (DO NOT VIOLATE)
* **JSONB Write Constraint:** `psycopg2` does not automatically adapt Python dicts to JSONB. All write paths for `state_json`, `clinical_output_json`, and `audit_output_json` MUST explicitly wrap dicts in `psycopg2.extras.Json()`. (Read paths receive plain dicts naturally).
* **The `signposting_json` Misnomer:** The `signposting_json` column in `practice_signposting` stores a plain HTML string, NOT JSON. Do not attempt to parse it as JSON.
* **`nh3` / DOMPurify Sync:** The `SIGNPOSTING_PURIFY_CONFIG` in `frontend/src/constants.ts` MUST exactly match the `nh3` allowlist in `practice_repository.py`.
* **`nh3` Link Constraint:** The `rel` attribute on `<a>` tags is reserved by `nh3`. Do not pass `rel` through the attributes dict or `nh3` will panic.

## 4. Required Environment Variables
| Variable | Purpose |
| :--- | :--- |
| `DATABASE_URL` | Postgres connection string (injected by Railway) |
| `PRACTICE_ID` | Practice identifier (must match seeded DB record) |
| `DATA_DIR` | Path to condition JSON directory (`data/`) |
| `DEV_MODE` | Set to 1 to skip SMTP and ADMIN_TOKEN checks |
| `PORT` | Injected by Railway. Uvicorn binds to this |
