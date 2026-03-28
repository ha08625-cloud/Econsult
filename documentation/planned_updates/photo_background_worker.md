Here is a short provisional plan entry you can paste into your planned updates document.

---

**Background Task Queue — Provisional Plan**

**Problem**

PDF generation with embedded photos loads full image pixel data into memory (a 5-photo submission may consume 250–500MB peak). This runs synchronously in the FastAPI request handler. Under concurrent load — plausible at peak submission times — this creates an OOM risk. Because PDF generation happens after the patient has submitted and may have closed their browser, a failure is a clinical safety issue, not just a UX issue.

**Proposed approach**

Decouple PDF generation and email delivery from the HTTP request. The router persists clinical data and returns a submission ID synchronously. PDF generation and delivery are handed off to a separate worker process via a job queue. The patient's response is not affected by downstream processing failures.

**Candidate implementations**

- `procrastinate` (Postgres-backed) — no new infrastructure, fits existing Railway deployment
- `arq` (Redis-backed) — requires Redis as a new dependency
- Celery — mature but heavy; probably overkill for this scale

**Open questions**

1. Does Railway support running two services (web + worker) on the current plan, and what is the cost implication?
2. Postgres-backed queue (procrastinate) vs Redis — preference for keeping infrastructure simple vs using a purpose-built broker?
3. How does the existing `delivery_orchestration.py` retry logic interact with task queue retry semantics — one of them needs to own retries, not both?
4. Should the submission ID be returned to the patient before or after the database row is committed? (Currently before — this is correct and should be preserved.)
5. What is the acceptable maximum delay between submission and delivery under this model — is a 30-second or 2-minute lag clinically acceptable?

**Prerequisite for going live with photo support**

This work should be completed before photo submission is enabled for real patients. The current synchronous implementation is acceptable for development and testing only.

---

That is intentionally short. It records the decision, the risk, the options, and what you need to answer before starting. Nothing in it commits you to a specific approach yet.