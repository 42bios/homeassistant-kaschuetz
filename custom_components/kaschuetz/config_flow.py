"""Config flow for Kaschuetz Oven integration.

Implements:
- User flow for the controller address and an optional season entity
- Reconfigure flow to change both later (e.g. a new IP address)
- Options flow for update interval and optimizer settings

Burn parameters are not part of the options: the controller only accepts them
through its save process, see the number entities and the save button.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

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


def _connection_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema for the controller address and the optional season entity."""
    season = defaults.get(CONF_SEASON_ENTITY)
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
            vol.Optional(
                CONF_SEASON_ENTITY,
                description={"suggested_value": season} if season else None,
            ): EntitySelector(EntitySelectorConfig(domain=["sensor", "select", "input_select"])),
        }
    )


class KaschuetzOptionsFlowHandler(OptionsFlow):
    """Handle update interval and optimizer options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for update interval and optimizer settings."""
        if user_input is not None:
            # Burn parameters of older versions are no longer kept in the options.
            return self.async_create_entry(title="", data=user_input)

        current_options = dict(self.config_entry.options)
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
    """Main config flow for Kaschuetz Oven Control."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the controller address and an optional season entity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host):
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={
                        CONF_HOST: host,
                        CONF_SEASON_ENTITY: user_input.get(CONF_SEASON_ENTITY),
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=_connection_schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the controller address or the season entity."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            if host != entry.unique_id:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host):
                # The entry's update listener reloads it with the new connection.
                return self.async_update_and_abort(
                    entry,
                    reason="reconfigure_successful",
                    unique_id=host,
                    data_updates={
                        CONF_HOST: host,
                        CONF_SEASON_ENTITY: user_input.get(CONF_SEASON_ENTITY),
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KaschuetzOptionsFlowHandler:
        """Return the options flow."""
        return KaschuetzOptionsFlowHandler()
