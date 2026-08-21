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
        def cleanup_stale_jobs_service(self, queued_timeout_seconds, running_timeout_seconds):
            return 0

        def list_projects(self, token):
            return []

        def count_projects_since(self, token, created_since):
            return 0

        def create_project(self, token, project):
            assert token == "test-token"
            assert project["user_id"] == "user-1"
            return {"id": "project-1", **project}

        def create_job(self, token, job):
            assert token == "test-token"
            assert job["user_id"] == "user-1"
            return {"id": "job-1", **job}

        def update_project(self, token, project_id, values):
            return None

        def upload_asset(self, token, storage_path, content, content_type="audio/mpeg"):
            return None

        def create_asset(self, token, asset):
            return asset

    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "data_backend", "supabase")
    monkeypatch.setattr(main_module, "dispatch_media_worker", lambda job_id: None)
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


def test_managed_project_creation_marks_dispatch_failure_as_failed(monkeypatch) -> None:
    class FakeManagedAPI:
        def __init__(self):
            self.project_updates = []
            self.job_updates = []

        def cleanup_stale_jobs_service(self, queued_timeout_seconds, running_timeout_seconds):
            return 0

        def list_projects(self, token):
            return []

        def count_projects_since(self, token, created_since):
            return 0

        def create_project(self, token, project):
            return {"id": "project-1", **project}

        def create_job(self, token, job):
            return {"id": "job-1", **job}

        def update_project(self, token, project_id, values):
            self.project_updates.append((project_id, values))

        def update_job_service(self, job_id, values):
            self.job_updates.append((job_id, values))

        def record_generation_error_service(self, error):
            self.error = error

        def delete_project_service(self, project_id):
            self.deleted_project = project_id

    import app.main as main_module

    fake_api = FakeManagedAPI()
    monkeypatch.setattr(main_module.settings, "data_backend", "supabase")
    monkeypatch.setattr(main_module, "dispatch_media_worker", lambda job_id: (_ for _ in ()).throw(RuntimeError("GitHub unavailable")))
    monkeypatch.setattr(main_module, "managed_api", lambda: fake_api)
    app.dependency_overrides[main_module.optional_current_user] = lambda: CurrentUser("user-1", "authenticated", "test-token")
    try:
        response = TestClient(app).post(
            "/v1/projects",
            json={"title": "Managed", "text": "Hello world.", "voice_id": "en-US-AriaNeural"},
        )
    finally:
        app.dependency_overrides.clear()
        monkeypatch.setattr(main_module.settings, "data_backend", "local")

    assert response.status_code == 503
    assert response.json()["detail"] == "The audio worker could not be started. Please try again."
    assert fake_api.project_updates == [("project-1", {"status": "failed"})]
    assert fake_api.deleted_project == "project-1"
    assert fake_api.job_updates[0][0] == "job-1"
    assert fake_api.job_updates[0][1]["status"] == "failed"
    assert fake_api.job_updates[0][1]["error_code"] == "WORKER_DISPATCH_FAILED"


def test_managed_project_creation_allows_a_queued_generation(monkeypatch) -> None:
    class FakeManagedAPI:
        def cleanup_stale_jobs_service(self, queued_timeout_seconds, running_timeout_seconds):
            return 0

        def count_projects_since(self, token, created_since):
            return 0

        def create_project(self, token, project):
            return {"id": "project-2", **project}

        def create_job(self, token, job):
            return {"id": "job-2", **job}

    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "data_backend", "supabase")
    monkeypatch.setattr(main_module, "dispatch_media_worker", lambda job_id: None)
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
    assert response.json()["status"] == "queued"


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


def test_production_does_not_fall_back_to_local_media(monkeypatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "app_env", "production")
    monkeypatch.setattr(main_module.settings, "data_backend", "local")
    response = TestClient(app).post(
        "/v1/projects",
        json={"title": "Test", "text": "Hello", "voice_id": "en-US-AriaNeural", "speech_rate": "normal"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "managed media backend is not configured"
    monkeypatch.setattr(main_module.settings, "app_env", "development")


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
    assert client.get("/v1/voices?locale=pt-BR").json()[0]["id"] == "pt-BR-Faber"
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
