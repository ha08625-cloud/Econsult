
Security & Compliance Architecture
LLM INSTRUCTIONS: This document defines the security boundaries, access controls, and compliance mechanisms of the Econsult system. It maps technical implementations to standard security audit requirements (such as Cyber Essentials Plus). Read this document to understand data lifecycle, authentication, and boundary defenses.
Scope
User access control, multi-factor authentication, input sanitization, malware mitigation, data retention, secure configuration enforcement, and data integrity.
Key files: app/core/dependencies.py, app/routers/admin_router.py, app/core/auth_repo.py, deletion_job.py, request_validation.py, tests/test_form_routes.py
1. User Access Control & Authentication (Admin Portal)
The patient-facing form is intentionally unauthenticated to ensure accessibility, but the Admin Portal enforces strict access controls:
 * MFA by Default: The admin portal is protected by Multi-Factor Authentication. Staff must request a login and authenticate using a time-limited secure code sent to their email.
 * Isolated MFA Delivery Pipeline: The Admin MFA code delivery utilizes a completely separate SMTP connection instance (AdminDeliveryService) from the clinical delivery path, ensuring operational isolation between authentication traffic and patient data.
 * Domain Allowlisting: The system strictly enforces an ALLOWED_ADMIN_DOMAINS environment variable. The domain of the initial admin email is validated against this list on every single startup, intentionally crashing the application if misconfigured.
 * No Default Passwords: The system does not use passwords. The legacy ADMIN_TOKEN has been replaced by MFA in production.
 * Single-Tenant Isolation: The application enforces a strict single-tenant architecture. The startup validation explicitly checks that exactly one practice exists in the database to prevent cross-contamination of patient data.
2. Secure Configuration & Fail-Fast Boundaries
The system refuses to run in an insecure or partially configured state.
 * Startup Validation: The application entry point (main.py) validates the presence of all required security, database, and email environment variables before accepting any HTTP requests. If critical infrastructure variables are missing, the process aborts.
 * The Two-Database Rule: Testing is strictly fenced from production. A hardcoded guardrail at the top of the integration test module prevents tests from running unless a dedicated TEST_DATABASE_URL is set, structurally preventing accidental test data writes or deletions against the production patient database.
 * Network Boundaries: The application is a single-container deployment hosted on Railway. The database is isolated within the cloud provider's internal network and is not directly exposed to the public internet.
3. Data Protection & Retention
Patient data is minimized, protected against concurrency flaws, and aggressively purged to reduce the impact of any potential breach.
 * Append-Only State & Concurrency Control: The in-flight RuntimeState is strictly append-only in the database. Each API request creates a new version row, protected by optimistic concurrency control (version consistency validation). This prevents race conditions, state overwrites, or session hijacking if multiple tabs are used.
 * Immutable Delivery Artifacts: Once a patient clicks submit, the finalized PDF is rendered immutable. It is stored once and used as-is for all delivery retries, guaranteeing the clinical record cannot be altered post-submission.
 * Ephemeral Storage & Nightly Deletion: Raw patient photos (submission_photos) and the finalized delivery artifact (submission_attachments) are retained only long enough to ensure delivery. A scheduled cron job (deletion_job.py) runs at midnight to permanently delete all photos and PDF attachments for submissions that have been successfully sent to the practice. Maximum retention is strictly bounded to approximately 24 hours.
 * No Cross-Session Memory: The clinical engine operates entirely on a session-backed basis. There is no conversational memory, no cross-session state, and no persistent per-user identity for patients.
4. Malware Mitigation & Input Sanitization
Because the system accepts files and free text from the public, strict validation occurs at multiple layers:
 * Independent Server-Side Enforcement: While the frontend checks file sizes, file counts, and MIME types as a usability guard, the backend server enforces these limits independently as a strict security boundary.
 * Header Verification: Before any file is written to the database, the server runs Image.open(...).verify() to validate the file header and ensure it is a legitimate image file, rather than an executable masquerading as an image.
 * Defensive Payload Checking: The PDF worker strictly validates the raw photo count fetched from the database against the declared attachment_count. If there is a mismatch (e.g., due to a dropped connection mid-upload), it fails the job immediately to prevent processing truncated or tampered payloads.
 * Input Sanitization (XSS): Admin-provided signposting text is strictly sanitized using the nh3 Python library. The system enforces that the rel attribute on <a> tags is reserved by nh3. This configuration must remain perfectly synchronized with the frontend DOMPurify allowlist to prevent Cross-Site Scripting (XSS) injection.
5. Security Update Management
Vulnerability patching is automated and enforced via CI/CD pipelines:
 * Dependency Automation: Dependabot is configured to automatically scan and update Docker base images, Python (pip) dependencies, Node/npm dependencies, and GitHub Actions weekly.
 * Synchronized Versions: Critical security libraries (like nh3 and DOMPurify) are explicitly pinned and managed to prevent divergent security rules between the frontend and backend.
