"""Text-to-speech platform for Soniox."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TTSAudioRequest,
    TTSAudioResponse,
    TtsAudioType,
    Voice,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonioxConfigEntry
from .api import SonioxApiError, SonioxAuthError, SonioxConnectionError, SonioxError
from .const import (
    ATTR_SPEED,
    CONF_TTS_MODEL,
    CONF_TTS_SPEED,
    CONF_TTS_VOICE,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_SPEED,
    DOMAIN,
    LOGGER,
    TITLE,
    TTS_SPEED_MAX,
    TTS_SPEED_MIN,
    TTS_STREAM_SAMPLE_RATE,
)
from .helpers import expand_language_tags, normalize_language, wav_stream_header


async def async_setup_entry(
    hass: HomeAssistant, entry: SonioxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Soniox TTS entity."""
    async_add_entities([SonioxTtsEntity(hass, entry)])


class SonioxTtsEntity(TextToSpeechEntity):
    """Synthesises speech with Soniox tts-rt-v2 (every voice speaks every language)."""

    _attr_has_entity_name = True
    _attr_translation_key = "text_to_speech"

    def __init__(self, hass: HomeAssistant, entry: SonioxConfigEntry) -> None:
        """Initialise from the config entry."""
        self._entry = entry
        self._client = entry.runtime_data.client
        self._voices = entry.runtime_data.tts_voices
        # Soniox TTS covers the same 60+ languages as STT; reuse that list.
        self._languages = entry.runtime_data.stt_languages
        self._attr_unique_id = f"{entry.entry_id}_tts"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Soniox",
            "model": "Real-time STT + TTS",
            "name": TITLE,
            "entry_type": "service",
        }
        ha_lang = normalize_language(hass.config.language)
        self._default_language = ha_lang if ha_lang in self._languages else "en"

    @property
    def default_language(self) -> str:
        """Language used when Assist does not pass one."""
        return self._default_language

    @property
    def supported_languages(self) -> list[str]:
        """Locale tags."""
        return expand_language_tags(self._languages)

    @property
    def supported_options(self) -> list[str]:
        """Per-call options accepted by tts.speak."""
        return [ATTR_VOICE, ATTR_SPEED]

    @property
    def default_options(self) -> dict[str, Any]:
        """Defaults from the Configure dialog."""
        return {
            ATTR_VOICE: self._configured_voice,
            ATTR_SPEED: float(self._entry.options.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED)),
        }

    @property
    def _configured_voice(self) -> str:
        voice = (self._entry.options.get(CONF_TTS_VOICE) or "").strip()
        if voice:
            return voice
        return self._voices[0]["id"] if self._voices else "Adrian"

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        """Voices are language-independent, so the same list for every language."""
        return [
            Voice(voice_id=v["id"], name=f"{v['id']} ({v['gender']})" if v.get("gender") else v["id"])
            for v in self._voices
        ] or None

    async def async_get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> TtsAudioType:
        """Synthesise and return ``("mp3", bytes)``."""
        voice = str(options.get(ATTR_VOICE) or self._configured_voice)
        speed = _clamp_speed(options.get(ATTR_SPEED, self._entry.options.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED)))
        lang = normalize_language(language) or self._default_language
        try:
            audio = await self._client.async_tts(
                text=message,
                language=lang,
                voice=voice,
                model=self._entry.options.get(CONF_TTS_MODEL, DEFAULT_TTS_MODEL),
                speed=speed,
                audio_format="mp3",
            )
        except SonioxAuthError as err:
            raise HomeAssistantError(f"Soniox API key rejected: {err}") from err
        except SonioxConnectionError as err:
            raise HomeAssistantError(f"Soniox unreachable: {err}") from err
        except SonioxApiError as err:
            raise HomeAssistantError(f"Soniox TTS failed: {err}") from err
        if not audio:
            raise HomeAssistantError("Soniox TTS returned no audio")
        LOGGER.debug(
            "Soniox TTS: %s chars → %s bytes (voice=%s lang=%s speed=%s)", len(message), len(audio), voice, lang, speed
        )
        return "mp3", audio

    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        """Stream Assist replies: text in as it is generated, WAV out as it is synthesised.

        The first audio chunk is awaited before handing the response back, so a
        failure before any audio exists falls back to the non-streaming path
        instead of leaving Home Assistant with a stream that goes silent.
        """
        recorder = _Recorder(request.message_gen)
        voice = str(request.options.get(ATTR_VOICE) or self._configured_voice)
        speed = _clamp_speed(
            request.options.get(ATTR_SPEED, self._entry.options.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED))
        )
        lang = normalize_language(request.language) or self._default_language
        chunks = self._client.async_tts_stream(
            recorder.stream(),
            language=lang,
            voice=voice,
            model=self._entry.options.get(CONF_TTS_MODEL, DEFAULT_TTS_MODEL),
            speed=speed,
            sample_rate=TTS_STREAM_SAMPLE_RATE,
        )
        try:
            first = await anext(chunks)
        except (StopAsyncIteration, SonioxError) as err:
            await chunks.aclose()
            LOGGER.warning("Soniox streaming TTS produced no audio (%s) — falling back to REST", err)
            message = await recorder.drain()
            ext, data = await self.async_get_tts_audio(message, request.language, dict(request.options))

            async def _single() -> AsyncGenerator[bytes]:
                yield data

            return TTSAudioResponse(ext, _single())

        async def _wav() -> AsyncGenerator[bytes]:
            yield wav_stream_header(TTS_STREAM_SAMPLE_RATE)
            yield first
            try:
                async for chunk in chunks:
                    yield chunk
            except SonioxError as err:
                raise HomeAssistantError(f"Soniox TTS stream failed: {err}") from err

        return TTSAudioResponse("wav", _wav())


class _Recorder:
    """Forward a text stream while keeping a copy, so a fallback can replay it whole."""

    def __init__(self, source: AsyncIterable[str]) -> None:
        self._source = source
        self.text = ""

    async def stream(self) -> AsyncGenerator[str]:
        async for chunk in self._source:
            self.text += chunk
            yield chunk

    async def drain(self) -> str:
        try:
            async for chunk in self._source:
                self.text += chunk
        except Exception:
            pass
        return self.text


def _clamp_speed(value: Any) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TTS_SPEED
    return max(TTS_SPEED_MIN, min(TTS_SPEED_MAX, speed))
