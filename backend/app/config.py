from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="WASP_", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://wasp:wasp@localhost:5432/wasp"
    redis_url: str = "redis://localhost:6379/0"
    celery_eager: bool = False

    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "wasp"
    s3_secret_key: str = "wasp-secret"
    s3_bucket: str = "wasp-documents"

    jwt_secret: str = "dev-only-insecure-secret-change-me-0000"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 8

    cors_origins: list[str] = ["http://localhost:5173"]

    # Extracted values below this confidence are flagged for human verification.
    low_confidence_threshold: float = 0.80

    # Local ONNX embedding model (fastembed, no GPU/torch). Dimension must match the model.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    model_cache_dir: str = "/models"


@lru_cache
def get_settings() -> Settings:
    return Settings()
