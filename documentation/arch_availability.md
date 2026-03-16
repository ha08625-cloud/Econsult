## Availability enforcement

### 1. Overview

The availability system controls when the patient-facing form is open or closed. It evaluates the current time against the practice's configured schedule and returns a result that the frontend and form init endpoint both consume.

The system is designed around a single principle: a failure in the availability system must never prevent a patient from accessing the form. Every failure path defaults to open.

### 2. Module responsibilities

#### availability_models.py (app/models/)

Data shapes only. No logic, no IO.

AvailabilityConfig: represents the stored row from practice_availability.
Constructed via `from_row(dict)` from the repository output. Includes
three optional override fields (override_status, override_expires_at,
override_message) added in Stage 3, all defaulting to None.

AvailabilityResult: the return type of `evaluate_availability()`. Contains
`is_open`, `closed_message`, and `after_hours_notice`. Both `GET /availability`
and the availability check inside `POST /form/init` consume this type.

`AvailabilityException`: represents a single row from the
`practice_availability_exceptions` table. Fields: `practice_id`,
`exception_date` (date), `exception_type` ("closed" or "custom_hours"),
`open_time` (optional time), `close_time` (optional time), `note`
(optional string). Has a `from_row(dict)` classmethod for construction
from a database row.

#### availability_repository.py (app/repositories/)

Database access only. No validation logic. No imports from service modules.

Methods:
- `init_availability(practice_id)`: inserts a default row using
  `INSERT ... ON CONFLICT DO NOTHING`. Called once at startup after the
  practice row exists.
- `get_availability(practice_id)`: returns all columns (including
  override columns) as a dict. Raises `ValueError` if the row does not
  exist.
- `set_availability(...)`: upserts the schedule config. No validation —
  the caller is responsible for calling `validate_availability_config()`
  first.
- `set_override(practice_id, override_status, override_expires_at,
  override_message)`: updates the three override columns. The caller
  is responsible for calling `validate_override()` first.
- `clear_override(practice_id)`: sets all three override columns to
  NULL. Idempotent — no error if no override was active.

