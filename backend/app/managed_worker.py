"""Managed media worker adapter; execution can later move to a durable queue."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from mutagen.mp3 import MP3

from app.media import FakeTTSProvider, add_metadata, chunk_text, synthesize_sync


class ManagedMediaAPI(Protocol):
    def update_project(self, access_token: str, project_id: str, values: dict[str, object]) -> None: ...
    def upload_asset(self, access_token: str, storage_path: str, content: bytes, content_type: str = "audio/mpeg") -> None: ...
    def create_asset(self, access_token: str, asset: dict[str, object]) -> dict[str, object]: ...
    def upload_asset_service(self, storage_path: str, content: bytes, content_type: str = "audio/mpeg") -> None: ...
    def create_asset_service(self, asset: dict[str, object]) -> dict[str, object]: ...
    def update_project_service(self, project_id: str, values: dict[str, object]) -> None: ...


def generate_managed_audio(project: dict[str, object], api: ManagedMediaAPI, access_token: str) -> None:
    project_id = str(project["id"])
    user_id = str(project["user_id"])
    try:
        api.update_project(access_token, project_id, {"status": "generating"})
        with tempfile.TemporaryDirectory(prefix=f"managed-{project_id}-") as temp:
            root = Path(temp)
            parts: list[Path] = []
            for index, text in enumerate(chunk_text(str(project["source_text"]))):
                part = root / f"part-{index:04d}.mp3"
                synthesize_sync(FakeTTSProvider(), text, part)
                parts.append(part)
            if not parts:
                raise ValueError("empty text")
            output = root / "output.mp3"
            if len(parts) == 1:
                parts[0].replace(output)
            else:
                manifest = root / "parts.txt"
                manifest.write_text("\n".join(f"file '{part}'" for part in parts), encoding="utf-8")
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-y", str(output)], check=True, capture_output=True)
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
