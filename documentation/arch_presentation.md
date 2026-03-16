# Pre-Session Presentation Architecture

This domain handles the read-only composition of data required by the frontend before a clinical session (`RuntimeState`) is initialized. 

### `presentation_service.py` Boundaries
* **Composition, Not Merging:** This module performs COMPOSITION, not MERGING. Each source (universal warning, practice signposting, condition presentation) populates a distinct field. There is NO field-level override logic.
* **Strict Isolation:** This module MUST NEVER access clinical data, modify any data, or handle authentication.
* **Tenancy Assumption:** The service is deployed in a single-tenant context. `practice_id` is always required; there is no concept of a missing practice.
