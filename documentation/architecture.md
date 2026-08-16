# Econsult System Architecture (Hub)

This is the master map of the system. Do NOT assume architectural details. Use this document to understand the global invariants and locate the specific domain documentation (Spokes). Read the codebase files directly for implementation details (function signatures, schemas, etc.).  All codebase files exist in Claude's project files and are directly accessible.  Claude project files mostly have flat file names for simplicity - full paths are used only if there is ambiguity e.g. frontend/index.html vs frontend/admin-ui/index.html.  See file_structure.md for the definitive file structure

## 1. Project-Level Invariants

These rules apply universally and MUST NOT be violated by any new feature or refactor:

* **Declarative Clinical Meaning:** Clinical meaning lives *only* in declarative JSON rulesets, never in code.
* **Deterministic Core:** The engine interprets rulesets deterministically (functional core).
* **Imperative Shell:** The UI renders engine output statelessly; it contains no clinical logic.
* **Encoder Boundaries:** Encoder models output signals; they do *not* make decisions. Encoder-filled answers must NEVER overwrite patient answers.
* **Safety Isolation:** Safety netting advice comes exclusively from deterministically coded rules in the ruleset using simple IF/AND/OR logic. Safety logic never mutates state.
* **Fail-Open Availability:** Any failure in the availability check (database, network, logic) MUST fail-open and allow the patient to proceed.
* **State & Session Constraints:** The system is session-backed and server-owned. There is NO conversational memory, NO cross-session state, and NO per-user identity. State is never round-tripped through the client or mutated in place.
* **Fail-Fast Configuration:** A misconfigured deployment (missing env vars, invalid rulesets, database state violations) MUST abort at startup. It must never silently degrade into a state where forms are sent to the wrong destination or safety rules are skipped.
* **Test Maintenance Obligation:** Whenever a test file is created or modified, prompt the user to: (1) add `pytestmark = pytest.mark.integration` if it is an integration test, (2) verify `arch_testing.md` is up to date. No changes to `ci.yml` or `Makefile` are needed if the marker is present — pytest discovers integration tests automatically via the marker.

## 2. High-Level Data Flow

The system is a server-owned, session-backed pipeline composed of strictly separated modules. No module other than the pipeline is aware of execution order.

**Request Pipeline:**
`HTTP Boundary (validation)` -> `Pipeline (ordering)` -> `Form Logic (deterministic core)` -> `Serialization (views)` -> `Persistence (lossless RuntimeState)`

## 3. Capability Index (Domain Routing)

When modifying or adding features, locate the relevant capability below to identify the associated Domain Architecture Document and key files.

### 3.1 Core Engine & Clinical Logic
* **Scope:** Contains core data flows for form initialization and submission, ruleset loading, applying patient answers, projecting state. 
* **Domain Doc:** `docs/arch_core_engine.md`
* **Key Files:** `form_logic.py`, `runtime_state.py`, `ruleset.py`, `condition_registry.py`, `pipeline.py`, `unit_conversion.py`

### 3.2 Clinical Safety & Projection
* **Scope:** Evaluating explicit patient answers against safety rules, blocking submissions.
* **Domain Doc:** `docs/arch_safety.md`
* **Key Files:** `safety_engine.py`, `projection.py`, `explicit_answers.py`

### 3.3 Encoder & ML Boundary
* **Scope:** Prompting encoders, mapping ML signals to answers, enforcing provenance.
* **Domain Doc:** `docs/arch_encoder.md`
* **Key Files:** `encoder_mapping.py`, `encoder_stub.py`, `encoder_contracts.py`

### 3.4 Practice Availability & Scheduling
* **Scope:** Weekly opening hours, per-date exceptions, manual overrides, fail-open logic.
* **Domain Doc:** `docs/arch_availability.md`
* **Key Files:** `availability_service.py`, `availability_repository.py`, `availability_models.py`

### 3.5 Submission, Serialization & Delivery
* **Scope:** Finalizing forms, auditing, persisting submission records, PDF generation, attachment storage, sending emails (Mailgun/SMTP path). NHS MESH transport is a separate spoke — see 3.14.
* **Domain Doc:** `docs/arch_submission.md`
* **Key Files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `attachment_repository.py`, `delivery_service.py`, `pdf_formatter.py`