- `get_exceptions(practice_id, from_date)`: returns all exception rows
  on or after `from_date`, ordered by date ascending. Used both by the
  evaluation path (which checks only today's exception) and by
  `GET /admin/availability/exceptions` (which displays all upcoming
  exceptions to the admin).
- `set_exception(practice_id, exception_date, exception_type, open_time,
  close_time, note)`: upserts a single exception row. No validation —
  the caller is responsible for calling `validate_exception()` first.
- `delete_exception(practice_id, exception_date)`: deletes a single
  exception row. Idempotent — no error if the row does not exist.

#### availability_service.py (app/services/)

Pure logic. No database access. No imports from any project module except
`app.models.availability_models`. Fully testable without a database.

`validate_availability_config()`: raises `ValueError` if `weekly_open_days`
contains invalid values or `open_time == close_time`. Does not validate
`open_time < close_time` (reversed times are a self-evident data entry
error given the domain constraint against overnight hours). Does not
validate empty `weekly_open_days` (that is a UI concern only).

`validate_override(status, expires_at, now_utc)`: raises `ValueError` if
status is not "open"/"closed", expires_at is null or timezone-naive,
expires_at is not in the future, or expires_at exceeds 24 hours from now.
The valid window is: now_utc < expires_at <= now_utc + 24 hours.

`deactivation_clears_override(is_active)`: returns True when is_active
is false, signalling that overrides should be cleared on deactivation.
The admin router calls this after PUT /admin/availability and, if true,
calls clear_override on the repository.

`validate_exception(exception_type, open_time, close_time)`: raises
`ValueError` if exception_type is not "closed"/"custom_hours"; if
custom_hours and either time is null; if closed and either time is not
null; if open_time == close_time; or if open_time >= close_time
(overnight hours are not supported — a reversed range would silently
never match any time in the evaluation logic, so this is rejected
explicitly).

`evaluate_availability(config, now_utc, exceptions=None)`: the
`exceptions` parameter defaults to `None`. Inside the function body,
`None` is replaced with an empty list. This avoids the mutable default
argument trap. The signature is backwards-compatible — existing callers
from Stage 3 continue to work without modification. Evaluation order is:
(1) is_active false: return open with no messages.
(2) Active override (override_status not null and expires_at > now_utc):
force-open returns open with after-hours notice; force-closed returns
closed with override_message (falling back to closed_message via
explicit is-not-None check).
(3) Per-date exception for today (Europe/London date): if exception_type
is "closed", return closed with config closed_message; if "custom_hours",
evaluate exception open_time/close_time against current London time.
After-hours notice is constructed from the exception's close_time for
custom_hours, or null for closed exceptions.
(4) Weekly schedule: converts UTC to Europe/London, checks day and time.

Dependency rules:
- availability_service must NOT import any repository module
- availability_service must NOT import any clinical engine module
- availability_service must NOT perform any IO

### 3. Fail-open design

The fail-open principle applies at every boundary:

`GET /availability`: if the database raises an exception, the exception
propagates and FastAPI returns HTTP 500. The frontend treats any non-200
response as fail-open and shows the form as normal.

`POST /form/init`: the availability check is wrapped in a try/except. If
any exception is raised during the check, it is logged and the request
proceeds as if the practice is open. If the check succeeds and the
practice is closed, the endpoint returns HTTP 503 with the closed message.

`POST /form/update` and `POST /form/finish`: these do not check
availability. Once a patient has been granted a session via `POST /form/init`,
they can complete and submit the form regardless of whether the practice
has since closed. This is the humane choice — a patient halfway through
a form should not have their work discarded.

`POST /form/finish` now returns a `submitted_after_hours` boolean. After
the existing finish logic completes, `check_availability` is called in a
try/except. If the result's `is_open` is false, `submitted_after_hours`
is true. If the check fails or the result is open,
`submitted_after_hours` is false. Uncertainty must not alarm the patient.
The response shape is: `{"submission_id": "...", "submitted_after_hours": true|false}`.

Frontend availability fetch failure: if `GET /availability` fails for any
reason (network error, any non-200 response including 500), the frontend
shows the form as normal with no closed message banner and no after-hours
notice.

### 4. is_active = false behaviour

When `is_active` is false, the practice has not opted in to schedule
enforcement. `GET /availability` returns `is_open: true` with null
messages. The form behaves as if availability does not exist. This is the
default state after `init_availability()` inserts the default row.

### 5. After-hours notice

When the practice is open and `is_active` is true, the service constructs
a notice string from the config's `close_time`: "Please note: forms
submitted after [HH:MM] will be reviewed on the next working day." The
time is formatted in 24-hour notation, the standard convention for UK
NHS systems. When the practice is closed, `is_active` is false, or there
is no meaningful close time to reference, `after_hours_notice` is null.

When a per-date exception with custom_hours is active and the practice
is open, the after-hours notice is constructed from the exception's
close_time, not the config's close_time. This reflects the actual
closing time for that day. When a per-date exception with type "closed"
is active, after_hours_notice is null (the practice is closed all day).

### 6. Timezone handling

All availability evaluation converts UTC to Europe/London time using
`zoneinfo.ZoneInfo("Europe/London")`. This correctly handles GMT/BST
transitions. The `tzdata` package is in `requirements.txt` to ensure
reliable timezone data on the Railway container.

`open_time` and `close_time` are stored as TIME columns in Postgres.
psycopg2 maps these to `datetime.time` objects automatically on read.
These times are always interpreted in Europe/London local time.

Overnight opening hours are not supported. An overnight service (where
`open_time > close_time`) is by definition an urgent or out-of-hours
service with different clinical logic. The evaluation assumes
`open_time < close_time` and this is an intentional domain constraint.

### 7. Database schema

Table `practice_availability` (created by migration 0002, extended by
migration 0003):

    practice_id          TEXT PRIMARY KEY REFERENCES practices(practice_id)
    is_active            BOOLEAN NOT NULL DEFAULT false
    weekly_open_days     TEXT[]  NOT NULL DEFAULT '{}'
    open_time            TIME   NOT NULL DEFAULT '08:00'
    close_time           TIME   NOT NULL DEFAULT '18:30'
    closed_message       TEXT
    override_status      TEXT CHECK (override_status IN ('open', 'closed'))
    override_expires_at  TIMESTAMPTZ
    override_message     TEXT

The three override columns (added by migration 0003) are all nullable.
A null override_status means no override is active.

The `weekly_open_days` column has a CHECK constraint using the Postgres
`<@` operator to assert that every element is one of the seven valid day
abbreviations (mon, tue, wed, thu, fri, sat, sun). Application-layer
validation in `availability_service.py` runs first and produces a better
error message; the database constraint is the backstop.

Table `practice_availability_exceptions` (created by migration 0004):
 
    practice_id     TEXT NOT NULL REFERENCES practices(practice_id)
    exception_date  DATE NOT NULL
    exception_type  TEXT NOT NULL CHECK (exception_type IN ('closed', 'custom_hours'))
    open_time       TIME
    close_time      TIME
    note            TEXT
    PRIMARY KEY (practice_id, exception_date)
 
The composite primary key ensures one exception per practice per date.
`open_time` and `close_time` are nullable — they are required for
custom_hours exceptions and must be null for closed exceptions.
Application-layer validation in `availability_service.py` enforces this;
the database does not have a cross-column constraint.

### 8. Startup sequence

The startup sequence in `main.py` is:

1. `alembic_upgrade()` — runs pending migrations (creates the table if
   migration 0002 has not yet run)
2. `_validate_startup(practice_repo)` — seeds the practice row if absent
3. `availability_repo.init_availability(practice_id)` — inserts the
   default availability row if absent

There is never a state where the availability row does not exist after
startup.

`GET /admin/availability/exceptions`: returns all exceptions on or after
today's date (Europe/London time), ordered by date ascending. This
includes today's exception if one exists — the admin needs to verify
what is currently active. The `from_date` passed to the repository is
today in Europe/London time, the same as the evaluation path. Requires
admin auth.
 
`PUT /admin/availability/exceptions/{date}`: creates or updates an
exception for the given date (YYYY-MM-DD format in the URL path).
Accepts `exception_type` ("closed" or "custom_hours"), `open_time` and
`close_time` (HH:MM strings or null), and `note` (string or null).
Validates via `validate_exception` in the service layer. Returns the
stored exception. Returns HTTP 400 if validation fails or the date
format is invalid.
 
`DELETE /admin/availability/exceptions/{date}`: deletes the exception
for the given date. Idempotent — no error if no exception existed.
Returns 204 No Content.

### 9. Admin endpoints

`GET /admin/availability`: returns the raw config dict with times
formatted as HH:MM strings and override_expires_at as ISO string.
Requires admin auth. Does not call `evaluate_availability`.

`PUT /admin/availability`: accepts the schedule config, validates via
the service layer, persists via the repository, and returns the updated
config. Logs a warning if `is_active` is true and `weekly_open_days` is
empty. If `is_active` is set to false, auto-clears any existing override
(sets all three override columns to NULL). Returns HTTP 400 if
validation fails.

`POST /admin/availability/override`: sets a manual force-open or
force-closed override. Accepts `status` ("open" or "closed"),
`expires_at` (timezone-aware ISO datetime string), and `message`
(string or null). Validates via `validate_override` in the service
layer. Rejects timezone-naive expires_at with HTTP 400. Returns the
updated raw config.

`DELETE /admin/availability/override`: clears any active override by
setting all three override columns to NULL. Idempotent — no error if
no override was active. Returns the updated raw config.

### 10. Banned imports

The following import rules apply to the availability modules:

- availability_service must NOT import any repository or IO module
- availability_repository must NOT import availability_service
- availability_models must NOT import any service or repository module
- admin_router may import availability_service for validation only
- Clinical engine modules (form_logic, safety_engine, encoder_mapping,
  encoder_stub, projection, serialisation) must NOT import any
  availability module — the clinical engine has no awareness of
  practice scheduling

### 11. Testing

Unit tests for `availability_service.py` live in
`tests/test_availability_service.py`. They test the pure logic with no
database. All tests construct `AvailabilityConfig` directly and pass
controlled UTC datetimes.

Tests 1-7 cover Stage 2: schedule evaluation, config validation, and
the fail-open pattern.

Tests 8-15 cover Stage 3: force-open override, force-closed with
override message, null message fallback to closed_message, empty string
message preserved (not fallback), expired override fallthrough to
schedule, timezone-naive expires_at rejection, is_active=false ignoring
force-closed override, and auto-clear on deactivation.

Additional boundary tests cover: exact open/close time boundaries, BST
offset effects, and override expiry edge cases.

Run with: `python -m tests.test_availability_service`

### 12. Manual override design
 
The override system allows an admin to temporarily force the form open or
closed regardless of the weekly schedule. This is designed for emergency
closures, staff training days, or extending access outside normal hours.
 
#### Override expiry
 
`override_expires_at` is always required when setting an override. Null is
not permitted. The valid window is `now_utc < override_expires_at <=
now_utc + 24 hours`. A non-null `override_expires_at` that has passed is
treated as no override — the evaluation falls through to the weekly
schedule. Expiry is strictly less-than: at exactly `override_expires_at`,
the override is no longer active.
 
#### Timezone requirement for expires_at
 
The admin UI submits `expires_at` as a UTC ISO string. The backend rejects
timezone-naive datetime strings with a clear error message. During BST, a
London-local time submitted without an offset would be stored as if it
were UTC, causing the override to expire one hour late.
 
#### Auto-clear on deactivation
 
When `PUT /admin/availability` sets `is_active` to false, any existing
override is cleared (all three override columns set to NULL). This
prevents stale override data from silently taking effect if the admin
later re-enables `is_active`. The logic is split: the service layer
function `deactivation_clears_override` returns a boolean, and the admin
router calls `clear_override` on the repository when true. The repository
writes only what it is told.
 
#### Override message fallback chain
 
When an override is active and `override_status` is `"closed"`:
(1) If `override_message is not None` (including empty string `""`): use
`override_message`. (2) If `override_message is None`: use
`closed_message`. (3) If both are None: return None. The explicit
`is None` check ensures that an empty string configured as the override
message is treated as an intentional choice, not as absent.
 
#### Admin portal override display
 
Active override is determined in JavaScript:
`override_status !== null && new Date(override_expires_at) > new Date()`.
`Date.now()` is UTC-safe. Local time must not be used for this comparison.
 
When displaying `override_expires_at` to the admin, the timestamp is
formatted in Europe/London local time using `Intl.DateTimeFormat` with
`timeZone: "Europe/London"`. This ensures correctness during BST.
 
#### Force-open after-hours notice
 
When a force-open override is active, the after-hours notice is still
constructed from the config's `close_time`. The override is temporary and
the patient should still be aware of the normal schedule.
 
### 13. Migration history
 
| Migration | Description |
|---|---|
| 0001 | Initial schema: four existing tables with IF NOT EXISTS |
| 0002 | practice_availability table (weekly schedule, closed message) |
| 0003 | Three override columns on practice_availability |
| 0004 | practice_availability_exceptions table (per-date exceptions) |

### 14. Per-date exceptions design
 
The exception system allows an admin to define per-date schedule
overrides for specific dates — either closing the practice entirely or
running custom hours. This is designed for bank holidays, staff training
days, or one-off extended hours.
 
#### Exception types
 
`closed`: the practice is closed all day. `open_time` and `close_time`
must be null. The service returns `closed_message` from the config (not
from the exception — exceptions do not carry their own closed message).
 
`custom_hours`: the practice is open during different hours than the
weekly schedule. Both `open_time` and `close_time` are required.
Overnight hours are not supported (same domain constraint as the weekly
schedule). The after-hours notice is constructed from the exception's
close_time, not the config's close_time.
 
#### Evaluation priority
 
The evaluation order is: override > exception > weekly schedule. An
active override always takes priority over an exception on the same day.
This is intentional — if an admin sets a force-open override during a
bank holiday exception, the override wins.
 
#### Exception date lookup
 
`get_exceptions()` is called with today's date in Europe/London time,
not UTC. Using the UTC date would miss exceptions that begin at midnight
London time on days not yet reached in UTC. The same repository method
is used both by the evaluation path and by the admin GET endpoint. The
evaluation logic takes the first matching entry for today and ignores
the rest.
 
#### check_availability orchestration function
 
`check_availability(availability_repo, practice_id, now_utc)` is
defined in `main.py`. It owns the full evaluation pipeline: fetch
config, compute today's London date, fetch exceptions, call
`evaluate_availability`. This function does not belong in
`availability_service.py` because the service layer has no database
access. Both `GET /availability` and the availability check inside
`POST /form/init` call `check_availability`. The fail-open try/except
wrapping lives in `main.py` around the call to `check_availability`.
 
#### Submitted-after-hours flag
 
`POST /form/finish` returns `submitted_after_hours` (boolean). After
the existing finish logic, `check_availability` is called in a
try/except. If the result's `is_open` is false, the flag is true. If
the check fails or the result is open, the flag is false. The frontend
uses this flag to display an appropriate confirmation message on the
submission screen. Uncertainty defaults to false — must not alarm the
patient.
 
#### Note field
 
Each exception has an optional `note` field (free text). This is for
admin reference only (e.g. "Bank holiday", "Staff training afternoon").
The note is not shown to patients and is not used in evaluation logic.
