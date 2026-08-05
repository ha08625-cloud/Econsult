# Implementation Plan: Recursive `any` / `all` Safety Clauses

## Plan

Today a safety rule is one flat OR: `rule["any"]` holds a list of leaf clauses, each of which is
`{"is_true": "<answer_key>"}` or `{"is_false": "<answer_key>"}`. There is no way to author "fever
AND flank pain" — only "fever OR flank pain".

This plan lets a clause be a nested group — `{"any": [...]}` or `{"all": [...]}` — evaluated
recursively, so rules can mix AND and OR. The top-level rule shape is unchanged: still
`{"any": [...], "message": "..."}`.

The engine change is small (~15 lines). The larger and more delicate half is `ruleset.py`, whose
validator currently rejects any clause that is not exactly one of `is_true`/`is_false` with no other
keys (`ruleset.py:362-380`). Without changing it, a nested clause aborts startup and the feature is
unreachable — every unit test would pass and no ruleset could ever use it.

Three tasks: engine, validator, documentation. No data model changes, no pipeline changes, no
frontend or PDF work, and no ruleset in `data/` adopts nesting in this ticket — so the whole change
is a behavioural no-op in production until a separate authoring ticket uses it.

---

## Scope

**In scope**

- `app/services/engine/safety_engine.py` — recursive clause evaluation
- `app/services/engine/ruleset.py` — recursive clause validation
- `tests/test_safety_engine.py` — nesting, `None` inside `all`, empty-group behaviour
- `tests/test_ruleset.py` — accept nested groups, reject malformed ones; revise three existing tests
- `documentation/arch_safety.md` — the "ANY logic" section, plus the `all`-with-unknown decision
- `documentation/arch_ruleset_schema.md` — clause grammar and the `any`-vs-`all` statements

**Out of scope**

- **Any change to `data/*.json`.** No existing ruleset needs nesting today. Adopting it in a real
  ruleset is a separate clinical-authoring ticket, and keeping it out of this one means this change
  cannot alter what any patient sees.
- **New leaf condition types.** `is_true` / `is_false` remain the only leaves.
- **Pipeline, projection, or `ExplicitAnswers` changes.** The safety boundary is untouched.
- **`SafetyEvaluation`, `triggered_rules`, or message payload shape.** Unchanged.
- **Frontend and PDF.** Neither reads clause structure.
- **`all` at the top level of a rule.** A rule must still be `{"any": [...]}`. An author who wants
  a whole-rule AND writes `{"any": [{"all": [...]}]}`. See design decision 2.

---

## Design Decisions

**1. Ship the engine before the validator.**
Between the two commits there is a window where one half of the feature exists. Engine-first is the
safe order: no committed ruleset uses nesting, so a recursive engine is inert, and the validator
still rejects nested rulesets at startup. Validator-first would open a window where a nested rule
validates cleanly, boots, and is then silently mis-evaluated by the flat engine — the exact
"validates cleanly, never fires" failure the comments at `ruleset.py:332-335` and `352-361` were
written to close.

**2. The top-level rule keeps its mandatory `any`.**
`rule["all"]` stays a startup error. This is now a deliberate restriction rather than typo
protection: a rule is a list of independent triggers, and OR is the clinically correct default for a
red-flag list. An author wanting AND across the whole rule nests one `all` group inside `any`, which
makes the intent explicit at the point of authoring and keeps every rule readable the same way.

**3. A clause has exactly one key, at every depth.**
A clause must contain exactly one of `is_true`, `is_false`, `any`, `all`, and nothing else. Leaf
values must be strings naming a declared `answer_key` whose `answer_type` is `"Boolean"`; group
values must be non-empty lists of clauses. This extends the existing "exactly one of" discipline
rather than inventing a second grammar. Without it, `{"is_true": "x", "all": [...]}` would let the
engine's key-dispatch order silently decide clinical meaning.

**4. Empty groups are rejected at every depth, because `all([])` is `True`.**
This is the sharpest trap in the feature. Python evaluates `all([])` to `True`, so a clause of
`{"all": []}` satisfies its rule unconditionally — and per `arch_safety.md`, any triggered rule
blocks submission. One typo would block every patient on that condition with a message they cannot
clear by changing their answers. The mirror, `{"any": []}`, is `False` and silently never fires. The
existing non-empty check at `ruleset.py:340` covers only the rule's top-level `any`; the recursive
validator must apply it to every nested group.

