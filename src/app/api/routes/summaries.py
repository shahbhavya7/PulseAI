"""Weekly summary endpoints.

* ``POST /summaries/{week}`` — generate (or regenerate) the summary for the ISO
  week (e.g. ``2026-W30``) and persist it.
* ``GET  /summaries/{week}`` — read the stored summary back.

Generation needs the LLM, so a missing key / API error degrades to **503**.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.summary import SummaryResponse
from app.services.llm import LLMError
from app.services.summaries import (
    NoIssuesForWeekError,
    generate_summary,
    get_summary,
    to_response,
)

router = APIRouter(tags=["summaries"])


@router.post("/summaries/{week}", response_model=SummaryResponse)
def create_summary(week: str, user: CurrentUser, db: DbSession) -> SummaryResponse:
    """Generate and persist the weekly summary for ``week``."""
    try:
        summary = generate_summary(db, user, week)
    except NoIssuesForWeekError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_issues", "message": str(exc)},
        ) from exc
    except LLMError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ai_unavailable", "message": exc.message},
        ) from exc
    return to_response(summary)


@router.get("/summaries/{week}", response_model=SummaryResponse)
def read_summary(week: str, user: CurrentUser, db: DbSession) -> SummaryResponse:
    """Return the stored weekly summary for ``week`` (404 if not generated yet)."""
    summary = get_summary(db, user, week)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_generated", "message": f"No summary for week {week}."},
        )
    return to_response(summary)
