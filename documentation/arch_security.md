# Security & Compliance Architecture

**LLM INSTRUCTIONS:** This document defines the security boundaries, access controls, and compliance mechanisms of the Econsult system. It maps technical implementations to standard security audit requirements (such as Cyber Essentials Plus). Read this document to understand data lifecycle, authentication, and boundary defenses.

---

## Scope

User access control, multi-factor authentication, rate limiting, input sanitization, malware mitigation, data retention, and secure configuration enforcement.

**Key files:** `dependencies.py`, `admin_router.py`, `auth_repository.py`, `auth_service.py`, `deletion_job.py`, `request_validation.py`, `image_sanitizer.py`, `form_router.py`, `rate_limit.py`, `webhook_router.py`

---

## 1. User Access Control & Authentication (Admin Portal)

The patient-facing form is intentionally unauthenticated to ensure accessibility. The Admin Portal enforces strict access controls.

- **MFA by Default.** The admin portal is protected by Multi-Factor Authentication. Staff must request a login code and authenticate using a time-limited secure code sent to their registered email address.
- **Isolated MFA Delivery Pipeline.** Admin MFA code delivery uses a completely separate service instance from the clinical delivery path, ensuring operational isolation between authentication traffic and patient data. In production this is MailgunHttpAdminDeliveryService; the SMTP equivalent AdminDeliveryService is available for deployments where SMTP is not blocked.
- **Domain Allowlisting.** The system enforces an `ALLOWED_ADMIN_DOMAINS` environment variable. The domain of the authenticating admin email is validated against this list on every login attempt. The application also validates this configuration at startup and aborts if it is absent or malformed.
- **No Default Passwords.** The system does not use passwords. The legacy `ADMIN_TOKEN` has been replaced by MFA in production.
- **Single-Tenant Isolation.** The application enforces a strict single-tenant architecture. Startup validation explicitly checks that exactly one practice exists in the database, preventing cross-contamination of patient data if the database is misconfigured.
- **Manual Admin User Provisioning.** The first admin user must be inserted before the application starts using `scripts/create_admin_user.py`. The application will refuse to start if no admin users exist for the practice. This replaces the previous `INITIAL_ADMIN_EMAIL` seeding mechanism, which has been removed. Additional users can be added via the admin UI once the system is running.

---

## 2. Secure Configuration & Fail-Fast Boundaries

The system refuses to run in an insecure or partially configured state.

- **Startup Validation.** The application entry point (`main.py`) validates the presence of all required security, database, and email environment variables before accepting any HTTP requests. Missing critical variables cause the process to abort rather than silently degrade.
- **Webhook Signing Key Enforcement.** When `MAILGUN_API_KEY` is set (i.e. Mailgun is the delivery provider), `MAILGUN_SIGNING_KEY` is also required at startup. Absent this key the webhook endpoint cannot verify HMAC signatures, which would allow any party to forge delivery events. The application aborts startup if `MAILGUN_API_KEY` is present but `MAILGUN_SIGNING_KEY` is not.
- **The Two-Database Rule.** Testing is strictly fenced from production. A hardcoded guardrail at the top of every integration test module prevents tests from running unless a dedicated `TEST_DATABASE_URL` environment variable is set. This structurally prevents accidental test data writes or deletions against the production patient database.
- **Network Boundaries.** The application is a single-container deployment hosted on Railway. The database is isolated within the cloud provider's internal network and is not directly exposed to the public internet.
- **Third-Party Observability (Sentry) — PII Lockdown.** Sentry is an external service. Its initialisation enforces strict data minimisation controls to prevent clinical data from leaving the system boundary:
  - **Backend (`telemetry.py`):** `send_default_pii=False`, `request_bodies="never"`, `with_locals=False`. The `request_bodies="never"` setting is the critical control — it drops multipart payloads containing raw clinical JSON and patient photos at the ASGI layer before Sentry can capture them. Worker processes additionally set `traces_sample_rate=0.0` to prevent infinite worker loops from being instrumented as transactions.
  - **Frontend (`main.tsx`):** Performance tracing is disabled (`tracesSampleRate: 0`). The `BrowserTracing`, `Breadcrumbs`, `GlobalHandlers`, `LinkedErrors`, `HttpContext`, and `Dedupe` integrations are explicitly removed from the SDK defaults, preventing DOM interaction tracking, SPA navigation recording, and URL parameter capture. A `beforeBreadcrumb` hook drops the request body size field for POST requests to `/form/update` and `/form/finish`. The `ErrorBoundary`'s `beforeCapture` hook strips React component props and state from error events, preventing patient answers held in transient UI state from being serialised and transmitted.
  - **Test isolation.** Sentry initialisation is bypassed entirely in all test environments (pytest presence, `TEST_DATABASE_URL` set, `DEV_MODE=1` on the backend; `import.meta.env.DEV` or `MODE === 'test'` on the frontend). This prevents test suite HTTP requests to Sentry's ingestion endpoints and eliminates the possibility of test data reaching Sentry's servers.
  - **Safety isolation invariant.** Triggered safety rules are successful, deterministic clinical operations. They are explicitly excluded from Sentry reporting. The backend `ignore_errors` list includes `APIError`, `ConditionNotFound`, `RateLimitError`, and `slowapi.errors.RateLimitExceeded` to suppress expected 4xx responses. Both rate limit exception types must be present: `RateLimitError` covers the service-layer per-email cooldown; `RateLimitExceeded` covers requests rejected by the SlowAPI IP-based limiter. The frontend `triggerFatalError` function must never be called from safety message handling paths.

