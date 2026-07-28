"""
Unit tests for request_validation.py.

Tests validate_patient_details — all validation paths including DOB numeric
checks, calendar date assembly, future date rejection, postcode format,
submitter field conditionals, and the new gender, nhs_number, and
preferred_name fields.

These are pure unit tests. No database, no HTTP, no app startup required.

Run from project root:
    python -m pytest tests/test_request_validation.py -v
"""

import unittest
from datetime import date

from app.core.errors import APIError
from app.core.request_validation import (
    validate_contact_preferences,
    validate_init_payload,
    validate_patient_details,
    validate_update_payload,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_pd(**overrides) -> dict:
    """
    Return a valid patient_details dict for patient_for="me".
    Keyword arguments override individual fields.
    """
    base = {
        "patient_for": "me",
        "first_name": "Jane",
        "last_name": "Smith",
        "date_of_birth": {"day": "15", "month": "3", "year": "1990"},
        "postcode": "SW1A 1AA",
        "gender": "female",
        "preferred_name": None,
        "nhs_number": None,
        "submitter_name": None,
        "submitter_relationship": None,
    }
    base.update(overrides)
    return base


def _valid_someone_else(**overrides) -> dict:
    """Return a valid patient_details dict for patient_for="someone_else"."""
    base = _valid_pd(
        patient_for="someone_else",
        submitter_name="Jane Doe",
        submitter_relationship="mother",
    )
    base.update(overrides)
    return base


def _raises_with(pd: dict, expected_fragment: str):
    """
    Assert that validate_patient_details raises APIError and that the
    message contains expected_fragment.
    """
    try:
        validate_patient_details(pd)
        raise AssertionError(
            f"Expected APIError containing {expected_fragment!r} but no exception was raised"
        )
    except APIError as e:
        assert expected_fragment in e.message, (
            f"Expected {expected_fragment!r} in error message, got: {e.message!r}"
        )


def _valid_cp(**overrides) -> dict:
    """
    Return a valid contact_preferences dict.
    Keyword arguments override individual fields.
    """
    base = {
        "contact_methods": ["email"],
        "email_address": "patient@example.com",
        "phone_number": None,
        "best_time_to_call": None,
        "doctor_preference": "any",
        "usual_doctor_name": None,
        "consultation_outcome": "face_to_face",
    }
    base.update(overrides)
    return base


def _cp_raises_with(cp: dict, expected_fragment: str):
    """
    Assert that validate_contact_preferences raises APIError and that the
    message contains expected_fragment.
    """
    try:
        validate_contact_preferences(cp)
        raise AssertionError(
            f"Expected APIError containing {expected_fragment!r} but no exception was raised"
        )
    except APIError as e:
        assert expected_fragment in e.message, (
            f"Expected {expected_fragment!r} in error message, got: {e.message!r}"
        )


# ---------------------------------------------------------------------------
# Section 1: validate_patient_details
# ---------------------------------------------------------------------------


class TestValidatePatientDetailsHappyPath(unittest.TestCase):
    def test_valid_me_payload_passes(self):
        validate_patient_details(_valid_pd())

    def test_valid_someone_else_payload_passes(self):
        validate_patient_details(_valid_someone_else())

    def test_postcode_without_space_passes(self):
        validate_patient_details(_valid_pd(postcode="SW1A1AA"))

    def test_postcode_lowercase_passes(self):
        # Regex is case-insensitive
        validate_patient_details(_valid_pd(postcode="sw1a 1aa"))

    def test_single_digit_day_and_month_passes(self):
        pd = _valid_pd()
        pd["date_of_birth"] = {"day": "1", "month": "1", "year": "2000"}
        validate_patient_details(pd)

    def test_all_gender_values_pass(self):
        for gender in ("male", "female", "other", "prefer_not_to_say"):
            with self.subTest(gender=gender):
                validate_patient_details(_valid_pd(gender=gender))

    def test_preferred_name_present_passes(self):
        validate_patient_details(_valid_pd(preferred_name="Jo"))

    def test_preferred_name_absent_passes(self):
        # None is acceptable for optional fields
        validate_patient_details(_valid_pd(preferred_name=None))

    def test_nhs_number_ten_digits_no_spaces_passes(self):
        validate_patient_details(_valid_pd(nhs_number="4857773456"))

    def test_nhs_number_absent_passes(self):
        validate_patient_details(_valid_pd(nhs_number=None))


class TestValidatePatientDetailsTopLevel(unittest.TestCase):
    def test_not_a_dict_raises(self):
        try:
            validate_patient_details("not a dict")
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("object", e.message)

    def test_extra_field_raises(self):
        pd = _valid_pd()
        pd["extra_field"] = "sneaky"
        _raises_with(pd, "Illegal")

    def test_missing_first_name_raises(self):
        pd = _valid_pd()
        del pd["first_name"]
        try:
            validate_patient_details(pd)
            self.fail("Expected APIError")
        except APIError:
            pass

    def test_empty_first_name_raises(self):
        _raises_with(_valid_pd(first_name=""), "first_name")

    def test_whitespace_only_first_name_raises(self):
        _raises_with(_valid_pd(first_name="   "), "first_name")

    def test_empty_last_name_raises(self):
        _raises_with(_valid_pd(last_name=""), "last_name")

    def test_invalid_patient_for_raises(self):
        _raises_with(_valid_pd(patient_for="myself"), "patient_for")

    def test_missing_patient_for_raises(self):
        pd = _valid_pd()
        del pd["patient_for"]
        try:
            validate_patient_details(pd)
            self.fail("Expected APIError")
        except APIError:
            pass


class TestValidatePatientDetailsDateOfBirth(unittest.TestCase):
    def _set_dob(self, day=None, month=None, year=None) -> dict:
        pd = _valid_pd()
        dob = {"day": "15", "month": "3", "year": "1990"}
        if day is not None:
            dob["day"] = day
        if month is not None:
            dob["month"] = month
        if year is not None:
            dob["year"] = year
        pd["date_of_birth"] = dob
        return pd

    def test_dob_not_a_dict_raises(self):
        pd = _valid_pd()
        pd["date_of_birth"] = "15/03/1990"
        _raises_with(pd, "object")

    def test_dob_extra_field_raises(self):
        pd = _valid_pd()
        pd["date_of_birth"] = {"day": "15", "month": "3", "year": "1990", "extra": "x"}
        _raises_with(pd, "Illegal")

    def test_dob_non_numeric_day_raises_clear_message(self):
        _raises_with(self._set_dob(day="ab"), "digits only")

    def test_dob_non_numeric_month_raises_clear_message(self):
        _raises_with(self._set_dob(month="xx"), "digits only")

    def test_dob_non_numeric_year_raises_clear_message(self):
        _raises_with(self._set_dob(year="19xx"), "digits only")

    def test_dob_empty_day_raises(self):
        _raises_with(self._set_dob(day=""), "day")

    def test_dob_empty_month_raises(self):
        _raises_with(self._set_dob(month=""), "month")

    def test_dob_empty_year_raises(self):
        _raises_with(self._set_dob(year=""), "year")

    def test_dob_feb_31_raises_invalid_calendar_date(self):
        _raises_with(self._set_dob(day="31", month="2"), "valid calendar date")

    def test_dob_feb_30_raises_invalid_calendar_date(self):
        _raises_with(self._set_dob(day="30", month="2"), "valid calendar date")

    def test_dob_month_13_raises_invalid_calendar_date(self):
        _raises_with(self._set_dob(month="13"), "valid calendar date")

    def test_dob_day_0_raises_invalid_calendar_date(self):
        _raises_with(self._set_dob(day="0"), "valid calendar date")

    def test_dob_future_date_raises(self):
        _raises_with(self._set_dob(year="2099"), "future")

    def test_dob_today_passes(self):
        # Today is not in the future — edge case
        today = date.today()
        pd = _valid_pd()
        pd["date_of_birth"] = {
            "day": str(today.day),
            "month": str(today.month),
            "year": str(today.year),
        }
        validate_patient_details(pd)

    def test_dob_with_leading_zeros_passes(self):
        pd = _valid_pd()
        pd["date_of_birth"] = {"day": "01", "month": "01", "year": "1990"}
        validate_patient_details(pd)


class TestValidatePatientDetailsPostcode(unittest.TestCase):
    def test_invalid_postcode_raises(self):
        _raises_with(_valid_pd(postcode="NOTAPOSTCODE"), "postcode")

    def test_empty_postcode_raises(self):
        _raises_with(_valid_pd(postcode=""), "postcode")

    def test_partial_postcode_raises(self):
        _raises_with(_valid_pd(postcode="SW1A"), "postcode")

    def test_valid_postcode_formats_pass(self):
        # Sample of valid UK postcode formats
        for postcode in ("SW1A 1AA", "M1 1AE", "B1 1BB", "EC1A 1BB", "W1A 0AX"):
            with self.subTest(postcode=postcode):
                validate_patient_details(_valid_pd(postcode=postcode))


class TestValidatePatientDetailsGender(unittest.TestCase):
    def test_missing_gender_raises(self):
        pd = _valid_pd()
        del pd["gender"]
        try:
            validate_patient_details(pd)
            self.fail("Expected APIError")
        except APIError:
            pass

    def test_null_gender_raises(self):
        _raises_with(_valid_pd(gender=None), "gender")

    def test_invalid_gender_string_raises(self):
        _raises_with(_valid_pd(gender="nonbinary"), "gender")

    def test_empty_string_gender_raises(self):
        _raises_with(_valid_pd(gender=""), "gender")


class TestValidatePatientDetailsNhsNumber(unittest.TestCase):
    def test_ten_digit_string_passes(self):
        validate_patient_details(_valid_pd(nhs_number="4857773456"))

    def test_nine_digits_raises(self):
        _raises_with(_valid_pd(nhs_number="485777345"), "nhs_number")

    def test_eleven_digits_raises(self):
        _raises_with(_valid_pd(nhs_number="48577734560"), "nhs_number")

    def test_digits_with_spaces_raises(self):
        # The frontend strips spaces before sending — backend expects no spaces
        _raises_with(_valid_pd(nhs_number="485 777 3456"), "nhs_number")

    def test_non_digit_characters_raises(self):
        _raises_with(_valid_pd(nhs_number="485X773456"), "nhs_number")

    def test_empty_string_raises(self):
        # Empty string is not valid — frontend should send null, not empty string
        _raises_with(_valid_pd(nhs_number=""), "nhs_number")

    def test_null_nhs_number_passes(self):
        validate_patient_details(_valid_pd(nhs_number=None))

    def test_non_string_nhs_number_raises(self):
        _raises_with(_valid_pd(nhs_number=4857773456), "nhs_number")


class TestValidatePatientDetailsPreferredName(unittest.TestCase):
    def test_preferred_name_string_passes(self):
        validate_patient_details(_valid_pd(preferred_name="Jo"))

    def test_preferred_name_null_passes(self):
        validate_patient_details(_valid_pd(preferred_name=None))

    def test_preferred_name_non_string_raises(self):
        _raises_with(_valid_pd(preferred_name=123), "preferred_name")

    def test_preferred_name_too_long_raises(self):
        _raises_with(_valid_pd(preferred_name="A" * 256), "preferred_name")

    def test_preferred_name_at_max_len_passes(self):
        validate_patient_details(_valid_pd(preferred_name="A" * 255))


class TestValidatePatientDetailsSubmitterFields(unittest.TestCase):
    def test_someone_else_missing_submitter_name_raises(self):
        pd = _valid_someone_else(submitter_name=None)
        _raises_with(pd, "submitter_name")

    def test_someone_else_empty_submitter_name_raises(self):
        pd = _valid_someone_else(submitter_name="")
        _raises_with(pd, "submitter_name")

    def test_someone_else_missing_submitter_relationship_raises(self):
        pd = _valid_someone_else(submitter_relationship=None)
        _raises_with(pd, "submitter_relationship")

    def test_someone_else_empty_submitter_relationship_raises(self):
        pd = _valid_someone_else(submitter_relationship="")
        _raises_with(pd, "submitter_relationship")

    def test_someone_else_submitter_name_too_long_raises(self):
        pd = _valid_someone_else(submitter_name="A" * 256)
        _raises_with(pd, "submitter_name")

    def test_someone_else_submitter_relationship_too_long_raises(self):
        pd = _valid_someone_else(submitter_relationship="A" * 256)
        _raises_with(pd, "submitter_relationship")

    def test_someone_else_submitter_fields_at_max_len_passes(self):
        validate_patient_details(
            _valid_someone_else(submitter_name="A" * 255, submitter_relationship="A" * 255)
        )

    def test_me_with_null_submitter_fields_passes(self):
        # submitter fields are present but null — this is valid for patient_for="me"
        validate_patient_details(_valid_pd(submitter_name=None, submitter_relationship=None))

    def test_me_with_submitter_name_populated_passes(self):
        # For patient_for="me", submitter fields are ignored even if populated
        validate_patient_details(
            _valid_pd(submitter_name="Someone", submitter_relationship="carer")
        )


class TestValidatePatientDetailsNameLength(unittest.TestCase):
    def test_first_name_too_long_raises(self):
        _raises_with(_valid_pd(first_name="A" * 256), "first_name")

    def test_first_name_at_max_len_passes(self):
        validate_patient_details(_valid_pd(first_name="A" * 255))

    def test_last_name_too_long_raises(self):
        _raises_with(_valid_pd(last_name="A" * 256), "last_name")

    def test_last_name_at_max_len_passes(self):
        validate_patient_details(_valid_pd(last_name="A" * 255))


# ---------------------------------------------------------------------------
# Section 2: validate_contact_preferences — consultation_outcome
# ---------------------------------------------------------------------------


class TestValidateContactPreferencesOutcomeHappyPath(unittest.TestCase):
    def test_valid_outcome_passes(self):
        validate_contact_preferences(_valid_cp(consultation_outcome="face_to_face"))

    def test_all_valid_outcome_values_pass(self):
        valid_values = [
            "admin_task",
            "face_to_face",
            "phone_appointment",
            "advice_only",
            "medication",
            "not_sure",
        ]
        for value in valid_values:
            with self.subTest(value=value):
                validate_contact_preferences(_valid_cp(consultation_outcome=value))


class TestValidateContactPreferencesOutcomeRejection(unittest.TestCase):
    def test_unknown_outcome_value_raises_422(self):
        _cp_raises_with(
            _valid_cp(consultation_outcome="in_person"),
            "consultation_outcome",
        )

    def test_empty_string_outcome_raises(self):
        _cp_raises_with(
            _valid_cp(consultation_outcome=""),
            "consultation_outcome",
        )

    def test_null_outcome_raises(self):
        _cp_raises_with(
            _valid_cp(consultation_outcome=None),
            "consultation_outcome",
        )

    def test_missing_outcome_field_raises(self):
        cp = _valid_cp()
        del cp["consultation_outcome"]
        try:
            validate_contact_preferences(cp)
            raise AssertionError("Expected APIError but no exception was raised")
        except APIError:
            pass

    def test_extra_field_alongside_outcome_raises(self):
        cp = _valid_cp()
        cp["unexpected"] = "value"
        _cp_raises_with(cp, "Illegal")


# ---------------------------------------------------------------------------
# Section 3: validate_contact_preferences — usual_doctor_name, email_address,
# phone_number type/length guards
# ---------------------------------------------------------------------------


class TestValidateContactPreferencesFreeTextFieldGuards(unittest.TestCase):
    def test_usual_doctor_name_dict_raises(self):
        _cp_raises_with(
            _valid_cp(doctor_preference="usual", usual_doctor_name={"nested": "object"}),
            "usual_doctor_name",
        )

    def test_usual_doctor_name_too_long_raises(self):
        _cp_raises_with(
            _valid_cp(doctor_preference="usual", usual_doctor_name="A" * 256),
            "usual_doctor_name",
        )

    def test_usual_doctor_name_at_max_len_passes(self):
        validate_contact_preferences(
            _valid_cp(doctor_preference="usual", usual_doctor_name="A" * 255)
        )

    def test_email_address_dict_raises(self):
        _cp_raises_with(
            _valid_cp(contact_methods=["email"], email_address={"nested": "object"}),
            "email_address",
        )

    def test_email_address_too_long_raises(self):
        _cp_raises_with(
            _valid_cp(contact_methods=["email"], email_address="a" * 256 + "@example.com"),
            "email_address",
        )

    def test_phone_number_dict_raises(self):
        _cp_raises_with(
            _valid_cp(contact_methods=["phone"], phone_number={"nested": "object"}),
            "phone_number",
        )

    def test_phone_number_too_long_raises(self):
        _cp_raises_with(
            _valid_cp(contact_methods=["phone"], phone_number="1" * 101),
            "phone_number",
        )

    def test_phone_number_at_max_len_passes(self):
        validate_contact_preferences(_valid_cp(contact_methods=["phone"], phone_number="1" * 100))

    def test_best_time_to_call_dict_raises(self):
        _cp_raises_with(
            _valid_cp(best_time_to_call={"nested": "object"}),
            "best_time_to_call",
        )

    def test_best_time_to_call_too_long_raises(self):
        _cp_raises_with(
            _valid_cp(best_time_to_call="A" * 256),
            "best_time_to_call",
        )

    def test_best_time_to_call_at_max_len_passes(self):
        validate_contact_preferences(_valid_cp(best_time_to_call="A" * 255))


# ---------------------------------------------------------------------------
# Section 4: validate_init_payload
# ---------------------------------------------------------------------------


class TestValidateInitPayload(unittest.TestCase):
    def test_valid_payload_with_free_text_passes(self):
        validate_init_payload({"condition_id": "uti1", "free_text": "Burning sensation"})

    def test_valid_payload_with_null_free_text_passes(self):
        validate_init_payload({"condition_id": "uti1", "free_text": None})

    def test_non_string_condition_id_raises(self):
        try:
            validate_init_payload({"condition_id": 123, "free_text": None})
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("condition_id", e.message)

    def test_extra_field_raises(self):
        try:
            validate_init_payload({"condition_id": "uti1", "free_text": None, "extra": "sneaky"})
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("Illegal", e.message)

    def test_free_text_object_raises(self):
        # Regression: validate_init_payload previously never checked the type
        # of free_text at all, so a JSON object or number passed validation
        # and could reach the encoder/PDF pipeline as a non-string value.
        try:
            validate_init_payload({"condition_id": "uti1", "free_text": {"nested": "object"}})
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("free_text", e.message)

    def test_free_text_number_raises(self):
        try:
            validate_init_payload({"condition_id": "uti1", "free_text": 12345})
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("free_text", e.message)

    def test_free_text_too_long_raises(self):
        try:
            validate_init_payload({"condition_id": "uti1", "free_text": "A" * 5001})
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("free_text", e.message)

    def test_free_text_at_max_len_passes(self):
        validate_init_payload({"condition_id": "uti1", "free_text": "A" * 5000})


# ---------------------------------------------------------------------------
# Section 5: validate_update_payload
# ---------------------------------------------------------------------------


class TestValidateUpdatePayload(unittest.TestCase):
    def _valid_update(self, **overrides) -> dict:
        base = {
            "runtime_id": "abc-123",
            "base_version": 1,
            "answers": {"some_key": "some_value"},
            "additional_text": None,
        }
        base.update(overrides)
        return base

    def test_valid_payload_passes(self):
        validate_update_payload(self._valid_update())

    def test_additional_text_object_raises(self):
        try:
            validate_update_payload(self._valid_update(additional_text={"nested": "object"}))
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("additional_text", e.message)

    def test_additional_text_too_long_raises(self):
        try:
            validate_update_payload(self._valid_update(additional_text="A" * 5001))
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("additional_text", e.message)

    def test_additional_text_at_max_len_passes(self):
        validate_update_payload(self._valid_update(additional_text="A" * 5000))

    def test_empty_answers_raises(self):
        try:
            validate_update_payload(self._valid_update(answers={}))
            self.fail("Expected APIError")
        except APIError as e:
            self.assertIn("answers", e.message)
