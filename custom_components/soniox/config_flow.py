"""Config and options flow for the Soniox integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SonioxApiError, SonioxAuthError, SonioxClient, SonioxConnectionError
from .const import (
    AUTO_LANGUAGE,
    CONF_API_KEY,
    CONF_CONTEXT_TERMS,
    CONF_CONTEXT_TEXT,
    CONF_LANGUAGE,
    CONF_REGION,
    CONF_SPEAKER_ID_URL,
    CONF_SPEAKER_THRESHOLD,
    CONF_STT_MODEL,
    CONF_TTS_MODEL,
    CONF_TTS_SPEED,
    CONF_TTS_VOICE,
    DEFAULT_REGION,
    DEFAULT_SPEAKER_THRESHOLD,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_SPEED,
    DOMAIN,
    REGIONS,
    TITLE,
    TTS_SPEED_MAX,
    TTS_SPEED_MIN,
)


def _region_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(REGIONS),
            translation_key="region",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _language_selector(languages: tuple[str, ...]) -> selector.SelectSelector:
    options = [selector.SelectOptionDict(value=AUTO_LANGUAGE, label="Automatic (pipeline language)")]
    options += [selector.SelectOptionDict(value=code, label=code) for code in languages]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN, sort=False)
    )


def _voice_selector(voices: list[dict[str, str]]) -> Any:
    if not voices:
        return selector.TextSelector()
    options = [
        selector.SelectOptionDict(
            value=v["id"],
            label=(
                f"★ {v.get('name') or v['id']} — {v['description']}"
                if v.get("gender") == "custom"
                else f"{v['id']} — {v['gender']} — {v['description'][:60]}"
                if v.get("description")
                else v["id"]
            ),
        )
        for v in voices
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN, sort=False)
    )


async def _validate(hass: Any, api_key: str, region: str) -> str | None:
    """Return an error key, or ``None`` when the key works for that region."""
    client = SonioxClient(api_key, async_get_clientsession(hass), region)
    try:
        await client.async_get_stt_languages()
    except SonioxAuthError:
        return "invalid_auth"
    except (SonioxConnectionError, SonioxApiError):
        return "cannot_connect"
    return None


class SonioxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """API key + region, with reauth and reconfigure."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> SonioxOptionsFlow:
        """Return the options flow."""
        return SonioxOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Initial setup."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _validate(self.hass, user_input[CONF_API_KEY], user_input[CONF_REGION])
            if error is None:
                return self.async_create_entry(title=TITLE, data=user_input)
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> config_entries.ConfigFlowResult:
        """Key was rejected at runtime."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for a new key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _validate(self.hass, user_input[CONF_API_KEY], user_input[CONF_REGION])
            if error is None:
                return self.async_update_reload_and_abort(entry, data=user_input)
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=self._schema(entry.data.get(CONF_REGION)), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Change key or region."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _validate(self.hass, user_input[CONF_API_KEY], user_input[CONF_REGION])
            if error is None:
                return self.async_update_reload_and_abort(entry, data=user_input)
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure", data_schema=self._schema(entry.data.get(CONF_REGION)), errors=errors
        )

    @staticmethod
    def _schema(region: str | None = None) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_REGION, default=region or DEFAULT_REGION): _region_selector(),
            }
        )


class SonioxOptionsFlow(config_entries.OptionsFlow):
    """Language mode, context, speaker-ID sidecar, and TTS voice/speed."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Single options page."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        runtime = self.config_entry.runtime_data
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_LANGUAGE, default=opts.get(CONF_LANGUAGE, AUTO_LANGUAGE)): _language_selector(
                    runtime.stt_languages
                ),
                vol.Optional(CONF_STT_MODEL, default=opts.get(CONF_STT_MODEL, DEFAULT_STT_MODEL)): str,
                vol.Optional(
                    CONF_CONTEXT_TERMS, description={"suggested_value": opts.get(CONF_CONTEXT_TERMS, "")}
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_CONTEXT_TEXT, description={"suggested_value": opts.get(CONF_CONTEXT_TEXT, "")}
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_SPEAKER_ID_URL, description={"suggested_value": opts.get(CONF_SPEAKER_ID_URL, "")}
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL)),
                vol.Optional(
                    CONF_SPEAKER_THRESHOLD, default=opts.get(CONF_SPEAKER_THRESHOLD, DEFAULT_SPEAKER_THRESHOLD)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode=selector.NumberSelectorMode.SLIDER)
                ),
                vol.Optional(CONF_TTS_MODEL, default=opts.get(CONF_TTS_MODEL, DEFAULT_TTS_MODEL)): str,
                vol.Optional(
                    CONF_TTS_VOICE,
                    default=opts.get(CONF_TTS_VOICE) or (runtime.tts_voices[0]["id"] if runtime.tts_voices else ""),
                ): _voice_selector(runtime.tts_voices),
                vol.Optional(
                    CONF_TTS_SPEED, default=opts.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=TTS_SPEED_MIN, max=TTS_SPEED_MAX, step=0.05, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
