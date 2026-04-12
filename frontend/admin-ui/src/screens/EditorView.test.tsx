import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, type Mock } from "vitest";
import EditorView from "./EditorView";
import type { ConditionSummary } from "../types";

// ---------------------------------------------------------------------------
// Mock all child components.
//
// Each child makes its own API calls on mount. We replace them with stubs
// so EditorView tests are isolated to EditorView's own logic.
//
// SignpostingEditor and AvailabilityEditor accept onUnsavedChange. The stubs
// expose a test helper (triggerUnsaved) so individual tests can simulate a
// child reporting unsaved changes without touching real Quill or fetch calls.
// ---------------------------------------------------------------------------

let triggerSignpostingUnsaved: (hasChanges: boolean) => void = () => {};
let triggerAvailabilityUnsaved: (hasChanges: boolean) => void = () => {};

vi.mock("./SignpostingEditor", () => ({
  default: ({ onUnsavedChange }: { onUnsavedChange: (v: boolean) => void }) => {
    triggerSignpostingUnsaved = onUnsavedChange;
    return <div data-testid="signposting-editor" />;
  },
}));

vi.mock("./AvailabilityEditor", () => ({
  default: ({ onUnsavedChange }: { onUnsavedChange: (v: boolean) => void }) => {
    triggerAvailabilityUnsaved = onUnsavedChange;
    return <div data-testid="availability-editor" />;
  },
}));

vi.mock("./PracticeSettingsTab", () => ({
  default: () => <div data-testid="practice-settings-tab" />,
}));

