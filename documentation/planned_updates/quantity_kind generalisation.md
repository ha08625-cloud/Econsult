# Implementation Plan: quantity_kind generalisation (Ticket 1)

## Plan

Make the unit-toggle mechanism quantity-kind-generic and remove the hardcoded weight assumptions from the parts of the pipeline that do not need clinical meaning. The chosen unit system moves from a form-wide field on `RuntimeState` to a per-answer field on `AnswerState`, which is where the fact actually belongs. Cross-question unit agreement becomes a frontend convention plus one startup authoring check, not a runtime validation path.

**No new quantity kind is introduced.** `"weight"` is still the only supported kind at the end of this ticket. Observable patient-facing behaviour is unchanged throughout.

Five tasks, each independently committable with a green test suite.

---

## Scope

**In scope**

- `app/services/engine/ruleset.py` — kind registry, `quantity_kind` validation, per-kind system vocabulary, shared-toggle authoring check
- `app/models/runtime_state.py` — `unit_system` moves from `RuntimeState` to `AnswerState`
- `app/services/engine/form_logic.py` — kind-first conversion dispatch
- `app/services/engine/serialisation.py` — per-answer system, `quantity_kind` in both views
- `app/models/serialisation_contracts.py` — `ClinicalOutput.unit_system` removed, sidecar shape extended
- `app/utils/pdf_formatter.py` — kind-dispatched formatter table
- `app/services/engine/unit_conversion.py` — module comment only
- `data/numeric_capability_demo.json` — migration
- `frontend/src/types.ts`, `frontend/src/helpers.ts`, `frontend/src/screens/EditScreen.tsx`, `frontend/src/screens/ReviewScreen.tsx`
- Tests: `test_ruleset.py`, `test_form_logic.py`, `test_serialisation.py`, `test_pdf_generation.py`, `test_wiring.py`, `helpers.test.ts`, `EditScreen.test.tsx`, `ReviewScreen.test.tsx`
- Docs: `arch_ruleset_schema.md`, `arch_core_engine.md`, `arch_submission.md`, `arch_frontend.md`, `arch_testing.md`

**Out of scope**

- Any new quantity kind (Ticket 2 adds `"height"` with its full wiring in one commit)
- Toggle button relabelling ("Metric"/"Imperial" without unit hints) — Ticket 2
- Compound quantity kinds such as blood pressure. These need a canonical system with more than one component and per-component min/max; `AnswerState.value` holds a single scalar, so they need a separate seam. Noted so it is not mistaken for trivial later.
- Runtime cross-question unit consistency and its 422 path — deliberately dropped, see design decision 4
- Rendering a single-system quantity question in `EditScreen.tsx` — no such kind can exist yet, see design decision 8

---

## Design Decisions

**1. The kind registry lives in `ruleset.py`.**
`form_logic.py` already imports from `ruleset.py`, so the reverse direction would be a circular import and would fail at startup. `ruleset.py` already owns the schema vocabulary (`VALID_ANSWER_TYPES`, `VALID_UNIT_SYSTEMS`), so it is the natural home. `form_logic.py` imports the registry from it. `pdf_formatter.py` does **not** import it — presentation importing the core engine would breach the layering — so its formatter table is a parallel table kept honest by a wiring test.

**2. Closed set of complete kinds.**
`quantity_kind` is validated at startup against the registry, which contains only kinds with complete wiring (component-key map, canonical system, converter, formatter). A ruleset can never declare a kind the engine cannot fully handle.

**3. Per-kind system vocabulary.**
`allowed_systems` is validated against the declared kind's own systems map, not a global `{"metric", "imperial"}` set. `VALID_UNIT_SYSTEMS` is deleted.

**4. The unit system is a property of an answer, not of a form.**
`RuntimeState.unit_system` is removed and `AnswerState.unit_system` added alongside `raw_components`. The inbound wire shape is already per-answer (`QuantityAnswerPayload` carries its own `system`), so this aligns storage with the contract that already exists. Consequences:

- `serialize_client_state` reads the answer's own system, so a single-system question can never serialise as `"system": null`
- `ClinicalOutput.unit_system` is removed; the system moves into each `quantity_answers` sidecar entry
- No form-level field has to name one vocabulary for all kinds, so no type has to be widened or narrowed as kinds are added
- No runtime cross-question consistency check is needed. A mixed-unit submission from a direct API client converts correctly per answer, records accurately, and renders faithfully. It is a readability oddity, not a defect. This is a conscious acceptance.

