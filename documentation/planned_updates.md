Architecture updates:
- Pydantic request model migration: Replace all hand-written isinstance/type-check validation in both admin_router.py and request_validation.py with Pydantic BaseModel definitions, letting FastAPI handle JSON parsing, type coercion, and missing-field errors automatically. This also requires adding a RequestValidationError exception handler in main.py to convert Pydantic's error format into the existing {"error": {"code": ..., "message": ...}} shape, updating the frontend extractErrorDetail functions to handle any new edge cases, and retiring the unused api_models.py dataclasses.

Features
- Attach photos
- Add usual GPs
- Add front page with admin/f2f/phone call/advice choice
- retry loop
- safety rules implemented on clicking yes/no, rather than on submit form
- database-backed email delivery queue with retries
- database-backed email delivery queue with retries - add background worker
- non blocking advisory messages
- Admin portal audit trails
- Patient facing audit trails
- Add a public_slug column - More flexibility, but adds complexity
- HTTPS for web traffic
- TLS for SMTP
- encrypted database storage
- Notification architecture

Late prototype updates
- Deterministic data augmentation
- Full question sets
- UI and UX improvements
- Encoder/head training
- dockerise and cloud
runtime_id is a bearer capability
guessing or leaking it exposes PHI-adjacent data
You do not need to solve auth in Phase 6, but you should:
state that runtime_id must be unguessable
state that rate-limiting and access control are deferred but required

Test suite
Good question to ask now before real patient data exists. There is no single universal standard, but there is a well-established approach that most professional teams converge on. Let me describe it honestly, including where the theory meets pragmatic reality for a project of your size.

The conceptual model: test pyramid
The idea is that you have three layers of tests, and the ratio matters:
Unit tests — test a single function in isolation, no database, no network, run in milliseconds. You should have many of these. Your existing EditScreen.test.tsx is an example.
Integration tests — test that two or more real components work together, usually involving a real database. Slower, fewer of them. Your test_form_routes.py is an example.
End-to-end tests — test the full system through a browser. Very slow, expensive to maintain, very few of them. You do not have any yet and do not need them soon.
The mistake teams make is inverting the pyramid — writing mostly integration and E2E tests because they feel more "real", and ending up with a slow, brittle test suite.

The database problem specifically
The gold standard for integration tests that need a database is to use a dedicated, ephemeral test database that is:

Completely separate from production
Reset to a known state before each test run (or each test)
Automatically provisioned, not manually maintained

The most common way to achieve this in Python projects is pytest with a local Postgres instance via Docker. The pattern looks like this:

A conftest.py file at the top of your tests/ directory starts a Postgres container, runs your Alembic migrations against it, and tears it down when the session ends
Each test that writes data either runs in a transaction that is rolled back after the test, or the database is wiped between tests
No .env file needed — the test infrastructure creates its own database URL

The library that handles the Docker side is pytest-docker or testcontainers-python. The transaction rollback pattern uses pytest fixtures to wrap each test in a transaction that never commits.

Honest assessment for your situation
The full Docker-based setup is the right long-term answer, but it has real setup cost and is probably premature for a single-developer project at your stage. Here is what I would actually recommend doing now vs later:
Now:

Provision a second Railway database (or a free local Postgres) specifically for testing, and put its URL in .env as TEST_DATABASE_URL. You have already done the hard part — your test guardrail already enforces that TEST_DATABASE_URL must be explicitly set, so production data is protected.
Add a conftest.py that runs Alembic migrations against the test database at the start of each test session and truncates the relevant tables between tests. This is much simpler than the Docker approach and sufficient for now.

Later, before you have real patient data or a second developer:

Move to testcontainers-python so the test database is fully ephemeral and requires no manual provisioning
Add proper pytest fixtures with transaction rollback so tests are fully isolated from each other

What to prioritise for test coverage:
Right now your most important gaps are unit tests for the engine — form_logic.py, safety_engine.py, projection.py. These are pure functions with no database dependency, so they are the easiest and highest-value tests to write. A bug in the safety engine is a clinical risk. A unit test that runs in 10 milliseconds and catches that bug is worth more than any integration test.

Practical next step
If you want to pursue this, I would suggest starting with a conftest.py for test isolation and writing unit tests for the safety engine. That is a well-scoped piece of work and directly addresses the highest clinical risk. Want to plan that out?

production readiness updates
- Encryption and cybersecurity
- Data protection
- Digital clinical safety
- disclaimers
- privacy notices

### Patient facing signposting information:
Phase 1A — Practice-specific signposting: COMPLETE
- practices and practice_signposting database tables
- practice_repository.py: CRUD for practices and signposting, email validation
- presentation_service.py: composes universal safety warning + practice signposting
  + condition presentation
- condition_registry.py: pre_form_information removed; presentation block limited
  to label and free_text_prompt
