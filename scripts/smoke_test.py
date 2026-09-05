"""Live smoke test against Soniox, outside Home Assistant.

    SONIOX_API_KEY=... python scripts/smoke_test.py path/to/16k-mono.wav "Tekst om uit te spreken"

Streams the WAV's PCM to Soniox STT (with a small Dutch context), then
synthesises the given text with TTS (REST) and with the real-time websocket,
writing ``smoke_tts.mp3`` and ``smoke_tts_stream.wav`` next to this script.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import load_modules

_mods = load_modules()
api = _mods["api"]
helpers = _mods["helpers"]


async def _pcm_chunks(pcm: bytes, chunk: int = 3200, realtime: bool = True):
    """Yield PCM in 100 ms chunks, paced like a microphone when ``realtime``."""
    for off in range(0, len(pcm), chunk):
        yield pcm[off : off + chunk]
        if realtime:
            await asyncio.sleep(chunk / 32000)


async def _text_chunks(text: str):
    for word in text.split(" "):
        yield word + " "
        await asyncio.sleep(0.05)


async def main() -> None:
    key = os.environ["SONIOX_API_KEY"]
    wav = Path(sys.argv[1]).read_bytes()
    text = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "Hallo, ik ben PA. Ik heb Kewpie mayonaise en koffiecups op de boodschappenlijst gezet."
    )
    pcm = wav[44:]
    out = Path(__file__).resolve().parent

    async with aiohttp.ClientSession() as session:
        client = api.SonioxClient(key, session, os.environ.get("SONIOX_REGION", "us"))

        langs = await client.async_get_stt_languages()
        print(f"STT languages: {len(langs)} (nl={'nl' in langs})")
        voices = await client.async_get_tts_voices()
        print(f"TTS voices ({len(voices)}): " + ", ".join(f"{v['id']}/{v['gender']}" for v in voices))

        ctx = helpers.build_context(
            ["Kewpie", "koffiecups", "Albert Heijn"], "Nederlandse smart-home huishoud-assistent"
        )
        t0 = time.monotonic()
        t_end_audio = None

        async def paced():
            nonlocal t_end_audio
            async for c in _pcm_chunks(pcm):
                yield c
            t_end_audio = time.monotonic()

        transcript, captured = await client.async_transcribe(paced(), language="nl", context=ctx, capture_audio=True)
        t1 = time.monotonic()
        print(
            f"STT (paced, {len(pcm) / 32000:.1f}s audio): {t1 - t0:.2f}s total, {t1 - t_end_audio:.2f}s after last audio, captured={len(captured)}B"
        )
        print(f"  → {transcript!r}")

        voice = os.environ.get("SONIOX_VOICE") or (voices[0]["id"] if voices else "Adrian")
        t0 = time.monotonic()
        mp3 = await client.async_tts(text=text, language="nl", voice=voice, audio_format="mp3")
        print(f"TTS REST voice={voice}: {len(mp3)} bytes in {time.monotonic() - t0:.2f}s → {out / 'smoke_tts.mp3'}")
        (out / "smoke_tts.mp3").write_bytes(mp3)

        t0 = time.monotonic()
        first = None
        chunks = bytearray()
        async for chunk in client.async_tts_stream(_text_chunks(text), language="nl", voice=voice, sample_rate=24000):
            if first is None:
                first = time.monotonic() - t0
            chunks.extend(chunk)
        print(
            f"TTS stream voice={voice}: first audio after {first:.2f}s, {len(chunks)} bytes PCM in {time.monotonic() - t0:.2f}s → {out / 'smoke_tts_stream.wav'}"
        )
        (out / "smoke_tts_stream.wav").write_bytes(helpers.pcm_to_wav(bytes(chunks), 24000))


if __name__ == "__main__":
    asyncio.run(main())
