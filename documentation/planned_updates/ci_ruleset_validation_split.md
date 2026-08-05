# Implementation Plan: Split ruleset validation into its own CI path

## Plan

Ruleset-authoring PRs touch nothing but JSON under `data/`, yet they currently run the full CI
matrix: ruff, the entire Python unit suite, an npm install, `tsc --noEmit`, Vitest, plus a second
job that spins up Postgres, runs Alembic migrations and seeds a database. None of that work can
detect a bad ruleset any faster than a single 30-line check can.

Worse, the check that actually matters is currently the *slowest* one. Nothing in the repository
validates the real committed files in `data/` except `main.py` calling `build_container()` at import
time, which is only exercised by `tests/test_form_routes.py` — a module that `pytest.skip`s itself
entirely when `TEST_DATABASE_URL` is unset. So today, a malformed ruleset is caught only by the
Postgres-gated integration job.

This plan adds one small test that validates the real `data/` directory without a database, and
gives it a dedicated CI job gated on a `data/**` path filter. JSON-only PRs then run that job alone;
Python PRs run `unit` + `integration` as they do today; PRs touching both run everything.

Three tasks. No files are moved or deleted, no production code changes.

---

## Scope

**In scope**

- New: `tests/test_data_rulesets.py` — validates the real `data/` tree, no database
- `.github/workflows/tests.yml` — a `rulesets` path filter and a third job
- `documentation/arch_testing.md` — new file row, CI job description

**Out of scope**

- **Moving or deleting `tests/test_ruleset.py`.** The provisional plan proposed relocating its 594
  lines into a new file. That work buys nothing: every test in it builds its ruleset from an in-test
  dict, so a change to `data/*.json` cannot break any of them. Relocating them would not add one bit
  of coverage to a JSON-only PR. See design decision 1.
- **Moving the three `build_container` tests out of `tests/test_wiring.py`** (lines 186–231). Same
  reason — they write synthetic rulesets to `tmp_path`. They also sit under a docstring (lines 14–19)
  that explains why the ruleset-validation phase is unit-testable there while the DB phase is not;
  splitting them orphans that explanation.
- Any change to `.github/workflows/security-scan.yml`.
- Any change to the `Makefile`. The new test is an ordinary unmarked unit test, so `make test` picks
  it up with no target changes.

---

## Design Decisions

**1. Add a test; do not reorganise the existing ones.**
The goal is coverage for JSON-only PRs. The existing ruleset tests are synthetic and cannot fail on a
JSON-only diff, so they are irrelevant to that goal. A new file is the entire delta.

**2. The new file targets the real `data/` tree, and nothing else.**
It does what `main.py` does — `ConditionRegistry(data_dir)` then `validate_rulesets(registry)` — and
stops there. `build_container` runs ruleset validation at `app/core/wiring.py:189`, before the first
repository is constructed at line 191, so this reproduces the startup contract with no database.

**3. The new file carries no `integration` marker.**
It therefore runs inside `make test` and inside the CI `unit` job (`pytest tests/ -m "not
integration"`) as well as in the new job. Code PRs keep the coverage they have; JSON PRs gain it. The
duplication is free — the test reads ~30 small JSON files.

**4. CI targets the new file by path, not by a pytest marker.**
`python -m pytest tests/test_data_rulesets.py` is one legible line in the workflow. A marker would
need a new entry in `pytest.ini` and a deselect expression in the `unit` job to avoid double-running,
for no benefit.

**5. The path filter is `data/**`, not `data/**/*.json`.**
Whether `data/**/*.json` matches a top-level file like `data/general.json` depends on picomatch's
zero-segment `**` behaviour — probably yes, but there is no reason to depend on it. `data/` holds
rulesets and the `data/synthetic/*.jsonl` encoder fixtures, and no Python test reads the `.jsonl`
files, so treating the whole directory as "rulesets" is correct.

**6. Two independent jobs, each on its own filter — not an if/else.**
A PR touching both `.py` and `.json` must run both paths. Gating each job on its own boolean gives
that for free.

