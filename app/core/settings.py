"""
Centralised environment variable settings for the web service.

Imported directly by main.py (load_web_settings), whose return value is
then passed into app/core/wiring.py to construct the AppContainer.

Design rules:

- All requiredness and cross-field rules formerly enforced inline in
  main.py (_require_env, _validate_email_config, _validate_mesh_delivery,
  since removed) are enforced here with the SAME operator-facing error
  messages. Startup error text must not regress.

- Empty or whitespace-only environment variables are treated as unset,
  matching the truthiness semantics of the original os.environ.get checks.
  The single exception is MESH_DELIVERY, which is compared exactly and
  unstripped, matching the original code (a value of " 0" must be rejected
  with its repr shown, not silently accepted).

- EmailSettings.delivery_mode is the single definition of which email path
  is configured. Consequence
  (deliberate, decided 2026-06): a partial Mailgun configuration (one of
  the pair set, not both) falls through to SMTP with a logged warning if
  SMTP is complete, or aborts startup if it is not. When both
  configurations are complete, Mailgun wins. The underlying boolean logic
  (complete / partial / mode selection) now lives in the leaf module
  app/core/email_mode.py, also consumed directly by worker_main.py, so the
  web and the delivery worker cannot drift apart on this predicate again.
  EmailSettings still owns blank-vs-unset normalisation for its own fields
  via the field_validator below; email_mode.py re-implements that same
  normalisation internally so it works correctly when worker_main.py calls
  it with raw os.environ values that have not been pre-normalised.

- Validators raise ValueError (per the pydantic contract). load_web_settings
  converts the resulting ValidationError into a RuntimeError whose message
  is the bare validator text, with pydantic's "Value error, " boilerplate
  stripped, so operators see clean messages. Note that pydantic's
  ValidationError is itself a ValueError subclass, so nested settings
  construction goes through _construct_clean to prevent doubled
  boilerplate when an inner model fails inside an outer validator.

DATABASE-DEPENDENT startup checks (practice exists, single tenant, practice
email present, admin user exists) are NOT here. They require repositories
and live in app/core/wiring.py (run_deployment_checks), called from
build_container after this module's checks pass.
"""

import logging
import os

from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import email_mode

logger = logging.getLogger(__name__)

# Project root: app/core/settings.py -> app/core -> app -> root.
# Matches main.py's _PROJECT_ROOT (the directory containing main.py).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_VALUE_ERROR_PREFIX = "Value error, "


