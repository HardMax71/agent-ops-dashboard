from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # Database
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = Field(min_length=32)  # no default → required env var
    jwt_algorithm: str = "HS256"
    access_token_expire_seconds: int = 900
    refresh_token_expire_seconds: int = 604800
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/callback"
    github_token_encryption_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    internal_service_secret: str = Field(default="dev-internal-secret")

    # LLM
    openai_api_key: str = ""

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_project: str = "agent-ops-v1"
    langsmith_api_key: str = ""
    langsmith_org_id: str = ""
    langsmith_project_id: str = ""
    langsmith_webhook_secret: str = ""

    # External
    tavily_api_key: str = ""
    github_token: str = ""
    github_webhook_secret: str = ""

    # Chroma
    chroma_persist_dir: str = "/data/chroma"

    # Job limits
    default_cost_budget_usd: float = 0.20

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.environment not in ("development", "test"):
            if self.internal_service_secret == "dev-internal-secret":  # noqa: S105
                raise ValueError(
                    "internal_service_secret must be explicitly set in non-development environments"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
