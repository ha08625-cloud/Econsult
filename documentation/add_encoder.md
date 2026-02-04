# Overall encoder plan

## Purpose

The current MVP uses a stub for the encoder module.  This next version will replace the stub with a real encoder module.  This is a provisional plan with details that need to be added, not a final impementation plan

## 1. Problem definition

Input
One free-text string (patient blurb)
Output
For each answer_key marked send_to_encoder = true:
true | false | null
Constraints
- Binary only
- No temporal reasoning
- No severity
- No safety decisions
- One pass only
- Encoder never sees RuntimeState, rules, or safety logic

ClinicalBERT is not a classifier.
It is a pretrained encoder
Input: text
Output: contextual token embeddings (768-dim vector per token)

## 2. One shared encoder, multiple binary heads
Pipeline:
free text
- ClinicalBERT
- pooled embedding (CLS or mean pooling)
- N binary classifiers (one per answer_key)
- {answer_key: true|false|null}

Properties:
- Single forward pass
- Fast
- Stable
- Easy to audit
Matches your ruleset-driven signal list

## 3. Define the encoder interface contract

This step has been completed (provisionally) by creating the file encoder_contracts.py

Inputs:
free_text: str

Constraints:
Raw user input with no preprocessing beyond tokenizer normalization

Explicit non-inputs:
- RuntimeState
- Current answers
- Answer provenance
- Safety rules
- Question order
- Which answers are required
- Whether a question was shown
- Whether a value blocks submission

Output: the only thing the encoder may emit

The encoder output must be:
Dict[answer_key, Optional[bool]]

Allowed values:
- True
- False
- Null

Disallowed values:
- Probabilities
- Confidence scores
- Strings
- Explanations
- Partial answers
- Lists
- Nested objects

Error handling rules:
Encoder failures are fatal, not graceful.
Examples of fatal errors:
- Empty output
- Invalid type
- Missing keys
- Unexpected exception
- Model not loaded
- Tokenization failure

Versioning requirements

The encoder interface must include:
- model_name
- model_version
- ruleset_hash

## 4. Decide how “null” is produced
ClinicalBERT will always output a probability. You must choose how uncertainty maps to null.
Concrete rule (example):

if p > 0.8 → true
elif p < 0.2 → false
else → null

## 5. Creation of training data
You need labeled examples:
Copy code

free_text, fever_present, dysuria_present, frequency_present
Sources:
Synthetic clinician-written examples (acceptable for MVP)
De-identified historical text (only if legally allowed)
Manual annotation (small but high-quality beats large and noisy)
Rules:
Labels must be independent
Missing information must be labeled explicitly as unknown
Do not infer negatives unless clinically explicit
If you cannot get data, stop. The model will not save you.

## 6. Fine-tune ClinicalBERT

Base model: emilyalsentzer/Bio_ClinicalBERT
Input: raw free text
Pooling: CLS token or mean pooling
Head: linear layer per signal
Loss: binary cross-entropy per head
Mask loss when label is unknown

## 7. Freeze the model and export deterministically
Once trained:
- Freeze weights
- Fix tokenizer version
- Fix max sequence length
- Fix preprocessing

Your encoder must be:
- Deterministic
- Versioned
- Hashable
- The model version must be logged into audit output.

## 8. Replace the stub
Only this file changes:
encoder_stub.py → encoder_model.py
Everything else remains untouched.
If you have to change:
RuntimeState
encoder_mapping
projection
safety
You violated containment.

## 9. Add encoder-specific tests

Tests:
Encoder never outputs keys not in definitions
Encoder never outputs non-boolean
Encoder respects null thresholding
Encoder output is stable for identical input
Mapping never overwrites patient answers
Accuracy testing comes later.

## 10. Invariants

1. Total mapping
- Every answer_key passed in must appear in the output
- Missing key = fatal error

2. No extras
- Output keys must be a strict subset of input keys
- Extra key = fatal error

3. Order independence
- Output must not depend on ordering of definitions

4. Null semantics
Null means "The text does not clearly assert presence or absence”
It does not mean:
- False
- Negative
- Safe
- Absent
