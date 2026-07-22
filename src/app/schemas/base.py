"""Shared Pydantic base classes for API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for all API schemas.

    ``from_attributes`` lets response models be built directly from ORM
    objects; ``extra="forbid"`` rejects unexpected fields on input.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")
