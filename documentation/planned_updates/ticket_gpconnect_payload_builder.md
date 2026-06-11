# Ticket: GP Connect Send Document — Spike, then Payload Builder

**Status:** Not started. Stage 1 can begin immediately (it is conversations, not code). Stage 2 depends on Stage 1 and on the `MeshPayloadBuilder` seam (MESH plan Phase 3).
**Why:** There is no registered workflow ID for raw PDF delivery to GP practices; the likely production endgame is GP Connect Send Document (see `docs/nhs_integration_reference.md`, "Workflow IDs"). This ticket prepares that path without committing the main pipeline to it.

## Stage 1 — Spike (questions for NHS Digital / first practice / system supplier)

1. **Applicability:** GP Connect Send Document v1's stated scope is consultations *outside* the patient's regular practice. Our use case is a patient submitting to their own practice. Does v2 (`GPCONNECT_SEND_DOCUMENT`, any document type) cover practice-own online consultation intake, or does a different standard / supplier integration route apply?
2. **Version:** v1.3.x is live but on a deprecation path; v2 is public beta. Which should a new sender target, and on what timeline?
3. **Accreditation:** what assurance route applies to us as a sending supplier (SCAL, clinical safety documentation), and what is its lead time?
4. **Addressing/demographics:** confirm the patient-based `Mex-To` convention applies, and therefore whether a PDS trace (see `ticket_pds_client_library.md`) or mandatory NHS number entry is required.

Output: a short written summary added to `docs/nhs_integration_reference.md` (facts) and a go/no-go recommendation for Stage 2.

## Stage 2 — `GpConnectSendDocumentPayloadBuilder`

- Implements the `MeshPayloadBuilder` Protocol from MESH plan Phase 3.
- Builds the ITK3-conformant FHIR Message (`Task`, `DocumentReference`, `Binary` embedding the PDF) for the version chosen in Stage 1; content type `application/fhir+json`.
- Validates output against NHS validation tooling; sandbox send tests.
- Startup validation of the builder/workflow-ID pairing (the two are coupled in the GP Connect specs).

## Explicitly out of scope

- ITK3 acknowledgement handling (inbound `_ACK` messages) — that is a MESH plan Phase 4 redesign, gated on Stage 1's answers.
- PDS wiring, accreditation paperwork, production enablement.

## Done when

Stage 1 answers are documented; Stage 2 builder merges behind the seam with nothing wiring it in production.