

**Layer 1 — Structured logging with alerting**

Every significant operational event (delivery failure, exhaustion, retry attempt) is logged as structured JSON with a consistent schema: `event_type`, `submission_id`, `attempt_count`, `error_message`, `timestamp`. This is the foundation everything else builds on. You are already logging, but unstructured log strings are hard to alert on reliably.

**Layer 2 — Log-based alerting**

A monitoring service watches your log stream and fires an alert when it sees specific event types. Railway supports this natively via log alerts. Datadog, Grafana Cloud, and Sentry all offer this at low cost. The alert fires to a channel the operator actually watches — email, Slack, PagerDuty depending on severity.

For exhausted submissions in a clinical system, the right severity is high enough that it wakes someone up. A failed submission is not a patient safety incident in your system (the patient has their submission ID and can follow up), but it is an operational failure that needs same-day resolution.

**Layer 3 — A dead letter mechanism**

For any submission that reaches `exhausted` status, a specific action is triggered automatically: not just a log, but an outbound notification to a configured operator address via a separate channel from SMTP (because if SMTP is the thing that is broken, emailing the operator about it is useless). This is typically a webhook to Slack or a push notification via a service like PagerDuty or Opsgenie. A single HTTP POST to a webhook URL is trivial to implement and does not depend on your SMTP infrastructure.

**Layer 4 — A health check endpoint**

A `GET /health` endpoint that returns the count of failed and exhausted submissions alongside standard uptime checks. This can be polled by an uptime monitoring service (UptimeRobot is free, Better Uptime is low cost) which alerts if the count exceeds zero or if the endpoint goes down. This is passive monitoring that costs almost nothing to implement.

**What I would actually recommend for your system right now**

Not all of this. In priority order:

First, structured logging for delivery events. This is low effort and makes everything else possible later.

Second, a webhook notification on exhaustion. One environment variable for a Slack or Teams webhook URL, one HTTP POST when a submission is exhausted. This is maybe 20 lines of code and gives you push alerting without any new infrastructure.

Third, defer layers 3 and 4 until you have real patient data or a second operator. The complexity is not justified at prototype stage.

The webhook approach is worth including in scope for this ticket because it is small and it closes the real gap: right now an exhausted submission is invisible unless someone looks. A Slack message costs almost nothing to implement and removes that blind spot.

Does that framing make sense, and do you want to include the webhook notification as part of this plan?
