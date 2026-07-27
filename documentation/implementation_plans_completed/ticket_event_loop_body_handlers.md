# Ticket: Move blocking work off the event loop in the body-reading handlers

**Status:** Complete. All 6 tasks in
`docs/implementation_plans_completed/plan_event_loop_body_handlers.md` are
implemented, tested, and merged. Every handler in `app/routers/` is a plain
`def` except the two documented exemptions (`form_finish`, `mailgun_webhook`)
and `main.py`'s `/healthz`. See `docs/arch_http_boundary.md`'s handler
concurrency rule for the settled state; this file and the plan are kept for
the design rationale (D1–D9) below.

**Task specs:** `docs/implementation_plans_completed/plan_event_loop_body_handlers.md`.
This file remains the design record — the plan file references it rather than repeating it,
so read this one first when picking up any task.

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
- A cheaper alternative to D1 was identified, spiked, and adopted. It is **D9**;
  the spike evidence is in Task 0.

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

**Superseded by D9 for all but one handler.** Task 0 established that a plain `def`
is achievable, so D1 now applies **only to `mailgun_webhook`**. It remains the
documented fallback: if D9 causes trouble in implementation, D1 is known to work
and can be reverted to per-handler without re-litigating anything.

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

Task 0 confirmed the behaviour empirically for the D9 shape too: `HTTPException`
and `APIError` raised from a plain `def` handler both reach `main.py`'s registered
handlers and produce identical responses. The test is still worth writing.

**D9. Body-reading handlers become plain `def`; a `BodyCapturingRoute` supplies the
raw body.** (Adopted on the strength of Task 0.) Supersedes D1 everywhere except
`mailgun_webhook`.

A ~10-line `APIRoute` subclass reads the body once in its async route handler and
stashes it on `request.state.raw_body`. The endpoint itself is then a plain `def`
that FastAPI dispatches to the threadpool, and it does its own
`json.loads` + `INVALID_PAYLOAD` exactly as today — so the `request_validation.py`
envelope is untouched, which is the constraint D2 exists to protect.

```python
class BodyCapturingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            request.state.raw_body = await request.body()
            return await original(request)

        return custom_handler
```

Why this over D1: 12 handlers stay single functions instead of becoming 24, no
dependency list is written twice, and the concurrency rule collapses to one
sentence — *every* handler is a plain `def` — instead of a rule plus a
body-reading exception.

**The cost, stated plainly.** `request.state.raw_body` appears from nowhere when
you read a handler; you have to know the route class exists. Worse, a handler added
to a router *without* `route_class=BodyCapturingRoute` fails with an
`AttributeError` at request time rather than at startup. Two required mitigations,
neither optional:

1. A single accessor in `request_validation.py` — `read_json_body(request)` — that
   raises an explicit, named error when `raw_body` is absent. Handlers call that,
   never `request.state.raw_body` directly. This turns the footgun into a message
   that says what is wrong.
2. `arch_http_boundary.md` documents the class, the accessor, and the fact that
   the two are a pair.

If those two feel like more indirection than the saving is worth, D1 is a
legitimate choice and nothing else in this ticket changes. This is a judgement
call, not a correctness one.

**Two shapes are exempt:**

- **`form_finish` must NOT use the route class.** Task 0 measured it: on a
  6.3 MB multipart upload the captured raw body is held *in addition to* the
  parsed form, roughly doubling peak memory for that request. It does not need the
  class anyway — `Form(...)`/`File(...)` parameters work in a plain `def` today,
  using `f.file.read()` in place of `await f.read()`.
- **`mailgun_webhook` keeps D1's shim.** It needs a parsed form with dynamic field
  names, which neither the route class nor `Form(...)` declaration can supply.

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
- `app/core/request_validation.py` — the `read_json_body(request)` accessor (D9)
- a home for `BodyCapturingRoute` (D9) — `request_validation.py` or a new
  `app/routers/_route_class.py`; decide in Task 1
- `documentation/arch_http_boundary.md` — restate the handler-concurrency rule
  around D9, including both exemptions and their reasons
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
  directly on the event loop. Under D9 the stronger form holds: every handler in
  `app/routers/` is a plain `def`, with `mailgun_webhook` the sole `async def`
  (shim only) and `/healthz` the sole standing exemption.
- `add_user` no longer blocks the loop on SMTP/HTTP (D6 thread-wrap).
- `arch_http_boundary.md` records D9, the `read_json_body` accessor, and both
  exemptions.
- A test asserts the audit-failure 500 (D8) — new coverage, none exists today.
- A test asserts that a handler on a router *without* `BodyCapturingRoute` fails
  loudly via `read_json_body` rather than with a bare `AttributeError` (D9's
  footgun mitigation).
- Full test suite passes, including integration tests (`make test-integration`
  with `TEST_DATABASE_URL` set, per the two-database rule in `arch_testing.md`).
- Concurrency smoke test: fire ~10 concurrent `POST /admin/auth/login` requests
  with bad credentials and confirm `GET /healthz` still answers promptly.

---

## Task breakdown

One task per router file keeps each chat's context small and each diff
independently reviewable. Severity first, then the mechanical remainder — with one
gating spike ahead of everything.

### Task 0 — Spike: can these handlers just be plain `def`? — **DONE**

Run against the pinned versions from `requirements.txt` (FastAPI 0.136.3,
Starlette 1.3.1, slowapi 0.1.9). **Outcome: yes, but not the way the review
proposed.** Adopted as D9.

