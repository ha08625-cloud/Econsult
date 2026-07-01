"""
Unit tests for app/core/upload_constants.py.

Verifies that the module loads the JSON file correctly and exposes the
expected named constants with the correct types and values.

No database required. Run with: make test
"""

import app.core.upload_constants as uc


def test_allowed_mime_types_is_list_of_strings():
    assert isinstance(uc.ALLOWED_MIME_TYPES, list)
    assert all(isinstance(t, str) for t in uc.ALLOWED_MIME_TYPES)


def test_allowed_mime_types_contains_expected_values():
    assert "image/jpeg" in uc.ALLOWED_MIME_TYPES
    assert "image/png" in uc.ALLOWED_MIME_TYPES


def test_max_file_size_bytes_is_5mb():
    assert isinstance(uc.MAX_FILE_SIZE_BYTES, int)
    assert uc.MAX_FILE_SIZE_BYTES == 5 * 1024 * 1024


def test_max_total_size_bytes_is_10mb():
    assert isinstance(uc.MAX_TOTAL_SIZE_BYTES, int)
    assert uc.MAX_TOTAL_SIZE_BYTES == 10 * 1024 * 1024


def test_max_file_count_is_5():
    assert isinstance(uc.MAX_FILE_COUNT, int)
    assert uc.MAX_FILE_COUNT == 5


def test_total_size_is_greater_than_single_file_limit():
    # Sanity check: the total cap must always exceed the per-file cap,
    # otherwise no submission could ever succeed.
    assert uc.MAX_TOTAL_SIZE_BYTES > uc.MAX_FILE_SIZE_BYTES
