# Econsult — System Diagrams (DRAFT)

Status: **draft for discussion**. Not yet a maintained artefact. Nothing else in the
documentation set links to it yet.

These diagrams are written in [Mermaid](https://mermaid.js.org/), a text format that
GitHub renders as pictures automatically. The source is plain text, so it diffs and
reviews like code — when the architecture changes, the diagram changes in the same
commit.

---

## How to read this file

There are two diagrams here, deliberately at **different zoom levels**:

| Diagram | Question it answers | When you'd look at it |
| --- | --- | --- |
| 1. Deployment view | *What separate things are running, and what do they talk to?* | Onboarding, deployment, "why is nothing being sent?" |
| 2. Submission flow | *What actually happens when a patient submits a form?* | Debugging a stuck submission, planning changes to delivery |

The single most common mistake with architecture diagrams is putting everything on
one canvas. A diagram that shows all 60 modules is a picture of a hairball and tells
you nothing. Each diagram should answer **one question**, and anything that doesn't
help answer it gets left out.

---

## Diagram 1 — Deployment view

*What separate processes exist, what data store do they share, and what outside
systems do they reach?*

Deliberately excluded: individual Python modules, the engine's internals, table
schemas. Those belong to a lower zoom level.

Reading note: arrows point **the way work flows**, not the way bytes travel. The
workers poll and claim from Postgres — the arrow from the database down to them means
"work reaches this process from here", not that the database calls out.

```mermaid
graph TB
    subgraph users[" "]
        patient["<b>Patient</b><br/>browser"]
        admin["<b>Practice admin</b><br/>browser"]
    end

    web["<b>Web service</b> · main.py<br/>FastAPI · serves both React bundles<br/>Runs Alembic migrations on boot<br/>The only process that accepts HTTP"]

    db[("<b>Postgres</b> — the only thing the processes share<br/>form sessions · submission records<br/>PDFs + photos as BYTEA<br/>pdf_jobs · delivery_jobs · mesh_jobs<br/>admin users · audit log")]

    subgraph workers["Background processes — no HTTP server, poll the database for work"]
        pdfw["<b>PDF worker</b><br/>pdf_worker_main.py"]
        delw["<b>Delivery worker</b><br/>worker_main.py"]
        meshw["<b>MESH dispatcher</b><br/>mesh_worker_main.py"]
        delj["<b>Deletion job</b><br/>deletion_job.py<br/>nightly one-shot"]
    end

    mailgun["<b>Mailgun</b>"]
    mesh["<b>NHS MESH</b><br/>mTLS + HMAC"]
    gp(["<b>GP practice</b><br/>clinical inbox"])

    patient -->|"/conditions · /availability<br/>/form/init · /update · /finish"| web
    admin -->|"/admin/*<br/>cookie session · password + OTP"| web

    web -->|"reads + writes"| db

    db --> pdfw
    db --> delw
    db --> meshw
    db --> delj

    delw -->|"send PDF"| mailgun
    meshw -->|"send PDF"| mesh
    mailgun --> gp
    mesh --> gp
    mailgun -.->|"delivery webhook<br/>POST /webhooks/mailgun"| web

    classDef proc fill:#e8f0fe,stroke:#4a6fa5,color:#111
    classDef ext fill:#f5f5f5,stroke:#999,stroke-dasharray:4 3,color:#111
    classDef store fill:#fff4e5,stroke:#c98a2b,color:#111
    classDef term fill:#e9f7ef,stroke:#4a9a6f,color:#111
    class web,pdfw,delw,meshw,delj proc
    class mailgun,mesh,patient,admin ext
    class db store
    class gp term
    style users fill:none,stroke:none
```

All five processes ship in **one Docker image** and run as separate Railway services,
selected by their start command. Sentry receives errors from all four long-running
processes; that's left off the diagram deliberately — it connects to everything and
would obscure the shape without telling you anything you didn't already assume.

**Things this diagram is meant to make obvious:**

- The four long-running processes **share nothing but the database**. There is no
  message broker, no queue server, no shared memory. The "queues" are Postgres tables
  that workers poll and claim. That is a real design decision with real consequences
  (simple to operate; polling latency; every handoff is transactional).
- The web service is the **only** process that speaks HTTP inbound. The workers have
  no HTTP server at all — you cannot health-check them over the network.
- Only the web service runs migrations. Workers assume the schema already exists and
  crash-restart until it does.
- PDFs and patient photos live **in Postgres as BYTEA**, not in object storage. That
  is unusual and worth being conscious of as volume grows.

---

## Diagram 2 — Submission flow

*What happens from "patient starts a form" to "PDF lands with the GP practice"?*

This is the same system at a lower zoom level, following one journey through it.
Split into two parts, because the interesting thing about this system is **where the
synchronous request ends and the asynchronous pipeline begins**.

### 2a — The synchronous part (patient is waiting)

```mermaid
sequenceDiagram
    autonumber
    participant P as Patient (React)
    participant W as Web · routers
    participant E as Engine (pure, deterministic)
    participant DB as Postgres

    Note over P,DB: Client holds only runtime_id + version.<br/>All state is server-owned — nothing round-trips through the browser.

    P->>W: POST /form/init {condition_id, free_text}
    W->>W: availability check — fail-open on any error
    W->>E: init_runtime_state()
    Note right of E: loads ruleset JSON,<br/>runs encoder (currently a stub)<br/>to pre-fill signals
    E-->>W: RuntimeState + client_state
    W->>DB: runtime_state_versions — version 1
    W-->>P: runtime_id, version, client_state

    loop one round trip per answer step
        P->>W: POST /form/update {runtime_id, base_version, answers}
        W->>E: apply answers → convert units → validate →<br/>project explicit answers → evaluate safety
        E-->>W: new state + safety messages
        W->>DB: append new version<br/>(rejects if base_version is stale)
        W-->>P: client_state + safety messages
    end

    Note over P,DB: Finish — the synchronous work stops here
    P->>W: POST /form/finish {patient details, photos}
    W->>W: sanitize photos (CDR — image rebuilt, metadata stripped)
    W->>E: clinical_output() + audit_output()
    W->>DB: submission_records + submission_photos + pdf_jobs (pending)
    W-->>P: 200 OK — returned before any PDF exists
```

### 2b — The asynchronous part (patient has gone home)

```mermaid
flowchart TD
    A(["pdf_jobs · pending"]) --> PW["<b>PDF worker</b><br/>claim → render PDF →<br/>save attachment → enqueue → mark done"]
    PW --> ATT[("submission_attachments<br/>PDF bytes")]
    PW --> SW{"MESH_DELIVERY<br/>env var<br/>chosen at worker startup"}

    SW -->|"= 0"| DJ(["delivery_jobs"])
    SW -->|"= 1"| MJ(["mesh_jobs"])

    DJ --> DW["<b>Delivery worker</b><br/>claim → send via Mailgun"]
    MJ --> MW["<b>MESH dispatcher</b><br/>claim → send via NHS Spine"]

    MW -->|"terminal error, or<br/>retries exhausted"| FB["mark_fallback_triggered<br/><i>commits first</i><br/>then create delivery_jobs row<br/>with is_fallback = true"]
    FB --> DJ

    DW --> GP(["GP practice inbox"])
    MW --> GP

    WH["Mailgun webhook<br/>POST /webhooks/mailgun"] -.->|"provider_accepted → delivered"| DJ

    classDef q fill:#fff4e5,stroke:#c98a2b,color:#111
    classDef work fill:#e8f0fe,stroke:#4a6fa5,color:#111
    classDef term fill:#e9f7ef,stroke:#4a9a6f,color:#111
    classDef choice fill:#f3eafc,stroke:#8a5fbf,color:#111
    class A,DJ,MJ,ATT q
    class PW,DW,MW,FB,WH work
    class GP term
    class SW choice
```

**Things this diagram is meant to make obvious:**

- There are **three queues in a chain**, not one: `pdf_jobs` → (`delivery_jobs` |
  `mesh_jobs`). Each stage claims, works, and marks. A submission can be stuck at any
  of the three, which is exactly the question you'll be asking when one goes missing.
- The email/MESH choice is **not per-submission**. It's an environment variable read
  once when the PDF worker boots, which picks the enqueuer implementation. Flipping it
  requires a worker restart.
- The fallback is **one-directional**: MESH can fall back to email, email never falls
  back to MESH.
- The ordering in the fallback box is a deliberate safety invariant. Marking the mesh
  job first means a crash mid-fallback leaves the submission *undelivered but
  detectable*, never *sent twice on both channels*. A recovery sweep repairs it.

---

## Open questions for the draft review

1. **Zoom level.** Is diagram 1 at the right altitude, or would a version showing the
   `router → service → repository` layering inside the web service be more useful for
   the work you actually do?
2. **Coverage.** These two skip the admin portal entirely (auth, MFA, availability
   config, audit log). Worth a third diagram, or is that better as prose?
3. **Maintenance.** A diagram nobody updates is worse than no diagram — it actively
   misleads. Options: (a) keep it deliberately coarse so it changes rarely, (b) commit
   to updating it whenever a process or queue is added, (c) treat it as a one-off
   onboarding artefact and date-stamp it as such. I'd suggest (a).

## Known simplifications in this draft

- The encoder is drawn as part of `init_runtime_state`. Today it is
  `encoder_stub.py` — a placeholder, not a real model.
- Retry/backoff exists at every worker stage and is not drawn; only the terminal
  fallback path is shown.
- The `mesh_jobs` lifecycle has six states; the diagram shows the two transitions
  that change where the PDF ends up.
- Rate limiting, request-size limits and the Sentry wiring exist on the request path
  and are omitted from diagram 2 to keep the journey readable.