**The proposed mechanism does not work.** `body: bytes = Body(...)` fails on
exactly the case that matters:

```
POST with Content-Type: application/json
  -> 422 {"detail":[{"type":"bytes_type","loc":["body"],
                     "msg":"Input should be a valid bytes", ...}]}
```

FastAPI parses the body as JSON whenever the request's `Content-Type` is
`application/json`, *then* validates the resulting dict against the declared
`bytes` and rejects it. Since that is precisely what the frontend sends, every real
request would have 422'd with FastAPI's envelope — the exact failure D2 exists to
prevent. It only appeared to work under `text/plain` or a missing content-type.
Had this been adopted from reasoning alone it would have broken every JSON endpoint
in the application.

Separately, a **missing body** with `Body(...)` also produces FastAPI's own
`{"detail":[{"type":"missing"...}]}` 422 before the handler runs — the second
envelope bypass the review flagged as the decider. `Body(default=b"")` fixes that
one, but not the content-type problem.

**What does work: a `BodyCapturingRoute` (D9).** Same goal, different mechanism.
Verified results:

| Check | Result |
|---|---|
| `Content-Type: application/json`, the real case | 200, handler sees raw bytes |
| Handler thread | `AnyIO worker thread`, `is_main=False` — genuinely off the loop |
| Sync `Depends` (stand-in for `require_admin`) | resolves, also on a worker thread |
| Malformed JSON / missing body / non-object body | our own envelope, unchanged |
| `parse_float=Decimal` (`form_update`'s requirement) | `Decimal('70.15')` preserved |
| `APIError` raised from the sync handler | reaches `main.py`'s handler, 422 envelope intact |
| `HTTPException(500)` (the audit path, D8) | propagates correctly |
| `@limiter.limit("3/minute")` | 200, 200, 200, 429, 429 — correct |
| OpenAPI schema | no distortion from the route class |

**The one negative result, which changed the plan:** on a body-capturing route, a
6.3 MB multipart upload holds the captured raw body *and* the parsed form
simultaneously (`raw_body_also_held: 6291983` alongside `total: 6291462`). That is
why `form_finish` is exempted in D9. On a plain router, `Form(...)`/`File(...)` +
`f.file.read()` in a `def` handler works and runs on a worker thread, with no
double-buffering.

**Not carried forward:** the review's suggestion that `form_update` would fit
`Body(bytes)` "more naturally". It would not — it fails the same content-type way
as the rest. Its `parse_float=Decimal` requirement is satisfied by D9 instead.

Spike scripts are scratch and were not committed; the table above is the record.

### Tasks 1–6 — **ALL DONE**

All of these assumed D9. Task 1 landed the `BodyCapturingRoute` and the
`read_json_body` accessor as part of its diff, since it is first; tasks 2–4 just
applied them. One deviation from the plan below: `BodyCapturingRoute` and
`read_json_body` ended up in a new `app/core/body_capture.py` rather than
`request_validation.py`, per that module's docstring rule (D9 note in Task 1 of
the plan file).

1. **`admin_user_router.py` — `add_user`.** Thread-wrap the invitation send per D6;
   Q1 is closed, there is no design question left to resolve. The real work here is
   that **this module has no tests** — write `tests/routers/test_admin_user_router.py`
   covering the 200/409/403/422 paths, both `email_sent` branches, and the
   transaction rollback, *before* touching the handler. Build on the existing
   `FakeAuthRepo` in `tests/helpers/admin_test_helpers.py`.
2. **`admin_auth_router.py` — `login` and `verify_mfa_code`,** including the D3
   bcrypt fix. Under D9 both stay single functions, which removes the two hazards
   the review flagged for the D1 shape — `login`'s `BackgroundTasks` and
   `verify_mfa_code`'s `set_cookie` response no longer have to cross a
   shim/`_impl` boundary at all. Just change `async def` to `def` and swap the
   body read for `read_json_body(request)`.
3. **`admin_practice_router.py` and `admin_availability_router.py`** — 6 handlers,
   all the same `get_conn` transaction shape (D4). One task.
4. **`form_router.py`** — 3 handlers, and the only file needing two different
   shapes:
   - `form_init` and `form_update` take D9 (`BodyCapturingRoute` + `def`).
     **`form_init` must also move `check_availability`**, with its fail-open
     `try/except` and 503 return intact — see the table note. This is the
     patient-facing hot path and fail-open is a project invariant.
   - **`form_finish` is exempt from the route class** (D9, double-buffering). It
     becomes a plain `def` with its existing `Form(...)`/`File(...)` parameters and
     `f.file.read()`, and it keeps its `run_in_threadpool` sanitisation call — that
     call is now redundant (the handler is already on a worker thread) but harmless;
     simplify it or leave it, either is defensible.
   - Because the two shapes differ, `form_finish` needs its own router instance or
     an explicitly non-capturing route. Decide that when writing the task.
5. **`webhook_router.py` — `mailgun_webhook`.** The one handler still on D1's
   shim/`_impl` shape: it needs a parsed form with dynamic Mailgun field names,
   which neither D9's route class nor `Form(...)` declaration can supply. Per D7,
   `_impl` also takes the three accessor-resolved values as plain parameters, so
   its signature will not match anything else in the ticket.
6. **Documentation.** `arch_http_boundary.md` handler-concurrency rule, restated
   around D9: every handler is a plain `def`; body-reading ones use
   `BodyCapturingRoute` + `read_json_body`; the two exemptions are `form_finish`
   (multipart) and `mailgun_webhook` (dynamic form fields), each with its reason.
