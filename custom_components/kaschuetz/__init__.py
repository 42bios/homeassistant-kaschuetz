"""Initialize the Kaschuetz integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_HOST,
    CONF_SEASON_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import KaschuetzDataCoordinator
from .models import KaschuetzConfigEntry, KaschuetzRuntimeData
from .services import async_setup_services
from .storage import async_load_optimizer, async_remove_optimizer, async_save_optimizer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Entities removed in 1.5.0; their values were not backed by the device protocol.
OBSOLETE_ENTITY_KEYS = ("com_error_text", "spr_code")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services once for all config entries."""
    async_setup_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entries of older versions.

    Version 1 used the host in entity unique ids and the device identifier, so
    a changed IP address would have created new entities. Version 2 uses the
    config entry id instead; entity ids and history are kept.
    """
    if entry.version > 2:
        return False

    if entry.version == 1:
        host = entry.data[CONF_HOST]
        entity_registry = er.async_get(hass)
        for key in OBSOLETE_ENTITY_KEYS:
            if entity_id := entity_registry.async_get_entity_id(
                Platform.SENSOR, DOMAIN, f"kaschuetz_{key}_{host}"
            ):
                entity_registry.async_remove(entity_id)

        suffix = f"_{host}"

        @callback
        def _migrate_unique_id(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
            if not entity_entry.unique_id.endswith(suffix):
                return None
            base = entity_entry.unique_id.removesuffix(suffix)
            return {"new_unique_id": f"{base}_{entry.entry_id}"}

        await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)

        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
            if (DOMAIN, host) in device.identifiers:
                device_registry.async_update_device(
                    device.id, new_identifiers={(DOMAIN, entry.entry_id)}
                )

        hass.config_entries.async_update_entry(entry, version=2)
        _LOGGER.debug("Migrated Kaschuetz entry %s to version 2", entry.entry_id)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: KaschuetzConfigEntry) -> None:
    """Reload when the connection or poll interval changed; other options apply live."""
    runtime = entry.runtime_data
    interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    if (
        runtime.poll_interval != interval
        or runtime.coordinator.host != entry.data[CONF_HOST]
        or runtime.coordinator.season_entity != entry.data.get(CONF_SEASON_ENTITY)
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        return
    entry.runtime_data.coordinator.async_update_listeners()


async def async_setup_entry(hass: HomeAssistant, entry: KaschuetzConfigEntry) -> bool:
    """Set up Kaschuetz from a config entry."""
    optimizer = await async_load_optimizer(hass, entry.entry_id)

    async def _persist_optimizer() -> None:
        await async_save_optimizer(hass, entry.entry_id, optimizer)

    poll_interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    coordinator = KaschuetzDataCoordinator(
        hass=hass,
        entry=entry,
        host=entry.data[CONF_HOST],
        season_entity=entry.data.get(CONF_SEASON_ENTITY),
        poll_interval=poll_interval,
        optimizer=optimizer,
        persist_callback=_persist_optimizer,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = KaschuetzRuntimeData(
        coordinator=coordinator, optimizer=optimizer, poll_interval=poll_interval
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KaschuetzConfigEntry) -> bool:
    """Unload a Kaschuetz config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_save_optimizer(hass, entry.entry_id, entry.runtime_data.optimizer)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: KaschuetzConfigEntry) -> None:
    """Delete the learned optimizer data when the entry is removed."""
    await async_remove_optimizer(hass, entry.entry_id)
