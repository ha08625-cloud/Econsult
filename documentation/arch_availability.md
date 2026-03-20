# Practice Availability & Scheduling

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the availability domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Controls when the patient-facing form is open or closed. Evaluates the current time against a configured schedule and returns a result consumed by both `GET /availability` and `POST /form/init`.

**Key files:** `availability_service.py`, `availability_repository.py`, `availability_models.py`, `availability_orchestration.py`

---

## Core Principle: Fail-Open

**Any failure in the availability system must never prevent a patient from accessing the form.** This applies at every boundary:

- `GET /availability`: non-200 response → frontend shows form as normal, no banner
- `POST /form/init`: availability check is wrapped in try/except; any exception is logged and the request proceeds as open
- `POST /form/update` and `POST /form/finish`: do NOT check availability. A patient halfway through a form must not have their work discarded if the practice closes mid-session.
- `submitted_after_hours` flag on `POST /form/finish`: if the check fails, defaults to `false`. Uncertainty must not alarm the patient.

---

## Module Responsibilities

### `availability_models.py`
Data shapes only. No logic, no IO. Contains `AvailabilityConfig`, `AvailabilityResult`, and `AvailabilityException`. Read this file for field names and types.

### `availability_repository.py`
Database access only. No validation logic. Must not import from `availability_service`. The caller is always responsible for validating before calling write methods.

### `availability_service.py`
Pure logic. No database access, no IO. Fully testable without a database. The only project import allowed is `availability_models`. Contains all validation functions and `evaluate_availability`.

---

## Design Decisions

### `is_active = false`
The practice has not opted in to schedule enforcement. `evaluate_availability` returns open immediately with null messages. This is the default state. The form behaves as if availability does not exist.

### Evaluation Order
Override → Per-date exception → Weekly schedule. An active override always wins, including over an exception on the same date. This is intentional — if an admin sets a force-open override during a bank holiday exception, the override wins.

### Overnight Hours Not Supported
`open_time < close_time` is a hard domain constraint. An overnight service implies urgent/out-of-hours clinical logic that is out of scope. Reversed time ranges are rejected explicitly at validation; they would otherwise silently never match.

### Timezone Handling
All evaluation converts UTC to `Europe/London` via `zoneinfo`. The `tzdata` package is in `requirements.txt` to ensure reliable timezone data on the Railway container. `open_time` and `close_time` are stored as Postgres `TIME` columns and always interpreted in Europe/London local time. Exception date lookup uses the London date, not UTC — using UTC would miss midnight-boundary exceptions.

### Override Expiry
`override_expires_at` is always required. Null is not permitted. Expiry is strictly less-than: at exactly `override_expires_at` the override is no longer active. A passed expiry falls through to the weekly schedule silently — no error, no alert.

Timezone-aware `expires_at` is required. A naive datetime submitted during BST would be stored as UTC and expire one hour late. The backend rejects naive values with HTTP 400.

### Override Message Fallback Chain
Force-closed override: use `override_message` if not None (including empty string `""`), else fall back to `closed_message`. The explicit `is None` check is intentional — an empty string is a valid configured message, not absent.

### Auto-Clear on Deactivation
Setting `is_active = false` auto-clears any existing override (all three override columns set to NULL). This prevents a stale override from silently re-activating if the admin later re-enables `is_active`. Logic is split: `deactivation_clears_override()` in the service returns a boolean; the admin router calls `clear_override` on the repository when true.

### After-Hours Notice
When the practice is open and `is_active` is true, an after-hours notice is constructed from `close_time`. During a `custom_hours` exception, the notice uses the exception's `close_time`, not the config's — it reflects the actual closing time for that day. During a `closed` exception or when `is_active` is false, `after_hours_notice` is null.

### `check_availability` Orchestration
`check_availability(availability_repo, practice_id, now_utc)` is defined in `app/services/availability_orchestration.py`. It owns the full pipeline: fetch config → compute today's London date → fetch exceptions → call `evaluate_availability`. It does not belong in `availability_service` because the service has no database access. `GET /availability` (via `public_router.py`) and `POST /form/init` and `POST /form/finish` (via `main.py`) all call this function. The fail-open try/except wrapping lives in the callers, not in `check_availability` itself — exceptions propagate so callers can log them with appropriate context.

### Exception Note Field
The `note` field on exceptions is for admin reference only (e.g. "Bank holiday"). It is not shown to patients and plays no role in evaluation.

### Admin Endpoints
Admin reads and writes raw config only. `GET /admin/availability` does not call `evaluate_availability`. See `admin_router.py` for endpoint details.

### Startup Guarantee
`init_availability()` is called at startup after the practice row exists. There is never a state post-startup where the availability row does not exist.

### Database Schema
See migration files `0002_availability_table.py`, `0003_availability_override.py`, `0004_availability_exceptions.py` for the definitive schema. The `weekly_open_days` column has a Postgres `<@` CHECK constraint as a backstop; application-layer validation in `availability_service` runs first and produces a better error message.

---

## Banned Imports

- `availability_service` must NOT import any repository, IO, or clinical engine module
- `availability_repository` must NOT import `availability_service`
- `availability_models` must NOT import any service or repository module
- Clinical engine modules (`form_logic`, `safety_engine`, `encoder_mapping`, `projection`, `serialisation`) must NOT import any availability module — the clinical engine has no awareness of practice scheduling

---

## Tests

Unit tests for `availability_service.py`: `tests/test_availability_service.py`

Tests cover: schedule evaluation, config validation, fail-open pattern, force-open/closed overrides, override message fallback, expired override fallthrough, timezone-naive rejection, `is_active=false` ignoring overrides, auto-clear on deactivation, BST offset effects, exact time boundaries, per-date exceptions (closed and custom_hours), evaluation priority order.

Run with: `python -m tests.test_availability_service`