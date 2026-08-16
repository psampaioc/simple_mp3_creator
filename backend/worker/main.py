"""Long-running Supabase job worker for self-hosted Piper TTS."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from app.managed_worker import generate_managed_audio_service
from app.settings import settings
from app.supabase_api import SupabaseAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("simple-mp3-worker")


def build_api() -> SupabaseAPI:
    return SupabaseAPI(settings.supabase_url, settings.supabase_publishable_key, secret_key=settings.supabase_secret_key)


def process_one(api: SupabaseAPI, worker_id: str) -> bool:
    job = api.claim_next_job_service(worker_id)
    if job is None:
        return False
    project = job.pop("project", None)
    if not isinstance(project, dict):
        logger.error("job_missing_project job_id=%s", job.get("id"))
        return True
    logger.info("job_claimed job_id=%s project_id=%s", job.get("id"), project.get("id"))
    try:
        generate_managed_audio_service(project, job, api)
    except Exception:
        logger.exception("job_failed job_id=%s project_id=%s", job.get("id"), project.get("id"))
    return True


def run() -> None:
    if settings.data_backend != "supabase":
        raise RuntimeError("The standalone worker requires DATA_BACKEND=supabase")
    if settings.tts_provider != "piper":
        raise RuntimeError("The standalone worker requires TTS_PROVIDER=piper")
    api = build_api()
    worker_id = f"{settings.worker_id}-{uuid4().hex[:8]}"
    logger.info("worker_started id=%s", worker_id)
    if settings.worker_once:
        process_one(api, worker_id)
        return
    while True:
        if not process_one(api, worker_id):
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