**5. Cross-question agreement is a frontend convention plus one authoring check.**
`EditScreen` keeps its single shared toggle driving every quantity question. The only server-side enforcement is at startup: all quantity questions offering more than one system must agree on `allowed_systems` (compared as sets) and on `default_system`. Without it, a ruleset where weight offers metric and imperial while height offers metric only would render the height question in a system it rejects, giving the patient an unclearable 422. That is a broken deployment and must abort at startup per the fail-fast invariant. Single-system questions are exempt — they sit outside the toggle by definition.

**6. Registry parity is enforced by a wiring test, not runtime errors.**
Kinds appear in `ruleset.py` (the registry), `form_logic.py` (converter table) and `pdf_formatter.py` (formatter table). A `test_wiring.py` case asserts the key sets agree and that each kind's canonical system maps to exactly one component key. A `KeyError` from an unregistered kind remains as defence in depth, but the test is the real guarantee. Frontend parity cannot be asserted from pytest and stays a manual obligation, recorded in `arch_frontend.md`.

**7. Backward compatibility, narrowed.**
`pdf_worker.py` regenerates PDFs from persisted `clinical_output_json`, so an in-flight retry job can cross the deploy boundary. A sidecar entry without `quantity_kind` therefore defaults to `"weight"` at the dispatch seam, following the existing `.get()` convention. The weight formatter derives metric-vs-imperial from the component keys (`{kg}` vs `{st, lb}`) rather than from a stored system, so there is no second code path and no dependence on a field pre-change records lack. `unit_system` is still recorded in the sidecar as clinical and audit data, and is available to future kinds whose component keys do not disambiguate.

**8. No single-system UI branch.**
No registered kind offers a single system, so a fixed-unit render path in `EditScreen.tsx` cannot be exercised by any ruleset or by any test other than a synthetic fixture. `initialUnitSystem` seeds from the first *multi-system* question (which removes the tie-break TODO, since design decision 5 guarantees they agree), but the fixed-label render branch is deferred to whichever ticket introduces a single-system kind. Recorded as a known limitation in `arch_frontend.md`.

**9. Registry shape.**

```python
QUANTITY_KINDS = {
    "weight": {
        "canonical_system": "metric",
        "systems": {
            "metric": ("kg",),
            "imperial": ("st", "lb"),
        },
    },
}
```

Component keys are ordered tuples so input order is authored once and shared with the frontend structure. Callers compare as sets. The canonical system is the one whose single component *is* the stored value; every other system needs a converter.

---

## Task 3: PDF formatter kind dispatch and registry parity test

### A. State of the world

Tasks 1 and 2 are complete: the registry and validation are in place, the unit system is per-answer, the sidecar carries `quantity_kind` and `unit_system`, and `form_logic` dispatches per kind. `pdf_formatter._format_quantity_answer` is still a single weight-shaped function.

### B. Files and deliverables

| File | Deliverable |
| --- | --- |
| `app/utils/pdf_formatter.py` | `_QUANTITY_FORMATTERS` table; weight logic moved into `_format_weight_quantity` |
| `tests/test_wiring.py` | Registry parity assertions |
| `tests/test_pdf_generation.py` | Dispatch case and missing-kind default case |

### C. Instructions

**`pdf_formatter.py`**

1. Rename the existing function to `_format_weight_quantity(canonical_value, sidecar_entry) -> str`, taking the whole sidecar entry so each kind's formatter picks the fields it needs without churning signatures as kinds are added. It reads `raw_components` and `decimal_places`, and detects imperial by the presence of `"st"`. It ignores `unit_system` — the component keys are unambiguous for weight, and this keeps records written before Task 2 rendering correctly.

2. Add `_QUANTITY_FORMATTERS: dict[str, Callable[[Any, dict], str]] = {"weight": _format_weight_quantity}`.

