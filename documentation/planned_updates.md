Architecture updates:
- Pydantic request model migration: Replace all hand-written isinstance/type-check validation in both admin_router.py and request_validation.py with Pydantic BaseModel definitions, letting FastAPI handle JSON parsing, type coercion, and missing-field errors automatically. This also requires adding a RequestValidationError exception handler in main.py to convert Pydantic's error format into the existing {"error": {"code": ..., "message": ...}} shape, updating the frontend extractErrorDetail functions to handle any new edge cases, and retiring the unused api_models.py dataclasses.

Updates
- test block is getting unwieldy
- non blocking advisory messages
- Admin portal audit trails
- Patient facing audit trails
- Add a public_slug column - More flexibility, but adds complexity
- HTTPS for web traffic
- TLS for SMTP
- encrypted database storage
- Notification architecture
- safety rules implemented on clicking yes/no, rather than on submit form (defer - big feature change and we need to know if blocking safety rules are desired or not)

Late prototype updates
- Deterministic data augmentation
- Full question sets
- Encoder/head training
- dockerise and cloud
runtime_id is a bearer capability
guessing or leaking it exposes PHI-adjacent data
You do not need to solve auth in Phase 6, but you should:
state that runtime_id must be unguessable
state that rate-limiting and access control are deferred but required


production readiness updates
- Encryption and cybersecurity
- Data protection
- Digital clinical safety
- disclaimers
- privacy notices
- SOPs