### 3.6 Frontend (Patient UI & Search)
* **Scope:** Stateless React rendering, condition search, combobox, fetching APIs.
* **Domain Doc:** `docs/arch_frontend.md`
* **Key Files:** `App.tsx`, `api.ts`, `types.ts`, `search.ts`, `ConditionCombobox.tsx`

### 3.7 Admin Portal & Configuration
* **Scope:** Admin authentication, editing signposting, configuring availability, managing practice settings, and the admin audit trail (recording all mutating admin actions and auth events).
* **Domain Doc:** `docs/arch_admin.md`
* **Key Files:** `admin_router.py`, `admin_context.py`, `practice_repository.py`, `audit_repository.py`, `http_utils.py`, `frontend/admin-ui/src/*`

### 3.8 HTTP Orchestration & App Entry
* **Scope:** FastAPI application, startup fail-fast validation, routing, error translation, rate limiting middleware.
* **Domain Doc:** Domain Doc: docs/arch_http_boundary.md
* **Key Files:** `main.py`, `request_validation.py`, `public_router.py`, `admin_router.py`, `form_router.py`, `dependencies.py`, `rate_limit.py`

### 3.9 API Boundary & Presentation
* **Scope:** Composing pre-session presentation data.
* **Domain Doc:** docs/arch_presentation.md
* **Key Files:** presentation_service.py

### 3.10 Clinical Ruleset Schema
* **Scope:** Layout and constraints for the clinical ruleset schemas
* **Domain Doc:** Domain Doc: docs/arch_ruleset_schema.md
* **Key Files:** Found in /data/ directory

### 3.11 Infrastructure, Database & Deployment
* **Scope:** Railway deployment configurations, the Dockerfile multi-stage build (Vite + Python), static file serving logic, Alembic database migrations, required environment variables, and Postgres/JSONB data quirks.
* **Domain Doc:** `docs/arch_infrastructure.md`
* **Key Files:** `Dockerfile`, `app/core/db.py` (Alembic initialization), `alembic/env.py`, `main.py` (for static serving mounts).

### 3.12 Testing Strategy
* **Scope:** Test categories (unit vs integration), two-database rule, migration obligations, Makefile targets.
* **Domain Doc:** `docs/arch_testing.md`
* **Key Files:** `tests/test_form_routes.py`, `tests/test_admin_router.py`, `Makefile`

### 3.13 Security & Compliance
* **Scope:** Access control, MFA, fail-fast configuration boundaries, data retention, file upload security (CDR), input sanitization, rate limiting, dependency patching, and image vulnerability scanning. Maps technical controls to Cyber Essentials Plus audit requirements.
* **Domain Doc:** `docs/arch_security.md`
* **Key Files:** `dependencies.py`, `admin_router.py`, `auth_repository.py`, `auth_service.py`, `deletion_job.py`, `request_validation.py`, `image_sanitizer.py`, `form_router.py`, `rate_limit.py`

### 3.14 MESH Dispatcher & NHS Delivery
* **Scope:** Dispatching clinical PDFs to a GP practice over NHS MESH, fallback to the Mailgun email path on terminal MESH failure, and the `mesh_jobs` lifecycle. mTLS transport security is covered in 3.13 (`arch_security.md` section 8); phased rollout and NHS protocol facts are in `mesh_integration_plan.md` and `nhs_integration_reference.md`, not this spoke.
* **Domain Doc:** `docs/arch_mesh.md`
* **Key Files:** `client.py`, `mesh_enqueuer.py`, `mesh_payload.py`, `mesh_repository.py`, `mesh_constants.py`, `mesh_worker.py`, `mesh_worker_main.py`

