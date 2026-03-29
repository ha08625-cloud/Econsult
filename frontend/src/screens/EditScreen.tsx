import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import EditScreen from "./EditScreen";
import type { ClientStateView } from "../types";
import type { PhotoAttachment } from "../uiTypes";
import {
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_COUNT,
  MAX_TOTAL_SIZE_BYTES,
} from "../upload_constants";

// Mock the api module so tests never make real HTTP calls
vi.mock("../api", () => ({
  updateForm: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

import { updateForm } from "../api";
const mockUpdateForm = vi.mocked(updateForm);

// Mock URL methods — jsdom does not implement them
const mockCreateObjectURL = vi.fn((file: File) => `blob:mock/${file.name}`);
const mockRevokeObjectURL = vi.fn();
vi.stubGlobal("URL", {
  createObjectURL: mockCreateObjectURL,
  revokeObjectURL: mockRevokeObjectURL,
});

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
  photos: [] as PhotoAttachment[],
  onPhotosChange: noop,
};

/** Create a minimal File with controllable size and type */
function makeFile(
  name: string,
  type: string,
  sizeBytes: number
): File {
  const content = new Uint8Array(sizeBytes);
  return new File([content], name, { type });
}

// userEvent.upload does not reliably fire onChange on hidden inputs in jsdom.
// This helper sets the files property directly and fires a synthetic change event.
function uploadFiles(input: HTMLInputElement, files: File[]) {
  Object.defineProperty(input, "files", {
    value: files,
    configurable: true,
  });
  fireEvent.change(input);
}

describe("EditScreen", () => {
  beforeEach(() => {
    mockUpdateForm.mockReset();
    mockCreateObjectURL.mockClear();
    mockRevokeObjectURL.mockClear();
  });

  // --- Existing tests ---

  it("renders all questions from clientState", () => {
    render(<EditScreen {...defaultProps} />);
    expect(screen.getByText("Do you have pain?")).toBeTruthy();
    expect(screen.getByText("How long have you had symptoms?")).toBeTruthy();
  });

  it("boolean questions render Yes and No radio buttons", () => {
    render(<EditScreen {...defaultProps} />);
    const radios = screen.getAllByRole("radio");
    const labels = radios.map((r) => r.parentElement?.textContent?.trim());
    expect(labels).toContain("Yes");
    expect(labels).toContain("No");
  });

  it("text questions render a text input", () => {
    render(
      <EditScreen
        {...defaultProps}
        clientState={{ ...baseClientState, questions: [textQuestion] }}
        editableAnswers={{ duration: "" }}
      />
    );
    // The additional-text textarea is always present, so there are two textboxes:
    // one for the question input and one for additional information.
    expect(screen.getAllByRole("textbox")).toHaveLength(2);
    expect(screen.getByText("How long have you had symptoms?")).toBeTruthy();
  });

  it("suggested questions render the suggested badge", () => {
    render(
      <EditScreen
        {...defaultProps}
        clientState={{ ...baseClientState, questions: [suggestedQuestion] }}
        editableAnswers={{ frequency: "Daily" }}
      />
    );
    expect(screen.getByText(/pre-filled from your description/i)).toBeTruthy();
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

  // --- Photo upload tests ---

  it("renders the photo section with an Add photos button", () => {
    render(<EditScreen {...defaultProps} />);
    expect(screen.getByRole("button", { name: /add photos/i })).toBeTruthy();
  });

  it("rejects a file with a disallowed MIME type and does not call onPhotosChange", () => {
    const onPhotosChange = vi.fn();
    render(<EditScreen {...defaultProps} onPhotosChange={onPhotosChange} />);

    const input = screen.getByLabelText("Upload photos") as HTMLInputElement;
    const badFile = makeFile("scan.pdf", "application/pdf", 1000);
    uploadFiles(input, [badFile]);

    expect(onPhotosChange).not.toHaveBeenCalled();
    expect(screen.getByText(/not a supported file type/i)).toBeTruthy();
  });

  it("rejects a file exceeding MAX_FILE_SIZE_BYTES and does not call onPhotosChange", () => {
    const onPhotosChange = vi.fn();
    render(<EditScreen {...defaultProps} onPhotosChange={onPhotosChange} />);

    const input = screen.getByLabelText("Upload photos") as HTMLInputElement;
    const bigFile = makeFile("big.jpg", "image/jpeg", MAX_FILE_SIZE_BYTES + 1);
    uploadFiles(input, [bigFile]);

    expect(onPhotosChange).not.toHaveBeenCalled();
    expect(screen.getByText(/too large/i)).toBeTruthy();
  });

  it("calls onPhotosChange with a single PhotoAttachment for a valid file", () => {
    const onPhotosChange = vi.fn();
    render(<EditScreen {...defaultProps} onPhotosChange={onPhotosChange} />);

    const input = screen.getByLabelText("Upload photos") as HTMLInputElement;
    const validFile = makeFile("photo.jpg", "image/jpeg", 1000);
    uploadFiles(input, [validFile]);

    expect(onPhotosChange).toHaveBeenCalledOnce();
    const result: PhotoAttachment[] = onPhotosChange.mock.calls[0][0];
    expect(result).toHaveLength(1);
    expect(result[0].file).toBe(validFile);
    expect(typeof result[0].previewUrl).toBe("string");
  });

  it("accumulates photos across two separate picker interactions", () => {
    const onPhotosChange = vi.fn();

    const { rerender } = render(
      <EditScreen {...defaultProps} onPhotosChange={onPhotosChange} />
    );

    const input = screen.getByLabelText("Upload photos") as HTMLInputElement;
    const file1 = makeFile("a.jpg", "image/jpeg", 1000);
    uploadFiles(input, [file1]);

    // Simulate App.tsx updating photos prop after first upload
    const firstCall: PhotoAttachment[] = onPhotosChange.mock.calls[0][0];
    rerender(
      <EditScreen
        {...defaultProps}
        photos={firstCall}
        onPhotosChange={onPhotosChange}
      />
    );

    const file2 = makeFile("b.png", "image/png", 1000);
    uploadFiles(input, [file2]);

    const secondCall: PhotoAttachment[] = onPhotosChange.mock.calls[1][0];
    expect(secondCall).toHaveLength(2);
    expect(secondCall[0].file).toBe(file1);
    expect(secondCall[1].file).toBe(file2);
  });

  it("calls onPhotosChange with the photo removed and revokes the object URL", async () => {
    const existingPhoto: PhotoAttachment = {
      file: makeFile("existing.jpg", "image/jpeg", 500),
      previewUrl: "blob:mock/existing.jpg",
    };
    const onPhotosChange = vi.fn();

    render(
      <EditScreen
        {...defaultProps}
        photos={[existingPhoto]}
        onPhotosChange={onPhotosChange}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /remove photo 1/i }));

    expect(mockRevokeObjectURL).toHaveBeenCalledWith("blob:mock/existing.jpg");
    expect(onPhotosChange).toHaveBeenCalledWith([]);
  });

  it("rejects a new file when it would exceed MAX_FILE_COUNT", () => {
    const existingPhotos: PhotoAttachment[] = Array.from(
      { length: MAX_FILE_COUNT },
      (_, i) => ({
        file: makeFile(`existing-${i}.jpg`, "image/jpeg", 100),
        previewUrl: `blob:mock/existing-${i}.jpg`,
      })
    );
    const onPhotosChange = vi.fn();

    render(
      <EditScreen
        {...defaultProps}
        photos={existingPhotos}
        onPhotosChange={onPhotosChange}
      />
    );

    const input = screen.getByLabelText("Upload photos") as HTMLInputElement;
    const extraFile = makeFile("extra.jpg", "image/jpeg", 100);
    uploadFiles(input, [extraFile]);

    expect(onPhotosChange).not.toHaveBeenCalled();
    expect(screen.getByText(/maximum of \d+ photos/i)).toBeTruthy();
  });

  it("rejects a batch that would exceed MAX_TOTAL_SIZE_BYTES", () => {
    // Two existing photos each at MAX_FILE_SIZE_BYTES = 10 MB combined (exactly at limit).
    // Adding 1 more byte tips over MAX_TOTAL_SIZE_BYTES.
    const atPerFileLimit = MAX_FILE_SIZE_BYTES;
    const existingPhotos: PhotoAttachment[] = [
      {
        file: makeFile("existing-a.jpg", "image/jpeg", atPerFileLimit),
        previewUrl: "blob:mock/existing-a.jpg",
      },
      {
        file: makeFile("existing-b.jpg", "image/jpeg", atPerFileLimit),
        previewUrl: "blob:mock/existing-b.jpg",
      },
    ];
    const onPhotosChange = vi.fn();

    render(
      <EditScreen
        {...defaultProps}
        photos={existingPhotos}
        onPhotosChange={onPhotosChange}
      />
    );

    const input = screen.getByLabelText("Upload photos") as HTMLInputElement;
    const newFile = makeFile("new.jpg", "image/jpeg", 1);
    uploadFiles(input, [newFile]);

    expect(onPhotosChange).not.toHaveBeenCalled();
    expect(screen.getByText(/total size/i)).toBeTruthy();
  });
});
