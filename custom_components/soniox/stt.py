"""Speech-to-text platform for Soniox."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from typing import Any

from homeassistant.components import stt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonioxConfigEntry
from .api import SonioxError
from .const import (
    AUTO_LANGUAGE,
    CONF_CONTEXT_TERMS,
    CONF_CONTEXT_TEXT,
    CONF_LANGUAGE,
    CONF_SPEAKER_ID_URL,
    CONF_SPEAKER_THRESHOLD,
    CONF_STT_MODEL,
    DEFAULT_SPEAKER_THRESHOLD,
    DEFAULT_STT_MODEL,
    DOMAIN,
    LOGGER,
    TITLE,
)
from .helpers import build_context, expand_language_tags, normalize_language, parse_terms, speaker_prefix


async def async_setup_entry(
    hass: HomeAssistant, entry: SonioxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Soniox STT entity."""
    async_add_entities([SonioxSttEntity(entry)])


class SonioxSttEntity(stt.SpeechToTextEntity):
    """Streams Assist audio to Soniox real-time STT."""

    _attr_has_entity_name = True
    _attr_translation_key = "speech_to_text"

    def __init__(self, entry: SonioxConfigEntry) -> None:
        """Initialise from the config entry."""
        self._entry = entry
        self._client = entry.runtime_data.client
        self._languages = entry.runtime_data.stt_languages
        self._attr_unique_id = f"{entry.entry_id}_stt"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Soniox",
            "model": "Real-time STT + TTS",
            "name": TITLE,
            "entry_type": "service",
        }

    @property
    def _fixed_language(self) -> str | None:
        lang = self._entry.options.get(CONF_LANGUAGE, AUTO_LANGUAGE)
        return None if lang == AUTO_LANGUAGE else lang

    @property
    def supported_languages(self) -> list[str]:
        """Locale tags Assist may pick."""
        if self._fixed_language:
            return expand_language_tags((self._fixed_language,))
        return expand_language_tags(self._languages)

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Container formats."""
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Codecs."""
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Bit depths."""
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Sample rates."""
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Channel layouts."""
        return [stt.AudioChannels.CHANNEL_MONO]

    def check_metadata(self, metadata: stt.SpeechMetadata) -> bool:
        """Accept regional variants of a supported base language."""
        if (
            metadata.format not in self.supported_formats
            or metadata.codec not in self.supported_codecs
            or metadata.bit_rate not in self.supported_bit_rates
            or metadata.sample_rate not in self.supported_sample_rates
            or metadata.channel not in self.supported_channels
        ):
            return False
        base = normalize_language(metadata.language)
        if self._fixed_language:
            return base == self._fixed_language
        return base in self._languages

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Transcribe one utterance."""
        opts = self._entry.options
        language = self._fixed_language or normalize_language(metadata.language) or None
        context = build_context(parse_terms(opts.get(CONF_CONTEXT_TERMS)), opts.get(CONF_CONTEXT_TEXT))
        speaker_url = (opts.get(CONF_SPEAKER_ID_URL) or "").strip()

        try:
            text, pcm = await self._client.async_transcribe(
                stream,
                language=language,
                model=opts.get(CONF_STT_MODEL, DEFAULT_STT_MODEL),
                sample_rate=int(metadata.sample_rate),
                context=context,
                capture_audio=bool(speaker_url),
            )
        except SonioxError as err:
            LOGGER.error("Soniox STT failed (language=%s): %s", language, err)
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Unexpected Soniox STT error")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        if not text:
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        if speaker_url and pcm:
            speaker, confidence = await self._client.async_identify_speaker(speaker_url, pcm, int(metadata.sample_rate))
            threshold = float(opts.get(CONF_SPEAKER_THRESHOLD, DEFAULT_SPEAKER_THRESHOLD))
            prefix = speaker_prefix(speaker, confidence, threshold)
            LOGGER.debug("speaker-id: %s (%.2f) → %r", speaker, confidence, prefix)
            text = f"{prefix}{text}"

        return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the active configuration for debugging."""
        return {
            "model": self._entry.options.get(CONF_STT_MODEL, DEFAULT_STT_MODEL),
            "language_mode": self._entry.options.get(CONF_LANGUAGE, AUTO_LANGUAGE),
            "context_terms": len(parse_terms(self._entry.options.get(CONF_CONTEXT_TERMS))),
            "speaker_id": bool((self._entry.options.get(CONF_SPEAKER_ID_URL) or "").strip()),
        }
