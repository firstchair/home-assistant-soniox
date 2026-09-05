# Changelog

All notable changes to this integration are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-09-05

### Added

- Cloned voices (`GET /v1/voices`) are listed first in the voice dropdown and in Assist's voice picker, marked ★, so a custom voice can be selected without copying its UUID.

## [0.1.0] - 2026-09-05

### Added

- Speech-to-text entity streaming Assist audio to Soniox `stt-rt-v5` over the real-time websocket, with vocabulary (`context.terms`), free-text context, automatic or fixed language, keepalive, and an optional pyannote-style speaker-identification endpoint that prefixes `[Speaker: NAME]`.
- Text-to-speech entity on `tts-rt-v2`: REST for `tts.speak`, real-time websocket streaming for Assist replies (WAV, 24 kHz), voice picker from the model's voice list, speed 0.7–1.3, and an emotion option that puts a Soniox audio tag in front of the message (inline tags always win).
- Config flow with US/EU region, reauth and reconfigure; options flow; diagnostics; English and Dutch translations; HACS metadata; brand icons; CI with hassfest, HACS validation, ruff and pytest.
