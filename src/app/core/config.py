"""Typed application settings loaded from the environment / ``.env``.

All settings are read through :func:`get_settings`, which is cached so the
``.env`` file and process environment are parsed exactly once per process.
Nothing here hardcodes a secret; every credential comes from the environment.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment the process is running in."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application configuration.

    Values are sourced (in priority order) from the process environment, then
    a ``.env`` file. Every field is prefixed with ``PULSE_`` to avoid clashes
    with unrelated environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="PULSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    env: Environment = Environment.LOCAL
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"
    project_name: str = "PulseAI"

    # ---- Postgres ----
    # A full DSN wins if provided; otherwise it is assembled from the parts.
    database_url: PostgresDsn | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "pulse"
    postgres_password: str = "pulse"
    postgres_db: str = "pulse"

    # ---- Redis ----
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")  # type: ignore[assignment]

    # ---- Engine tuning ----
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True

    @model_validator(mode="after")
    def _assemble_database_url(self) -> Settings:
        """Build ``database_url`` from parts when a full DSN was not supplied."""
        if self.database_url is None:
            self.database_url = PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        """The database URL as a plain string for SQLAlchemy/Alembic."""
        assert self.database_url is not None  # guaranteed by the validator
        return str(self.database_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        """True when running in the production environment."""
        return self.env is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance."""
    return Settings()
