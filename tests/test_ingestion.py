"""Edge cases: parsers, file dispatch, boundary detection, and the pipeline.

Covers the non-DB parts of services/ingestion.py.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from app.models.enums import IssueFlag
from app.schemas.upload import SkipReason
from app.services import ingestion
from app.services.ingestion import (
    EmptyFileError,
    MissingTextColumnError,
    ParsedRecord,
    ParseResult,
    detect_boundaries,
    parse_csv,
    parse_file,
    parse_pdf,
    parse_text,
    run_pipeline,
)

USER = UUID("00000000-0000-0000-0000-0000000000cc")


# ===========================================================================
# Parsing
# ===========================================================================


def test_parse_csv_rows_and_skips_blanks() -> None:
    result = parse_csv(b"text\nfirst issue\n\nsecond issue\n   \n")
    assert result.parser == "csv" and result.splittable is False
    assert [r.text for r in result.records] == ["first issue", "second issue"]
    assert result.blank_skipped == 2
    assert result.records[0].source_ref == "row 2"


def test_parse_csv_missing_text_column_raises() -> None:
    with pytest.raises(MissingTextColumnError):
        parse_csv(b"id,priority\n1,high\n")


def test_parse_csv_empty_file_raises() -> None:
    with pytest.raises(EmptyFileError):
        parse_csv(b"")


def test_parse_csv_latin1_recovered_and_flagged() -> None:
    result = parse_csv("text\ncafé problem\n".encode("latin-1"))
    assert result.records[0].flags == [IssueFlag.ENCODING_RECOVERED.value]
    assert "café" in result.records[0].text


def test_parse_text_reads_document() -> None:
    result = parse_text(b"just some feedback text")
    assert result.parser == "text" and result.splittable is True
    assert result.records[0].text == "just some feedback text"


def test_parse_file_dispatch() -> None:
    assert parse_file("a.csv", None, b"text\nhi\n").parser == "csv"
    assert parse_file("notes.txt", None, b"hello").parser == "text"
    assert parse_file("unknown.xyz", None, b"fallback text").parser == "text"
    assert parse_file("x", "text/csv", b"text\nhi\n").parser == "csv"


# ---- PDF (pdfplumber mocked to avoid binary fixtures) ----------------------


class _FakePage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> _FakePdf:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _patch_pdf(monkeypatch: pytest.MonkeyPatch, pages: list[str | None]) -> None:
    fake = _FakePdf([_FakePage(p) for p in pages])
    monkeypatch.setattr(ingestion.pdfplumber, "open", lambda _stream: fake)


def test_parse_pdf_with_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pdf(monkeypatch, ["Page one problem.", "Page two detail."])
    result = parse_pdf(b"%PDF-fake")
    assert result.records[0].text == "Page one problem.\nPage two detail."
    assert result.records[0].needs_manual_review is False


def test_scanned_pdf_flagged_needs_manual_review(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pdf(monkeypatch, [None, ""])
    record = parse_pdf(b"%PDF-fake").records[0]
    assert record.needs_manual_review is True
    assert IssueFlag.SCANNED_PDF.value in record.flags


# ===========================================================================
# Boundary detection
# ===========================================================================


def test_single_message_stays_one_segment() -> None:
    result = detect_boundaries("Just one customer complaint about billing.")
    assert result.segments == ["Just one customer complaint about billing."]
    assert result.needs_manual_split is False


def test_split_on_from_headers() -> None:
    blob = "From: alice@x.com\nMy order never arrived.\nFrom: bob@y.com\nDouble charged."
    result = detect_boundaries(blob)
    assert len(result.segments) == 2 and result.needs_manual_split is False
    assert "alice" in result.segments[0] and "bob" in result.segments[1]


def test_split_on_original_message_marker() -> None:
    blob = "Refund request.\n-----Original Message-----\nOlder shipping request."
    result = detect_boundaries(blob)
    assert len(result.segments) == 2 and result.needs_manual_split is False


def test_split_on_double_blank_line() -> None:
    blob = "Customer one has a login problem.\n\n\nCustomer two cannot pay."
    result = detect_boundaries(blob)
    assert len(result.segments) == 2


def test_single_blank_line_does_not_oversplit() -> None:
    blob = "I have a problem.\n\nIt started yesterday and is still happening."
    assert len(detect_boundaries(blob).segments) == 1


def test_ambiguous_thread_flags_needs_manual_split_not_merged() -> None:
    blob = (
        "From: alice@x.com\nPlease see below.\n"
        "On Mon, Jan 1, Bob wrote:\nFrom: bob@y.com\nOriginal question here."
    )
    result = detect_boundaries(blob)
    assert result.needs_manual_split is True
    assert len(result.segments) == 1
    assert "alice" in result.segments[0] and "bob" in result.segments[0]


def test_empty_blob_has_no_segments() -> None:
    result = detect_boundaries("   \n  ")
    assert result.segments == [] and result.needs_manual_split is False


# ===========================================================================
# Pipeline
# ===========================================================================


def _csv_result(*texts: str) -> ParseResult:
    records = [ParsedRecord(text=t, source_ref=f"row {i + 2}") for i, t in enumerate(texts)]
    return ParseResult(parser="csv", records=records, splittable=False)


def _text_result(text: str, **kw: Any) -> ParseResult:
    return ParseResult(
        parser="text",
        records=[ParsedRecord(text=text, source_ref="document", **kw)],
        splittable=True,
    )


def test_normal_rows_are_prepared() -> None:
    result = run_pipeline(_csv_result("App crashes on login.", "Payment fails."), user_id=USER)
    assert len(result.prepared) == 2 and result.skipped == []


def test_intra_file_duplicates_are_skipped() -> None:
    result = run_pipeline(
        _csv_result("Same complaint text", "same   complaint   text"), user_id=USER
    )
    assert len(result.prepared) == 1
    assert [s.reason for s in result.skipped] == [SkipReason.DUPLICATE.value]


def test_cross_upload_duplicate_via_existing_hashes() -> None:
    first = run_pipeline(_csv_result("A brand new issue about sync"), user_id=USER)
    existing = {first.prepared[0].content_hash}
    second = run_pipeline(
        _csv_result("A brand new issue about sync"), user_id=USER, existing_hashes=existing
    )
    assert second.prepared == []
    assert second.skipped[0].reason == SkipReason.DUPLICATE.value


def test_empty_after_cleaning_is_skipped() -> None:
    result = run_pipeline(_csv_result("> only quoted content\n> nothing else"), user_id=USER)
    assert result.prepared == []
    assert result.skipped[0].reason == SkipReason.EMPTY_AFTER_CLEAN.value


def test_pii_and_boilerplate_flags_propagate() -> None:
    text = "Charge me at john@example.com for the order.\nBest regards,\nJohn"
    item = run_pipeline(_csv_result(text), user_id=USER).prepared[0]
    assert IssueFlag.PII_REDACTED.value in item.flags
    assert IssueFlag.BOILERPLATE_STRIPPED.value in item.flags
    assert "john@example.com" not in item.stored_text


def test_one_word_row_created_but_flagged() -> None:
    item = run_pipeline(_csv_result("broken"), user_id=USER).prepared[0]
    assert IssueFlag.ONE_WORD.value in item.flags and item.needs_manual_review is True


def test_text_blob_splits_into_multiple_items() -> None:
    blob = "From: a@x.com\nOrder missing.\nFrom: b@y.com\nWrong item shipped."
    assert len(run_pipeline(_text_result(blob), user_id=USER).prepared) == 2


def test_needs_manual_split_marks_single_flagged_item() -> None:
    blob = "From: a@x.com\nSee below.\nOn Mon, Bob wrote:\nFrom: b@y.com\nOriginal."
    result = run_pipeline(_text_result(blob), user_id=USER)
    assert len(result.prepared) == 1
    item = result.prepared[0]
    assert IssueFlag.NEEDS_MANUAL_SPLIT.value in item.flags
    assert item.needs_manual_review is True


def test_scanned_pdf_becomes_review_placeholder() -> None:
    scanned = ParseResult(
        parser="pdf",
        records=[
            ParsedRecord(
                text="",
                source_ref="document",
                flags=[IssueFlag.SCANNED_PDF.value],
                needs_manual_review=True,
            )
        ],
        splittable=True,
    )
    item = run_pipeline(scanned, user_id=USER).prepared[0]
    assert IssueFlag.SCANNED_PDF.value in item.flags and item.needs_manual_review is True


def test_blank_skipped_count_carried_through() -> None:
    pr = ParseResult(parser="csv", records=[ParsedRecord("real one", "row 2")], blank_skipped=3)
    result = run_pipeline(pr, user_id=USER)
    assert result.blank_skipped == 3 and result.detected == 1
