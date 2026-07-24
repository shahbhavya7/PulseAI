"""Chat endpoints — sessions, streamed messages, memory sweep.

* ``POST /chat/sessions`` — start a session.
* ``GET  /chat/sessions`` — list the user's sessions.
* ``GET  /chat/sessions/{id}`` — one session + transcript.
* ``POST /chat/sessions/{id}/messages`` — ask a question; the answer streams back
  as Server-Sent Events (``data:`` lines, terminated by ``event: done``).
* ``POST /chat/sessions/{id}/end`` — archive + write the memory summary.
* ``POST /chat/sweep`` — summarise the user's idle sessions.

Everything is scoped to the authenticated user (guardrail: chat can only read
that user's data).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.schemas.chat import (
    ChatMessageOut,
    ChatSessionDetail,
    ChatSessionOut,
    CreateSessionRequest,
    SendMessageRequest,
    SweepResponse,
)
from app.services import chat
from app.services.chat import ChatError

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _session_out(session: object) -> ChatSessionOut:
    s = session  # ChatSession
    return ChatSessionOut(
        id=s.id,  # type: ignore[attr-defined]
        title=s.title,  # type: ignore[attr-defined]
        status=str(s.status),  # type: ignore[attr-defined]
        created_at=s.created_at,  # type: ignore[attr-defined]
        updated_at=s.updated_at,  # type: ignore[attr-defined]
    )


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: CreateSessionRequest, user: CurrentUser, db: DbSession
) -> ChatSessionOut:
    """Start a new chat session."""
    session = chat.create_session(db, user, title=payload.title)
    return _session_out(session)


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(user: CurrentUser, db: DbSession) -> list[ChatSessionOut]:
    """List the user's sessions, newest first."""
    return [_session_out(s) for s in chat.list_sessions(db, user)]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: UUID, user: CurrentUser, db: DbSession) -> ChatSessionDetail:
    """Return a session and its full transcript."""
    try:
        session = chat.get_session(db, user, session_id)
    except ChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    messages = [
        ChatMessageOut(id=m.id, role=str(m.role), content=m.content, created_at=m.created_at)
        for m in chat.list_messages(db, session)
    ]
    base = _session_out(session)
    return ChatSessionDetail(**base.model_dump(), messages=messages)


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: UUID, payload: SendMessageRequest, user: CurrentUser, db: DbSession
) -> StreamingResponse:
    """Ask a question; stream the grounded answer as SSE."""
    try:
        session = chat.get_session(db, user, session_id)
    except ChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    token_iter = chat.stream_turn(
        db, user, session, payload.message, week=payload.week, category=payload.category
    )

    def event_stream() -> Iterator[str]:
        # Each token is a JSON-encoded SSE data line; a final `done` event closes.
        try:
            for token in token_iter:
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:  # noqa: BLE001 — SSE must always close cleanly
            logger.exception("Chat stream error")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_session(session_id: UUID, user: CurrentUser, db: DbSession) -> None:
    """Archive a session and write its cross-session memory summary."""
    try:
        session = chat.get_session(db, user, session_id)
    except ChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    chat.end_session(db, user, session)


@router.post("/sweep", response_model=SweepResponse)
def sweep(user: CurrentUser, db: DbSession) -> SweepResponse:
    """Summarise + archive the user's idle sessions."""
    return SweepResponse(swept=chat.sweep_idle_sessions(db, user))
