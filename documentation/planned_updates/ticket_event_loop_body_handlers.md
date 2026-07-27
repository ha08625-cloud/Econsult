# Ticket: Move blocking work off the event loop in the body-reading handlers

**Status:** Not started. Provisional plan — needs the review pass (workflow step 2)
before it is broken into tasks.

**Raised by:** `docs/implementation_plans_completed/event_loop_blocking_ticket.md`,
"Follow-up ticket to raise". The design is already settled there as D7; this ticket
carries it forward and adds one call that the parent ticket missed.

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
| `form_router.py` | `form_init` | `runtime_repo.create_initial` |
| `form_router.py` | `form_update` | `runtime_repo.get_latest`, `insert_new_version` |
| `form_router.py` | `form_finish` | `runtime_repo.get_latest`/`close_session`, `submission_repo.create_submission`, `photo_repo.save_photos`, `pdf_repo.create_job`, `practice_repo.get_email` (sanitisation is already threaded) |
| `webhook_router.py` | `mailgun_webhook` | `_consume_token` (own `get_conn`), `delivery_repo.mark_delivered` / `mark_provider_failed` / `append_provider_event` |

### Severity ordering

The 13 are not equally bad. Fix in this order if the ticket is split across
sessions:

1. **`add_user` — up to 30 seconds of stalled loop.** It calls
   `delivery_service.send_admin_invitation` directly (`admin_user_router.py:225`).
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

---

## Design decisions

**D1. Async shim awaiting the body, delegating to a sync `_impl` via
`run_in_threadpool`.** Inherited from the parent ticket's D7, unchanged. The shim
stays `async def`, does only `await request.json()` / `.body()` / `.form()` /
`f.read()`, then hands the parsed body and the injected dependencies to a plain
`def _impl` that contains everything else. All blocking work — repository calls,
`get_conn` transaction blocks, service calls — moves wholesale into `_impl`.

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

---

## Open questions for the review pass

**Q1. Should `send_admin_invitation` become a `BackgroundTask` instead of being
thread-wrapped?** There is precedent in the codebase: `login` already dispatches
the MFA email via `background_tasks.add_task(_send_mfa_code_background, ...)` for
exactly this reason, with failure cleanup inside the task. Doing the same in
`add_user` would take the mail latency out of the response entirely rather than
just off the loop.

The obstacle is the response contract. `add_user` currently returns
`{"ok": true, "email_sent": <bool>}`, and it knows `email_sent` because it waits
for the send. A background task cannot report back into a response that has
already been sent, so the field would have to become optimistic, or be dropped,
or the admin portal would need a different way to learn about delivery failure —
`resend_invitation` already exists as the recovery path. Check what the frontend
actually does with `email_sent` before deciding. Thread-wrapping is the
lower-churn option and fixes the loop-blocking regardless; the background-task
version is the better design if the contract change is acceptable.

**Q2. Is `mailgun_webhook` worth including?** It is an unauthenticated public
endpoint, which argues for fixing it, but it is called only by Mailgun and its
`_consume_token` opens its own connection outside the repository layer. Confirm
during review that moving it does not disturb the replay-protection logic.

**Q3. Does the audit-log-failure-returns-500 pattern survive the move?** Several
handlers catch an exception from `log_event` and raise `HTTPException(500, ...)`.
`run_in_threadpool` propagates exceptions from the worker thread, so raising
`HTTPException` from inside `_impl` should behave identically — but it is worth
one explicit test rather than an assumption, since it is the error path for
15 audit sites.

---

## Scope

**In scope**

- `app/routers/admin/admin_user_router.py` — `add_user`
- `app/routers/admin/admin_auth_router.py` — `login` (including the `hash_code`
  bcrypt call, D3), `verify_mfa_code`
- `app/routers/admin/admin_practice_router.py` — 3 handlers
- `app/routers/admin/admin_availability_router.py` — 3 handlers
- `app/routers/form_router.py` — 3 handlers
- `app/routers/webhook_router.py` — `mailgun_webhook` (subject to Q2)
- `documentation/arch_http_boundary.md` — extend the handler-concurrency rule to
  record the shim/`_impl` shape as the required pattern for body-reading handlers
- Router tests for each converted handler

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
- `arch_http_boundary.md` records the shim/`_impl` pattern.
- Full test suite passes, including integration tests (`make test-integration`
  with `TEST_DATABASE_URL` set, per the two-database rule in `arch_testing.md`).
- Concurrency smoke test: fire ~10 concurrent `POST /admin/auth/login` requests
  with bad credentials and confirm `GET /healthz` still answers promptly.

---

## Suggested task breakdown

One task per router file keeps each chat's context small and each diff
independently reviewable. Suggested order — severity first, then the mechanical
remainder:

1. `admin_user_router.py` — `add_user`. Resolve Q1 before starting; this is the
   30-second block and the only task with a design question attached.
2. `admin_auth_router.py` — `login` and `verify_mfa_code`, including the D3 bcrypt
   fix.
3. `admin_practice_router.py` and `admin_availability_router.py` — 6 handlers,
   all the same `get_conn` transaction shape. Can be one task.
4. `form_router.py` — 3 handlers. `form_finish` is the fiddliest: it awaits
   `UploadFile.read()` and already calls `run_in_threadpool` mid-body for
   sanitisation, so the shim must read the uploads first and pass bytes into
   `_impl`.
5. `webhook_router.py` — `mailgun_webhook`, if Q2 resolves in favour.
6. Documentation.