- main.py: presentation endpoint updated to use PresentationService
- types.ts: ConditionPresentation updated to reflect new structure

Phase 1A.1 — Single-tenant deployment configuration: COMPLETE
- practices table: email column added (required, no default)
- practice_repository.py: email support, get_email(), count_practices(),
  InvalidEmailError
- submission_repository.py: new module, submission_records table, delivery
  status tracking
- email_service.py: new module, plain text clinical output email, DEV_MODE
  support, EmailDeliveryError
- serialisation_contracts.py: question_labels added to ClinicalOutput
- serialisation.py: clinical_output() now takes ruleset parameter, builds
  question_labels
- engine_adapters.py: finish_runtime_state returns (ClinicalOutput, AuditOutput)
  tuple
- presentation_service.py: practice_id now required (single-tenant contract)
- main.py: startup validation (PRACTICE_ID, single practice, email, SMTP);
  form/finish creates submission record and sends email; ?practice= query
  parameter removed
- app.jsx: Screen 4 patient guidance message added
- migrate_phase1a1.py: one-shot migration script for dev environments

Phase 2 — Admin endpoints: COMPLETE
- admin_context.py: AdminContext dataclass, require_admin dependency
- admin_router.py: GET/PUT/DELETE /admin/conditions/{id}/signposting,
  GET /admin/conditions
- main.py: register admin router, add app.state.registry/practice_repo,
  ADMIN_TOKEN startup check
- tests/test_admin_router.py: auth and endpoint behaviour tests
- API contracts:
    GET /admin/conditions → { conditions: [{ id, label }] }
    GET /admin/conditions/{id}/signposting → { condition_id, signposting: [] | null }
    PUT /admin/conditions/{id}/signposting → same shape as GET
    DELETE /admin/conditions/{id}/signposting → 204 no body
- Authentication: Bearer token required on all admin endpoints. Token must match
  ADMIN_TOKEN env var in production. In DEV_MODE with no ADMIN_TOKEN set, any
  non-empty token is accepted.
- types.ts has no admin types. admin.html is self-contained and does not use
  types.ts.

Phase 3 — Admin frontend: COMPLETE
- frontend/admin/admin.html: single self-contained file, React 18 + JSX via
  Babel-standalone CDN, no build step
- TokenView: token entry with connectivity check against GET /admin/conditions;
  token stored in React state only, never in localStorage
- EditorView: condition dropdown with unsaved-change detection via ref + callback
  prop pattern; confirm() dialog on condition switch with pending changes
- SignpostingEditorWithRef: full list editor per condition — load, add, delete,
  reorder, per-item blank validation, save with spinner, inline status messages
- Try/catch on all fetch calls; network errors produce inline messages, not
  browser error dialogs
- Served at /admin-portal/ via StaticFiles mount in main.py (registered after
  admin router to avoid route shadowing)
- Note: token field is a temporary placeholder, replaced entirely in Phase 5

Phase 4 — Audit trail: DEFERRED
Deferred until the product is closer to production readiness. Currently system is being used by one practice, one admin
Scope: log all signposting changes made via the admin interface for inspection
and future regulatory purposes.

Expected new artefacts:
- signposting_audit_log table with columns:
    event_id TEXT PRIMARY KEY
    practice_id TEXT NOT NULL
    condition_id TEXT NOT NULL
    action TEXT NOT NULL          -- "put" | "delete"
    token_identity TEXT           -- hash of bearer token, not raw value
    previous_value TEXT           -- JSON array or null (null on first put)
    new_value TEXT                -- JSON array or null (on delete)
    changed_at TIMESTAMP NOT NULL
- audit_repository.py: write-only append log, no update or delete operations
- admin_router.py: call audit_repository.log_event() after every successful
  PUT or DELETE (on failure the signposting change is still committed —
  a logging failure must not roll back a valid admin action)
- GET /admin/conditions/{id}/signposting/audit or similar read endpoint
  (exact shape TBD in Phase 4)

What Phase 3 intentionally does not provide for Phase 4:
- The bearer token is available in AdminContext but its raw value should not
  be logged. Phase 4 should store a hash (e.g. SHA-256 truncated) or a stable
  token alias. The identity field exists to detect "which admin session made
  this change", not to recover the token itself.
- No previous_value is captured today. Phase 4 must fetch the existing
  signposting before overwriting it in order to record the diff. The
  GET-then-PUT pattern in admin_router.py will need to become a
  GET-then-log-then-PUT sequence.

Phase 5 — Practice authentication: DEFERRED
Deferred until the product is closer to production readiness. All other
features should be complete before authentication is introduced.

Planned deliverables:
- practice_tokens table
- practice_context.py for token validation
- admin_context.py replaced in its entirety with session-based MFA
- Token-based access to admin endpoints
- auth_method field in AdminContext is a string rather than an enum
  specifically to allow Phase 5 to introduce new values without modifying
  the dataclass
