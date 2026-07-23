# Provisional plan: quantity_kind generalisation (Ticket 1)

Make the shared/global unit toggle a properly validated, quantity-kind-generic mechanism, with no hardcoded weight/kg assumptions left in the parts of the pipeline that do not need clinical meaning. **No new quantity kind is introduced in this ticket** — "weight" is still the only supported kind at the end of it. Same observable behaviour, safer plumbing, one new validation path (Step 3).

## Scope

In scope: `ruleset.py`, `form_logic.py`, `serialisation.py`, `serialisation_contracts.py`, `pdf_formatter.py`, `unit_conversion.py` (comment only), ruleset JSON migration, `types.ts`, `helpers.ts`, `EditScreen.tsx`, associated tests, `test_wiring.py`, `arch_ruleset_schema.md`.

Out of scope: any new quantity kind; toggle button relabelling ("Metric"/"Imperial" without unit hints) — deferred to Ticket 2 so this ticket stays strictly behaviour-preserving apart from Step 3; per-component min/max (a future compound-kind ticket, e.g. blood pressure, would need it — noted here so it is not mistaken for trivial later).

## Design decisions (confirmed)

1. **Closed set of complete kinds.** `quantity_kind` is validated at startup against a closed set containing only kinds with complete wiring (component-key map, converter, formatter entry). In this ticket the set is `{"weight"}`. Ticket 2 adds `"height"` in the same commit as its full wiring, so a ruleset can never declare a kind the engine cannot fully handle. Declaring a kind ahead of its wiring would violate the fail-fast invariant.

2. **Per-kind system vocabulary.** `allowed_systems` values are validated against the declared kind's own component map, not a global `{"metric", "imperial"}` set. Weight's vocabulary is `{"metric", "imperial"}` today; a future single-system kind (e.g. blood pressure in mmHg) defines its own. This is a one-line difference in validation now versus a migration later.

3. **Consistency rules exempt single-system questions (option B).** Chosen over the strict form-wide rule (option A) because option A would make a single-system kind (e.g. blood pressure) unable to coexist with weight on one form and would have to be unwound.
   - Ruleset-level: all quantity questions offering **more than one** system must share identical `allowed_systems` and identical `default_system`. Single-system questions are exempt (degenerate toggle).
   - Runtime-level: collect submitted systems only from multi-system questions; if more than one distinct system appears, reject with `AnswerValidationError` (422) naming the disagreeing questions. Single-system questions are already forced onto their sole system by the existing per-question `system not in allowed_systems` check.
   - With weight as the only kind, both rules behave identically to option A today.
   - Known constraint to record in `arch_ruleset_schema.md`: the form-global toggle assumes every *multi-system* kind supports the same system set. Single-system kinds sit outside the toggle.

4. **Registry parity enforced by wiring test, not runtime errors.** Kinds live in parallel tables in `ruleset.py`, `form_logic.py`, and `pdf_formatter.py`. `VALID_QUANTITY_KINDS` is derived from the component-key registry, and a `test_wiring.py` case asserts all tables share identical key sets. A `NotImplementedError` in the converter dispatch remains as defence in depth, but the parity test is the real guarantee. A single shared registry module was considered and rejected: it would couple presentation formatting to the core engine.

5. **Backward compatibility with persisted submissions.** `pdf_worker.py` regenerates PDFs from persisted `clinical_output_json` (`ClinicalOutput.from_dict`). Records persisted before this change have `quantity_answers` sidecar entries without `quantity_kind`, and in-flight PDF/MESH retry jobs will cross the deploy boundary. A missing `quantity_kind` therefore defaults to `"weight"` at the formatter/deserialisation seam, following the existing `.get()` pattern used for `unit_system` and `photo_quality_tier`. Covered by a dedicated test.

6. **`runtime.unit_system` semantics.** Set once from the agreed system of the multi-system questions, after the runtime consistency check passes — not overwritten per question. If a form someday has only single-system quantity questions it stays `None`; the per-kind formatter dispatch removes the PDF's dependence on the global field for kinds with only one rendering.

## Sequencing

Four steps, each independently testable and revertible. Steps 1 and 2 are behaviour-preserving; Step 3 is the only observable behaviour change; Step 4 is frontend.

---

## Step 1: ruleset schema (standalone, can start immediately)

**`ruleset.py`**
- Add `quantity_kind` as a required field on any question with `quantity: true`.
- Validate against the closed set (`{"weight"}` for now; in Step 2 this becomes derived from the `form_logic.py` registry — acceptable to hardcode in Step 1 and re-point in Step 2).
- Validate `allowed_systems` against the declared kind's system vocabulary (per-kind, not global).
- The engine does not read `quantity_kind` yet in this step; purely additive validation.

**Data migration**
- Add `"quantity_kind": "weight"` to every ruleset JSON with a quantity question. Confirmed in project files: only `numeric_capability_demo.json` (`general.json` has none). **Verify against the real `data/` directory before merging** — fail-fast startup means a missed file takes the whole app down on deploy. Code and JSON land in one atomic commit.

**Tests**
- `test_ruleset.py`: missing `quantity_kind`, unknown kind, `allowed_systems` value not in the kind's vocabulary.

## Step 2: backend dispatch restructure (behaviour-preserving)

