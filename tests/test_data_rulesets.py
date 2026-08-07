"""
Database-free equivalent of the ruleset-validation phase of application
startup (app/core/wiring.py:build_container, before any repository is
constructed).

This is the only check that runs against the real data/ tree on a
rulesets-only PR: main.py's build_container() call is only exercised by
tests/test_form_routes.py, which skips itself entirely when
TEST_DATABASE_URL is unset. No integration marker -- this is a unit test.
"""

from pathlib import Path

import pytest

from app.core.condition_registry import ConditionRegistry
from app.core.wiring import validate_rulesets

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Condition ids that other tests hardcode and depend on. If you rename or
# delete one of these rulesets, update the dependant test in the same PR --
# it will not otherwise fail on a rulesets-only PR, since integration tests
# don't run on those PRs.
_PINNED_CONDITION_IDS = {
    # tests/test_form_routes.py: NUMERIC_DEMO_CONDITION_ID and the quantity
    # boundary tests, which also depend on its patient_weight_kg answer key.
    "numeric_capability_demo",
}


@pytest.fixture(scope="module")
def registry() -> ConditionRegistry:
    return ConditionRegistry(str(DATA_DIR))


def test_every_committed_ruleset_loads_and_validates(registry: ConditionRegistry) -> None:
    validate_rulesets(registry)


def test_registry_discovers_every_json_file_on_disk(registry: ConditionRegistry) -> None:
    # data/synthetic/ holds offline encoder training data (fragment
    # libraries, manifest.json), not clinical rulesets, and is excluded by
    # the registry -- see app/core/condition_registry.py::_load_all.
    json_file_count = sum(
        1
        for path in DATA_DIR.rglob("*.json")
        if "synthetic" not in path.relative_to(DATA_DIR).parts[:-1]
    )
    assert json_file_count == len(registry.list_conditions())


def test_condition_ids_pinned_by_other_tests_still_exist(registry: ConditionRegistry) -> None:
    known_ids = {condition["id"] for condition in registry.list_conditions()}
    missing = _PINNED_CONDITION_IDS - known_ids
    assert not missing, (
        f"Pinned condition id(s) {missing} are referenced by an integration test "
        "that does not run on rulesets-only PRs. If you renamed or deleted the "
        "ruleset, update that test (and this file's _PINNED_CONDITION_IDS) in "
        "the same PR."
    )
