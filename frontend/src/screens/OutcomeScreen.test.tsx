import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import OutcomeScreen from "./OutcomeScreen";

const noop = () => {};

const defaultProps = {
  practiceName: null,
  onContinue: noop,
  onBack: noop,
};

describe("OutcomeScreen", () => {
  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  it("renders the page heading", () => {
    render(<OutcomeScreen {...defaultProps} />);
    expect(screen.getByText("What do you need today?")).toBeTruthy();
  });

  it("renders all six outcome options", () => {
    render(<OutcomeScreen {...defaultProps} />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(6);
  });

  it("renders each outcome label", () => {
    render(<OutcomeScreen {...defaultProps} />);
    expect(screen.getByText(/administrative task only/i)).toBeTruthy();
    expect(screen.getByText(/face to face appointment/i)).toBeTruthy();
    expect(screen.getByText(/phone appointment/i)).toBeTruthy();
    expect(screen.getByText(/medical advice by text or email/i)).toBeTruthy();
    expect(screen.getByText(/medication request/i)).toBeTruthy();
    expect(screen.getByText(/not sure/i)).toBeTruthy();
  });

  it("passes practiceName through to the page shell", () => {
    render(<OutcomeScreen {...defaultProps} practiceName="Summertown Health Centre" />);
    expect(screen.getByText("Summertown Health Centre")).toBeTruthy();
  });

  it("renders without error when practiceName is null", () => {
    expect(() =>
      render(<OutcomeScreen {...defaultProps} practiceName={null} />)
    ).not.toThrow();
  });

  // ---------------------------------------------------------------------------
  // Initial state
  // ---------------------------------------------------------------------------

  it("no radio is selected on initial render", () => {
    render(<OutcomeScreen {...defaultProps} />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.every((r) => !r.checked)).toBe(true);
  });

  it("Continue button remains enabled on initial render (clicking shows the hint instead)", () => {
    render(<OutcomeScreen {...defaultProps} />);
    expect(
      screen.getByRole("button", { name: /continue/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("renders the hint text when no option is selected", () => {
    render(<OutcomeScreen {...defaultProps} />);
    expect(screen.getByText(/select an option to continue/i)).toBeInTheDocument();
  });

  it("hint text is not shown once an option is selected", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
    expect(screen.queryByText(/select an option to continue/i)).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Accessibility
  // ---------------------------------------------------------------------------

  it("radio group is wrapped in a fieldset with the correct legend", () => {
    render(<OutcomeScreen {...defaultProps} />);
    // getByRole('group') finds the fieldset; its accessible name comes from the legend
    expect(screen.getByRole("radiogroup", { name: /request type/i })).toBeInTheDocument();
  });

  it("each radio has aria-required set to true", () => {
    render(<OutcomeScreen {...defaultProps} />);
    const radios = screen.getAllByRole("radio");
    radios.forEach((radio) => {
      expect(radio).toHaveAttribute("aria-required", "true");
    });
  });

  // ---------------------------------------------------------------------------
  // Selection behaviour
  // ---------------------------------------------------------------------------

  it("Continue button is enabled after selecting an option", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
    expect(
      screen.getByRole("button", { name: /continue/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("only one radio is checked after making a selection", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("radio", { name: /phone appointment/i }));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.filter((r) => r.checked)).toHaveLength(1);
  });

  it("selecting a second option deselects the first", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
    await userEvent.click(screen.getByRole("radio", { name: /phone appointment/i }));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const checked = radios.filter((r) => r.checked);
    expect(checked).toHaveLength(1);
    expect(
      (screen.getByRole("radio", { name: /phone appointment/i }) as HTMLInputElement).checked
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: /not sure/i }) as HTMLInputElement).checked
    ).toBe(false);
  });

  // ---------------------------------------------------------------------------
  // Callbacks
  // ---------------------------------------------------------------------------

  it("calls onContinue with the correct value when Continue is clicked", async () => {
    const onContinue = vi.fn();
    render(<OutcomeScreen {...defaultProps} onContinue={onContinue} />);
    await userEvent.click(
      screen.getByRole("radio", { name: /face to face appointment/i })
    );
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledOnce();
    expect(onContinue).toHaveBeenCalledWith("face_to_face");
  });

  it("calls onContinue with admin_task when that option is selected", async () => {
    const onContinue = vi.fn();
    render(<OutcomeScreen {...defaultProps} onContinue={onContinue} />);
    await userEvent.click(
      screen.getByRole("radio", { name: /administrative task only/i })
    );
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledWith("admin_task");
  });

  it("does not call onContinue when Continue is clicked with nothing selected, and moves focus to the hint", async () => {
    const onContinue = vi.fn();
    render(<OutcomeScreen {...defaultProps} onContinue={onContinue} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).not.toHaveBeenCalled();
    expect(screen.getByText(/select an option to continue/i)).toBe(
      document.activeElement
    );
  });

  it("calls onBack when Back is clicked", async () => {
    const onBack = vi.fn();
    render(<OutcomeScreen {...defaultProps} onBack={onBack} />);
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("does not call onBack when Continue is clicked", async () => {
    const onBack = vi.fn();
    render(<OutcomeScreen {...defaultProps} onBack={onBack} />);
    await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onBack).not.toHaveBeenCalled();
  });
});