# MESH Sandbox (local dev)

A locally-run mock of NHS Digital's MESH API. Used while building and testing
`mesh_worker.py` (dispatcher) and `mesh_inbox_worker.py` (receipt poller)
without needing real Spine credentials.

This directory exists only for **local development**. The sandbox is never
deployed to Railway and never runs in CI.

## Prerequisites

Docker installed locally (Docker Desktop on macOS/Windows, or Docker Engine
on Linux).

## Quick start

```
make sandbox-up        # start in background
make sandbox-check     # confirm health endpoint responds
make sandbox-down      # stop and remove
```

Or directly with docker compose:

```
cd sandbox/
docker compose up -d
curl -k https://localhost:8700/health   # should return ok
docker compose down
```

The `-k` flag on curl is required because the sandbox uses a self-signed
TLS certificate. Our Python workers do the same thing internally when
`MESH_ENV=sandbox`.

## What's in here

| File | Purpose |
|---|---|
| `docker-compose.yml` | Pulls and runs the official `NHSDigital/mesh-sandbox` Docker image, pinned to tag `v1.0.54`. |
| `mailboxes.jsonl` | Defines two pre-created mailboxes inside the sandbox. |

## The two mailboxes

| Mailbox ID | ODS code | Role |
|---|---|---|
| `SENDER_MAILBOX` | `X26` | Our workers authenticate as this mailbox when sending. Receives delivery receipts back from the sandbox. |
| `TARGET_MAILBOX` | `A99999` | The mock GP practice. Our workers POST messages here. |

`X26` is the standard NHS test ODS code. The startup guard in `main.py`
allows `X26` only when `MESH_ENV` is `sandbox` or `integration` — it refuses
to start in `production` mode if `TARGET_ODS_CODE=X26`, preventing clinical
data from being sent to a test mailbox.

## How the sandbox helps end-to-end testing

The sandbox **automatically generates a delivery receipt** whenever a message
is POSTed to a target mailbox. The receipt appears in the sender mailbox's
inbox within a few seconds. This means:

1. `mesh_worker.py` sends a message to `TARGET_MAILBOX`.
2. The sandbox auto-generates a delivery receipt.
3. The receipt lands in `SENDER_MAILBOX` inbox.
4. `mesh_inbox_worker.py` polls the inbox, finds the receipt, and transitions
   `mesh_jobs.status` from `provider_accepted` to `delivered`.

The full happy-path flow can be tested locally without any real NHS
infrastructure.

## Configuring workers to use the sandbox

Set these environment variables when running workers locally:

```
MESH_DELIVERY=1
MESH_ENV=sandbox
MESH_URL=https://localhost:8700
MESH_SHARED_KEY=TestKey
MESH_MAILBOX_ID=SENDER_MAILBOX
MESH_MAILBOX_PASSWORD=password
SENDER_ODS_CODE=X26
TARGET_ODS_CODE=A99999
```

TLS verification is automatically disabled by the worker's HTTP client when
`MESH_ENV=sandbox`. Production deployments physically cannot hit the sandbox
because the URLs differ.

## State and persistence

Messages live in memory only. `docker compose down` wipes everything,
including any in-flight messages and receipts. This is intentional — a clean
slate per dev session is more useful than persistence for the work we're
doing here. If persistence ever becomes useful for debugging, add
`STORE_MODE=file` plus a volume mount in `docker-compose.yml`.

## Bumping the sandbox version

Edit the `refs/tags/v1.0.54` in `docker-compose.yml`. Releases are at
<https://github.com/NHSDigital/mesh-sandbox/releases>. Re-run
`docker compose up --build -d` to rebuild.

Sandbox behaviour can change between releases — bump deliberately, not
casually.