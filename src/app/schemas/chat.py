"""Schemas for the chat endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import APIModel


class ChatMessageOut(APIModel):
    """One persisted message in a session."""

    id: UUID
    role: str
    content: str
    created_at: datetime


class ChatSessionOut(APIModel):
    """A session with its status (used in the session list)."""

    id: UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(ChatSessionOut):
    """A session plus its full transcript."""

    messages: list[ChatMessageOut]


class CreateSessionRequest(APIModel):
    """Optional title for a new session."""

    title: str | None = Field(default=None, max_length=512)


class SendMessageRequest(APIModel):
    """A user turn plus optional retrieval filters (week/category)."""

    message: str = Field(min_length=1, max_length=4000)
    week: str | None = Field(default=None, max_length=8)
    category: str | None = Field(default=None, max_length=32)


class SweepResponse(APIModel):
    """Result of the idle-session sweep."""

    swept: int
