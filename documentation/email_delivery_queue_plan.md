### Objective

Prevent patient consultation loss when email delivery fails.
Guarantee **eventual delivery** to the `@nhs.net` mailbox while keeping the prototype architecture simple.

No redesign of the clinical engine or FastAPI app required.

---

# Provisional Plan: Email Delivery Queue

## 1. Design Principle

Email sending must **not occur during the request cycle**.

Current flow (fragile):

```
Patient submits form
      ↓
FastAPI generates consultation summary
      ↓
SMTP send
      ↓
Success or failure returned to patient request
```

If SMTP fails, the consultation may be lost.

Replace with **queue-based delivery**.

New flow:

```
Patient submits form
      ↓
FastAPI generates consultation summary
      ↓
Consultation stored in database
      ↓
Email job added to queue
      ↓
Response returned to patient
            ↓
Background worker processes queue
            ↓
Retries until delivery succeeds
```

The consultation exists **before any email attempt**.

---

# 2. Database Table

Add a table for delivery jobs.

```
email_delivery_queue

id (uuid, primary key)

consultation_id (uuid)
recipient_email (text)

subject (text)
body (text)

status (enum)
    pending
    sending
    sent
    failed

attempt_count (int)

last_attempt_at (timestamp)
next_attempt_at (timestamp)

created_at (timestamp)
```

Purpose:

* persist jobs
* track retries
* prevent duplicate sending
* allow monitoring

---

# 3. FastAPI Submission Flow Change

Current behaviour likely resembles:

```
generate_summary()
send_email()
return success
```

Replace with:

```
generate_summary()

store consultation record

insert email job into email_delivery_queue

return success
```

No SMTP activity happens in the request handler.

---

# 4. Background Worker

Add a lightweight worker process.

Options suitable for a prototype:

**Option A (simplest)**
FastAPI background task loop.

**Option B (better separation)**
Separate Python worker process.

Worker loop:

```
while true:

    select jobs where
        status = pending
        and next_attempt_at <= now()

    limit 10

    for job:
        mark as sending

        try:
            send email via SMTP

            mark as sent

        except:
            increment attempt_count
            set status = pending
            schedule next_attempt_at using backoff
```

---

# 5. Retry Strategy

Avoid hammering SMTP servers.

Example backoff:

```
attempt 1  -> immediate
attempt 2  -> 2 minutes
attempt 3  -> 10 minutes
attempt 4  -> 30 minutes
attempt 5  -> 2 hours
attempt 6+ -> 6 hours
```

Cap attempts at something like **20 attempts (~3 days)**.

After that:

```
status = failed
```

Staff alert required.

---

# 6. Idempotency Protection

Email jobs must never send duplicates accidentally.

Protection methods:

1. **Job state machine**

```
pending → sending → sent
```

2. Worker must atomically claim jobs:

```
UPDATE ... WHERE status = pending
RETURNING row
```

Prevents two workers sending the same email.

---

# 7. Minimal Admin Visibility (Important for NHS use)

Add a simple endpoint:

```
GET /admin/email-queue
```

Returns:

```
pending jobs
failed jobs
attempt counts
```

Staff can verify deliveries.

Later improvements could include:

* resend button
* alerting
* dashboard

---

# 8. Security and NHS Data Protection

This design **does not break NHS security requirements**.

Important points:

### Transport encryption

SMTP must use:

```
STARTTLS or SMTPS
```

This protects patient data in transit.

Most `@nhs.net` mail gateways already require this.

---

### Storage encryption

If the server stores consultation text in the database:

Use either:

* encrypted disk (recommended)
* database encryption at rest

Typical NHS hosting platforms already support this.

---

### Access control

Ensure:

* API requires authentication for admin endpoints
* database not publicly accessible

---

# 9. Impact on Email Delivery Failures

The queue **directly solves the failure problem**.

Without queue:

```
SMTP failure → consultation potentially lost
```

With queue:

```
SMTP failure → job retried until delivery
```

Even if:

* SMTP server temporarily down
* network outage
* nhs.net throttling

the consultation remains safe.

---

# 10. Complexity Impact

This adds only **three components**:

```
1 database table
1 worker loop
small FastAPI change
```

No message broker required.

No Redis required.

No architectural redesign.

---

# 11. Future Scaling (Optional Later)

If the system expands beyond one practice:

Replace the queue table with a dedicated system:

* Redis + RQ
* RabbitMQ + Celery
* AWS SQS

The **API interface does not change**, so the upgrade is straightforward.

---

# Final Assessment

Your current prototype **does not require redesign** for NHS security or reliability.

Adding a **persistent delivery queue** provides:

* consultation safety
* retry capability
* auditability
* compliance readiness

while keeping the architecture minimal for a single-practice deployment.
