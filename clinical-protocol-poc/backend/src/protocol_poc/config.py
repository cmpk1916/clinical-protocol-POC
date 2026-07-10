from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    database_url: str = "postgresql+psycopg://protocol_poc:protocol_poc@postgres:5432/protocol_poc"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    storage_bucket: str = "protocol-inputs"
    local_storage_path: str = "/tmp/protocol-poc-inputs"
    max_upload_bytes: int = 25 * 1024 * 1024
    max_zip_entries: int = 1_000
    max_zip_entry_bytes: int = 10 * 1024 * 1024
    max_zip_total_bytes: int = 50 * 1024 * 1024
    max_zip_compression_ratio: float = 100.0
    identity_hmac_secret: str = ""
    identity_replay_window_seconds: int = 300
    allow_insecure_identity_headers: bool = False
    environment: str = "production"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
