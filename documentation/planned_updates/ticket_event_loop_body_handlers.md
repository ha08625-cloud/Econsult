# Ticket: Move blocking work off the event loop in the body-reading handlers

**Status:** Reviewed (workflow step 2 complete). Not started. Task 0 is a spike
that gates the shape of D1 — run it before expanding tasks 1–6 into full task
specs.

**Raised by:** `docs/implementation_plans_completed/event_loop_blocking_ticket.md`,
"Follow-up ticket to raise". The design is already settled there as D7; this ticket
carries it forward and adds one call that the parent ticket missed.

**Review pass changes.** The review verified every claim below against the code.
Corrections and resolutions, summarised so the diff from the provisional plan is
visible:

- `form_init` had a **second** blocking call that the original table missed —
  `check_availability`, which runs *before* the body is read. See the table note.
- `add_user` has **no test coverage at all**. This changes what Task 1 involves.
- **Q1 is resolved** in favour of thread-wrapping. It is now D6; the open question
  is deleted.
- **Q2 is resolved** in favour of including `mailgun_webhook`, but the work is not
  what the provisional plan described. It is now D7.
- **Q3 is resolved** — the behaviour is safe, but the test is new coverage rather
  than a re-verification. It is now D8.
- A cheaper alternative to D1 was identified and is unverified. It is Task 0.

---

## Context

The parent ticket established the concurrency rule at the HTTP boundary: all
database access is blocking psycopg2, so an `async def` handler runs its queries
directly on the single event loop and serialises every concurrent request behind
them. It fixed that rule for everything it could reach cheaply — `require_admin`
became plain `def`, 20 no-body handlers became plain `def`, and the auth service
calls and image sanitisation moved to `run_in_threadpool`.

It explicitly deferred the 15 handlers that read the request body. A plain `def`
handler cannot `await request.json()`, so those handlers had to stay `async def`,
and their blocking work stayed on the loop. This ticket finishes the job.

Two things have changed since the parent ticket was written, both of which affect
severity rather than approach:

- **`connect_timeout` and `statement_timeout` have landed** in `app/core/db.py`.
  The unbounded-block scenario — Postgres unreachable, handler blocks forever,
  `/healthz` stops answering, Railway restart-loops — is now bounded. Remaining DB
  blocks are capped by the server-side statement timeout.
- **A blocking *network* call was found on the loop** that is not a database call
  at all, and is far larger than anything the parent ticket addressed. See the
  severity ordering below.

---

## Current state

15 handlers are still `async def`. Two of them (`request_password_reset`,
`set_password`) were fully wrapped by the parent ticket and have no blocking work
left on the loop — they are listed for completeness and need no change. That
leaves **13 handlers** to fix.

| File | Handler | Blocking work still on the loop |
|---|---|---|
| `admin_user_router.py` | `add_user` | `delivery_service.send_admin_invitation` (SMTP or Mailgun HTTP), `get_conn` transaction, `user_service.add_user`, `generate_reset_token`, `log_event` |
| `admin_auth_router.py` | `login` | `auth_service.hash_code` (bcrypt), `auth_repo.upsert_auth_code`, `log_event` ×2 |
| `admin_auth_router.py` | `verify_mfa_code` | `log_event` ×2 |
| `admin_auth_router.py` | `request_password_reset` | *none — already clean* |
| `admin_auth_router.py` | `set_password` | *none — already clean* |
| `admin_practice_router.py` | `put_practice_email` | `get_conn` transaction, `get_practice`, `get_email`, `update_email`, `log_event` |
| `admin_practice_router.py` | `put_signposting` | `get_conn` transaction, `get_signposting`, `set_signposting`, `log_event` |
| `admin_practice_router.py` | `put_doctors` | `get_conn` transaction, `get_doctors`, `set_doctors`, `log_event` |
| `admin_availability_router.py` | `put_availability` | `get_conn` transaction, `get_availability`, `set_availability`, `clear_override`, `log_event` |
| `admin_availability_router.py` | `post_override` | `get_conn` transaction, `get_availability`, `set_override`, `log_event` |
| `admin_availability_router.py` | `put_exception` | `get_conn` transaction, `get_exception`, `set_exception`, `log_event` |
| `form_router.py` | `form_init` | **`check_availability` (see note)**, `runtime_repo.create_initial` |
| `form_router.py` | `form_update` | `runtime_repo.get_latest`, `insert_new_version` |
| `form_router.py` | `form_finish` | `runtime_repo.get_latest`/`close_session`, `submission_repo.create_submission`, `photo_repo.save_photos`, `pdf_repo.create_job`, `practice_repo.get_email` (sanitisation is already threaded) |
| `webhook_router.py` | `mailgun_webhook` | `_consume_token` (own `get_conn`), `delivery_repo.mark_delivered` / `mark_provider_failed` / `append_provider_event` |

