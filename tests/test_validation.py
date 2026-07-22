"""Edge cases: decoding, CSV file-level checks, content-quality classification.

Covers services/validation.py.
"""

from __future__ import annotations

import pytest

from app.models.enums import IssueFlag
from app.services.validation import (
    MissingTextColumnError,
    UndecodableFileError,
    classify_content,
    decode_bytes,
    find_text_column,
    is_blank,
)

# ---- decoding / encoding auto-repair ---------------------------------------


def test_utf8_is_fast_path_not_recovered() -> None:
    result = decode_bytes("Olá, mundo".encode())
    assert result.text == "Olá, mundo"
    assert result.encoding == "utf-8" and result.recovered is False


def test_latin1_is_auto_repaired() -> None:
    result = decode_bytes("café résumé señor".encode("latin-1"))
    assert "café" in result.text and result.recovered is True


def test_utf16_bom_decoded() -> None:
    result = decode_bytes("hello world".encode("utf-16"))  # includes BOM
    assert result.text == "hello world" and result.recovered is True


def test_empty_bytes_decode_to_empty_string() -> None:
    result = decode_bytes(b"")
    assert result.text == "" and result.recovered is False


def test_binary_data_asks_for_utf8() -> None:
    # NUL bytes → binary/mojibake → rejected with a UTF-8 remedy.
    with pytest.raises(UndecodableFileError) as exc:
        decode_bytes(b"\x00\x81\x8d\x8f\x90\x9d" * 3)
    assert "UTF-8" in exc.value.message


# ---- CSV file-level checks -------------------------------------------------


def test_named_text_column_is_found() -> None:
    assert find_text_column(["id", "body", "created"]) == "body"


def test_case_insensitive_match() -> None:
    assert find_text_column(["ID", "Message"]) == "Message"


def test_single_column_used_implicitly() -> None:
    assert find_text_column(["whatever"]) == "whatever"


def test_missing_text_column_raises_named_error() -> None:
    with pytest.raises(MissingTextColumnError) as exc:
        find_text_column(["id", "created_at", "priority"])
    assert "text" in exc.value.message and "priority" in exc.value.message


@pytest.mark.parametrize("value", [None, "", "   ", "\t", "nan", "NaN"])
def test_blank_values_detected(value: object) -> None:
    assert is_blank(value) is True


@pytest.mark.parametrize("value", ["hello", " x ", "0", "not blank"])
def test_non_blank_values(value: str) -> None:
    assert is_blank(value) is False


# ---- per-item content quality ----------------------------------------------


def test_empty_content_is_junk_zero_confidence() -> None:
    verdict = classify_content("   ")
    assert verdict.is_junk is True and verdict.confidence == 0.0
    assert IssueFlag.JUNK.value in verdict.flags


def test_one_word_flagged() -> None:
    verdict = classify_content("broken")
    assert verdict.is_junk is True and IssueFlag.ONE_WORD.value in verdict.flags


def test_symbols_only_is_junk() -> None:
    verdict = classify_content("!!!! ???? @@@@ ####")
    assert verdict.is_junk is True and IssueFlag.JUNK.value in verdict.flags


def test_substantive_text_not_junk() -> None:
    verdict = classify_content("The checkout page throws a 500 error on submit.")
    assert verdict.is_junk is False and verdict.confidence > 0.5 and verdict.flags == []
