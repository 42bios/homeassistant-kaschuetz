"""Initialize the Kaschuetz integration.

Home Assistant will call async_setup_entry(...) when the user adds
this integration via the UI. We then forward to 'sensor' platform.
"""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kaschuetz from a config entry by forwarding to sensor platform."""
    _LOGGER.debug("Setting up Kaschuetz entry: %s", entry.as_dict())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Kaschuetz config entry by unloading sensor platform."""
    _LOGGER.debug("Unloading Kaschuetz entry: %s", entry.as_dict())
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
