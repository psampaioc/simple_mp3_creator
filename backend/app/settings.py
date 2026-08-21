from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/local.db"
    storage_dir: str = "./data/storage"
    tts_provider: str = "fake"
    piper_model_path: str = "./models/en_US-amy-low.onnx"
    worker_poll_seconds: float = 2.0
    worker_id: str = "simple-mp3-worker"
    worker_once: bool = False
    worker_job_id: str = ""
    github_actions_token: str = ""
    github_repository: str = "psampaioc/simple_mp3_creator"
    github_worker_workflow: str = "media-worker.yml"
    edge_tts_voice: str = "en-US-AriaNeural"
    cors_origins: str = "http://localhost:3000"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    # Backward-compatible fallback for projects still using the legacy key.
    supabase_service_role_key: str = ""
    data_backend: str = "local"
    cron_secret: str = ""
    source_file_max_bytes: int = 5 * 1024 * 1024
    generation_rate_limit_count: int = 5
    generation_rate_limit_window_seconds: int = 3600
    # GitHub Actions can wait behind the previous single-worker run.
    queued_job_timeout_seconds: int = 3600
    running_job_timeout_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def piper_model_path_for_locale(locale: str | None) -> str:
    """Return the bundled Piper model matching the project's language."""
    if locale == "pt-BR":
        return str(Path(settings.piper_model_path).with_name("pt_BR-cadu-medium.onnx"))
    return settings.piper_model_path
