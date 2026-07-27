# Implementation Plan: CLINICAL SUMMARY PDF block (`pdf_label`)

## Plan

Add an optional `pdf_label` field to ruleset questions. Where authored, the label is collected at serialisation time into a `pdf_labels` sidecar on `ClinicalOutput` and used to render a scannable CLINICAL SUMMARY block near the top of the PDF, between PATIENT DESCRIPTION and ANSWERS. The full ANSWERS section is unchanged and always present.

`pdf_label` is validated fail-fast at startup like every other optional ruleset field. The summary formats its values through the same helper as ANSWERS, so a quantity (unit-toggle) answer carries its units in both places.

No database change, no migration, no frontend change. A ruleset with no `pdf_label` anywhere produces a document identical to today's.

Five tasks, each independently committable with a green test suite.

---

## Scope

**In scope**

- `app/services/engine/ruleset.py` — `pdf_label` startup validation
- `app/models/serialisation_contracts.py` — `pdf_labels` field on `ClinicalOutput`, `.get()` in `from_dict`
- `app/services/engine/serialisation.py` — populate `pdf_labels` in `clinical_output()`
- `app/utils/pdf_formatter.py` — shared value formatter, CLINICAL SUMMARY block
- `data/uti1.json` — authored labels for one ruleset, to exercise the feature end to end
- Tests: `test_ruleset.py`, `test_serialisation.py`, `test_pdf_formatter.py`
- Docs: `arch_ruleset_schema.md`, `arch_submission.md`, `arch_testing.md`

**Out of scope**

- Authoring `pdf_label` across the remaining 14 rulesets in `data/` and the 16 in `data/questions/`. Label selection is a clinical judgement per condition and belongs in its own pass once the block has been seen in a real PDF. Only `uti1.json` is authored here.
- Any frontend change. `serialize_client_state` does not carry `pdf_label`; the patient never sees it.
- Any database column. `pdf_labels` rides inside the existing `clinical_output_json` JSONB via `asdict()`.
- Filtering the summary to positive findings only. See design decision 5 — the rule is a one-line change if the decision reverses after seeing real output.
- Reordering the summary independently of ruleset question order. See design decision 9.

---

## Design Decisions

**1. Field name is `pdf_label`.**
Not `question_label` or `short_label`. The field is explicitly a PDF display concern and naming it after the question invites confusion with `question` (the full patient-facing text) and `question_labels` (the existing answer_key → question text map on `ClinicalOutput`).

**2. Optional per question; absence means exclusion.**
A question without `pdf_label` simply does not appear in the summary. This is the correct default for free-text questions and for secondary findings that would dilute the block.

**3. The section renders only when at least one label exists.**
No labels in the ruleset means no CLINICAL SUMMARY heading and no vertical space consumed. Existing rulesets are byte-for-byte unaffected until someone authors a label.

**4. Position: between PATIENT DESCRIPTION and ANSWERS.**
The clinician reads the patient's own words first, gets the scannable findings second, and has the full detail below. Putting the summary above the free text would bury the one section that is not reconstructible from structured data.

**5. The summary shows every labelled finding, including negatives.**
`Fever: No` appears. This is deliberate: for a symptom checklist the clinically useful fact is that fever was *asked and excluded*, not merely that it was not mentioned. A positives-only block would be shorter but would make a negative and an unasked question indistinguishable at a glance.

The cost is that the block degrades into a shorter copy of ANSWERS if authors label everything. The mitigation is authoring discipline, not code: **4–6 labels per ruleset**, covering red flags and the discriminators that change management. This is recorded as a constraint in `arch_ruleset_schema.md` in Task 5.

If this proves wrong once real PDFs are reviewed, the reversal is a single `if` in the render loop plus a doc edit. Nothing else in the design depends on it.

**6. The summary formats values through the same helper as ANSWERS.**
The two sections must never disagree about the same answer. A quantity question with a `pdf_label` would otherwise render `Weight: 74.8` in the summary — no unit — while ANSWERS twenty lines below reads `Weight: 11 st 11 lb (74.8 kg)`. A unitless weight in a clinician's at-a-glance block is exactly the failure this section exists to prevent. Task 3 extracts `_format_display_value` and calls it from both places, so the quantity branch cannot be forgotten in one of them.

