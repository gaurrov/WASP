from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="WASP_", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://wasp:wasp@localhost:5432/wasp"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "wasp"
    s3_secret_key: str = "wasp-secret"
    s3_bucket: str = "wasp-documents"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 8

    cors_origins: list[str] = ["http://localhost:5173"]

    # Embedding size for regulatory chunks; must match the embedding model chosen in M3.
    embedding_dim: int = 768


@lru_cache
def get_settings() -> Settings:
    return Settings()
