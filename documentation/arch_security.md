# Security & Compliance Architecture

**LLM INSTRUCTIONS:** This document defines the security boundaries, access controls, and compliance mechanisms of the Econsult system. It maps technical implementations to standard security audit requirements (such as Cyber Essentials Plus). Read this document to understand data lifecycle, authentication, and boundary defenses.

---

## Scope

User access control, multi-factor authentication, input sanitization, malware mitigation, data retention, and secure configuration enforcement.

**Key files:** `app/core/dependencies.py`, `app/routers/admin_router.py`, `app/core/auth_repo.py`, `deletion_job.py`, `request_validation.py`

---

## 1. User Access Control & Authentication (Admin Portal)

The patient-facing form is intentionally unauthenticated to ensure accessibility, but the Admin Portal enforces strict access controls:

* **MFA by Default:** The admin portal is protected by Multi-Factor Authentication. Staff must request a login and authenticate using a time-limited secure code sent to their email.
* **Domain Allowlisting:** The system strictly enforces an `ALLOWED_ADMIN_DOMAINS` environment variable. The domain of the initial admin email is validated against this list on *every single startup*, intentionally crashing the application if misconfigured.
* **No Default Passwords:** The system does not use passwords. The legacy `ADMIN_TOKEN` has been replaced by MFA in production.
* **Single-Tenant Isolation:** The application enforces a strict single-tenant architecture. The startup validation explicitly checks that exactly one practice exists in the database to prevent cross-contamination of patient data.

## 2. Secure Configuration & Fail-Fast Boundaries

The system refuses to run in an insecure or partially configured state. 

* **Startup Validation:** The application entry point (`main.py`) validates the presence of all required security, database, and email environment variables before accepting any HTTP requests. If critical infrastructure variables are missing, the process aborts.
* **Network Boundaries:** The application is a single-container deployment hosted on Railway. The database is isolated within the cloud provider's internal network and is not directly exposed to the public internet. 

## 3. Data Protection & Retention

Patient data is minimized and aggressively purged to reduce the impact of any potential breach.

* **Ephemeral Storage:** Raw patient photos (`submission_photos`) and the finalized delivery artifact (`submission_attachments`) are retained only long enough to ensure delivery. 
* **Nightly Deletion:** A scheduled cron job (`deletion_job.py`) runs at midnight to permanently delete all photos and PDF attachments for submissions that have been successfully sent to the practice. Maximum retention is strictly bounded to approximately 24 hours.
* **No Cross-Session Memory:** The clinical engine operates entirely on a session-backed basis. There is no conversational memory, no cross-session state, and no persistent per-user identity for patients.

## 4. Malware Mitigation & Input Sanitization

Because the system accepts files and free text from the public, strict validation occurs at multiple layers:

* **File Upload Constraints:** The frontend strictly limits file sizes, file counts, and MIME types prior to upload. 
* **Header Verification:** Before any file is written to the database, the server runs `Image.open(...).verify()` to validate the file header and ensure it is a legitimate image file, rather than an executable masquerading as an image.
* **Input Sanitization (XSS):** Admin-provided signposting text is strictly sanitized using the `nh3` Python library. This configuration must remain perfectly synchronized with the frontend `DOMPurify` allowlist to prevent Cross-Site Scripting (XSS) injection.

## 5. Security Update Management

Vulnerability patching is automated and enforced via CI/CD pipelines:
* **Dependency Automation:** Dependabot is configured to automatically scan and update Docker base images, Python (pip) dependencies, Node/npm dependencies, and GitHub Actions weekly.
* **Synchronized Versions:** Critical security libraries (like `nh3` and `DOMPurify`) are explicitly pinned to prevent divergent security rules between the frontend and backend.
