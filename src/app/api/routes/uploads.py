"""``POST /uploads`` — ingest a CSV / PDF / text file into tickets and issues.

The heavy lifting lives in :class:`~app.services.ingestion.service.IngestionService`.
This route only reads the multipart file, delegates, and maps file-level
:class:`~app.services.ingestion.errors.IngestionError` subclasses to clear 4xx
responses.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile, status
from fastapi.exceptions import HTTPException

from app.api.deps import CurrentUser, DbSession
from app.schemas.upload import UploadSummary
from app.services.ingestion import (
    EmptyFileError,
    IngestionError,
    IngestionService,
    MissingTextColumnError,
    UndecodableFileError,
    UnsupportedFileTypeError,
)

router = APIRouter(tags=["uploads"])

# Map each file-level error to an HTTP status. Everything else → 422.
_STATUS_BY_ERROR: dict[type[IngestionError], int] = {
    UnsupportedFileTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    UndecodableFileError: status.HTTP_400_BAD_REQUEST,
    EmptyFileError: status.HTTP_400_BAD_REQUEST,
    MissingTextColumnError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@router.post(
    "/uploads",
    response_model=UploadSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file and ingest it into tickets/issues",
)
def create_upload(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(..., description="CSV, PDF, or plain-text file"),
) -> UploadSummary:
    """Ingest ``file`` for the acting user and return the upload summary."""
    data = file.file.read()
    try:
        return IngestionService(db).ingest(
            user,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
        )
    except IngestionError as exc:
        http_status = _STATUS_BY_ERROR.get(type(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
