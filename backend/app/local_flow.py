"""Local SQLite project/job flow used before the managed Supabase boundary."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.media import FakeTTSProvider, add_metadata, chunk_text, synthesize_sync


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Project:
    id: str
    title: str
    source_text: str
    voice_id: str
    speech_rate: str
    author: str | None
    status: str
    stage: str
    output_path: str | None
    error_code: str | None


class LocalStore:
    def __init__(self, database_url: str, storage_dir: str) -> None:
        self.database_path = self._database_path(database_url)
        self.storage_dir = Path(storage_dir)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _database_path(database_url: str) -> Path:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("local flow requires a sqlite database URL")
        path = database_url.removeprefix(prefix)
        return Path(path).resolve()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    voice_id TEXT NOT NULL,
                    speech_rate TEXT NOT NULL,
                    author TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    output_path TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                """
            )

    def create_project(
        self,
        *,
        title: str,
        source_text: str,
        voice_id: str,
        speech_rate: str,
        author: str | None,
    ) -> Project:
        project_id = str(uuid.uuid4())
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', NULL, NULL, ?, ?)",
                (project_id, title, source_text, voice_id, speech_rate, author, now, now),
            )
            connection.execute(
                "INSERT INTO jobs (id, project_id, status, created_at) VALUES (?, ?, 'queued', ?)",
                (str(uuid.uuid4()), project_id, now),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> Project:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        return Project(**{key: row[key] for key in Project.__annotations__})

    def list_projects(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [Project(**{key: row[key] for key in Project.__annotations__}) for row in rows]

    def mark_generating(self, project_id: str) -> None:
        self._update(project_id, "generating", "generating", None)

    def queue_project(self, project_id: str) -> None:
        self._update(project_id, "queued", "queued", None, None)
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'queued', error_code = NULL, finished_at = NULL WHERE project_id = ?",
                (project_id,),
            )

    def mark_ready(self, project_id: str, output_path: Path) -> None:
        self._update(project_id, "ready", "ready", str(output_path))
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'ready', finished_at = ? WHERE project_id = ?",
                (utc_now(), project_id),
            )

    def mark_failed(self, project_id: str, error_code: str) -> None:
        self._update(project_id, "failed", "failed", None, error_code)
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'failed', error_code = ?, finished_at = ? WHERE project_id = ?",
                (error_code, utc_now(), project_id),
            )

    def delete_project(self, project_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def _update(
        self,
        project_id: str,
        status: str,
        stage: str,
        output_path: str | None,
        error_code: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE projects SET status = ?, stage = ?, output_path = ?, error_code = ?, updated_at = ? WHERE id = ?",
                (status, stage, output_path, error_code, utc_now(), project_id),
            )


def generate_audio(project_id: str, store: LocalStore) -> Project:
    project = store.get_project(project_id)
    store.mark_generating(project_id)
    try:
        output_path = store.storage_dir / f"{project_id}.mp3"
        with tempfile.TemporaryDirectory(prefix=f"mp3-{project_id}-") as temp_dir:
            parts: list[Path] = []
            for index, text in enumerate(chunk_text(project.source_text)):
                part = Path(temp_dir) / f"part-{index:04d}.mp3"
                synthesize_sync(FakeTTSProvider(), text, part)
                parts.append(part)
            if not parts:
                raise ValueError("empty text")
            if len(parts) == 1:
                parts[0].replace(output_path)
            else:
                manifest = Path(temp_dir) / "parts.txt"
                manifest.write_text("\n".join(f"file '{part}'" for part in parts), encoding="utf-8")
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-y", str(output_path)],
                    check=True,
                    capture_output=True,
                )
        add_metadata(output_path, title=project.title, artist=project.author or project.voice_id, album="Simple MP3 Creator")
        store.mark_ready(project_id, output_path)
    except Exception:
        store.mark_failed(project_id, "GENERATION_FAILED")
        raise
    return store.get_project(project_id)


def project_json(project: Project) -> dict[str, object | None]:
    return json.loads(json.dumps(project.__dict__))
