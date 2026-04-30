import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { friendlyPhotoErrorMessage } from "./helpers";
import { finishForm, friendlyErrorMessage, ApiError } from "./api";
import type { ContactPreferences, PatientDetails } from "./types";

// ---------------------------------------------------------------------------
// friendlyPhotoErrorMessage
// ---------------------------------------------------------------------------

describe("friendlyPhotoErrorMessage", () => {
  it("returns a patient-friendly message for a per-file size error", () => {
    const result = friendlyPhotoErrorMessage("Photo 1 exceeds the 5242880 byte limit");
    expect(result).toBe(
      "One of your photos is too large to send. Please go back and remove it, then try again."
    );
  });

  it("returns a patient-friendly message for a combined size error", () => {
    const result = friendlyPhotoErrorMessage("Combined photo size exceeds the 10485760 byte limit");
    expect(result).toBe(
      "Your photos together are too large to send. Please go back and remove one or more, then try again."
    );
  });

  it("returns a patient-friendly message for a count error", () => {
    const result = friendlyPhotoErrorMessage("Too many photos: maximum is 5");
    expect(result).toBe(
      "You have attached too many photos. Please go back and remove some, then try again."
    );
  });

  it("returns the server message directly for an ImageTooLargeError", () => {
    // The server message from ImageTooLargeError already contains patient-facing
    // instructions, so it is passed through rather than replaced with a generic string.
    const detail =
      "Image could not be reduced below the 5 MB limit. " +
      "Please check your camera settings — 12MP or lower is recommended. " +
      "You can also crop the image before uploading.";
    const result = friendlyPhotoErrorMessage(detail);
    expect(result).toBe(detail);
  });

  it("returns null for an unrecognised detail string", () => {
    const result = friendlyPhotoErrorMessage("Something completely unexpected");
    expect(result).toBeNull();
  });

  it("returns null for an empty string", () => {
    expect(friendlyPhotoErrorMessage("")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// friendlyErrorMessage — 422 branch
// ---------------------------------------------------------------------------

describe("friendlyErrorMessage — 422 photo errors", () => {
  it("converts a recognised photo detail string into a patient-friendly message", () => {
    const err = new ApiError("HTTP 422", 422, "Photo 2 exceeds the 5242880 byte limit");
    expect(friendlyErrorMessage(err)).toBe(
      "One of your photos is too large to send. Please go back and remove it, then try again."
    );
  });

  it("passes through the ImageTooLargeError message from the server", () => {
    const detail =
      "Image could not be reduced below the 5 MB limit. " +
      "Please check your camera settings — 12MP or lower is recommended. " +
      "You can also crop the image before uploading.";
    const err = new ApiError("HTTP 422", 422, detail);
    expect(friendlyErrorMessage(err)).toBe(detail);
  });

  it("falls back to the generic message for an unrecognised 422 detail", () => {
    const err = new ApiError("HTTP 422", 422, "Some unexpected server error");
    expect(friendlyErrorMessage(err)).toBe("Something went wrong. Please try again.");
  });

  it("falls back to the generic message for a 422 with no detail", () => {
    const err = new ApiError("HTTP 422", 422, null);
    expect(friendlyErrorMessage(err)).toBe("Something went wrong. Please try again.");
  });
});

// ---------------------------------------------------------------------------
// finishForm — multipart fetch
// ---------------------------------------------------------------------------

const RUNTIME_ID = "test-runtime-id";
const VERSION = 1;

const CONTACT_PREFS: ContactPreferences = {
  contact_methods: ["email"],
  email_address: "patient@example.com",
  phone_number: null,
  best_time_to_call: null,
  doctor_preference: "any",
  usual_doctor_name: null,
  consultation_outcome: "not_sure",
};

const PATIENT_DETAILS: PatientDetails = {
  patient_for: "me",
  first_name: "Jane",
  last_name: "Smith",
  date_of_birth: { day: "01", month: "01", year: "1980" },
  postcode: "SW1A 1AA",
  gender: "female",
};

describe("finishForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends a multipart POST and returns submission_id on success", async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ submission_id: "abc-123" }), { status: 200 })
    );

    const result = await finishForm(
      RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [], null
    );

    expect(result).toEqual({ submission_id: "abc-123" });

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/form/finish");
    expect(init.method).toBe("POST");
    // Content-Type must NOT be set manually — the browser sets it with the boundary
    const headers = init.headers as Record<string, string> | undefined;
    expect(headers?.["Content-Type"]).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("includes the JSON payload as the 'payload' field", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ submission_id: "abc-123" }), { status: 200 })
    );

    await finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [], null);

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    const payloadField = body.get("payload");
    expect(typeof payloadField).toBe("string");
    const parsed = JSON.parse(payloadField as string);
    expect(parsed.runtime_id).toBe(RUNTIME_ID);
    expect(parsed.version).toBe(VERSION);
    expect(parsed.contact_preferences).toEqual(CONTACT_PREFS);
    expect(parsed.patient_details).toEqual(PATIENT_DETAILS);
  });

  it("does not include photo_quality_tier in the payload when no photos are submitted", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ submission_id: "abc-123" }), { status: 200 })
    );

    await finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [], null);

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    const parsed = JSON.parse(body.get("payload") as string);
    expect(parsed).not.toHaveProperty("photo_quality_tier");
  });

  it("includes photo_quality_tier in the payload when photos are present", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ submission_id: "abc-123" }), { status: 200 })
    );

    const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], "a.jpg", { type: "image/jpeg" });
    await finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [file], "standard");

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    const parsed = JSON.parse(body.get("payload") as string);
    expect(parsed.photo_quality_tier).toBe("standard");
  });

  it("includes photo_quality_tier 'high' when high tier is selected", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ submission_id: "abc-123" }), { status: 200 })
    );

    const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], "a.jpg", { type: "image/jpeg" });
    await finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [file], "high");

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    const parsed = JSON.parse(body.get("payload") as string);
    expect(parsed.photo_quality_tier).toBe("high");
  });

  it("appends each File as a 'photos' field", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ submission_id: "abc-123" }), { status: 200 })
    );

    const file1 = new File([new Uint8Array([0xff, 0xd8, 0xff])], "a.jpg", { type: "image/jpeg" });
    const file2 = new File([new Uint8Array([0xff, 0xd8, 0xff])], "b.jpg", { type: "image/jpeg" });

    await finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [file1, file2], "standard");

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    const photoFields = body.getAll("photos");
    expect(photoFields).toHaveLength(2);
    expect((photoFields[0] as File).name).toBe("a.jpg");
    expect((photoFields[1] as File).name).toBe("b.jpg");
  });

  it("throws ApiError with status 422 and detail on a photo validation failure", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Photo 1 exceeds the 5242880 byte limit" }),
        { status: 422 }
      )
    );

    await expect(
      finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [], null)
    ).rejects.toMatchObject({
      status: 422,
      detail: "Photo 1 exceeds the 5242880 byte limit",
    });
  });

  it("throws ApiError with null status on network failure", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(
      finishForm(RUNTIME_ID, VERSION, CONTACT_PREFS, PATIENT_DETAILS, [], null)
    ).rejects.toMatchObject({ status: null });
  });
});