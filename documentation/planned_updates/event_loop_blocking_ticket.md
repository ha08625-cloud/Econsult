# Plan

**Ticket:** Event-loop blocking and proxy header trust.

## Context

Two problems at the HTTP boundary, combined into one ticket because the second is
the control that bounds the first.

1. Every route handler and the `require_admin` dependency are `async def`, while
   all database access is blocking psycopg2. Blocking work runs directly on the
   single event loop, so concurrent requests serialise behind it.
2. `extract_ip` returns the **leftmost** `X-Forwarded-For` entry, which is
   whatever the client sent. This defeats every per-IP rate limit and makes all
   15 audit-log IP addresses forgeable.

Together, one machine can hold the event loop for 300 ms per request indefinitely
via unauthenticated `POST /admin/auth/login` (`_fixed_delay` sleeps 300 ms on
every attempt), taking the patient form offline. Fixing the async problem alone
converts "one request stalls everything" into "40 concurrent requests exhaust the
threadpool" — the rate limiter is what actually bounds it, so the proxy fix lands
first.

Outcome: blocking work runs in the threadpool instead of on the loop, and per-IP
rate limiting becomes trustworthy.

### What changed since the provisional plan

Both prerequisites were resolved during review, without a deployment:

- **P1 answered — no longer blocking.** slowapi 0.1.9 **does** rate-limit plain
  `def` handlers. Verified by running slowapi 0.1.9 + fastapi 0.136.3 with
  `SlowAPIMiddleware` installed: a `def` handler under `@limiter.limit("2/minute")`
  returned `[200, 200, 429]`, and ran on an `AnyIO worker thread`. Task 4 stays at
  20 handlers.
- **P2 largely answered — the hop-count constant is dropped.** Reading uvicorn
  0.40.0's source: `proxy_headers` defaults to `True` but `forwarded_allow_ips`
  resolves to `"127.0.0.1"`, and nothing in this repo sets it. Railway's edge
  reaches the container over the private network, not loopback, so
  `ProxyHeadersMiddleware` almost certainly never fires and `request.client.host`
  is the Railway proxy — **identical for every client**. That kills the original
  design's fallback (see D3). uvicorn's own `_TrustedHosts.get_trusted_client_host`
  walks `X-Forwarded-For` from the **right**, which is the correct algorithm; this
  plan implements the same walk with a trust predicate that needs no configuration.

---

# Scope

**In scope**

- `app/utils/http_utils.py` — proxy header trust model
- `app/core/rate_limit.py` — detection of failed IP resolution
- `app/core/admin_context.py` — `require_admin` to plain `def`
- `app/routers/form_router.py` — image sanitisation off the loop
- `app/routers/admin/admin_auth_router.py` — auth service calls off the loop
- `app/services/admin/auth_service.py` — docstrings only, no behaviour change
- The 20 route handlers that do not read the request body: convert to plain `def`
- New `tests/test_http_utils.py`
- Documentation updates

**Explicitly out of scope**

- The 15 handlers that read the request body (`await request.json()`,
  `request.body()`, `request.form()`, `UploadFile.read()`). They remain
  `async def` with blocking DB calls on the loop. Follow-up ticket — see D7.
- Replacing psycopg2 with an async driver. Rejected — see D6.
- Adding `--workers` to the uvicorn command. Rejected — see D5.
- `connect_timeout` / statement timeout in `db.py`. Separate ticket.
- `main.py`'s `/healthz` handler. It is `async def` but touches no database, so
  it is harmless. Mentioned only so the next reader does not file it as a
  violation of the new rule.

**Done when**

- `extract_ip` ignores attacker-supplied `X-Forwarded-For` entries, with unit
  test coverage (it currently has none).
- `require_admin` and the 20 no-body handlers are plain `def`.
- Image sanitisation and the auth service calls run via `run_in_threadpool`.
- The five architecture documents record the concurrency rule and the trust model.
- Full test suite passes; the deployed app resolves real client IPs correctly.

---

# Design Decisions

**D1. Resolve the client IP by walking `X-Forwarded-For` from the right, trusting
an entry only if it is globally routable.**

