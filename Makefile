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
# Notes on ignored files in make test:
#   test_form_routes.py                    — integration, requires TEST_DATABASE_URL
#   test_public_routes.py                  — integration, imports main.py (triggers alembic_upgrade)
#   test_repositories.py                   — integration, calls alembic_upgrade() at module level;
#                                            run directly as: python -m tests.test_repositories
#   test_pipeline_repositories.py          — integration, requires TEST_DATABASE_URL
# ---------------------------------------------------------------------------

include .env
export

.PHONY: test test-integration test-all migrate-test

test:
	python -m pytest tests/ \
		--ignore=tests/test_form_routes.py \
		--ignore=tests/test_public_routes.py \
		--ignore=tests/test_repositories.py \
		--ignore=tests/test_pipeline_repositories.py \
		-v
	cd frontend && npx vitest run

test-integration:
	python -m pytest \
		tests/test_form_routes.py \
		tests/test_public_routes.py \
		tests/test_pipeline_repositories.py \
		-v

test-all:
	python -m pytest tests/ \
		--ignore=tests/test_form_routes.py \
		--ignore=tests/test_public_routes.py \
		--ignore=tests/test_repositories.py \
		--ignore=tests/test_pipeline_repositories.py \
		-v
	cd frontend && npx vitest run
	python -m pytest \
		tests/test_form_routes.py \
		tests/test_public_routes.py \
		tests/test_pipeline_repositories.py \
		-v

migrate-test:
	DATABASE_URL=$(TEST_DATABASE_URL) python -m alembic upgrade head