**7. The new test pins the condition ids that other tests depend on.**
`tests/test_form_routes.py:914` hardcodes `NUMERIC_DEMO_CONDITION_ID = "numeric_capability_demo"`.
Today, deleting or renaming that ruleset breaks the integration job. After this change, a JSON-only
PR that deletes it would skip integration entirely and merge green. Asserting the pinned ids exist
closes that hole in three lines.

**8. No ruff in the new job.**
ruff does not lint JSON. The `unit` job still lints every Python file on any Python change.

**9. Skipped jobs and branch protection are already safe.**
GitHub treats a job skipped by an `if:` condition as passing for required status checks. That is how
doc-only PRs already pass today (see the comment at `.github/workflows/tests.yml:14-20`). Adding a
third job with the same shape introduces no new risk in either direction: a JSON-only PR skips
`unit`/`integration`, a Python-only PR skips `ruleset-validation`, and both are green.

---

## Task 1: Add `tests/test_data_rulesets.py`

**A. State of the world:** Nothing yet. No test validates the real files in `data/` outside the
Postgres-gated `tests/test_form_routes.py`. `tests/test_ruleset.py` and `tests/test_wiring.py` are
untouched by this plan and stay exactly where they are.

**B. Files:**

- New: `tests/test_data_rulesets.py` — the only deliverable for this task.

**C. Instructions:**

Create the file with a module docstring explaining what it guards: this is the fast, database-free
equivalent of the ruleset-validation phase of application startup, and it is the only check that runs
on a rulesets-only PR. Do **not** add `pytestmark = pytest.mark.integration` — it is a unit test.

Resolve the data directory the same way `app/core/settings.py` resolves its default (`<project
root>/data`), from `__file__` rather than from an environment variable, so the test validates the
committed tree regardless of any `DATA_DIR` set in the environment:

```python
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
```

Write these tests:

1. **`test_every_committed_ruleset_loads_and_validates`** — construct
   `ConditionRegistry(str(DATA_DIR))` and pass it to `validate_rulesets` (both imported from
   `app.core.condition_registry` and `app.core.wiring` respectively). Assert nothing raises. This is
   the load-bearing test: registry construction already rejects a missing/invalid `condition_id`, a
   duplicate `condition_id`, a malformed presentation block and out-of-bounds `search_tags`, and
   `validate_rulesets` then runs `load_ruleset` over every file, which is where question,
   `answer_type`, quantity, `pdf_label` and safety-key validation happens.

2. **`test_registry_discovers_every_json_file_on_disk`** — count `.json` files under `DATA_DIR`
   recursively (`DATA_DIR.rglob("*.json")`) and assert it equals `len(registry.list_conditions())`.
   Guards against a file silently not being walked. Note `ConditionRegistry._load_all` uses
   `os.walk` and matches on the `.json` suffix, so the two counts must agree exactly; the
   `data/synthetic/` fixtures are `.jsonl` and correctly excluded by both.

3. **`test_condition_ids_pinned_by_other_tests_still_exist`** — assert that every id in a
   module-level `_PINNED_CONDITION_IDS` frozenset appears in the registry. Seed it with
   `"numeric_capability_demo"` and a comment naming the dependant
   (`tests/test_form_routes.py`, the quantity boundary tests, which also depend on its
   `patient_weight_kg` answer key). Write the failure message so it tells the author what to do:
   the ruleset is referenced by an integration test that does not run on rulesets-only PRs, so
   renaming or deleting it means updating that test in the same PR.

Use a module-scoped fixture for the registry so it is built once for all three tests.

`ruff` runs with `line-length = 100` (see `pyproject.toml`); run `ruff format` on the new file before
committing.

**Verification:** `python -m pytest tests/test_data_rulesets.py -v` — no database, no env vars
required. Then sanity-check it actually bites: temporarily break a safety-rule `answer_key` reference
in any file under `data/`, confirm test 1 fails naming that condition, and revert.

---

## Task 2: CI workflow changes

**A. State of the world:** Task 1 is complete; `tests/test_data_rulesets.py` exists and passes.
`.github/workflows/tests.yml` has a `changes` job producing a single `code` output (`'**'` minus
`'!**/*.md'`) that gates both `unit` and `integration`.

