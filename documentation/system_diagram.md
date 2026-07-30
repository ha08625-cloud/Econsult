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
| 3. Layering | *Where does a given piece of code belong?* | Adding a feature, reviewing a PR, settling "should this go in the router?" |
| 4. Admin portal | *How does an admin log in, and what can they reach?* | Auth changes, adding an admin screen, audit/compliance questions |

Diagrams 1 and 2 are about **runtime** — what happens while the system is running.
Diagrams 3 and 4 are about **code structure** — where things live. They're different
kinds of map and it's worth not mixing them on one canvas.

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

## Diagram 3 — Layering inside the web service

*When I add a piece of code, where does it belong?*

This is a **structure** map, not a runtime map. Nothing here happens in time order —
it shows which module is allowed to call which. Only the web service is drawn; the
workers have their own, much shorter chain.

```mermaid
graph TB
    subgraph L1["1 · ROUTERS — validate, orchestrate, translate errors. No business logic."]
        pub["<b>public_router</b><br/>/conditions · /availability<br/>/practice · /doctors"]
        form["<b>form_router</b><br/>/form/init · /update · /finish"]
        adm["<b>admin_router</b><br/>5 sub-routers · /admin/*"]
        hook["<b>webhook_router</b><br/>/webhooks/mailgun"]
    end

    subgraph L2["2 · SERVICES — business logic"]
        pres["presentation_service"]
        avail["availability_service<br/>+ orchestration"]
        authsvc["auth_service<br/><i>no DB access — repos<br/>passed in as arguments</i>"]
        usersvc["user_service"]
        pipe["<b>engine/pipeline.py</b><br/>pure · deterministic · no IO<br/>form_logic · ruleset · projection<br/>safety_engine · encoder_mapping<br/>serialisation · unit_conversion"]
    end

    subgraph L3["3 · REPOSITORIES — SQL only. One owner per table."]
        repos["practice · availability · runtime_state · submission<br/>attachment · photo · pdf · delivery · auth · audit"]
    end

    db[("Postgres")]

    pub --> pres
    pub --> avail
    form --> avail
    form --> pipe
    adm --> authsvc
    adm --> usersvc
    adm --> avail

    pres --> repos
    avail --> repos
    usersvc --> repos
    authsvc --> repos
    form --> repos
    adm --> repos
    hook --> repos

    repos --> db

    classDef router fill:#e8f0fe,stroke:#4a6fa5,color:#111
    classDef svc fill:#f3eafc,stroke:#8a5fbf,color:#111
    classDef engine fill:#e9f7ef,stroke:#4a9a6f,color:#111
    classDef repo fill:#fff4e5,stroke:#c98a2b,color:#111
    class pub,form,adm,hook router
    class pres,avail,authsvc,usersvc svc
    class pipe engine
    class repos,db repo
```

**Things this diagram is meant to make obvious:**

- **The engine is the unusual layer.** It sits at service level but touches no
  database and performs no IO — the same inputs always give the same outputs. That is
  what makes the clinical logic testable without a database, and it is the reason
  `file_structure.md` carries a list of banned imports protecting it.
- **`auth_service` has no database access at all.** Repositories are passed to it as
  arguments. Its arrow to the repository band is drawn for completeness, but the
  dependency runs the other way round to everything else on the diagram.
- **Several routers reach straight past the service layer to a repository.** That's
  the crossing lines from `form_router` and `admin_router` down to band 3, and it is
  accurate, not a drawing error. The service layer is only populated where there was
  real logic to hold; simple reads and writes go direct. Worth being conscious of —
  "we have three layers" is true in places and aspirational in others.
- **Objects are not imported, they're injected.** `wiring.py` builds every repository
  and service exactly once at startup and puts them on `app.state`; routers receive
  them through `Depends(get_*)`. That's left off the canvas deliberately — it applies
  to every arrow in band 1, so drawing it would add lines everywhere and shape
  nowhere.