**7. `pdf_label` is validated fail-fast at startup.**
Every other optional ruleset field is checked at load time — `range_warning_text`'s type, `encoder_prompt`'s presence *and* absence, the whole quantity field group. An unvalidated `pdf_label` would let a non-string, a label on a free-text question, or two questions sharing one label pass startup and surface as a broken PDF for a real patient. Four rules, all in `ruleset.py`:

- present and non-null → must be a non-empty string
- must not appear on an `answer_type: "text"` question — a free-text answer cannot render usefully in the 65mm label / 115mm value row, and would push the block past a page boundary
- must be unique within the ruleset (exact string match) — two rows reading `Fever:` with different answers is worse than no summary at all
- absent or `null` → no constraint

Boolean and Number questions may both carry one. Number is explicitly included because that is where the quantity/units concern of decision 6 lives.

**8. `pdf_labels` is a sidecar on `ClinicalOutput`, mirroring `question_labels`.**
Same shape (`answer_key` → string), same reason (the PDF worker has no ruleset when it regenerates a document from persisted `clinical_output_json`), same backward-compatibility convention: `from_dict` reads it with `.get()` so records written before this change deserialise cleanly and produce no summary. Persistence is `asdict()` into the existing JSONB column, so there is no migration and no repository change.

**9. Summary order follows ruleset question order.**
The dict comprehension in `clinical_output()` iterates `ruleset["questions"]`, and dicts preserve insertion order through `asdict()`, JSONB, and `from_dict`. Authors control summary order by ordering questions, which is the same lever they already use for ANSWERS. No separate ordering field.

**10. An unanswered labelled question renders `(not answered)`.**
Same as ANSWERS. The summary reads `clinical_output.answers.get(key)`, so a labelled key missing from `answers` entirely — which should not happen, since runtime state carries every declared question — degrades to the same string rather than raising.

---

## Task 1: Ruleset schema validation

### A. State of the world

No previous tasks. `pdf_label` does not exist anywhere in the codebase or in any ruleset file. `validate_ruleset` performs no unknown-key rejection, so adding the field to a JSON file is already tolerated — this task adds the fail-fast rules of design decision 7 so that a *malformed* label is rejected at startup.

### B. Files and deliverables

- `app/services/engine/ruleset.py` — new `_validate_pdf_label` helper, called from the question loop in `validate_ruleset`; duplicate-label tracking in that loop
- `tests/test_ruleset.py` — accept and reject cases
- Deliverable: a ruleset with a malformed or duplicated `pdf_label` aborts startup with a clear message; all existing tests pass

### C. Instructions

**`app/services/engine/ruleset.py`**

Add the helper alongside the other `_validate_*` functions, after `_validate_quantity_fields`:

```python
def _validate_pdf_label(q: dict[str, Any]) -> None:
    """
    Validate the optional pdf_label field.

    pdf_label is a PDF display concern only: it names a question in the
    CLINICAL SUMMARY block (see arch_submission.md) and has no effect on form
    logic, encoder behaviour, or safety rules. It is optional, so absence is
    always valid, but a label that is present must be usable:

      - a non-empty string, since an empty label renders a bare colon
      - not on a text question, because a free-text answer cannot render
        usefully in the summary's fixed-width value column

    Uniqueness within the ruleset is enforced by the caller, which is the only
    place with a view across questions.
    """
    key = q["answer_key"]
    label = q.get("pdf_label")

    if label is None:
        return

    if not isinstance(label, str) or not label.strip():
        raise ValueError(
            f"Question '{key}' pdf_label must be a non-empty string or null, got {label!r}"
        )

    if q.get("answer_type") == "text":
        raise ValueError(
            f"Text question '{key}' must not set pdf_label: a free-text answer "
            f"cannot render usefully in the CLINICAL SUMMARY block"
        )
```

