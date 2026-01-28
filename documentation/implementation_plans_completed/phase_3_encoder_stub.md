
1. Encoder contract



Define a hard boundary

Input

{

free_text: string | null,

encoder_definitions: [

{

  signal_id: string,

  encoder_prompt: string

}

]

}

Notes:

Encoder never sees questions

Encoder never sees rules

Encoder never sees current answers

Prompts are identifiers, not instructions

Output

{

signal_id: true | false | null,

...

}

Rules:

Missing signal → treated as null

Encoder cannot invent signal_ids

Encoder cannot emit anything else

2. Encoder stub behaviour



Minimal logic.  All we need is some way of outputting true, false and null.  This stub will be replaced in its entirety - no stub logic will ever touch the real encoder module

Therefore, minimal logic:

Fever returns fever=true

Burning returns dysuria=true

Frequency returns frequency=true

No returns=false

None of the above=null

“No” being a global signal and inaccurate is acceptable for the purpose of the stub (the purpose is not to have any actual logic, it is to test that the signals are received and interpreted)

3. Mapping layer



New encoder_mapping.py module

Responsibilities:

For each signal output:

Map to exactly one answer_key

Populate answer_value if and only if:

answer is currently empty

Set:

answer_source = "encoder"

Preserve:

raw encoder output verbatim in RuntimeState.audit.encoder_raw

Rules:

Encoder never overwrites user input

Encoder output is optional noise

Mapping failures are fatal (schema violation)

4. Provenance semantics



Final set:

unanswered

encoder

encoder_confirmed

encoder_corrected

patient

Allowed transitions.

From

To

Allowed

Reason

unanswered

encoder

yes

prefill

unanswered

patient

yes

direct answer

encoder

encoder_confirmed

yes

submit without change

encoder

encoder_corrected

yes

user edits

encoder_confirmed

encoder_corrected

Yes (changed from earlier)

Users can go back and change answers at any time.  Encoder_confirmed can be changed to encoder_corrected and vice versa.  Encoder_confirmed/corrected can never be changed to unanswered or patient

patient

encoder

no

encoder never overwrites

patient

encoder_confirmed

no

nonsense

Encoder stub must only ever produce encoder.

Normalization to encoder_confirmed happens in Phase 6.

5. Failure modes



Fail loud:

signal_id not in ruleset

encoder_prompt missing for send_to_encoder=true

duplicate signal_id

encoder returns unknown signal

Fail soft:

free_text is null → return all nulls

empty keyword match → nulls

Never:

Default to false

Infer absence

Trigger safety logic

6. Test cases you must write in Phase 3



Minimum set:

Happy path

Free text contains one keyword

Answer populated as encoder

Override protection

Pre-filled answer exists

Encoder output ignored

Null degradation

No free text

RuntimeState identical to no-encoder run

Audit completeness

Raw encoder outputs preserved verbatim

Safety isolation

Encoder=true does not trigger safety

If any of these fail, the boundary is broken.

7. Explicit non-goals (write these in code comments)



Accuracy

NLP

Negation

Confidence

Partial matches

Multi-question inference