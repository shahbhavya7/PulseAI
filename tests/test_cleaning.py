"""Edge cases: boilerplate stripping, PII redaction, language, hashing.

Covers services/cleaning.py.
"""

from __future__ import annotations

from uuid import UUID

from app.services.cleaning import (
    CARD_TOKEN,
    EMAIL_TOKEN,
    PHONE_TOKEN,
    UNKNOWN_LANGUAGE,
    content_hash,
    detect_language,
    normalise_text,
    redact_pii,
    strip_boilerplate,
)

USER_A = UUID("00000000-0000-0000-0000-0000000000aa")
USER_B = UUID("00000000-0000-0000-0000-0000000000bb")


# ---- boilerplate -----------------------------------------------------------


def test_signature_delimiter_stripped() -> None:
    result = strip_boilerplate("My app keeps crashing on login.\n-- \nJane Doe\nAcme")
    assert result.text == "My app keeps crashing on login."
    assert result.boilerplate_stripped is True


def test_signature_opener_stripped() -> None:
    result = strip_boilerplate("Cannot reset my password.\nBest regards,\nJohn")
    assert result.text == "Cannot reset my password."
    assert result.boilerplate_stripped is True


def test_quoted_reply_block_stripped() -> None:
    text = "Still broken after the update.\nOn Mon, Jan 1, Bob wrote:\n> old\n> more"
    result = strip_boilerplate(text)
    assert result.text == "Still broken after the update."
    assert result.boilerplate_stripped is True


def test_leading_quote_lines_removed() -> None:
    result = strip_boilerplate("> previous\nActual new content here.")
    assert "previous" not in result.text
    assert "Actual new content here." in result.text


def test_no_boilerplate_left_untouched() -> None:
    text = "A clean message with no signature."
    result = strip_boilerplate(text)
    assert result.text == text
    assert result.boilerplate_stripped is False


# ---- PII redaction ---------------------------------------------------------


def test_email_redacted() -> None:
    result = redact_pii("Contact me at john.doe@example.com please")
    assert EMAIL_TOKEN in result.text and "john.doe@example.com" not in result.text
    assert result.redacted is True


def test_luhn_valid_card_redacted() -> None:
    result = redact_pii("My card is 4111 1111 1111 1111 thanks")
    assert CARD_TOKEN in result.text and "4111" not in result.text


def test_non_luhn_digits_not_treated_as_card() -> None:
    result = redact_pii("order number 1234567812345670000")
    assert CARD_TOKEN not in result.text


def test_phone_redacted() -> None:
    result = redact_pii("call +1 (555) 123-4567 tomorrow")
    assert PHONE_TOKEN in result.text and "555" not in result.text


def test_email_not_misread_as_phone() -> None:
    result = redact_pii("write to a1@b.com only")
    assert EMAIL_TOKEN in result.text and PHONE_TOKEN not in result.text


def test_clean_text_reports_no_redaction() -> None:
    assert redact_pii("just a normal sentence").redacted is False


# ---- language --------------------------------------------------------------


def test_english_detected() -> None:
    assert detect_language("The application crashes every time I open it.") == "en"


def test_spanish_detected() -> None:
    assert detect_language("Tengo un problema con mi factura del mes pasado.") == "es"


def test_short_text_is_unknown_language() -> None:
    assert detect_language("hi") == UNKNOWN_LANGUAGE


# ---- normalise + hash ------------------------------------------------------


def test_normalise_collapses_whitespace_and_lowercases() -> None:
    assert normalise_text("  Hello   WORLD\n\tfoo ") == "hello world foo"


def test_same_text_same_user_same_hash() -> None:
    a = content_hash(USER_A, normalise_text("Duplicate issue"))
    b = content_hash(USER_A, normalise_text("duplicate   issue"))
    assert a == b


def test_same_text_different_user_different_hash() -> None:
    a = content_hash(USER_A, normalise_text("same words"))
    b = content_hash(USER_B, normalise_text("same words"))
    assert a != b
