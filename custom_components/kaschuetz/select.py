"""Kaschuetz select platform."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_OPTIMIZER_MODE,
    DOMAIN,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODES,
    RUNTIME_COORDINATOR,
)
from .coordinator import KaschuetzDataCoordinator
from .entity import KaschuetzEntity

OPTIMIZER_MODE = SelectEntityDescription(
    key="optimizer_mode",
    translation_key="optimizer_mode",
    entity_category=EntityCategory.CONFIG,
    options=OPTIMIZER_MODES,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz select entities."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    async_add_entities([KaschuetzOptimizerModeSelect(entry, coordinator)])


class KaschuetzOptimizerModeSelect(KaschuetzEntity, SelectEntity):
    """Select entity for optimizer behavior profile."""

    def __init__(self, entry: ConfigEntry, coordinator: KaschuetzDataCoordinator) -> None:
        super().__init__(coordinator, OPTIMIZER_MODE)
        self._entry = entry

    @property
    def current_option(self) -> str:
        """Return current optimizer mode."""
        mode = str(self._entry.options.get(CONF_OPTIMIZER_MODE, OPTIMIZER_MODE_BALANCED))
        return mode if mode in OPTIMIZER_MODES else OPTIMIZER_MODE_BALANCED

    async def async_select_option(self, option: str) -> None:
        """Set optimizer mode option."""
        new_options = {**dict(self._entry.options), CONF_OPTIMIZER_MODE: option}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()
