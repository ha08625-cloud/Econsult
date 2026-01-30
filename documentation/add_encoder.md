
Step 0 — Lock the problem definition (before touching ML)
Do this first or you will waste time.
Input
One free-text string (patient blurb)
Output
For each answer_key marked send_to_encoder = true:
true | false | null
Constraints (non-negotiable, already correct in your design)
Binary only
No temporal reasoning
No severity
No safety decisions
One pass only
Encoder never sees RuntimeState, rules, or safety logic
If any of these are relaxed later, ClinicalBERT is the wrong tool.

Step 1 — Understand what ClinicalBERT actually gives you
ClinicalBERT is not a classifier.
It is:
A pretrained encoder
Input: text
Output: contextual token embeddings (768-dim vector per token)
It does not output booleans. It does not know what “fever_present” is.
You must add heads.

Step 2 — One shared encoder, multiple binary heads
Pipeline:
free text
→ ClinicalBERT
→ pooled embedding (CLS or mean pooling)
→ N binary classifiers (one per answer_key)
→ {answer_key: true|false|null}
Properties:
Single forward pass
Fast
Stable
Easy to audit
Matches your ruleset-driven signal list
This aligns cleanly with your existing encoder_definitions extraction

Step 3 — Define the encoder interface contract (code, not ML)
Before training anything, define the pure interface your real encoder must satisfy.
Equivalent to your stub, but stricter:
Copy code

encode(
  free_text: str,
  signals: List[EncoderSignalDefinition]
) -> Dict[answer_key, Optional[bool]]
Where EncoderSignalDefinition contains:
answer_key
encoder_prompt (used only for training / labeling, not inference)
answer_type == Boolean
This guarantees the real encoder can replace the stub without touching:
pipeline
mapping
safety
serialization
If this interface changes later, you failed the architecture.
Step 4 — Decide how “null” is produced (critical)
ClinicalBERT will always output a probability. You must choose how uncertainty maps to null.
Concrete rule (example):
Copy code

if p > 0.8 → true
elif p < 0.2 → false
else → null
Why this matters:
Prevents over-confident autofill
Preserves user authority
Reduces medico-legal risk
This logic belongs inside the encoder module, not mapping or rules.
Step 5 — Get or create training data (this is the real work)
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
Step 6 — Fine-tune ClinicalBERT (mechanics, not magic)
Concrete setup:
Base model: emilyalsentzer/Bio_ClinicalBERT
Input: raw free text
Pooling: CLS token or mean pooling
Head: linear layer per signal
Loss: binary cross-entropy per head
Mask loss when label is unknown
This is standard multi-label classification.
Do not:
Add attention tricks
Add prompts
Add generation
Mix safety logic
Step 7 — Freeze the model and export deterministically
Once trained:
Freeze weights
Fix tokenizer version
Fix max sequence length
Fix preprocessing
Your encoder must be:
Deterministic
Versioned
Hashable
The model version must be logged into audit output.
Step 8 — Replace the stub (surgically)
Only this file changes:
encoder_stub.py → encoder_model.py
Everything else remains untouched.
If you have to change:
RuntimeState
encoder_mapping
projection
safety
You violated containment.
Step 9 — Add encoder-specific tests (non-ML tests)
You are not testing accuracy here. You are testing behavioral invariants.
Tests:
Encoder never outputs keys not in definitions
Encoder never outputs non-boolean
Encoder respects null thresholding
Encoder output is stable for identical input
Mapping never overwrites patient answers
Accuracy testing comes later.
Step 10 — Accept what this will never do
ClinicalBERT will not:
Understand timelines reliably
Resolve contradictions
Replace explicit questions
Be “clinically smart”
That is fine. Your architecture already assumes this.