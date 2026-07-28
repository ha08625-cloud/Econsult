// File path: frontend/src/ConditionCombobox_test.tsx
//
// New test file — ConditionCombobox.tsx previously had no dedicated tests.
// Mirrors the conventions used in SelectConditionScreen_test.tsx (vitest
// globals, @testing-library/react, no userEvent.setup()).

import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConditionCombobox from "./ConditionCombobox";
import type { ConditionSummary } from "./types";

const noop = () => {};

const sampleConditions: ConditionSummary[] = [
  { id: "uti1", label: "Urinary symptoms", search_tags: ["uti", "urine", "waterworks"] },
  { id: "back1", label: "Back pain", search_tags: ["back", "spine"] },
  { id: "skin1", label: "Skin rash", search_tags: ["rash", "skin", "itchy"] },
];

function getInput() {
  return screen.getByRole("combobox") as HTMLInputElement;
}

function renderCombobox(props: {
  selectedId: string | null;
  onChange: (id: string | null) => void;
}) {
  return render(
    <>
      <label id="condition-label">What is your consultation about?</label>
      <ConditionCombobox
        conditions={sampleConditions}
        selectedId={props.selectedId}
        onChange={props.onChange}
        labelId="condition-label"
      />
    </>
  );
}

describe("ConditionCombobox", () => {
  // ---------------------------------------------------------------------------
  // Opening the list
  // ---------------------------------------------------------------------------

  it("opens the listbox and shows all conditions on focus", async () => {
    renderCombobox({ selectedId: null, onChange: noop });
    await userEvent.click(getInput());
    expect(screen.getByRole("listbox")).toBeTruthy();
    for (const c of sampleConditions) {
      expect(screen.getByRole("option", { name: c.label })).toBeTruthy();
    }
  });

  it("pressing Escape closes the listbox without selecting anything", async () => {
    const onChange = vi.fn();
    renderCombobox({ selectedId: null, onChange: onChange });
    const input = getInput();
    await userEvent.click(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------------
  // Filtering
  // ---------------------------------------------------------------------------

  it("filters the list as the user types", async () => {
    renderCombobox({ selectedId: null, onChange: noop });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.type(input, "back");
    expect(screen.getByRole("option", { name: "Back pain" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "Urinary symptoms" })).toBeNull();
  });

  it("shows a count footer when the list is filtered down", async () => {
    renderCombobox({ selectedId: null, onChange: noop });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.type(input, "back");
    expect(screen.getAllByText(/showing 1 of 3 conditions/i).length).toBeGreaterThan(0);
  });

  it("falls back to the full list and shows a no-match notice for an unmatched query", async () => {
    renderCombobox({ selectedId: null, onChange: noop });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.type(input, "zzzzzzzzzz");
    expect(screen.getAllByText(/no matching conditions/i).length).toBeGreaterThan(0);
    for (const c of sampleConditions) {
      expect(screen.getByRole("option", { name: c.label })).toBeTruthy();
    }
  });

  it("only exposes option children to the listbox role, with info rows announced via a live region instead", async () => {
    renderCombobox({ selectedId: null, onChange: noop });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.type(input, "back");

    const listbox = screen.getByRole("listbox");
    for (const child of Array.from(listbox.children)) {
      expect(["option", "presentation"]).toContain(child.getAttribute("role"));
    }

    expect(screen.getAllByRole("option").length).toBe(1);
  });

  it("announces the result count in an aria-live status region", async () => {
    renderCombobox({ selectedId: null, onChange: noop });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.type(input, "back");

    const status = document.querySelector('[aria-live="polite"]');
    expect(status).not.toBeNull();
    expect(status!.textContent).toMatch(/showing 1 of 3 conditions/i);
  });

  // ---------------------------------------------------------------------------
  // Selecting
  // ---------------------------------------------------------------------------

  it("clicking a suggestion fills the input and calls onChange with the condition id", async () => {
    const onChange = vi.fn();
    renderCombobox({ selectedId: null, onChange: onChange });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.click(screen.getByRole("option", { name: "Back pain" }));
    expect(onChange).toHaveBeenCalledWith("back1");
    expect(input.value).toBe("Back pain");
  });

  it("ArrowDown then Enter selects the active option", async () => {
    const onChange = vi.fn();
    renderCombobox({ selectedId: null, onChange: onChange });
    const input = getInput();
    await userEvent.click(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("uti1");
    expect(input.value).toBe("Urinary symptoms");
  });

  it("typing after a selection clears it by calling onChange with null", async () => {
    const onChange = vi.fn();
    renderCombobox({ selectedId: "uti1", onChange: onChange });
    const input = getInput();
    await userEvent.click(input);
    await userEvent.type(input, "x");
    expect(onChange).toHaveBeenCalledWith(null);
  });

  // ---------------------------------------------------------------------------
  // selectedId reflected in the list
  // ---------------------------------------------------------------------------

  it("marks the option matching selectedId as aria-selected", async () => {
    renderCombobox({ selectedId: "back1", onChange: noop });
    await userEvent.click(getInput());
    expect(screen.getByRole("option", { name: "Back pain" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByRole("option", { name: "Urinary symptoms" })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  // ---------------------------------------------------------------------------
  // selectedId reflected on mount
  // ---------------------------------------------------------------------------

  it("shows the selected condition's label when mounted with a selectedId", () => {
    renderCombobox({ selectedId: "back1", onChange: noop });
    expect(getInput().value).toBe("Back pain");
  });
});
