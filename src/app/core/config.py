"""Typed application settings loaded from the environment / ``.env``.

All settings are read through :func:`get_settings`, which is cached so the
``.env`` file and process environment are parsed exactly once per process.
Nothing here hardcodes a secret; every credential comes from the environment.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import (
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    computed_field,
    model_validator,
)
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
    # Browser origins allowed to call the API (the Next.js dev server by default).
    # Override with PULSE_CORS_ORIGINS as a comma-separated list.
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @model_validator(mode="before")
    @classmethod
    def _split_cors_origins(cls, data: dict[str, object]) -> dict[str, object]:
        """Allow PULSE_CORS_ORIGINS to be a comma-separated string in the env."""
        origins = data.get("cors_origins") if isinstance(data, dict) else None
        if isinstance(origins, str):
            data["cors_origins"] = [o.strip() for o in origins.split(",") if o.strip()]
        return data

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

    # ---- OpenAI (Phase 2 AI pipeline) ----
    # The key lives only in the environment / .env — never hardcoded. When it is
    # unset the pipeline degrades gracefully instead of crashing.
    openai_api_key: SecretStr | None = None
    # GPT-5.x small model. `.env` overrides this; keep it in sync with .env.example.
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    # GPT-5.x reasoning effort: "minimal" is fastest/cheapest for classification.
    openai_reasoning_effort: str = "minimal"
    # Cache TTL for AI results keyed by content_hash (7 days).
    ai_cache_ttl_seconds: int = 604800
    # Embedding model (Phase 3). 1536 dims matches app.models.issue.EMBEDDING_DIM.
    openai_embedding_model: str = "text-embedding-3-small"

    # ---- Phase 5: auth (Google / Apple OIDC) ----
    # Signs the session JWT stored in the httpOnly cookie. MUST be set in any
    # non-local environment; a dev default keeps local boot working.
    jwt_secret: SecretStr = SecretStr("dev-insecure-change-me")
    jwt_algorithm: str = "HS256"
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days
    session_cookie_name: str = "pulse_session"
    # Cookie flags. Secure must be True behind HTTPS in production; SameSite=lax
    # works for the top-level redirect back from the OAuth provider.
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    session_cookie_domain: str | None = None
    # Base URLs used to build the OAuth redirect URI and the post-login bounce.
    # backend_base_url is where the provider redirects (…/api/auth/callback/{p});
    # frontend_base_url is where we send the browser after a successful login.
    backend_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    oauth_state_secret: SecretStr = SecretStr("dev-insecure-state-change-me")

    # Google OIDC. Both must be set for the Google button to work.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None

    # Apple Sign In. All four must be set for the Apple button to work; the
    # client secret is a short-lived JWT generated from the .p8 key at runtime.
    apple_client_id: str | None = None  # the Services ID (e.g. com.pulseai.web)
    apple_team_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: SecretStr | None = None  # contents of the .p8 file

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def apple_enabled(self) -> bool:
        return bool(
            self.apple_client_id
            and self.apple_team_id
            and self.apple_key_id
            and self.apple_private_key
        )

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