**Note — `form_init`'s availability check.** `check_availability(availability_repo,
...)` runs at `form_router.py:123`, *before* `await request.json()` on line 134. It
is a blocking psycopg2 call on the event loop and the provisional plan omitted it.

This is not a bookkeeping correction. It is the only blocking call in the table on
the patient-facing hot path — it runs on every form start, rate-limited at
`30/minute`, which is an order of magnitude more traffic than any admin route here.
It also changes the shape of the `form_init` conversion: the shim cannot simply
await the body and delegate, because this call precedes the body read. The whole
check — including its fail-open `try/except` and the 503 `JSONResponse` return —
moves into `_impl`, ahead of the parsed-body work. Fail-open behaviour is a
project-level invariant (`architecture.md` §1) and must be preserved exactly.

### Severity ordering

The 13 are not equally bad. Fix in this order if the ticket is split across
sessions:

1. **`add_user` — up to 30 seconds of stalled loop.** It calls
   `delivery_service.send_admin_invitation` directly (`admin_user_router.py:226`).
   That is a synchronous `smtplib.SMTP` connect-and-send with a 30-second timeout,
   or on the Mailgun path a `requests.post` with `timeout=30`. If the mail
   provider is slow or unreachable, one admin adding one user takes the entire
   application offline for up to 30 seconds — including `/healthz`. This is the
   single largest block remaining in the codebase, an order of magnitude worse
   than any bcrypt or query cost, and it is the reason this ticket should not sit
   in the backlog indefinitely.

2. **`login` — ~250–300 ms of bcrypt.** `auth_service.hash_code` at
   `admin_auth_router.py:183` is `bcrypt.hashpw(..., gensalt())` at the default 12
   rounds, called on the event loop on every successful step-1 login. The parent
   ticket's Task 3 wrapped all four `auth_service` *verification* entry points but
   missed this one, because it hashes the outgoing OTP rather than checking an
   incoming secret. It is the same order of CPU cost as the `checkpw` that was
   correctly moved. See D3.

3. **Everything else — single-digit milliseconds each.** Short psycopg2 queries,
   now bounded by `statement_timeout` in `db.py`. Real, but nobody will notice
   them at single-practice load. Fix them for consistency with the rule, not
   because they hurt.

### Existing test coverage

Checked during the review, because it determines how risky each conversion is:

| Handler(s) | Covering tests |
|---|---|
| `login`, `verify_mfa_code` | `tests/routers/test_admin_auth_router.py` (754 lines) |
| `put_practice_email`, `put_signposting`, `put_doctors` | `tests/routers/test_admin_practice_router.py` (441 lines) |
| `put_availability`, `post_override`, `put_exception` | `tests/routers/test_admin_availability_router.py` (489 lines) |
| `form_init`, `form_update`, `form_finish` | `tests/test_form_routes.py` (874 lines) |
| `mailgun_webhook` | `tests/test_webhook_router.py` |
| **`add_user`** | **none — see below** |

**`admin_user_router.py` has no tests.** There is no
`tests/routers/test_admin_user_router.py`, and no test in the suite hits `/users`
or imports the module. The highest-severity handler is therefore also the only one
with no regression net, which inverts the usual assumption that severity-first
ordering is also risk-first ordering. Task 1 must *write* that file, not adjust
one. `tests/helpers/admin_test_helpers.py` already provides a `FakeAuthRepo` with
`get_users_by_practice`, `count_users_for_practice` and the delete path, so the
harness largely exists.

Separately, no test anywhere asserts the audit-failure 500 — see D8.

---

## Design decisions

**D1. Async shim awaiting the body, delegating to a sync `_impl` via
`run_in_threadpool`.** Inherited from the parent ticket's D7. The shim stays
`async def`, does only `await request.json()` / `.body()` / `.form()` / `f.read()`,
then hands the parsed body and the injected dependencies to a plain `def _impl`
that contains everything else. All blocking work — repository calls, `get_conn`
transaction blocks, service calls — moves wholesale into `_impl`.

This is an existing convention rather than a new one:
`admin_auth_router._process_password_reset` (line 334) is already exactly this
shape, and its docstring already states the rule. Follow it.

**Subject to Task 0.** If the spike succeeds, most handlers become a single plain
`def` and no `_impl` is needed. D1 is the fallback and is known to work.

**D2. No Pydantic body models.** Inherited from D7. `request_validation.py`
produces a specific error envelope that the frontend and a large number of tests
depend on; Pydantic would replace it with its own 422 shape. This is settled — do
not reopen it.

**D3. The `hash_code` bcrypt fix is folded into this ticket rather than shipped as
a standalone one-liner.** It lives inside `login`, which this ticket rewrites into
the shim/`_impl` shape anyway, and moving it into `_impl` fixes it for free. A
separate commit would mean touching the same function twice for no benefit. It is
independent of everything else here, so it can still be lifted out early as
`hashed = await run_in_threadpool(auth_service.hash_code, code)` if this ticket
stalls — `run_in_threadpool` is already imported in that file and nothing else
calls `hash_code`.

**D4. The `conn=conn` transaction convention is unaffected.** Six of the 13
handlers wrap several repository calls in a `with get_conn(...) as conn:` block
and pass `conn=conn` down. The whole block moves into `_impl` intact — it is
ordinary synchronous code running on one worker thread, which is exactly what it
already assumes. No repository signatures change.

**D5. Threadpool sizing stays at the default 40 — but re-check it after `add_user`
moves.** Inherited from the parent ticket's D8. The reasoning there was that the
rate limiter is the intended ceiling. That still holds, but note what changes:
thread-wrapping `send_admin_invitation` converts "30 seconds of blocked loop" into
"one pool thread held for 30 seconds". `POST /users` is admin-authenticated and
rate-limited at `10/minute`, so pool exhaustion from this path is not realistic.
Recording the trade-off so it is a decision rather than an oversight.

**D6. `add_user`'s invitation send is thread-wrapped, not moved to a
`BackgroundTask`.** (Resolves provisional Q1.) The question was whether to take
mail latency out of the response entirely, at the cost of the `email_sent` field.
Two pieces of evidence settle it:

- **The frontend consumes `email_sent`.** `UsersTab.tsx:82` renders a warning
  banner when it is false, `types.ts:72` types it as a required boolean, and
  `UsersTab.test.tsx` covers both branches (lines 208–231). A background task
  would mean a frontend change plus test churn on top of the router work.
- **`resend_invitation` already does it the thread-wrapped way.**
  `admin_user_router.py:334` is a plain `def` handler that calls
  `send_admin_invitation` synchronously in the threadpool and returns the
  identical `{"ok", "email_sent"}` shape.

The second point is decisive. `add_user` and `resend_invitation` are siblings
returning the same contract to the same screen; thread-wrapping makes them
structurally identical, whereas a background task gives them the same response
shape with two different delivery semantics. That divergence buys nothing the
admin can observe. Take the thread-wrap.

**D7. `mailgun_webhook` is in scope, and its `_impl` signature will not look like
the others.** (Resolves provisional Q2.) The replay-protection concern raised in Q2
is unfounded: `_consume_token` is one self-contained `get_conn` block that moves
wholesale, and threading does not alter the `ON CONFLICT DO NOTHING` semantics.

The real friction is different. `mailgun_webhook` uses **no `Depends` at all** — it
calls `get_mailgun_signing_key(request)` (line 166), `get_database_url(request)`
(179) and `get_delivery_repo(request)` (190) as direct accessors mid-body. Those
are `app.state` reads and are safe to leave in the shim, but `_impl` must then take
the resolved values as ordinary parameters rather than injected dependencies. It is
the one handler in this ticket whose signature diverges from the pattern; expect it
and do not try to force it into the common shape.

Form-field declaration is not an option here either — Mailgun's field names are
dynamic (`event-data[message][headers][message-id]`), so `await request.form()`
stays.

**D8. The audit-failure 500 survives the move, and the test for it is new
coverage.** (Resolves provisional Q3.) `run_in_threadpool` re-raises exceptions
from the worker thread unchanged, so `HTTPException(500, ...)` raised inside
`_impl` behaves identically. The parent ticket already relies on this for
`_sanitize_photos`.

The correction is to the framing: no test anywhere asserts
`"Action succeeded but audit logging failed"`. There are 15 audit sites using this
pattern and **zero** existing coverage of the error path. The test called for here
is therefore new coverage, not a re-verification of something already pinned. Write
one — it is cheap, and the audit trail is mandatory (`arch_admin.md`).

---

## Scope

**In scope**

- `app/routers/admin/admin_user_router.py` — `add_user`
- `app/routers/admin/admin_auth_router.py` — `login` (including the `hash_code`
  bcrypt call, D3), `verify_mfa_code`
- `app/routers/admin/admin_practice_router.py` — 3 handlers
- `app/routers/admin/admin_availability_router.py` — 3 handlers
- `app/routers/form_router.py` — 3 handlers
- `app/routers/webhook_router.py` — `mailgun_webhook` (confirmed in scope, D7)
- `documentation/arch_http_boundary.md` — extend the handler-concurrency rule to
  record whichever pattern Task 0 selects as the required shape for body-reading
  handlers
- Router tests for each converted handler, including:
  - **a new `tests/routers/test_admin_user_router.py`** — the module has no tests
    at all today
  - **at least one audit-failure-500 test** — that error path has no coverage
    today either (D8)

**Explicitly out of scope**

- Replacing psycopg2 with an async driver. Rejected in the parent ticket (D6) and
  still rejected: the `conn=conn` convention runs through every repository and
  every mutating router, and this fixes a concurrency ceiling a single-practice
  deployment will not reach.
- Adding `--workers` to uvicorn. Rejected in the parent ticket (D5) — the
  in-memory slowapi storage assumes one web worker, and N workers would silently
  multiply every rate limit by N.
- Raising the anyio threadpool size. See D5.
- `main.py`'s `/healthz`. Still `async def`, still touches no database, still
  correct as-is.

**Done when**

- No handler in `app/routers/` performs blocking database, bcrypt, or network work
  directly on the event loop. The only work left in an `async def` body is
  awaiting the request body and delegating.
- `add_user` no longer blocks the loop on SMTP/HTTP (via D5 thread-wrap or Q1
  background task).
- `arch_http_boundary.md` records the selected pattern.
- Full test suite passes, including integration tests (`make test-integration`
  with `TEST_DATABASE_URL` set, per the two-database rule in `arch_testing.md`).
- Concurrency smoke test: fire ~10 concurrent `POST /admin/auth/login` requests
  with bad credentials and confirm `GET /healthz` still answers promptly.

---

## Task breakdown

One task per router file keeps each chat's context small and each diff
independently reviewable. Severity first, then the mechanical remainder — with one
gating spike ahead of everything.

### Task 0 — Spike: can these handlers just be plain `def`? (gates D1)

**Run this first. It is time-boxed to roughly 30 minutes and it may remove most of
the ticket.**

D2 rejects Pydantic body models, correctly, and that is not being reopened. But
note *why* the shim exists: solely because `await request.json()` forces
`async def`. That is a property of how the body is read, not of Pydantic.

FastAPI can hand a raw body to a **sync** handler via `body: bytes = Body(...)`.
`bytes` carries no Pydantic shape validation, so the handler does its own
`json.loads` and raises `INVALID_PAYLOAD` exactly as it does today — the
`request_validation.py` error envelope is preserved untouched, which is the whole
constraint D2 exists to protect. If that holds, each handler stays a single plain
`def` dispatched to the threadpool by FastAPI, with no shim, no `_impl`, and
roughly 13 fewer functions than D1 produces.

Two handlers where it looks especially strong:

- **`form_update`** already reads raw bytes (`await request.body()` at line 185)
  because it needs `json.loads(..., parse_float=Decimal)`. It fits `Body(bytes)`
  more naturally than it fits the current code.
- **`form_finish`** may need none of this. `Form(...)` and `File(...)` parameters
  work in a sync `def` today; the only change is `f.file.read()` in place of
  `await f.read()`. That would eliminate the fiddliest conversion in the list.

**Unverified — this is why it is a spike, not a decision.** It could not be checked
during the review because FastAPI is not installed in that environment. The edges
to establish, on one handler, before adopting it anywhere:

1. What FastAPI returns for a **missing or empty** body with `bytes = Body(...)`.
   If it emits its own 422 before the handler runs, that bypasses the envelope and
   is exactly the failure D2 guards against.
2. Content-type handling — whether a non-JSON or absent `Content-Type` changes the
   parameter's resolution.
3. OpenAPI schema churn, and whether anything consumes the generated schema.
4. That `@limiter.limit` still behaves. Low risk: sync handlers with the decorator
   are already proven in `public_router.py` and `resend_invitation`.

**Outcome:** if it works, rewrite tasks 1–5 around plain `def` and drop the
shim/`_impl` shape. If it does not, D1 stands unchanged and the cost was half an
hour. Record the result in this file either way, then expand tasks 1–6 into full
task specs (workflow step 3).

### Tasks 1–6

1. **`admin_user_router.py` — `add_user`.** Thread-wrap the invitation send per D6;
   Q1 is closed, there is no design question left to resolve. The real work here is
   that **this module has no tests** — write `tests/routers/test_admin_user_router.py`
   covering the 200/409/403/422 paths, both `email_sent` branches, and the
   transaction rollback, *before* touching the handler. Build on the existing
   `FakeAuthRepo` in `tests/helpers/admin_test_helpers.py`.
2. **`admin_auth_router.py` — `login` and `verify_mfa_code`,** including the D3
   bcrypt fix. Two things to get right:
   - `login` takes `BackgroundTasks`. It is injected into the shim and passed
     through to `_impl`; `add_task` is a list append and is safe off-loop, but it
     is easy to fumble during the split.
   - `verify_mfa_code` builds a `JSONResponse` and calls `set_cookie` (lines
     323–332). Construct and return it from inside `_impl` — do not split response
     construction back out into the shim.
3. **`admin_practice_router.py` and `admin_availability_router.py`** — 6 handlers,
   all the same `get_conn` transaction shape (D4). One task.
4. **`form_router.py`** — 3 handlers. Two corrections to the provisional plan:
   - **`form_init` must move `check_availability` too**, with its fail-open
     `try/except` and 503 return intact — see the table note. This is the
     patient-facing hot path and the fail-open behaviour is a project invariant.
   - **`form_finish` may be trivial** if Task 0 succeeds (`f.file.read()` in a sync
     `def`). Under D1 it is the fiddliest of the three: the shim reads the uploads
     and passes bytes into `_impl`, which then owns the already-threaded
     sanitisation call.
5. **`webhook_router.py` — `mailgun_webhook`.** Confirmed in scope. Per D7, `_impl`
   takes the three accessor-resolved values as plain parameters; its signature will
   not match the other handlers.
6. **Documentation.** `arch_http_boundary.md` handler-concurrency rule, updated to
   record the pattern Task 0 selected.
