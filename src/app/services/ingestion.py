"""Ingestion: parse an uploaded file, prepare items, and persist tickets/issues.

The whole request path for ``POST /uploads`` is: the route calls
:class:`IngestionService`, which parses (``parse_csv`` / ``parse_pdf`` /
``parse_text``), splits blobs (:func:`detect_boundaries`), cleans each item via
:mod:`app.services.cleaning`, validates via :mod:`app.services.validation`, and
writes one :class:`~app.models.ticket.Ticket` + **one**
:class:`~app.models.issue.Issue` per item (multi-issue fan-out is deferred to the
AI phase).

Error types raised by validation are re-exported here so the route imports
everything ingestion-related from one module.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pandas as pd
import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import (
    IssueCategory,
    IssueFlag,
    IssueSeverity,
    IssueStatus,
    TicketSource,
)
from app.models.issue import Issue
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.upload import (
    CreatedItem,
    SkippedItemOut,
    SkipReason,
    UploadCounts,
    UploadSummary,
)
from app.services.cleaning import (
    UNKNOWN_LANGUAGE,
    content_hash,
    detect_language,
    normalise_text,
    redact_pii,
    strip_boilerplate,
)
from app.services.stats_cache import invalidate_user_stats
from app.services.validation import (
    EmptyFileError,
    IngestionError,
    MissingTextColumnError,
    UndecodableFileError,
    UnsupportedFileTypeError,
    classify_content,
    decode_bytes,
    find_text_column,
    is_blank,
)

logger = get_logger(__name__)

# Re-exported so callers (e.g. the route) import all ingestion symbols from here.
__all__ = [
    "EmptyFileError",
    "IngestionError",
    "IngestionService",
    "MissingTextColumnError",
    "ParseResult",
    "UndecodableFileError",
    "UnsupportedFileTypeError",
    "detect_boundaries",
    "parse_csv",
    "parse_file",
    "parse_pdf",
    "parse_text",
]

_TITLE_MAX = 120
_SCANNED_PLACEHOLDER = "[SCANNED_PDF: no extractable text — manual review required]"


# ===========================================================================
# Parsing — one function per file type
# ===========================================================================


@dataclass
class ParsedRecord:
    """One raw unit of text extracted from a source file."""

    text: str
    source_ref: str  # human-readable origin, e.g. "row 3" or "document"
    flags: list[str] = field(default_factory=list)
    needs_manual_review: bool = False


@dataclass
class ParseResult:
    """Everything a parser produces for one file."""

    parser: str  # "csv" | "pdf" | "text"
    records: list[ParsedRecord]
    blank_skipped: int = 0
    # Whether records may hold multiple concatenated customers and should run
    # through boundary detection. CSV rows are atomic and set this False.
    splittable: bool = False


def parse_csv(data: bytes) -> ParseResult:
    """Parse CSV bytes into one record per non-blank data row.

    Decodes with encoding auto-repair, validates the text column, and skips and
    counts blank rows. Duplicate rows are handled later by content-hash dedup.
    """
    decoded = decode_bytes(data)
    base_flags = [IssueFlag.ENCODING_RECOVERED.value] if decoded.recovered else []
    try:
        frame = pd.read_csv(
            io.StringIO(decoded.text),
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=False,
        )
    except pd.errors.EmptyDataError as exc:
        raise EmptyFileError("The CSV file is empty.") from exc

    text_col = find_text_column(list(frame.columns))

    records: list[ParsedRecord] = []
    blank_skipped = 0
    for position, value in enumerate(frame[text_col].tolist()):
        row_number = position + 2  # +1 header, +1 for 1-based numbering
        if is_blank(value):
            blank_skipped += 1
            continue
        records.append(
            ParsedRecord(text=str(value), source_ref=f"row {row_number}", flags=list(base_flags))
        )
    return ParseResult("csv", records, blank_skipped=blank_skipped, splittable=False)


def parse_pdf(data: bytes) -> ParseResult:
    """Parse PDF bytes into a single document record.

    OCR is out of scope: a PDF with no extractable text is treated as a scan and
    emitted as an empty record flagged ``scanned_pdf`` + ``needs_manual_review``.
    """
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()

    if not text:
        record = ParsedRecord(
            text="",
            source_ref="document",
            flags=[IssueFlag.SCANNED_PDF.value],
            needs_manual_review=True,
        )
        return ParseResult("pdf", [record], splittable=True)

    return ParseResult("pdf", [ParsedRecord(text=text, source_ref="document")], splittable=True)


def parse_text(data: bytes) -> ParseResult:
    """Parse plain-text bytes into a single document record (decoded/repaired)."""
    decoded = decode_bytes(data)
    flags = [IssueFlag.ENCODING_RECOVERED.value] if decoded.recovered else []
    record = ParsedRecord(text=decoded.text.strip(), source_ref="document", flags=flags)
    return ParseResult("text", [record], splittable=True)


# File-type dispatch. Extension first, then content-type; text is the fallback.
_CSV_EXT = (".csv",)
_CSV_CT = ("text/csv", "application/csv", "application/vnd.ms-excel")
_PDF_EXT = (".pdf",)
_PDF_CT = ("application/pdf",)


def parse_file(filename: str, content_type: str | None, data: bytes) -> ParseResult:
    """Select the parser for ``filename``/``content_type`` and parse ``data``.

    Plain text is the catch-all for any decodable upload, so this only raises
    :class:`UnsupportedFileTypeError` if the text fallback is unreachable.
    """
    name = filename.lower()
    if name.endswith(_CSV_EXT) or content_type in _CSV_CT:
        return parse_csv(data)
    if name.endswith(_PDF_EXT) or content_type in _PDF_CT:
        return parse_pdf(data)
    return parse_text(data)


# ===========================================================================
# Boundary detection — split a blob into per-customer tickets
# ===========================================================================

_FROM_RE = re.compile(r"^\s*From:\s*.+$", re.IGNORECASE | re.MULTILINE)
_ORIGINAL_RE = re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE | re.MULTILINE)
_ON_WROTE_RE = re.compile(r"^\s*On .+ wrote:\s*$", re.IGNORECASE | re.MULTILINE)
# A deliberate separator: 2+ blank lines. Single blank lines (paragraphs) do NOT
# split, to avoid chopping one customer's message into many tickets.
_MULTI_BLANK_RE = re.compile(r"\n[ \t]*\n[ \t]*\n+")


@dataclass
class BoundaryResult:
    """Segments produced by boundary detection."""

    segments: list[str]
    needs_manual_split: bool


def _split_on_markers(text: str) -> list[str]:
    """Split text immediately *before* each From:/Original-Message marker."""
    starts = {0}
    for pattern in (_FROM_RE, _ORIGINAL_RE):
        for match in pattern.finditer(text):
            starts.add(match.start())
    ordered = sorted(starts)
    segments = [text[a:b] for a, b in zip(ordered, ordered[1:], strict=False)]
    segments.append(text[ordered[-1] :])
    return [s.strip() for s in segments if s.strip()]


def detect_boundaries(text: str) -> BoundaryResult:
    """Split ``text`` into per-customer segments.

    Splits cleanly on From:/Original-Message markers or 2+ blank-line gaps. When
    multiple senders are interleaved with quoted-reply markers (an ambiguous
    forwarded thread), returns the whole blob as one segment flagged
    ``needs_manual_split`` — never merged-and-forgotten.
    """
    stripped = text.strip()
    if not stripped:
        return BoundaryResult(segments=[], needs_manual_split=False)

    from_count = len(_FROM_RE.findall(stripped))
    marker_count = from_count + len(_ORIGINAL_RE.findall(stripped))
    quoted_count = len(_ON_WROTE_RE.findall(stripped))

    if from_count >= 2 and quoted_count >= 1:
        return BoundaryResult(segments=[stripped], needs_manual_split=True)

    if marker_count == 0:
        blocks = [b.strip() for b in _MULTI_BLANK_RE.split(stripped) if b.strip()]
        if len(blocks) > 1:
            return BoundaryResult(segments=blocks, needs_manual_split=False)
        return BoundaryResult(segments=[stripped], needs_manual_split=False)

    segments = _split_on_markers(stripped)
    if not segments:
        return BoundaryResult(segments=[stripped], needs_manual_split=False)
    return BoundaryResult(segments=segments, needs_manual_split=False)


# ===========================================================================
# Pipeline — parsed records → prepared + skipped items (pure, no DB)
# ===========================================================================


@dataclass
class PreparedItem:
    """A cleaned, deduped item ready to become a Ticket + Issue."""

    source_ref: str
    stored_text: str  # cleaned + PII-redacted; this is what gets persisted
    title: str
    language: str
    confidence: float
    flags: list[str]
    needs_manual_review: bool
    content_hash: str


@dataclass
class SkippedItem:
    """A candidate item dropped rather than persisted."""

    source_ref: str
    reason: str  # a SkipReason value


@dataclass
class PipelineResult:
    """Outcome of running the pipeline over one parsed file."""

    parser: str
    prepared: list[PreparedItem] = field(default_factory=list)
    skipped: list[SkippedItem] = field(default_factory=list)
    blank_skipped: int = 0

    @property
    def detected(self) -> int:
        """Candidate items considered (persisted + skipped, excl. blank rows)."""
        return len(self.prepared) + len(self.skipped)


def _make_title(text: str) -> str:
    """Derive a short title from the first non-empty line of the text."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:_TITLE_MAX]
    return "(untitled)"


