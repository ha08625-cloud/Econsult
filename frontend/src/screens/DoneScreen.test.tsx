import { render, screen } from "@testing-library/react";
import DoneScreen from "./DoneScreen";

describe("DoneScreen", () => {
  it("renders the checkmark SVG icon", () => {
    render(<DoneScreen practiceWasClosed={false} />);
    expect(document.querySelector(".done-icon svg")).not.toBeNull();
  });

  it("renders the after-hours message when practiceWasClosed is true", () => {
    render(<DoneScreen practiceWasClosed={true} />);
    expect(
      screen.getByText(/your submission will be reviewed on the next working day/i)
    ).toBeTruthy();
    expect(
      screen.queryByText(/if you do not hear back/i)
    ).toBeNull();
  });

  it("renders the standard follow-up message when practiceWasClosed is false", () => {
    render(<DoneScreen practiceWasClosed={false} />);
    expect(
      screen.getByText(/if you do not hear back from the practice/i)
    ).toBeTruthy();
    expect(
      screen.queryByText(/your submission will be reviewed on the next working day/i)
    ).toBeNull();
  });
});