"""Config flow for Kaschuetz Oven integration.

Implements:
- Main Flow for IP + optional season_entity
- Options Flow for abbrand parameters + update interval
- Setting the new abbrand parameters on the device after user input.
"""

from __future__ import annotations

import logging
import requests
import voluptuous as vol

from typing import Any, Dict

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL, MIN_UPDATE_INTERVAL, MAX_UPDATE_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

def _test_connection(hass: HomeAssistant, host: str) -> bool:
    """
    Quick request to verify the Kaschuetz device is reachable using rqType=1.
    Return True if successful, False otherwise.
    """
    url = f"http://{host}/jsonRq"
    try:
        resp = requests.post(url, json={"rqType": 1}, timeout=3)
        resp.raise_for_status()
        return True
    except requests.RequestException as err:
        _LOGGER.error("Connection test failed: %s", err)
        return False

def _fetch_current_params(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """
    Example: fetch the current abbrand parameters (if the device supports it).
    Let's say rqType=4 returns:
      { "aTemp": 200, "schW":300, "regW":600, "regP":200 }
    """
    url = f"http://{host}/jsonRq"
    try:
        resp = requests.post(url, json={"rqType": 4}, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        _LOGGER.debug("Fetched current params from device: %s", data)
        return data
    except requests.RequestException as err:
        _LOGGER.warning("Could not fetch current abbrand params: %s", err)
        return {}

def _send_abbrand_params(hass: HomeAssistant, host: str, params: Dict[str, int]) -> None:
    """
    Example: set new abbrand parameters on the device.
    Suppose rqType=8 is used to update:
      { "aTemp": X, "schW": Y, "regW":Z, "regP": W }
    """
    url = f"http://{host}/jsonRq"
    body = {
        "rqType": 8,
        "aTemp": params.get("aTemp"),
        "schW":  params.get("schW"),
        "regW":  params.get("regW"),
        "regP":  params.get("regP")
    }
    try:
        resp = requests.post(url, json=body, timeout=3)
        resp.raise_for_status()
        _LOGGER.debug("Successfully sent abbrand params: %s", body)
    except requests.RequestException as err:
        _LOGGER.error("Failed to send abbrand params: %s", err)


class KaschuetzOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle advanced abbrand parameter options, including update interval."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the config_entry for reference."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Ask for abbrand parameters & update interval.
        Then set them in the device if changed.
        """
        if user_input is not None:
            # Validate or clamp the update interval if needed
            interval = user_input.get("update_interval", DEFAULT_UPDATE_INTERVAL)
            if interval < MIN_UPDATE_INTERVAL:
                interval = MIN_UPDATE_INTERVAL
            elif interval > MAX_UPDATE_INTERVAL:
                interval = MAX_UPDATE_INTERVAL
            user_input["update_interval"] = interval

            # Send new abbrand params to the device (if supported).
            # We do this only if the device is reachable & user changes something.
            host = self.config_entry.data["host"]
            _LOGGER.info("User updated abbrand params: %s", user_input)
            await self.hass.async_add_executor_job(
                _send_abbrand_params,
                self.hass,
                host,
                {
                    "aTemp": user_input["aTemp"],
                    "schW":  user_input["schW"],
                    "regW":  user_input["regW"],
                    "regP":  user_input["regP"]
                }
            )

            return self.async_create_entry(title="", data=user_input)

        # Pre-Fill from existing options or from device
        current_options = dict(self.config_entry.options)
        host = self.config_entry.data["host"]

        device_params = await self.hass.async_add_executor_job(
            _fetch_current_params, self.hass, host
        )

        def_aTemp = current_options.get("aTemp", device_params.get("aTemp", 200))
        def_schW  = current_options.get("schW",  device_params.get("schW", 300))
        def_regW  = current_options.get("regW",  device_params.get("regW", 600))
        def_regP  = current_options.get("regP",  device_params.get("regP", 200))

        def_update_interval = current_options.get("update_interval", DEFAULT_UPDATE_INTERVAL)

        schema = vol.Schema({
            vol.Optional("aTemp", default=def_aTemp): vol.Coerce(int),
            vol.Optional("schW",  default=def_schW):  vol.Coerce(int),
            vol.Optional("regW",  default=def_regW):  vol.Coerce(int),
            vol.Optional("regP",  default=def_regP):  vol.Coerce(int),
            vol.Required("update_interval", default=def_update_interval): vol.Coerce(int),
        })

        return self.async_show_form(step_id="init", data_schema=schema)

class KaschuetzConfigFlow(ConfigFlow, domain=DOMAIN):
    """Main Config Flow for Kaschuetz Oven Control."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask for the device IP and optional season_entity."""
        errors = {}

        if user_input is not None:
            valid = await self.hass.async_add_executor_job(
                _test_connection, self.hass, user_input["host"]
            )
            if valid:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={
                        "host": user_input["host"],
                        "season_entity": user_input.get("season_entity"),
                    },
                )
            else:
                errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required("host"): str,
            vol.Optional("season_entity"): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_get_options_flow(self, config_entry: ConfigEntry) -> KaschuetzOptionsFlowHandler:
        """
        Return the OptionsFlow for advanced abbrand parameters.
        Called when user clicks on 'Configure' (gear icon) in the Integration UI.
        """
        return KaschuetzOptionsFlowHandler(config_entry)