@dataclass
class SegmentSkip:
    """A segment that was cleaned but is not worth persisting, with a reason."""

    reason: str  # a SkipReason value


def _prepare_segment(
    text: str,
    *,
    user_id: UUID,
    base_flags: list[str],
    base_needs_review: bool,
    needs_manual_split: bool,
    source_ref: str,
) -> PreparedItem | SegmentSkip | None:
    """Clean, redact, tag, and hash one segment.

    Returns ``None`` if empty after cleaning, a :class:`SegmentSkip` if the
    content is non-analyzable (one-word / greeting / gibberish — discarded, not
    stored), otherwise a :class:`PreparedItem` ready to persist.
    """
    cleaned = strip_boilerplate(text)
    redacted = redact_pii(cleaned.text)
    stored = redacted.text

    normalised = normalise_text(stored)
    if not normalised:
        return None

    content = classify_content(stored)
    # Junk (empty/one-word/greeting/gibberish) has nothing to analyze — discard it
    # rather than storing a ticket. It is reported as a "non_analyzable" skip.
    # A ticket flagged for manual review (e.g. scanned PDF, unclear split) is NOT
    # discarded — that's a real item a human needs to see.
    if content.is_junk and not (base_needs_review or needs_manual_split):
        return SegmentSkip(SkipReason.NON_ANALYZABLE.value)

    language = detect_language(stored)

    flags: list[str] = list(base_flags)
    if cleaned.boilerplate_stripped:
        flags.append(IssueFlag.BOILERPLATE_STRIPPED.value)
    if redacted.redacted:
        flags.append(IssueFlag.PII_REDACTED.value)
    if language == UNKNOWN_LANGUAGE:
        flags.append(IssueFlag.LANGUAGE_UNKNOWN.value)
    if needs_manual_split:
        flags.append(IssueFlag.NEEDS_MANUAL_SPLIT.value)
    flags.extend(content.flags)
    flags = list(dict.fromkeys(flags))  # de-dupe, preserve order

    needs_review = base_needs_review or needs_manual_split or content.is_junk
    return PreparedItem(
        source_ref=source_ref,
        stored_text=stored,
        title=_make_title(stored),
        language=language,
        confidence=content.confidence,
        flags=flags,
        needs_manual_review=needs_review,
        content_hash=content_hash(user_id, normalised),
    )