In `validate_ruleset`, add a tracking set next to `seen_answer_keys`:

```python
    seen_answer_keys = set()
    seen_pdf_labels: set[str] = set()
    answer_key_types: dict[str, str] = {}
```

and inside the question loop, immediately after the `_validate_quantity_fields(q)` call:

```python
        _validate_pdf_label(q)
        pdf_label = q.get("pdf_label")
        if pdf_label is not None:
            if pdf_label in seen_pdf_labels:
                raise ValueError(
                    f"Duplicate pdf_label {pdf_label!r} on question '{q['answer_key']}': "
                    f"summary rows must be unambiguous"
                )
            seen_pdf_labels.add(pdf_label)
```

Comparison is exact and case-sensitive. `"Fever"` and `"fever"` are treated as distinct; that is an authoring smell, not a correctness problem, and normalising would create a rule that is harder to explain than it is worth.

**`tests/test_ruleset.py`**

Add a new section after the quantity-kind group (around line 278), using the existing `_with(...)` / `validate_ruleset` helpers. Note `_base_ruleset()`'s single question is a Number named `weight`, so `_with(pdf_label=...)` targets a Number question directly:

```python
# ---------------------------------------------------------------------------
# pdf_label
# ---------------------------------------------------------------------------


def test_accepts_absent_pdf_label():
    validate_ruleset(_base_ruleset())


def test_accepts_null_pdf_label():
    validate_ruleset(_with(pdf_label=None))


def test_accepts_pdf_label_on_number_question():
    validate_ruleset(_with(pdf_label="Weight"))


def test_accepts_pdf_label_on_boolean_question():
    rs = _with(answer_type="Boolean", pdf_label="Fever")
    for field_name in ("decimal_places", "min", "max"):
        del rs["questions"][0][field_name]
    validate_ruleset(rs)


def test_rejects_empty_pdf_label():
    with pytest.raises(ValueError, match="pdf_label"):
        validate_ruleset(_with(pdf_label=""))


def test_rejects_whitespace_only_pdf_label():
    with pytest.raises(ValueError, match="pdf_label"):
        validate_ruleset(_with(pdf_label="   "))


def test_rejects_non_string_pdf_label():
    with pytest.raises(ValueError, match="pdf_label"):
        validate_ruleset(_with(pdf_label=42))


def test_rejects_pdf_label_on_text_question():
    rs = _with(answer_type="text", pdf_label="Onset")
    for field_name in ("decimal_places", "min", "max"):
        del rs["questions"][0][field_name]
    with pytest.raises(ValueError, match="must not set pdf_label"):
        validate_ruleset(rs)


def test_rejects_duplicate_pdf_label():
    rs = _with(pdf_label="Weight")
    second = copy.deepcopy(rs["questions"][0])
    second["question_id"] = "q2"
    second["answer_key"] = "weight_again"
    rs["questions"].append(second)
    with pytest.raises(ValueError, match="Duplicate pdf_label"):
        validate_ruleset(rs)
```

Run `python -m pytest tests/test_ruleset.py -v` and confirm green before committing.

---

## Task 2: Contract and serialisation

### A. State of the world

Task 1 is complete: `pdf_label` is validated at startup but nothing reads it. This task carries it from the ruleset into `ClinicalOutput` so the PDF worker can render it without reloading the ruleset. No database change.

### B. Files and deliverables

- `app/models/serialisation_contracts.py` — `pdf_labels` field on `ClinicalOutput`, read in `from_dict`
- `app/services/engine/serialisation.py` — populate it in `clinical_output()`
- `tests/test_serialisation.py` — build, round-trip and legacy-record coverage
- Deliverable: `clinical_output()` returns a `pdf_labels` dict containing only labelled questions; the dict survives `asdict()` → JSONB → `from_dict`; a record written before this change deserialises to `{}`

### C. Instructions

**`app/models/serialisation_contracts.py`**

Add the field to `ClinicalOutput` after `quantity_answers` (it must come after the existing defaulted fields). Use the file's own lowercase builtin generics — there is no `typing.Dict` import and none should be added:

