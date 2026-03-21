# ---------------------------------------------------------------------------
# Test targets
#
# Unit tests (no database required):
#     make test
#
# Integration tests (requires TEST_DATABASE_URL in .env):
#     make test-integration
#
# All tests:
#     make test-all
#
# Migrations against test database:
#     make migrate-test
# ---------------------------------------------------------------------------

include .env
export

.PHONY: test test-integration test-all migrate-test

test:
	python -m pytest tests/ --ignore=tests/test_form_routes.py -v

test-integration:
	python -m pytest tests/test_form_routes.py -v

test-all:
	python -m pytest tests/ -v

migrate-test:
	DATABASE_URL=$(TEST_DATABASE_URL) python -m alembic upgrade head