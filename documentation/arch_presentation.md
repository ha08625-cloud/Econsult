# Pre-Session Presentation

**LLM INSTRUCTIONS:** This domain is small and stable. Read `presentation_service.py` directly for the return shape and method signatures.

---

## Scope

Read-only composition of data required by the frontend before a clinical session (`RuntimeState`) is initialised. Covers the universal safety warning and per-condition presentation.

**Key files:** `presentation_service.py`

---

## Design Decisions & Invariants

### Composition, not merging
`PresentationService` composes data from multiple sources into distinct fields. There is no field-level override logic — practice signposting and condition presentation occupy separate slots in the output. This is a deliberate constraint: if override logic were introduced, the boundary between clinical content and practice content would erode.

### Universal safety warning is hardcoded
`UNIVERSAL_SAFETY_WARNING` is a module-level constant, not a database value. It is intentionally not editable by practices. It is served standalone via `GET /safety-warning` and also included in `GET /conditions/{id}/presentation` for API backwards compatibility (the frontend ignores it in the latter).

### Single-tenant contract
`practice_id` is always required. There is no concept of a missing or optional practice. It is resolved from `app.state` at the HTTP layer and passed in explicitly.

### Two-step pre-session flow
1. `GET /safety-warning` — returns the universal warning. The frontend requires checkbox confirmation before the patient can proceed. This gate happens before condition selection.
2. `GET /conditions/{id}/presentation` — returns condition label, free-text prompt, universal warning (backwards compat), and practice signposting. Raises `ConditionNotFound` for unknown condition IDs.

---

## What This Module Must Never Do

- Access clinical data (rulesets, `RuntimeState`, answers, safety rules)
- Modify any data — read-only composition only
- Handle authentication