**`form_logic.py`**
- Replace flat `_COMPONENT_KEYS = {"metric": {"kg"}, "imperial": {"st","lb"}}` with a kind-first map: `{"weight": {"metric": {"kg"}, "imperial": {"st","lb"}}}`. This map is the source of truth for `VALID_QUANTITY_KINDS` and each kind's system vocabulary.
- New `_canonical_component_key(quantity_kind, system)` — returns `"kg"` for weight/metric; the single seam Ticket 2 extends.
- New `_convert_imperial(quantity_kind, components)` — dispatches to `imperial_weight_to_kg` for `"weight"`; raises `NotImplementedError` (internal error, not 422) for an unregistered kind, as backstop behind the wiring test.
- `convert_unit_answers` reads each question's `quantity_kind` and routes through the new seams. No consistency check yet (Step 3). Per-question behaviour, ordering in the pipeline, and the payload contract (client round-trips the whole answers map) are unchanged.

**`unit_conversion.py`**
- No functional change. Module-level comment noting per-kind dispatch lives in `form_logic.py`; a new kind's conversion function is added here and registered there.

**`serialisation.py`** (shape changes — two, both required)
- Client state view: `question_dict` emits `quantity_kind` for quantity questions (the frontend keys `UNIT_COMPONENTS` on it in Step 4).
- `clinical_output`: each `quantity_answers` sidecar entry gains `quantity_kind`, alongside `raw_components` and `decimal_places`.
- Update comments describing "canonical kg value" to "canonical value for the question's quantity_kind". `unit_system` stays a single form-wide field — correct under the global-toggle design, not a stopgap; correct the comments that call it one.

**`serialisation_contracts.py` / `pdf_formatter.py`**
- `_format_quantity_answer` becomes a thin dispatcher on `quantity_kind` over `_QUANTITY_FORMATTERS: dict[str, Callable]`; existing weight logic moves to `_format_weight_quantity` registered under `"weight"`.
- Missing `quantity_kind` in a sidecar entry defaults to `"weight"` (pre-migration records and in-flight jobs — design decision 5).

**`ruleset.py`**
- Re-point the closed set to derive from the `form_logic.py` registry.

**Tests**
- `test_unit_conversion.py`: no new cases; confirm existing weight cases pass through the restructured path.
- `test_serialisation.py`: sidecar carries `quantity_kind`; client view emits it.
- `test_pdf_generation.py`: kind-dispatched formatter; the missing-kind-defaults-to-weight backward-compat case.
- `test_wiring.py`: parity assertion across the ruleset/form_logic/pdf_formatter kind tables.
- Existing tests must pass unchanged — the definition of done for this step.

## Step 3: consistency checks (the only new behaviour)

**`ruleset.py`**
- `_validate_quantity_kind_consistency(ruleset)`: all multi-system quantity questions must share identical `allowed_systems` and identical `default_system`; single-system questions exempt. Called from `validate_ruleset`.

**`form_logic.py`**
- In `convert_unit_answers`: collect submitted systems from multi-system questions; more than one distinct system raises `AnswerValidationError` naming the disagreeing questions. `runtime.unit_system` is set once, after the check passes. Payload-scoped checking is sufficient because the client contract round-trips the full answers map and the existing dict-shape check already forces full quantity re-submission.

**`arch_ruleset_schema.md`** (user-maintained; prompt for update)
- Record the multi-system consistency rule, the single-system exemption, and the known constraint from design decision 3.

**Tests**
- `test_ruleset.py`: multi-system questions with differing `allowed_systems` rejected; differing `default_system` rejected; single-system question alongside multi-system questions accepted (fixture proves the exemption).
- `test_form_logic.py`: conflicting systems across two multi-system questions rejected; fixture ruleset needed (production has no two-quantity form yet); single-system question does not trip the check.
- `test_form_routes.py`: one integration test submitting conflicting systems, expecting 422.

## Step 4: frontend restructure

**`types.ts`**
- `QuantityKind` type (`"weight"` only, extendable). Add `quantity_kind` to the question view and quantity payload/value types where needed.

**`helpers.ts`**
- Restructure `UNIT_COMPONENTS` to `Record<QuantityKind, Record<UnitSystem, readonly string[]>>`.
- `initialUnitSystem`: seed from the first **multi-system** quantity question. The TODO about disagreeing defaults is deleted — ruleset validation (Step 3) now guarantees multi-system questions agree, so no client-side tie-break exists.

**`EditScreen.tsx`**
- Toggle derived from multi-system questions only; single-system questions render with a fixed unit label and do not participate in the toggle. (No single-system kind exists yet; this is the structural change only.)
- Generalise the `kgNum` range-check to read the canonical component key for the question's `quantity_kind`/metric system instead of hardcoding `"kg"`. Preserve the documented limitation: the advisory range notice is shown only in metric.
- `UNIT_SYSTEM_LABELS`/`COMPONENT_LABELS` keyed to work with the kind-first structure; visible label text unchanged in this ticket (relabelling deferred to Ticket 2).

**Tests**
- `helpers_test.ts`, `EditScreen_test.tsx`: restructured `UNIT_COMPONENTS`, generalised range-check, toggle derivation.

## Open items to confirm before implementation planning

1. Verify no ruleset JSON in the real `data/` directory beyond `numeric_capability_demo.json` has a quantity question.
2. Confirm deferral of toggle relabelling to Ticket 2.
3. On completion, prompt to update `arch_testing.md` (new cases in `test_wiring.py`, `test_serialisation.py`, `test_pdf_generation.py`, fixture rulesets in `test_form_logic.py`/`test_form_routes.py`) and `arch_ruleset_schema.md` (Step 3).
