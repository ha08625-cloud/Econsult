import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SelectConditionScreen from "./SelectConditionScreen";
import type { ConditionSummary } from "../types";

const noop = () => {};

const sampleConditions: ConditionSummary[] = [
  { id: "uti1", label: "Urinary symptoms", search_tags: ["uti", "urine"] },
  { id: "back1", label: "Back pain", search_tags: ["back", "spine"] },
];

const defaultProps = {
  practiceName: null,
  conditions: sampleConditions,
  selectedConditionId: null,
  onConditionChange: noop,
  onContinue: noop,
  onBlankForm: noop,
  onBack: noop,
};

describe("SelectConditionScreen", () => {
  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  it("renders loading state when conditions is null", () => {
    render(<SelectConditionScreen {...defaultProps} conditions={null} />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("loading container has role=status so screen readers announce it", () => {
    render(<SelectConditionScreen {...defaultProps} conditions={null} />);
    expect(screen.getByRole("status")).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // Focus management (issue 9)
  // ---------------------------------------------------------------------------

  it("focuses the heading when conditions load", async () => {
    const { rerender } = render(
      <SelectConditionScreen {...defaultProps} conditions={null} />
    );
    rerender(<SelectConditionScreen {...defaultProps} conditions={sampleConditions} />);
    await waitFor(() => {
      expect(document.activeElement?.tagName).toBe("H1");
    });
  });

  // ---------------------------------------------------------------------------
  // Loaded state — rendering
  // ---------------------------------------------------------------------------

  it("renders the condition label when conditions are loaded", () => {
    render(<SelectConditionScreen {...defaultProps} />);
    expect(screen.getByText(/what is your consultation about/i)).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // Button states
  // ---------------------------------------------------------------------------

  it("Continue button is disabled when no condition is selected", () => {
    render(<SelectConditionScreen {...defaultProps} selectedConditionId={null} />);
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("Continue button is enabled when a condition is selected", () => {
    render(<SelectConditionScreen {...defaultProps} selectedConditionId="uti1" />);
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("Use blank form button calls onBlankForm", async () => {
    const onBlankForm = vi.fn();
    render(<SelectConditionScreen {...defaultProps} onBlankForm={onBlankForm} />);
    await userEvent.click(screen.getByRole("button", { name: /use blank form/i }));
    expect(onBlankForm).toHaveBeenCalledTimes(1);
  });

  it("Continue button calls onContinue", async () => {
    const onContinue = vi.fn();
    render(
      <SelectConditionScreen
        {...defaultProps}
        selectedConditionId="uti1"
        onContinue={onContinue}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  // ---------------------------------------------------------------------------
  // Accessibility (issue 3)
  // ---------------------------------------------------------------------------

  it("Use blank form button is described by the hint paragraph", () => {
    render(<SelectConditionScreen {...defaultProps} />);
    const btn = screen.getByRole("button", { name: /use blank form/i });
    const hintId = btn.getAttribute("aria-describedby");
    expect(hintId).toBeTruthy();
    const hintEl = document.getElementById(hintId!);
    expect(hintEl?.textContent).toMatch(/cannot find a condition/i);
  });
});