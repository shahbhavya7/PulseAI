"""Schemas for the ``POST /uploads`` response.

The upload summary reports, per file: how many candidate items were detected and
how they resolved — created, skipped (with reason), and flagged (created but
needing attention). Per-item detail is included so a caller can drill in.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.schemas.base import APIModel


class SkipReason(StrEnum):
    """Why a candidate item was dropped rather than persisted."""

    BLANK = "blank"  # empty row / whitespace-only source
    EMPTY_AFTER_CLEAN = "empty_after_clean"  # became empty once boilerplate removed
    DUPLICATE = "duplicate"  # content_hash already seen (this batch or DB)


class PasteTicketRequest(APIModel):
    """A single ticket typed/pasted straight into the app (no file)."""

    text: str = Field(min_length=1, max_length=20_000, description="The ticket message")
    title: str | None = Field(
        default=None, max_length=200, description="Optional label for the source"
    )


class CreatedItem(APIModel):
    """A persisted ticket/issue pair produced from the upload."""

    source_ref: str
    ticket_id: UUID
    issue_id: UUID
    title: str
    language: str
    confidence: float
    flags: list[str]
    needs_manual_review: bool

    @property
    def flagged(self) -> bool:
        return bool(self.flags) or self.needs_manual_review


class SkippedItemOut(APIModel):
    """A candidate item that was not persisted."""

    source_ref: str
    reason: SkipReason


class UploadCounts(APIModel):
    """Headline tallies for the upload."""

    detected: int = Field(description="Candidate items found (excl. blank rows)")
    created: int = Field(description="Tickets/issues persisted")
    skipped: int = Field(description="Items dropped (blank, empty, or duplicate)")
    flagged: int = Field(description="Created items carrying flags / manual review")
    duplicates: int = Field(description="Items skipped as duplicates")
    blanks: int = Field(description="Blank source rows skipped at parse time")


class UploadSummary(APIModel):
    """Full result of one file upload."""

    filename: str
    content_type: str | None
    parser: str
    encoding_recovered: bool = False
    analyzed: bool = Field(
        default=False, description="Whether created tickets were auto-classified in-request"
    )
    analyzed_count: int = Field(default=0, description="How many tickets were auto-classified")
    counts: UploadCounts
    created_items: list[CreatedItem]
    skipped_items: list[SkippedItemOut]
