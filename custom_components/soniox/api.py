"""Async client for the Soniox API (speech-to-text, text-to-speech, models).

Deliberately free of Home Assistant imports so it can be exercised from a plain
script (see ``scripts/smoke_test.py``) and unit-tested without the HA test
harness. Only depends on ``aiohttp``, which Home Assistant ships.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

import aiohttp

from .const import DEFAULT_STT_MODEL, DEFAULT_TTS_MODEL, ENDPOINTS, REGION_US
from .helpers import pcm_to_wav, render_tokens

_LOGGER = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 10.0
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
STT_TIMEOUT_SECONDS = 60.0
SPEAKER_ID_TIMEOUT = aiohttp.ClientTimeout(total=10)
# Cap on the audio we buffer for speaker identification (16 kHz s16le mono ≈ 32 kB/s).
SPEAKER_ID_MAX_BYTES = 32_000 * 60


class SonioxError(Exception):
    """Base error."""


class SonioxAuthError(SonioxError):
    """The API key was rejected."""


class SonioxConnectionError(SonioxError):
    """Soniox could not be reached."""


class SonioxApiError(SonioxError):
    """Soniox returned an error for a request."""


class SonioxClient:
    """Thin aiohttp wrapper around the Soniox endpoints of one region."""

    def __init__(self, api_key: str, session: aiohttp.ClientSession, region: str = REGION_US) -> None:
        """Initialise for one API key and one region."""
        self._api_key = api_key
        self._session = session
        self._endpoints = ENDPOINTS.get(region, ENDPOINTS[REGION_US])

    # ── REST ──────────────────────────────────────────────────────────────

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _get_json(self, path: str) -> Any:
        url = f"{self._endpoints['api']}{path}"
        try:
            async with self._session.get(url, headers=self._headers, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status in (401, 403):
                    raise SonioxAuthError(f"HTTP {resp.status} for {path}")
                if resp.status >= 400:
                    raise SonioxApiError(f"HTTP {resp.status} for {path}: {(await resp.text())[:200]}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise SonioxConnectionError(str(err)) from err
        except TimeoutError as err:
            raise SonioxConnectionError(f"timeout for {path}") from err

    async def async_get_stt_languages(self, model: str = DEFAULT_STT_MODEL) -> tuple[str, ...]:
        """Return the language codes of the real-time STT model (validates the key)."""
        data = await self._get_json("/models")
        models = data.get("models", data) if isinstance(data, dict) else data
        chosen = None
        for m in models:
            if m.get("id") == model:
                chosen = m
                break
        if chosen is None:
            rt = [m for m in models if str(m.get("id", "")).startswith("stt-rt")]
            if not rt:
                raise SonioxApiError(f"model {model} not available for this API key")
            chosen = rt[0]
        codes = []
        for lang in chosen.get("languages", []):
            code = lang.get("code") if isinstance(lang, dict) else lang
            if code:
                codes.append(str(code))
        return tuple(sorted(set(codes)))

    async def async_get_tts_voices(self, model: str = DEFAULT_TTS_MODEL) -> list[dict[str, str]]:
        """Return the built-in voices of a TTS model as ``{id, description, gender}`` dicts."""
        data = await self._get_json("/tts-models")
        models = data.get("models", data) if isinstance(data, dict) else data
        for m in models:
            if m.get("id") == model or m.get("aliased_model_id") == model:
                return [
                    {
                        "id": str(v.get("id")),
                        "description": str(v.get("description", "")),
                        "gender": str(v.get("gender", "")),
                    }
                    for v in m.get("voices", [])
                    if v.get("id")
                ]
        return []

    async def async_tts(
        self,
        *,
        text: str,
        language: str,
        voice: str,
        model: str = DEFAULT_TTS_MODEL,
        speed: float | None = None,
        audio_format: str = "mp3",
        sample_rate: int | None = None,
    ) -> bytes:
        """Synthesise ``text`` and return the encoded audio bytes."""
        payload: dict[str, Any] = {
            "model": model,
            "language": language,
            "voice": voice,
            "audio_format": audio_format,
            "text": text,
        }
        if speed is not None and abs(speed - 1.0) > 1e-6:
            payload["speed"] = round(speed, 2)
        if sample_rate:
            payload["sample_rate"] = sample_rate
        try:
            async with self._session.post(
                self._endpoints["tts"],
                headers={**self._headers, "Content-Type": "application/json"},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise SonioxAuthError(f"HTTP {resp.status} for tts")
                if resp.status >= 400:
                    raise SonioxApiError(f"HTTP {resp.status} for tts: {(await resp.text())[:300]}")
                return await resp.read()
        except aiohttp.ClientError as err:
            raise SonioxConnectionError(str(err)) from err
        except TimeoutError as err:
            raise SonioxConnectionError("timeout for tts") from err

    # ── Speaker identification (optional sidecar) ─────────────────────────

    async def async_identify_speaker(self, url: str, pcm: bytes, sample_rate: int = 16000) -> tuple[str | None, float]:
        """POST the utterance as WAV to a pyannote-style ``/identify`` endpoint.

        Expects ``{"speaker": str, "confidence": float}`` back. Never raises:
        speaker identification must not take the transcript down with it.
        """
        form = aiohttp.FormData()
        form.add_field("audio", pcm_to_wav(pcm, sample_rate), filename="utterance.wav", content_type="audio/wav")
        try:
            async with self._session.post(url, data=form, timeout=SPEAKER_ID_TIMEOUT) as resp:
                if resp.status >= 400:
                    _LOGGER.warning("speaker-id %s returned HTTP %s", url, resp.status)
                    return None, 0.0
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.warning("speaker-id %s failed: %s", url, err)
            return None, 0.0
        speaker = data.get("speaker") if isinstance(data, dict) else None
        confidence = data.get("confidence", 0.0) if isinstance(data, dict) else 0.0
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        return (str(speaker) if speaker else None), confidence

    # ── Real-time STT ─────────────────────────────────────────────────────

    async def async_transcribe(
        self,
        audio: AsyncIterable[bytes],
        *,
        language: str | None,
        model: str = DEFAULT_STT_MODEL,
        sample_rate: int = 16000,
        context: dict[str, Any] | None = None,
        capture_audio: bool = False,
    ) -> tuple[str, bytes]:
        """Stream PCM s16le mono audio to Soniox and return ``(text, captured_pcm)``.

        Audio is forwarded as it arrives, so Soniox transcribes while the user
        is still talking; after the stream ends an empty frame asks Soniox to
        finalise, and the loop returns on ``finished``. ``captured_pcm`` holds a
        copy of the audio (capped) when ``capture_audio`` is set, for speaker
        identification.
        """
        config: dict[str, Any] = {
            "api_key": self._api_key,
            "model": model,
            "audio_format": "pcm_s16le",
            "num_channels": 1,
            "sample_rate": sample_rate,
            "client_reference_id": "home-assistant-soniox",
        }
        if language:
            config["language_hints"] = [language]
            config["language_hints_strict"] = True
        if context:
            config["context"] = context

        tokens: list[dict[str, Any]] = []
        captured = bytearray()
        sent_bytes = 0

        async def _pump(ws: aiohttp.ClientWebSocketResponse) -> None:
            nonlocal sent_bytes
            async for chunk in audio:
                if not chunk:
                    continue
                data = bytes(chunk)
                sent_bytes += len(data)
                if capture_audio and len(captured) < SPEAKER_ID_MAX_BYTES:
                    captured.extend(data)
                await ws.send_bytes(data)
            # Empty frame = end of audio → Soniox finalises and sends finished.
            await ws.send_str("")

        async def _keepalive(ws: aiohttp.ClientWebSocketResponse) -> None:
            while True:
                await asyncio.sleep(KEEPALIVE_SECONDS)
                await ws.send_str(json.dumps({"type": "keepalive"}))

        try:
            async with self._session.ws_connect(
                self._endpoints["stt_ws"], heartbeat=None, timeout=aiohttp.ClientWSTimeout(ws_close=10)
            ) as ws:
                await ws.send_str(json.dumps(config))
                pump = asyncio.create_task(_pump(ws))
                keep = asyncio.create_task(_keepalive(ws))
                try:
                    async with asyncio.timeout(STT_TIMEOUT_SECONDS):
                        async for msg in ws:
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                if msg.type in (
                                    aiohttp.WSMsgType.CLOSE,
                                    aiohttp.WSMsgType.CLOSED,
                                    aiohttp.WSMsgType.ERROR,
                                ):
                                    break
                                continue
                            event = json.loads(msg.data)
                            if event.get("error_code") is not None or event.get("error_message"):
                                code = event.get("error_code")
                                message = f"Soniox {code} {event.get('error_type', '')}: {event.get('error_message', '')}".strip()
                                if code in (401, 403):
                                    raise SonioxAuthError(message)
                                raise SonioxApiError(message)
                            tokens.extend(t for t in event.get("tokens", []) if t.get("is_final"))
                            if event.get("finished"):
                                break
                finally:
                    keep.cancel()
                    if not pump.done():
                        pump.cancel()
                    await asyncio.gather(pump, keep, return_exceptions=True)
        except (aiohttp.ClientError, ConnectionError) as err:
            raise SonioxConnectionError(str(err)) from err
        except TimeoutError as err:
            raise SonioxConnectionError("timeout waiting for Soniox transcript") from err

        text = render_tokens(tokens)
        _LOGGER.debug("Soniox STT done: %s bytes sent, %s final tokens, %r", sent_bytes, len(tokens), text[:80])
        return text, bytes(captured)

    # ── Real-time TTS ─────────────────────────────────────────────────────

    async def async_tts_stream(
        self,
        text: AsyncIterable[str],
        *,
        language: str,
        voice: str,
        model: str = DEFAULT_TTS_MODEL,
        speed: float | None = None,
        sample_rate: int = 24000,
    ) -> AsyncGenerator[bytes]:
        """Stream text chunks in, yield raw PCM s16le chunks out.

        Text is forwarded as it arrives (e.g. straight from the LLM), so audio
        for the first sentence starts before the reply is complete. An empty
        chunk with ``text_end`` closes the stream; the loop ends on ``audio_end``.
        """
        stream_id = uuid.uuid4().hex
        config: dict[str, Any] = {
            "api_key": self._api_key,
            "stream_id": stream_id,
            "model": model,
            "language": language,
            "voice": voice,
            "audio_format": "pcm_s16le",
            "sample_rate": sample_rate,
        }
        if speed is not None and abs(speed - 1.0) > 1e-6:
            config["speed"] = round(speed, 2)

        async def _pump(ws: aiohttp.ClientWebSocketResponse) -> None:
            async for chunk in text:
                if chunk:
                    await ws.send_str(json.dumps({"text": chunk, "text_end": False, "stream_id": stream_id}))
            await ws.send_str(json.dumps({"text": "", "text_end": True, "stream_id": stream_id}))

        try:
            async with self._session.ws_connect(
                self._endpoints["tts_ws"], heartbeat=None, timeout=aiohttp.ClientWSTimeout(ws_close=10)
            ) as ws:
                await ws.send_str(json.dumps(config))
                pump = asyncio.create_task(_pump(ws))
                try:
                    async with asyncio.timeout(STT_TIMEOUT_SECONDS):
                        async for msg in ws:
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                if msg.type in (
                                    aiohttp.WSMsgType.CLOSE,
                                    aiohttp.WSMsgType.CLOSED,
                                    aiohttp.WSMsgType.ERROR,
                                ):
                                    break
                                continue
                            event = json.loads(msg.data)
                            if event.get("error_code") is not None or event.get("error_message"):
                                code = event.get("error_code")
                                message = f"Soniox {code}: {event.get('error_message', '')}".strip()
                                if code in (401, 403):
                                    raise SonioxAuthError(message)
                                raise SonioxApiError(message)
                            if event.get("audio"):
                                yield base64.b64decode(event["audio"])
                            if event.get("audio_end") or event.get("terminated"):
                                break
                finally:
                    if not pump.done():
                        pump.cancel()
                    await asyncio.gather(pump, return_exceptions=True)
        except (aiohttp.ClientError, ConnectionError) as err:
            raise SonioxConnectionError(str(err)) from err
        except TimeoutError as err:
            raise SonioxConnectionError("timeout waiting for Soniox TTS audio") from err