def _placeholder_item(record: ParsedRecord, user_id: UUID) -> PreparedItem:
    """Build a review placeholder for an empty-but-flagged record (scanned PDF)."""
    normalised = normalise_text(_SCANNED_PLACEHOLDER)
    return PreparedItem(
        source_ref=record.source_ref,
        stored_text=_SCANNED_PLACEHOLDER,
        title="(scanned document — needs manual review)",
        language=UNKNOWN_LANGUAGE,
        confidence=0.0,
        flags=list(dict.fromkeys([*record.flags, IssueFlag.LANGUAGE_UNKNOWN.value])),
        needs_manual_review=True,
        content_hash=content_hash(user_id, normalised),
    )


def _append_or_dedup(result: PipelineResult, seen: set[str], item: PreparedItem) -> None:
    """Append ``item`` unless its content hash was already seen (duplicate)."""
    if item.content_hash in seen:
        result.skipped.append(SkippedItem(item.source_ref, SkipReason.DUPLICATE.value))
        return
    seen.add(item.content_hash)
    result.prepared.append(item)


def run_pipeline(
    parse_result: ParseResult,
    *,
    user_id: UUID,
    existing_hashes: set[str] | None = None,
) -> PipelineResult:
    """Transform a :class:`ParseResult` into prepared + skipped items with dedup."""
    result = PipelineResult(parser=parse_result.parser, blank_skipped=parse_result.blank_skipped)
    seen: set[str] = set(existing_hashes or set())

    for record in parse_result.records:
        if parse_result.splittable:
            boundary = detect_boundaries(record.text)
            segments = boundary.segments
            needs_split = boundary.needs_manual_split
        else:
            segments = [record.text] if record.text.strip() else []
            needs_split = False

        if not segments:
            # Empty text but parser demanded review (scanned PDF) → placeholder.
            if record.needs_manual_review:
                _append_or_dedup(result, seen, _placeholder_item(record, user_id))
            continue

        for segment in segments:
            prepared = _prepare_segment(
                segment,
                user_id=user_id,
                base_flags=record.flags,
                base_needs_review=record.needs_manual_review,
                needs_manual_split=needs_split,
                source_ref=record.source_ref,
            )
            if prepared is None:
                result.skipped.append(
                    SkippedItem(record.source_ref, SkipReason.EMPTY_AFTER_CLEAN.value)
                )
                continue
            if isinstance(prepared, SegmentSkip):
                # Non-analyzable (one-word / greeting / gibberish) — discarded.
                result.skipped.append(SkippedItem(record.source_ref, prepared.reason))
                continue
            _append_or_dedup(result, seen, prepared)

    return result


