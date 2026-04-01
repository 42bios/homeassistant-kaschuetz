"""Config flow for Kaschuetz Oven integration.

Implements:
- Main Flow for IP + optional season_entity
- Options Flow for abbrand parameters + update interval
- Setting the new abbrand parameters on the device after user input.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import (
    KaschuetzApiError,
    async_fetch_params,
    async_post_json,
    async_send_abbrand_params,
)
from .const import (
    CONF_HOST,
    CONF_OPTIMIZER_MODE,
    CONF_SEASON_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_A_TEMP,
    DEFAULT_NAME,
    DEFAULT_REGP,
    DEFAULT_REGW,
    DEFAULT_SCHW,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODES,
)

_LOGGER = logging.getLogger(__name__)


def _normalize_host(raw_host: str) -> str:
    """Normalize user-provided host input."""
    host = raw_host.strip()
    if "://" in host:
        parsed = urlsplit(host)
        if parsed.hostname:
            return parsed.hostname
    host = host.split("/")[0]
    return host


async def _test_connection(hass: HomeAssistant, host: str) -> bool:
    """Verify the Kaschuetz device is reachable using rqType=1."""
    try:
        await async_post_json(hass, host, {"rqType": 1})
        return True
    except KaschuetzApiError as err:
        _LOGGER.error("Connection test failed: %s", err)
        return False


async def _fetch_current_params(
    hass: HomeAssistant, host: str
) -> dict[str, Any]:
    """Fetch current abbrand parameters if supported by the device."""
    try:
        data = await async_fetch_params(hass, host)
        _LOGGER.debug("Fetched current params from device: %s", data)
        return data
    except KaschuetzApiError as err:
        _LOGGER.warning("Could not fetch current abbrand params: %s", err)
        return {}


class KaschuetzOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle advanced abbrand parameter options, including update interval."""

    @staticmethod
    def _normalize_param(value: Any, fallback: int) -> int:
        """Normalize device option values and avoid unsupported sentinel values."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed >= 0 else fallback

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the config_entry for reference."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Ask for abbrand parameters & update interval.
        Then set them in the device if changed.
        """
        if user_input is not None:
            user_input[CONF_UPDATE_INTERVAL] = max(
                MIN_UPDATE_INTERVAL,
                min(
                    MAX_UPDATE_INTERVAL,
                    int(user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
                ),
            )

            host = self._config_entry.data[CONF_HOST]
            _LOGGER.info("User updated abbrand params: %s", user_input)

            current_options = dict(self._config_entry.options)
            abbrand_keys = ("aTemp", "schW", "regW", "regP")
            changed = any(
                user_input.get(key) != current_options.get(key)
                for key in abbrand_keys
            )
            if changed:
                try:
                    await async_send_abbrand_params(
                        self.hass,
                        host,
                        {key: int(user_input[key]) for key in abbrand_keys},
                    )
                except KaschuetzApiError as err:
                    _LOGGER.error("Failed to send abbrand params: %s", err)

            return self.async_create_entry(title="", data=user_input)

        current_options = dict(self._config_entry.options)
        host = self._config_entry.data[CONF_HOST]

        device_params = await _fetch_current_params(self.hass, host)

        def_aTemp = self._normalize_param(
            current_options.get("aTemp", device_params.get("aTemp", DEFAULT_A_TEMP)),
            DEFAULT_A_TEMP,
        )
        def_schW = self._normalize_param(
            current_options.get("schW", device_params.get("schW", DEFAULT_SCHW)),
            DEFAULT_SCHW,
        )
        def_regW = self._normalize_param(
            current_options.get("regW", device_params.get("regW", DEFAULT_REGW)),
            DEFAULT_REGW,
        )
        def_regP = self._normalize_param(
            current_options.get("regP", device_params.get("regP", DEFAULT_REGP)),
            DEFAULT_REGP,
        )

        def_update_interval = current_options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        def_optimizer_mode = current_options.get(
            CONF_OPTIMIZER_MODE, OPTIMIZER_MODE_BALANCED
        )
        if def_optimizer_mode not in OPTIMIZER_MODES:
            def_optimizer_mode = OPTIMIZER_MODE_BALANCED

        schema = vol.Schema({
            vol.Optional("aTemp", default=def_aTemp): vol.Coerce(int),
            vol.Optional("schW", default=def_schW): vol.Coerce(int),
            vol.Optional("regW", default=def_regW): vol.Coerce(int),
            vol.Optional("regP", default=def_regP): vol.Coerce(int),
            vol.Required(CONF_UPDATE_INTERVAL, default=def_update_interval): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
            ),
            vol.Optional(CONF_OPTIMIZER_MODE, default=def_optimizer_mode): vol.In(
                OPTIMIZER_MODES
            ),
        })

        return self.async_show_form(step_id="init", data_schema=schema)

class KaschuetzConfigFlow(ConfigFlow, domain=DOMAIN):
    """Main Config Flow for Kaschuetz Oven Control."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask for the device IP and optional season_entity."""
        errors = {}

        if user_input is not None:
            normalized_host = _normalize_host(user_input[CONF_HOST])
            await self.async_set_unique_id(normalized_host)
            self._abort_if_unique_id_configured()

            valid = await _test_connection(self.hass, normalized_host)
            if valid:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={
                        CONF_HOST: normalized_host,
                        CONF_SEASON_ENTITY: user_input.get(CONF_SEASON_ENTITY),
                    },
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_SEASON_ENTITY): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> KaschuetzOptionsFlowHandler:
        """Return the options flow."""
        return KaschuetzOptionsFlowHandler(config_entry)
