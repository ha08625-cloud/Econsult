// File path: frontend/src/helpers.test.ts
//
// New test file. Covers the quantity (unit-toggle) helpers added for
// patient-selectable units: editable-answer seeding, the shared-toggle seed,
// component-key maps, and the string->number payload conversion. Vitest
// globals, no React (these are pure functions).

import {
  initialiseEditableAnswers,
  initialUnitSystem,
  emptyComponents,
  quantityComponentsToNumbers,
  UNIT_COMPONENTS,
} from "./helpers";
import type { ClientStateView, ClientQuestion, QuantityValueView } from "./types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function mkQuestion(overrides: Partial<ClientQuestion>): ClientQuestion {
  return {
    answer_key: "q",
    question_text: "Q?",
    answer_type: "number",
    current_value: null,
    required: true,
    suggested: false,
    ...overrides,
  };
}

function mkState(questions: ClientQuestion[]): ClientStateView {
  return {
    condition_label: "Demo",
    free_text: null,
    additional_text: null,
    questions,
  };
}

const unansweredImperialDefault = mkState([
  mkQuestion({
    answer_key: "weight",
    quantity: true,
    default_system: "imperial",
    allowed_systems: ["metric", "imperial"],
    current_value: null,
  }),
]);

const unansweredMetricDefault = mkState([
  mkQuestion({
    answer_key: "weight",
    quantity: true,
    default_system: "metric",
    allowed_systems: ["metric", "imperial"],
    current_value: null,
  }),
]);

const answeredImperial = mkState([
  mkQuestion({
    answer_key: "weight",
    quantity: true,
    default_system: "metric",
    allowed_systems: ["metric", "imperial"],
    current_value: { system: "imperial", components: { st: "11", lb: "11" } },
  }),
]);

// ---------------------------------------------------------------------------
// emptyComponents / UNIT_COMPONENTS
// ---------------------------------------------------------------------------

describe("emptyComponents", () => {
  it("returns a blank kg for metric", () => {
    expect(emptyComponents("metric")).toEqual({ kg: "" });
  });

  it("returns blank st and lb for imperial", () => {
    expect(emptyComponents("imperial")).toEqual({ st: "", lb: "" });
  });
});

describe("UNIT_COMPONENTS", () => {
  it("maps each system to its component keys", () => {
    expect(UNIT_COMPONENTS.metric).toEqual(["kg"]);
    expect(UNIT_COMPONENTS.imperial).toEqual(["st", "lb"]);
  });
});

// ---------------------------------------------------------------------------
// initialUnitSystem
// ---------------------------------------------------------------------------

describe("initialUnitSystem", () => {
  it("defaults to metric when there is no quantity question", () => {
    const state = mkState([
      mkQuestion({ answer_key: "flag", answer_type: "boolean", current_value: true }),
    ]);
    expect(initialUnitSystem(state)).toBe("metric");
  });

  it("uses the question's default_system when unanswered", () => {
    expect(initialUnitSystem(unansweredImperialDefault)).toBe("imperial");
  });

  it("uses the answered system in preference to the default", () => {
    expect(initialUnitSystem(answeredImperial)).toBe("imperial");
  });
});

// ---------------------------------------------------------------------------
// initialiseEditableAnswers
// ---------------------------------------------------------------------------

describe("initialiseEditableAnswers", () => {
  it("seeds an unanswered imperial-default quantity with blank st/lb", () => {
    const init = initialiseEditableAnswers(unansweredImperialDefault);
    expect(init.weight).toEqual({ system: "imperial", components: { st: "", lb: "" } });
  });

  it("seeds an unanswered metric-default quantity with blank kg", () => {
    const init = initialiseEditableAnswers(unansweredMetricDefault);
    expect(init.weight).toEqual({ system: "metric", components: { kg: "" } });
  });

  it("copies an answered quantity value", () => {
    const init = initialiseEditableAnswers(answeredImperial);
    expect(init.weight).toEqual({ system: "imperial", components: { st: "11", lb: "11" } });
  });

  it("does not share the components object with the source state", () => {
    const a = initialiseEditableAnswers(answeredImperial);
    (a.weight as QuantityValueView).components.st = "12";
    const b = initialiseEditableAnswers(answeredImperial);
    expect((b.weight as QuantityValueView).components.st).toBe("11");
  });

  it("passes boolean and text answers through unchanged", () => {
    const state = mkState([
      mkQuestion({ answer_key: "flag", answer_type: "boolean", current_value: true }),
      mkQuestion({ answer_key: "notes", answer_type: "text", current_value: "hi" }),
      mkQuestion({
        answer_key: "weight",
        quantity: true,
        default_system: "metric",
        allowed_systems: ["metric", "imperial"],
        current_value: null,
      }),
    ]);
    const init = initialiseEditableAnswers(state);
    expect(init.flag).toBe(true);
    expect(init.notes).toBe("hi");
    expect(init.weight).toEqual({ system: "metric", components: { kg: "" } });
  });
});

// ---------------------------------------------------------------------------
// quantityComponentsToNumbers
// ---------------------------------------------------------------------------

describe("quantityComponentsToNumbers", () => {
  it("converts imperial whole-number components", () => {
    expect(quantityComponentsToNumbers({ st: "11", lb: "11" })).toEqual({ st: 11, lb: 11 });
  });

  it("converts a metric decimal component", () => {
    expect(quantityComponentsToNumbers({ kg: "70.5" })).toEqual({ kg: 70.5 });
  });
});
