# Security & Compliance Architecture

**LLM INSTRUCTIONS:** This document defines the security boundaries, access controls, and compliance mechanisms of the Econsult system. It maps technical implementations to standard security audit requirements (such as Cyber Essentials Plus). Read this document to understand data lifecycle, authentication, and boundary defenses.

---

## Scope

User access control, multi-factor authentication, rate limiting, input sanitization, malware mitigation, data retention, secure configuration enforcement, and outbound integration TLS.

**Key files:** `dependencies.py`, `admin_router.py`, `auth_repository.py`, `auth_service.py`, `deletion_job.py`, `request_validation.py`, `image_sanitizer.py`, `form_router.py`, `rate_limit.py`, `webhook_router.py`

---

## 1. User Access Control & Authentication (Admin Portal)

The patient-facing form is intentionally unauthenticated to ensure accessibility. The Admin Portal enforces strict access controls.

- **Two-Factor Authentication.** The admin portal uses password + email OTP (2FA). Login is a two-step flow: email and password are submitted first; if correct, a time-limited one-time code is generated and emailed; the code is then submitted to complete authentication and issue a session cookie. A session is only issued after both factors pass.

- **Sliding Session Expiry.** Sessions use a 60-minute sliding TTL, not a fixed absolute one: every authenticated request that passes `require_admin` extends `expires_at` by another 60 minutes and re-issues the `httponly`/`secure`/`samesite=strict` session cookie, so an actively-used session never lapses mid-work. There is no absolute session cap — an admin who stays continuously active can remain logged in indefinitely. The refresh is best-effort (logged on failure, request proceeds) since a database outage would already have failed the session-validation step that precedes it.

- **Password Requirements.** Passwords must be between 12 and 128 characters and achieve a minimum zxcvbn score of 3 ("good"). The same threshold is enforced independently on both the frontend (disabling the submit button) and the backend (`set_new_password` in `auth_service.py`). On the backend, if the score is below threshold, the specific zxcvbn feedback string is returned to the user as `WEAK_PASSWORD` (HTTP 422). This provides actionable guidance rather than a generic rejection.

- **Password Storage.** Passwords are hashed with bcrypt (cost factor from `bcrypt.gensalt()` defaults). Raw passwords are never stored or logged. The `hashed_password` column on `admin_users` is `NULL` for newly invited accounts that have not yet completed setup.

- **Account Lockout.** Three consecutive wrong passwords lock the account for 15 minutes (`password_locked_until` on `admin_users`). The lockout timestamp is set atomically with the third failed attempt in a single UPDATE. The attempt counter is reset to 0 on successful password verification and on any successful `set_password` call.

- **`password_changed_at` Audit Field.** Every time a new password is stored, `password_changed_at` is updated atomically by `AuthRepository.set_password`. This field is required for Cyber Essentials Plus compliance auditing. It is never set by any other method.

- **Isolated MFA Delivery Pipeline.** Admin MFA code delivery uses a completely separate service instance from the clinical delivery path, ensuring operational isolation between authentication traffic and patient data. In production this is `MailgunHttpAdminDeliveryService`; the SMTP equivalent `AdminDeliveryService` is available for deployments where SMTP is not blocked.

- **Background Task OTP Delivery with Cleanup.** The OTP is generated and written to the database synchronously before the 200 response is returned to the client. The email is then dispatched as a FastAPI `BackgroundTask`. If background delivery fails, the exception is reported to Sentry and the OTP record is deleted from the database. This cleanup ensures the 60-second cooldown does not block an immediate retry when no code was delivered.

- **Domain Allowlisting.** The system enforces an `ALLOWED_ADMIN_DOMAINS` environment variable. The domain of the authenticating admin email is validated against this list on every login attempt. The application validates this configuration at startup and aborts if it is absent or malformed.

- **No Default Credentials.** Newly created accounts have `hashed_password = NULL`. They cannot be used to log in until the user follows their setup link and sets a password. There is no default or temporary password path.

- **Single-Tenant Isolation.** Startup validation explicitly checks that exactly one practice exists in the database, preventing cross-contamination of patient data if the database is misconfigured.

- **Manual Admin User Provisioning.** The first admin user must be inserted before the application starts using `scripts/create_admin_user.py`. After inserting the user, the script generates a one-time setup token and prints the setup URL to stdout. The operator must forward this URL to the user. The application will refuse to start if no admin users exist for the practice.

