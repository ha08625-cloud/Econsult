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
* **Scope:** Building the encoder's training dataset by recombining hand-written sentence fragments. Offline only
* **Domain Doc:** `docs/arch_training.md`

### 3.16 Encoder Training & Evaluation (Offline Tooling)
* **Scope:** Training and evaluating one encoder head against those datasets. Offline only.
* **Domain Doc:** `docs/arch_encoder_training.md`
* **Key Files:** `scripts/encoder_training/*.py`, `requirements-ml.txt`, `.dockerignore`, `models/encoder/<signal>/<arm>/` (head artefacts and metadata sidecars; Arm B's ~440MB weights are git-ignored), `reports/encoder_training/`, `data/realistic/` (the permanently held-out real-text evaluation set)

### 3.17 Training Run Console (Local GUI)
* **Scope:** A local, browser-based console for starting the runs documented in `arch_encoder_training.md` section 10, watching their output live, stopping them, and putting the reports, models, log and manifest they produced on a new GitHub branch. Offline only, `127.0.0.1` only, no authentication. It types the documented commands; it does not know what training is, and it never interprets a result. The catalogue is built around two composite entries (`decl-sweep-2x2`, `decl-sweep-register`) that run a whole sweep — smoke test, every cell the comparison needs, the comparison, the companion scoring — as one parameterless run; the remaining entries exist to repeat one of those steps on its own. A composite regenerates its cells every time rather than checking whether they exist, because generation is deterministic and a presence check would turn a half-written tree into a silently wrong comparison four hours later. The sequencing is a property of the catalogue, not of the training code: nothing in `scripts/encoder_training/` chains a smoke test to a generation run to a comparison, so a future experiment gets the same one-button behaviour by adding an entry to `runs.json` and writing no code — but training several arms and pairing their results inside *one* invocation, which is what `declarative-compare`'s paired statistics require, is a training-CLI feature no catalogue entry substitutes for. Each composite's second and third steps are a training canary (`train-canary`, also a standalone entry): one signal, one fold, against a single-fold tree of its own. `smoke-cuda` launches a matmul, which cannot catch what only a real backward pass reveals — an op with no deterministic kernel under `--determinism strict`, an OOM at the configured batch size, a fused optimiser kernel faulting on a mismatched wheel. The canary needs its own tree because `load_folds` refuses a tree whose sidecar records a different fold count than the one requested, so a one-fold run cannot read a cell built at five; it writes only to `canary` directories, and skips the real-text holdout because `declarative-compare` already loads and validates it before any GPU work.
* **Domain Doc:** none of its own — this entry plus the module docstrings in `scripts/training_gui/`.
* **Key Files:** `scripts/training_gui/runs.json` (the catalogue of runnable commands), `catalogue.py`, `runner.py`, `gitops.py`, `server.py`, `static/index.html`, `tools/train-gui.sh`, `tools/train-gui.bat`, `tests/test_training_gui.py`
* **Invariants:**
  * The console never imports `scripts/encoder_training` or `scripts/synthetic_data`; it invokes them as subprocesses, so a change to a training command is a change in one place. `app/` never imports the console (asserted by `tests/test_encoder_training_dataset.py::test_app_never_imports_the_offline_tooling`, which covers any `scripts.*` import).
  * The browser can *name* a run; it cannot *compose* one. Every request carries a catalogue id and, per declared parameter, one string that must exactly match a `choices` member committed in `runs.json`. No endpoint accepts a command, an argument, a path or a branch name. The composites go further and declare no parameters at all, so no browser-supplied string reaches their argv.
  * `step_labels` in `runs.json` is presentational and never reaches an argv; it exists so a 29-step run reads as a checklist. `catalogue.py` validates only that there is one non-empty label per step, because a list out of step with the steps would label the wrong rows. `/api/status` joins the labels onto the manifest by `entry_id` (an entry the catalogue no longer has gets an empty list, and the page falls back to step numbers); the manifest itself stays free of them, because a label belongs to the catalogue and a run's record should not fossilise a caption.
  * Everything the progress display shows — per-step status and duration, total elapsed, the tab title and its dot — is arithmetic in the page over timestamps the manifest already carries. The runner records `started_at`/`ended_at` per step and per run and knows nothing about how they are displayed.
  * The page is a two-column shell rather than a scrolling document: the header carries the verdict, the catalogue scrolls on the left and the log holds the right column at viewport height, so starting a run never scrolls its own output off the screen. Long descriptions and the per-entry command lines are collapsed by default for the same reason — the column is a list of runs, and the 29 command lines of one entry would otherwise be the whole of it. Below 1000px the columns stack. Presentation only: no endpoint, manifest field or catalogue field exists to serve it.
  * **Stop** is the only button that asks for confirmation, and Run deliberately does not: a confirm on the press made most often is a confirm that gets clicked through, which would also weaken the one sitting next to it.
* **What it does not do:** it saves the mechanical minutes per run and the mis-commits that come with them. It does not touch the write-up obligations in `reports/encoder_training/README.md`, and it does not make a run worth having.

## 4. Other reference files

### 4.1 nhs_integration_reference.md
Contains information about information with integration with NHS APIs such as MESH, PDS and GP connect. This is not included in the architecture spoke documents deliberately - it contains facts not design decisions

### 4.2 file_structure.md
File structure reference

### 4.3 Deployment checklist

### 4.4 README.md
For onboarding new developers
