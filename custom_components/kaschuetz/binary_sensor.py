"""Kaschuetz binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, RUNTIME_COORDINATOR
from .coordinator import KaschuetzDataCoordinator

BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="door_open",
        translation_key="door_open",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    BinarySensorEntityDescription(
        key="communication_problem",
        translation_key="communication_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz binary sensors."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    entities = [
        KaschuetzBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class KaschuetzBinarySensor(
    CoordinatorEntity[KaschuetzDataCoordinator], BinarySensorEntity
):
    """Kaschuetz binary sensor entity."""

    def __init__(
        self,
        coordinator: KaschuetzDataCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"kaschuetz_{description.key}_{coordinator.host}"
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {("kaschuetz", coordinator.host)},
            "name": DEFAULT_NAME,
            "manufacturer": "Kaschuetz",
            "model": "Oven Controller",
        }

    @property
    def is_on(self) -> bool:
        """Return binary state."""
        data = self.coordinator.data or {}
        if self.entity_description.key == "door_open":
            return data.get("state") == 7
        if self.entity_description.key == "communication_problem":
            com_error = data.get("ComError")
            if isinstance(com_error, int) and com_error != 0:
                return True
            return self.coordinator.consecutive_failures > 0
        return False