3. `_format_quantity_answer(canonical_value, sidecar_entry)` becomes a thin dispatcher: `kind = sidecar_entry.get("quantity_kind", "weight")`, look up the formatter, call it. Comment the default: it exists for records persisted before the field was added, following the same `.get()` convention as `photo_quality_tier`. A `KeyError` on an unregistered kind is correct — it is an internal wiring failure, not bad input.

4. Update the call site in the answers loop to pass `(value, qa)`.

5. Comment above the table that this is a parallel table to `ruleset.QUANTITY_KINDS`, deliberately not importing it (presentation must not import the core engine), and that `test_wiring.py` asserts they agree.

**`tests/test_wiring.py`**

6. Add a section with these assertions:
   - `set(ruleset.QUANTITY_KINDS) == set(pdf_formatter._QUANTITY_FORMATTERS)`
   - for every kind, `canonical_system(kind)` is a key of its `systems` map
   - for every kind, the canonical system maps to exactly one component key (the direct path assumes a single scalar; a compound kind needs a different seam)
   - for every `(kind, system)` where `system` is not canonical, `(kind, system)` is in `form_logic._NON_CANONICAL_CONVERTERS`, and the converter table contains no pair outside the registry
   - the registry is non-empty (guards against the assertions becoming vacuous)

   Extend the module docstring to explain why a presentation-layer formatter table is asserted in a wiring test: the tables cannot import each other without breaching layering, so the test is the only place the contract can be enforced. Note that this pulls `fpdf` into an otherwise dependency-light file, which is acceptable as it is already a hard dependency.

**`tests/test_pdf_generation.py`**

7. Add a case proving dispatch happens on `quantity_kind`, and a case where the sidecar entry omits `quantity_kind` and still renders as weight (the backward-compatibility default).

---

## Task 4: Frontend

### A. State of the world

The backend is complete. The client state view now carries `quantity_kind` on every quantity question and reports each answered quantity's own system. The frontend still keys `UNIT_COMPONENTS` on system alone and hardcodes `"kg"` in two places.

Behaviour must not change: one shared toggle, toggling clears rather than converts, metric-only range notice, same visible labels.

### B. Files and deliverables

| File | Deliverable |
| --- | --- |
| `frontend/src/types.ts` | `QuantityKind` type; `quantity_kind` on `ClientQuestion` |
| `frontend/src/helpers.ts` | Kind-first `QUANTITY_KINDS`; `emptyComponents` signature change; `initialUnitSystem` change; display formatter table |
| `frontend/src/screens/EditScreen.tsx` | Kind-driven component rendering; generalised range check |
| `frontend/src/screens/ReviewScreen.tsx` | Kind-keyed display formatter |
| `frontend/src/helpers.test.ts`, `EditScreen.test.tsx`, `ReviewScreen.test.tsx` | Fixtures and cases updated |

### C. Instructions

**`types.ts`**

1. Add `export type QuantityKind = "weight";` and `quantity_kind?: QuantityKind;` to `ClientQuestion` alongside the other quantity fields. Comment that `UnitSystem` stays `"metric" | "imperial"` because that is the vocabulary of every registered kind today, and that a kind with its own systems widens it.

**`helpers.ts`**

2. Replace `UNIT_COMPONENTS` with a structure mirroring the backend registry:

   ```ts
   export const QUANTITY_KINDS: Record<QuantityKind, {
     canonicalSystem: UnitSystem;
     systems: Record<string, readonly string[]>;
   }> = {
     weight: {
       canonicalSystem: "metric",
       systems: { metric: ["kg"], imperial: ["st", "lb"] },
     },
   };
   ```

   Comment that this mirrors `ruleset.QUANTITY_KINDS` and that parity is a manual obligation — no automated check spans the language boundary.

3. `emptyComponents(kind, system)` gains the kind parameter and reads from `QUANTITY_KINDS`. Update `initialiseEditableAnswers`, which has the question in scope.

4. `initialUnitSystem` seeds from the first quantity question with **more than one** allowed system. Delete the multi-quantity tie-break TODO — the startup check in `ruleset.py` guarantees multi-system questions agree, so no client-side tie-break exists.

5. Add the display formatter table used by `ReviewScreen`:

   ```ts
   export const QUANTITY_DISPLAY_FORMATTERS: Record<QuantityKind, (v: QuantityValueView) => string> = {
     weight: (v) => v.system === "imperial"
       ? `${v.components.st ?? ""} st ${v.components.lb ?? ""} lb`
       : `${v.components.kg ?? ""} kg`,
   };
   ```

