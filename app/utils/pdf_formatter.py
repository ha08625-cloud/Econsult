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
    pdf = _EConsultPDF()
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()

    # --- Document header (NHS Styled) ---
    pdf.ln(5) # Push down to accommodate the top accent bar
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.set_text_color(*_NHS_BLUE)
    pdf.cell(0, 8, "Online Consultation Form", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

    if practice_name:
        pdf.set_font("Helvetica", size=11)
        pdf.set_text_color(*_NHS_DARK_GREY)
        pdf.cell(0, 6, practice_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

    pdf.set_text_color(0, 0, 0) # Reset to black
    pdf.ln(4)

    # Note: SUBMISSION DETAILS section was removed from here and moved to the end.

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

    # --- Submission metadata (MOVED TO END) ---
    pdf.section_heading("SESSION DETAILS")
    pdf.row("Condition:", condition_label)
    pdf.row("Submission ID:", submission_id)
    pdf.row("Submitted at:", submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC"), draw_separator=False)

    return bytes(pdf.output())
