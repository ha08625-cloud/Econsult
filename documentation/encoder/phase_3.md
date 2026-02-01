Phase 3: define the encoder interface contract

What Step 3 is

It is:
* A software contract
* A containment boundary
* A regulatory firewall

3.2 Inputs: what the encoder is allowed to see

3.2.1 Free text (exactly one string)

free_text: str

Constraints:

Raw, unmodified user input

No preprocessing beyond tokenizer normalization

No truncation logic outside the encoder


The encoder owns tokenization and truncation. Nobody else touches the text.


---

3.2.2 Encoder signal definitions (strictly declarative)

Each signal definition must contain only what is required to extract it.

Minimum viable shape (conceptual, not syntax):

answer_key — opaque identifier

answer_type — must be Boolean

encoder_prompt — semantic anchor


What this means:

The encoder knows what concepts exist

It does not know:

Question wording

Visibility rules

Safety implications

Required vs optional

Runtime state



This mirrors your current ruleset → encoder definitions extraction. That’s correct.


---

3.3 Explicit non-inputs (this is where people usually fail)

The encoder must never receive:

RuntimeState

Current answers

Answer provenance

Safety rules

Question order

Which answers are required

Whether a question was shown

Whether a value blocks submission


Reason: If the encoder sees any of this, it stops being an extractor and becomes a decision-maker.

That is architecturally disallowed.


---

3.4 Output: the only thing the encoder may emit

The encoder output must be:

Dict[answer_key, Optional[bool]]

Nothing else.

Allowed values:

True

False

None (means “cannot infer”)


Disallowed values:

Probabilities

Confidence scores

Strings

Explanations

Partial answers

Lists

Nested objects


Why:

Probabilities invite downstream logic misuse

Explanations invite UI leakage

Anything richer than a boolean breaks containment


If you want probabilities later, they stay inside the encoder module and die there.


---

3.5 Cardinality and completeness rules

These are strict invariants:

1. Total mapping

Every answer_key passed in must appear in the output

Missing key = fatal error



2. No extras

Output keys must be a strict subset of input keys

Extra key = fatal error



3. Order independence

Output must not depend on ordering of definitions




This makes the encoder deterministic and auditable.


---

3.6 Null semantics (reiterated, but enforced here)

None means:

“The text does not clearly assert presence or absence”


It does not mean:

False

Negative

Safe

Absent


This semantic must be enforced at the encoder boundary, not downstream.

Downstream code must never reinterpret None.


---

3.7 Error handling rules

Encoder failures are fatal, not graceful.

Examples of fatal errors:

Empty output

Invalid type

Missing keys

Unexpected exception

Model not loaded

Tokenization failure


Reason: A broken accelerator must not silently degrade into incorrect clinical data.

Fail loud. Let the pipeline abort.


---

3.8 Versioning requirements (often forgotten)

The encoder interface must include:

model_name

model_version

ruleset_hash


These do not go into clinical output. They do go into audit output.

Why: You must be able to answer:

> “Which model suggested this answer, under which ruleset?”



Without this, your audit trail is incomplete.


---

3.9 Where this interface lives in your architecture

Correct placement (you already did this right conceptually):

ruleset
  → extract encoder definitions
encoder module
  → consume free text + definitions
  → emit booleans
encoder_mapping
  → apply provenance + overwrite rules

The interface is the seam between inference and clinical state.

Nothing crosses that seam except booleans.