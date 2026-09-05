# Soniox for Home Assistant

Speech-to-text **and** text-to-speech for the Home Assistant Assist pipeline, backed by [Soniox](https://soniox.com): one multilingual real-time model for 60+ languages, semantic context for names and product terms, and studio voices that speak every supported language.

Built for a Dutch household running a Voice PE, but nothing in here is Dutch-specific.

## What you get

| Entity | Backed by | Notes |
|---|---|---|
| `stt.soniox_speech_to_text` | `stt-rt-v5` over the real-time websocket | Audio is streamed while you talk, so the transcript is ready right after Assist's silence detection. |
| `tts.soniox_text_to_speech` | `tts-rt-v2` | Non-streaming `tts.speak` via REST, streaming Assist replies via the real-time websocket (audio starts on the first sentence). |

Extras the stock providers do not have:

- **Vocabulary and context.** Names, products and command phrases that keep getting misheard go into Soniox `context.terms`; a free-text description of your domain goes into `context.text`. Up to ~8k tokens, editable in the Configure dialog.
- **Speaker identification (optional).** Point the integration at a pyannote-style endpoint that accepts the utterance as WAV and answers `{"speaker": "Lukas", "confidence": 0.87}`. Above the threshold, the transcript is prefixed with `[Speaker: Lukas] ` so a downstream conversation agent knows who is talking.
- **EU region.** Pick *European Union* during setup if your Soniox project has EU data residency. The API key of an EU project only works against the EU hosts.
- **Any voice, any language.** Soniox voices are language-independent, so the voice you pick keeps its timbre whether Assist answers in Dutch or English. Speed is adjustable from 0.7 to 1.3.

## Requirements

- Home Assistant 2025.12 or newer
- A Soniox account with a funded balance (Soniox no longer hands out free credits) and an API key from <https://console.soniox.com>

## Installation

### HACS

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/firstchair/home-assistant-soniox`, category **Integration**
3. Install **Soniox (STT + TTS)** and restart Home Assistant

### Manual

Copy `custom_components/soniox` into your `config/custom_components/` directory and restart.

## Setup

1. **Settings → Devices & services → Add integration → Soniox**
2. Paste the API key and choose the region of your Soniox project
3. **Configure** (optional): language mode, vocabulary, context text, speaker-identification URL and threshold, TTS voice and speed
4. **Settings → Voice assistants** → open your pipeline → set *Speech-to-text* and/or *Text-to-speech* to the Soniox entities

### Options reference

| Option | Default | Meaning |
|---|---|---|
| Speech-to-text language | Automatic | *Automatic* sends the pipeline language as a strict hint; a fixed language is always used. |
| Speech-to-text model | `stt-rt-v5` | Any real-time model your key can use. |
| Vocabulary (terms) | empty | Comma- or newline-separated words → `context.terms`. |
| Context (free text) | empty | Domain description → `context.text`. |
| Speaker identification URL | empty | `POST` multipart `audio` (WAV) → `{speaker, confidence}`. Empty = off. |
| Speaker confidence threshold | 0.5 | Minimum confidence for the `[Speaker: …]` prefix. |
| Text-to-speech model | `tts-rt-v2` | |
| Voice | first voice of the model | Any voice from the model's list. |
| Emotion / tone | neutral | A Soniox audio tag placed before every message (`[warm]`, `[excited]`, `[calm]`, …). Overridable per call via `options: {emotion: playful}`. |
| Speaking speed | 1.0 | 0.7–1.3, also overridable per `tts.speak` call via `options: {speed: 1.1}`. |

### `tts.speak` options

```yaml
action: tts.speak
target:
  entity_id: tts.soniox_text_to_speech
data:
  media_player_entity_id: media_player.living_room
  message: "De was is klaar."
  language: nl
  options:
    voice: Mina
    speed: 1.1
    emotion: warm
```

### Emotion and audio tags

Soniox TTS v2 is steered with **audio tags** in the text itself, always in English, placed before the words they affect: emotions (`[happy]`, `[sad]`, `[excited]`, `[calm]`, `[relieved]`…), tone (`[warm]`, `[stern]`, `[playful]`, `[sarcastic]`, `[reassuringly]`…), sounds (`[laughs]`, `[sighs]`, `[gasps]`, `[clears throat]`…), volume and pace (`[whispering]`, `[loudly]`, `[slowly]`, `[hesitantly]`…) and pauses (`[pause]`, `[long pause]`). See Soniox's [Emotion & tone](https://soniox.com/docs/tts/concepts/emotion-and-tone) page for the full list.

The integration exposes this two ways:

- **Default emotion** in Configure (or `emotion` in `tts.speak` options) → one tag is put in front of the whole message. Pick `neutral` for none.
- **Inline tags** are passed through verbatim, so a conversation agent can write `[sighs] De vaatwasser is alweer vol.` and get exactly that. A message that already starts with a tag is never given a second one.

Uppercase words are shouted, `*asterisks*` add stress, `...` and `—` add pauses. Tags apply to the streaming path as well: the tag is sent as the first text chunk.

## How it works

- **STT** opens `wss://stt-rt.soniox.com/transcribe-websocket`, sends the config (PCM s16le, sample rate from Assist, `language_hints`, `context`), forwards each audio chunk as it arrives, sends an empty frame when Assist stops recording, and returns the final tokens once Soniox reports `finished`. Endpoint detection is left to Assist's own VAD. A keepalive goes out every 10 s in case the pipeline stalls.
- **Speaker ID** buffers a copy of the PCM (capped at 60 s), wraps it in a WAV header and posts it to your endpoint after the stream ends. Failures are logged and ignored: the transcript never depends on it.
- **TTS (`tts.speak`)** posts to `https://tts-rt.soniox.com/tts` and returns MP3.
- **TTS (streaming)** opens `wss://tts-rt.soniox.com/tts-websocket`, forwards the reply text as it is generated and yields PCM (24 kHz) behind a WAV header, so playback starts before the LLM has finished the sentence. Falls back to the non-streaming path when the first chunk fails.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements_test.txt
pytest -q
ruff check custom_components tests scripts
SONIOX_API_KEY=... python scripts/smoke_test.py path/to/16k-mono.wav "Hallo, ik ben PA."
```

`api.py` and `helpers.py` have no Home Assistant imports on purpose, so the smoke test talks to the real API without a running HA.

## Credits

Structure borrowed from [greimela/home-assistant-soniox-stt](https://github.com/greimela/home-assistant-soniox-stt) and sfox38's Cartesia Sonic TTS integration (mirrored at [BobMcGlobus/ha-cartesia-tts](https://github.com/BobMcGlobus/ha-cartesia-tts)). MIT licensed.
