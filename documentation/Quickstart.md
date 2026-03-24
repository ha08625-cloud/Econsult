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