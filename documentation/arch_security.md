# Security & Compliance Architecture

**LLM INSTRUCTIONS:** This document defines the security boundaries, access controls, and compliance mechanisms of the Econsult system. It maps technical implementations to standard security audit requirements (such as Cyber Essentials Plus). Read this document to understand data lifecycle, authentication, and boundary defenses.

---

## Scope

User access control, multi-factor authentication, input sanitization, malware mitigation, data retention, and secure configuration enforcement.

**Key files:** `dependencies.py`, `admin_router.py`, `auth_repository.py`, `auth_service.py`, `deletion_job.py`, `request_validation.py`, `image_sanitizer.py`, `form_router.py`

---

## 1. User Access Control & Authentication (Admin Portal)

The patient-facing form is intentionally unauthenticated to ensure accessibility. The Admin Portal enforces strict access controls.

- **MFA by Default.** The admin portal is protected by Multi-Factor Authentication. Staff must request a login code and authenticate using a time-limited secure code sent to their registered email address.
- **Isolated MFA Delivery Pipeline.** Admin MFA code delivery uses a completely separate service instance from the clinical delivery path, ensuring operational isolation between authentication traffic and patient data. In production this is MailgunHttpAdminDeliveryService; the SMTP equivalent AdminDeliveryService is available for deployments where SMTP is not blocked.
- **Domain Allowlisting.** The system enforces an `ALLOWED_ADMIN_DOMAINS` environment variable. The domain of the authenticating admin email is validated against this list on every login attempt. The application also validates this configuration at startup and aborts if it is absent or malformed.
- **No Default Passwords.** The system does not use passwords. The legacy `ADMIN_TOKEN` has been replaced by MFA in production.
- **Single-Tenant Isolation.** The application enforces a strict single-tenant architecture. Startup validation explicitly checks that exactly one practice exists in the database, preventing cross-contamination of patient data if the database is misconfigured.

---

## 2. Secure Configuration & Fail-Fast Boundaries

The system refuses to run in an insecure or partially configured state.

- **Startup Validation.** The application entry point (`main.py`) validates the presence of all required security, database, and email environment variables before accepting any HTTP requests. Missing critical variables cause the process to abort rather than silently degrade.
- **The Two-Database Rule.** Testing is strictly fenced from production. A hardcoded guardrail at the top of every integration test module prevents tests from running unless a dedicated `TEST_DATABASE_URL` environment variable is set. This structurally prevents accidental test data writes or deletions against the production patient database.
- **Network Boundaries.** The application is a single-container deployment hosted on Railway. The database is isolated within the cloud provider's internal network and is not directly exposed to the public internet.

---

## 3. Data Protection & Retention

Patient data is minimised, protected against concurrency flaws, and aggressively purged to reduce the impact of any potential breach.

- **Append-Only State & Concurrency Control.** In-flight `RuntimeState` is strictly append-only in the database. Each API request creates a new version row, protected by optimistic concurrency control (version consistency validation). This prevents race conditions, state overwrites, or session hijacking if multiple browser tabs are used.
- **Immutable Delivery Artifacts.** Once a patient clicks submit, the finalised PDF is rendered immutable. It is stored once and used as-is for all delivery retries, guaranteeing the clinical record cannot be altered post-submission.
- **Ephemeral Storage & Nightly Deletion.** Raw patient photos (`submission_photos`) and the finalised delivery artifact (`submission_attachments`) are retained only long enough to ensure delivery. A scheduled cron job (`deletion_job.py`) runs at midnight to permanently delete all photos and PDF attachments for submissions that have been successfully delivered. Maximum retention is strictly bounded to approximately 24 hours.
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

---

## 5. Security Update Management

Vulnerability patching is automated and enforced via CI/CD pipelines.

- **Dependency Automation.** Dependabot is configured to automatically scan and propose updates for Docker base images, Python (`pip`) dependencies, Node/npm dependencies, and GitHub Actions on a weekly schedule.
- **Synchronised Security Libraries.** Critical security libraries (`nh3` and `DOMPurify`) are explicitly pinned. Version changes require deliberate synchronisation between the frontend and backend allowlists.
