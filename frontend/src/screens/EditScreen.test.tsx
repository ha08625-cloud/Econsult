import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import EditScreen from "./EditScreen";
import type { ClientStateView } from "../types";
import type { PhotoTier } from "./EditScreen";

// Mock the api module so tests never make real HTTP calls
vi.mock("../api", () => ({
  updateForm: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

import { updateForm } from "../api";
const mockUpdateForm = vi.mocked(updateForm);

const noop = () => {};

const booleanQuestion = {
  answer_key: "has_pain",
  question_text: "Do you have pain?",
  answer_type: "boolean" as const,
  current_value: null,
  required: true,
  suggested: false,
};

const textQuestion = {
  answer_key: "duration",
  question_text: "How long have you had symptoms?",
  answer_type: "text" as const,
  current_value: null,
  required: true,
  suggested: false,
};

const suggestedQuestion = {
  answer_key: "frequency",
  question_text: "How often do you experience this?",
  answer_type: "text" as const,
  current_value: "Daily",
  required: false,
  suggested: true,
};

const baseClientState: ClientStateView = {
  condition_label: "Urinary symptoms",
  free_text: null,
  additional_text: null,
  questions: [booleanQuestion, textQuestion],
};

const baseAnswers: Record<string, boolean | string | null> = {
  has_pain: null,
  duration: null,
};

// defaultProps now includes the two new required tier props.
// photoTier: null represents the initial state before the patient has
// chosen a tier — this is the correct default for most existing tests
// since they do not exercise the photo upload section.
const defaultProps = {
  practiceName: null,
  clientState: baseClientState,
  editableAnswers: baseAnswers,
  additionalText: "",
  onAnswersChange: noop,
  onAdditionalTextChange: noop,
  onContinue: noop,
  onBack: noop,
  runtimeId: "runtime-123",
  version: 1,
  photos: [],
  onPhotosChange: noop,
  photoTier: null as PhotoTier | null,
  onPhotoTierChange: noop,
};

describe("EditScreen", () => {
  beforeEach(() => {
    mockUpdateForm.mockReset();
  });

  it("renders all questions from clientState", () => {
    render(<EditScreen {...defaultProps} />);
    expect(screen.getByText("Do you have pain?")).toBeTruthy();
    expect(screen.getByText("How long have you had symptoms?")).toBeTruthy();
  });

  it("boolean questions render Yes and No radio buttons within a fieldset", () => {
    render(<EditScreen {...defaultProps} />);

    // Asserts the fieldset and legend structure is accessible
    const group = screen.getByRole("group", { name: /do you have pain/i });
    expect(group).toBeTruthy();

    // Asserts label wrapping works natively
    expect(within(group).getByLabelText("Yes")).toBeTruthy();
    expect(within(group).getByLabelText("No")).toBeTruthy();
  });

  it("text questions render a text input associated with its label", () => {
    render(
      <EditScreen
        {...defaultProps}
        clientState={{ ...baseClientState, questions: [textQuestion] }}
        editableAnswers={{ duration: "" }}
      />
    );

    // This will fail if the htmlFor/id association is broken
    const input = screen.getByLabelText("How long have you had symptoms?");
    expect(input.tagName).toBe("INPUT");
  });

  it("suggested questions render the suggested badge and optional indicator", () => {
    render(
      <EditScreen
        {...defaultProps}
        clientState={{ ...baseClientState, questions: [suggestedQuestion] }}
        editableAnswers={{ frequency: "Daily" }}
      />
    );

    expect(screen.getByText(/pre-filled from your description/i)).toBeTruthy();

    // Use getAllByText because "Additional information" and "Photos"
    // also statically render the "(optional)" indicator on this screen.
    const optionalIndicators = screen.getAllByText("(optional)");
    expect(optionalIndicators.length).toBeGreaterThanOrEqual(3);
  });

  it("Continue button is disabled when a required answer is missing", () => {
    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: null, duration: null }}
      />
    );
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(true);
  });

  it("Continue button is enabled when all required answers are filled", () => {
    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: true, duration: "Three days" }}
      />
    );
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("does not crash when editableAnswers has no keys matching clientState questions", () => {
    // Defensive: prop mismatch should not throw
    expect(() =>
      render(<EditScreen {...defaultProps} editableAnswers={{}} />)
    ).not.toThrow();
  });

  it("calls onContinue with API result on successful submit", async () => {
    const onContinue = vi.fn();
    const mockResult = {
      runtime_id: "runtime-123",
      version: 2,
      client_state: { ...baseClientState, questions: [] },
      safety_messages: [],
    };
    mockUpdateForm.mockResolvedValueOnce(mockResult);

    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: true, duration: "Two days" }}
        onContinue={onContinue}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /review answers/i }));

    expect(onContinue).toHaveBeenCalledWith({
      version: 2,
      clientState: mockResult.client_state,
      safetyMessages: [],
    });
  });

  it("displays an inline error when the API call fails", async () => {
    mockUpdateForm.mockRejectedValueOnce(new Error("Network error"));

    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: true, duration: "Two days" }}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /review answers/i }));

    expect(screen.getByText(/network error/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Tier selection
// ---------------------------------------------------------------------------

describe("EditScreen — tier selection", () => {
  it("renders both tier radio options", () => {
    render(<EditScreen {...defaultProps} />);
    expect(screen.getByLabelText(/high quality/i)).toBeTruthy();
    expect(screen.getByLabelText(/standard quality/i)).toBeTruthy();
  });

  it("file input is not rendered before a tier is selected", () => {
    render(<EditScreen {...defaultProps} photoTier={null} />);
    expect(screen.queryByLabelText(/photo-upload/i)).toBeNull();
    // The native file input has no accessible label, so query by role
    expect(
      document.querySelector('input[type="file"]')
    ).toBeNull();
  });

  it("file input is rendered once a tier is selected", () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    expect(document.querySelector('input[type="file"]')).toBeTruthy();
  });

  it("calls onPhotoTierChange with 'high' when the high-tier option is selected", async () => {
    const onPhotoTierChange = vi.fn();
    render(
      <EditScreen {...defaultProps} onPhotoTierChange={onPhotoTierChange} />
    );
    await userEvent.click(screen.getByLabelText(/high quality/i));
    expect(onPhotoTierChange).toHaveBeenCalledWith("high");
  });

  it("calls onPhotoTierChange with 'standard' when the standard-tier option is selected", async () => {
    const onPhotoTierChange = vi.fn();
    render(
      <EditScreen {...defaultProps} onPhotoTierChange={onPhotoTierChange} />
    );
    await userEvent.click(screen.getByLabelText(/standard quality/i));
    expect(onPhotoTierChange).toHaveBeenCalledWith("standard");
  });

  it("high-tier option is checked when photoTier prop is 'high'", () => {
    render(<EditScreen {...defaultProps} photoTier="high" />);
    expect(
      (screen.getByLabelText(/high quality/i) as HTMLInputElement).checked
    ).toBe(true);
    expect(
      (screen.getByLabelText(/standard quality/i) as HTMLInputElement).checked
    ).toBe(false);
  });

  it("standard-tier option is checked when photoTier prop is 'standard'", () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    expect(
      (screen.getByLabelText(/standard quality/i) as HTMLInputElement).checked
    ).toBe(true);
    expect(
      (screen.getByLabelText(/high quality/i) as HTMLInputElement).checked
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Tier-conditional file input behaviour
// ---------------------------------------------------------------------------

describe("EditScreen — file input per tier", () => {
  it("high-tier file input does not have the multiple attribute", () => {
    render(<EditScreen {...defaultProps} photoTier="high" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    // The multiple attribute must be absent — its presence would allow the OS
    // picker to accept more than one file, undermining the 1-photo constraint.
    expect(input.multiple).toBe(false);
  });

  it("standard-tier file input has the multiple attribute", () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.multiple).toBe(true);
  });

  it("shows an error and does not call onPhotosChange when adding a second photo in high tier", async () => {
    // Simulate one photo already attached
    const existingPhoto = {
      file: new File([new Uint8Array([0xff, 0xd8, 0xff])], "existing.jpg", {
        type: "image/jpeg",
      }),
      previewUrl: "blob:existing",
    };
    const onPhotosChange = vi.fn();

    render(
      <EditScreen
        {...defaultProps}
        photoTier="high"
        photos={[existingPhoto]}
        onPhotosChange={onPhotosChange}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const newFile = new File(
      [new Uint8Array([0xff, 0xd8, 0xff])],
      "second.jpg",
      { type: "image/jpeg" }
    );
    await userEvent.upload(input, newFile);

    // Count error must be shown
    expect(screen.getAllByText(/maximum of 1 photo/i).length).toBeGreaterThanOrEqual(1);
    // Photos must not be updated
    expect(onPhotosChange).not.toHaveBeenCalled();
  });

  it("shows an error and does not call onPhotosChange when adding a 6th photo in standard tier", async () => {
    // Simulate five photos already attached
    const makePhoto = (name: string) => ({
      file: new File([new Uint8Array([0xff, 0xd8, 0xff])], name, {
        type: "image/jpeg",
      }),
      previewUrl: `blob:${name}`,
    });
    const fivePhotos = [
      makePhoto("a.jpg"),
      makePhoto("b.jpg"),
      makePhoto("c.jpg"),
      makePhoto("d.jpg"),
      makePhoto("e.jpg"),
    ];
    const onPhotosChange = vi.fn();

    render(
      <EditScreen
        {...defaultProps}
        photoTier="standard"
        photos={fivePhotos}
        onPhotosChange={onPhotosChange}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const newFile = new File(
      [new Uint8Array([0xff, 0xd8, 0xff])],
      "sixth.jpg",
      { type: "image/jpeg" }
    );
    await userEvent.upload(input, newFile);

    expect(screen.getAllByText(/maximum of 5 photos/i).length).toBeGreaterThanOrEqual(1);
    expect(onPhotosChange).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Photo guide modal
// ---------------------------------------------------------------------------

describe("EditScreen — photo guide modal", () => {
  // The guide link only renders once a tier is selected.
  // All modal tests use photoTier="standard" as a representative tier.

  it("guide link is not shown when no tier is selected", () => {
    render(<EditScreen {...defaultProps} photoTier={null} />);
    expect(screen.queryByRole("button", { name: /how to take a good photo/i })).toBeNull();
  });

  it("guide link is shown once a tier is selected", () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    expect(
      screen.getByRole("button", { name: /how to take a good photo/i })
    ).toBeTruthy();
  });

  it("modal is not visible on initial render", () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("modal opens when the guide link is clicked", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("modal contains the expected guidance text", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );
    expect(screen.getByText(/well-lit area/i)).toBeTruthy();
    expect(screen.getByText(/15cm/i)).toBeTruthy();
    expect(screen.getByText(/countdown timer/i)).toBeTruthy();
  });

  it("modal closes when the Got it button is clicked", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );
    expect(screen.getByRole("dialog")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /got it/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("modal closes when the close button is clicked", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );
    expect(screen.getByRole("dialog")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /close guidance/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("modal closes when the Escape key is pressed", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );
    expect(screen.getByRole("dialog")).toBeTruthy();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("modal closes when the backdrop overlay is clicked", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();

    // Click the overlay element itself, not the inner panel.
    // The dialog role is on the overlay div, so clicking it directly
    // triggers the backdrop close handler.
    await userEvent.click(dialog);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("focus moves to the close button when the modal opens", async () => {
    render(<EditScreen {...defaultProps} photoTier="standard" />);
    await userEvent.click(
      screen.getByRole("button", { name: /how to take a good photo/i })
    );

    await vi.waitFor(() => {
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: /close guidance/i })
      );
    });
  });
});


// ---------------------------------------------------------------------------
// Number questions
// ---------------------------------------------------------------------------

const numberQuestion = {
  answer_key: "patient_weight_kg",
  question_text: "What is your weight in kg?",
  answer_type: "number" as const,
  current_value: null,
  required: true,
  suggested: false,
  decimal_places: 1,
  min: 2,
  max: 400,
  range_warning_text:
    "That weight is outside the usual range. Please check you entered it correctly.",
};

const numberClientState: ClientStateView = {
  ...baseClientState,
  questions: [numberQuestion],
};

function renderNumber(value: string | null) {
  return render(
    <EditScreen
      {...defaultProps}
      clientState={numberClientState}
      editableAnswers={{ patient_weight_kg: value }}
    />
  );
}

describe("EditScreen — number questions", () => {
  it("renders a number input associated with its label", () => {
    renderNumber("");
    const input = screen.getByLabelText(/what is your weight in kg/i) as HTMLInputElement;
    expect(input.tagName).toBe("INPUT");
    expect(input.type).toBe("number");
  });

  it("shows an inline precision error and disables Continue when too many decimals are entered", () => {
    renderNumber("70.55");
    expect(screen.getByText(/at most 1 decimal place/i)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(true);
  });

  it("treats a typed trailing zero as too precise (string is held verbatim)", () => {
    renderNumber("70.50");
    expect(screen.getByText(/at most 1 decimal place/i)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(true);
  });

  it("accepts a value at the allowed precision and enables Continue", () => {
    renderNumber("70.5");
    expect(screen.queryByText(/at most 1 decimal place/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("accepts a whole number and enables Continue", () => {
    renderNumber("70");
    expect(screen.queryByText(/at most 1 decimal place/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("shows the range notice for an out-of-range value but does NOT block Continue", () => {
    renderNumber("500"); // within precision (whole number), above max of 400
    expect(screen.getByText(/outside the usual range/i)).toBeTruthy();
    // Range is advisory only: Continue stays enabled.
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("does not show the range notice for an in-range value", () => {
    renderNumber("70.5");
    expect(screen.queryByText(/outside the usual range/i)).toBeNull();
  });
});
