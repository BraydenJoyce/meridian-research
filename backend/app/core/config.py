from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_version: str = "0.1.0"
    debug: bool = False
    app_base_url: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/meridian"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # AI providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_planner_model: str = "claude-sonnet-4-20250514"
    anthropic_writer_model: str = "claude-sonnet-4-20250514"
    anthropic_critic_model: str = "claude-sonnet-4-20250514"
    anthropic_hypothesis_model: str = "claude-sonnet-4-20250514"
    anthropic_metrics_model: str = "claude-sonnet-4-20250514"
    anthropic_strategist_model: str = "claude-sonnet-4-20250514"

    # Search
    tavily_api_key: str = ""

    # Modal CV inference
    modal_base_url: str = "local"
    modal_api_secret: str = ""

    # News APIs
    newsapi_key: str = ""
    gnews_key: str = ""

    # Auth
    supabase_jwt_secret: str = ""

    # Monitoring
    sentry_dsn: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000"]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


settings = Settings()
