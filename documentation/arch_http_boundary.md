# HTTP Boundary & Orchestration (`main.py`)

**Scope:** The FastAPI application, request validation, startup constraints, and HTTP-to-engine orchestration. 

## 1. Architectural Rules (Strictly Enforced)
* **Imperative Shell Only:** `main.py` MUST NOT contain clinical logic, safety rule evaluation, or encoder invocation. It translates HTTP to engine entry points.
* **State Management:** Clinical presentation metadata never enters the core engine. `condition_label` is resolved from the registry and passed explicitly to engine adapters.
* **Resource Sharing:** Repositories and registries are initialized once and stored in `app.state` to be accessed by routers without circular imports.

## 2. Startup Validation (Fail-Fast)
Any failure in startup validation MUST raise a `RuntimeError` and abort application startup. A misconfigured deployment must not silently degrade.
* **Single Tenant Enforced:** The database MUST contain exactly one practice. Multiple practices imply a safety violation (cross-contamination of clinical data). 
* **Required Config:** `PRACTICE_ID` must match the DB, and emails must be configured (unless `DEV_MODE=1`).

## 3. Resilience & Failure Modes
* **Fail-Open Availability:** The availability check inside `POST /form/init` is wrapped in a try/except. A database failure MUST proceed as if the practice is open. We never lock patients out due to system errors.
* **Submission Recovery:** During `form/finish`, the submission record MUST be created in the database with `delivery_status = "pending"` *before* attempting the email send. This ensures the record is not lost if the email SMTP connection crashes.
