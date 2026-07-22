"""ORM models.

Importing this package pulls in every model module so that ``Base.metadata``
is fully populated — required for Alembic autogenerate and ``create_all``.
"""

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.enums import (
    ChatRole,
    ChatSessionStatus,
    IssueCategory,
    IssueFlag,
    IssueSeverity,
    IssueStatus,
    SummaryStatus,
    TicketPriority,
    TicketSource,
    TicketStatus,
    UserRole,
)
from app.models.issue import Issue
from app.models.ticket import Ticket
from app.models.user import User
from app.models.weekly_summary import WeeklySummary

__all__ = [
    "ChatMessage",
    "ChatRole",
    "ChatSession",
    "ChatSessionStatus",
    "Issue",
    "IssueCategory",
    "IssueFlag",
    "IssueSeverity",
    "IssueStatus",
    "SummaryStatus",
    "Ticket",
    "TicketPriority",
    "TicketSource",
    "TicketStatus",
    "User",
    "UserRole",
    "WeeklySummary",
]