```python
    # Per labelled answer_key: the short clinical label authored as pdf_label in
    # the ruleset. Drives the PDF's CLINICAL SUMMARY block; empty when no
    # question in the ruleset carries a label, in which case no summary section
    # is rendered. Display only -- it has no clinical or logical meaning beyond
    # naming a row. Mirrors question_labels, which is snapshotted for the same
    # reason: the PDF worker has no ruleset when it regenerates a document.
    pdf_labels: dict[str, str] = field(default_factory=dict)
```

In `from_dict`, add alongside `quantity_answers`:

```python
            pdf_labels=data.get("pdf_labels") or {},
```

`or {}` rather than a bare default, matching the `quantity_answers` line directly above it, so a stored `null` also lands as `{}`.

Extend the `from_dict` docstring's backward-compatibility sentence to name `pdf_labels` alongside `quantity_answers`.

**`app/services/engine/serialisation.py`**

In `clinical_output()`, immediately after the `question_labels` comprehension:

```python
    # Short display labels for the PDF's CLINICAL SUMMARY block, in ruleset
    # question order. Only labelled questions appear; a ruleset with none
    # produces an empty dict and no summary section. ruleset.py has already
    # rejected an empty, non-string, duplicated, or text-question label at
    # startup, so no filtering beyond presence is needed here.
    pdf_labels = {
        q["answer_key"]: q["pdf_label"] for q in ruleset["questions"] if q.get("pdf_label")
    }
```

Pass `pdf_labels=pdf_labels` in the `ClinicalOutput(...)` construction, after `question_labels`.

Add a line to the function docstring noting that `pdf_labels` is snapshotted for the PDF's summary block.

**`tests/test_serialisation.py`**

Add a section after the quantity clinical-output group. Reuse the existing `_runtime` and `_patient_details` helpers — `_runtime` supplies answers for `weight` and `notes`, which is exactly the labelled-Number-plus-unlabelled-text pair needed here:

```python
# ---------------------------------------------------------------------------
# pdf_labels -- CLINICAL SUMMARY snapshot
# ---------------------------------------------------------------------------


def _pdf_label_ruleset():
    rs = _ruleset()
    rs["questions"][0]["pdf_label"] = "Weight"
    return rs


def test_clinical_output_collects_authored_pdf_labels():
    out = clinical_output(_runtime("70.5"), _pdf_label_ruleset(), _patient_details())
    assert out.pdf_labels == {"weight": "Weight"}


def test_clinical_output_pdf_labels_empty_when_none_authored():
    out = clinical_output(_runtime("70.5"), _ruleset(), _patient_details())
    assert out.pdf_labels == {}


def test_clinical_output_pdf_labels_round_trip():
    from dataclasses import asdict

    out = clinical_output(_runtime("70.5"), _pdf_label_ruleset(), _patient_details())
    restored = ClinicalOutput.from_dict(asdict(out))
    assert restored.pdf_labels == {"weight": "Weight"}
```

Extend the existing `test_clinical_output_from_dict_defaults_for_legacy_record` with one assertion — the legacy dict already omits the key, so no fixture change is needed:

```python
    assert restored.pdf_labels == {}
```

Run `python -m pytest tests/test_serialisation.py -v` and confirm green before committing.

---

## Task 3: PDF formatter

### A. State of the world

Tasks 1 and 2 are complete: `ClinicalOutput` carries a `pdf_labels` dict populated from the ruleset. Nothing renders it yet. This task adds the CLINICAL SUMMARY block and, as a precondition, removes the duplicated value-formatting logic that would otherwise let the two sections disagree (design decision 6).

### B. Files and deliverables

- `app/utils/pdf_formatter.py` — `_format_display_value` helper; ANSWERS refactored onto it; CLINICAL SUMMARY block
- `tests/test_pdf_formatter.py` — five new tests
- Deliverable: the block renders between PATIENT DESCRIPTION and ANSWERS when `pdf_labels` is non-empty, with quantity answers carrying their units; the document is unchanged when `pdf_labels` is empty

