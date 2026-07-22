"""Business-logic services layer.

Services encapsulate operations that span models and external clients so the
API layer stays thin. Phase 0 ships the health/readiness service; domain
services (triage, summarization, chat) land in later phases.
"""

from app.services.health import HealthService
from app.services.ingestion import IngestionService

__all__ = ["HealthService", "IngestionService"]