---

## 3. Data Protection & Retention

Patient data is minimised, protected against concurrency flaws, and aggressively purged to reduce the impact of any potential breach.

- **Append-Only State & Concurrency Control.** In-flight `RuntimeState` is strictly append-only in the database. Each API request creates a new version row, protected by optimistic concurrency control (version consistency validation). This prevents race conditions, state overwrites, or session hijacking if multiple browser tabs are used.
- **Immutable Delivery Artifacts.** Once a patient clicks submit, the finalised PDF is rendered immutable. It is stored once and used as-is for all delivery retries, guaranteeing the clinical record cannot be altered post-submission.
- **Ephemeral Storage & Nightly Deletion.** Raw patient photos (`submission_photos`) and the finalised delivery artifact (`submission_attachments`) are retained only long enough to ensure delivery. A scheduled cron job (`deletion_job.py`) runs at midnight to permanently delete all photos and PDF attachments for submissions where `delivery_jobs.status = 'delivered'`. Maximum retention is strictly bounded to approximately 24 hours for the Mailgun webhook path. See `arch_submission.md` Known Limitations for the SMTP path and `provider_accepted` edge cases.
- **No Cross-Session Memory.** The clinical engine operates entirely on a session-backed basis. There is no conversational memory, no cross-session state, and no persistent per-user identity for patients.

---

## 4. Malware Mitigation & File Upload Security

Because the system accepts files and free text from the public, strict validation and sanitization occurs at multiple layers.

- **Independent Server-Side Enforcement.** The frontend checks file sizes, file counts, and MIME types as a usability guard only. The backend server enforces all limits independently as a strict security boundary, including a server-side count check that is the primary enforcement point (FastAPI does not enforce count limits on `list[UploadFile]`).

- **Image Content Disarm and Reconstruction (CDR).** Before any uploaded photo is written to the database, the server applies CDR via `app/utils/image_sanitizer.py`. Every image is fully decoded by Pillow and re-encoded from scratch as a JPEG. This provides the following guarantees:

  - **Full-decode validation.** The previous approach used `Image.open(...).verify()`, which checks the file header only. A file with a valid header but a corrupt or truncated body would pass that check but then fail during PDF generation, leaving the submission in a degraded state. CDR performs a full decode, catching corrupt bodies at the router before any database write occurs.
  - **Metadata stripping.** EXIF data, ICC profiles, and all other metadata are discarded. The output buffer is written entirely from the decoded pixel values.
  - **Format normalisation.** Output is always JPEG regardless of whether the input was JPEG or PNG. All bytes stored in `submission_photos` are sanitized JPEG.
  - **Structural polyglot defence.** A polyglot file embeds a second payload (such as executable code) in regions Pillow ignores — for example, bytes appended after the JPEG end-of-image marker. Because CDR re-encodes from the decoded pixel buffer rather than forwarding the original bytes, any such payload is discarded and never reaches the database or the PDF worker.

- **Post-Sanitization Size Re-Validation.** After CDR, the router re-validates each image against the per-file and combined size limits. This is necessary because re-encoding an already-compressed JPEG can marginally increase its size. The invariant that stored bytes are within declared limits is maintained.

- **Defensive Photo Count Check (PDF Worker).** The PDF worker validates the raw photo count fetched from the database against the declared `attachment_count` on the `pdf_jobs` row. A mismatch (for example, caused by a dropped connection mid-upload) causes the job to fail immediately rather than process a truncated payload.

- **Input Sanitization (XSS).** The XSS surface has two distinct paths, each handled differently:

  - **Signposting (admin-authored HTML).** This is the only path where content is rendered as HTML in the browser. Admin-provided signposting text is sanitized using `nh3` on the backend before storage, with a strict tag and attribute allowlist (`p`, `strong`, `em`, `a`, `ul`, `ol`, `li`, `br`; `href`, `rel`, `target` on `<a>` only; `http`/`https` URL schemes only). On the frontend, `DOMPurify.sanitize()` with `SIGNPOSTING_PURIFY_CONFIG` is applied again before rendering via `dangerouslySetInnerHTML`. The two allowlists are kept explicitly synchronised. `nh3` automatically injects `rel="noopener noreferrer"` on `<a>` tags; the `DOMPurify` config must preserve `rel` to avoid stripping this on render.
  - **Patient free text.** The patient free text field (`FreeTextScreen`) uses React's standard controlled `textarea` (value/onChange). React escapes all content as plain text — it never renders free text as HTML. There is no `dangerouslySetInnerHTML` involved in this path. No additional sanitization is applied or required, as the data is stored and rendered as plain text throughout (including in the PDF output).

