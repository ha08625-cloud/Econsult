# Econsult Quick Start

## Prerequisites
- Backend dependencies installed in the `econsult` conda environment
- Node dependencies installed (`frontend/node_modules` exists)
- `runtime.db` exists with the Summertown practice record
- `.env` file exists in project root

## Start the backend

From project root, in terminal 1:

```bash
export $(cat .env | xargs) && PYTHONPATH=backend uvicorn backend.main:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

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
| Practice admin | http://localhost:8000/admin-portal/ |

Admin token: any non-empty string in DEV_MODE (ADMIN_TOKEN not set)

## .env reference

```
DEV_MODE=1
PRACTICE_ID=summertown_health_centre
DB_PATH=runtime.db
DATA_DIR=data
```

## Useful checks

Verify backend is up:
```bash
curl http://localhost:8000/conditions
```

Verify a submission was recorded:
```bash
sqlite3 runtime.db "SELECT submission_id, delivery_status FROM submission_records ORDER BY submitted_at DESC LIMIT 5"
```