---

## 2. Timing Attack Mitigation

Both `verify_mfa_code` and `verify_login_credentials` in `auth_service.py` enforce a minimum response time of 300ms (`_MIN_RESPONSE_SECONDS`) using `_fixed_delay(start)`, where `start = time.monotonic()` is captured at the top of the function.

`verify_login_credentials` additionally mitigates CPU-timing leaks from bcrypt:

All fast checks (user lookup, cooldown, lockout, no-password guard) are evaluated first and their outcomes are recorded in a `should_use_real_hash` flag. A single `bcrypt.checkpw()` call is then executed unconditionally — against the real `hashed_password` on the success path, or against a module-level `_DUMMY_HASH` (a bcrypt hash of a static string, computed at import time) on all failure paths. `_fixed_delay(start)` is called immediately after this bcrypt call, before any branching on the result. This means:

- An attacker cannot distinguish "user not found" from "wrong password" via response time (the dummy bcrypt runs in the same CPU time as the real one).
- The minimum 300ms window is always measured from before bcrypt, so bcrypt's CPU cost is inside the window, not additional to it.

Uses `time.sleep` (not `asyncio.sleep`) because all repository calls are synchronous psycopg2. The router (`admin_auth_router.py`) calls these `auth_service` entry points via `run_in_threadpool`, so `time.sleep` is correct and must stay — the 300ms floor is measured on wall-clock time via `time.monotonic()`, which is unaffected by which thread it runs on.

---

## 3. Secure Configuration & Fail-Fast Boundaries

The system refuses to run in an insecure or partially configured state.

- **Startup Validation.** The application entry point (`main.py`) validates the presence of all required security, database, and email environment variables before accepting any HTTP requests. Missing critical variables cause the process to abort rather than silently degrade.
- **Webhook Signing Key Enforcement.** When `MAILGUN_API_KEY` is set, `MAILGUN_SIGNING_KEY` is also required at startup.
- **The Two-Database Rule.** A hardcoded guardrail at the top of every integration test module prevents tests from running unless a dedicated `TEST_DATABASE_URL` environment variable is set.
- **Network Boundaries.** The application runs as four Railway services from a single Docker image (see docs/arch_infrastructure.md, Process Topology).  Containers run as an unprivileged user (appuser); the application filesystem is root-owned and effectively read-only to the process.
- **Third-Party Observability (Sentry) — PII Lockdown.** Sentry initialisation enforces strict data minimisation controls:
  - **Backend (`telemetry.py`):** `send_default_pii=False`, `request_bodies="never"`, `with_locals=False`.
  - **Frontend (`main.tsx`):** Performance tracing disabled. `BrowserTracing`, `Breadcrumbs`, `GlobalHandlers`, `LinkedErrors`, `HttpContext`, and `Dedupe` integrations explicitly removed. A `beforeBreadcrumb` hook drops request body size for POST requests to `/form/update` and `/form/finish`. The `ErrorBoundary`'s `beforeCapture` hook strips React component props and state.
  - **Test isolation.** Sentry initialisation is bypassed in all test environments.
  - **Safety isolation invariant.** `APIError`, `ConditionNotFound`, `RateLimitError`, and `slowapi.errors.RateLimitExceeded` are in `ignore_errors` to suppress expected 4xx responses.

---

## 4. Data Protection & Retention

- **Append-Only State & Concurrency Control.** In-flight `RuntimeState` is strictly append-only. Each API request creates a new version row protected by optimistic concurrency control.
- **Immutable Delivery Artifacts.** The finalised PDF is rendered immutable once a patient submits.
- **Ephemeral Storage & Nightly Deletion.** Raw patient photos and PDF attachments are deleted by a scheduled cron job at midnight for all delivered submissions.
- **No Cross-Session Memory.** No conversational memory, no cross-session state, no persistent per-user identity for patients.

---

## 5. Malware Mitigation & File Upload Security

