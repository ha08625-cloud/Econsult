## This document covers the architecture for the encoder modules and the ML boundary: `encoder_mapping.py`, `encoder_stub.py`, `encoder_contracts.py`

### encoder_stub.py — Replaceable encoder façade

Responsibilities:
* Accept free text + encoder definitions
* Emit {answer_key: true | false | null}

Constraints:
* Encoder never sees rules, questions or answers, RuntimeState
* Encoder output is non‑authoritative
* Stub logic is intentionally naive
* This module is expected to be deleted and replaced by a real encoder without impacting any other module.

### encoder_mapping.py — Encoder containment layer

Responsibilities:
* Apply encoder output to RuntimeState
* Enforce provenance rules
* Preserve raw encoder output for audit

Rules:

* Encoder never overwrites patient input
* Encoder only populates unanswered fields
* Mapping failures are fatal
* Encoder influence is fully contained in this module

This is the regulatory boundary between inference and clinical data.

### encoder_contracts.py — Encoder boundary contracts

Defines the only data structures permitted to cross the boundary between
an encoder implementation (stub or ML-backed) and the rest of the form engine.

Contains:
* EncoderSignalDefinition (frozen dataclass): answer_key + encoder_prompt
* EncoderOutput (frozen dataclass): model_name, model_version, ruleset_hash,
  signals dict {answer_key: True | False | None}

EncoderOutput.validate_against(definitions):
* Validates that output keys exactly match the provided definitions
* Validates that all values are True, False, or None
* Raises ValueError/TypeError on mismatch

Properties:
* Both dataclasses are frozen (immutable)
* No business logic beyond validation
* No imports from engine modules
* Imported by encoder_mapping.py and engine_adapters.py only