**`EditScreen.tsx`**

6. `handleComponentChange(answerKey, componentKey, value)` needs the kind for its `emptyComponents` fallback. Add a `kind` parameter and pass it from the render block, which has `q` in scope. The other two call sites (`handleUnitSystemChange`, which loops over questions, and the render block) already have it.

7. The component input loop reads `QUANTITY_KINDS[kind].systems[unitSystem]` instead of `UNIT_COMPONENTS[unitSystem]`.

8. Generalise the range check. Replace the hardcoded `"kg"` with the kind's canonical component key, and replace `unitSystem === "metric"` with a comparison against the kind's canonical system. Preserve the documented limitation: the advisory notice is shown only in the canonical system, because `min`/`max` are expressed in canonical units and do not map cleanly onto the others.

9. Leave `UNIT_SYSTEM_LABELS` and `COMPONENT_LABELS` flat and unchanged. Component keys are unique across kinds in practice, and `UNIT_SYSTEM_LABELS` is exactly what Ticket 2 relabels — restructuring it now while forbidding a text change would be churn. Add a comment recording both assumptions.

10. Do not add a fixed-unit render path for single-system questions (design decision 8).

**`ReviewScreen.tsx`**

11. Replace the local `formatQuantityAnswer` with a lookup into `QUANTITY_DISPLAY_FORMATTERS` keyed on the question's `quantity_kind`, defaulting to `"weight"` when absent. Keep the comment explaining that this shows what the patient typed and that the canonical conversion appears on the clinical PDF, not here.

**Tests**

12. `helpers.test.ts`: add `quantity_kind: "weight"` to the question fixtures at lines 45, 55, 65, 147. Replace the `UNIT_COMPONENTS` assertions at lines 86–89 with the kind-first structure. Update `emptyComponents` calls for the new signature. Add cases for `initialUnitSystem` skipping a single-system question, and for the weight display formatter.

13. `EditScreen.test.tsx`: add `quantity_kind: "weight"` to `quantityQuestion` (line 564) and the number question fixture at line 476 if it carries quantity fields. All existing assertions must pass unchanged.

14. `ReviewScreen.test.tsx`: add `quantity_kind: "weight"` to the fixture at line 249. Existing rendering assertions unchanged.

---

## Task 5: Documentation

### A. State of the world

All code is complete and CI is green. These are user-maintained documents; the changes below are the statements this ticket has falsified or added.

### B. Files and deliverables

`arch_ruleset_schema.md`, `arch_core_engine.md`, `arch_submission.md`, `arch_frontend.md`, `arch_testing.md`.

### C. Instructions

**`arch_ruleset_schema.md`**

- Add `quantity_kind` to the schema shape block, in the quantity field group.
- In the quantity constraint paragraph: `quantity_kind` is required on a quantity question and must be one of the registered kinds; `allowed_systems` is validated against that kind's own vocabulary, not a global pair; the fields must be absent when `quantity` is unset.
- Add the shared-toggle rule: quantity questions offering more than one system must agree on `allowed_systems` and `default_system`, because the client toggle is form-wide. Single-system questions are exempt. Record the reason (an unclearable 422) so it is not mistaken for a stylistic rule.
- Rewrite the "Kilograms is the canonical unit" paragraph: each kind declares its own canonical system, and `min`/`max` are expressed in that kind's canonical unit. Weight is the only registered kind today.

**`arch_core_engine.md`**

- Line 39: the core resolves to the question's kind's canonical unit, not universally kilograms.
- Line 41: the chosen system is recorded per answer in `AnswerState.unit_system`, not once per form. Explain why: the system is a property of an answer, and the inbound wire shape was already per-answer.
- Line 44 (the "Deferred" bullet): cross-question consistency is no longer deferred, it is deliberately not enforced at runtime. Record the design decision and the accepted consequence (a direct-API client can mix units; each answer converts and renders correctly). Replace the "second quantity kind" deferral with a pointer to the registry as the extension seam.
- Line 60: `unit_conversion.py` holds per-kind arithmetic; dispatch lives in `form_logic.py`.
- Note the compound-kind limitation: the canonical system must map to exactly one component, so blood pressure and similar kinds need a separate seam.

