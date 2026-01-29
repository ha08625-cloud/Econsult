Early prototype updates
- Server side state storage and audit output storage
- Suggestion conditions in addition to safety conditions
- Add encoders
- retry loop
- safety rules implemented on clicking yes/no, rather than on submit form

Late prototype updates
- Multiple conditions
- Full question sets
- UI and UX improvements
- Autocomplete/typeahead
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

optional updates
- Allow surgeries to add local service suggestions e.g. direct referral to physio
