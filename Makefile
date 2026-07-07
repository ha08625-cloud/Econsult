# ---------------------------------------------------------------------------
# Test targets
#
# Unit tests — Python (no database) + frontend Vitest:
#     make test
#
# Integration tests — Python only (requires TEST_DATABASE_URL in .env):
#     make test-integration
#
# All tests — Python unit + frontend Vitest + Python integration:
#     make test-all
#
# Lint and format check — Python only, no database:
#     make lint
#
# One-time setup so ruff runs automatically on every commit:
#     make hooks-install
#
# Migrations against test database:
#     make migrate-test
#
# Integration test files are identified by @pytest.mark.integration.
# When adding a new integration test file, add the pytestmark line —
# no changes to this Makefile or ci.yml are needed.
# ---------------------------------------------------------------------------
#
# MESH sandbox targets (local development only — see sandbox/README.md)
#
# Start the local MESH sandbox:
#     make sandbox-up
#
# Verify it is running:
#     make sandbox-check
#
# Stop and remove:
#     make sandbox-down
#
# The sandbox is never deployed to Railway or used in CI.
# ---------------------------------------------------------------------------

include .env
export

.PHONY: test test-integration test-all lint hooks-install migrate-test seed-test-db sandbox-up sandbox-down sandbox-check

test:
	python -m pytest tests/ -m "not integration" -v
	cd frontend && npx vitest run

lint:
	ruff check .
	ruff format --check .

hooks-install:
	pre-commit install

seed-test-db:
	DATABASE_URL=$(TEST_DATABASE_URL) \
	PRACTICE_EMAIL=test@example.com \
	PRACTICE_NAME="Test Practice" \
	ADMIN_URL=http://localhost/admin \
	python scripts/create_admin_user.py test-admin@example.com --create-practice

test-integration: seed-test-db
	python -m pytest tests/ -m integration -v

test-all:
	python -m pytest tests/ -m "not integration" -v
	cd frontend && npx vitest run
	$(MAKE) test-integration

migrate-test:
	DATABASE_URL=$(TEST_DATABASE_URL) python -m alembic upgrade head

sandbox-up:
	cd sandbox && docker compose up -d

sandbox-down:
	cd sandbox && docker compose down

sandbox-check:
	@echo "Expect: a successful mTLS handshake and a JSON health response."
	curl --cacert sandbox/certs/sandbox_ca.pem \
	     --cert   sandbox/certs/sandbox_client.pem \
	     --key    sandbox/certs/sandbox_client.key \
	     https://localhost:8700/health