Phase 6C — MVP Infrastructure Decisions

Purpose

Lock the minimum set of infrastructure and implementation choices required to begin coding Phase 6, while keeping all decisions explicitly scoped to the MVP and reversible in later versions.

This phase answers how Phase 6A semantics and Phase 6B HTTP contracts will be implemented, without altering their meaning.


---

Guiding principles

Prefer boring, explicit, debuggable choices

Optimise for correctness, inspectability, and ease of refactor

Assume single-developer velocity

Avoid premature scalability or distribution concerns

Make all temporary choices obvious in code



---

Web framework

Chosen framework: FastAPI

Rationale:

Strong request/response schema enforcement

Automatic validation at the HTTP boundary

Clear separation between transport layer and business logic

Native support for typed models (Pydantic)

Automatic OpenAPI generation for inspection and testing


Constraints:

FastAPI is used only as a thin HTTP shell

No business logic may live in route handlers

All clinical, safety, and provenance logic remains in the existing engine modules



---

Process model

Assumption: single-process, single-worker server

Rationale:

Appropriate for MVP and local deployment

Simplifies concurrency reasoning

Avoids distributed locking concerns


Implications:

Optimistic concurrency is enforced logically via version, not via distributed locks

Horizontal scaling is explicitly out of scope for Phase 6



---

Persistence backend

Chosen backend: SQLite

Rationale:

Zero external dependencies

Transactional semantics available

Inspectable with standard tooling

Easy migration path to Postgres later


Usage constraints:

SQLite is used only as a persistence layer, not as a domain model

RuntimeState is stored as opaque serialized data

No complex querying or joins



---

RuntimeState serialization format

Chosen format: JSON (dataclass → dict → JSON)

Rationale:

Human-readable for audit and debugging

Language-agnostic

Avoids security risks of pickling

Easy to evolve with explicit versioning


Rules:

The serialized RuntimeState is treated as opaque by the database layer

Deserialization failures are fatal and fail loud

No partial deserialization or schema inference



---

Database schema (MVP)

Single table: runtime_state_versions

Illustrative columns:

runtime_id (TEXT)

version (INTEGER)

ruleset_hash (TEXT)

state_json (TEXT)

created_at (TIMESTAMP)

is_closed (BOOLEAN)


Constraints:

(runtime_id, version) is the primary key

Only one row per (runtime_id, version)

is_closed = true prevents further updates

Enforce: /form/finish sets is_closed=true on the latest version

On /form/update, reject if any row for that runtime_id has is_closed=true



---

Error handling strategy

All HTTP errors conform to the Phase 6B error envelope

FastAPI exception handlers map internal exceptions → HTTP errors

No raw exceptions leak to the client

All error codes are explicit and enumerated



---

Testing strategy (MVP)

Unit tests for:

route validation

version conflict handling

session closure enforcement


Engine logic remains unit-tested independently

No load or concurrency testing in Phase 6



---

Explicit non-goals (Phase 6C)

Horizontal scaling

Background jobs

Caching layers

ORM abstractions beyond minimal persistence helpers

Authentication or authorisation

Retention enforcement