- **PDF Output — Injection Risk.** The PDF formatter (`pdf_formatter.py`) uses `fpdf2`. Patient-supplied strings are passed directly to `cell()`, `multi_cell()`, and `body_text()` calls. This is safe: PDF is a binary format, not a markup language, and `fpdf2` does not use its optional HTML rendering mode anywhere in the codebase. There is no mechanism by which text content in a PDF cell can execute code. XSS sanitization is not applicable to this output path. The relevant threat model for PDFs (embedded JavaScript via interactive form fields or PDF actions) does not apply here as no such features are used.

- **Webhook Endpoint Security.** The Mailgun webhook endpoint (`POST /webhooks/mailgun`) is a public-facing endpoint. It is secured by three independent controls: timestamp staleness check (>15 minutes dropped), HMAC-SHA256 signature verification using `MAILGUN_SIGNING_KEY`, and token-based replay protection backed by the `webhook_tokens` database table. See `arch_submission.md` for the full webhook security model.

---

## 5. Rate Limiting

Brute-force and enumeration attacks are mitigated at the HTTP boundary using SlowAPI (`app/core/rate_limit.py`), wired into the application via `SlowAPIMiddleware` in `main.py`.

**Key file:** `rate_limit.py`

### Admin MFA endpoints — 5 requests/minute per IP

`POST /admin/auth/request-code` and `POST /admin/auth/verify` are both decorated with `@limiter.limit("5/minute")`. These are the only unauthenticated endpoints that interact with credentials, making them the primary brute-force surface.

The IP limit is one layer of a defence-in-depth stack. Two independent service-layer controls also apply:

- `auth_service.request_mfa_code` enforces a **60-second per-email cooldown** backed by the database (`last_requested_at`). This survives process restarts and fires before the slowapi counter is relevant for single-machine attacks.
- `auth_service.verify_mfa_code` enforces a **3-attempt per-email lockout** backed by the database (`attempts_count`). Exceeding this deletes the code and requires a fresh request cycle.

The IP limit adds protection against a distributed attack cycling through different email addresses faster than the per-email cooldowns can engage.

**Audit evasion accepted:** SlowAPI rejects excess requests before they reach the `audit_repo.log_event` call. This is intentional — the database audit log is for clinical admin staff monitoring business actions. Brute-force traffic is visible in stdout logs and Sentry for the technical team.

### Patient-facing endpoints — 30 requests/minute per IP

All endpoints in `public_router.py` and `form_router.py` are decorated with `@limiter.limit("30/minute")`. This provides baseline protection against automated scraping or submission flooding. The limit is intentionally generous to accommodate scenarios where multiple patients share a single NAT IP (care home, public library) without violating the Fail-Open Availability invariant.

### Webhook endpoint

The webhook endpoint (`POST /webhooks/mailgun`) is covered by the SlowAPI middleware. No dedicated rate limit decorator is applied — the middleware provides baseline protection and the HMAC security boundary is the primary control against illegitimate traffic.

### IP extraction

The limiter uses `extract_ip` from `app/core/http_utils.py` as its key function rather than SlowAPI's built-in `get_remote_address`. This is necessary because Railway sits behind a reverse proxy — `request.client.host` always resolves to the proxy IP. `extract_ip` correctly reads `X-Forwarded-For` and `X-Real-IP` headers to obtain the real client IP.

### Storage

In-memory storage (`limits.storage.MemoryStorage`) is used deliberately. The deployment is a single web worker. Redis would add operational overhead with no benefit at this scale. Counters reset on process restart, which is acceptable — a restart clears a brief window of protection, but the service-layer database-backed controls remain active throughout.

### Error envelope

When SlowAPI rejects a request it raises `slowapi.errors.RateLimitExceeded`. A custom handler in `main.py` catches this and returns the standard error envelope: `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."}}` with HTTP 429. This is consistent with the existing `RateLimitError` handler so the frontend always receives the same shape regardless of which layer fired the limit.

---

## 6. Security Update Management

Vulnerability patching is automated and enforced via CI/CD pipelines.

- **Dependency Automation.** Dependabot is configured to automatically scan and propose updates for Docker base images, Python (`pip`) dependencies, Node/npm dependencies, and GitHub Actions on a weekly schedule.
- **Synchronised Security Libraries.** Critical security libraries (`nh3` and `DOMPurify`) are explicitly pinned. Version changes require deliberate synchronisation between the frontend and backend allowlists.