**`arch_submission.md`**

- Line 258: `ClinicalOutput` no longer carries a top-level `unit_system`. Describe the four-key sidecar entry (`quantity_kind`, `raw_components`, `unit_system`, `decimal_places`) and why the sidecar exists (the PDF has no ruleset).
- Line 268: the client view carries `quantity_kind`; the PDF dispatches on it; the weight formatter derives the system from the component keys.

**`arch_frontend.md`**

- Line 84: the toggle seeds from the first multi-system quantity question; the tie-break TODO is gone because ruleset validation guarantees agreement.
- Record two limitations: single-system quantity questions have no render path yet, and frontend/backend registry parity is a manual obligation with no automated check.

**`arch_testing.md`**

- New and changed cases: `test_ruleset.py` (kind validation, shared-toggle check), `test_wiring.py` (registry parity — note the section now imports `pdf_formatter`), `test_serialisation.py` (per-answer system, sidecar shape), `test_pdf_generation.py` (kind dispatch, missing-kind default), `helpers.test.ts` (kind-first structure, display formatter), `ReviewScreen.test.tsx`.
- No new test files are created, so no `pytestmark` or `ci.yml` changes are needed.

---

## Verification before merge

1. `data/` contains no ruleset with a `quantity: true` question other than `numeric_capability_demo.json`. Startup is fail-fast; a missed file takes the app down on deploy.
2. Full pytest and vitest suites green.
3. Deploy to Railway and walk the demo condition end to end in both systems, confirming the PDF renders `"11 st 11 lb (74.8 kg)"` and `"70.5 kg"` exactly as before.
4. Any submissions persisted in dev or staging before this change: confirm PDF regeneration still succeeds, or clear them. The system is not live, so this is a convenience check rather than a data-integrity one.


---

## Task 1: Ruleset schema, kind registry and data migration

### A. State of the world

Nothing has been completed yet; this is the first task. The engine does not read `quantity_kind` at the end of this task — the validation is purely additive, and the JSON migration lands in the same commit so no ruleset is left invalid.

### B. Files and deliverables

| File | Deliverable |
| --- | --- |
| `app/services/engine/ruleset.py` | `QUANTITY_KINDS` registry, `VALID_QUANTITY_KINDS`, two accessors, `quantity_kind` validation, per-kind `allowed_systems` validation, shared-toggle check; `VALID_UNIT_SYSTEMS` deleted |
| `data/numeric_capability_demo.json` | `"quantity_kind": "weight"` added |
| `tests/test_ruleset.py` | Existing quantity fixtures updated; new accept/reject cases |

### C. Instructions

**`ruleset.py`**

1. Delete `VALID_UNIT_SYSTEMS`. Add the `QUANTITY_KINDS` registry from design decision 9, `VALID_QUANTITY_KINDS = frozenset(QUANTITY_KINDS)`, and two module-level accessors:
   - `canonical_system(kind: str) -> str`
   - `component_keys(kind: str, system: str) -> tuple[str, ...]`

   Document in a module comment that this registry is the single source of truth for kinds and that `form_logic.py` and `pdf_formatter.py` hold parallel tables kept in step by `test_wiring.py`.

2. In `_validate_quantity_fields`, when `quantity is True`:
   - `quantity_kind` must be present, a string, and in `VALID_QUANTITY_KINDS`. The error must list the allowed kinds.
   - `allowed_systems` entries must be keys of `QUANTITY_KINDS[kind]["systems"]`, not a global set. Keep the existing non-empty, list-type and duplicate checks unchanged.
   - `default_system` check is unchanged.

3. In the `else` branch (non-quantity questions), add `quantity_kind` to the list of fields that must be absent, alongside `allowed_systems` and `default_system`. Same rationale as the existing rule: a field set without the flag would be silently ignored.

4. Add `_validate_shared_toggle_consistency(ruleset)` and call it from `validate_ruleset` after the per-question loop. Collect every quantity question with `len(allowed_systems) > 1`. If there are two or more, assert they all share the same `set(allowed_systems)` and the same `default_system`; raise `ValueError` naming the disagreeing `answer_key`s. Questions with exactly one allowed system are excluded. The docstring must state the reason: the client toggle is form-wide, so a mismatch would render a question in a system it rejects and give the patient an unclearable 422.