### C. Instructions

**`app/utils/pdf_formatter.py`**

Add the shared formatter immediately after `_format_quantity_answer`:

```python
def _format_display_value(value, quantity_entry: dict | None) -> str:
    """
    Render one answer for display, dispatching to the quantity formatter when
    the answer has a sidecar entry.

    Both the CLINICAL SUMMARY block and the ANSWERS section call this, so the
    two can never disagree about the same answer -- in particular, a quantity
    answer carries its units in both places rather than appearing as a bare
    canonical number in the summary.
    """
    if quantity_entry is not None:
        return _format_quantity_answer(value, quantity_entry)
    return _format_answer(value)
```

Rewrite the ANSWERS loop body in `generate_pdf` to use it:

```python
    # --- Answers ---
    pdf.section_heading("ANSWERS")
    for key, value in clinical_output.answers.items():
        label = clinical_output.question_labels.get(key, key)
        formatted = _format_display_value(value, clinical_output.quantity_answers.get(key))
        pdf.row(f"{label}:", formatted)
```

Insert the summary block immediately *before* that ANSWERS block, after PATIENT DESCRIPTION:

```python
    # --- Clinical summary ---
    # A scannable at-a-glance block of the findings the ruleset author marked
    # with pdf_label, in ruleset question order. Renders only when the ruleset
    # carries at least one label, so a ruleset with none produces the same
    # document as before this section existed. Negatives are included by design
    # (see arch_submission.md): "asked and excluded" is a clinically different
    # fact from "not mentioned".
    if clinical_output.pdf_labels:
        pdf.section_heading("CLINICAL SUMMARY")
        for answer_key, short_label in clinical_output.pdf_labels.items():
            formatted = _format_display_value(
                clinical_output.answers.get(answer_key),
                clinical_output.quantity_answers.get(answer_key),
            )
            pdf.row(f"{short_label}:", formatted)
```

No new `_EConsultPDF` method is needed — `section_heading` and `row` handle this, including the page-break check inside `row`.

**`tests/test_pdf_formatter.py`**

Add a section at the end of the file, using the existing `extract_pdf_text`, `_make_patient` and `submission_kwargs` fixtures:

```python
# ---------------------------------------------------------------------------
# CLINICAL SUMMARY block (pdf_label)
#
# The block renders between PATIENT DESCRIPTION and ANSWERS when pdf_labels is
# non-empty, formats values through the same helper as ANSWERS (so a quantity
# answer keeps its units), and disappears entirely when no label is authored.
# ---------------------------------------------------------------------------


def _summary_output(pdf_labels, answers=None, quantity_answers=None):
    return ClinicalOutput(
        condition_id="uti1",
        free_text="symptoms",
        additional_text=None,
        answers=answers or {"dysuria_present": True, "fever_present": False},
        safety_messages=[],
        question_labels={
            "dysuria_present": "Are you experiencing pain when passing urine?",
            "fever_present": "Have you felt like you have had a fever during this episode?",
        },
        pdf_labels=pdf_labels,
        patient_details=_make_patient(),
        contact_preferences=None,
        quantity_answers=quantity_answers or {},
    )


def test_clinical_summary_renders_when_labels_present(submission_kwargs):
    output = _summary_output({"dysuria_present": "Dysuria", "fever_present": "Fever"})
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "CLINICAL SUMMARY" in pdf_text
    assert "Dysuria:" in pdf_text
    assert "Fever:" in pdf_text


def test_clinical_summary_absent_when_no_labels(submission_kwargs):
    output = _summary_output({})
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "CLINICAL SUMMARY" not in pdf_text


def test_clinical_summary_adds_no_content_when_no_labels(submission_kwargs):
    # Byte length, not bytes: the document must be structurally identical to one
    # produced before the section existed. Same precedent as the photo tests.
    with_labels = generate_pdf(
        clinical_output=_summary_output({"dysuria_present": "Dysuria"}), **submission_kwargs
    )
    without_labels = generate_pdf(clinical_output=_summary_output({}), **submission_kwargs)
    assert len(with_labels) > len(without_labels)


def test_clinical_summary_quantity_answer_keeps_units(submission_kwargs):
    # Regression: the summary must not render a bare canonical number where
    # ANSWERS renders "11 st 11 lb (74.8 kg)".
    output = _summary_output(
        {"patient_weight_kg": "Weight"},
        answers={"patient_weight_kg": "74.8"},
        quantity_answers={
            "patient_weight_kg": {
                "quantity_kind": "weight",
                "raw_components": {"st": 11, "lb": 11},
                "unit_system": "imperial",
                "decimal_places": 1,
            }
        },
    )
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "Weight:" in pdf_text
    assert "11 st 11 lb" in pdf_text
    assert "74.8 kg" in pdf_text


def test_answers_section_complete_when_only_some_questions_labelled(submission_kwargs):
    output = _summary_output({"dysuria_present": "Dysuria"})
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    # Both full question texts still appear in ANSWERS...
    assert "Are you experiencing pain when passing urine?" in pdf_text
    assert "Have you felt like you have had a fever during this episode?" in pdf_text
    # ...and the one labelled question also appears in the summary.
    assert "Dysuria:" in pdf_text
```

