"""
PDF formatter.

Pure utility: takes clinical submission data and returns raw PDF bytes.
No database access. No imports from routers or delivery service.

generate_pdf() mirrors the sections in the plain-text email body so both
outputs carry the same information in the same order.
"""

from datetime import datetime
from typing import Optional

from fpdf import FPDF

from app.models.serialisation_contracts import ClinicalOutput


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


class _EConsultPDF(FPDF):
    """FPDF subclass with convenience methods for this document style."""

    def header(self):
        # No running header — each page starts blank.
        pass

    def section_heading(self, title: str) -> None:
        self.ln(_SECTION_GAP)
        self.set_font("Helvetica", style="B", size=10)
        self.cell(0, _LINE_H, title, ln=True)
        self.set_draw_color(180, 180, 180)
        self.line(self.get_x(), self.get_y(), self.get_x() + 180, self.get_y())
        self.ln(1)
        self.set_font("Helvetica", size=9)

    def row(self, label: str, value: str) -> None:
        self.set_font("Helvetica", style="B", size=9)
        self.cell(60, _LINE_H, label, ln=False)
        self.set_font("Helvetica", size=9)
        self.multi_cell(0, _LINE_H, value)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", size=9)
        self.multi_cell(0, _LINE_H, text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pdf(
    condition_label: str,
    clinical_output: ClinicalOutput,
    submission_id: str,
    submitted_at: datetime,
    practice_name: Optional[str] = None,
) -> bytes:
    """
    Generate a PDF representation of a clinical submission.

    Returns raw PDF bytes. The caller is responsible for attaching or saving them.

    Sections mirror the plain-text email body: header, submission metadata,
    patient details, free text description, answers, additional information,
    safety flags, contact preferences, footer.
    """
    pdf = _EConsultPDF()
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()

    # --- Document title ---
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, "E-Consultation Submission", ln=True, align="C")

    if practice_name:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, practice_name, ln=True, align="C")

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

    # --- Footer ---
    pdf.ln(_SECTION_GAP)
    pdf.set_font("Helvetica", style="I", size=8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(
        0, 5,
        "Generated automatically by the e-consultation system. Do not reply to this document.",
        ln=True,
        align="C",
    )

    return bytes(pdf.output())
