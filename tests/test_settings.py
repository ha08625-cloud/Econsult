"""
Unit tests for app/core/settings.py.

Pure unit tests: no database, no integration marker. They exercise the
real environment-sourcing path via monkeypatch rather than constructor
keyword arguments, so the pydantic-settings env plumbing is covered.

Every test starts from a fully cleared environment (see _clean_env) and
sets only the variables it needs. Without this, real environment variables
on a developer machine or in CI would leak into missing-variable test
cases and make them flaky.
"""

import logging

import pytest

from app.core.settings import (
    EmailSettings,
    MeshSettings,
    WebSettings,
    load_web_settings,
)

# Every environment variable the settings module reads.
_ALL_VARS = [
    "PRACTICE_ID",
    "ALLOWED_ADMIN_DOMAINS",
    "DATABASE_URL",
    "DATA_DIR",
    "EMAIL_FROM",
    "MAILGUN_API_KEY",
    "MAILGUN_DOMAIN",
    "MAILGUN_SIGNING_KEY",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "MESH_DELIVERY",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove all settings-relevant variables before every test."""
    for name in _ALL_VARS:
        monkeypatch.delenv(name, raising=False)


def _set_smtp(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "noreply@example.nhs.uk")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-pass")


def _set_mailgun(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "noreply@example.nhs.uk")
    monkeypatch.setenv("MAILGUN_API_KEY", "key-123")
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setenv("MAILGUN_SIGNING_KEY", "signing-123")


def _set_web_scalars(monkeypatch):
    monkeypatch.setenv("PRACTICE_ID", "test_practice")
    monkeypatch.setenv("ALLOWED_ADMIN_DOMAINS", "nhs.net")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("MESH_DELIVERY", "0")


# ---------------------------------------------------------------------------
# EmailSettings: delivery_mode and completeness rules
# ---------------------------------------------------------------------------

def test_complete_smtp_selects_smtp_mode(monkeypatch):
    _set_smtp(monkeypatch)
    settings = EmailSettings()
    assert settings.delivery_mode == "smtp"
    assert settings.has_complete_smtp is True
    assert settings.has_complete_mailgun is False


def test_complete_mailgun_selects_mailgun_mode(monkeypatch):
    _set_mailgun(monkeypatch)
    settings = EmailSettings()
    assert settings.delivery_mode == "mailgun"


def test_mailgun_takes_precedence_when_both_complete(monkeypatch):
    _set_smtp(monkeypatch)
    _set_mailgun(monkeypatch)
    settings = EmailSettings()
    assert settings.delivery_mode == "mailgun"


def test_partial_mailgun_with_complete_smtp_falls_through(monkeypatch):
    # MAILGUN_API_KEY without MAILGUN_DOMAIN: the legacy service-selection
    # branch would have chosen Mailgun here (broken at send time). The
    # settings module must select SMTP instead.
    _set_smtp(monkeypatch)
    monkeypatch.setenv("MAILGUN_API_KEY", "key-123")
    settings = EmailSettings()
    assert settings.delivery_mode == "smtp"
    assert settings.has_partial_mailgun is True


def test_partial_mailgun_domain_only_also_falls_through(monkeypatch):
    _set_smtp(monkeypatch)
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.example.com")
    settings = EmailSettings()
    assert settings.delivery_mode == "smtp"


def test_partial_mailgun_fall_through_logs_warning(monkeypatch, caplog):
    _set_smtp(monkeypatch)
    monkeypatch.setenv("MAILGUN_API_KEY", "key-123")
    with caplog.at_level(logging.WARNING, logger="app.core.settings"):
        EmailSettings()
    assert any(
        "Partial Mailgun configuration" in record.message
        for record in caplog.records
    )


def test_partial_mailgun_without_smtp_aborts(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "noreply@example.nhs.uk")
    monkeypatch.setenv("MAILGUN_API_KEY", "key-123")
    with pytest.raises(ValueError, match="No email delivery configuration found"):
        EmailSettings()


def test_no_email_config_at_all_aborts(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "noreply@example.nhs.uk")
    with pytest.raises(ValueError, match="No email delivery configuration found"):
        EmailSettings()


def test_missing_email_from_aborts(monkeypatch):
    _set_smtp(monkeypatch)
    monkeypatch.delenv("EMAIL_FROM")
    with pytest.raises(ValueError, match="EMAIL_FROM"):
        EmailSettings()


def test_empty_email_from_treated_as_missing(monkeypatch):
    # Legacy os.environ.get truthiness: "" counts as unset.
    _set_smtp(monkeypatch)
    monkeypatch.setenv("EMAIL_FROM", "   ")
    with pytest.raises(ValueError, match="EMAIL_FROM"):
        EmailSettings()


def test_complete_mailgun_without_signing_key_aborts(monkeypatch):
    _set_mailgun(monkeypatch)
    monkeypatch.delenv("MAILGUN_SIGNING_KEY")
    with pytest.raises(ValueError, match="MAILGUN_SIGNING_KEY"):
        EmailSettings()


def test_smtp_does_not_require_signing_key(monkeypatch):
    _set_smtp(monkeypatch)
    settings = EmailSettings()
    assert settings.MAILGUN_SIGNING_KEY is None


# ---------------------------------------------------------------------------
# MeshSettings: exact-value rules
# ---------------------------------------------------------------------------

def test_mesh_delivery_zero_accepted(monkeypatch):
    monkeypatch.setenv("MESH_DELIVERY", "0")
    assert MeshSettings().MESH_DELIVERY == "0"


def test_mesh_delivery_missing_aborts():
    with pytest.raises(ValueError, match="Required environment variable not set: MESH_DELIVERY"):
        MeshSettings()


def test_mesh_delivery_one_rejected_in_phase_1a(monkeypatch):
    monkeypatch.setenv("MESH_DELIVERY", "1")
    with pytest.raises(ValueError, match="not yet supported"):
        MeshSettings()


@pytest.mark.parametrize("bad_value", ["true", "2", "yes", "00", " 0", "0 "])
def test_mesh_delivery_rejects_non_exact_values(monkeypatch, bad_value):
    monkeypatch.setenv("MESH_DELIVERY", bad_value)
    with pytest.raises(ValueError, match="must be exactly '0' or '1'"):
        MeshSettings()


# ---------------------------------------------------------------------------
# WebSettings: scalar requiredness and composition
# ---------------------------------------------------------------------------

def test_full_valid_environment_loads(monkeypatch):
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    settings = load_web_settings()
    assert settings.PRACTICE_ID == "test_practice"
    assert settings.email.delivery_mode == "smtp"
    assert settings.mesh.MESH_DELIVERY == "0"


@pytest.mark.parametrize("missing", ["DATABASE_URL", "PRACTICE_ID", "ALLOWED_ADMIN_DOMAINS"])
def test_missing_scalar_aborts_with_named_variable(monkeypatch, missing):
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        load_web_settings()


def test_nested_email_failure_surfaces_through_loader(monkeypatch):
    _set_web_scalars(monkeypatch)
    # No email configuration at all.
    monkeypatch.setenv("EMAIL_FROM", "noreply@example.nhs.uk")
    with pytest.raises(RuntimeError, match="No email delivery configuration found"):
        load_web_settings()


def test_nested_mesh_failure_surfaces_through_loader(monkeypatch):
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    monkeypatch.setenv("MESH_DELIVERY", "true")
    with pytest.raises(RuntimeError, match="must be exactly '0' or '1'"):
        load_web_settings()


def test_loader_error_messages_have_no_pydantic_boilerplate(monkeypatch):
    _set_web_scalars(monkeypatch)
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(RuntimeError) as excinfo:
        load_web_settings()
    text = str(excinfo.value)
    assert "Value error" not in text
    assert "validation error" not in text
    assert text == "Required environment variable not set: DATABASE_URL"


def test_data_dir_default_points_at_project_data(monkeypatch):
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    settings = load_web_settings()
    assert settings.data_dir.endswith("data")
    assert settings.DATA_DIR is None


def test_data_dir_override(monkeypatch):
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    monkeypatch.setenv("DATA_DIR", "/tmp/custom-data")
    settings = load_web_settings()
    assert settings.data_dir == "/tmp/custom-data"


def test_empty_data_dir_falls_back_to_default(monkeypatch):
    # Legacy: os.environ.get("DATA_DIR") or default — "" uses the default.
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    monkeypatch.setenv("DATA_DIR", "")
    settings = load_web_settings()
    assert settings.DATA_DIR is None
    assert settings.data_dir.endswith("data")


def test_explicit_nested_models_accepted_for_tests(monkeypatch):
    # Stage 2's wiring tests will construct WebSettings with pre-built
    # nested models; pin that construction path here.
    _set_web_scalars(monkeypatch)
    _set_smtp(monkeypatch)
    email = EmailSettings()
    mesh = MeshSettings()
    settings = WebSettings(email=email, mesh=mesh)
    assert settings.email is email
    assert settings.mesh is mesh
