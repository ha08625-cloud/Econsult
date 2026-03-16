## Pre-Session Presentation Architecture

This domain handles the read-only composition of data required by the frontend before a clinical session (`RuntimeState`) is initialized. 

### `presentation_service.py` Boundaries
* **Composition, Not Merging:** This module performs COMPOSITION, not MERGING. Each source (universal warning, practice signposting, condition presentation) populates a distinct field. There is NO field-level override logic.
* **Strict Isolation:** This module MUST NEVER access clinical data, modify any data, or handle authentication.
* **Tenancy Assumption:** The service is deployed in a single-tenant context. `practice_id` is always required; there is no concept of a missing practice.

## Presentation Data Flow
The system strictly separates the universal safety warning from condition-specific presentation so the safety gate occurs before any form interaction.

* **Step 1: Pre-session Safety Gate (Screen 0)**
  * Endpoint: `GET /safety-warning`
  * Action: Returns the universal safety warning constant.
  * UI Rule: The frontend renders the warning and strictly requires checkbox confirmation before the patient can proceed to condition selection.

* **Step 2: Condition Presentation (Screen 2)**
  * Endpoint: `GET /conditions/{id}/presentation`
  * Action: `presentation_service` composes a response by fetching the condition presentation from the registry and practice signposting from the database. 
  * API Note: `universal_safety_warning` is still returned in this payload for API backwards compatibility, but the frontend ignores it here.
