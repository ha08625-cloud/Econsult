# Implementation Plan: Move blocking work off the event loop in the body-reading handlers

**Source ticket:** `docs/planned_updates/ticket_event_loop_body_handlers.md`. That
document holds the full design rationale (D1–D9), the severity ordering, the
handler table, and the Task 0 spike evidence. **Read it before starting any task
below.** This file is the task breakdown only and deliberately does not repeat it.

**Parent ticket:** `docs/implementation_plans_completed/event_loop_blocking_ticket.md`,
which established the handler-concurrency rule and deferred these 13 handlers.

---

## Plan

All database access is blocking psycopg2. An `async def` handler runs its queries
directly on the single event loop thread and serialises every concurrent request
behind them. The parent ticket fixed this for every handler it could reach; it
deferred the 15 that read the request body, because a plain `def` handler cannot
`await request.json()`.

Task 0 (already done, in the ticket) established that it can, given a
`BodyCapturingRoute` that reads the body once before the endpoint runs. So the
work is: convert 13 handlers from `async def` to plain `def`, which moves every
blocking call inside them into the anyio threadpool.

The largest single win is `add_user`, which currently makes a synchronous SMTP or
Mailgun call with a 30-second timeout directly on the loop.

---

## Scope

**In scope**

- `app/core/body_capture.py` — new; `BodyCapturingRoute` and `read_json_body`
- `app/routers/admin/admin_user_router.py` — `add_user`
- `app/routers/admin/admin_auth_router.py` — `login`, `verify_mfa_code`, plus the
  two already-clean handlers for consistency
- `app/routers/admin/admin_practice_router.py` — 3 handlers
- `app/routers/admin/admin_availability_router.py` — 3 handlers
- `app/routers/form_router.py` — 3 handlers
- `app/routers/webhook_router.py` — `mailgun_webhook`
- `documentation/arch_http_boundary.md`
- Router tests, including a new `tests/routers/test_admin_user_router.py`

**Out of scope** — unchanged from the ticket: async driver migration,
uvicorn `--workers`, raising the threadpool size, `main.py`'s `/healthz`.

---

## Design decisions

D1–D9 live in the ticket. Three consequences of D9 that are easy to miss and that
every task below depends on:

**Existing `run_in_threadpool` calls inside these handlers must be unwrapped.** You
cannot `await` in a plain `def`. Every
`await run_in_threadpool(f, ...)` inside a converted handler becomes a direct
`f(...)` call. This is correct, not a regression: the whole handler is already
running on a worker thread, so the wrapper was only ever there to get off the loop.
Leaving it nested would consume a second pool thread to do the same work.

**Blocking calls need no wrapping once the handler is `def`.** `add_user`'s
`send_admin_invitation`, `login`'s `bcrypt.hashpw`, and every `get_conn`
transaction block are off the loop automatically. D6's decision (keep the
synchronous send and the `email_sent` field, do not background it) stands; the
mechanism is simply that nothing extra is needed, which is exactly the symmetry
with `resend_invitation` that D6 argued for.

**`request.state.raw_body` is never read directly.** Handlers call
`read_json_body(request)`, which raises a named error if the route class is
missing. See D9's footgun note.

---

# Task 1: Body-capture foundation and `add_user`

**A. State of the world**

Nothing in this ticket has been implemented. This is the first task and every
later task depends on the module it creates.

`add_user` (`app/routers/admin/admin_user_router.py:125`) is the highest-severity
handler in the ticket: it calls `delivery_service.send_admin_invitation` at line
226, a synchronous SMTP connect-and-send with a 30-second timeout, or a
`requests.post(timeout=30)` on the Mailgun path — directly on the event loop.

