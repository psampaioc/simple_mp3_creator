from fastapi.testclient import TestClient

from app.main import app
from app.local_flow import LocalStore


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_project_api_uses_local_job_flow(tmp_path, monkeypatch) -> None:
    app.state.local_store = LocalStore(f"sqlite:///{tmp_path / 'local.db'}", str(tmp_path / "storage"))
    response = TestClient(app).post(
        "/v1/projects",
        json={"title": "Demo", "text": "Hello world.", "voice_id": "voice", "speech_rate": "normal"},
    )
    assert response.status_code == 202
    project_id = response.json()["id"]
    project = TestClient(app).get(f"/v1/projects/{project_id}")
    assert project.status_code == 200
    assert project.json()["status"] == "ready"
    monkeypatch.setattr(app.state, "local_store", None, raising=False)


def test_project_api_rejects_empty_text(tmp_path, monkeypatch) -> None:
    app.state.local_store = LocalStore(f"sqlite:///{tmp_path / 'local.db'}", str(tmp_path / "storage"))
    response = TestClient(app).post(
        "/v1/projects",
        json={"title": "Demo", "text": " \n ", "voice_id": "voice"},
    )
    assert response.status_code == 422
    monkeypatch.setattr(app.state, "local_store", None, raising=False)
