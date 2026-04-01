"""Kaschuetz select platform."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OPTIMIZER_MODE,
    DEFAULT_NAME,
    DOMAIN,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODES,
    RUNTIME_COORDINATOR,
)
from .coordinator import KaschuetzDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz select entities."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    async_add_entities([KaschuetzOptimizerModeSelect(hass, entry, coordinator)])


class KaschuetzOptimizerModeSelect(
    CoordinatorEntity[KaschuetzDataCoordinator], SelectEntity
):
    """Select entity for optimizer behavior profile."""

    _attr_options = OPTIMIZER_MODES

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator: KaschuetzDataCoordinator
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"kaschuetz_optimizer_mode_{coordinator.host}"
        self._attr_translation_key = "optimizer_mode"
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {("kaschuetz", coordinator.host)},
            "name": DEFAULT_NAME,
            "manufacturer": "Kaschuetz",
            "model": "Oven Controller",
        }

    @property
    def current_option(self) -> str:
        """Return current optimizer mode."""
        mode = str(self._entry.options.get(CONF_OPTIMIZER_MODE, OPTIMIZER_MODE_BALANCED))
        if mode in OPTIMIZER_MODES:
            return mode
        return OPTIMIZER_MODE_BALANCED

    async def async_select_option(self, option: str) -> None:
        """Set optimizer mode option."""
        if option not in OPTIMIZER_MODES:
            return
        new_options = {**dict(self._entry.options), CONF_OPTIMIZER_MODE: option}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()
