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

from .const import DOMAIN, RUNTIME_COORDINATOR, STATE_DOOR_OPEN, STATE_FAULT
from .coordinator import KaschuetzDataCoordinator
from .entity import KaschuetzEntity

BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="door_open",
        translation_key="door_open",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    BinarySensorEntityDescription(
        key="fault",
        translation_key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
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
    async_add_entities(
        KaschuetzBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class KaschuetzBinarySensor(KaschuetzEntity, BinarySensorEntity):
    """Kaschuetz binary sensor entity."""

    @property
    def available(self) -> bool:
        """Keep the communication sensor available when polling fails."""
        if self.entity_description.key == "communication_problem":
            return True
        return super().available

    @property
    def is_on(self) -> bool | None:
        """Return binary state."""
        key = self.entity_description.key
        if key == "communication_problem":
            return not self.coordinator.last_update_success
        data = self.coordinator.data or {}
        if not data:
            return None
        if key == "door_open":
            return data.get("state") == STATE_DOOR_OPEN
        if key == "fault":
            return data.get("state") == STATE_FAULT or data.get("errorState") is not None
        return None
