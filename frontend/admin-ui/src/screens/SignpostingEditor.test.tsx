/**
 * SignpostingEditor.test.tsx
 *
 * Quill is an imperative DOM library that does not work in jsdom. It is
 * replaced here with a hand-written fake that exposes the same interface
 * the component calls:
 *
 *   getText()                         — returns the current text content
 *   setText(value)                    — sets text and resets content
 *   on(event, handler)                — registers an event handler
 *   off(event)                        — removes all handlers for an event
 *   getSemanticHTML()                 — returns HTML representation
 *   clipboard.dangerouslyPasteHTML()  — sets content from an HTML string
 *
 * Tests drive the "text-change" event by calling
 * fakeQuillInstance.simulateChange() after mutating fakeQuillInstance.text.
 * This lets us assert on onUnsavedChange callbacks and unsaved-change UI
 * without needing a real browser environment.
 *
 * DOMPurify.sanitize is mocked to return its input unchanged. Sanitisation
 * correctness is the responsibility of the Python backend and is tested
 * there.
 */

import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, type Mock } from "vitest";

// ---------------------------------------------------------------------------
// Quill mock — must be declared before the component import so that Vitest's
// module mock hoisting replaces the real Quill before SignpostingEditor loads.
// ---------------------------------------------------------------------------

interface FakeQuill {
  text: string;
  handlers: Record<string, (() => void)[]>;
  getText: () => string;
  setText: (v: string) => void;
  on: (event: string, handler: () => void) => void;
  off: (event: string) => void;
  getSemanticHTML: () => string;
  clipboard: { dangerouslyPasteHTML: (html: string) => void };
  simulateChange: () => void;
}

// The fake instance is stored in module scope so individual tests can
// access it to drive text-change events and inspect state.
let fakeQuillInstance: FakeQuill;

vi.mock("quill", () => {
  const FakeQuillClass = vi.fn().mockImplementation(() => {
    fakeQuillInstance = {
      text: "\n", // Quill's empty state is a single newline
      handlers: {},
      getText() {
        return this.text;
      },
      setText(v: string) {
        this.text = v || "\n";
      },
      on(event: string, handler: () => void) {
        if (!this.handlers[event]) this.handlers[event] = [];
        this.handlers[event].push(handler);
      },
      off(event: string) {
        this.handlers[event] = [];
      },
      getSemanticHTML() {
        return `<p>${this.text.trim()}</p>`;
      },
      clipboard: {
        dangerouslyPasteHTML(html: string) {
          // Extract the text content from the pasted HTML so getText()
          // returns something meaningful after a paste.
          fakeQuillInstance.text = html.replace(/<[^>]+>/g, "") + "\n";
        },
      },
      simulateChange() {
        (this.handlers["text-change"] || []).forEach((h) => h());
      },
    };
    return fakeQuillInstance;
  });

  return { default: FakeQuillClass };
});

// ---------------------------------------------------------------------------
// DOMPurify mock
// ---------------------------------------------------------------------------

vi.mock("dompurify", () => ({
  default: {
    sanitize: (input: string) => input,
  },
}));

// ---------------------------------------------------------------------------
// API mock
// ---------------------------------------------------------------------------

vi.mock("../api", () => {
  class AuthError extends Error {
    constructor() {
      super("Session expired or not authenticated.");
      this.name = "AuthError";
    }
  }

  return {
    fetchSignposting: vi.fn(),
    putSignposting: vi.fn(),
    AuthError,
  };
});

import { fetchSignposting, putSignposting, AuthError } from "../api";
const mockFetch = fetchSignposting as Mock;
const mockPut = putSignposting as Mock;

// ---------------------------------------------------------------------------
// Component import — after all mocks are in place
// ---------------------------------------------------------------------------

import SignpostingEditor from "./SignpostingEditor";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const noop = () => {};

function renderEditor(overrides: Partial<{
  conditionId: string;
  onUnsavedChange: (v: boolean) => void;
  onAuthError: () => void;
}> = {}) {
  const props = {
    conditionId: "urinary_symptoms",
    onUnsavedChange: noop,
    onAuthError: noop,
    ...overrides,
  };
  return render(<SignpostingEditor {...props} />);
}

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

describe("SignpostingEditor — loading state", () => {
  it("shows a loading indicator while the fetch is in progress", async () => {
    // Never resolves during this test
    mockFetch.mockReturnValue(new Promise(() => {}));
    renderEditor();
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("hides the loading indicator after the fetch resolves", async () => {
    mockFetch.mockResolvedValueOnce(null);
    renderEditor();
    await waitFor(() =>
      expect(screen.queryByText(/loading/i)).toBeNull()
    );
  });

  it("shows the Save button after loading completes", async () => {
    mockFetch.mockResolvedValueOnce(null);
    renderEditor();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save/i })).toBeTruthy()
    );
  });
});

describe("SignpostingEditor — load error", () => {
  it("shows an error message when the fetch fails", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network failure"));
    renderEditor();
    await waitFor(() =>
      expect(screen.getByText(/could not load signposting/i)).toBeTruthy()
    );
  });

  it("includes the error detail in the message", async () => {
    mockFetch.mockRejectedValueOnce(new Error("timeout"));
    renderEditor();
    await waitFor(() =>
      expect(screen.getByText(/timeout/i)).toBeTruthy()
    );
  });

  it("does not show the Save button when loading failed", async () => {
    mockFetch.mockRejectedValueOnce(new Error("bad"));
    renderEditor();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /save/i })).toBeNull()
    );
  });
});

