### Architecture updates:
- Pydantic request model migration: Replace all hand-written isinstance/type-check validation in both admin_router.py and request_validation.py with Pydantic BaseModel definitions, letting FastAPI handle JSON parsing, type coercion, and missing-field errors automatically. This also requires adding a RequestValidationError exception handler in main.py to convert Pydantic's error format into the existing {"error": {"code": ..., "message": ...}} shape, updating the frontend extractErrorDetail functions to handle any new edge cases, and retiring the unused api_models.py dataclasses.

### Updates
- add alerting via Sentry
- papertrail logging
- remove submissions after 7 days
- add new end object DebugOutput with no confidential info
- Add backup alternative SMTP provider 
- Add a public_slug column - More flexibility, but adds complexity
- HTTPS for web traffic
- TLS for SMTP
- encrypted database storage
- Notification architecture
- safety rules implemented on clicking yes/no, rather than on submit form (defer - big feature change and we need to know if blocking safety rules are desired or not)

### Admin portal updates
- IP-based rate limiting via `slowapi` — separate ticket
- Multiple admin users or role-based access control beyond the `role` field in the schema
- Staff vs admin role enforcement in router handlers (schema supports it, enforcement is not implemented)
- Session refresh / sliding expiry
- Passowrds for true MFA

### Encoder updates
- Deterministic data augmentation
- Full question sets
- Encoder/head training

### production readiness updates
- MHRA registration - econsult health is registered as a class I medical device (technically anything that acts as patient triage is class 2a but we want to avoid that)
- Encryption and cybersecurity
- Data protection
- Digital clinical safety
- disclaimers
- privacy notices
- SOPs
- developer on retainer
- contract with confidentiality clause (they cannot share the code), a non-compete clause (they cannot build a competing product using your work), and an assignment clause (anything they build for you belongs to you, not them).

### multi-tenancy updates

Alerting
The industry standard for a solo developer on a small production system is Sentry on the free tier. You add roughly five lines of code to your FastAPI startup, and any unhandled exception or explicit sentry_sdk.capture_message() call with a critical level sends you an email. It integrates with Python in about ten minutes. The alternative many solo developers use is a simple email alert via the logging handler — Python's logging.handlers.SMTPHandler can email you directly on CRITICAL-level log events, and you already have SMTP configured in this project, so the infrastructure is already there.
My honest opinion: for a medical system, before you go live with real patient data, some form of proactive alerting is not optional. Discovering a delivery failure by checking logs manually is not acceptable when the thing failing to deliver is a patient's clinical submission to their GP.

GitHub Token
Never store it in a text file on your desktop, a notepad, or anywhere in your project files. The industry standard is a password manager — 1Password, Bitwarden (free tier available), or similar. You store the token once, it's encrypted at rest, and you retrieve it when needed. Bitwarden is a reasonable free starting point for a solo developer. The secondary rule is: if a token is ever accidentally committed or exposed in any document, treat it as compromised and regenerate it immediately regardless of whether you think anyone saw it.

Database Backups
Railway's paid plans include automated daily backups with point-in-time recovery. The industry standard question to answer is: what is your recovery point objective (how much data can you afford to lose) and your recovery time objective (how long can the system be down). For a GP econsult system, losing even one submission is clinically significant. You should verify Railway's backup retention period, test that you can actually restore from a backup before going live, and document the restore procedure. "Test the restore" is the part almost everyone skips and the part that matters most — a backup you've never tested is not a backup you can rely on.
Deployment Rollback
The industry standard for a small Railway deployment is a documented runbook, not an automated rollback system. That means a short text document that says: if a deployment breaks production, here are the exact steps — how to revert to the previous git commit, how to run alembic downgrade -1 against production, how to redeploy the previous container. The key insight is that you write this when things are working, not when they're broken. A solo developer at 11pm with a broken deployment and no written procedure is in a genuinely bad position.
test_public_routes.py
The pragmatic fix is to add the same TEST_DATABASE_URL guardrail that your other integration tests already have. It's five lines of code at the top of the file and makes it consistent with everything else. This is a small but real maintenance risk and worth fixing before the test suite grows.