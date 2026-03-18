# Econsult System Architecture (Hub)

**LLM INSTRUCTIONS:** This is the master map of the system. Do NOT assume architectural details. Use this document to understand the global invariants and locate the specific domain documentation (Spokes). Read the codebase files directly for implementation details (function signatures, schemas, etc.).  All codebase files exist in Claude's project files and are directly accessible.  Claude project files mostly have flat file names for simplicity - full paths are used only if there is ambiguity e.g. frontend/index.html vs frontend/admin-ui/index.html.  See file_structure.md for the definitive file structure

## 1. Project-Level Invariants (Strictly Enforced)

These rules apply universally and MUST NOT be violated by any new feature or refactor:

* **Declarative Clinical Meaning:** Clinical meaning lives *only* in declarative JSON rulesets, never in code.
* **Deterministic Core:** The engine interprets rulesets deterministically (functional core).
* **Imperative Shell:** The UI renders engine output statelessly; it contains no clinical logic.
* **Encoder Boundaries:** Encoder models output signals; they do *not* make decisions. Encoder-filled answers must NEVER overwrite patient answers.
* **Safety Isolation:** Safety netting advice comes exclusively from deterministically coded rules in the ruleset using simple IF/AND/OR logic. Safety logic never mutates state.
* **Fail-Open Availability:** Any failure in the availability check (database, network, logic) MUST fail-open and allow the patient to proceed.
* **State & Session Constraints:** The system is session-backed and server-owned. There is NO conversational memory, NO cross-session state, and NO per-user identity. State is never round-tripped through the client or mutated in place.
* **Fail-Fast Configuration:** A misconfigured deployment (missing env vars, invalid rulesets, database state violations) MUST abort at startup. It must never silently degrade into a state where forms are sent to the wrong destination or safety rules are skipped.

## 2. High-Level Data Flow

The system is a server-owned, session-backed pipeline composed of strictly separated modules. No module other than the pipeline is aware of execution order.

**Request Pipeline:**
`HTTP Boundary (validation)` -> `Pipeline (ordering)` -> `Form Logic (deterministic core)` -> `Serialization (views)` -> `Persistence (lossless RuntimeState)`

## 3. Capability Index (Domain Routing)

When modifying or adding features, locate the relevant capability below to identify the associated Domain Architecture Document and key files.

### 3.1 Core Engine & Clinical Logic
* **Scope:** Contains core data flows for form initialization and submission, ruleset loading, applying patient answers, projecting state. 
* **Domain Doc:** `arch_core_engine.md`
* **Key Files:** `form_logic.py`, `runtime_state.py`, `ruleset.py`, `condition_registry.py`, `engine_adapters.py`

### 3.2 Clinical Safety & Projection
* **Scope:** Evaluating explicit patient answers against safety rules, blocking submissions.
* **Domain Doc:** `arch_safety.md`
* **Key Files:** `safety_engine.py`, `projection.py`, `explicit_answers.py`

### 3.3 Encoder & ML Boundary
* **Scope:** Prompting encoders, mapping ML signals to answers, enforcing provenance.
* **Domain Doc:** `arch_encoder.md`
* **Key Files:** `encoder_mapping.py`, `encoder_stub.py`, `encoder_contracts.py`

### 3.4 Practice Availability & Scheduling
* **Scope:** Weekly opening hours, per-date exceptions, manual overrides, fail-open logic.
* **Domain Doc:** `arch_availability.md`
* **Key Files:** `availability_service.py`, `availability_repository.py`, `availability_models.py`

### 3.5 Submission, Serialization & Delivery
* **Scope:** Finalizing forms, auditing, persisting submission records, sending emails.
* **Domain Doc:** `arch_submission.md`
* **Key Files:** `serialization.py`, `serialisation_contracts.py`, `submission_repository.py`, `email_service.py`

### 3.6 Frontend (Patient UI & Search)
* **Scope:** Stateless React rendering, condition search, combobox, fetching APIs.
* **Domain Doc:** `arch_frontend.md`
* **Key Files:** `App.tsx`, `api.ts`, `types.ts`, `search.ts`, `ConditionCombobox.tsx`

### 3.7 Admin Portal & Configuration
* **Scope:** Admin authentication, editing signposting, configuring availability. All admin errors use `APIError` constructors from `errors.py`; the only `HTTPException` in this domain is the 401 in `admin_context.py`.
* **Domain Doc:** `arch_admin.md`
* **Key Files:** `admin_router.py`, `admin_context.py`, `practice_repository.py`, `errors.py`, `frontend/admin-ui/src/api.ts`, `frontend/admin-ui/src/types.ts`

### 3.8 HTTP Orchestration & App Entry
* **Scope:** FastAPI application, startup fail-fast validation, routing, error translation. The `api_error_handler` (registered in `main.py`) translates all `APIError` exceptions to HTTP 422 JSON responses.
* **Domain Doc:** `arch_http_boundary.md`
* **Key Files:** `main.py`, `request_validation.py`, `errors.py`

### 3.9 API Boundary & Presentation
* **Scope:** Composing pre-session presentation data.
* **Domain Doc:** `arch_presentation.md`
* **Key Files:** `presentation_service.py`

### 3.10 Clinical Ruleset Schema
* **Scope:** Layout and constraints for the clinical ruleset schemas
* **Domain Doc:** `arch_ruleset_schema.md`
* **Key Files:** Found in /data/ directory

### 3.11 Infrastructure, Database & Deployment
* **Scope:** Railway deployment configurations, the Dockerfile multi-stage build (Vite + Python), static file serving logic, Alembic database migrations, required environment variables, and Postgres/JSONB data quirks.
* **Domain Doc:** `arch_infrastructure.md`
* **Key Files:** `Dockerfile`, `db.py`, `alembic_env.py`, `main.py` (for static serving mounts).
