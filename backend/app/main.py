from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUser, current_user
from app.local_flow import LocalStore, generate_audio, project_json
from app.media import normalize_text
from app.settings import settings

app = FastAPI(title="Simple MP3 Creator API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10_000)
    voice_id: str = Field(min_length=1, max_length=120)
    speech_rate: str = Field(default="normal", pattern="^(slow|normal|fast)$")
    author: str | None = Field(default=None, max_length=200)
    output_format: str = Field(default="mp3", pattern="^mp3$")


VOICE_CATALOG = [
    {"id": "en-US-AriaNeural", "locale": "en-US", "label": "Aria · English (US)"},
    {"id": "pt-BR-FranciscaNeural", "locale": "pt-BR", "label": "Francisca · Português (Brasil)"},
]


def local_store() -> LocalStore:
    store = getattr(app.state, "local_store", None)
    if store is None:
        store = LocalStore(settings.database_url, settings.storage_dir)
        app.state.local_store = store
    return store


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/v1/voices")
def list_voices(locale: str | None = Query(default=None, max_length=16)) -> list[dict[str, str]]:
    if locale is None:
        return VOICE_CATALOG
    return [voice for voice in VOICE_CATALOG if voice["locale"] == locale]


@app.get("/v1/auth/me")
def authenticated_identity(user: CurrentUser = Depends(current_user)) -> dict[str, str]:
    """Small protected probe used by the frontend and auth integration tests."""
    return {"id": user.id, "role": user.role}


@app.post("/v1/projects", status_code=status.HTTP_202_ACCEPTED)
def create_project(payload: ProjectCreate, background_tasks: BackgroundTasks) -> dict[str, object | None]:
    source_text = normalize_text(payload.text)
    if not source_text:
        raise HTTPException(status_code=422, detail="text must contain non-whitespace content")
    project = local_store().create_project(
        title=payload.title.strip(),
        source_text=source_text,
        voice_id=payload.voice_id,
        speech_rate=payload.speech_rate,
        author=payload.author,
    )
    background_tasks.add_task(generate_audio, project.id, local_store())
    return project_json(project)


@app.get("/v1/projects")
def list_projects() -> list[dict[str, object | None]]:
    return [project_json(project) for project in local_store().list_projects()]


@app.get("/v1/projects/{project_id}")
def get_project(project_id: str) -> dict[str, object | None]:
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


@app.get("/v1/projects/{project_id}/download")
def download_project(project_id: str) -> FileResponse:
    try:
        project = local_store().get_project(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    if project.status != "ready" or not project.output_path or not Path(project.output_path).is_file():
        raise HTTPException(status_code=409, detail="project audio is not ready")
    filename = "".join(character if character.isalnum() or character in "-_ " else "_" for character in project.title).strip() or "audio"
    return FileResponse(project.output_path, media_type="audio/mpeg", filename=f"{filename}.mp3")