Proxies *append* to `X-Forwarded-For`, so the trustworthy entry is at the right
end, not the left. Rather than hard-coding how many hops to skip, walk right to
left and return the first entry that is a valid, globally-routable IP address,
using stdlib `ipaddress`. Railway's internal proxy addresses are private
(`10.0.0.0/8`, `fd00::/8`); real client addresses arriving over the public
internet are global. `ipaddress.ip_address(s).is_global` correctly excludes
private, loopback, link-local, CGNAT (`100.64.0.0/10`) and documentation ranges —
verified.

Why this beats a fixed hop count: it is robust to Railway changing its internal
topology, and it cannot be silently invalidated by adding an internal hop. An
attacker cannot defeat it by spoofing, because they cannot append an entry *after*
the one Railway adds — any value they inject ends up to the left of the real one.

This is a *superseding* decision: the provisional plan's D5 (module-level hop
constant) and its associated `deployment_checklist.md` warning are dropped. A CDN
in front of Railway would still break this (the CDN's public IP would become the
rightmost global entry), so that caveat is retained and documented.

**D2. Keep the logic in `extract_ip`; leave uvicorn's proxy settings at their
defaults.**

Do not set `FORWARDED_ALLOW_IPS` or add `--proxy-headers` to the Dockerfile CMD.
Two reasons. First, `FORWARDED_ALLOW_IPS="*"` — the obvious value to reach for on
Railway — sets uvicorn's `always_trust` flag, which returns
`x_forwarded_for_hosts[0]`, the **leftmost** entry. That is exactly as spoofable
as the bug being fixed, and it would look like a fix. Second, keeping resolution
in one pure function means the app stays correct even if someone sets that
variable later, because `extract_ip` does its own parsing and does not depend on
`request.client.host` being rewritten.

**D3. Falling back to `client_host` is a detectable degraded state, not a safe
default.**

If resolution fails, `client_host` is the Railway proxy — the same value for every
client — so every caller collapses into one rate-limit bucket. The `5/minute`
limit on the auth endpoints would then become global: one attacker locks out every
admin. This is an availability regression, so it must be *detected*, not silently
tolerated. `extract_ip` still returns `client_host` as a last resort (it is the
only thing actually known), and `_ip_key` in `rate_limit.py` logs an ERROR when the
resolved IP equals `request.client.host`, which is the signature of this failure.

Detection lives in `rate_limit.py`, not `http_utils.py`, because
`file_structure.md` requires `app/utils/` to be pure with no IO.

**D4. No signature change to `extract_ip`.**

All 16 call sites pass `(request.headers, request.client.host if request.client
else None)` — 15 audit-log sites plus `_ip_key`. Changing only the function body
fixes every call site with zero churn and preserves the "utils are pure, stdlib
only" rule.

**D5. Do not add `--workers` to uvicorn.**

`rate_limit.py` documents in-memory slowapi storage on the explicit assumption of a
single web worker. N workers would silently multiply every rate limit by N, and
would shard loop blocking rather than fix it.

**D6. Do not migrate to an async driver.**

The `conn=conn` transaction-passing convention runs through every repository and
every mutating router. An async rewrite touches all of it to solve a concurrency
ceiling this deployment will not reach.

**D7. Do not use Pydantic body models to make the body-reading handlers sync.**

`request_validation.py` produces a specific error envelope that the frontend and a
large number of tests depend on; Pydantic would replace it with its own 422 shape.
Recorded here for the follow-up ticket, where the recommended approach is an
`async def` shim that awaits the body then delegates to a sync `_impl` via
`run_in_threadpool`.

**D8. Keep the anyio threadpool at its default size (40).**

Tasks 2, 3 and 4 all newly route through this pool: `require_admin` on every
authenticated request, 20 handlers, and `_fixed_delay`'s 300 ms sleep. Forty
concurrent logins can hold every token for 300 ms and starve the admin portal.
Raising `total_tokens` is a one-line change but there is no evidence it is needed —
the rate limiter is the intended ceiling, **which is why Task 1 lands first**. This
is an ordering constraint, not a preference.

**D9. Documentation path note.**

The docs directory on disk is `documentation/`, but `README.md`, `architecture.md`
and the spoke documents all cross-reference each other as `docs/...`. Edit files at
`documentation/<name>.md`; keep writing cross-references as `docs/<name>.md` to
match the existing convention.