Run `python -m pytest tests/test_pdf_formatter.py -v` and confirm green before committing.

---

## Task 4: Author labels on `uti1.json`

### A. State of the world

Tasks 1–3 are complete: the mechanism works end to end but no ruleset carries a label, so no PDF has changed. This task authors labels for one ruleset so the block can be reviewed in a real document before the remaining rulesets are done in a separate pass.

### B. Files and deliverables

- `data/uti1.json` — `pdf_label` on six of the eight questions
- Deliverable: a submission against `uti1` produces a PDF with a six-row CLINICAL SUMMARY block; startup validation passes

### C. Instructions

Add a `pdf_label` key to each of the following questions in `data/uti1.json`, placed after `encoder_prompt` in each object:

| `answer_key` | `pdf_label` |
| --- | --- |
| `dysuria_present` | `Dysuria` |
| `urinary_frequency_present` | `Frequency` |
| `fever_present` | `Fever` |
| `flank_pain_present` | `Flank pain` |
| `haematuria_present` | `Haematuria` |
| `recent_uti_present` | `UTI in last 30 days` |

Leave `nocturia_present` unlabelled — it is a supporting symptom rather than a discriminator, and the block is held to 4–6 rows per design decision 5. Leave `symptom_onset_text` unlabelled; it is `answer_type: "text"` and Task 1's validation rejects a label on it.

**The clinical selection above is a proposal, not a fixed part of this plan.** The set is chosen so the summary shows the two cystitis symptoms plus the three pyelonephritis discriminators and the recurrence flag. Adjust before implementing if the clinical priorities differ; the plan does not otherwise depend on which questions are labelled.

Verify with `python -c "from app.services.engine.ruleset import load_ruleset; load_ruleset('data/uti1.json')"` — startup validation must pass. Then run the full unit suite.

---

## Task 5: Documentation

### A. State of the world

Tasks 1–4 are complete and the feature is live in `uti1.json`. This task records the schema field, the contract change, and the test coverage.

Note on document targeting: `arch_presentation.md` covers `presentation_service.py` — pre-session composition of condition label, free-text prompt and the universal safety warning. It has nothing to do with the PDF. PDF layout and the `ClinicalOutput` contract are documented in `arch_submission.md`.

### B. Files and deliverables

- `documentation/arch_ruleset_schema.md` — `pdf_label` in the Schema Shape block and a Design Constraints entry
- `documentation/arch_submission.md` — extend the `ClinicalOutput` bullet; add a CLINICAL SUMMARY bullet
- `documentation/arch_testing.md` — update the `test_ruleset.py`, `test_serialisation.py` and `test_pdf_formatter.py` rows
- Deliverable: all three updated; no other doc mentions `pdf_label`

