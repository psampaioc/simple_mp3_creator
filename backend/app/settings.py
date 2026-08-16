from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/local.db"
    storage_dir: str = "./data/storage"
    tts_provider: str = "fake"
    edge_tts_voice: str = "en-US-AriaNeural"
    cors_origins: str = "http://localhost:3000"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    # Backward-compatible fallback for projects still using the legacy key.
    supabase_service_role_key: str = ""
    data_backend: str = "local"
    cron_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
