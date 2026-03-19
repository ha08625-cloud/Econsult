import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SelectConditionScreen from "./SelectConditionScreen";
import type { ConditionSummary } from "../types";

const noop = () => {};

const sampleConditions: ConditionSummary[] = [
  { id: "uti1", label: "Urinary symptoms", search_tags: ["uti", "urine"] },
  { id: "back1", label: "Back pain", search_tags: ["back", "spine"] },
];

const defaultProps = {
  conditions: sampleConditions,
  selectedConditionId: null,
  onConditionChange: noop,
  onContinue: noop,
  onBlankForm: noop,
};

describe("SelectConditionScreen", () => {
  it("renders loading state when conditions is null", () => {
    render(<SelectConditionScreen {...defaultProps} conditions={null} />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("renders the condition label when conditions are loaded", () => {
    render(<SelectConditionScreen {...defaultProps} />);
    expect(screen.getByText(/what is your consultation about/i)).toBeTruthy();
  });

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
});