`admin_user_router.py` has **no test coverage of any kind**. There is no
`tests/routers/test_admin_user_router.py` and no test in the suite hits `/users`.
Write the tests before touching the handler; they are the only regression net this
task has.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/core/body_capture.py` | New. `BodyCapturingRoute` (per D9) and `read_json_body(request)`. Module docstring explains that the two are a pair and why. |
| `tests/routers/test_admin_user_router.py` | New. Covers `add_user` and `resend_invitation`. |
| `app/routers/admin/admin_user_router.py` | `router = APIRouter(route_class=BodyCapturingRoute)`; `add_user` becomes plain `def`. |
| `tests/test_body_capture.py` | New. Pins the `read_json_body` failure mode. |

**C. Instructions**

1. Create `app/core/body_capture.py`:

   ```python
   class BodyCapturingRoute(APIRoute):
       def get_route_handler(self) -> Callable:
           original = super().get_route_handler()

           async def custom_handler(request: Request) -> Response:
               request.state.raw_body = await request.body()
               return await original(request)

           return custom_handler
   ```

   Add `read_json_body(request)` alongside it. It must:
   - raise a clear, named error (not a bare `AttributeError`) when
     `request.state.raw_body` is absent, naming `BodyCapturingRoute` in the
     message — this is the D9 footgun mitigation and is required;
   - `json.loads` the bytes and raise `INVALID_PAYLOAD("Invalid JSON body")` on
     failure, matching the existing message exactly;
   - accept an optional `parse_float` argument for `form_update`'s `Decimal`
     requirement (Task 4).

   Do **not** put this in `request_validation.py` — that module is pure
   payload-shape validation with no Starlette imports, and should stay that way.

2. Write `tests/routers/test_admin_user_router.py` **before** changing the handler,
   and confirm it passes against the current `async def` code. Cover:
   `POST /users` 200 with `email_sent: true`; 200 with `email_sent: false` when
   `send_admin_invitation` raises; 409 duplicate email; 403 disallowed domain; 422
   invalid email format; 401 expired session; malformed JSON body; and the
   transaction rollback path (audit write fails → 500, nothing committed).
   Build on `FakeAuthRepo` in `tests/helpers/admin_test_helpers.py`, which already
   has `get_users_by_practice` and `count_users_for_practice`. Also cover
   `resend_invitation`, which is untested and is `add_user`'s sibling.

3. Change `router = APIRouter()` to
   `router = APIRouter(route_class=BodyCapturingRoute)` at line 66.

4. Convert `add_user` to plain `def`. Replace the `try: body = await
   request.json()` block at lines 159–162 with `body = read_json_body(request)`.
   Everything else in the body is unchanged — the `get_conn` block, the
   `send_admin_invitation` call, and the `email_sent` logic all stay exactly as
   they are and are now off the loop by virtue of the handler being sync.

5. Add a `tests/test_body_capture.py` asserting that a handler registered on a
   router *without* `route_class=BodyCapturingRoute` fails via `read_json_body`'s
   named error rather than an `AttributeError`.

6. Run `make test`. Per the project test obligation, add
   `pytestmark = pytest.mark.integration` to any new test file that needs a
   database, and check whether `arch_testing.md` needs updating.

---

# Task 2: `admin_auth_router.py`

**A. State of the world**

Task 1 is complete: `body_capture.py` exists and `add_user` is converted.

Four handlers here read the body. Two have blocking work on the loop:

- `login` (line 103) — `auth_service.hash_code` at line 183 is
  `bcrypt.hashpw(..., gensalt())` at 12 rounds, ~250–300 ms on the loop on every
  successful step-1 login. The parent ticket wrapped the four `auth_service`
  *verification* entry points but missed this one, because it hashes an outgoing
  OTP rather than checking an incoming secret (ticket D3). Plus two `log_event`
  calls and `upsert_auth_code`.
- `verify_mfa_code` (line 228) — two `log_event` calls.

`request_password_reset` (line 377) and `set_password` (line 432) already delegate
all their blocking work via `run_in_threadpool` and have nothing left on the loop.
They are converted anyway, for consistency with the rule and because it removes the
wrappers. This is a deliberate small scope addition, not drift — the ticket's
"Done when" states that every handler in `app/routers/` ends up a plain `def`.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/routers/admin/admin_auth_router.py` | `route_class` on the router; all four body-reading handlers become plain `def`; `run_in_threadpool` wrappers unwrapped; D3 bcrypt fix lands as a side effect. |
| `tests/routers/test_admin_auth_router.py` | Existing 754-line file — adjust as needed; add the audit-failure-500 test (D8). |

**C. Instructions**

1. Set `route_class=BodyCapturingRoute` on the router at line 53.

2. Convert all four handlers to plain `def` and replace each
   `body = await request.json()` block (lines 132, 253, 405, 457) with
   `read_json_body(request)`.

3. Unwrap every `run_in_threadpool` call in this file into a direct call — see the
   design-decisions note above. Specifically:
   - `login`: `verify_login_credentials` (line 155)
   - `verify_mfa_code`: `verify_mfa_code` (line 281)
   - `request_password_reset`: `_process_password_reset` (line 418)
   - `set_password`: `verify_reset_token` and `set_new_password` (lines 475–476)

   `partial` may become unused; remove the import if so. Keep
   `_process_password_reset` as a module-level function — it is still a coherent
   unit and its docstring should be updated to say the caller is now a sync
   handler rather than a threadpool dispatch.

4. `hash_code` (line 183) needs no code change — it is off the loop once `login` is
   sync. That is D3, resolved.

5. Two things that are *no longer* hazards, because D9 keeps each handler a single
   function: `login`'s `BackgroundTasks` injection and `verify_mfa_code`'s
   `JSONResponse` + `set_cookie` (lines 323–332) both stay exactly where they are.
   Do not restructure them.

