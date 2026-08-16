from pathlib import Path

from mutagen.mp3 import MP3

from app.local_flow import LocalStore, generate_audio


def test_local_project_is_created_and_generated(tmp_path: Path) -> None:
    store = LocalStore(f"sqlite:///{tmp_path / 'local.db'}", str(tmp_path / "storage"))
    project = store.create_project(
        title="Demo",
        source_text="First sentence. Second sentence.",
        voice_id="en-US-AriaNeural",
        speech_rate="normal",
        author=None,
    )
    assert project.status == "queued"
    ready = generate_audio(project.id, store)
    assert ready.status == "ready"
    assert ready.output_path is not None
    assert MP3(ready.output_path).info.length > 0
    assert list((tmp_path / "storage").glob("*.mp3"))


def test_delete_project_removes_the_row(tmp_path: Path) -> None:
    store = LocalStore(f"sqlite:///{tmp_path / 'local.db'}", str(tmp_path / "storage"))
    project = store.create_project(title="Demo", source_text="Text", voice_id="voice", speech_rate="normal", author=None)
    store.delete_project(project.id)
    assert store.list_projects() == []
