# MESH Sandbox (local dev)

A locally-run mock of NHS Digital's MESH API, fronted by an nginx
mTLS-terminating proxy. Used while building and testing `mesh_worker.py`
(dispatcher) and `mesh_tracking_worker.py` (status poller) without needing
real Spine credentials.

This directory exists only for **local development**. It is never deployed
to Railway and never runs in CI.

## Prerequisites

- Docker installed locally (Docker Desktop on macOS/Windows, or Docker
  Engine on Linux).
- The dev PKI generated. If `sandbox/certs/sandbox_*.pem` files are missing,
  run `bash sandbox/certs/generate.sh` once. See `sandbox/certs/README.md`.

## Quick start

```
make sandbox-up        # start nginx + mesh_sandbox in background
make sandbox-check     # confirm the proxy + mTLS chain works
make sandbox-down      # stop and remove
```

`sandbox-check` uses curl with the dev client cert. Plain curl -k https://localhost:8700/health will now return HTTP 400 "No required SSL certificate was sent" from nginx — that is the mTLS layer doing its job.

## Topology

```
worker process                 nginx (in docker)            mesh_sandbox (in docker)
(MeshClient w/ certs)          mTLS termination             HTTPS, self-signed
                               + client-cert validation     cert (rotates on
                                                            restart)

host:8700 ─ HTTPS+mTLS ──────► nginx:443
                                  │  validates client cert
                                  │  against sandbox_ca.pem
                                  └─► https://mesh_sandbox:443
                                      (proxy_ssl_verify off,
                                       internal docker network)
```

- The worker connects to `https://localhost:8700`.
- nginx terminates TLS, validates the worker's client certificate against
  the dev CA in `sandbox/certs/sandbox_ca.pem`, then proxies HTTPS to the
  sandbox over an internal docker network.
- The sandbox container has **no host port mapping**. It is reachable only
  from within the docker network.
- The internal nginx → sandbox hop uses HTTPS-without-verify because the
  sandbox's self-signed cert rotates on container restart and verifying
  it would be pointless. The internal hop never leaves the docker bridge
  network.

The production mTLS code path in `MeshClient` (presenting a client cert,
verifying a server cert against a CA bundle) is therefore exercised on
every local sandbox request. See `docs/arch_security.md` section 8.

## What's in here

| File | Purpose |
|---|---|
| `docker-compose.yml` | Pulls the official `NHSDigital/mesh-sandbox` image at v1.0.54, runs it behind an nginx mTLS proxy. |
| `nginx/nginx.conf` | nginx config: TLS termination + client-cert validation + reverse proxy. |
| `certs/` | Dev PKI (CA, server cert, client cert). See `certs/README.md`. |
| `mailboxes.jsonl` | Defines two pre-created mailboxes inside the sandbox. |

## The two mailboxes

| Mailbox ID | ODS code | Role |
|---|---|---|
| `SENDER_MAILBOX` | `X26` | The worker authenticates as this mailbox when sending. The tracking endpoint reads its message status. |
| `TARGET_MAILBOX` | `A99999` | The mock GP practice. The worker POSTs messages here. |

`X26` is the standard NHS test ODS code. The mailbox IDs and passwords are
defined in `mailboxes.jsonl` and loaded by the sandbox at startup.

## How the sandbox helps end-to-end testing

The mesh-sandbox auto-marks any message POSTed to a target mailbox as
delivered shortly after acceptance. The end-to-end happy path is:

1. `mesh_worker.py` POSTs a message to `TARGET_MAILBOX`, gets back a
   32-char hex `messageID`.
2. The sandbox auto-transitions the message to delivered.
3. `mesh_tracking_worker.py` polls
   `/messageexchange/<sender_mailbox>/outbox/tracking?messageID=<messageID>`, finds
   `statusSuccess: SUCCESS`, and transitions the local `mesh_jobs.status`
   to `delivered`.

This flow can be exercised locally without any real NHS infrastructure.
Sandbox limitations vs production are tracked in
`docs/nhs_integration_reference.md`.

## Configuring workers to use the sandbox

Set these environment variables when running workers locally (a
`.env.sandbox` file is a convenient pattern):

```
MESH_DELIVERY=1
MESH_BASE_URL=https://localhost:8700
MESH_SHARED_KEY=TestKey
MESH_MAILBOX_ID=SENDER_MAILBOX
MESH_MAILBOX_PASSWORD=password
MESH_CA_CERT_PATH=sandbox/certs/sandbox_ca.pem
MESH_CLIENT_CERT_PATH=sandbox/certs/sandbox_client.pem
MESH_CLIENT_KEY_PATH=sandbox/certs/sandbox_client.key
```

There is no special-case skip for sandbox — the mTLS code path is exercised
exactly as it will be in production. The only thing that differs across
environments is the *contents* of the three cert files.

## State and persistence

The mesh-sandbox container uses a file-backed store at `/tmp/mesh_store`
inside the container. `docker compose down` wipes the container which
wipes the store — a clean slate per dev session is typically more useful
than persistence for the work we're doing here.

If you need persistence across `docker compose down` cycles, add a named
volume in `docker-compose.yml` mounting to `/tmp/mesh_store` on the
`mesh_sandbox` service.

## Bumping the sandbox version

Edit the `refs/tags/v1.0.54` in `docker-compose.yml`. Releases are at
<https://github.com/NHSDigital/mesh-sandbox/releases>. Re-run
`docker compose up --build -d` to rebuild.

Sandbox behaviour can change between releases — bump deliberately, not
casually.

## Troubleshooting

- **`curl -k https://localhost:8700/health` returns HTTP 400 "No required SSL certificate was sent" from nginx.** Correct: the nginx layer rejects connections that do not
  present a valid client cert. Use the certs as shown in `make sandbox-check`.

- **nginx exits immediately after start.** Run `docker compose logs nginx`.
  The most common cause is a missing cert file under `sandbox/certs/`.
  Run `bash sandbox/certs/generate.sh` and restart.

- **Worker logs "could not load PEM client certificate" or "no such file or
  directory" at startup.** The env vars `MESH_CLIENT_CERT_PATH` or
  `MESH_CLIENT_KEY_PATH` point at a path that does not exist. The worker
  fail-fasts before reaching the handshake — see `mesh_worker_main.py`.

- **Restarted mesh_sandbox but requests still time out via nginx.** nginx
  resolves the upstream service name at startup and caches the IP. If the
  mesh_sandbox container is recreated, restart nginx too: `make sandbox-down
  && make sandbox-up`.

- **`make sandbox-up` succeeds but `make sandbox-check` returns nothing or
  hangs.** Check `docker compose ps`; both `mesh_sandbox` and `nginx`
  should be running. nginx depends on `mesh_sandbox` being healthy, which
  takes a few seconds after `up`. If `mesh_sandbox` is healthy but
  `nginx` is not started, the depends_on condition has not yet fired —
  wait or restart.
