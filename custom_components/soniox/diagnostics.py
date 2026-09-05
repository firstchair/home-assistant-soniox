"""Diagnostics for the Soniox integration (API key redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SonioxConfigEntry
from .const import CONF_API_KEY

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SonioxConfigEntry) -> dict[str, Any]:
    """Return entry data/options plus what we cached from Soniox."""
    return {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "stt_languages": list(entry.runtime_data.stt_languages),
        "tts_voices": [v["id"] for v in entry.runtime_data.tts_voices],
    }
