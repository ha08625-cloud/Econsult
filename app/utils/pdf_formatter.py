"""
PDF formatter.

Pure utility: takes clinical submission data and returns raw PDF bytes.
No database access. No imports from routers or delivery service.

generate_pdf() mirrors the sections in the plain-text email body so both
outputs carry the same information in the same order.
"""

import io
from datetime import datetime
from typing import Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.models.serialisation_contracts import ClinicalOutput
from app.core.consultation_outcomes import CONSULTATION_OUTCOMES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_answer(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return "(not answered)"
    return str(value)


def _dob_display(dob_iso: str) -> str:
    """
    Convert ISO date string "YYYY-MM-DD" to "15 March 1990".
    Falls back to the raw string if parsing fails.
    """
    try:
        return datetime.strptime(dob_iso, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return dob_iso


# ---------------------------------------------------------------------------
# PDF layout constants
# ---------------------------------------------------------------------------

_MARGIN = 15        # mm left/right margin
_LINE_H = 6         # mm standard line height
_SECTION_GAP = 4    # mm gap before a new section heading
_PAGE_W = 210       # A4 width in mm
_USABLE_W = _PAGE_W - 2 * _MARGIN   # 180mm
_LABEL_W = 55       # mm — label column width in two-column rows
_VALUE_W = _USABLE_W - _LABEL_W     # 125mm — value column width

# Maximum height an embedded photo may occupy on the page.
# Images taller than this at _USABLE_W wide are scaled down to fit.
# This prevents a single tall image from being taller than a full page,
# which would cause FPDF2 to clip it rather than paginate correctly.
# A4 usable height (297mm - 2 * 15mm margin - 15mm auto-page-break margin) = ~252mm.
# 200mm leaves comfortable breathing room.
_MAX_IMAGE_H = 200  # mm

# Lookup dict from outcome value to human-readable label.
# Derived from CONSULTATION_OUTCOMES at module load time — do not hardcode here.
_OUTCOME_LABELS: dict[str, str] = {
    entry["value"]: entry["label"] for entry in CONSULTATION_OUTCOMES
}


class _EConsultPDF(FPDF):
    """FPDF subclass with convenience methods for this document style."""

    def header(self):
        # No running header — each page starts blank.
        pass

    def section_heading(self, title: str) -> None:
        self.ln(_SECTION_GAP)
        self.set_font("Helvetica", style="B", size=10)
        self.cell(0, _LINE_H, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(180, 180, 180)
        self.line(self.get_x(), self.get_y(), self.get_x() + _USABLE_W, self.get_y())
        self.ln(1)
        self.set_font("Helvetica", size=9)

    def row(self, label: str, value: str) -> None:
        """
        Render a two-column label/value row.

        Both widths are explicit so fpdf2 wraps the value within the remaining
        column rather than overflowing. multi_cell advances the cursor to the
        next line after rendering.
        """
        self.set_x(self.l_margin)
        self.set_font("Helvetica", style="B", size=9)
        self.cell(_LABEL_W, _LINE_H, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", size=9)
        self.multi_cell(_VALUE_W, _LINE_H, value)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", size=9)
        self.multi_cell(_USABLE_W, _LINE_H, text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pdf(
    condition_label: str,
    clinical_output: ClinicalOutput,
    submission_id: str,
    submitted_at: datetime,
    practice_name: Optional[str] = None,
    photo_bytes: Optional[list[bytes]] = None,
) -> bytes:
    """
    Generate a PDF representation of a clinical submission.

    Returns raw PDF bytes. The caller is responsible for attaching or saving them.

    Sections mirror the plain-text email body: header, submission metadata,
    patient details, free text description, answers, additional information,
    safety flags, contact preferences, footer.

    If photo_bytes is provided and non-empty, a PHOTOS section is appended
    after the footer. Each image is embedded at full usable width (_USABLE_W),
    capped at _MAX_IMAGE_H tall to prevent overflow on a single page. FPDF2
    handles pagination automatically between images.

    Memory note: FPDF2 decodes each JPEG into a raw pixel buffer internally
    before embedding. A single 5 MB JPEG may decompress to 50-100 MB in memory.
    With multiple large photos, peak memory during PDF generation can be
    several hundred MB. This is accepted at current scale. A background worker
    with async PDF generation is the planned mitigation — see arch_submission.md.
    """
    pdf = _EConsultPDF()
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()

    # --- Document title ---
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, "E-Consultation Submission", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    if practice_name:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, practice_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    pdf.ln(2)

    # --- Submission metadata ---
    pdf.section_heading("SUBMISSION DETAILS")
    pdf.row("Condition:", condition_label)
    pdf.row("Submission ID:", submission_id)
    pdf.row("Submitted at:", submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC"))

    # --- Patient details ---
    pd = clinical_output.patient_details
    pdf.section_heading("PATIENT DETAILS")
    pdf.row("Patient for:", pd.patient_for or "")
    pdf.row("Name:", f"{pd.first_name} {pd.last_name}")
    if pd.date_of_birth:
        pdf.row("Date of birth:", _dob_display(pd.date_of_birth))
    pdf.row("Postcode:", pd.postcode or "")
    if pd.submitter_name:
        pdf.row("Submitted by:", pd.submitter_name)
    if pd.submitter_relationship:
        pdf.row("Relationship:", pd.submitter_relationship)

    # --- Patient description (free text) ---
    pdf.section_heading("PATIENT DESCRIPTION")
    pdf.body_text(clinical_output.free_text or "(none provided)")

    # --- Answers ---
    pdf.section_heading("ANSWERS")
    for key, value in clinical_output.answers.items():
        label = clinical_output.question_labels.get(key, key)
        pdf.row(f"{label}:", _format_answer(value))

    # --- Additional information ---
    if clinical_output.additional_text:
        pdf.section_heading("ADDITIONAL INFORMATION")
        pdf.body_text(clinical_output.additional_text)

    # --- Safety flags ---
    if clinical_output.safety_messages:
        pdf.section_heading("SAFETY FLAGS")
        for msg in clinical_output.safety_messages:
            flag_id = msg.get("id", "")
            flag_text = msg.get("text", "")
            pdf.row(f"[{flag_id}]", flag_text)

    # --- Contact preferences ---
    cp = clinical_output.contact_preferences
    if cp:
        pdf.section_heading("CONTACT PREFERENCES")

        methods = cp.get("contact_methods") or []
        method_labels = {"email": "Email", "text": "Text message", "phone": "Phone call"}
        readable_methods = ", ".join(method_labels.get(m, m) for m in methods)
        if readable_methods:
            pdf.row("Contact methods:", readable_methods)

        if cp.get("email_address"):
            pdf.row("Email address:", cp["email_address"])
        if cp.get("phone_number"):
            pdf.row("Phone number:", cp["phone_number"])
        if cp.get("best_time_to_call"):
            pdf.row("Best time to call:", cp["best_time_to_call"])

        doctor_pref = cp.get("doctor_preference")
        if doctor_pref == "usual":
            pdf.row("Doctor preference:", "Usual doctor")
            if cp.get("usual_doctor_name"):
                pdf.row("Usual doctor name:", cp["usual_doctor_name"])
        elif doctor_pref == "any":
            pdf.row("Doctor preference:", "Soonest available doctor")

        outcome = cp.get("consultation_outcome")
        if outcome:
            outcome_label = _OUTCOME_LABELS.get(outcome, outcome)
            pdf.row("Consultation outcome:", outcome_label)

    # --- Footer ---
    pdf.ln(_SECTION_GAP)
    pdf.set_font("Helvetica", style="I", size=8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(
        0, 5,
        "Generated automatically by the e-consultation system. Do not reply to this document.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )

    # --- Photos ---
    # Rendered after the footer so clinical content always appears first.
    # Each image is embedded at full usable width. Height is capped at
    # _MAX_IMAGE_H to prevent a single tall image from overflowing a page.
    # FPDF2 auto-paginates between images when needed.
    if photo_bytes:
        pdf.set_text_color(0, 0, 0)
        pdf.section_heading("PHOTOS")
        total = len(photo_bytes)
        for i, img_bytes in enumerate(photo_bytes):
            pdf.body_text(f"Photo {i + 1} of {total}")
            pdf.ln(2)
            pdf.image(io.BytesIO(img_bytes), w=_USABLE_W, h=_MAX_IMAGE_H, keep_aspect_ratio=True)

    return bytes(pdf.output())