6. Add the D8 test: patch `audit_repo.log_event` to raise and assert the endpoint
   returns 500 with `"Action succeeded but audit logging failed. Please report
   this."`. No test currently asserts this anywhere in the suite, across 15 audit
   sites. One test on one handler is enough.

7. Run `make test`.

---

# Task 3: `admin_practice_router.py` and `admin_availability_router.py`

**A. State of the world**

Tasks 1 and 2 are complete.

Six handlers, all the same shape: `await request.json()`, then a
`with get_conn(...) as conn:` block wrapping several repository calls with
`conn=conn`, then `log_event`. Each is single-digit milliseconds of blocking work,
now bounded by `statement_timeout`. They are converted for consistency with the
rule, not because they hurt (ticket severity tier 3).

Per ticket D4, no repository signature changes and no change to the `conn=conn`
convention — the transaction block is ordinary synchronous code and moves
untouched.

| Handler | Line |
|---|---|
| `put_practice_email` | `admin_practice_router.py:129` |
| `put_signposting` | `admin_practice_router.py:239` |
| `put_doctors` | `admin_practice_router.py:405` |
| `put_availability` | `admin_availability_router.py:166` |
| `post_override` | `admin_availability_router.py:342` |
| `put_exception` | `admin_availability_router.py:551` |

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/routers/admin/admin_practice_router.py` | `route_class` on the router (line 62); 3 handlers to plain `def`. |
| `app/routers/admin/admin_availability_router.py` | `route_class` on the router (line 63); 3 handlers to plain `def`. |
| `tests/routers/test_admin_practice_router.py`, `tests/routers/test_admin_availability_router.py` | Adjust as needed. |

**C. Instructions**

1. Set `route_class=BodyCapturingRoute` on both routers.

2. For each of the six handlers: `async def` → `def`, and replace the
   `body = await request.json()` block (lines 155, 272, 434 and 200, 368, 587) with
   `read_json_body(request)`.

3. Change nothing else. No `get_conn` block, no repository call, and no path
   parameter (`condition_id`, `date`) needs touching.

4. Run `make test`. These two test files total 930 lines and exercise the handlers
   through the app, so most or all should pass unchanged — investigate any that do
   not rather than adjusting the assertion.

---

# Task 4: `form_router.py`

**A. State of the world**

Tasks 1–3 are complete.

Three handlers, and the only file in this ticket needing **two different shapes**.

- `form_init` (line 112) — carries a blocking call the provisional ticket missed:
  `check_availability(availability_repo, ...)` at line 123, which runs *before*
  `await request.json()` at line 134. This is the patient-facing hot path, hit on
  every form start at `30/minute` — more traffic than any admin route in this
  ticket. Also `runtime_repo.create_initial`.
- `form_update` (line 176) — reads raw bytes at line 185 because it needs
  `json.loads(..., parse_float=Decimal)` so Number answers arrive as exact
  Decimals. Plus `get_latest` and `insert_new_version`.
- `form_finish` (line 250) — **exempt from `BodyCapturingRoute`** per D9: Task 0
  measured a 6.3 MB multipart upload holding the captured raw body *in addition to*
  the parsed form, roughly doubling peak memory. It does not need the route class,
  because `Form(...)`/`File(...)` parameters already work in a plain `def`.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/routers/form_router.py` | Two routers: a body-capturing one for `form_init`/`form_update`, a plain one for `form_finish`. All three handlers plain `def`. |
| `tests/test_form_routes.py` | Existing 874-line file — adjust as needed. Add a Decimal-precision regression test if one does not already exist. |

**C. Instructions**

1. `form_init` and `form_update` go on a router with
   `route_class=BodyCapturingRoute`; `form_finish` goes on a plain `APIRouter()`.
   Both are included by the same parent — pick whichever arrangement reads more
   clearly (two module-level routers, or one plain router plus an explicit
   per-route override) and say why in a comment. The constraint is only that
   `form_finish`'s route must not capture the body.

2. `form_init`: convert to `def` and replace line 134 with `read_json_body(request)`.
   **The `check_availability` block at lines 122–132 stays exactly where it is** —
   ahead of the body read, inside the now-sync handler. Preserve its fail-open
   `try/except` and the 503 `JSONResponse` verbatim: fail-open availability is a
   project-level invariant (`architecture.md` §1), and a patient must never be
   locked out by a database failure.

3. `form_update`: convert to `def` and replace lines 185–186 with
   `read_json_body(request, parse_float=Decimal)`. The Decimal behaviour is the
   reason this handler reads raw bytes rather than calling `request.json()`;
   Task 0 confirmed it survives. Verify with a test asserting a submitted
   `70.15` arrives as `Decimal('70.15')`, not a float.