### 3.15 Encoder Training Data (Synthetic Generation)
* **Scope:** Building the encoder's training dataset by recombining hand-written sentence fragments. Offline only — nothing here runs in the live application and `app/` never imports it (`tests/test_wiring.py` enforces that). Covers the fragment libraries, label-first generation, train/val/test splitting and five-fold cross-validation over fragment clusters, the library lint, and the `.stats.json` provenance sidecar. The training strategy itself and the full design rationale stay in `documentation/encoder/`.
* **Domain Doc:** `docs/arch_training.md`
* **Key Files:** `scripts/synthetic_data/*.py`, `data/synthetic/manifest.json`, `data/synthetic/conditions/<condition>/**/*.txt` (signal-bearing and condition-specific filler libraries), `data/synthetic/filler/*.txt` (condition-agnostic filler)
* **Note on sample size:** every evaluation number is bounded by the number of distinct fragment *clusters* behind a slice, not the number of examples. See `arch_training.md` section 10 before reading any figure this pipeline produces.

### 3.16 Encoder Training & Evaluation (Offline Tooling)
* **Scope:** Training and evaluating one encoder head against those datasets, and saying honestly what the resulting numbers are worth. Offline only; `tests/test_encoder_training_dataset.py` enforces that `app/` never imports it. Covers the two training arms (Arm A, a frozen probe; Arm B, a full fine-tune), the baselines and negative controls, the decision rule, the cluster bootstrap and paired McNemar tests, the head artefacts and metadata sidecars, and the evaluation report. ML dependencies live in `requirements-ml.txt` and never reach production or CI.
* **Domain Doc:** `docs/arch_encoder_training.md`
* **Key Files:** `scripts/encoder_training/*.py`, `requirements-ml.txt`, `.dockerignore`, `models/encoder/<signal>/<arm>/` (head artefacts and metadata sidecars; Arm B's ~440MB weights are git-ignored), `reports/encoder_training/`, `data/realistic/` (the permanently held-out real-text evaluation set)
* **Note on the one number that is not a recombination:** every Arm B run since 2026-08-16 also scores the 67 hand-written submissions in `data/realistic/`, after its margin is chosen and its synthetic test split scored, so the set can select nothing. It is a **validity** instrument and cannot rank two models — 67 submissions give roughly ±12 points overall and ±23 or worse on a per-signal decisive slice. See `arch_encoder_training.md` section 11 and `data/realistic/README.md`.
* **Note before swapping in a real encoder:** a single head cannot satisfy `EncoderOutput.validate_against`, which requires output keys to match the ruleset's `send_to_encoder` signals exactly — `data/uti1.json` declares seven. See 3.3 and `arch_encoder_training.md` section 9.
* **Note on expanding past one signal:** libraries exist for six of the seven signals and **all six have now been trained** (2026-08-16), one Arm B head each at `roberta-base`. That is six separate single-signal heads, *not* one model answering six questions. The **merge step now exists** (`scripts/encoder_training/merge.py`, `merge-folds`): it concatenates the six per-signal fold trees into one that `load_folds` reads unchanged, keeping every head masked where it had no label and every example's original id in `meta.source_ids`. Joint training itself still needs per-head margin selection and a report shape that can hold several signals. Results table in `arch_training.md` section 10; write-up in `reports/encoder_training/2026-08-16-plain-english.md`. The plan of record is `planned_updates/multi_symptom_training_expansion.md`, summarised in `arch_training.md` 12.8.
* **Note before comparing signals:** only the `fever_*` and `dysuria_*` confounder libraries carry cluster markers, so the other four signals' effective sample sizes are upper bounds and their intervals are narrower than the truth. Every report prints the measured coverage and this warning above its own headline. This matters less than it was predicted to: the 2026-08-16 runs put fully-tagged `dysuria` second of six and both untagged weak signals last, so tagging is not what separates them. See `arch_training.md` section 10.
* **Note on `null → true`:** the cell that invents a symptom into a patient's pre-filled form. Across the six trained heads it runs 1.34% (`fever`) to 4.04% (`nocturia`). No head has been through a safety review against `arch_encoder.md`'s boundary, and none is wired to anything.

## 4. Other reference files

### 4.1 nhs_integration_reference.md
Contains information about information with integration with NHS APIs such as MESH, PDS and GP connect. This is not included in the architecture spoke documents deliberately - it contains facts not design decisions

### 4.2 file_structure.md
File structure reference

### 4.3 Deployment checklist

### 4.4 README.md
For onboarding new developers