---

# Task 3: CPU-bound work off the event loop

**A. State of the world**

Tasks 1 and 2 are complete: the IP trust model is fixed and `require_admin` runs
in the threadpool.

Two pieces of blocking work remain on the loop inside handlers that must stay
`async def` because they read the request body:

- **Image sanitisation** (`form_router.py:296-305`). Up to 5 photos; the `high`
  tier runs up to three full 4K decode/resize/re-encode cycles per photo.
  Plausibly seconds of frozen loop, on the patient-facing critical path.
- **`auth_service` calls** from `admin_auth_router.py`. `_fixed_delay`
  (`auth_service.py:107`) is a deliberate `time.sleep()` enforcing a 300 ms floor
  on every auth attempt for timing-attack resistance, plus bcrypt on top. The
  module docstring already anticipates this fix and suggests `run_in_executor`.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/routers/form_router.py` | Sanitisation loop extracted to a module-level sync helper, called via `run_in_threadpool`. |
| `app/routers/admin/admin_auth_router.py` | `auth_service` entry points wrapped in `run_in_threadpool`. |
| `app/services/admin/auth_service.py` | Docstring updates only. No behaviour change. |

**C. Instructions**

1. In `app/routers/form_router.py`, extract the loop at lines 296-305 into a
   module-level sync helper (e.g. `_sanitize_photos(photo_bytes, tier)`) returning
   the sanitised list. Call it with
   `await run_in_threadpool(_sanitize_photos, photo_bytes, effective_tier)`.
   Import from `starlette.concurrency`.

   Preserve the per-index error messages exactly — `INVALID_PAYLOAD(str(exc))` for
   `ImageTooLargeError` and `f"Photo {i + 1} is not a valid image"` for
   `ValueError`. Document in the helper's docstring that it deliberately raises
   `HTTPException` across the threadpool boundary; this works (exceptions
   propagate from `run_in_threadpool` unchanged) but is unusual for a helper that
   otherwise looks pure, so it needs stating.

   Leave the post-sanitisation size checks at lines 307-315 on the loop — they are
   cheap.

   **Known gap, accept and state it:** `form_finish` still performs its submission,
   PDF-job and photo writes on the loop. Out of scope for this ticket.

2. In `app/routers/admin/admin_auth_router.py`, wrap the `auth_service` entry
   points in `run_in_threadpool`: `verify_login_credentials`, `verify_mfa_code`,
   `set_new_password`, and the reset-request path. Use `functools.partial` or
   positional arguments as the existing call shapes require.

   This moves both bcrypt and `_fixed_delay`'s `time.sleep` off the loop. The
   timing-attack mitigation is unaffected: it depends on wall-clock elapsed time
   measured with `time.monotonic()`, which does not care which thread it runs on.

3. Update two stale docstrings in `app/services/admin/auth_service.py`:
   - The `bcrypt note` (lines 34-38) says "If this ever becomes a performance
     concern, wrap calls in `run_in_executor` from the async router." Change it to
     record that the router now does this.
   - `_fixed_delay`'s docstring (lines 111-117) justifies `time.sleep` over
     `asyncio.sleep` on the grounds that moving to `run_in_executor` would be
     needed for the whole function. That is now exactly what happens. Rewrite it
     to say the caller runs this in the threadpool, so `time.sleep` is correct and
     must stay.

4. Run `make test`. Pay attention to `tests/routers/test_admin_auth_router.py` —
   `arch_testing.md` notes that `TestMFARateLimiting` patches `auth_service`
   functions, and patched targets must still be reached through the
   `run_in_threadpool` call.

---

# Task 4: Convert the 20 no-body handlers to plain `def`

**A. State of the world**

Tasks 1-3 are complete: IP trust is fixed, `require_admin` is sync, and the
CPU-bound work in `form_finish` and the auth router runs in the threadpool.

35 route handlers exist across 8 router files. 20 of them never read the request
body and are `async def` purely by habit, so their blocking psycopg2 calls run on
the event loop. Converting them to plain `def` moves them to the threadpool.

**Prerequisite already resolved:** slowapi 0.1.9 rate-limits plain `def` handlers
correctly. Verified during plan review with `SlowAPIMiddleware` installed — a `def`
handler under `@limiter.limit("2/minute")` returned `[200, 200, 429]` and ran on an
AnyIO worker thread. The 6 rate-limited public endpoints and `resend_invitation`
can all be converted.

**B. Files and deliverables**

| File | Handlers to convert |
|---|---|
| `app/routers/public_router.py` | 6 — all of them (lines 56, 65, 74, 86, 109, 133) |
| `app/routers/admin/admin_practice_router.py` | 5 (lines 92, 109, 217, 334, 390) |
| `app/routers/admin/admin_availability_router.py` | 4 (lines 150, 473, 533, 702) |
| `app/routers/admin/admin_user_router.py` | 3 (lines 75, 267, 334) |
| `app/routers/admin/admin_audit_router.py` | 1 (line 23) |
| `app/routers/admin/admin_auth_router.py` | 1 — `logout` (line 461) |

**C. Instructions**

1. For each handler listed above, change `async def` to `def`. Nothing else — no
   body changes, no signature changes, no decorator changes.

2. Before converting each one, confirm it contains no `await`. The line numbers
   above are from an inventory taken during planning and may have shifted; the
   check that matters is the absence of `await` in the body, not the line number.
   The 15 handlers **not** listed all contain one of `await request.json()`,
   `await request.body()`, `await request.form()`, or `await f.read()`, and must
   stay `async def`.

3. Do **not** convert `main.py`'s `/healthz` handler. It is out of scope and
   touches no database.

4. Run the full test suite including integration tests
   (`make test-integration` or `pytest -m integration`, which needs
   `TEST_DATABASE_URL` set — see `arch_testing.md`'s two-database rule).

---

# Task 5: Documentation

**A. State of the world**

Tasks 1-4 are complete. All code changes are in. This task records the design
decisions so the next reader does not undo them.

Per `CLAUDE.md`: record design decisions and data flows, do not duplicate what is
readable from the code. Per D9: the directory on disk is `documentation/`, but
cross-references between docs are written as `docs/...` — follow the existing
convention.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `documentation/arch_http_boundary.md` | New handler-concurrency rule. |
| `documentation/arch_security.md` | Proxy trust model in §6; update §2 timing-attack note. |
| `documentation/deployment_checklist.md` | CDN caveat. |
| `documentation/arch_infrastructure.md` | Cross-reference from the psycopg2 section. |
| `documentation/arch_testing.md` | Register `tests/test_http_utils.py`. |

**C. Instructions**

1. `arch_http_boundary.md` — add to the "Architectural Rules (Strictly Enforced)"
   section: handlers that do not read the request body are plain `def`; handlers
   that do remain `async def` and must delegate blocking work to the threadpool
   via `run_in_threadpool`. State the reason — all DB access is blocking psycopg2,
   so an `async def` handler executes its queries on the event loop and serialises
   every concurrent request. Note that `require_admin` is sync for the same
   reason, and that `/healthz` is the one exempt `async def` because it touches no
   database.

2. `arch_security.md` §6, "Storage and IP extraction" — replace the current
   one-line mention with the trust model: proxies append to `X-Forwarded-For`, so
   the leftmost entry is client-supplied and forgeable; `extract_ip` walks the
   header right to left and returns the first globally-routable address. Record
   that uvicorn's `ProxyHeadersMiddleware` is deliberately left at its defaults
   and that `FORWARDED_ALLOW_IPS="*"` must **not** be set, because uvicorn's
   `always_trust` path returns the leftmost entry and would silently reintroduce
   the bug (D2). Note the degraded-state ERROR log from `_ip_key` and what it
   means (D3).

3. `arch_security.md` §2 — the closing line currently reads "Uses `time.sleep`
   (not `asyncio.sleep`) because all repository calls are synchronous psycopg2.
   Revisit with `run_in_executor` if concurrent load becomes a concern." Update
   it: the router now calls these functions via `run_in_threadpool`, so
   `time.sleep` is correct and the 300 ms floor is unaffected because it is
   measured on wall-clock time.

4. `deployment_checklist.md` — add a note that IP resolution assumes Railway is
   the only proxy in front of the app. Inserting a CDN would make the CDN's public
   IP the rightmost globally-routable entry in `X-Forwarded-For`, silently
   breaking per-IP rate limiting and audit-log IPs, and would require revisiting
   `extract_ip`.

5. `arch_infrastructure.md` — add a cross-reference from the existing psycopg2
   section to the new handler-concurrency rule in `docs/arch_http_boundary.md`.

6. `arch_testing.md` — add `tests/test_http_utils.py` to the "Python unit tests
   (`tests/`)" index with a one-line description.

7. Per the Test Maintenance Obligation in `architecture.md`: `test_http_utils.py`
   is a unit test, so it needs no `integration` marker and no `ci.yml` or
   `Makefile` change.

---

# Verification

1. **Unit tests:** `make test` — `tests/test_http_utils.py` is the main new
   coverage. Confirm no regressions in `tests/routers/` (the auth router tests
   patch `auth_service` functions that are now called through
   `run_in_threadpool`) or `tests/test_admin_context.py` (which pins
   `admin_context`'s import surface in a subprocess).
2. **Integration tests:** `make test-integration` with `TEST_DATABASE_URL` set to
   the separate test database, per `arch_testing.md`'s two-database rule. This is
   the real check on Task 4 — 20 handlers changed execution model.
3. **Rate limiting still fires:** the existing `TestMFARateLimiting` tests cover
   the auth endpoints. `conftest.py`'s autouse `reset_rate_limiter` fixture keeps
   counters from leaking between tests.
4. **Deploy and confirm the trust model.** The system is not yet live, so this is
   low-risk. After deploying to Railway, hit an admin auth endpoint twice from a
   known public IP — once clean, once sending a forged
   `X-Forwarded-For: 1.2.3.4` — and check the `admin_audit_log` rows. Both must
   record the real public IP, not `1.2.3.4`. Then check the logs for the ERROR
   from `_ip_key`: its absence confirms resolution is working; its presence means
   Railway is not appending as assumed and `extract_ip` needs revisiting before
   the rate limiter can be trusted.
5. **Concurrency smoke test (optional but cheap):** fire ~10 concurrent
   `POST /admin/auth/login` requests with bad credentials and confirm
   `GET /healthz` still responds promptly. Before this ticket they would have
   queued behind 300 ms of `time.sleep` each.

---

# Follow-up ticket to raise

**Move blocking DB work off the loop in the 15 body-reading handlers.** They
remain `async def` with blocking psycopg2 calls on the event loop. The design is
already settled in D7: an `async def` shim that awaits the body, then delegates to
a sync `_impl` via `run_in_threadpool`. Pydantic body models are rejected because
they would replace the `request_validation.py` error envelope that the frontend
and many tests depend on. Raise this now, while the reasoning is fresh.


---

# Task 1: Proxy header trust model

**A. State of the world**

Nothing in this ticket has been completed yet. This is the first task and the rest
depend on it landing first (D8).

`app/utils/http_utils.py` contains a single function, `extract_ip`, which returns
`headers["x-forwarded-for"].split(",")[0].strip()` — the leftmost entry, which is
attacker-controlled. It has **no test coverage at all** despite being
security-critical: no file in `tests/` references `extract_ip` or
`x-forwarded-for`. It is called from 16 places, all passing the same two arguments.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/utils/http_utils.py` | Rewritten `extract_ip` body per D1. Signature unchanged. Docstring header corrected. |
| `app/core/rate_limit.py` | ERROR log in `_ip_key` when IP resolution degrades (D3); corrected module-path reference; comment pinning the `request` parameter name. |
| `app/repositories/audit_repository.py` | Corrected module-path reference in the comment at line 85. |
| `tests/test_http_utils.py` | New table-driven unit test file. |

