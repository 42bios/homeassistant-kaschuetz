"""Kaschuetz number platform for burn parameters."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import KaschuetzApiError, async_send_abbrand_params
from .const import (
    CONF_HOST,
    DEFAULT_A_TEMP,
    DEFAULT_NAME,
    DEFAULT_REGP,
    DEFAULT_REGW,
    DEFAULT_SCHW,
    DOMAIN,
    RUNTIME_COORDINATOR,
)
from .coordinator import KaschuetzDataCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class KaschuetzNumberDescription(NumberEntityDescription):
    """Metadata for a writable Kaschuetz number entity."""

    key: str
    name: str
    default_value: int
    native_min_value: int
    native_max_value: int
    native_step: int


NUMBER_DESCRIPTIONS: tuple[KaschuetzNumberDescription, ...] = (
    KaschuetzNumberDescription(
        key="aTemp",
        name="Active Temperature",
        default_value=DEFAULT_A_TEMP,
        native_min_value=120,
        native_max_value=320,
        native_step=1,
    ),
    KaschuetzNumberDescription(
        key="schW",
        name="Closing Value",
        default_value=DEFAULT_SCHW,
        native_min_value=120,
        native_max_value=700,
        native_step=1,
    ),
    KaschuetzNumberDescription(
        key="regW",
        name="Regulation Value",
        default_value=DEFAULT_REGW,
        native_min_value=200,
        native_max_value=1200,
        native_step=1,
    ),
    KaschuetzNumberDescription(
        key="regP",
        name="Regulation Period",
        default_value=DEFAULT_REGP,
        native_min_value=120,
        native_max_value=600,
        native_step=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz number entities."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    entities = [
        KaschuetzNumberEntity(hass, entry, coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    ]
    async_add_entities(entities)


class KaschuetzNumberEntity(CoordinatorEntity[KaschuetzDataCoordinator], NumberEntity):
    """Writable number entity mapped to burn parameter options."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: KaschuetzDataCoordinator,
        description: KaschuetzNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"kaschuetz_{description.key}_{coordinator.host}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_device_info = {
            "identifiers": {("kaschuetz", coordinator.host)},
            "name": DEFAULT_NAME,
            "manufacturer": "Kaschuetz",
            "model": "Oven Controller",
        }

    @property
    def native_value(self) -> float:
        """Return number value from config entry options."""
        try:
            return float(
                self._entry.options.get(
                    self.entity_description.key, self.entity_description.default_value
                )
            )
        except (TypeError, ValueError):
            return float(self.entity_description.default_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set number, persist in options, and push to device."""
        new_value = int(round(value))
        options = dict(self._entry.options)
        options[self.entity_description.key] = new_value

        applied = {
            "aTemp": int(options.get("aTemp", DEFAULT_A_TEMP)),
            "schW": int(options.get("schW", DEFAULT_SCHW)),
            "regW": int(options.get("regW", DEFAULT_REGW)),
            "regP": int(options.get("regP", DEFAULT_REGP)),
        }

        try:
            await async_send_abbrand_params(self.hass, self._entry.data[CONF_HOST], applied)
        except KaschuetzApiError as err:
            _LOGGER.error("Failed writing params from number entity: %s", err)
            return

        self.hass.config_entries.async_update_entry(self._entry, options=options)
        self.async_write_ha_state()
