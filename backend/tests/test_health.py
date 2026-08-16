from fastapi.testclient import TestClient

from app.main import app
from app.local_flow import LocalStore
from app.auth import CurrentUser


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_authenticated_identity_requires_bearer_token() -> None:
    response = TestClient(app).get("/v1/auth/me")
    assert response.status_code == 401


def test_cleanup_requires_cron_secret() -> None:
    response = TestClient(app).get("/v1/internal/cleanup")
    assert response.status_code == 401


def test_managed_project_creation_uses_authenticated_user(monkeypatch) -> None:
    class FakeManagedAPI:
        def create_project(self, token, project):
            assert token == "test-token"
            assert project["user_id"] == "user-1"
            return {"id": "project-1", **project}

        def create_job(self, token, job):
            assert token == "test-token"
            assert job["user_id"] == "user-1"
            return job

        def update_project(self, token, project_id, values):
            return None

        def upload_asset(self, token, storage_path, content, content_type="audio/mpeg"):
            return None

        def create_asset(self, token, asset):
            return asset

    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "data_backend", "supabase")
    monkeypatch.setattr(main_module, "managed_api", lambda: FakeManagedAPI())
    app.dependency_overrides[main_module.optional_current_user] = lambda: CurrentUser("user-1", "authenticated", "test-token")
    try:
        response = TestClient(app).post(
            "/v1/projects",
            json={"title": "Managed", "text": "Hello world.", "voice_id": "en-US-AriaNeural"},
        )
    finally:
        app.dependency_overrides.clear()
        monkeypatch.setattr(main_module.settings, "data_backend", "local")

    assert response.status_code == 202
    assert response.json()["id"] == "project-1"


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


def test_voices_and_download_endpoints(tmp_path, monkeypatch) -> None:
    app.state.local_store = LocalStore(f"sqlite:///{tmp_path / 'local.db'}", str(tmp_path / "storage"))
    client = TestClient(app)
    assert client.get("/v1/voices?locale=pt-BR").json()[0]["id"] == "pt-BR-FranciscaNeural"
    response = client.post(
        "/v1/projects",
        json={"title": "My recording", "text": "Hello world.", "voice_id": "voice"},
    )
    project_id = response.json()["id"]
    download = client.get(f"/v1/projects/{project_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "audio/mpeg"
    assert download.content.startswith(b"ID3") or len(download.content) > 100
    monkeypatch.setattr(app.state, "local_store", None, raising=False)
