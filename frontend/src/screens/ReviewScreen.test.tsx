import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReviewScreen from "./ReviewScreen";
import type { ClientStateView, SafetyMessage } from "../types";
import type { PhotoAttachment } from "../uiTypes";

const noop = () => {};

function makePhoto(n: number): PhotoAttachment {
  return { file: new File([], `photo${n}.jpg`), previewUrl: `blob:fake-url-${n}` };
}

const baseClientState: ClientStateView = {
  condition_label: "Urinary symptoms",
  free_text: null,
  additional_text: null,
  questions: [
    {
      answer_key: "q1",
      question_text: "Do you have pain?",
      answer_type: "boolean",
      current_value: true,
      required: true,
      suggested: false,
    },
    {
      answer_key: "q2",
      question_text: "How long have you had symptoms?",
      answer_type: "text",
      current_value: "Three days",
      required: true,
      suggested: false,
    },
  ],
};

describe("ReviewScreen", () => {
  it("renders the condition label and question list", () => {
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("Urinary symptoms")).toBeTruthy();
    expect(screen.getByText("Do you have pain?")).toBeTruthy();
    expect(screen.getByText("How long have you had symptoms?")).toBeTruthy();
  });

  it("renders boolean answers as Yes or No", () => {
    const clientState: ClientStateView = {
      ...baseClientState,
      questions: [
        {
          answer_key: "q1",
          question_text: "Do you have pain?",
          answer_type: "boolean",
          current_value: true,
          required: true,
          suggested: false,
        },
        {
          answer_key: "q2",
          question_text: "Any fever?",
          answer_type: "boolean",
          current_value: false,
          required: true,
          suggested: false,
        },
      ],
    };
    render(
      <ReviewScreen
        clientState={clientState}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("Yes")).toBeTruthy();
    expect(screen.getByText("No")).toBeTruthy();
  });

  it("renders safety alert when safety messages are present", () => {
    const safetyMessages: SafetyMessage[] = [
      { rule_id: "r1", message: "Seek urgent care immediately." },
    ];
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={safetyMessages}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    
    // Verify the alert role is present for immediate screen reader announcement
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/seek urgent care immediately/i)).toBeTruthy();
    
    // Use a textContent matcher constrained by tagName to test the sr-only + visible text combo
    // Bypassing testing-library's normalized `content` string in favor of native DOM `textContent`
    // to avoid cross-browser or jsdom whitespace inconsistencies.
    expect(
      screen.getByText((_, element) => {
        const text = element?.textContent || "";
        return (
          element?.tagName === "STRONG" &&
          /Important:\s*Action required/.test(text)
        );
      })
    ).toBeTruthy();
  });

  it("Continue button remains enabled when safety messages are present, but clicking focuses the alert instead of continuing", async () => {
    const safetyMessages: SafetyMessage[] = [
      { rule_id: "r1", message: "Seek urgent care immediately." },
    ];
    const onContinue = vi.fn();
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={safetyMessages}
        photos={[]}
        onBack={noop}
        onContinue={onContinue}
      />
    );
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn.hasAttribute("disabled")).toBe(false);
    await userEvent.click(btn);
    expect(onContinue).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBe(document.activeElement);
  });

  it("Continue button is enabled when no safety messages", () => {
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(
      screen.getByRole("button", { name: /continue/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("Back button calls onBack", async () => {
    const onBack = vi.fn();
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={[]}
        onBack={onBack}
        onContinue={noop}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("Continue button calls onContinue", async () => {
    const onContinue = vi.fn();
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={onContinue}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("does not render photos section when photos is empty", () => {
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.queryByText(/^Photos/)).toBeNull();
    expect(screen.queryByText(/to remove a photo/i)).toBeNull();
  });

  it("renders the correct number of thumbnails when photos are present", () => {
    const photos = [makePhoto(1), makePhoto(2)];
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={photos}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("Photos (2)")).toBeTruthy();
    const images = screen.getAllByRole("img");
    expect(images).toHaveLength(2);
    expect(screen.getByText(/to remove a photo/i)).toBeTruthy();
  });

  it("each thumbnail has the correct src and alt text", () => {
    const photos = [makePhoto(1), makePhoto(2)];
    render(
      <ReviewScreen
        clientState={baseClientState}
        safetyMessages={[]}
        photos={photos}
        onBack={noop}
        onContinue={noop}
      />
    );
    const images = screen.getAllByRole("img");
    expect(images[0].getAttribute("src")).toBe("blob:fake-url-1");
    expect(images[0].getAttribute("alt")).toBe("Photo 1");
    expect(images[1].getAttribute("src")).toBe("blob:fake-url-2");
    expect(images[1].getAttribute("alt")).toBe("Photo 2");
  });

  // --- Quantity (unit-toggle) answers ---

  function quantityState(
    current_value: ClientStateView["questions"][number]["current_value"]
  ): ClientStateView {
    return {
      condition_label: "Weight demo",
      free_text: null,
      additional_text: null,
      questions: [
        {
          answer_key: "weight",
          question_text: "What is your current weight?",
          answer_type: "number",
          current_value,
          required: true,
          suggested: false,
          quantity: true,
          quantity_kind: "weight",
          allowed_systems: ["metric", "imperial"],
          default_system: "metric",
          decimal_places: 1,
        },
      ],
    };
  }

  it("renders an imperial quantity answer as stones and pounds", () => {
    render(
      <ReviewScreen
        clientState={quantityState({ system: "imperial", components: { st: "11", lb: "11" } })}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("11 st 11 lb")).toBeTruthy();
  });

  it("renders a metric quantity answer as kilograms", () => {
    render(
      <ReviewScreen
        clientState={quantityState({ system: "metric", components: { kg: "70.5" } })}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("70.5 kg")).toBeTruthy();
  });

  it("keeps a zero pounds component rather than dropping it", () => {
    render(
      <ReviewScreen
        clientState={quantityState({ system: "imperial", components: { st: "11", lb: "0" } })}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("11 st 0 lb")).toBeTruthy();
  });

  it("renders an unanswered quantity question as Not answered", () => {
    render(
      <ReviewScreen
        clientState={quantityState(null)}
        safetyMessages={[]}
        photos={[]}
        onBack={noop}
        onContinue={noop}
      />
    );
    expect(screen.getByText("Not answered")).toBeTruthy();
  });
});