from app.managed_worker import generate_managed_audio


class FakeAPI:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []
        self.uploads: list[tuple[str, bytes]] = []
        self.assets: list[dict[str, object]] = []

    def update_project_service(self, project_id, values):
        self.updates.append({"id": project_id, **values})

    def upload_asset_service(self, storage_path, content, content_type="audio/mpeg"):
        self.uploads.append((storage_path, content))

    def create_asset_service(self, asset):
        self.assets.append(asset)
        return {"id": "asset-1", **asset}


def test_managed_worker_generates_and_uploads_private_mp3() -> None:
    api = FakeAPI()
    generate_managed_audio(
        {"id": "project-1", "user_id": "user-1", "title": "Demo", "source_text": "Hello.", "voice_id": "voice"},
        api,
    )

    assert api.uploads[0][0] == "user-1/project-1.mp3"
    assert api.uploads[0][1].startswith(b"ID3")
    assert api.assets[0]["kind"] == "mp3"
    assert api.updates[0]["status"] == "generating"
    assert api.updates[-1]["status"] == "ready"
