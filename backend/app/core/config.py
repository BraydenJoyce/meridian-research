from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_version: str = "0.1.0"
    debug: bool = False

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

    # Search
    tavily_api_key: str = ""

    # Modal CV inference
    modal_base_url: str = "local"
    modal_api_secret: str = ""

    # News APIs
    newsapi_key: str = ""
    gnews_key: str = ""

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
