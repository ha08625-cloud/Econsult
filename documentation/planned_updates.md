Architecture updates:
- split frontend/src/App.tsx
- split main.py

Features
- Form for someone else, e.g. a child
- PDF generation
- add personal information e.g. name, DOB
- retry loop
- safety rules implemented on clicking yes/no, rather than on submit form
- database-backed email delivery queue with retries
- non blocking advisory messages
- Attach photos
- Add a public_slug column - More flexibility, but adds complexity
- HTTPS for web traffic
- TLS for SMTP
- encrypted database storage

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
