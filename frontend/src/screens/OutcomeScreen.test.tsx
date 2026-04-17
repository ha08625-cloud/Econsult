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

  it("renders the page heading and description", () => {
    render(<OutcomeScreen {...defaultProps} />);
    expect(screen.getByText("What do you need today?")).toBeTruthy();
    expect(
      screen.getByText(/select the option that best describes your request/i)
    ).toBeTruthy();
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

  it("renders the urgent care notice across formatted tags", () => {
    render(<OutcomeScreen {...defaultProps} />);
    
    // Checks for the main warning text
    expect(
      screen.getByText(/do not use this form for urgent matters/i)
    ).toBeTruthy();

    // Uses a matcher function to find fragmented text split by <strong> tags
    expect(
      screen.getByText((content, element) => {
        const hasText = (node: Element | null) =>
          node?.textContent === "111" || node?.textContent === "999";
        const children = Array.from(element?.children || []);
        return (
          content.includes("call") && 
          children.some((child) => hasText(child as Element))
        );
      })
    ).toBeTruthy();
  });

  it("passes practiceName through to the page shell", () => {
    render(
      <OutcomeScreen {...defaultProps} practiceName="Summertown Health Centre" />
    );
    expect(screen.getByText("Summertown Health Centre")).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // Initial state
  // ---------------------------------------------------------------------------

  it("no radio is selected on initial render", () => {
    render(<OutcomeScreen {...defaultProps} />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.every((r) => !r.checked)).toBe(true);
  });

  it("Continue button is disabled on initial render", () => {
    render(<OutcomeScreen {...defaultProps} />);
    expect(
      screen.getByRole("button", { name: /continue/i })
    ).toBeDisabled();
  });

  // ---------------------------------------------------------------------------
  // Selection behaviour
  // ---------------------------------------------------------------------------

  it("Continue button is enabled after selecting an option", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
    expect(
      screen.getByRole("button", { name: /continue/i })
    ).toBeEnabled();
  });

  it("only one radio is checked after making a selection", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(
      screen.getByRole("radio", { name: /phone appointment/i })
    );
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.filter((r) => r.checked)).toHaveLength(1);
  });

  it("selecting a second option deselects the first", async () => {
    render(<OutcomeScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
    await userEvent.click(
      screen.getByRole("radio", { name: /phone appointment/i })
    );
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const checked = radios.filter((r) => r.checked);
    expect(checked).toHaveLength(1);
    expect(
      (screen.getByRole("radio", {
        name: /phone appointment/i,
      }) as HTMLInputElement).checked
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: /not sure/i }) as HTMLInputElement)
        .checked
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

  it("calls onBack when Back is clicked", async () => {
    const onBack = vi.fn();
    render(<OutcomeScreen {...defaultProps} onBack={onBack} />);
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledOnce();
  });
});