# ===========================================================================
# Persistence service
# ===========================================================================


def iso_week(moment: datetime | None = None) -> str:
    """Return the ISO-8601 week string ``YYYY-Www`` for ``moment`` (default now)."""
    moment = moment or datetime.now(UTC)
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


class IngestionService:
    """Coordinates parse → pipeline → persist for a single uploaded file."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _existing_hashes(self, user: User) -> set[str]:
        """All content hashes already stored for this user (for dedup)."""
        rows = self.db.execute(
            select(Issue.content_hash)
            .join(Ticket, Issue.ticket_id == Ticket.id)
            .where(Ticket.owner_id == user.id)
        ).scalars()
        return set(rows)

    def _persist(self, user: User, item: PreparedItem, week: str) -> tuple[Ticket, Issue]:
        """Create a Ticket + one Issue for a prepared item."""
        ticket = Ticket(
            owner_id=user.id,
            title=item.title,
            body=item.stored_text,
            source=TicketSource.API,
            external_id=None,
        )
        self.db.add(ticket)
        self.db.flush()  # assign ticket.id before creating the issue

        issue = Issue(
            ticket_id=ticket.id,
            title=item.title,
            description=item.stored_text,
            category=IssueCategory.OTHER,
            severity=IssueSeverity.MEDIUM,
            status=IssueStatus.OPEN,
            confidence=item.confidence,
            needs_manual_review=item.needs_manual_review,
            flags=item.flags,
            content_hash=item.content_hash,
            week=week,
        )
        self.db.add(issue)
        self.db.flush()
        return ticket, issue

    def ingest(
        self,
        user: User,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
        auto_analyze: bool | None = None,
    ) -> UploadSummary:
        """Ingest one uploaded file and return its summary.

        When ``auto_analyze`` is enabled (defaulting to the ``auto_analyze_on_upload``
        setting) each created ticket is run through the AI classifier in the same
        request; a model outage degrades gracefully to the unclassified placeholder.

        Raises:
            IngestionError: For file-level failures (unsupported type, undecodable
                bytes, missing text column, empty file) — mapped to 4xx upstream.
        """
        if auto_analyze is None:
            auto_analyze = get_settings().auto_analyze_on_upload
        parse_result = parse_file(filename, content_type, data)
        encoding_recovered = any(
            IssueFlag.ENCODING_RECOVERED.value in record.flags for record in parse_result.records
        )

        pipeline = run_pipeline(
            parse_result,
            user_id=user.id,
            existing_hashes=self._existing_hashes(user),
        )

        if not pipeline.prepared and not pipeline.skipped and pipeline.blank_skipped == 0:
            raise EmptyFileError("The file contained no usable content.")

        week = iso_week()
        created_items: list[CreatedItem] = []
        created_tickets: list[Ticket] = []
        for item in pipeline.prepared:
            ticket, issue = self._persist(user, item, week)
            created_tickets.append(ticket)
            created_items.append(
                CreatedItem(
                    source_ref=item.source_ref,
                    ticket_id=ticket.id,
                    issue_id=issue.id,
                    title=item.title,
                    language=item.language,
                    confidence=item.confidence,
                    flags=item.flags,
                    needs_manual_review=item.needs_manual_review,
                )
            )
        self.db.commit()

        # New issues exist (placeholders at minimum), so the cached Overview is
        # stale even when auto-analyze is off and the pipeline never runs.
        invalidate_user_stats(str(user.id))

        # Classify the freshly-created tickets in the same request so the
        # dashboard shows categorised data without a manual "Analyse" click.
        # Best-effort: a model outage leaves the placeholder issues intact.
        discarded: set[UUID] = set()
        analyzed_count = 0
        if auto_analyze:
            analyzed_count, discarded = self._auto_analyze(created_tickets)

        # Tickets the model judged not real were deleted → move them out of the
        # "created" list and report them as non-analyzable instead.
        discarded_items = [c for c in created_items if c.ticket_id in discarded]
        created_items = [c for c in created_items if c.ticket_id not in discarded]

        skipped_items = [
            SkippedItemOut(source_ref=s.source_ref, reason=SkipReason(s.reason))
            for s in pipeline.skipped
        ] + [
            SkippedItemOut(source_ref=c.source_ref, reason=SkipReason.NON_ANALYZABLE)
            for c in discarded_items
        ]
        duplicates = sum(1 for s in pipeline.skipped if s.reason == SkipReason.DUPLICATE.value)
        non_analyzable = sum(
            1 for s in pipeline.skipped if s.reason == SkipReason.NON_ANALYZABLE.value
        ) + len(discarded_items)
        flagged = sum(1 for c in created_items if c.flags or c.needs_manual_review)

        summary = UploadSummary(
            filename=filename,
            content_type=content_type,
            parser=pipeline.parser,
            encoding_recovered=encoding_recovered,
            analyzed=analyzed_count > 0,
            analyzed_count=analyzed_count - len(discarded_items),
            counts=UploadCounts(
                detected=pipeline.detected,
                created=len(created_items),
                skipped=len(pipeline.skipped) + pipeline.blank_skipped + len(discarded_items),
                flagged=flagged,
                duplicates=duplicates,
                non_analyzable=non_analyzable,
                blanks=pipeline.blank_skipped,
            ),
            created_items=created_items,
            skipped_items=skipped_items,
        )
        logger.info(
            "Upload '%s' (%s): detected=%d created=%d skipped=%d flagged=%d analyzed=%d",
            filename,
            pipeline.parser,
            summary.counts.detected,
            summary.counts.created,
            summary.counts.skipped,
            summary.counts.flagged,
            analyzed_count,
        )
        return summary

    def ingest_text(
        self,
        user: User,
        *,
        text: str,
        title: str | None = None,
        auto_analyze: bool | None = None,
    ) -> UploadSummary:
        """Ingest a single pasted-in ticket (same path as a plain-text upload).

        The text runs through the identical parse → clean → persist → classify
        flow as a ``.txt`` upload, so pasting one ticket behaves exactly like
        uploading a one-message file. ``title`` only names the synthetic source.
        """
        filename = f"{title.strip()}.txt" if title and title.strip() else "pasted-ticket.txt"
        return self.ingest(
            user,
            filename=filename,
            content_type="text/plain",
            data=text.encode("utf-8"),
            auto_analyze=auto_analyze,
        )

    def _auto_analyze(self, tickets: list[Ticket]) -> tuple[int, set[UUID]]:
        """Classify each created ticket in-request.

        Returns ``(analyzed_count, discarded_ids)`` where ``discarded_ids`` are
        tickets the model judged not real (greeting / gibberish / non-issue) and
        deleted. Best-effort: a missing key or model outage (``LLMError``) leaves
        that ticket's placeholder issue untouched so the upload still succeeds and
        the ticket can be analysed later. Imported lazily to avoid a circular
        import (``pipeline`` imports this module for ``iso_week``).
        """
        if not tickets:
            return 0, set()

        from app.services.llm import LLMError
        from app.services.pipeline import analyze_and_persist

        analyzed = 0
        discarded: set[UUID] = set()
        for ticket in tickets:
            ticket_id = ticket.id
            try:
                issues = analyze_and_persist(self.db, ticket)
                analyzed += 1
                if not issues:
                    # Empty result → the model discarded it as not a real ticket.
                    discarded.add(ticket_id)
            except LLMError as exc:
                logger.warning(
                    "Auto-analyze skipped for ticket %s (model unavailable): %s",
                    ticket_id,
                    exc,
                )
                # analyze_and_persist rolls its own writes into the session; a
                # failure raised before commit leaves the placeholder issue.
                self.db.rollback()
        return analyzed, discarded
