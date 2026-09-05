"""Pure helpers for the Soniox integration (no Home Assistant imports, unit-testable)."""

from __future__ import annotations

import re
import struct
from typing import Any

from .const import LANGUAGE_TAGS

_SPECIAL_TOKEN = re.compile(r"^<[a-z_]+>$", re.IGNORECASE)


def normalize_language(language: str | None) -> str:
    """Turn a Home Assistant locale tag (``nl-NL``, ``en_US``) into a Soniox code (``nl``)."""
    if not language:
        return ""
    return language.lower().replace("_", "-").split("-", maxsplit=1)[0]


def expand_language_tags(languages: tuple[str, ...] | list[str]) -> list[str]:
    """Expand Soniox base codes into the locale tags Assist pipelines use."""
    expanded: list[str] = []
    for language in languages:
        for tag in LANGUAGE_TAGS.get(language, (language,)):
            if tag not in expanded:
                expanded.append(tag)
    return expanded


def render_tokens(tokens: list[dict[str, Any]]) -> str:
    """Join Soniox tokens into text.

    Tokens carry their own leading whitespace (``"Zet"``, ``" de"``, ``" lamp"``),
    so they are concatenated without a separator. Control tokens such as
    ``<end>``/``<fin>`` are dropped. Only final tokens count.
    """
    parts = [
        t["text"]
        for t in tokens
        if isinstance(t.get("text"), str) and t.get("is_final") and not _SPECIAL_TOKEN.match(t["text"])
    ]
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def parse_terms(raw: str | None) -> list[str]:
    """Split a comma/newline separated terms string into a clean list."""
    if not raw:
        return []
    seen: list[str] = []
    for part in re.split(r"[,\n]", raw):
        term = part.strip()
        if term and term not in seen:
            seen.append(term)
    return seen


def build_context(terms: list[str], text: str | None) -> dict[str, Any] | None:
    """Build the Soniox ``context`` object; ``None`` when there is nothing to send."""
    ctx: dict[str, Any] = {}
    if terms:
        ctx["terms"] = terms
    if text and text.strip():
        ctx["text"] = text.strip()
    return ctx or None


def speaker_prefix(speaker: str | None, confidence: float, threshold: float) -> str:
    """Return the ``[Speaker: NAME] `` prefix when the identification is trustworthy."""
    if not speaker or speaker.lower() == "unknown" or confidence < threshold:
        return ""
    return f"[Speaker: {speaker}] "


_LEADING_TAG = re.compile(r"^\s*\[[a-z][a-z -]*\]", re.IGNORECASE)


def apply_audio_tag(text: str, tag: str | None) -> str:
    """Prefix ``text`` with a Soniox audio tag such as ``[excited]``.

    ``neutral``/empty means no tag. A message that already starts with a tag
    is left alone, so inline tags written by the caller win over the default.
    """
    tag = (tag or "").strip().strip("[]").lower()
    if not tag or tag == "neutral" or _LEADING_TAG.match(text):
        return text
    return f"[{tag}] {text}" if text else f"[{tag}] "


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
    """Wrap raw little-endian PCM in a minimal RIFF/WAVE header."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        len(pcm),
    )
    return header + pcm


def wav_stream_header(sample_rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    """WAV header for a stream of unknown length (sizes 0xFFFFFFFF = read until close)."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        0xFFFFFFFF,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        0xFFFFFFFF,
    )
