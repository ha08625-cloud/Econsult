"""
Unit tests for request_validation.py and delivery_service formatting helpers.

Two sections:
1. validate_patient_details — all validation paths including DOB numeric
   checks, calendar date assembly, future date rejection, postcode format,
   and submitter field conditionals.
2. _format_patient_details — email body formatting for patient details block,
   including ISO date conversion, submitter line conditional, and postcode
   uppercasing.

These are pure unit tests. No database, no HTTP, no app startup required.

Run from project root:
    python -m pytest tests/test_request_validation.py -v
"""

import unittest
from datetime import date

from app.core.request_validation import validate_patient_details
from app.core.errors import APIError
from app.models.serialisation_contracts import PatientDetails
from app.services.delivery_service import _format_patient_details


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

    def test_me_with_null_submitter_fields_passes(self):
        # submitter fields are present but null — this is valid for patient_for="me"
        validate_patient_details(_valid_pd(submitter_name=None, submitter_relationship=None))

    def test_me_with_submitter_name_populated_passes(self):
        # For patient_for="me", submitter fields are ignored even if populated
        validate_patient_details(_valid_pd(submitter_name="Someone", submitter_relationship="carer"))


# ---------------------------------------------------------------------------
# Section 2: _format_patient_details
# ---------------------------------------------------------------------------

class TestFormatPatientDetails(unittest.TestCase):
    """
    Tests for _format_patient_details in delivery_service.py.

    The function returns a list of strings forming a labelled block:
      [0] ""                          (blank separator line)
      [1] "PATIENT DETAILS"
      [2] "-" * 40
      [3] "  Patient for:  <value>"
      [4] "  Name:         <first> <last>"
      [5] "  Date of birth:<formatted date>"
      [6] "  Postcode:     <UPPERCASED>"
      [7] "  Submitted by: <name>"    (only if submitter_name is set)
      [8] "  Relationship: <value>"   (only if submitter_relationship is set)
    """

    def _make_pd(self, **kwargs) -> PatientDetails:
        defaults = dict(
            patient_for="me",
            first_name="Jane",
            last_name="Smith",
            date_of_birth="1990-03-15",
            postcode="sw1a 1aa",
        )
        defaults.update(kwargs)
        return PatientDetails(**defaults)

    def test_me_produces_seven_lines(self):
        # blank + header + separator + 4 fields = 7 lines, no submitter lines
        lines = _format_patient_details(self._make_pd())
        self.assertEqual(len(lines), 7)

    def test_name_line_format(self):
        lines = _format_patient_details(self._make_pd())
        self.assertIn("Jane Smith", lines[4])

    def test_postcode_is_uppercased(self):
        lines = _format_patient_details(self._make_pd(postcode="sw1a 1aa"))
        self.assertIn("SW1A 1AA", lines[6])

    def test_iso_date_formatted_as_human_readable(self):
        lines = _format_patient_details(self._make_pd(date_of_birth="1990-03-15"))
        self.assertIn("15 March 1990", lines[5])

    def test_single_digit_day_has_no_leading_zero(self):
        # "%-d" strips the leading zero: 5 March, not 05 March
        lines = _format_patient_details(self._make_pd(date_of_birth="1990-03-05"))
        self.assertIn("5 March 1990", lines[5])
        self.assertNotIn("05 March", lines[5])

    def test_someone_else_with_relationship_produces_nine_lines(self):
        # 7 base lines + submitted by + relationship = 9
        pd = self._make_pd(
            patient_for="someone_else",
            submitter_name="John Doe",
            submitter_relationship="father",
        )
        lines = _format_patient_details(pd)
        self.assertEqual(len(lines), 9)
        self.assertIn("John Doe", lines[7])
        self.assertIn("father", lines[8])

    def test_someone_else_without_relationship_produces_eight_lines(self):
        # 7 base lines + submitted by = 8, no relationship line
        pd = self._make_pd(
            patient_for="someone_else",
            submitter_name="John Doe",
            submitter_relationship=None,
        )
        lines = _format_patient_details(pd)
        self.assertEqual(len(lines), 8)
        self.assertIn("John Doe", lines[7])

    def test_someone_else_without_submitter_name_produces_seven_lines(self):
        # submitter_name absent — neither submitted by nor relationship line added
        pd = self._make_pd(
            patient_for="someone_else",
            submitter_name=None,
            submitter_relationship="mother",
        )
        lines = _format_patient_details(pd)
        self.assertEqual(len(lines), 7)

    def test_different_months_format_correctly(self):
        cases = [
            ("1990-01-01", "1 January 1990"),
            ("1990-06-15", "15 June 1990"),
            ("1990-12-31", "31 December 1990"),
        ]
        for iso, expected in cases:
            with self.subTest(iso=iso):
                lines = _format_patient_details(self._make_pd(date_of_birth=iso))
                self.assertIn(expected, lines[5])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