**C. Instructions**

1. Rewrite the body of `extract_ip` in `app/utils/http_utils.py`. Keep the
   signature `(headers, client_host: str | None) -> str | None`. Import
   `ipaddress` (stdlib — this does not violate the purity rule in
   `file_structure.md`). Resolution order:
   - Split `x-forwarded-for` on commas and strip each entry. Iterate **in
     reverse**. Return the first entry that parses as an IP address and has
     `.is_global` true.
   - If that yields nothing, apply the same validity check to `x-real-ip`.
   - Otherwise return `client_host or None`.

   Malformed entries must be skipped, not raise — `ipaddress.ip_address()` raises
   `ValueError` on junk, so guard each entry.

2. Rewrite the docstring to explain *why* the walk is right-to-left (proxies
   append; the leftmost entry is client-supplied) and why the trust predicate is
   "globally routable" rather than a hop count. State the one thing that breaks
   it: a CDN placed in front of Railway, whose public IP would become the
   rightmost global entry.

3. Fix the stale module path in the docstring header at
   `app/utils/http_utils.py:2` — it reads `app/core/http_utils.py`. The same wrong
   path appears at `app/core/rate_limit.py:16` and
   `app/repositories/audit_repository.py:85`. Fix all three.

4. In `_ip_key` (`app/core/rate_limit.py`), after calling `extract_ip`, log at
   ERROR level if the resolved value is non-None and equal to
   `request.client.host`. That equality is the signature of D3's degraded state —
   every client sharing one rate-limit bucket. Keep the existing `or "unknown"`
   fallback. Add a module-level `logger = logging.getLogger(__name__)` if absent.

