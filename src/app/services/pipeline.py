"""AI pipeline orchestration: clean → cache → (skip junk | LLM) → validate → persist.

Two entry points:

* :func:`analyze` — the pure-ish analysis flow (no DB). Cleans the text, checks
  the Redis cache, skips the LLM for empty/junk, otherwise calls the model, and
  caches the validated result. Used by ``POST /analyze`` and reused by the
  persist path.
* :func:`analyze_and_persist` — runs :func:`analyze` for a ticket, then fans the
  result out into one :class:`~app.models.issue.Issue` row per analyzed issue.

The model call is injectable (`analyzer=`), so tests exercise the whole pipeline
without touching OpenAI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import IssueCategory, IssueSeverity, IssueStatus
from app.models.issue import Issue
from app.models.ticket import Ticket
from app.schemas.ai import (
    Classification,
    IssueAnalysis,
    SentimentLabel,
    SentimentUrgency,
    Themes,
    TicketAnalysis,
    UrgencyLabel,
)
from app.services import llm
from app.services.ai_cache import get_cached_analysis, set_cached_analysis
from app.services.cleaning import (
    content_hash,
    normalise_text,
    redact_pii,
    strip_boilerplate,
)
from app.services.ingestion import iso_week
from app.services.llm import LLMError
from app.services.validation import classify_content
from app.services.vector_store import VectorStore, get_vector_store

logger = get_logger(__name__)

# Below this classification confidence an issue is routed for manual review.
LOW_CONFIDENCE_THRESHOLD = 0.5

# A model callable: cleaned text -> TicketAnalysis. Defaults to the real LLM.
Analyzer = Callable[[str], TicketAnalysis]


class AnalysisSource(StrEnum):
    """Where an analysis result came from (useful for tests and debugging)."""

    CACHE = "cache"
    LLM = "llm"
    SKIPPED_JUNK = "skipped_junk"


@dataclass
class AnalysisOutcome:
    """Result of :func:`analyze` — the analysis plus how it was produced."""

    analysis: TicketAnalysis
    source: AnalysisSource
    content_hash: str
    cleaned_text: str
    flags: list[str]


def _junk_analysis() -> TicketAnalysis:
    """Deterministic default used when we skip the LLM for empty/junk input."""
    return TicketAnalysis(
        issues=[
            IssueAnalysis(
                summary="(no analyzable content)",
                classification=Classification(category=IssueCategory.OTHER, confidence=0.0),
                sentiment_urgency=SentimentUrgency(
                    sentiment_score=0.0,
                    sentiment_label=SentimentLabel.NEUTRAL,
                    urgency_score=0.0,
                    urgency_label=UrgencyLabel.LOW,
                ),
                themes=Themes(labels=[]),
            )
        ]
    )


def analyze(
    text: str,
    *,
    user_id_str: str,
    analyzer: Analyzer | None = None,
    use_cache: bool = True,
) -> AnalysisOutcome:
    """Analyze raw ticket text end-to-end (no persistence).

    Steps: clean (strip boilerplate + redact PII) → hash → skip LLM for junk →
    cache lookup → LLM call → cache store.

    Args:
        text: Raw ticket text.
        user_id_str: Owner id as a string; scopes the content hash / cache key.
        analyzer: Model callable (injected in tests).
        use_cache: Set False to force a fresh model call.

    Raises:
        LLMError: On missing key or API failure (caller degrades to 503).
    """
    analyzer = analyzer or llm.analyze_ticket_text

    # 1. Clean: strip boilerplate/quotes, then redact PII so nothing sensitive is
    #    ever sent to the model or written to the cache.
    cleaned = redact_pii(strip_boilerplate(text).text).text
    normalised = normalise_text(cleaned)
    chash = content_hash_from_str(user_id_str, normalised)

    # 2. Skip the LLM for empty/junk — saves cost, guarantees consistency.
    verdict = classify_content(cleaned)
    if verdict.is_junk:
        analysis = _junk_analysis()
        flags = [*verdict.flags]
        # Cache the deterministic default too, so repeats stay identical.
        if use_cache:
            set_cached_analysis(chash, analysis)
        return AnalysisOutcome(analysis, AnalysisSource.SKIPPED_JUNK, chash, cleaned, flags)

    # 3. Cache check — identical text returns the identical stored result.
    if use_cache:
        cached = get_cached_analysis(chash)
        if cached is not None:
            return AnalysisOutcome(cached, AnalysisSource.CACHE, chash, cleaned, [])

    # 4. LLM call (may raise LLMError → handled upstream). 5. Result is already
    #    schema-validated by the SDK against TicketAnalysis.
    analysis = analyzer(cleaned)

    # 6. Store for next time.
    if use_cache:
        set_cached_analysis(chash, analysis)
    return AnalysisOutcome(analysis, AnalysisSource.LLM, chash, cleaned, [])


def content_hash_from_str(user_id_str: str, normalised_text: str) -> str:
    """Hash helper that accepts the user id as a string (route/tests convenience)."""
    return content_hash(UUID(user_id_str), normalised_text)


_URGENCY_TO_SEVERITY: dict[UrgencyLabel, IssueSeverity] = {
    UrgencyLabel.LOW: IssueSeverity.LOW,
    UrgencyLabel.MEDIUM: IssueSeverity.MEDIUM,
    UrgencyLabel.HIGH: IssueSeverity.HIGH,
    UrgencyLabel.CRITICAL: IssueSeverity.CRITICAL,
}


def _embed_issues(vector_store: VectorStore, issues: list[Issue]) -> None:
    """Embed each issue's text in the same flow; on failure mark for re-embed.

    A transient embedding error must never lose a row: we keep the issue with
    ``embedding=None`` and ``needs_reembed=True`` so a later job can retry.
    """
    if not issues:
        return
    try:
        vectors = vector_store.embed([i.description or i.title for i in issues])
        for issue, vector in zip(issues, vectors, strict=True):
            issue.embedding = vector
            issue.needs_reembed = False
    except LLMError as exc:
        logger.warning("Embedding failed; marking %d issue(s) for re-embed: %s", len(issues), exc)
        for issue in issues:
            issue.embedding = None
            issue.needs_reembed = True


def analyze_and_persist(
    db: Session,
    ticket: Ticket,
    *,
    analyzer: Analyzer | None = None,
    vector_store: VectorStore | None = None,
) -> list[Issue]:
    """Analyze ``ticket`` and replace its issues with the analyzed fan-out.

    Idempotent: existing issues for the ticket are removed and rebuilt from the
    (possibly cached) analysis, so re-running yields the same rows. Each issue is
    embedded in the same flow; embedding failures mark the row for re-embed.
    """
    text = ticket.body or ticket.title
    outcome = analyze(text, user_id_str=str(ticket.owner_id), analyzer=analyzer)

    # Replace prior issues for this ticket (fan-out is authoritative).
    db.execute(delete(Issue).where(Issue.ticket_id == ticket.id))

    week = iso_week()
    now = datetime.now(UTC)
    created: list[Issue] = []
    for index, item in enumerate(outcome.analysis.issues):
        cls = item.classification
        su = item.sentiment_urgency
        needs_review = (
            outcome.source is AnalysisSource.SKIPPED_JUNK
            or cls.confidence < LOW_CONFIDENCE_THRESHOLD
        )
        flags = list(dict.fromkeys(outcome.flags))
        # Unique per issue within the ticket (satisfies the (ticket, hash) uniq).
        issue_hash = content_hash_from_str(
            str(ticket.owner_id),
            normalise_text(f"{ticket.id}:{index}:{item.summary}"),
        )
        issue = Issue(
            ticket_id=ticket.id,
            title=item.summary[:512],
            description=item.summary,
            category=cls.category,
            severity=_URGENCY_TO_SEVERITY[su.urgency_label],
            status=IssueStatus.OPEN,
            confidence=cls.confidence,
            needs_manual_review=needs_review,
            flags=flags,
            content_hash=issue_hash,
            week=week,
            sentiment_score=su.sentiment_score,
            urgency_score=su.urgency_score,
            themes=item.themes.labels,
            analyzed_at=now,
        )
        db.add(issue)
        created.append(issue)

    # Embed in the same flow as the row write (best-effort; never loses a row).
    _embed_issues(vector_store or get_vector_store(), created)

    db.commit()
    logger.info(
        "Analyzed ticket %s (%s): %d issue(s)",
        ticket.id,
        outcome.source,
        len(created),
    )
    return created
