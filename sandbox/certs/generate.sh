#!/usr/bin/env bash
# Generate the local dev mTLS PKI for the MESH sandbox.
#
# Outputs (committed to git):
#   sandbox_ca.pem      - throwaway dev CA cert
#   sandbox_ca.key      - throwaway dev CA private key
#   sandbox_server.pem  - server cert signed by CA, SAN: localhost, 127.0.0.1
#   sandbox_server.key  - server private key
#   sandbox_client.pem  - client cert signed by CA, CN: econsult-worker
#   sandbox_client.key  - client private key
#
# These are intentionally committed. See sandbox/certs/README.md for why.
# NEVER use this script for production certs.
#
# Usage:
#   bash sandbox/certs/generate.sh           # idempotent: skip if files exist
#   bash sandbox/certs/generate.sh --force   # regenerate from scratch

set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$CERT_DIR"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
    FORCE=1
fi

# Returns 0 (yes, regenerate) or 1 (no, skip).
needs_regen() {
    local path="$1"
    if [[ -f "$path" && "$FORCE" -eq 0 ]]; then
        return 1
    fi
    return 0
}

# ---------- CA ----------
if needs_regen sandbox_ca.pem; then
    echo "Generating CA..."
    openssl genrsa -out sandbox_ca.key 2048 2>/dev/null
    openssl req -new -x509 -days 3650 \
        -key sandbox_ca.key \
        -out sandbox_ca.pem \
        -subj "/CN=econsult-sandbox-ca" 2>/dev/null
    chmod 600 sandbox_ca.key
else
    echo "exists, skipping: sandbox_ca.pem (use --force to regenerate)"
fi

# ---------- server ----------
if needs_regen sandbox_server.pem; then
    echo "Generating server cert..."
    openssl genrsa -out sandbox_server.key 2048 2>/dev/null
    openssl req -new \
        -key sandbox_server.key \
        -out sandbox_server.csr \
        -subj "/CN=localhost" 2>/dev/null

    cat > sandbox_server.ext <<'EOF'
subjectAltName = DNS:localhost,IP:127.0.0.1
EOF

    openssl x509 -req \
        -in sandbox_server.csr \
        -CA sandbox_ca.pem \
        -CAkey sandbox_ca.key \
        -CAcreateserial \
        -days 3650 \
        -extfile sandbox_server.ext \
        -out sandbox_server.pem 2>/dev/null

    chmod 600 sandbox_server.key
    rm -f sandbox_server.csr sandbox_server.ext
else
    echo "exists, skipping: sandbox_server.pem (use --force to regenerate)"
fi

# ---------- client ----------
if needs_regen sandbox_client.pem; then
    echo "Generating client cert..."
    openssl genrsa -out sandbox_client.key 2048 2>/dev/null
    openssl req -new \
        -key sandbox_client.key \
        -out sandbox_client.csr \
        -subj "/CN=econsult-worker" 2>/dev/null

    openssl x509 -req \
        -in sandbox_client.csr \
        -CA sandbox_ca.pem \
        -CAkey sandbox_ca.key \
        -CAcreateserial \
        -days 3650 \
        -out sandbox_client.pem 2>/dev/null

    chmod 600 sandbox_client.key
    rm -f sandbox_client.csr
else
    echo "exists, skipping: sandbox_client.pem (use --force to regenerate)"
fi

# Cleanup CA serial state (CAcreateserial recreates it on demand).
rm -f sandbox_ca.srl

echo ""
echo "PKI ready in $CERT_DIR"
ls -la *.pem *.key 2>/dev/null