5. Add a comment above `_ip_key` recording a slowapi landmine found during review:
   `slowapi/extension.py:496` dispatches on `inspect.signature(lim.key_func)`
   containing a parameter named **literally** `request`. Ours is named correctly.
   Renaming it drops slowapi to calling `key_func()` with no arguments, which
   raises `TypeError`.

6. Write `tests/test_http_utils.py` as a table-driven unit test. This is a unit
   test — do **not** add `pytestmark = pytest.mark.integration`. Cases:
   - Spoofed leftmost entry ignored: `"1.2.3.4, 8.8.8.8"` resolves to `8.8.8.8`.
   - Spoofed **private** leftmost entry ignored: `"10.0.0.1, 8.8.8.8"` → `8.8.8.8`.
   - Private proxy hops on the right are skipped:
     `"8.8.8.8, 10.0.0.1, 10.0.0.2"` → `8.8.8.8`.
   - Single global entry returned as-is.
   - All entries private → falls through to `x-real-ip`, then `client_host`.
   - Malformed entries (`"junk, 8.8.8.8"`, empty strings, stray whitespace) do not
     raise.
   - No headers at all → `client_host`.
   - Nothing determinable → `None`.

   **Important:** use genuinely globally-routable addresses in the fixtures
   (`8.8.8.8`, `1.1.1.1`). The RFC 5737 documentation ranges — `192.0.2.0/24`,
   `198.51.100.0/24`, `203.0.113.0/24` — are the natural choice for test data but
   `is_global` returns **False** for all of them, so tests written with those
   would fail confusingly.

