"""Deterministic building blocks for turning text and artwork into MP3 assets."""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps


def normalize_text(text: str) -> str:
    """Normalize line endings and whitespace without changing word order."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [" ".join(paragraph.split()) for paragraph in re.split(r"\n\s*\n", text)]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def chunk_text(text: str, max_chars: int = 4_000) -> list[str]:
    """Split normalized text at paragraph/sentence/word boundaries."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    normalized = normalize_text(text)
    if not normalized:
        return []
    chunks: list[str] = []
    current = ""
    units = re.split(r"(?<=[.!?])\s+|\n\n+", normalized)
    for unit in (part.strip() for part in units):
        if not unit:
            continue
        words = unit.split()
        while words:
            candidate = " ".join(words)
            if len(candidate) <= max_chars:
                addition = candidate if not current else f"{current} {candidate}"
                if len(addition) <= max_chars:
                    current = addition
                    words = []
                    continue
            if current:
                chunks.append(current)
                current = ""
                continue
            # A single oversized sentence is split only at word boundaries.
            piece = words.pop(0)
            while words and len(f"{piece} {words[0]}") <= max_chars:
                piece = f"{piece} {words.pop(0)}"
            chunks.append(piece)
    if current:
        chunks.append(current)
    return chunks


class TTSProvider(Protocol):
    async def synthesize(self, text: str, output_path: Path) -> None: ...


@dataclass(frozen=True)
class FakeTTSProvider:
    """Write a stable local placeholder for deterministic tests."""

    marker: bytes = b"SIMPLE-MP3-CREATOR-FAKE-AUDIO\n"

    async def synthesize(self, text: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.marker + normalize_text(text).encode("utf-8"))


@dataclass(frozen=True)
class EdgeTTSProvider:
    voice: str

    async def synthesize(self, text: str, output_path: Path) -> None:
        import edge_tts

        output_path.parent.mkdir(parents=True, exist_ok=True)
        await edge_tts.Communicate(text, self.voice).save(str(output_path))


def synthesize_sync(provider: TTSProvider, text: str, output_path: Path) -> None:
    asyncio.run(provider.synthesize(text, output_path))


def normalize_cover_art(source: bytes, size: tuple[int, int] = (1400, 1400)) -> bytes:
    """Center-crop artwork to a square JPEG with a stable RGB color mode."""
    with Image.open(io.BytesIO(source)) as image:
        image = ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=False, progressive=False)
        return output.getvalue()


def add_metadata(
    mp3_path: Path,
    *,
    title: str,
    artist: str,
    album: str,
    cover_art: bytes | None = None,
) -> None:
    """Write ID3 metadata and optional attached picture without changing audio."""
    from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TIT2, TPE1

    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("TALB")
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    if cover_art is not None:
        tags.delall("APIC:")
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_art))
    tags.save(str(mp3_path), v2_version=3)
