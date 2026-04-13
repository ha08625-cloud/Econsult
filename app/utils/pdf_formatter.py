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
_LINE_H = 7         # mm standard line height
_PAGE_W = 210       # A4 width in mm
_USABLE_W = _PAGE_W - 2 * _MARGIN   # 180mm
_LABEL_W = 65       # mm — label column width in two-column rows
_VALUE_W = _USABLE_W - _LABEL_W     # 115mm — value column width
_LEFT_INDENT = 5    # mm — indent for free text body blocks

# Colours
_SAFETY_BG     = (255, 248, 230)   # light amber for safety flag rows
_RULE_COLOUR   = (200, 200, 200)   # light grey for horizontal rules/separators
_FOOTER_COLOUR = (120, 120, 120)   # grey for footer text
_INDENT_BAR    = (200, 200, 200)   # grey for free text left-border bar

# Maximum height an embedded photo may occupy on the page.
_MAX_IMAGE_H = 200  # mm

# Lookup dict from outcome value to human-readable label.
_OUTCOME_LABELS: dict[str, str] = {
    entry["value"]: entry["label"] for entry in CONSULTATION_OUTCOMES
}


class _EConsultPDF(FPDF):
    """FPDF subclass with convenience methods for this document style."""

    def header(self):
        # No running header — each page starts blank.
        pass

    def footer(self):
        """
        Render a consistent footer with page numbers at the bottom of every page.
        """
        self.set_y(-15)
        self.set_font("Helvetica", style="I", size=8)
        self.set_text_color(*_FOOTER_COLOUR)
        self.cell(
            0, 5, 
            f"Online Consultation Form  |  Page {self.page_no()} of {{nb}}", 
            align="C"
        )
        self.set_text_color(0, 0, 0) # Reset text color for safety

    def section_heading(self, title: str) -> None:
        """
        Render a clean section heading with a crisp bottom underline.
        """
        self.ln(8) # Breathing room before new section
        
        self.set_font("Helvetica", style="B", size=11)
        self.set_text_color(60, 60, 60) # Dark charcoal
        
        self.cell(_USABLE_W, _LINE_H, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        # Draw a crisp underline exactly beneath the heading
        y_line = self.get_y()
        self.set_draw_color(*_RULE_COLOUR)
        self.set_line_width(0.3)
        self.line(self.l_margin, y_line, self.l_margin + _USABLE_W, y_line)
        self.set_line_width(0.2) # Reset to FPDF default
        
        self.ln(2)
        self.set_text_color(0, 0, 0) # Reset text to black

    def row(self, label: str, value: str, draw_separator: bool = True) -> None:
        """
        Render a two-column label/value row with an optional faint bottom border.
        """
        self.set_x(self.l_margin)

        self.set_font("Helvetica", style="B", size=10)
        self.cell(_LABEL_W, _LINE_H, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", size=10)
        self.multi_cell(_VALUE_W, _LINE_H, value)

        if draw_separator:
            y = self.get_y()
            self.set_draw_color(245, 245, 245) # Very faint line
            self.line(self.l_margin, y, self.l_margin + _USABLE_W, y)
            self.ln(1)

    def safety_row(self, label: str, value: str) -> None:
        """
        Render a safety flag row with amber background and bold value text.
        """
        self.set_x(self.l_margin)
        self.set_fill_color(*_SAFETY_BG)
        x = self.get_x()
        y = self.get_y()
        self.rect(x, y, _USABLE_W, _LINE_H, style="F")
        self.set_xy(x, y)

        self.set_font("Helvetica", style="B", size=10)
        self.cell(_LABEL_W, _LINE_H, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", style="B", size=10)
        self.multi_cell(_VALUE_W, _LINE_H, value)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", size=10)
        self.multi_cell(_USABLE_W, _LINE_H, text)

    def body_text_indented(self, text: str) -> None:
        """
        Render free text with a left indent and a grey vertical bar on the
        left edge to visually distinguish it from structured rows.
        """
        x = self.l_margin
        y = self.get_y()

        self.set_x(x + _LEFT_INDENT)
        self.set_font("Helvetica", size=10)
        self.multi_cell(_USABLE_W - _LEFT_INDENT, _LINE_H, text)

        end_y = self.get_y()
        self.set_draw_color(*_INDENT_BAR)
        self.set_line_width(0.8)
        self.line(x + 1, y, x + 1, end_y)
        self.set_line_width(0.2)
        self.ln(2)


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
    """
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()

    # --- Document header (Modernized Hierarchy) ---
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 8, "Online Consultation", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

    if practice_name:
        pdf.set_font("Helvetica", size=11)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, practice_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + _USABLE_W, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(2)

    # --- Submission metadata ---
    pdf.section_heading("SUBMISSION DETAILS")
    pdf.row("Condition:", condition_label)
    pdf.row("Submission ID:", submission_id)
    pdf.row("Submitted at:", submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC"), draw_separator=False)

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
    pdf.body_text_indented(clinical_output.free_text or "(none provided)")

    # --- Answers ---
    pdf.section_heading("ANSWERS")
    for key, value in clinical_output.answers.items():
        label = clinical_output.question_labels.get(key, key)
        pdf.row(f"{label}:", _format_answer(value))

    # --- Additional information ---
    if clinical_output.additional_text:
        pdf.section_heading("ADDITIONAL INFORMATION")
        pdf.body_text_indented(clinical_output.additional_text)

    # --- Safety flags ---
    if clinical_output.safety_messages:
        pdf.section_heading("SAFETY FLAGS")
        for msg in clinical_output.safety_messages:
            flag_id = msg.get("id", "")
            flag_text = msg.get("text", "")
            pdf.safety_row(f"[{flag_id}]", flag_text)

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
            pdf.row("Consultation outcome:", outcome_label, draw_separator=False)

    # --- Photos ---
    if photo_bytes:
        pdf.set_text_color(0, 0, 0)
        pdf.section_heading("PHOTOS")
        total = len(photo_bytes)
        for i, img_bytes in enumerate(photo_bytes):
            pdf.set_font("Helvetica", style="I", size=9)
            pdf.body_text(f"Photo {i + 1} of {total}")
            pdf.ln(2)
            pdf.image(io.BytesIO(img_bytes), w=_USABLE_W, h=_MAX_IMAGE_H, keep_aspect_ratio=True)

    return bytes(pdf.output())
