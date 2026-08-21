from pathlib import Path

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUser, current_user, optional_current_user
from app.github_actions import dispatch_media_worker
from app.local_flow import LocalStore, generate_audio, project_json
from app.media import normalize_text
from app.settings import settings

app = FastAPI(title="Simple MP3 Creator API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=10_000)
    voice_id: str = Field(min_length=1, max_length=120)
    speech_rate: str = Field(default="normal", pattern="^(slow|normal|fast)$")
    author: str | None = Field(default=None, max_length=200)
    output_format: str = Field(default="mp3", pattern="^mp3$")
    source_type: str | None = Field(default=None, pattern="^(txt|pdf|docx)$")
    source_storage_path: str | None = Field(default=None, max_length=300)
    source_filename: str | None = Field(default=None, max_length=255)
    source_content_type: str | None = Field(default=None, max_length=120)
    source_size_bytes: int | None = Field(default=None, gt=0)


class SourceFileCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0)


class ExtractedTextUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


VOICE_CATALOG = [
    {"id": "en-US-AriaNeural", "locale": "en-US", "label": "Aria · English (US)"},
    {"id": "pt-BR-Faber", "locale": "pt-BR", "label": "Faber · Português (Brasil)"},
]

SOURCE_TYPES = {
    ".txt": ("txt", "text/plain"),
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def local_store() -> LocalStore:
    store = getattr(app.state, "local_store", None)
    if store is None:
        store = LocalStore(settings.database_url, settings.storage_dir)
        app.state.local_store = store
    return store


def managed_api():
    from app.supabase_api import SupabaseAPI

    return SupabaseAPI(
        settings.supabase_url,
        settings.supabase_publishable_key,
        secret_key=settings.supabase_secret_key,
        service_role_key=settings.supabase_service_role_key,
    )


def managed_project_json(project: dict[str, object | None]) -> dict[str, object | None]:
    return {**project, "stage": project.get("status")}


ACTIVE_GENERATION_STATUSES = {"queued", "extracting", "generating", "tagging", "uploading"}


def enforce_generation_limits(api, user: CurrentUser) -> None:
    api.cleanup_stale_jobs_service(settings.queued_job_timeout_seconds, settings.running_job_timeout_seconds)
    created_since = datetime.now(timezone.utc) - timedelta(seconds=settings.generation_rate_limit_window_seconds)
    profile = api.get_profile(user.access_token, user.id) or {}
    plan = str(profile.get("plan") or "free")
    generation_limit = 20 if plan == "paid" else settings.generation_rate_limit_count
    recent_count = api.count_projects_since(user.access_token, created_since.isoformat())
    if recent_count >= generation_limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "GENERATION_LIMIT",
                "plan": plan,
                "limit": generation_limit,
                "window_minutes": settings.generation_rate_limit_window_seconds // 60,
                "message": f"The {plan} plan allows {generation_limit} generations per hour.",
            },
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/v1/internal/cleanup")
def cleanup_expired(authorization: str | None = Header(default=None)) -> dict[str, int]:
    if not settings.cron_secret or not authorization or not secrets.compare_digest(authorization, f"Bearer {settings.cron_secret}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid cleanup credentials")
    if settings.data_backend != "supabase":
        return {"assets": 0, "projects": 0}
    api = managed_api()
    assets = api.list_expired_assets_service()
    for asset in assets:
        api.delete_storage_object_service(str(asset["storage_path"]))
        api.delete_asset_service(str(asset["id"]))
    projects = api.list_expired_projects_service()
    for project in projects:
        api.delete_project_service(str(project["id"]))
    return {"assets": len(assets), "projects": len(projects)}


@app.get("/v1/voices")
def list_voices(locale: str | None = Query(default=None, max_length=16)) -> list[dict[str, str]]:
    if locale is None:
        return VOICE_CATALOG
    return [voice for voice in VOICE_CATALOG if voice["locale"] == locale]


@app.get("/v1/auth/me")
def authenticated_identity(user: CurrentUser = Depends(current_user)) -> dict[str, str]:
    """Small protected probe used by the frontend and auth integration tests."""
    return {"id": user.id, "role": user.role}


