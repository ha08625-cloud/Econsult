"""
PDF formatter.

Pure utility: takes clinical submission data and returns raw PDF bytes.
No database access. No imports from routers or delivery service.
"""

import io
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.core.consultation_outcomes import CONSULTATION_OUTCOMES
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


def _format_kg(canonical_value, decimal_places: int) -> str:
    """
    Render the canonical kilogram value at exactly decimal_places, in plain
    (non-exponential) notation. The stored value is already rounded by
    convert_unit_answers; quantizing again with explicit ROUND_HALF_UP is
    idempotent and guarantees consistent trailing digits on the document.
    """
    d = Decimal(str(canonical_value))
    quantum = Decimal(1).scaleb(-decimal_places)
    return format(d.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _format_quantity_answer(
    canonical_value, raw_components: dict, unit_system: str | None, decimal_places: int
) -> str:
    """
    Format a quantity (unit-toggle) answer for the document.

    Imperial shows the patient's stones and pounds with the converted kilograms
    in parentheses, e.g. "11 st 11 lb (74.8 kg)". Metric shows the kilograms the
    patient typed directly, e.g. "70.5 kg" -- no parenthetical, since the raw
    input already is the canonical unit.
    """
    if unit_system == "imperial":
        st = raw_components.get("st")
        lb = raw_components.get("lb")
        kg_display = _format_kg(canonical_value, decimal_places)
        return f"{st} st {lb} lb ({kg_display} kg)"
    # metric: the patient typed kilograms; show them verbatim.
    return f"{raw_components.get('kg')} kg"


def _dob_display(dob_iso: str) -> str:
    """
    Convert ISO date string "YYYY-MM-DD" to "15 March 1990".
    Falls back to the raw string if parsing fails.
    """
    try:
        return datetime.strptime(dob_iso, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return dob_iso


def _age_from_dob(dob_iso: str) -> int | None:
    """
    Calculate age in whole years from an ISO date string "YYYY-MM-DD".
    Returns None if the string cannot be parsed.

    Age is calculated as of today. A birthday that has not yet occurred
    this calendar year means the patient has not yet reached their next
    birthday, so one year is subtracted.
    """
    try:
        dob = datetime.strptime(dob_iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = date.today()
    age = today.year - dob.year
    # Subtract 1 if the birthday hasn't occurred yet this year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age


_GENDER_LABELS: dict[str, str] = {
    "male": "Male",
    "female": "Female",
    "other": "Other",
    "prefer_not_to_say": "Prefer not to say",
}


# ---------------------------------------------------------------------------
# PDF layout constants (NHS Palette)
# ---------------------------------------------------------------------------

_MARGIN = 15  # mm left/right margin
_LINE_H = 7  # mm standard line height
_PAGE_W = 210  # A4 width in mm
_USABLE_W = _PAGE_W - 2 * _MARGIN  # 180mm
_LABEL_W = 65  # mm — label column width in two-column rows
_VALUE_W = _USABLE_W - _LABEL_W  # 115mm — value column width
_LEFT_INDENT = 5  # mm — indent for free text body blocks

# Colours - NHS Palette
_NHS_BLUE = (0, 94, 184)  # Primary NHS Blue
_NHS_DARK_GREY = (66, 85, 99)  # NHS Dark Grey for standard text/labels
_NHS_MID_GREY = (118, 134, 146)  # Footer text
_SAFETY_BG = (255, 241, 241)  # Very pale NHS Red tint
_SAFETY_TEXT = (218, 41, 28)  # NHS Red
_RULE_COLOUR = (232, 237, 238)  # NHS Pale Grey for separators
_INDENT_BAR = (0, 94, 184)  # NHS Blue for free-text accent bars

# Maximum height an embedded photo may occupy on the page.
_MAX_IMAGE_H = 200  # mm

# Lookup dict from outcome value to human-readable label.
_OUTCOME_LABELS: dict[str, str] = {
    entry["value"]: entry["label"] for entry in CONSULTATION_OUTCOMES
}


class _EConsultPDF(FPDF):
    """FPDF subclass with convenience methods for this document style."""

    def header(self):
        """
        Draw an NHS Blue accent bar at the very top edge of every page.
        """
        self.set_fill_color(*_NHS_BLUE)
        self.rect(0, 0, _PAGE_W, 5, style="F")

    def footer(self):
        """
        Render a consistent footer with page numbers at the bottom of every page.
        """
        self.set_y(-15)
        self.set_font("Helvetica", style="I", size=8)
        self.set_text_color(*_NHS_MID_GREY)
        self.cell(0, 5, f"Online Consultation Form  |  Page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(0, 0, 0)  # Reset text color for safety

    def section_heading(self, title: str) -> None:
        """
        Render a clean section heading in NHS Blue with a crisp bottom underline.
        """
        self.ln(8)

        self.set_font("Helvetica", style="B", size=11)
        self.set_text_color(*_NHS_BLUE)

        self.cell(_USABLE_W, _LINE_H, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        y_line = self.get_y()
        self.set_draw_color(*_RULE_COLOUR)
        self.set_line_width(0.4)
        self.line(self.l_margin, y_line, self.l_margin + _USABLE_W, y_line)
        self.set_line_width(0.2)

        self.ln(3)
        self.set_text_color(0, 0, 0)

    def row(self, label: str, value: str, draw_separator: bool = True) -> None:
        """
        Render a two-column label/value row that properly wraps text in both columns.
        """
        self.set_font("Helvetica", style="B", size=10)
        label_lines = len(self.multi_cell(_LABEL_W, _LINE_H, label, dry_run=True, output="LINES"))

        self.set_font("Helvetica", size=10)
        value_lines = len(self.multi_cell(_VALUE_W, _LINE_H, value, dry_run=True, output="LINES"))

        row_height = max(label_lines, value_lines) * _LINE_H

        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()

        start_x = self.l_margin
        start_y = self.get_y()

        self.set_font("Helvetica", style="B", size=10)
        self.set_text_color(*_NHS_DARK_GREY)
        self.set_xy(start_x, start_y)
        self.multi_cell(_LABEL_W, _LINE_H, label)

        self.set_font("Helvetica", size=10)
        self.set_text_color(0, 0, 0)
        self.set_xy(start_x + _LABEL_W, start_y)
        self.multi_cell(_VALUE_W, _LINE_H, value)

        self.set_y(start_y + row_height)

        if draw_separator:
            self.set_draw_color(*_RULE_COLOUR)
            self.line(self.l_margin, self.get_y(), self.l_margin + _USABLE_W, self.get_y())
            self.ln(1)

    def safety_row(self, label: str, value: str) -> None:
        """
        Render a safety flag row with pale red background, handling text wrap in both columns.
        """
        self.set_font("Helvetica", style="B", size=10)
        label_lines = len(self.multi_cell(_LABEL_W, _LINE_H, label, dry_run=True, output="LINES"))
        value_lines = len(self.multi_cell(_VALUE_W, _LINE_H, value, dry_run=True, output="LINES"))

        row_height = max(label_lines, value_lines) * _LINE_H
        box_height = row_height + 2

        if self.get_y() + box_height > self.page_break_trigger:
            self.add_page()

        start_x = self.l_margin
        start_y = self.get_y()

        self.set_fill_color(*_SAFETY_BG)
        self.rect(start_x, start_y, _USABLE_W, box_height, style="F")

        self.set_text_color(*_SAFETY_TEXT)
        self.set_xy(start_x, start_y + 1)
        self.multi_cell(_LABEL_W, _LINE_H, label)

        self.set_xy(start_x + _LABEL_W, start_y + 1)
        self.multi_cell(_VALUE_W, _LINE_H, value)

        self.set_text_color(0, 0, 0)
        self.set_y(start_y + box_height + 1)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", size=10)
        self.multi_cell(_USABLE_W, _LINE_H, text)

    def body_text_indented(self, text: str) -> None:
        """
        Render free text with a left indent and a vertical bar on the left edge.
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
    practice_name: str | None = None,
    photo_bytes: list[bytes] | None = None,
) -> bytes:
    """
    Generate a PDF representation of a clinical submission.
    Returns raw PDF bytes. The caller is responsible for attaching or saving them.
    """
    pdf = _EConsultPDF()
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()

    # --- Document header ---
    pdf.ln(5)
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.set_text_color(*_NHS_BLUE)
    pdf.cell(0, 8, "Online Consultation Form", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

    if practice_name:
        pdf.set_font("Helvetica", size=11)
        pdf.set_text_color(*_NHS_DARK_GREY)
        pdf.cell(0, 6, practice_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # --- Patient details ---
    pd = clinical_output.patient_details
    pdf.section_heading("PATIENT DETAILS")

    # Combined summary line: "Joe Bloggs, Male, 34"
    # Gender and age are always included here — gender is required and age derives
    # from DOB which is always present. The name used here is the registered name;
    # preferred name appears as a separate row below if provided.
    gender_label = _GENDER_LABELS.get(pd.gender, pd.gender) if pd.gender else ""
    age = _age_from_dob(pd.date_of_birth) if pd.date_of_birth else None
    summary_parts = [f"{pd.first_name} {pd.last_name}"]
    if gender_label:
        summary_parts.append(gender_label)
    if age is not None:
        summary_parts.append(str(age))
    pdf.row("Patient:", ", ".join(summary_parts))

    if pd.preferred_name:
        pdf.row("Preferred name:", pd.preferred_name)

    if pd.date_of_birth:
        pdf.row("Date of birth:", _dob_display(pd.date_of_birth))

    pdf.row("Postcode:", pd.postcode or "")

    if pd.nhs_number:
        # Display with standard NHS spacing: 3 digits, space, 3 digits, space, 4 digits
        n = pd.nhs_number
        pdf.row("NHS number:", f"{n[:3]} {n[3:6]} {n[6:]}")

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
        if key in clinical_output.quantity_answers:
            qa = clinical_output.quantity_answers[key]
            formatted = _format_quantity_answer(
                value,
                qa["raw_components"],
                clinical_output.unit_system,
                qa["decimal_places"],
            )
        else:
            formatted = _format_answer(value)
        pdf.row(f"{label}:", formatted)

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

    # --- Session metadata ---
    pdf.section_heading("SESSION DETAILS")
    pdf.row("Condition:", condition_label)
    pdf.row("Submission ID:", submission_id)
    pdf.row("Submitted at:", submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC"), draw_separator=False)

    return bytes(pdf.output())