describe("SignpostingEditor — auth error on load", () => {
  it("calls onAuthError and does not show an error message", async () => {
    const onAuthError = vi.fn();
    mockFetch.mockRejectedValueOnce(new AuthError());
    renderEditor({ onAuthError });
    await waitFor(() => expect(onAuthError).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/could not load/i)).toBeNull();
  });
});

describe("SignpostingEditor — save success", () => {
  it("calls putSignposting with the correct condition ID on save", async () => {
    mockFetch.mockResolvedValueOnce(null);
    mockPut.mockResolvedValueOnce("<p>content</p>");

    renderEditor({ conditionId: "back_pain" });
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1));
    expect(mockPut.mock.calls[0][0]).toBe("back_pain");
  });

  it("shows 'Saved' status after a successful save", async () => {
    mockFetch.mockResolvedValueOnce(null);
    mockPut.mockResolvedValueOnce("<p>saved content</p>");

    renderEditor();
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(screen.getByText(/saved/i)).toBeTruthy()
    );
  });

  it("calls onUnsavedChange(false) after a successful save", async () => {
    const onUnsavedChange = vi.fn();
    mockFetch.mockResolvedValueOnce(null);
    mockPut.mockResolvedValueOnce("<p>content</p>");

    renderEditor({ onUnsavedChange });
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      const calls = onUnsavedChange.mock.calls.map(([v]) => v);
      expect(calls).toContain(false);
    });
  });

  it("Save button is not disabled while idle", async () => {
    mockFetch.mockResolvedValueOnce(null);
    renderEditor();
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /save/i });
      expect(btn.hasAttribute("disabled")).toBe(false);
    });
  });

  it("Save button is disabled while saving is in progress", async () => {
    mockFetch.mockResolvedValueOnce(null);
    // putSignposting never resolves during this test
    mockPut.mockReturnValue(new Promise(() => {}));

    renderEditor();
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /saving/i });
      expect(btn.hasAttribute("disabled")).toBe(true);
    });
  });
});

describe("SignpostingEditor — save failure", () => {
  it("shows an error save status when putSignposting rejects", async () => {
    mockFetch.mockResolvedValueOnce(null);
    mockPut.mockRejectedValueOnce(new Error("Server error"));

    renderEditor();
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(screen.getByText(/save failed/i)).toBeTruthy()
    );
  });

  it("does not call onAuthError when save fails with a generic error", async () => {
    const onAuthError = vi.fn();
    mockFetch.mockResolvedValueOnce(null);
    mockPut.mockRejectedValueOnce(new Error("oops"));

    renderEditor({ onAuthError });
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => screen.getByText(/save failed/i));
    expect(onAuthError).not.toHaveBeenCalled();
  });
});

describe("SignpostingEditor — auth error on save", () => {
  it("calls onAuthError and does not show a save-failed message", async () => {
    const onAuthError = vi.fn();
    mockFetch.mockResolvedValueOnce(null);
    mockPut.mockRejectedValueOnce(new AuthError());

    renderEditor({ onAuthError });
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(onAuthError).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/save failed/i)).toBeNull();
  });
});

describe("SignpostingEditor — unsaved change tracking", () => {
  it("calls onUnsavedChange(true) when content changes from baseline", async () => {
    const onUnsavedChange = vi.fn();
    mockFetch.mockResolvedValueOnce(null);

    renderEditor({ onUnsavedChange });
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    // Mutate the fake Quill's text then fire the text-change event
    act(() => {
      fakeQuillInstance.text = "new content\n";
      fakeQuillInstance.simulateChange();
    });

    expect(onUnsavedChange).toHaveBeenCalledWith(true);
  });

  it("calls onUnsavedChange(false) when content returns to baseline", async () => {
    const onUnsavedChange = vi.fn();
    mockFetch.mockResolvedValueOnce(null);

    renderEditor({ onUnsavedChange });
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    // Baseline for an empty load is "\n". Change then revert.
    act(() => {
      fakeQuillInstance.text = "something\n";
      fakeQuillInstance.simulateChange();
    });
    act(() => {
      fakeQuillInstance.text = "\n";
      fakeQuillInstance.simulateChange();
    });

    const calls = onUnsavedChange.mock.calls.map(([v]) => v);
    expect(calls[calls.length - 1]).toBe(false);
  });

  it("shows the unsaved changes warning when content has changed", async () => {
    mockFetch.mockResolvedValueOnce(null);

    renderEditor();
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    act(() => {
      fakeQuillInstance.text = "changed\n";
      fakeQuillInstance.simulateChange();
    });

    expect(screen.getByText(/unsaved changes/i)).toBeTruthy();
  });

  it("does not show the unsaved warning when content is unchanged", async () => {
    mockFetch.mockResolvedValueOnce(null);
    renderEditor();
    await waitFor(() => screen.getByRole("button", { name: /save/i }));
    expect(screen.queryByText(/unsaved changes/i)).toBeNull();
  });

  it("loads existing content into the editor on mount", async () => {
    mockFetch.mockResolvedValueOnce("<p>existing content</p>");

    renderEditor();
    await waitFor(() => screen.getByRole("button", { name: /save/i }));

    // After dangerouslyPasteHTML the fake stores the stripped text.
    // Verify the clipboard method was called by confirming getText()
    // reflects the pasted content.
    expect(fakeQuillInstance.getText()).toContain("existing content");
  });
});