---

## Diagram 4 — Admin portal

Two views again, for the same reason as diagram 2: one runtime, one structural.

### 4a — Login (runtime)

```mermaid
sequenceDiagram
    autonumber
    participant A as Admin (browser)
    participant R as admin_auth_router
    participant S as auth_service
    participant DB as Postgres
    participant MG as Mailgun

    Note over A,MG: Step 1 — password. Rate limited to 5/min.

    A->>R: POST /admin/auth/login {email, password}
    R->>S: verify_login_credentials()
    S->>DB: read admin_users
    Note right of S: timing-safe compare, with a dummy-hash path so a<br/>missing user costs the same as a wrong password

    alt any failure — wrong password, no such user, locked, no password set
        S-->>R: INVALID_CREDENTIALS
        R->>DB: audit — auth.login.step1_failed
        R-->>A: 422, generic message that hides which gate failed
    else password correct
        R->>DB: upsert admin_auth_codes (hashed OTP, 10 min TTL)
        R->>MG: background task — email the 6-digit code
        R->>DB: audit — auth.login.step1_succeeded
        R-->>A: 200 {ok: true} — client switches to the OTP screen
    end

    Note over A,MG: Step 2 — one-time code

    A->>R: POST /admin/auth/verify {email, code}
    R->>S: verify_mfa_code()
    S->>DB: check code, then INSERT admin_sessions + set last_login
    R->>DB: audit — auth.login.succeeded
    R-->>A: 200 + Set-Cookie session_id<br/>HttpOnly · Secure · SameSite=strict

    Note over A,DB: Every later request

    A->>R: any /admin/* request, cookie attached
    R->>DB: require_admin — get_session_context(session_id)
    Note right of R: 401 if absent, malformed or expired.<br/>On success the expiry is extended — idle timeout, not a hard cap.
    R->>R: AdminContext {practice_id, user_id, actor_email}<br/>handed to the endpoint — this is what the audit log stamps
    R-->>A: the endpoint's own response
```

**Things this diagram is meant to make obvious:**

- **Two independent factors.** Password and one-time code are separate round trips.
  Passing step 1 gets you no session — only step 2 issues the cookie.
- **The failure branch is deliberately uninformative.** Every step-1 failure returns
  the same 422 regardless of cause, so an attacker cannot use the response to discover
  which email addresses are registered. The failure *is* recorded in the audit log —
  just not disclosed to the caller.
- **The OTP email is sent as a background task.** The response doesn't wait for
  Mailgun. That's not only speed: making the caller wait would reintroduce a timing
  difference between "user exists" and "user doesn't", undoing the point above.
- **The session is an idle timeout, not a fixed lifetime.** Every authenticated
  request extends it.

### 4b — What an authenticated admin can reach (structure)

