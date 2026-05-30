# Sandbox dev PKI

This directory contains an intentionally committed throwaway PKI used by the
MESH sandbox in `sandbox/docker-compose.yml`.

## What's here

- `generate.sh` — idempotent OpenSSL script that creates everything below
- `sandbox_ca.pem` / `sandbox_ca.key` — local-only root CA
- `sandbox_server.pem` / `sandbox_server.key` — server cert used by the nginx mTLS proxy
- `sandbox_client.pem` / `sandbox_client.key` — client cert used by workers and curl

The cert files do not exist in a fresh checkout. Run the script once to
generate them:

    bash sandbox/certs/generate.sh

After generation they are committed alongside the script.

## Why these private keys are committed

These keys are throwaways. The CA that signed them exists only inside this
repo. The only place they are trusted is by the nginx config inside
`sandbox/docker-compose.yml`, which never runs outside local development.
Committing them removes per-developer setup friction and makes the dev
environment deterministic across machines and CI checkouts.

There is no security implication to committing them. An attacker who
obtains them can impersonate a worker against a locally-running sandbox on
the same host — which is something they already could do, because they
already have shell access.

## What must NEVER be committed here

Real NHS production certs. Real NHS PTL/integration certs. Anything signed
by a real CA. These are operational secrets that live as Railway secrets
and are mounted as files at worker startup time. The runtime file paths
are configured via the env vars `MESH_CA_CERT_PATH`,
`MESH_CLIENT_CERT_PATH`, and `MESH_CLIENT_KEY_PATH` — not via this
directory.

If you are tempted to put a real cert here for any reason, stop. Talk to
the operator about the right path through Railway secrets.

## Regenerating

The script is idempotent — running it twice does nothing the second time:

    bash sandbox/certs/generate.sh

To regenerate from scratch (e.g. CA expired at some far future point):

    bash sandbox/certs/generate.sh --force

After regenerating, restart the sandbox so nginx picks up the new server
cert:

    make sandbox-down && make sandbox-up

Any worker process holding a `MeshClient` instance must also be restarted
so the new client cert is picked up.

## Cert details

All certs use RSA-2048 and a 10-year validity. Subjects:

- CA: `CN=econsult-sandbox-ca`
- Server: `CN=localhost`, SAN: `DNS:localhost, IP:127.0.0.1`
- Client: `CN=econsult-worker`