def _blank_to_none(value: object) -> object:
    """Treat empty / whitespace-only env vars as unset (legacy truthiness)."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _clean_messages(exc: ValidationError) -> str:
    """Extract bare validator message text from a ValidationError."""
    messages = []
    for err in exc.errors():
        msg = err.get("msg", "")
        if msg.startswith(_VALUE_ERROR_PREFIX):
            msg = msg[len(_VALUE_ERROR_PREFIX) :]
        messages.append(msg)
    return "\n".join(messages)


def _construct_clean[T: BaseSettings](settings_cls: type[T]) -> T:
    """
    Construct a settings model, converting ValidationError into a plain
    ValueError carrying only the clean message text.

    Needed because pydantic's ValidationError subclasses ValueError: if a
    nested model raised ValidationError directly inside an outer model's
    validator, pydantic would wrap the full multi-line error dump as the
    outer message, doubling the boilerplate.
    """
    try:
        return settings_cls()
    except ValidationError as exc:
        raise ValueError(_clean_messages(exc)) from exc


# ---------------------------------------------------------------------------
# Email settings
# ---------------------------------------------------------------------------


class EmailSettings(BaseSettings):
    """
    Email delivery configuration.

    A complete configuration must be present:
      - Mailgun HTTP: MAILGUN_API_KEY + MAILGUN_DOMAIN (+ MAILGUN_SIGNING_KEY)
      - SMTP:         SMTP_HOST + SMTP_USER + SMTP_PASSWORD
    EMAIL_FROM is required in both cases.
    """

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    EMAIL_FROM: str | None = None

    MAILGUN_API_KEY: str | None = None
    MAILGUN_DOMAIN: str | None = None
    MAILGUN_SIGNING_KEY: str | None = None

    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None

    @field_validator(
        "EMAIL_FROM",
        "MAILGUN_API_KEY",
        "MAILGUN_DOMAIN",
        "MAILGUN_SIGNING_KEY",
        "SMTP_HOST",
        "SMTP_USER",
        "SMTP_PASSWORD",
        mode="before",
    )
    @classmethod
    def _normalise_blank(cls, value: object) -> object:
        return _blank_to_none(value)

    # --- Derived predicates -------------------------------------------------

    @property
    def has_complete_mailgun(self) -> bool:
        return email_mode.has_complete_mailgun(self.MAILGUN_API_KEY, self.MAILGUN_DOMAIN)

    @property
    def has_complete_smtp(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)

    @property
    def has_partial_mailgun(self) -> bool:
        """One of the Mailgun pair is set, but not both."""
        return email_mode.has_partial_mailgun(self.MAILGUN_API_KEY, self.MAILGUN_DOMAIN)

    @property
    def delivery_mode(self) -> str:
        """
        The single definition of which email path is configured.

        Returns "mailgun" only for a COMPLETE Mailgun configuration;
        otherwise "smtp". Validation guarantees that whichever mode this
        returns is complete by the time the model is constructed.
        """
        return email_mode.select_email_delivery_mode(self.MAILGUN_API_KEY, self.MAILGUN_DOMAIN)

    # --- Cross-field rules --------------------------------------------------

    @model_validator(mode="after")
    def _validate_email_config(self) -> "EmailSettings":
        if not self.EMAIL_FROM:
            raise ValueError(
                "Required environment variable not set: EMAIL_FROM. "
                "Set this to the sender address for outgoing emails."
            )

        if not self.has_complete_mailgun and not self.has_complete_smtp:
            raise ValueError(
                "No email delivery configuration found. "
                "Set either MAILGUN_API_KEY + MAILGUN_DOMAIN (Mailgun HTTP) "
                "or SMTP_HOST + SMTP_USER + SMTP_PASSWORD (SMTP)."
            )

        if self.delivery_mode == "mailgun" and not self.MAILGUN_SIGNING_KEY:
            raise ValueError(
                "Required environment variable not set: MAILGUN_SIGNING_KEY. "
                "Set this to the Mailgun webhook signing key to enable webhook "
                "signature verification."
            )

        if self.has_partial_mailgun:
            # Deliberate fall-through to SMTP, but never silently: a typo in
            # MAILGUN_DOMAIN must not invisibly demote a deployment to SMTP.
            logger.warning(
                "Partial Mailgun configuration detected (one of MAILGUN_API_KEY / "
                "MAILGUN_DOMAIN is set, but not both). Falling through to SMTP "
                "delivery. If Mailgun was intended, set both variables."
            )

        return self


# ---------------------------------------------------------------------------
# MESH settings
# ---------------------------------------------------------------------------


class MeshSettings(BaseSettings):
    """
    MESH delivery mode flag.

    Must be present and exactly "0" or "1". No defaulting is permitted --
    a deployment that has not made an explicit choice must abort, per the
    Fail-Fast Configuration project invariant.
    """

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    # No blank-normalisation and no stripping: the original code compared
    # the raw value exactly and reported its repr on mismatch.
    MESH_DELIVERY: str | None = None

    @model_validator(mode="after")
    def _validate_mesh_delivery(self) -> "MeshSettings":
        value = self.MESH_DELIVERY
        if value is None:
            raise ValueError(
                "Required environment variable not set: MESH_DELIVERY. "
                "Must be exactly '0' or '1'. No default is permitted."
            )
        if value not in ("0", "1"):
            raise ValueError(
                f"MESH_DELIVERY must be exactly '0' or '1', got: {value!r}. "
                "No other values (including truthy strings) are accepted."
            )
        if value == "1":
            raise ValueError(
                "MESH_DELIVERY=1 is not yet supported. Phase 1a only "
                "implements the email path. Set MESH_DELIVERY=0."
            )
        return self


# ---------------------------------------------------------------------------
# Web service settings (composition root)
# ---------------------------------------------------------------------------


class WebSettings(BaseSettings):
    """
    Complete environment configuration for the web service process.

    Composes EmailSettings and MeshSettings. Constructing this class
    performs every environment-variable startup check that does not
    require a database connection.

    The nested email and mesh models may be passed explicitly (tests do
    this); when omitted, they are constructed from the environment inside
    the model validator.

    Note on error ordering: this validator checks scalars first, then
    constructs the nested models, so a missing DATABASE_URL is reported
    before a missing EMAIL_FROM. Errors are reported one at a time, as
    before, and all message text is identical to the legacy checks.
    """

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    PRACTICE_ID: str | None = None
    ALLOWED_ADMIN_DOMAINS: str | None = None
    DATABASE_URL: str | None = None
    DATA_DIR: str | None = None

    email: EmailSettings | None = None
    mesh: MeshSettings | None = None

    @field_validator(
        "PRACTICE_ID",
        "ALLOWED_ADMIN_DOMAINS",
        "DATABASE_URL",
        "DATA_DIR",
        mode="before",
    )
    @classmethod
    def _normalise_blank(cls, value: object) -> object:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _validate_required(self) -> "WebSettings":
        if not self.DATABASE_URL:
            raise ValueError("Required environment variable not set: DATABASE_URL")
        if not self.PRACTICE_ID:
            raise ValueError("Required environment variable not set: PRACTICE_ID")
        if not self.ALLOWED_ADMIN_DOMAINS:
            raise ValueError(
                "Required environment variable not set: ALLOWED_ADMIN_DOMAINS. "
                "Set this to a comma-separated list of permitted admin email domains "
                "(e.g. 'nhs.net,gov.uk')."
            )

        if self.email is None:
            self.email = _construct_clean(EmailSettings)
        if self.mesh is None:
            self.mesh = _construct_clean(MeshSettings)

        return self

    @property
    def data_dir(self) -> str:
        """DATA_DIR if set, otherwise <project root>/data (legacy default)."""
        return self.DATA_DIR or os.path.join(_PROJECT_ROOT, "data")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_web_settings() -> WebSettings:
    """
    Load and validate all web-service environment settings.

    Converts pydantic's ValidationError into a RuntimeError carrying only
    the validator message text, preserving the operator-facing error
    quality of the original main.py checks. RuntimeError is what the
    deployment dry-run (python -c "from main import app") and Railway
    logs have always shown for configuration failures.
    """
    try:
        return WebSettings()
    except ValidationError as exc:
        raise RuntimeError(_clean_messages(exc)) from exc