vi.mock("./AuditLogTab", () => ({
  default: () => <div data-testid="audit-log-tab" />,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const noop = () => {};

const twoConditions: ConditionSummary[] = [
  { id: "urinary_symptoms", label: "Urinary symptoms" },
  { id: "back_pain", label: "Back pain" },
];

const defaultProps = {
  conditions: twoConditions,
  onAuthError: noop,
};

// ---------------------------------------------------------------------------
// Tab rendering
// ---------------------------------------------------------------------------

describe("EditorView — tab bar", () => {
  it("renders all four tab buttons", () => {
    render(<EditorView {...defaultProps} />);
    expect(screen.getByRole("button", { name: "Signposting" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Availability" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Practice settings" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Audit log" })).toBeTruthy();
  });

  it("signposting tab is active by default", () => {
    render(<EditorView {...defaultProps} />);
    expect(
      screen.getByRole("button", { name: "Signposting" }).className
    ).toContain("active");
  });

  it("availability tab is not active by default", () => {
    render(<EditorView {...defaultProps} />);
    expect(
      screen.getByRole("button", { name: "Availability" }).className
    ).not.toContain("active");
  });

  it("clicking Availability tab marks it active", async () => {
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    expect(
      screen.getByRole("button", { name: "Availability" }).className
    ).toContain("active");
  });

  it("clicking Practice settings tab marks it active", async () => {
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Practice settings" }));
    expect(
      screen.getByRole("button", { name: "Practice settings" }).className
    ).toContain("active");
  });

  it("clicking Audit log tab marks it active", async () => {
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Audit log" }));
    expect(
      screen.getByRole("button", { name: "Audit log" }).className
    ).toContain("active");
  });
});

// ---------------------------------------------------------------------------
// Tab content rendering
// ---------------------------------------------------------------------------

describe("EditorView — tab content", () => {
  it("renders the condition selector on the signposting tab by default", () => {
    render(<EditorView {...defaultProps} />);
    expect(document.getElementById("condition-select")).not.toBeNull();
  });

  it("renders PracticeSettingsTab when Practice settings tab is clicked", async () => {
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Practice settings" }));
    expect(screen.getByTestId("practice-settings-tab")).toBeTruthy();
  });

  it("renders AuditLogTab when Audit log tab is clicked", async () => {
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Audit log" }));
    expect(screen.getByTestId("audit-log-tab")).toBeTruthy();
  });

  it("AvailabilityEditor is always mounted regardless of active tab", () => {
    render(<EditorView {...defaultProps} />);
    // On the default signposting tab, AvailabilityEditor is still in the DOM.
    expect(screen.getByTestId("availability-editor")).toBeTruthy();
  });

  it("AvailabilityEditor is hidden when signposting tab is active", () => {
    render(<EditorView {...defaultProps} />);
    const wrapper = screen.getByTestId("availability-editor").parentElement!;
    expect(wrapper.style.display).toBe("none");
  });

  it("AvailabilityEditor is visible when availability tab is active", async () => {
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    const wrapper = screen.getByTestId("availability-editor").parentElement!;
    expect(wrapper.style.display).toBe("block");
  });
});

// ---------------------------------------------------------------------------
// Condition selector
// ---------------------------------------------------------------------------

describe("EditorView — condition selector", () => {
  it("renders all passed conditions as options", () => {
    render(<EditorView {...defaultProps} />);
    const select = document.getElementById("condition-select") as HTMLSelectElement;
    expect(select.options.length).toBe(2);
    expect(select.options[0].value).toBe("urinary_symptoms");
    expect(select.options[1].value).toBe("back_pain");
  });

  it("selects the first condition by default", () => {
    render(<EditorView {...defaultProps} />);
    const select = document.getElementById("condition-select") as HTMLSelectElement;
    expect(select.value).toBe("urinary_symptoms");
  });

  it("shows empty state when no conditions are passed", () => {
    render(<EditorView conditions={[]} onAuthError={noop} />);
    expect(screen.getByText("Select a condition to begin.")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Unsaved change guard — switching tab away from signposting
// ---------------------------------------------------------------------------

describe("EditorView — unsaved guard when leaving signposting tab", () => {
  beforeEach(() => {
    triggerSignpostingUnsaved = () => {};
    triggerAvailabilityUnsaved = () => {};
  });

  it("does not show confirm dialog when leaving signposting tab with no unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("shows confirm dialog when leaving signposting tab with unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    expect(confirmSpy).toHaveBeenCalledOnce();
    confirmSpy.mockRestore();
  });

  it("stays on signposting tab when confirm is cancelled", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    expect(
      screen.getByRole("button", { name: "Signposting" }).className
    ).toContain("active");
    confirmSpy.mockRestore();
  });

  it("switches tab when confirm is accepted", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    expect(
      screen.getByRole("button", { name: "Availability" }).className
    ).toContain("active");
    confirmSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Unsaved change guard — switching tab away from availability
// ---------------------------------------------------------------------------

describe("EditorView — unsaved guard when leaving availability tab", () => {
  beforeEach(() => {
    triggerSignpostingUnsaved = () => {};
    triggerAvailabilityUnsaved = () => {};
  });

  it("does not show confirm dialog when leaving availability tab with no unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    await userEvent.click(screen.getByRole("button", { name: "Practice settings" }));
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("shows confirm dialog when leaving availability tab with unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    act(() => triggerAvailabilityUnsaved(true));
    await userEvent.click(screen.getByRole("button", { name: "Practice settings" }));
    expect(confirmSpy).toHaveBeenCalledOnce();
    confirmSpy.mockRestore();
  });

  it("stays on availability tab when confirm is cancelled", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    act(() => triggerAvailabilityUnsaved(true));
    await userEvent.click(screen.getByRole("button", { name: "Practice settings" }));
    expect(
      screen.getByRole("button", { name: "Availability" }).className
    ).toContain("active");
    confirmSpy.mockRestore();
  });

  it("switches tab when confirm is accepted", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorView {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: "Availability" }));
    act(() => triggerAvailabilityUnsaved(true));
    await userEvent.click(screen.getByRole("button", { name: "Practice settings" }));
    expect(
      screen.getByRole("button", { name: "Practice settings" }).className
    ).toContain("active");
    confirmSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Unsaved change guard — switching condition on signposting tab
// ---------------------------------------------------------------------------

describe("EditorView — unsaved guard when switching condition", () => {
  beforeEach(() => {
    triggerSignpostingUnsaved = () => {};
  });

  it("does not show confirm dialog when switching condition with no unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    render(<EditorView {...defaultProps} />);
    const select = document.getElementById("condition-select") as HTMLSelectElement;
    await userEvent.selectOptions(select, "back_pain");
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("shows confirm dialog when switching condition with unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    const select = document.getElementById("condition-select") as HTMLSelectElement;
    await userEvent.selectOptions(select, "back_pain");
    expect(confirmSpy).toHaveBeenCalledOnce();
    confirmSpy.mockRestore();
  });

  it("keeps the current condition selected when confirm is cancelled", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    const select = document.getElementById("condition-select") as HTMLSelectElement;
    await userEvent.selectOptions(select, "back_pain");
    expect(select.value).toBe("urinary_symptoms");
    confirmSpy.mockRestore();
  });

  it("switches to the new condition when confirm is accepted", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    const select = document.getElementById("condition-select") as HTMLSelectElement;
    await userEvent.selectOptions(select, "back_pain");
    expect(select.value).toBe("back_pain");
    confirmSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Clicking the already-active tab
// ---------------------------------------------------------------------------

describe("EditorView — clicking the active tab", () => {
  it("does not show a confirm dialog when clicking the already-active tab", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    render(<EditorView {...defaultProps} />);
    act(() => triggerSignpostingUnsaved(true));
    // Click the tab that is already active — should be a no-op.
    await userEvent.click(screen.getByRole("button", { name: "Signposting" }));
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});