4. `form_finish`: convert to `def`, keeping its `payload: str = Form(...)` and
   `photos: list[UploadFile] = File(default=[])` parameters unchanged. Replace
   `[await f.read() for f in photos]` at line 268 with `[f.file.read() for f in photos]`.
   Then unwrap `await run_in_threadpool(_sanitize_photos, ...)` at line 320 into a
   direct `_sanitize_photos(photo_bytes, effective_tier)` call — the handler is
   already on a worker thread. Keep `_sanitize_photos` as a module-level helper and
   update its docstring, which currently explains it exists to be dispatched to the
   threadpool.

   Everything else — the size and count checks, tier validation, the CDR comment
   block, and the four-step persistence ordering at lines 405–443 — is untouched.

5. Run `make test`, then `make test-integration` with `TEST_DATABASE_URL` set, per
   the two-database rule in `arch_testing.md`.

---

# Task 5: `webhook_router.py`

**A. State of the world**

Tasks 1–4 are complete.

`mailgun_webhook` (line 131) is the **one handler that keeps D1's async shim**. It
needs a parsed form with dynamic Mailgun field names
(`event-data[message][headers][message-id]`), which neither `BodyCapturingRoute`
nor a `Form(...)` declaration can supply — so `await request.form()` stays and the
handler stays `async def`.

Per ticket D7, its `_impl` will not look like any other handler in this ticket: the
handler uses **no `Depends` at all**, calling `get_mailgun_signing_key(request)`
(line 166), `get_database_url(request)` (179) and `get_delivery_repo(request)`
(190) as direct accessors mid-body. Those are `app.state` reads and are safe to
leave in the shim; `_impl` takes the resolved values as ordinary parameters.

Blocking work: `_consume_token` (its own `get_conn`, line 102) and
`delivery_repo.mark_delivered` / `mark_provider_failed` / `append_provider_event`.
D7 confirmed the replay-protection logic is unaffected — `_consume_token` is one
self-contained block with `ON CONFLICT DO NOTHING` semantics that threading does
not alter.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/routers/webhook_router.py` | `mailgun_webhook` split into an async shim and a sync `_impl`. |
| `tests/test_webhook_router.py` | Existing file — adjust as needed. |

**C. Instructions**

1. The shim keeps the `@router.post("/webhooks/mailgun")` decorator and stays
   `async def`. It does only: `form = await request.form()`,
   `payload = dict(form)`, resolve the three accessors, then
   `return await run_in_threadpool(_mailgun_webhook_impl, payload, signing_key, database_url, delivery_repo)`.

2. `_mailgun_webhook_impl` is a module-level plain `def` containing everything from
   the security-field extraction (line 147) to the final return. All five
   `JSONResponse` returns — 200 stale, 403 misconfigured, 403 bad signature, 200
   replay, 406 race, 200 ok — move into it unchanged. Response construction inside
   a threadpool worker is fine.

3. Do not change `_verify_mailgun_signature`, `_is_stale`, or `_consume_token`.
   Do not alter the status codes: 406 in particular is load-bearing, since it is
   what makes Mailgun retry the provider-message-id race.

4. Add a docstring note on `_impl` recording why this handler alone keeps the shim
   (dynamic form field names), so nobody "consistency-fixes" it later.

5. Run `make test`.

---

# Task 6: Documentation

**A. State of the world**

Tasks 1–5 are complete. No handler in `app/routers/` performs blocking database,
bcrypt, or network work on the event loop.

`documentation/arch_http_boundary.md` line 23 still states the parent ticket's
rule: handlers that read the body "must stay `async def`" and delegate via
`run_in_threadpool`. That is now wrong in its general form.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `documentation/arch_http_boundary.md` | Handler-concurrency rule restated around D9. |
| `documentation/planned_updates/ticket_event_loop_body_handlers.md` | Mark complete; move to `documentation/implementation_plans_completed/` with this plan file. |

**C. Instructions**

1. Rewrite the handler-concurrency rule to say: every handler in `app/routers/` is
   a plain `def`, so FastAPI dispatches it to the anyio threadpool; body-reading
   handlers get their body from `read_json_body(request)`, which requires the
   router to be constructed with `route_class=BodyCapturingRoute`. State that the
   class and the accessor are a pair.

2. Record the three exemptions and the reason for each, so they read as decisions
   rather than oversights:
   - `form_finish` — no route class; multipart double-buffering (Task 0 measured
     it).
   - `mailgun_webhook` — async shim; dynamic Mailgun form field names.
   - `main.py`'s `/healthz` — `async def`, touches no database.

3. Keep cross-references written as `docs/<name>.md` even though files live in
   `documentation/`, per the parent ticket's D9 path note.

4. Per the project documentation guideline, record the design decision and the
   rule — do not duplicate the implementation, which is readable in
   `body_capture.py`.

5. Move both this file and the ticket into
   `documentation/implementation_plans_completed/`.
