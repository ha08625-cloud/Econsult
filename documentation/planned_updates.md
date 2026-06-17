### Updates
- papertrail logging
- background worker heartbeat
- remove submissions after 7 days
- Notification architecture
- safety rules implemented on clicking yes/no, rather than on submit form (defer - big feature change and we need to know if blocking safety rules are desired or not)

### Admin portal updates
- Session refresh / sliding expiry

### Encoder updates
- Deterministic data augmentation
- Full question sets
- Encoder/head training

### production readiness updates
- MHRA registration - econsult health is registered as a class I medical device (technically anything that acts as patient triage is class 2a but we want to avoid that)
- Encryption and cybersecurity
- Data protection
- Digital clinical safety
- disclaimers
- privacy notices
- SOPs
- developer on retainer
- contract with confidentiality clause (they cannot share the code), a non-compete clause (they cannot build a competing product using your work), and an assignment clause (anything they build for you belongs to you, not them).

Database Backups
Railway's paid plans include automated daily backups with point-in-time recovery. The industry standard question to answer is: what is your recovery point objective (how much data can you afford to lose) and your recovery time objective (how long can the system be down). For a GP econsult system, losing even one submission is clinically significant. You should verify Railway's backup retention period, test that you can actually restore from a backup before going live, and document the restore procedure. "Test the restore" is the part almost everyone skips and the part that matters most — a backup you've never tested is not a backup you can rely on.
Deployment Rollback
The industry standard for a small Railway deployment is a documented runbook, not an automated rollback system. That means a short text document that says: if a deployment breaks production, here are the exact steps — how to revert to the previous git commit, how to run alembic downgrade -1 against production, how to redeploy the previous container. The key insight is that you write this when things are working, not when they're broken. A solo developer at 11pm with a broken deployment and no written procedure is in a genuinely bad position.
test_public_routes.py
The pragmatic fix is to add the same TEST_DATABASE_URL guardrail that your other integration tests already have. It's five lines of code at the top of the file and makes it consistent with everything else. This is a small but real maintenance risk and worth fixing before the test suite grows.