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
# Migrations against test database:
#     make migrate-test
#
# Integration test files are identified by @pytest.mark.integration.
# When adding a new integration test file, add the pytestmark line —
# no changes to this Makefile or ci.yml are needed.
# ---------------------------------------------------------------------------

include .env
export

.PHONY: test test-integration test-all migrate-test

test:
	python -m pytest tests/ -m "not integration" -v
	cd frontend && npx vitest run

test-integration:
	python -m pytest tests/ -m integration -v

test-all:
	python -m pytest tests/ -m "not integration" -v
	cd frontend && npx vitest run
	python -m pytest tests/ -m integration -v

migrate-test:
	DATABASE_URL=$(TEST_DATABASE_URL) python -m alembic upgrade head