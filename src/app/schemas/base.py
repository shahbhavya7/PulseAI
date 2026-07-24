"""Shared Pydantic base classes for API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for all API schemas.

    ``from_attributes`` lets response models be built directly from ORM
    objects; ``extra="forbid"`` rejects unexpected fields on input.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")
    # from_attributes=True: a Pydantic model can be built straight from an ORM
    # object, auto-populating its fields from the object's attributes.
    # extra="forbid": if any unexpected field is provided when creating an
    # instance of this model, a validation error is raised.
