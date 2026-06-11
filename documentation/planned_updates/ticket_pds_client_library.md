# Ticket: PDS Client Library (dormant)

**Status:** Not started. Independent of the MESH plan; runs in parallel.
**Why:** GP Connect Send Document addresses messages by patient (`GPPROVIDER_<NhsNo>_<DOB>_<Surname>`). If that route is adopted, the NHS number will most likely come from a server-side PDS trace, not patient entry. This ticket builds the client library now, while the PDS discovery in `docs/nhs_integration_reference.md` is fresh, without wiring it into anything.

## Scope

Pure client library in the Phase 2a `MeshClient` mould:

- `app/services/pds/client.py` — `PdsClient`, keyword-only constructor, reads no env vars, no DB access.
- Methods: `get_patient_by_nhs_number(...)` and `search_by_demographics(...)`.
- Result classification: `exact_match` / `no_match` / `multiple_matches` / `superseded_nhs_number`, following the deliverability decision tree in the reference doc.
- `errors.py` with transient/terminal split, mirroring the MESH error contract.
- Unit tests plus sandbox integration tests (guarded on a `PDS_BASE_URL` module-level skip, DB-free, `integration` marker — same convention as `test_mesh_client_integration.py`).

## Explicitly out of scope

- Any pipeline wiring, env vars in production config, or schema changes.
- Any enrichment or overwriting of patient-entered data (project invariant: external data never overwrites patient answers).
- **The fuzzy-match resolution policy.** PDS matching is brittle in practice (e.g. "John Jack" / "Smith" vs first/middle/last splits); what the system does on no-match or near-match is a clinical-safety and governance decision requiring practice input. Do not design it here.

## Done when

Library and tests merge; nothing imports it outside tests; reference doc updated with any new PDS facts observed.