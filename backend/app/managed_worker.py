"""Managed media generation shared by the standalone worker."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from mutagen.mp3 import MP3

from app.media import EdgeTTSProvider, FakeTTSProvider, PiperTTSProvider, add_metadata, normalize_text, synthesize_sync
from app.settings import settings


class ManagedMediaAPI(Protocol):
    def update_project(self, access_token: str, project_id: str, values: dict[str, object]) -> None: ...
    def upload_asset(self, access_token: str, storage_path: str, content: bytes, content_type: str = "audio/mpeg") -> None: ...
    def create_asset(self, access_token: str, asset: dict[str, object]) -> dict[str, object]: ...
    def upload_asset_service(self, storage_path: str, content: bytes, content_type: str = "audio/mpeg") -> None: ...
    def create_asset_service(self, asset: dict[str, object]) -> dict[str, object]: ...
    def update_project_service(self, project_id: str, values: dict[str, object]) -> None: ...
    def update_job_service(self, job_id: str, values: dict[str, object]) -> None: ...


def generate_managed_audio(project: dict[str, object], api: ManagedMediaAPI, access_token: str) -> None:
    project_id = str(project["id"])
    user_id = str(project["user_id"])
    try:
        api.update_project(access_token, project_id, {"status": "generating"})
        with tempfile.TemporaryDirectory(prefix=f"managed-{project_id}-") as temp:
            root = Path(temp)
            output = root / "output.mp3"
            source_text = normalize_text(str(project["source_text"]))
            if not source_text:
                raise ValueError("empty text")
            if settings.tts_provider == "edge-tts":
                synthesize_sync(EdgeTTSProvider(str(project["voice_id"])), source_text, output)
            else:
                synthesize_sync(FakeTTSProvider(), source_text, output)
            add_metadata(output, title=str(project["title"]), artist=str(project.get("author") or project["voice_id"]), album="Simple MP3 Creator")
            audio = MP3(str(output))
            content = output.read_bytes()
            path = f"{user_id}/{project_id}.mp3"
            api.upload_asset(access_token, path, content)
            asset = api.create_asset(access_token, {"project_id": project_id, "user_id": user_id, "kind": "mp3", "storage_path": path, "content_type": "audio/mpeg", "size_bytes": len(content)})
            api.update_project(access_token, project_id, {"status": "ready", "duration_ms": round(audio.info.length * 1000), "output_size_bytes": len(content), "output_bitrate": audio.info.bitrate, "cover_asset_id": None})
            del asset
    except Exception:
        api.update_project(access_token, project_id, {"status": "failed"})
        raise


def generate_managed_audio_service(project: dict[str, object], job: dict[str, object], api: ManagedMediaAPI) -> None:
    """Generate one claimed job without carrying a user's JWT into the worker."""
    project_id = str(project["id"])
    job_id = str(job["id"])
    user_id = str(project["user_id"])
    try:
        api.update_project_service(project_id, {"status": "generating"})
        api.update_job_service(job_id, {"status": "generating", "stage": "generating", "started_at": datetime.now(timezone.utc).isoformat()})
        with tempfile.TemporaryDirectory(prefix=f"managed-{project_id}-") as temp:
            root = Path(temp)
            output = root / "output.mp3"
            source_text = normalize_text(str(project["source_text"]))
            if not source_text:
                raise ValueError("empty text")
            if settings.tts_provider == "piper":
                synthesize_sync(PiperTTSProvider(settings.piper_model_path), source_text, output)
            elif settings.tts_provider == "edge-tts":
                synthesize_sync(EdgeTTSProvider(str(project["voice_id"])), source_text, output)
            else:
                synthesize_sync(FakeTTSProvider(), source_text, output)
            api.update_job_service(job_id, {"stage": "tagging"})
            add_metadata(output, title=str(project["title"]), artist=str(project.get("author") or project["voice_id"]), album="Simple MP3 Creator")
            audio = MP3(str(output))
            content = output.read_bytes()
            path = f"{user_id}/{project_id}.mp3"
            api.update_job_service(job_id, {"stage": "uploading"})
            api.upload_asset_service(path, content)
            api.create_asset_service({"project_id": project_id, "user_id": user_id, "kind": "mp3", "storage_path": path, "content_type": "audio/mpeg", "size_bytes": len(content)})
            api.update_project_service(project_id, {"status": "ready", "duration_ms": round(audio.info.length * 1000), "output_size_bytes": len(content), "output_bitrate": audio.info.bitrate, "cover_asset_id": None})
            api.update_job_service(job_id, {"status": "ready", "stage": "ready", "finished_at": datetime.now(timezone.utc).isoformat(), "error_code": None, "error_detail": None})
    except Exception as error:
        api.update_project_service(project_id, {"status": "failed"})
        api.update_job_service(job_id, {"status": "failed", "stage": "failed", "finished_at": datetime.now(timezone.utc).isoformat(), "error_code": type(error).__name__, "error_detail": str(error)[:500]})
        raise
