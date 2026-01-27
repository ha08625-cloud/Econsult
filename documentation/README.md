### Overview
### What this system is

This is an improved online medical consultation form system

This is what exists now:
- An e-consultation form accessed through a website, usually the GP surgery website
- The user can type in a symptom and the system searches for what it thinks is the right symptom from a pre-determined list (e.g. user types UTI and system searches for closest likely answers e.g. urinary symptoms or urinary incontinence)
- Once confirmed, the system then allows the user to type a free text response
- But that response is simply added to the output verbatim, not processed further in any way
- The system then asks a series of yes/no questions, even if those questions were already answered in the original free text response

The “smart” component
- The system will have a series of presenting complaints that the patient can pick e.g. urinary symptoms, back pain, request for sick note (administrative)
- Based on that presenting complaint, the system will have a series of questions or data points that are required (overlapping but different for each presenting complaint)
- For example for urinary symptoms, it will want to know whether there is fever, dysuria, abdominal or pelvic pain, flank pain, shivers/rigors, recent infections etc
- The patient can write a short blurb explaining their presenting complaint
- That blurb is then run through an encoder model
- The encoder model will have a series of heads which are boolean classifiers for each required symptom e.g. fever: yes or no and then pre-fills the form based on those answers
- That is the current scope of the project
- More complicated inference is deferred e.g. attempting to extract pain character descriptions or temporal classification - would result in significant increase in time input, complexity and hardware requirements
- Suggested answers are clearly marked and can always be changed
- This is about better forms, not artificial intelligence replacing clinicians

### 1. Architectural position
Core principle
- Encoders accelerate form completion. They never replace explicit answers.
- Free text is an optional accelerator, not a dependency.
- If a patient skips it:
- the system degrades gracefully to a standard branched form
- no hidden logic breaks
- no safety logic is affected

### 2. Avoiding “hard NLP” explicitly
If a field is:
- temporally complex
- gradient-based (severity scales)
- open-ended by nature
- then it is never encoder-extracted

Instead:
- dropdown
- checkbox
- free text

### 3. System architecture proposal

Client (Web)
 ├─ Optional free text
 ├─ Dynamic question list
 │    ├─ suggested answers (pre-filled, editable)
 │    └─ suppressed irrelevant questions
 └─ Safety messages (read-only)

Server
 ├─ EncoderAnnotator
 │    └─ one pass, binary signals only
 ├─ FormRulesEngine
 │    └─ show / hide / suggest
 ├─ SafetyNetEngine
 │    └─ deterministic rules
 └─ AuditLog

Notably absent:
- no dialogue manager
- no LLM
- no per-turn orchestration
- no conversational state

### 4. Condition modelling
Each condition has three layers

Layer 1 — Signals (encoder-capable)
- Binary only.
- Example: urinary symptoms
- dysuria_present
- frequency_present
- fever_present
- flank_pain_present

Layer 2 — Explicit questions
- Always asked unless suppressed. Answers are authoritative.
- Example: duration (dropdown)

Layer 3 — Safety netting
- Consume only explicit answers.
- Example:
- IF flank_pain == yes
- OR fever == yes
- THEN show urgent care message
- Encoders never directly trigger safety advice

### 5. UX rules
- Suggested answers are visually marked (“We’ve pre-filled this based on what you wrote”)
- Nothing is locked: user can always change suggestions
- Free text is always preserved verbatim, never overwritten and always visible to clinician

### 6. Regulatory safety
- This system does not diagnose
- This system does not prioritise urgency
- This system does not replace clinician review
- This system optimises data capture only

### 7. Step-by-step plan to start the new project
Step 1 — Pick one condition (urinary)
Step 2 — Implement form without any ML.  Pure rules + branching.
Step 3 — Add encoder.  Populate suggestions

### 8. Scope
- Working MVP
- Single condition, boolean extraction limited to three questions/data points:
- PC: urinary sx, boolean extraction: fever, dysuria, urinary frequency
- Encoder extracts information, doesnt have to be accurate
- Information is displayed and user can correct
- Output includes free text responses and yes/no outputs
- Single safety net message based on one boolean red flag fever

### 9. Later versions
- Multiple conditions
- Full question sets
- UI and UX improvements
- Encoder/head training
