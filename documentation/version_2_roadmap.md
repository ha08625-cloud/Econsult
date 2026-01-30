The MVP was a proof of concept for us, the developers. Version 2 will be a demonstration proof of concept - a "sales artefact" to show off the idea to others
This is not intended to be a production ready version for actual clinical use - there are many steps to go before that

### Phase 1 — The "Brains" (Real Encoder Integration)

**Goal:** Replace the naive `encoder_stub.py` with actual encoder intelligence to create the "wow" factor

### Phase 2 — Content Expansion (Multi-Condition)

**Goal:** Prove the system is a *platform*, not just a hardcoded script

1. **New Rulesets:** Author 2 new JSON rulesets.
* *Sore Throat:* (Fever, Swollen glands, Can swallow liquids).
* *Headache:* (Visual disturbance, Neck stiffness, Thunderclap onset).

2. **Condition Selector:** Update the Backend `form_logic` to accept a `condition_id` at initialization. Each ruleset is individually named so that should fit nicely with our existing architecture (e.g. the urinary symptoms example ruleset is called uti1.json)
3. **Frontend Update:** Replace the hardcoded "Init" screen with a "Select Condition" menu.

### Phase 3 — The "Memory" (Cloud-Ready Persistence)

**Goal:** Stop saving state to the "local machine" (files) so the app works on the web with multiple concurrent users.
**Constraint:** Keep it lightweight.

1. **Redis or Postgres:** Replace the file-system persistence in `repository.py` with a cloud-native store.
* *Redis:* Best for ephemeral sessions (TTL 1 hour). Perfect for a demo that doesn't need long-term storage.


2. **Session Isolation:** specific verification that User A's `runtime_id` cannot bleed into User B's session.

### Phase 4 — The "Face" (UI Polish)

**Goal:** The Phase 7 "Dumb UI" is functional but ugly. Investors judge quality by design.
**Constraint:** Do not add React complexity (Router/Redux). Just style the existing structure.

1. **CSS Framework:** Add Tailwind CSS or Bootstrap.
2. **Visual Feedback:**
* Highlight "Auto-filled by AI" answers in a distinct, friendly color (e.g., soft blue background).
* Make the "Safety Block" look authoritative but not broken (e.g., amber warning banner, not a crash screen).


3. **Loading States:** Add a spinner during the `encoder` step

### Phase 5 — Deployment & Hygiene

**Goal:** A URL you can email to someone.

1. **Containerize:** Dockerize the Python Backend and the Frontend build.
2. **Hosting:** Deploy to a PaaS like Render, Fly.io, or Heroku. (Easier than raw AWS for a simple demo)