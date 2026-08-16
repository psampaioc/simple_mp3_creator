import io
from pathlib import Path

from PIL import Image
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from app.media import (
    FakeTTSProvider,
    add_metadata,
    chunk_text,
    normalize_cover_art,
    normalize_text,
    synthesize_sync,
)


def test_normalize_text_and_chunking_are_stable() -> None:
    text = "  First\r\n line.\n\nSecond   line with words.  "
    assert normalize_text(text) == "First line.\n\nSecond line with words."
    assert normalize_text("Cafe\u0301") == "Café"
    assert chunk_text(text, max_chars=12) == ["First line.", "Second line", "with words."]


def test_fake_provider_and_metadata_are_deterministic(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    synthesize_sync(FakeTTSProvider(), "Hello   world", audio)
    assert MP3(str(audio)).info.length > 0
    add_metadata(audio, title="Title", artist="Artist", album="Album", year=2026, comment="Test")
    tags = ID3(str(audio))
    assert tags["TIT2"].text == ["Title"]
    assert tags["TPE1"].text == ["Artist"]
    assert tags["TALB"].text == ["Album"]
    assert str(tags["TDRC"].text[0]) == "2026"
    comment = next(frame for frame in tags.values() if frame.FrameID == "COMM")
    assert comment.text == ["Test"]


def test_cover_art_is_square_jpeg_and_attaches_as_apic(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (80, 40), (10, 20, 30, 255)).save(source)
    cover = normalize_cover_art(source.read_bytes(), max_size=64)
    audio = tmp_path / "audio.mp3"
    synthesize_sync(FakeTTSProvider(), "hello", audio)
    add_metadata(audio, title="T", artist="A", album="L", cover_art=cover)
    tags = ID3(str(audio))
    picture = next(frame for frame in tags.values() if frame.FrameID == "APIC")
    assert picture.mime == "image/jpeg"
    with Image.open(io.BytesIO(picture.data)) as image:
        assert image.size == (64, 32)
    assert picture.data.startswith(b"\xff\xd8")


def test_cover_art_only_crops_when_requested(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (80, 40), (10, 20, 30)).save(source)
    cover = normalize_cover_art(source.read_bytes(), max_size=64, square_crop=True)
    with Image.open(io.BytesIO(cover)) as image:
        assert image.size == (40, 40)