```mermaid
graph TB
    subgraph UI["Admin UI · frontend/admin-ui — a second React bundle, served by the same web process"]
        login["LoginView<br/>SetPasswordView"]
        sign["SignpostingEditor"]
        prac["PracticeSettingsTab"]
        availui["AvailabilityEditor"]
        users["UsersTab"]
        auditui["AuditLogTab"]
    end

    guard{{"<b>require_admin</b> — the gate<br/>session cookie → AdminContext<br/>401 if absent, malformed or expired<br/>extends expiry on every hit"}}

    subgraph RT["app/routers/admin/ — five sub-routers behind one thin admin_router"]
        rauth["<b>admin_auth_router</b><br/><i>the only unauthenticated one</i><br/>login · verify · reset · logout"]
        rprac["admin_practice_router<br/>signposting · settings · doctors"]
        ravail["admin_availability_router<br/>weekly · overrides · exceptions"]
        ruser["admin_user_router<br/>add · remove · resend invite"]
        raudit["admin_audit_router<br/>read only"]
    end

    arepo[("auth_repo<br/>admin_users · sessions<br/>auth_codes · reset_tokens")]
    prepo[("practice_repo<br/>practice · signposting<br/>doctors")]
    vrepo[("availability_repo<br/>weekly · overrides<br/>exceptions")]
    audrepo[("audit_repo<br/>admin_audit_log")]

    login --> rauth
    sign --> guard
    prac --> guard
    availui --> guard
    users --> guard
    auditui --> guard

    guard --> rprac
    guard --> ravail
    guard --> ruser
    guard --> raudit

    rauth --> arepo
    ruser --> arepo
    rprac --> prepo
    ruser --> prepo
    ravail --> vrepo
    raudit --> audrepo

    rauth ==> audrepo
    rprac ==> audrepo
    ravail ==> audrepo
    ruser ==> audrepo

    classDef ui fill:#e8f0fe,stroke:#4a6fa5,color:#111
    classDef rt fill:#f3eafc,stroke:#8a5fbf,color:#111
    classDef repo fill:#fff4e5,stroke:#c98a2b,color:#111
    classDef g fill:#fde8e8,stroke:#c0392b,color:#111
    class login,sign,availui,prac,users,auditui ui
    class rauth,rprac,ravail,ruser,raudit rt
    class arepo,prepo,vrepo,audrepo repo
    class guard g
```

Thick arrows are audit writes.

**Things this diagram is meant to make obvious:**

- **One gate, and exactly one router outside it.** `admin_auth_router` is
  unauthenticated by necessity — you can't require a session to log in. Everything
  else goes through `require_admin`. That makes the auth router the piece to look at
  hardest in review.
- **Every mutating router writes to the audit log.** The thick arrows all converge on
  one table. Audit is a cross-cutting obligation, not a feature of one screen.
- **The admin UI is a separate React bundle** from the patient app, but served by the
  same web process — so it is not separately deployable, and shares the same origin.
- **The admin surface only reaches four repositories.** No admin route touches
  submissions, PDFs, photos or the delivery queues. Admins configure the practice;
  they do not read patient data through this portal.

---

## Open questions for the draft review

1. **Which of these four earn their keep?** They cost more to maintain than they look.
   My guess at the ranking by value-per-line-of-maintenance: 2 (submission flow) > 1
   (deployment) > 4 (admin) > 3 (layering). Diagram 3 is the one most likely to drift,
   because module structure changes far more often than process topology.
2. **Diagram 3's honesty problem.** It shows routers reaching past the service layer.
   That's accurate today. If that's a pattern you want to move away from, the diagram
   is a useful record of the current state; if it's fine, the "3 layers" framing may be
   overselling what's actually a 2-layer system with some services in it.
3. **Maintenance.** A diagram nobody updates is worse than no diagram — it actively
   misleads. Options: (a) keep them deliberately coarse so they change rarely, (b)
   commit to updating whenever a process or queue is added, (c) treat them as one-off
   onboarding artefacts and date-stamp them. I'd suggest (a) for 1 and 2, and either
   dropping 3 or accepting it will need a refresh every few months.

## Known simplifications in this draft

- The encoder is drawn as part of `init_runtime_state`. Today it is
  `encoder_stub.py` — a placeholder, not a real model.
- Retry/backoff exists at every worker stage and is not drawn; only the terminal
  fallback path is shown.
- The `mesh_jobs` lifecycle has six states; the diagram shows the two transitions
  that change where the PDF ends up.
- Rate limiting, request-size limits and the Sentry wiring exist on the request path
  and are omitted from diagram 2 to keep the journey readable.
- Diagram 3 collapses all ten repositories into one box. They are separate classes
  with one table owner each — drawing them individually would triple the arrows
  without changing the shape.
- Diagram 3 covers the web service only. The workers have their own chain
  (`worker loop → repositories → Postgres`) with no router or service layer at all.
- Diagram 4a omits the password-reset and set-password flows, which share the
  invitation-token path used when an admin is first added.
