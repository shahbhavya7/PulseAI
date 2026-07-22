"""Domain enumerations.

Every enum is a :class:`~enum.StrEnum`; its string ``value`` is what gets
persisted in a plain ``String`` column (see :data:`app.models.mixins`-style
usage in each model). Storing the string keeps the database human-readable and
decoupled from Python's enum ordering.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Authorization role of a :class:`~app.models.user.User`."""

    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TicketSource(StrEnum):
    """Where a :class:`~app.models.ticket.Ticket` originated."""

    EMAIL = "email"
    SLACK = "slack"
    WEB = "web"
    API = "api"
    MANUAL = "manual"


class TicketStatus(StrEnum):
    """Lifecycle state of a ticket."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    """Business priority of a ticket."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class IssueSeverity(StrEnum):
    """Severity of an individual issue extracted from a ticket."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueStatus(StrEnum):
    """Triage state of an issue (the atomic unit of work)."""

    OPEN = "open"
    TRIAGED = "triaged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class IssueCategory(StrEnum):
    """Classification of an issue."""

    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    QUESTION = "question"
    INCIDENT = "incident"
    OTHER = "other"


class SummaryStatus(StrEnum):
    """Generation state of a weekly summary."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


class ChatSessionStatus(StrEnum):
    """Lifecycle state of a chat session."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ChatRole(StrEnum):
    """Author role of a chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class IssueFlag(StrEnum):
    """Machine annotations attached to an issue during ingestion.

    Persisted as strings in :attr:`app.models.issue.Issue.flags`.
    """

    # Parser-level
    SCANNED_PDF = "scanned_pdf"  # no extractable text → likely image scan
    ENCODING_RECOVERED = "encoding_recovered"  # decoded via non-UTF-8 fallback
    # Boundary
    NEEDS_MANUAL_SPLIT = "needs_manual_split"  # multiple customers, unclear split
    # Cleaning
    BOILERPLATE_STRIPPED = "boilerplate_stripped"
    PII_REDACTED = "pii_redacted"
    LANGUAGE_UNKNOWN = "language_unknown"
    # Content quality
    ONE_WORD = "one_word"
    JUNK = "junk"