**B. Files:**

- `.github/workflows/tests.yml` — the only deliverable.

**C. Instructions:**

1. In the `changes` job, add `rulesets` to `outputs` alongside `code`, and add the filter:

   ```yaml
   filters: |
     code:
       - '**'
       - '!**/*.md'
       - '!data/**'
     rulesets:
       - 'data/**'
   ```

   Order matters in `dorny/paths-filter`: last match wins, so the negations must follow `'**'`.

2. Update the comment block above the `changes` job (currently lines 14–20). It says the job
   "detects whether anything other than markdown docs changed", which stops being true. Rewrite it to
   describe the three-way split, and keep the existing note about skipped jobs still reporting a
   status for branch protection.

3. Add a third job, placed after `changes` and before `unit`:

   ```yaml
   ruleset-validation:
     name: Ruleset validation
     needs: changes
     if: needs.changes.outputs.rulesets == 'true'
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v7
       - name: Set up Python
         uses: actions/setup-python@v7
         with:
           python-version: "3.12"
       - name: Install Python dependencies
         run: pip install -r requirements.txt pytest
       - name: Validate committed rulesets
         run: python -m pytest tests/test_data_rulesets.py -v
   ```

   Match the `integration` job's dependency line (`requirements.txt` only, no
   `requirements-dev.txt`) — the new test needs pytest and the app's own imports, not ruff. If the
   test fails to import in CI but passes locally, that is the likely cause; add
   `-r requirements-dev.txt` rather than guessing.

   No `services:`, no environment variables, no Node steps.

4. Leave the `if:` conditions on `unit` and `integration` as they are — they already read
   `needs.changes.outputs.code == 'true'`, and the filter change alone narrows them.

**Verification:** cannot be checked locally. Confirm on the PR itself: the PR for this plan touches
`.github/` and `documentation/` but no `data/` file, so `ruleset-validation` should appear as
**skipped** and `unit`/`integration` should run. To prove the other direction before relying on it,
push a throwaway whitespace-only change to any file in `data/` on a scratch branch and confirm
`ruleset-validation` runs alone.

---

## Task 3: Documentation

**A. State of the world:** Tasks 1 and 2 are complete. `documentation/arch_testing.md` does not know
about the new test file or the third CI job, and one of its statements is now conditionally wrong.

**B. Files:**

- `documentation/arch_testing.md` — the only deliverable.

**C. Instructions:**

1. Add a row to the Python unit tests table (the one containing the `test_ruleset.py` and
   `test_wiring.py` rows, around lines 110–136) for `test_data_rulesets.py`. Cover what it asserts
   and, importantly, *why it exists separately from `test_ruleset.py`*: `test_ruleset.py` validates
   the schema rules against synthetic fixtures, `test_data_rulesets.py` validates the real committed
   files against those rules. Note that it is the sole gate on a rulesets-only PR.

2. Amend the statement at line 74 — "No changes to `Makefile` or `ci.yml` are needed when adding a
   new integration test file" — which remains true for integration tests but now sits alongside a
   workflow that does dispatch on paths. Add a short subsection describing the three CI jobs and
   their path filters, so the next person to add a job knows the pattern.

3. Add a line to the pinned-condition-id story: `data/numeric_capability_demo.json` is referenced by
   name from `tests/test_form_routes.py` and is now asserted to exist by `test_data_rulesets.py`.

Keep to the document's existing table style and register. Do not restate anything already legible
from the test file itself.

---

## Task 4: Branch protection (manual, outside the repository)

Not a code change — flagged so it is not missed.

If `Unit tests` and/or `Integration tests` are configured as required status checks in GitHub branch
protection, decide whether to add `Ruleset validation` to that list. Per design decision 9 it is safe
either way: skipped jobs count as passing, so requiring it will not block Python-only PRs, and
leaving it optional will not block anything. Requiring it is the stronger choice — without it, a
rulesets-only PR has no required check that actually inspects the rulesets.

This setting is not visible from a Claude Code session; it must be changed in the repository
settings on github.com.
