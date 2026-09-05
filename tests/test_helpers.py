"""Unit tests for the pure helpers."""

from __future__ import annotations

from custom_components.soniox.helpers import (
    apply_audio_tag,
    build_context,
    expand_language_tags,
    normalize_language,
    parse_terms,
    pcm_to_wav,
    render_tokens,
    speaker_prefix,
)


def test_normalize_language() -> None:
    assert normalize_language("nl-NL") == "nl"
    assert normalize_language("en_US") == "en"
    assert normalize_language("de") == "de"
    assert normalize_language(None) == ""


def test_expand_language_tags() -> None:
    tags = expand_language_tags(("nl", "xx"))
    assert tags[:3] == ["nl", "nl-NL", "nl-BE"]
    assert "xx" in tags


def test_render_tokens_joins_without_separator_and_drops_control_tokens() -> None:
    tokens = [
        {"text": "Zet", "is_final": True},
        {"text": " de", "is_final": True},
        {"text": " lamp", "is_final": True},
        {"text": "<end>", "is_final": True},
        {"text": " aan", "is_final": False},
        {"text": "<fin>", "is_final": True},
    ]
    assert render_tokens(tokens) == "Zet de lamp"


def test_parse_terms_and_context() -> None:
    assert parse_terms(" Kewpie, koffiecups\nAlbert Heijn,,Kewpie ") == ["Kewpie", "koffiecups", "Albert Heijn"]
    assert build_context([], "") is None
    assert build_context(["Kewpie"], None) == {"terms": ["Kewpie"]}
    assert build_context(["Kewpie"], " huishoud ") == {"terms": ["Kewpie"], "text": "huishoud"}


def test_speaker_prefix() -> None:
    assert speaker_prefix("Lukas", 0.8, 0.5) == "[Speaker: Lukas] "
    assert speaker_prefix("Lukas", 0.4, 0.5) == ""
    assert speaker_prefix("unknown", 0.9, 0.5) == ""
    assert speaker_prefix(None, 0.9, 0.5) == ""


def test_pcm_to_wav_header() -> None:
    wav = pcm_to_wav(b"\x00\x01" * 8, sample_rate=16000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and wav[36:40] == b"data"
    assert len(wav) == 44 + 16
    assert int.from_bytes(wav[24:28], "little") == 16000


def test_apply_audio_tag() -> None:
    assert apply_audio_tag("Hallo", "excited") == "[excited] Hallo"
    assert apply_audio_tag("Hallo", "[Warm]") == "[warm] Hallo"
    assert apply_audio_tag("Hallo", "neutral") == "Hallo"
    assert apply_audio_tag("Hallo", None) == "Hallo"
    # inline tag written by the caller wins
    assert apply_audio_tag("[whispering] sst", "excited") == "[whispering] sst"
    # lead for the streaming path
    assert apply_audio_tag("", "calm") == "[calm] "
    assert apply_audio_tag("", "neutral") == ""