**5. Nesting is capped at three group levels.**
`MAX_SAFETY_CLAUSE_DEPTH = 3`, where the rule's own `any` is level 1. This is not about stack
safety — rulesets are finite authored JSON. It is so that a clinician reviewing a rule can hold it
in their head. Three levels expresses anything realistic (`any` of `all`s of `any`s); more is a sign
the rule should be split.

**6. Unknown answers make an `all` group unsatisfied.**
A leaf with a `None` answer returns `False`, so a single unknown defeats an enclosing `all`. This
follows directly from existing `None` semantics — "unknown" is not "true", and an `all` cannot be
proven when part of it is unanswered — and needs no tri-state logic. It is worth recording
explicitly because it is a new clinical exposure: AND rules are precisely the ones an unanswered
question can silently defeat. `{"all": [fever, flank_pain]}` with `fever=True` and `flank_pain`
unanswered does not fire.

**7. Malformed clauses return `False` in the engine, but that is a backstop, not the safety
mechanism.**
A clause matching none of the four keys evaluates to `False`. Note the direction honestly: a rule
that does not fire means the patient is *not* warned and *not* blocked, which is the unsafe
direction, not a safe default. The actual protection is task 2 — the validator makes malformed
clauses unreachable at startup, per the fail-fast invariant in `architecture.md` ("must never
silently degrade into a state where safety rules are skipped"). The `False` return exists only so a
bug elsewhere cannot raise mid-request.

**8. Leaf evaluation is preserved verbatim.**
The existing `is_true` / `is_false` logic is moved into the recursive helper unchanged, including
its behaviour on a clause carrying both keys. Validation rejects that shape, so the path is dead —
but leaving it alone means every existing flat test passes without modification, which is the
cheapest available proof that the refactor changed nothing it should not have.

**Open question (does not block implementation):** every ruleset in `data/` uses flat `any` today,
and `data/uti1.json:87-88` deliberately groups fever and flank pain as OR. Adding `all` makes red
flags fire *less* often by construction. Worth naming the specific clinical rule that needs this
before a ruleset adopts it in the follow-up ticket.

---

## Task 1: Engine — recursive clause evaluation

**A. State of the world**

Nothing in this plan has been implemented yet. `evaluate_safety` in
`app/services/engine/safety_engine.py` walks `rule["any"]` with an inline `for`/`break` loop
(lines 27-41) that understands only leaf clauses. This task makes evaluation recursive so a clause
can be a nested `{"any": [...]}` or `{"all": [...]}` group. The validator still rejects nested
rulesets at startup after this task — that is expected and is fixed in task 2. No ruleset in `data/`
uses nesting, so this task changes no production behaviour.

**B. Files and deliverables**

- `app/services/engine/safety_engine.py` — add a module-level `_clause_satisfied(clause, answers) ->
  bool`; rewrite the inline loop to use it; update the docstring's Semantics block.
- `tests/test_safety_engine.py` — new test cases for nesting. Existing tests must pass **unmodified**.

**C. Instructions**

1. Add `_clause_satisfied(clause: dict, answers: dict) -> bool` above `evaluate_safety`. Dispatch in
   this order:
   - `is_true` / `is_false` — move the existing leaf logic across verbatim: satisfied when
     `answers.get(key) is True` / `is False` respectively. Do not restructure it, do not "fix" the
     case where both keys are present.
   - `"any" in clause` → `any(_clause_satisfied(c, answers) for c in clause["any"])`
   - `"all" in clause` → `all(_clause_satisfied(c, answers) for c in clause["all"])`
   - otherwise → `False`
2. Guard the group branches against a non-list value (return `False`) so a malformed clause cannot
   raise mid-request. Validation makes this unreachable; it is a backstop only.
3. In `evaluate_safety`, replace the `for cond in conditions` loop with
   `satisfied = any(_clause_satisfied(c, answers) for c in rule.get("any", []))`. Keep reading
   `rule["any"]` directly — do **not** pass the whole `rule` dict into `_clause_satisfied`. A rule
   also carries `"message"`, so treating it as a clause would mean the helper accepts dicts with
   stray keys, which is the shape validation exists to reject.
4. Everything below the loop — `triggered_rules`, the message payload, `SafetyEvaluation` — is
   unchanged.
5. Update the docstring's Semantics block: a clause is either a leaf (`is_true`/`is_false`) or a
   group (`any`/`all`) evaluated recursively; `None` remains unknown and satisfies neither, so an
   unknown leaf makes an enclosing `all` unsatisfied.
6. New tests to add:
   - `all` group inside a rule's `any`: fires only when every leaf is satisfied
   - `any` group nested inside an `all` group
   - three levels of nesting (`any` > `all` > `any`)
   - `None` inside an `all` group does not satisfy it, even when every other leaf does
   - `None` inside a nested `any` group is ignored, as at the top level
   - a clause with no recognised key does not fire
   - **document current behaviour for empty groups**: `{"any": []}` does not fire and `{"all": []}`
     *does* fire (vacuous truth). Assert both, with a comment pointing at task 2 as the reason
     neither can reach production. These tests pin the exact hazard the validator closes.
7. This file has no `pytestmark` and must not gain one — `evaluate_safety` is a pure function and
   these are unit tests. `arch_testing.md` needs no change (no new test file).
8. Check before finishing: `ruff check app/services/engine/safety_engine.py tests/test_safety_engine.py`
   and `python -m pytest tests/test_safety_engine.py`. Skip the full suite and skip the build — CI's
   unit job is the real gate.

---

## Task 2: Validator — recursive clause validation in `ruleset.py`

**A. State of the world**

Task 1 is complete: `safety_engine.py` evaluates nested `any` / `all` groups recursively. But
`validate_ruleset` in `app/services/engine/ruleset.py` still enforces the flat grammar — a clause
must contain exactly one of `is_true` / `is_false` and no other keys (lines 362-380) — so any
ruleset using a nested group raises `ValueError` and aborts startup. This task teaches the validator
the nested grammar, which is what actually makes the feature usable. Validation runs at startup only;
there is no runtime re-validation.

**B. Files and deliverables**

- `app/services/engine/ruleset.py` — a `MAX_SAFETY_CLAUSE_DEPTH` constant and a module-level
  recursive clause validator; the inline clause loop inside `validate_ruleset` calls it.
- `tests/test_ruleset.py` — new acceptance and rejection cases; three existing tests revised.

**C. Instructions**

1. Add a module-level constant `MAX_SAFETY_CLAUSE_DEPTH = 3` near the other module constants, with a
   comment that the rule's own `any` list is depth 1 and the cap exists for author/reviewer
   legibility, not stack safety.
2. Add a module-level helper, e.g.:

   ```
   _validate_safety_clause(clause, rule_id, seen_answer_keys, answer_key_types, depth)
   ```

   `seen_answer_keys` and `answer_key_types` are locals built in `validate_ruleset`
   (`ruleset.py:276-278`) and must be threaded through the recursion so nested leaves get the same
   declared-key and Boolean checks as top-level ones. `depth` is the group level containing this
   clause; `validate_ruleset` passes `1`.
3. The helper enforces, in order:
   - clause is a dict — reuse the existing "not an object" message
   - **exactly one** of `is_true`, `is_false`, `any`, `all` is present — extend the existing
     "exactly one" message to name all four keys
   - no keys outside that set — reuse the existing "unexpected keys" message
   - leaf (`is_true` / `is_false`): value is a string; the key is in `seen_answer_keys`; its
     `answer_key_types` entry is `"Boolean"`. Keep the three existing error messages as they are —
     `tests/test_ruleset.py` matches on `"must be a string"`, `"unknown answer_key"` and
     `"not 'Boolean'"`.
   - group (`any` / `all`): value is a list; the list is **non-empty**; `depth + 1` does not exceed
     `MAX_SAFETY_CLAUSE_DEPTH`; then recurse into each child at `depth + 1`.
   - Error messages must include `rule_id`, and for nested failures should indicate the nesting so an
     author can find the clause in a deep rule.
4. In `validate_ruleset`, leave the rule-level checks alone (lines 336-350: `any` required, is a
   list, non-empty; `message` required, non-empty string). Replace only the body of the
   `for clause in rule["any"]` loop with a call to the helper at `depth=1`.
5. Rejecting an empty nested group is the single most important check here — `all([])` is `True`, so
   `{"all": []}` would fire its rule for every patient and block every submission on that condition.
   Give it its own test and its own comment.
6. New tests in the safety section of `tests/test_ruleset.py` (reuse the `_with_safety_rule` helper
   at line 501):
   - accepts `{"all": [...]}` nested inside a rule's `any`
   - accepts `any` nested inside `all`
   - accepts three group levels; rejects four (match on the depth message)
   - rejects `{"all": []}` and `{"any": []}` nested — separate tests, since only one of them is
     dangerous and the comments should say which
   - rejects a group whose value is not a list
   - rejects a clause mixing a leaf and a group, e.g. `{"is_true": "diarrhoea", "all": [...]}`
   - rejects `{"any": [...], "all": [...]}`
   - rejects a nested leaf referencing an unknown `answer_key`, and one referencing the `text`
     question — proving the checks reach into the recursion
7. Three existing tests need attention:
   - `test_rejects_clause_with_unexpected_key` (line 528) — `note` is still rejected; confirm the
     assertion still matches once the allowed-key set has four members.
   - `test_rejects_clause_with_neither_key` (line 523) — `{}` is still rejected; update the comment
     if it names only two keys.
   - `test_rejects_rule_with_typo_key_instead_of_any` (line 570) — **keep the test, rewrite the
     comment.** Its rationale changes from "that's a typo" to "`all` is legal nested but deliberately
     not at the top level of a rule; author a whole-rule AND as `{"any": [{"all": [...]}]}`". Without
     that, a future reader will read it as obsolete and relax it. Consider renaming it to
     `test_rejects_all_at_rule_top_level`.
8. Do not modify `tests/test_wiring.py` — its safety rule at line 145 uses an unknown `answer_key` to
   assert startup failure and is unaffected.
9. No `pytestmark` changes; no new test files; `arch_testing.md` unchanged.
10. Check before finishing: `ruff check app/services/engine/ruleset.py tests/test_ruleset.py`, then
    `python -m pytest tests/test_ruleset.py tests/test_safety_engine.py tests/test_data_rulesets.py`.
    The last one validates the real `data/` tree and proves no existing ruleset regressed. Skip the
    full suite and the build.

---

## Task 3: Documentation

**A. State of the world**

Tasks 1 and 2 are complete: the engine evaluates nested `any` / `all` groups and the validator
accepts and constrains them. Two architecture documents now describe behaviour that no longer
exists and must be corrected. No code changes in this task.

**B. Files and deliverables**

- `documentation/arch_safety.md` — rewrite the "Safety rules use ANY logic" section (lines 37-39);
  add the `all`-with-unknown decision to the `None` semantics section.
- `documentation/arch_ruleset_schema.md` — update the `safety` block in the schema shape, and the
  three safety paragraphs under "Design Constraints".

**C. Instructions**

1. `arch_safety.md`, the "Safety rules use ANY logic" section — the sentence "The engine does not
   support AND-only rules at the top level" is now half-wrong. Replace the section with: a rule
   still fires when any clause in its top-level `any` is satisfied; a clause is now either a leaf
   (`is_true` / `is_false`) or a nested `any` / `all` group, evaluated recursively; `all` is not
   permitted at the top level of a rule, so a whole-rule AND is authored as
   `{"any": [{"all": [...]}]}`. Record why (design decision 2): a rule is a list of independent
   triggers and OR is the correct default for a red-flag list.
2. `arch_safety.md`, the `None` semantics section — append design decision 6. State plainly that an
   unknown leaf makes an enclosing `all` unsatisfied, give the fever/flank-pain example, and name the
   exposure: AND rules are the ones an unanswered question can silently defeat. This is the entry a
   future clinical reviewer most needs.
3. `arch_ruleset_schema.md`, the schema shape block — extend the `safety.rules` example to show a
   nested group alongside the leaf form.
4. `arch_ruleset_schema.md`, "Safety rules use `"any"` (OR) semantics" — the claim "The key must be
   `"any"`, not `"all"` — both the validator in `ruleset.py` and the engine in `safety_engine.py`
   read this key" is now true only of a rule's top level. Rewrite it to say exactly that.
5. `arch_ruleset_schema.md`, "Safety clauses have a strict, closed shape" — this paragraph is the
   grammar and is now wrong. Rewrite it as design decision 3 plus the constraints from task 2: a
   clause holds exactly one of `is_true`, `is_false`, `any`, `all`; leaves are strings naming
   declared Boolean `answer_key`s; groups are non-empty lists of clauses; nesting is capped at
   `MAX_SAFETY_CLAUSE_DEPTH` (3, counting the rule's own `any` as level 1). State the reason empty
   groups are rejected — `all([])` is `True`, so an empty `all` would fire its rule for every
   patient — because that is the constraint an author is most likely to think is pedantic.
6. `arch_ruleset_schema.md`, "Safety rules reference only declared `answer_key`s" — still true;
   clarify that it holds at every nesting depth.
7. Keep to the documented style: design decisions and invariants, no duplication of function
   signatures or implementation detail that is readable in the code.