### C. Instructions

**`documentation/arch_ruleset_schema.md`**

In the Schema Shape question object, add after `encoder_prompt` and before the Number-only group:

```
      "pdf_label": "<string>" | null,   // optional; PDF display only — short clinical
                                        // label naming this question's row in the
                                        // CLINICAL SUMMARY block. Boolean and Number
                                        // questions only. Omit to exclude.
```

Add a Design Constraints entry after the quantity entries:

> **`pdf_label` is a PDF display concern, validated like everything else.** An optional short label naming the question's row in the PDF's CLINICAL SUMMARY block (see `arch_submission.md`). It has no effect on form logic, encoder behaviour, or safety rules, and is never sent to the client. When present it must be a non-empty string, must not appear on a `text` question (a free-text answer cannot render usefully in the summary's fixed-width value column), and must be unique within the ruleset (exact match) so that no two summary rows carry the same name. Questions without one simply do not appear in the block, and a ruleset with none produces no block at all. Validated at startup by `ruleset.py`.
>
> **Authoring constraint: 4–6 labels per ruleset.** The block shows every labelled finding including negatives, because "asked and excluded" and "not mentioned" are clinically different facts. That only stays scannable if labels are reserved for red flags and the discriminators that change management. Labelling every question turns the block into a shorter copy of ANSWERS and defeats its purpose.

**`documentation/arch_submission.md`**

Extend the `ClinicalOutput` bullet in the Serialisation Contracts section (around line 260) with a sentence after the `question_labels` sentence:

> It also carries `pdf_labels` (answer_key -> short display label), snapshotted from the ruleset's `pdf_label` fields for the same reason as `question_labels` — the PDF worker regenerates documents from persisted JSONB and has no ruleset. Like `quantity_answers`, it defaults to an empty dict and is read via `.get()` in `from_dict`, so records predating it deserialise cleanly and simply render no summary.

Add a new bullet after the "Quantity answers, wire shape" bullet (around line 270):

> - **CLINICAL SUMMARY block.** `pdf_formatter.py` renders an optional scannable block between PATIENT DESCRIPTION and ANSWERS, one row per entry in `ClinicalOutput.pdf_labels`, in ruleset question order. It renders only when at least one label exists; the full ANSWERS section is always present and unchanged, so the summary is strictly additive and never the only place a finding appears. Both sections format values through the shared `_format_display_value` helper, which dispatches on the `quantity_answers` sidecar — without that, a labelled quantity question would render a bare canonical number in the summary (`Weight: 74.8`) while ANSWERS showed `11 st 11 lb (74.8 kg)`. Negatives are included by design; the block is kept scannable by an authoring constraint on label count, not by filtering (see `arch_ruleset_schema.md`).

**`documentation/arch_testing.md`**

- `test_ruleset.py` row (line 125): append `Also pdf_label validation: non-empty string, rejected on text questions, unique within the ruleset.`
- `test_serialisation.py` row (line 126): append `pdf_labels coverage: collected from authored labels only, empty when none authored, and round-tripped through from_dict (with the legacy-record case asserting an empty dict).`
- `test_pdf_formatter.py` row (line 133): append `CLINICAL SUMMARY coverage: block renders with labels and disappears without them, adds no content when unlabelled, a labelled quantity answer keeps its units, and the ANSWERS section stays complete when only some questions are labelled.`

---

## Verification before merge

1. `make lint` — clean.
2. `make test` — full unit suite plus frontend Vitest green. The frontend is untouched but the suite must stay green.
3. `python -c "from app.services.engine.ruleset import load_ruleset; import glob; [load_ruleset(p) for p in glob.glob('data/*.json')]"` — every shipped ruleset still loads.
4. Generate one PDF against `uti1` (submit through the running app, or call `generate_pdf` directly with a hand-built `ClinicalOutput`) and look at it. Confirm the block sits below PATIENT DESCRIPTION, reads cleanly at six rows, and does not push ANSWERS onto a second page unnecessarily. Design decision 5 is the one choice here that only real output can validate.
