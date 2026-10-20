"""Config flow for Kaschuetz Oven integration.

Implements:
- Main flow for IP + optional season_entity
- Options flow for update interval and optimizer settings

Burn parameters are not part of the options: the controller only accepts them
through its save process, see the number entities and the save button.
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

from .api import KaschuetzApiError, async_post_json
from .const import (
    CONF_EXPERIMENTAL_AUTO_OPTIMIZE,
    CONF_HOST,
    CONF_OPTIMIZER_MODE,
    CONF_OPTIMIZER_PROFILE,
    CONF_SEASON_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_EXPERIMENTAL_AUTO_OPTIMIZE,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODES,
    OPTIMIZER_PROFILE_DEFAULT,
    OPTIMIZER_PROFILES,
    RQ_QUERY_TEMP,
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
    """Verify the Kaschuetz device is reachable with a status query."""
    try:
        data = await async_post_json(hass, host, {"rqType": RQ_QUERY_TEMP})
        if "state" not in data:
            _LOGGER.error("Device at %s did not answer like a Kaschuetz controller", host)
            return False
        return True
    except KaschuetzApiError as err:
        _LOGGER.error("Connection test failed: %s", err)
        return False


class KaschuetzOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle update interval and optimizer options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the config_entry for reference."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask for update interval and optimizer settings."""
        if user_input is not None:
            # Burn parameters of older versions are no longer kept in the options.
            return self.async_create_entry(title="", data=user_input)

        current_options = dict(self._config_entry.options)
        def_update_interval = current_options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        def_optimizer_mode = current_options.get(
            CONF_OPTIMIZER_MODE, OPTIMIZER_MODE_BALANCED
        )
        def_optimizer_profile = current_options.get(
            CONF_OPTIMIZER_PROFILE, OPTIMIZER_PROFILE_DEFAULT
        )
        def_experimental_auto_optimize = bool(
            current_options.get(
                CONF_EXPERIMENTAL_AUTO_OPTIMIZE, DEFAULT_EXPERIMENTAL_AUTO_OPTIMIZE
            )
        )
        if def_optimizer_mode not in OPTIMIZER_MODES:
            def_optimizer_mode = OPTIMIZER_MODE_BALANCED
        if def_optimizer_profile not in OPTIMIZER_PROFILES:
            def_optimizer_profile = OPTIMIZER_PROFILE_DEFAULT

        schema = vol.Schema({
            vol.Required(CONF_UPDATE_INTERVAL, default=def_update_interval): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
            ),
            vol.Optional(CONF_OPTIMIZER_MODE, default=def_optimizer_mode): vol.In(
                OPTIMIZER_MODES
            ),
            vol.Optional(CONF_OPTIMIZER_PROFILE, default=def_optimizer_profile): vol.In(
                OPTIMIZER_PROFILES
            ),
            vol.Optional(
                CONF_EXPERIMENTAL_AUTO_OPTIMIZE,
                default=def_experimental_auto_optimize,
            ): bool,
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
