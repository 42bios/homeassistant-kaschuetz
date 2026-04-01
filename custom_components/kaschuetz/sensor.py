"""Kaschuetz sensor platform."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, RUNTIME_COORDINATOR
from .coordinator import (
    KaschuetzDataCoordinator,
    map_com_error_to_text,
    map_error_state_to_text,
    map_state_to_text,
)

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(key="flap_position", translation_key="flap_position"),
    SensorEntityDescription(key="burn_status", translation_key="burn_status"),
    SensorEntityDescription(
        key="com_error_code",
        translation_key="com_error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="com_error_text",
        translation_key="com_error_text",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="spr_code",
        translation_key="spr_code",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="error_state_code",
        translation_key="error_state_code",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="error_state_text",
        translation_key="error_state_text",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="connection_quality",
        translation_key="connection_quality",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="consecutive_failures",
        translation_key="consecutive_failures",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_successful_poll",
        translation_key="last_successful_poll",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="optimizer_samples",
        translation_key="optimizer_samples",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="optimizer_cycles",
        translation_key="optimizer_cycles",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="optimizer_confidence",
        translation_key="optimizer_confidence",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="device_a_temp",
        translation_key="device_a_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="device_sch_w",
        translation_key="device_sch_w",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="device_reg_w",
        translation_key="device_reg_w",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="device_reg_p",
        translation_key="device_reg_p",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz sensors from config entry."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    entities = [
        KaschuetzSensor(entry, coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class KaschuetzSensor(CoordinatorEntity[KaschuetzDataCoordinator], SensorEntity):
    """Single sensor backed by the shared Kaschuetz coordinator."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: KaschuetzDataCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
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
    def native_value(self):
        """Return current sensor value from coordinator data."""
        data = self.coordinator.data or {}
        key = self.entity_description.key

        if key == "temperature":
            return data.get("Temp")
        if key == "flap_position":
            return data.get("Klappe")
        if key == "burn_status":
            state = data.get("state")
            return map_state_to_text(state if isinstance(state, int) else None)
        if key == "com_error_code":
            return data.get("ComError")
        if key == "com_error_text":
            com_error = data.get("ComError")
            return map_com_error_to_text(com_error if isinstance(com_error, int) else None)
        if key == "spr_code":
            return data.get("spr")
        if key == "error_state_code":
            return data.get("errorState")
        if key == "error_state_text":
            error_state = data.get("errorState")
            return map_error_state_to_text(error_state if isinstance(error_state, int) else None)
        if key == "connection_quality":
            return self.coordinator.connection_quality
        if key == "consecutive_failures":
            return self.coordinator.consecutive_failures
        if key == "last_successful_poll":
            return self.coordinator.last_success
        if key == "optimizer_samples":
            return self.coordinator.optimizer.sample_count()
        if key == "optimizer_cycles":
            suggestion = self.coordinator.optimizer.calculate(dict(self._entry.options))
            return suggestion.get("cycles_used")
        if key == "optimizer_confidence":
            suggestion = self.coordinator.optimizer.calculate(dict(self._entry.options))
            return suggestion.get("confidence")
        if key == "device_a_temp":
            return data.get("aTemp")
        if key == "device_sch_w":
            return data.get("schW")
        if key == "device_reg_w":
            return data.get("regW")
        if key == "device_reg_p":
            return data.get("regP")
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        """Expose additional diagnostics for optimization sensors."""
        key = self.entity_description.key
        if key in {"optimizer_cycles", "optimizer_confidence"}:
            suggestion = self.coordinator.optimizer.calculate(dict(self._entry.options))
            return {
                "samples_used": suggestion.get("samples_used"),
                "cycles_used": suggestion.get("cycles_used"),
                "stats": suggestion.get("stats"),
                "cycle_stats": suggestion.get("cycle_stats"),
                "optimizer_mode": suggestion.get("optimizer_mode"),
            }
        return None