@app.post("/v1/source-files")
def create_source_file(payload: SourceFileCreate, user: CurrentUser | None = Depends(optional_current_user)) -> dict[str, object]:
    if settings.data_backend != "supabase":
        raise HTTPException(status_code=503, detail="document uploads require the managed media backend")
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    suffix = PurePath(payload.filename).suffix.lower()
    source_type = SOURCE_TYPES.get(suffix)
    if source_type is None or payload.content_type not in {source_type[1], "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="only .txt, .pdf, and .docx files are supported")
    if payload.size_bytes > settings.source_file_max_bytes:
        raise HTTPException(status_code=413, detail="document exceeds the 5 MB limit")
    storage_path = f"{user.id}/source/{uuid4().hex}{suffix}"
    target = managed_api().create_signed_upload_url(user.access_token, storage_path)
    return {**target, "source_type": source_type[0], "content_type": source_type[1], "max_size_bytes": settings.source_file_max_bytes}


@app.post("/v1/projects", status_code=status.HTTP_202_ACCEPTED)
def create_project(
    payload: ProjectCreate,
    background_tasks: BackgroundTasks,
    user: CurrentUser | None = Depends(optional_current_user),
) -> dict[str, object | None]:
    source_text = normalize_text(payload.text or "")
    has_source_file = payload.source_storage_path is not None
    if source_text and has_source_file:
        raise HTTPException(status_code=422, detail="choose pasted text or a source file, not both")
    if not source_text and not has_source_file:
        raise HTTPException(status_code=422, detail="text or a supported source file is required")
    if settings.app_env == "production" and settings.data_backend != "supabase":
        raise HTTPException(status_code=503, detail="managed media backend is not configured")
    if settings.data_backend == "supabase":
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        api = managed_api()
        enforce_generation_limits(api, user)
        locale = next((voice["locale"] for voice in VOICE_CATALOG if voice["id"] == payload.voice_id), "und")
        if has_source_file:
            if not payload.source_type or not payload.source_filename or not payload.source_content_type or not payload.source_size_bytes:
                raise HTTPException(status_code=422, detail="source file metadata is incomplete")
            if not payload.source_storage_path.startswith(f"{user.id}/source/"):
                raise HTTPException(status_code=403, detail="source file does not belong to the current user")
            if payload.source_size_bytes > settings.source_file_max_bytes or payload.source_type not in {"txt", "pdf", "docx"}:
                raise HTTPException(status_code=413, detail="source file is invalid or too large")
        project = api.create_project(
            user.access_token,
            {
                "user_id": user.id,
                "title": payload.title.strip(),
                "source_text": None if has_source_file else source_text,
                "character_count": None if has_source_file else len(source_text),
                "voice_id": payload.voice_id,
                "locale": locale,
                "speech_rate": payload.speech_rate,
                "author": payload.author,
                "output_format": payload.output_format,
                "status": "queued",
                "source_type": payload.source_type or "pasted",
                "source_storage_path": payload.source_storage_path,
                "source_filename": payload.source_filename,
                "source_content_type": payload.source_content_type,
                "extraction_status": "queued" if has_source_file else "not_needed",
            },
        )
        if has_source_file:
            asset = api.create_asset(
                user.access_token,
                {"project_id": project["id"], "user_id": user.id, "kind": "source_original", "storage_path": payload.source_storage_path, "content_type": payload.source_content_type, "size_bytes": payload.source_size_bytes},
            )
            api.update_project(user.access_token, str(project["id"]), {"source_asset_id": asset["id"]})
            project["source_asset_id"] = asset["id"]
        job = api.create_job(
            user.access_token,
            {"project_id": project["id"], "user_id": user.id, "status": "queued", "stage": "queued"},
        )
        try:
            dispatch_media_worker(str(job["id"]))
        except RuntimeError as error:
            # The project/job are created before dispatch so the worker can claim
            # them. If dispatch fails, do not leave an orphaned queued job that
            # will be restored as active forever after a page reload.
            api.update_project(user.access_token, str(project["id"]), {"status": "failed"})
            try:
                api.record_generation_error_service(
                    {
                        "project_id": str(project["id"]),
                        "user_id": user.id,
                        "error_code": "WORKER_DISPATCH_FAILED",
                        "error_detail": str(error)[:500],
                    }
                )
            except Exception:
                pass
            try:
                api.update_job_service(
                    str(job["id"]),
                    {
                        "status": "failed",
                        "stage": "failed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "error_code": "WORKER_DISPATCH_FAILED",
                        "error_detail": str(error)[:500],
                    },
                )
            except Exception:
                pass
            try:
                api.delete_project_service(str(project["id"]))
            except Exception:
                pass
            raise HTTPException(status_code=503, detail="The audio worker could not be started. Please try again.") from error
        return managed_project_json(project)
    project = local_store().create_project(
        title=payload.title.strip(),
        source_text=source_text,
        voice_id=payload.voice_id,
        speech_rate=payload.speech_rate,
        author=payload.author,
    )
    background_tasks.add_task(generate_audio, project.id, local_store())
    return project_json(project)


@app.patch("/v1/projects/{project_id}/source-text")
def update_extracted_text(project_id: str, payload: ExtractedTextUpdate, user: CurrentUser | None = Depends(optional_current_user)) -> dict[str, object | None]:
    if settings.data_backend != "supabase" or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    api = managed_api()
    project = api.get_project(user.access_token, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if project.get("status") != "review":
        raise HTTPException(status_code=409, detail="project is not awaiting text review")
    source_text = normalize_text(payload.text)
    if not source_text:
        raise HTTPException(status_code=422, detail="text must contain non-whitespace content")
    api.update_project(user.access_token, project_id, {"source_text": source_text, "character_count": len(source_text), "status": "queued", "extraction_status": "ready", "extraction_error": None})
    job = api.get_job_service(project_id)
    if job is None:
        raise HTTPException(status_code=500, detail="project job not found")
    api.update_job_service(str(job["id"]), {"status": "queued", "stage": "queued", "finished_at": None, "locked_at": None, "locked_by": None})
    try:
        dispatch_media_worker(str(job["id"]))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="media worker is not configured") from error
    updated = api.get_project(user.access_token, project_id)
    return managed_project_json(updated or project)


@app.get("/v1/projects")
def list_projects(user: CurrentUser | None = Depends(optional_current_user)) -> list[dict[str, object | None]]:
    if settings.data_backend == "supabase":
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        api = managed_api()
        api.cleanup_stale_jobs_service(settings.queued_job_timeout_seconds, settings.running_job_timeout_seconds)
        return [managed_project_json(project) for project in api.list_projects(user.access_token)]
    return [project_json(project) for project in local_store().list_projects()]


@app.get("/v1/projects/{project_id}")
def get_project(project_id: str, user: CurrentUser | None = Depends(optional_current_user)) -> dict[str, object | None]:
    if settings.data_backend == "supabase":
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        project = managed_api().get_project(user.access_token, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return managed_project_json(project)
    try:
        return project_json(local_store().get_project(project_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error


@app.post("/v1/projects/{project_id}/retry")
def retry_project(project_id: str, background_tasks: BackgroundTasks) -> dict[str, object | None]:
    store = local_store()
    try:
        project = store.get_project(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    if project.status != "failed":
        raise HTTPException(status_code=409, detail="only failed projects can be retried")
    store.queue_project(project_id)
    background_tasks.add_task(generate_audio, project_id, store)
    return project_json(store.get_project(project_id))


@app.delete("/v1/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str) -> None:
    store = local_store()
    try:
        project = store.get_project(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    store.delete_project(project_id)
    if project.output_path:
        Path(project.output_path).unlink(missing_ok=True)


@app.get("/v1/projects/{project_id}/download", response_model=None)
def download_project(project_id: str, user: CurrentUser | None = Depends(optional_current_user)) -> FileResponse | dict[str, str]:
    if settings.data_backend == "supabase":
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        project = managed_api().get_project(user.access_token, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        if project.get("status") != "ready":
            raise HTTPException(status_code=409, detail="project audio is not ready")
        asset = managed_api().get_mp3_asset(user.access_token, project_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="project audio not found")
        filename = "".join(character if character.isalnum() or character in "-_ " else "_" for character in str(project.get("title") or "audio")).strip() or "audio"
        return {"url": managed_api().create_signed_url(user.access_token, str(asset["storage_path"])), "filename": f"{filename}.mp3"}
    try:
        project = local_store().get_project(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    if project.status != "ready" or not project.output_path or not Path(project.output_path).is_file():
        raise HTTPException(status_code=409, detail="project audio is not ready")
    filename = "".join(character if character.isalnum() or character in "-_ " else "_" for character in project.title).strip() or "audio"
    return FileResponse(project.output_path, media_type="audio/mpeg", filename=f"{filename}.mp3")