- **Independent Server-Side Enforcement.** The frontend file size and MIME type checks are usability guards only. The backend enforces all limits independently.
- **Image Content Disarm and Reconstruction (CDR).** Every uploaded photo is fully decoded by Pillow and re-encoded from scratch as JPEG, discarding EXIF and all metadata. The sanitizer is tier-aware: output resolution and quality are controlled by the submission tier passed from `form_router.py`. A quality iteration fallback enforces the EMIS 5 MB output limit for high-tier submissions.
- **Post-Sanitization Size Re-Validation.** After CDR, each image is re-validated against size limits. Re-encoding an already-compressed JPEG can marginally increase its size; this check maintains the invariant that stored bytes are within the declared limits.
- **Defensive Photo Count Check (PDF Worker).** The PDF worker validates the raw photo count against `attachment_count` on the `pdf_jobs` row.
- **Input Sanitization (XSS).** Signposting (admin-authored HTML) is sanitized with `nh3` on the backend and `DOMPurify` on the frontend, with synchronised allowlists. Patient free text is stored and rendered as plain text throughout — no HTML rendering path exists.
- **PDF Output — Injection Risk.** `fpdf2` does not use HTML rendering mode. PDF cell content cannot execute code.
- **Webhook Endpoint Security.** Timestamp staleness check (>15 minutes dropped), HMAC-SHA256 signature verification, and token-based replay protection.

---

## 6. Rate Limiting

Brute-force and enumeration attacks are mitigated at the HTTP boundary using SlowAPI (`app/core/rate_limit.py`).

### Admin auth endpoints — 5 requests/minute per IP

`POST /admin/auth/login`, `POST /admin/auth/verify`, `POST /admin/auth/request-reset`, and `POST /admin/auth/set-password` are all decorated with `@limiter.limit("5/minute")`.

The IP limit is one layer of a defence-in-depth stack. Additional service-layer controls apply:

- `verify_login_credentials` enforces a **60-second per-email OTP cooldown** (checked before password verification so a 429 cannot confirm a correct password guess) and a **3-attempt / 15-minute password lockout**, both backed by the database.
- `verify_mfa_code` enforces a **3-attempt per-email OTP lockout** backed by `admin_auth_codes.attempts_count`.
- `request-reset` always returns 200 regardless of whether the email is registered, and applies `_fixed_delay()` to prevent DB I/O timing leaks.

The IP limit adds protection against distributed attacks cycling through different email addresses faster than per-email controls engage.

### Patient-facing endpoints — 30 requests/minute per IP

All endpoints in `public_router.py` and `form_router.py` are decorated with `@limiter.limit("30/minute")`.

### Storage and IP extraction

In-memory storage (`limits.storage.MemoryStorage`) is used deliberately — single worker, no Redis overhead. `extract_ip` from `http_utils.py` is used as the key function to correctly handle Railway's reverse proxy headers.

**Trust model.** Proxies *append* to `X-Forwarded-For`, so the leftmost entry is whatever the client sent — attacker-controlled — and the trustworthy entry is at the right end. `extract_ip` walks the header right to left and returns the first entry that parses as an IP address and is globally routable (`ipaddress.ip_address(s).is_global`), which correctly excludes Railway's private internal-network addresses (`10.0.0.0/8`, `fd00::/8`) along with loopback, link-local, CGNAT, and documentation ranges. This needs no configured hop count: it is robust to Railway changing its internal topology, and an attacker cannot defeat it because they cannot inject an entry to the right of the one Railway appends. If no entry qualifies, `x-real-ip` is tried, then the raw `client_host`. The one thing that breaks this: a CDN placed in front of Railway, whose public IP would become the rightmost globally-routable entry (see `docs/deployment_checklist.md`).

Uvicorn's `ProxyHeadersMiddleware` is deliberately left at its defaults. `FORWARDED_ALLOW_IPS="*"` must **not** be set — it enables uvicorn's `always_trust` path, which returns the *leftmost* `X-Forwarded-For` entry and would silently reintroduce the exact spoofing bug this trust model fixes. Keeping resolution entirely inside `extract_ip` means the app stays correct even if that variable is set later.

**Degraded-state detection.** If resolution falls all the way through to `client_host`, that value is the Railway proxy — identical for every client — so every caller would collapse into one rate-limit bucket, turning the 5/minute admin auth limit into a global one. `_ip_key` in `rate_limit.py` logs an ERROR when the resolved IP equals `request.client.host`, which is the signature of this failure. Absence of that log confirms IP resolution is working as designed.

### Error envelope

SlowAPI rejections return `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."}}` with HTTP 429, consistent with the `RateLimitError` handler.

---

## 7. Security Update Management