**`data/numeric_capability_demo.json`**

Add `"quantity_kind": "weight"` to the `patient_weight_kg` question. Before merging, verify against the real `data/` directory that no other ruleset has a `quantity: true` question — startup is fail-fast, so a missed file takes the whole app down on deploy. The project files contain only `general.json` (no Number questions) and `numeric_capability_demo.json`, but the project files may not mirror `data/`.

**`tests/test_ruleset.py`**

5. Every existing `_with(quantity=True, ...)` call must gain `quantity_kind="weight"`. There are roughly ten, at lines 136–216. They will all fail otherwise; this is expected and is the first signal the validation is live.

6. New cases:
   - accepts a valid quantity question carrying `quantity_kind`
   - rejects a quantity question with `quantity_kind` missing
   - rejects an unknown `quantity_kind` (e.g. `"mass"`)
   - rejects `allowed_systems` containing a value outside the kind's vocabulary (e.g. `["metric", "nautical"]`) — this replaces the existing global-set test
   - rejects `quantity_kind` set on a non-quantity question
   - accepts two multi-system quantity questions that agree
   - rejects two multi-system quantity questions with differing `allowed_systems`
   - rejects two multi-system quantity questions with differing `default_system`
   - accepts a single-system quantity question alongside a multi-system one (proves the exemption)

   The last four need a two-question fixture; `_base_ruleset()` has one question, so add a local helper rather than reshaping the existing one.

7. `test_ruleset.py` gains cases: prompt for `arch_testing.md` update at the end of the ticket (Task 5).

---

## Task 2: Data model and engine conversion

### A. State of the world

Task 1 is complete: `quantity_kind` is a required, validated field on every quantity question, the registry lives in `ruleset.py`, and the demo ruleset is migrated. Nothing reads `quantity_kind` yet and the unit system is still a form-wide field.

This task moves the unit system onto the answer and makes the conversion path kind-generic. It is behaviour-preserving: identical inputs produce identical canonical values, identical `raw_components`, and an identical PDF.

### B. Files and deliverables

| File | Deliverable |
| --- | --- |
| `app/models/runtime_state.py` | `AnswerState.unit_system` added; `RuntimeState.unit_system` removed |
| `app/services/engine/form_logic.py` | Kind-first conversion via the registry and a converter table; writes the per-answer system |
| `app/services/engine/serialisation.py` | Client view emits `quantity_kind` and the per-answer system; sidecar gains `quantity_kind` and `unit_system` |
| `app/models/serialisation_contracts.py` | `ClinicalOutput.unit_system` removed; sidecar docstring updated |
| `app/utils/pdf_formatter.py` | Call site reads the sidecar; metric-vs-imperial derived from component keys |
| `app/services/engine/unit_conversion.py` | Module comment only |
| `tests/test_form_logic.py`, `tests/test_serialisation.py`, `tests/test_pdf_generation.py` | Fixtures and assertions updated |

### C. Instructions

**`runtime_state.py`**

1. Add `unit_system: str | None = None` to `AnswerState`, immediately after `raw_components`, and include it in `to_dict` and in `from_dict` via `d.get("unit_system")` (same convention as `raw_components`). Type it `str | None`, not a `Literal` — systems are per-kind vocabulary now.

2. Extend the `AnswerState` docstring: `unit_system` is `None` for every answer except an answered quantity-bearing Number question, where it records which of the question's `allowed_systems` the patient used. It is the per-answer companion to `raw_components` and is what lets the client view and the clinical record report the patient's unit without a form-level field.

3. Remove `unit_system` from `RuntimeState`: the field, the `to_dict` entry and the `from_dict` line. Persisted states that still carry the key deserialise cleanly because `from_dict` enumerates fields explicitly and ignores extras.

**`form_logic.py`**

4. Delete `_COMPONENT_KEYS`. Import `QUANTITY_KINDS`, `canonical_system` and `component_keys` from `ruleset.py`.

