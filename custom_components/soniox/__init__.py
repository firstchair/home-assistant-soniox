"""Soniox speech-to-text and text-to-speech for Home Assistant Assist."""

from __future__ import annotations

from dataclasses import dataclass, field

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SonioxApiError, SonioxAuthError, SonioxClient, SonioxConnectionError
from .const import (
    CONF_API_KEY,
    CONF_REGION,
    CONF_STT_MODEL,
    CONF_TTS_MODEL,
    DEFAULT_REGION,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DOMAIN,
    LOGGER,
)

PLATFORMS: list[Platform] = [Platform.STT, Platform.TTS]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class SonioxRuntimeData:
    """Shared runtime state for both platforms."""

    client: SonioxClient
    stt_languages: tuple[str, ...]
    tts_voices: list[dict[str, str]] = field(default_factory=list)


type SonioxConfigEntry = ConfigEntry[SonioxRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> bool:
    """Validate the key, cache languages + voices, and load STT/TTS."""
    client = SonioxClient(
        entry.data[CONF_API_KEY],
        async_get_clientsession(hass),
        entry.data.get(CONF_REGION, DEFAULT_REGION),
    )
    try:
        languages = await client.async_get_stt_languages(entry.options.get(CONF_STT_MODEL, DEFAULT_STT_MODEL))
    except SonioxAuthError as err:
        raise ConfigEntryAuthFailed from err
    except (SonioxConnectionError, SonioxApiError) as err:
        raise ConfigEntryNotReady from err

    # Voices are nice-to-have: a failure here must not block STT. Cloned voices
    # (console → Voices, or POST /v1/voices) are listed first so they are easy
    # to find among the 90+ built-in ones.
    voices: list[dict[str, str]] = []
    try:
        voices = await client.async_get_custom_voices()
    except (SonioxConnectionError, SonioxApiError) as err:
        LOGGER.warning("Could not fetch Soniox cloned voices: %s", err)
    try:
        voices += await client.async_get_tts_voices(entry.options.get(CONF_TTS_MODEL, DEFAULT_TTS_MODEL))
    except (SonioxConnectionError, SonioxApiError) as err:
        LOGGER.warning("Could not fetch Soniox TTS voices: %s", err)

    entry.runtime_data = SonioxRuntimeData(client=client, stt_languages=languages, tts_voices=voices)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> bool:
    """Unload both platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