- **Dependency Automation.** Dependabot scans Docker base images, Python, Node/npm, and GitHub Actions dependencies on a weekly schedule.
- **Vulnerability Scan Gate (CE+).** `security-scan.yml` builds the production Docker image and scans it with Trivy on every push and pull request to `main`. The scan fails the pipeline (`exit-code: 1`) on any HIGH or CRITICAL finding (CVSS >= 7.0) that has a fix available; `ignore-unfixed: true` prevents the pipeline from blocking on vulnerabilities with no released patch. Because this scans the built image rather than a manifest, it covers OS/base-image packages as well as the pinned Python dependencies in `requirements.txt` — including transitive ones such as `starlette` under `fastapi`. This complements Dependabot rather than duplicating it: Dependabot proposes update PRs, the Trivy gate blocks any merge that would ship a fixable HIGH/CRITICAL CVE. The `aquasecurity/trivy-action` pin is held at v0.35.0 or higher following the March 2026 trivy-action supply-chain compromise.
- **Synchronised Security Libraries.** `nh3` and `DOMPurify` are explicitly pinned. Version changes require deliberate synchronisation between the frontend and backend allowlists. `zxcvbn-ts` packages (`@zxcvbn-ts/core`, `@zxcvbn-ts/language-en`, `@zxcvbn-ts/language-common`) and the Python `zxcvbn` library must be kept at compatible versions — the minimum score threshold (3) is enforced on both sides independently, so a major library change that redefines score semantics would require coordinated updates.

---

## 8. MESH Outbound TLS

MESH integration uses mutual TLS (mTLS) at every environment — sandbox, integration, and production. There is no special-case skip for sandbox; the worker unconditionally presents a client certificate and unconditionally verifies the server certificate against a configured CA bundle.

- **Strict path inputs, no toggles.** `MeshClient` accepts three mandatory string paths: a CA bundle (`ca_cert_path`), a client certificate (`client_cert_path`), and a client private key (`client_key_path`). All three are typed as `str` — never `None`, never optional. There is no boolean to disable verification and no environment-name-driven bypass. Misconfiguration cannot accidentally degrade to one-way TLS or to plain HTTPS.

- **Fail-fast at worker startup.** Before the MESH worker process instantiates `MeshClient` or attempts the MESH handshake, it validates that all three env vars (`MESH_CA_CERT_PATH`, `MESH_CLIENT_CERT_PATH`, `MESH_CLIENT_KEY_PATH`) are set and that the files they point to exist on disk. Missing env var or missing file aborts startup with a clear log line identifying the missing input. (Implementation in `mesh_worker_main.py`, landing in Phase 3 of the MESH integration plan.)

- **Sandbox parity via an nginx mTLS proxy.** The NHSDigital `mesh-sandbox` container does not enforce mTLS natively: its uvicorn process is launched with `--ssl-certfile` and `--ssl-keyfile` only, with no `--ssl-ca-certs` or `--ssl-cert-reqs`, and the image exposes no env var to enable client-cert verification. Local mTLS parity is therefore achieved by placing an nginx TLS-terminating proxy in front of the sandbox container. nginx validates the worker's client cert against a local dev CA and proxies plain HTTP to the sandbox on an internal docker network. This means the production mTLS code path is exercised on every local sandbox call. See `sandbox/docker-compose.yml` and `sandbox/nginx/nginx.conf`.

- **Committed dev PKI.** The dev CA, server cert, and client cert under `sandbox/certs/` are deliberately committed to the repository. They sign nothing the outside world trusts and are accepted only by the local nginx proxy. Rationale, regeneration procedure, and the rule "never commit real NHS certs here" are documented in `sandbox/certs/README.md`.

- **Production cert handling.** Real NHS certs are operational secrets. They are stored as Railway secrets, mounted as files at container startup, and pointed to by the three env vars above. They must never be generated by `sandbox/certs/generate.sh` and must never be committed. Cert rotation is an operator action: replace the cert files at the configured paths and restart the worker process so the `MeshClient`'s underlying `requests.Session` is rebuilt with the new material.

- **Parity limits.** nginx-fronted mTLS catches the common mTLS bugs: failing to present a cert, presenting a cert signed by the wrong CA, or failing to verify the server cert against the expected CA. It does not catch Spine-specific behaviours such as cipher-suite restrictions, peer-cert subject-DN validation, or revocation checks. First contact with the NHS PTL environment may still surface issues invisible to the sandbox; this is an accepted limitation of any local mTLS emulation.