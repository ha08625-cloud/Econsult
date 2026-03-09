The MVP was a proof of concept for us, the developers. Version 2 will be a demonstration proof of concept - a "sales artefact" to show off the idea to others
This is not intended to be a production ready version for actual clinical use - there are many steps to go before that

### Phase 1 — The "Memory" (Cloud-Ready Persistence)

**Goal:** Stop saving state to the "local machine" (files) so the app works on the web with multiple concurrent users.
**Constraint:** Keep it lightweight.

1. **Redis or Postgres:** Replace the file-system persistence in `repository.py` with a cloud-native store.
* *Redis:* Best for ephemeral sessions (TTL 1 hour). Perfect for a demo that doesn't need long-term storage.


2. **Session Isolation:** specific verification that User A's `runtime_id` cannot bleed into User B's session.

### Phase 2 — Deployment & Hygiene

**Goal:** A URL you can email to someone.

1. **Containerize:** Dockerize the Python Backend and the Frontend build.
2. **Hosting:** Deploy to a PaaS like Render, Fly.io, or Heroku. (Easier than raw AWS for a simple demo)
