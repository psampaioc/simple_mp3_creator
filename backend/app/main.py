from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from app.local_flow import LocalStore, generate_audio, project_json
from app.media import normalize_text
from app.settings import settings

app = FastAPI(title="Simple MP3 Creator API", version="0.1.0")


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10_000)
    voice_id: str = Field(min_length=1, max_length=120)
    speech_rate: str = Field(default="normal", pattern="^(slow|normal|fast)$")
    author: str | None = Field(default=None, max_length=200)


def local_store() -> LocalStore:
    store = getattr(app.state, "local_store", None)
    if store is None:
        store = LocalStore(settings.database_url, settings.storage_dir)
        app.state.local_store = store
    return store


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


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