7. Run `make test` (or `pytest -m "not integration"`). Existing tests assert
   `ip_address=None` only, so regression risk is low.


---

# Task 2: `require_admin` to plain `def`

**A. State of the world**

Task 1 is complete: `extract_ip` now resolves real client IPs and per-IP rate
limiting is trustworthy.

`require_admin` in `app/core/admin_context.py:139` is `async def` but makes two
blocking psycopg2 calls — `get_session_context` and `update_session_expiry` — on
every authenticated admin request. Both run directly on the event loop. FastAPI
runs *sync* dependencies in the threadpool, so changing the keyword is the whole
fix.

**B. Files and deliverables**

| File | Deliverable |
|---|---|
| `app/core/admin_context.py` | `async def require_admin` → `def require_admin`; docstring records why it is deliberately sync. |

**C. Instructions**

1. Change `async def require_admin(...)` to `def require_admin(...)` at
   `app/core/admin_context.py:139`. No other change to the function body — there
   is no `await` in it.

2. Add a short paragraph to the module docstring stating that `require_admin` is
   deliberately a sync `def` so FastAPI resolves it in the threadpool, because
   `get_session_context` and `update_session_expiry` are blocking psycopg2 calls
   that would otherwise stall the event loop on every authenticated request.

3. All callers use `Depends(require_admin)`, and `tests/test_admin_context.py`
   exercises it through the app rather than awaiting it directly — confirmed, no
   test changes expected. Run `make test` to verify.