5. Add the converter table, keyed by `(kind, system)` for every non-canonical system:

   ```python
   _NON_CANONICAL_CONVERTERS: dict[tuple[str, str], Callable[[dict], Decimal]] = {
       ("weight", "imperial"): lambda c: imperial_weight_to_kg(c["st"], c["lb"]),
   }
   ```

   Comment that a new kind registers its conversion function here and its arithmetic in `unit_conversion.py`, and that `test_wiring.py` asserts every non-canonical `(kind, system)` pair has an entry.

6. In `convert_unit_answers`:
   - read `kind = q["quantity_kind"]` with direct access (validation guarantees presence; a `KeyError` here is a programming error, not client input)
   - `expected_keys = set(component_keys(kind, system))` replaces the `_COMPONENT_KEYS[system]` lookup
   - replace the `if system == "metric"` branch with `if system == canonical_system(kind)`. The canonical branch reads the kind's single canonical component key rather than the literal `"kg"`, runs it through `_validate_number_value`, and stores `{key: format(canonical, "f")}` in `raw_components`.
   - the non-canonical branch looks up `_NON_CANONICAL_CONVERTERS[(kind, system)]`, calls it with the components dict, translates `ValueError` to `AnswerValidationError` as now, and quantizes to `decimal_places`. Persisting whole-number components as ints stays, but generalise it to iterate the kind's component keys instead of naming `st` and `lb`.
   - replace `runtime.unit_system = system` with `a.unit_system = system`

   Update the docstring: the canonical unit is the question's kind's canonical system, not kilograms; the chosen system is recorded per answer; the closing paragraph about deferred cross-question consistency is replaced by a note that agreement is a client convention enforced at authoring time in `ruleset.py`.

**`unit_conversion.py`**

7. Comment only, no functional change. Note that per-kind dispatch lives in `form_logic._NON_CANONICAL_CONVERTERS` and that a new kind adds its arithmetic here and registers it there.

**`serialisation.py`**

8. In `serialize_client_state`, for a quantity question: emit `question_dict["quantity_kind"] = q["quantity_kind"]`, and build `current_value` from `answer.unit_system` instead of `runtime.unit_system`.

9. In `clinical_output`, each sidecar entry becomes:

   ```python
   quantity_answers[key] = {
       "quantity_kind": q["quantity_kind"],
       "raw_components": a.raw_components,
       "unit_system": a.unit_system,
       "decimal_places": q["decimal_places"],
   }
   ```

   Remove `unit_system=runtime.unit_system` from the `ClinicalOutput(...)` call. Update the comments that describe the canonical value as kilograms.

**`serialisation_contracts.py`**

10. Remove the `unit_system` field from `ClinicalOutput` and its line in `from_dict`. Update the `quantity_answers` comment to describe the four-key entry shape. Keep `quantity_answers=data.get("quantity_answers") or {}`.

**`pdf_formatter.py`**

11. Change `_format_quantity_answer` to take `(canonical_value, raw_components, decimal_places)` — drop the `unit_system` parameter — and detect imperial by `"st" in raw_components`. Update the call site to stop passing `clinical_output.unit_system`. Comment that the component keys are unambiguous for weight and that this keeps PDF regeneration working for records written before the sidecar carried a system. The internal restructure into a kind-dispatched table is Task 3.

**Tests**

12. `test_form_logic.py`: add `"quantity_kind": "weight"` to `_quantity_ruleset` (line 455). This fixture never calls `validate_ruleset`, so it does not fail in Task 1 — it fails here, when `convert_unit_answers` reads the key. Rewrite the eight `rt.unit_system` assertions (lines 492, 525, 560, 607, 637, 649 and neighbours) to read `rt.answers["weight"].unit_system`.

13. `test_serialisation.py`: add `"quantity_kind": "weight"` to `_quantity_ruleset` (line 149). `_quantity_runtime` (line 173) must set the system on the `AnswerState`, not on `RuntimeState`. Rewrite `test_clinical_output_records_unit_system` (line 266) to assert the sidecar entry, and the `from_dict` round-trip assertions at lines 306 and 331. Add a case asserting the client view emits `quantity_kind`. Check any assertion comparing a whole question dict for equality — the new key will break it.

14. `test_pdf_generation.py`: `_quantity_output` (line 1043) drops the `unit_system=` constructor argument and moves the system into the sidecar entry. The existing imperial and metric rendering assertions must pass unchanged — that is the definition of done for this task.