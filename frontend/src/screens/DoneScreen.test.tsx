import { render, screen } from "@testing-library/react";
import DoneScreen from "./DoneScreen";

describe("DoneScreen", () => {
  it("renders the checkmark SVG icon and hides it from screen readers", () => {
    render(<DoneScreen practiceName={null} practiceWasClosed={false} />);
    
    const iconContainer = document.querySelector(".done-icon");
    const svg = iconContainer?.querySelector("svg");
    
    expect(iconContainer).not.toBeNull();
    expect(iconContainer?.getAttribute("aria-hidden")).toBe("true");
    
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("renders the after-hours message when practiceWasClosed is true", () => {
    render(<DoneScreen practiceName={null} practiceWasClosed={true} />);
    expect(
      screen.getByText(/your submission will be reviewed on the next working day/i)
    ).toBeTruthy();
    expect(
      screen.queryByText(/if you do not hear back/i)
    ).toBeNull();
  });

  it("renders the standard follow-up message when practiceWasClosed is false", () => {
    render(<DoneScreen practiceName={null} practiceWasClosed={false} />);
    expect(
      screen.getByText(/if you do not hear back from the practice/i)
    ).toBeTruthy();
    expect(
      screen.queryByText(/your submission will be reviewed on the next working day/i)
    ).toBeNull();
  });
});