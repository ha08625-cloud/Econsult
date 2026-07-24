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
  QUANTITY_KINDS,
  QUANTITY_DISPLAY_FORMATTERS,
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
    quantity_kind: "weight",
    default_system: "imperial",
    allowed_systems: ["metric", "imperial"],
    current_value: null,
  }),
]);

const unansweredMetricDefault = mkState([
  mkQuestion({
    answer_key: "weight",
    quantity: true,
    quantity_kind: "weight",
    default_system: "metric",
    allowed_systems: ["metric", "imperial"],
    current_value: null,
  }),
]);

const answeredImperial = mkState([
  mkQuestion({
    answer_key: "weight",
    quantity: true,
    quantity_kind: "weight",
    default_system: "metric",
    allowed_systems: ["metric", "imperial"],
    current_value: { system: "imperial", components: { st: "11", lb: "11" } },
  }),
]);

// ---------------------------------------------------------------------------
// emptyComponents / QUANTITY_KINDS
// ---------------------------------------------------------------------------

describe("emptyComponents", () => {
  it("returns a blank kg for weight/metric", () => {
    expect(emptyComponents("weight", "metric")).toEqual({ kg: "" });
  });

  it("returns blank st and lb for weight/imperial", () => {
    expect(emptyComponents("weight", "imperial")).toEqual({ st: "", lb: "" });
  });
});

describe("QUANTITY_KINDS", () => {
  it("maps weight's canonical system and each system to its component keys", () => {
    expect(QUANTITY_KINDS.weight.canonicalSystem).toBe("metric");
    expect(QUANTITY_KINDS.weight.systems.metric).toEqual(["kg"]);
    expect(QUANTITY_KINDS.weight.systems.imperial).toEqual(["st", "lb"]);
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

  it("skips a single-system quantity question and falls through to metric", () => {
    const state = mkState([
      mkQuestion({
        answer_key: "weight",
        quantity: true,
        quantity_kind: "weight",
        default_system: "imperial",
        allowed_systems: ["imperial"],
        current_value: null,
      }),
    ]);
    expect(initialUnitSystem(state)).toBe("metric");
  });

  it("skips a single-system quantity question in favour of a later multi-system one", () => {
    const state = mkState([
      mkQuestion({
        answer_key: "single",
        quantity: true,
        quantity_kind: "weight",
        default_system: "imperial",
        allowed_systems: ["imperial"],
        current_value: null,
      }),
      mkQuestion({
        answer_key: "weight",
        quantity: true,
        quantity_kind: "weight",
        default_system: "metric",
        allowed_systems: ["metric", "imperial"],
        current_value: null,
      }),
    ]);
    expect(initialUnitSystem(state)).toBe("metric");
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
        quantity_kind: "weight",
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

// ---------------------------------------------------------------------------
// QUANTITY_DISPLAY_FORMATTERS
// ---------------------------------------------------------------------------

describe("QUANTITY_DISPLAY_FORMATTERS.weight", () => {
  it("formats an imperial value as stones and pounds", () => {
    const formatted = QUANTITY_DISPLAY_FORMATTERS.weight({
      system: "imperial",
      components: { st: "11", lb: "11" },
    });
    expect(formatted).toBe("11 st 11 lb");
  });

  it("formats a metric value as kilograms", () => {
    const formatted = QUANTITY_DISPLAY_FORMATTERS.weight({
      system: "metric",
      components: { kg: "70.5" },
    });
    expect(formatted).toBe("70.5 kg");
  });
});