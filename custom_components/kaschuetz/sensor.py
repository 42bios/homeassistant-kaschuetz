"""Kaschuetz sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    MATCH_ALL,
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BURN_PARAM_SCALE,
    SAVE_STATUSES,
)
from .coordinator import (
    ERROR_STATE_LABELS,
    LANGUAGE_LABELS,
    STATE_LABELS,
    KaschuetzDataCoordinator,
    map_error_state_to_text,
    map_language,
    map_state_to_text,
)
from .entity import KaschuetzEntity
from .models import KaschuetzConfigEntry
from .params import parse_param


@dataclass(frozen=True, kw_only=True)
class KaschuetzSensorDescription(SensorEntityDescription):
    """Sensor description with a value function."""

    value_fn: Callable[[KaschuetzSensor], Any]
    attributes_fn: Callable[[KaschuetzSensor], dict[str, Any] | None] | None = None
    unrecorded: bool = False


def _data(sensor: KaschuetzSensor) -> dict[str, Any]:
    return sensor.coordinator.data or {}


def _flap_percent(sensor: KaschuetzSensor) -> int | None:
    raw = _data(sensor).get("Klappe")
    if isinstance(raw, int) and 0 <= raw <= 7:
        return round((raw / 7) * 100)
    return None


def _device_param(key: str) -> Callable[[KaschuetzSensor], float | None]:
    def _value(sensor: KaschuetzSensor) -> float | None:
        raw = parse_param(_data(sensor).get(key))
        return None if raw is None else raw / BURN_PARAM_SCALE[key]

    return _value


def _kpi(key: str) -> Callable[[KaschuetzSensor], Any]:
    return lambda sensor: sensor.coordinator.optimizer.latest_history_kpis().get(key)


def _suggestion_attributes(sensor: KaschuetzSensor) -> dict[str, Any]:
    suggestion = sensor.suggestion()
    return {
        key: suggestion.get(key)
        for key in (
            "aTemp",
            "schW",
            "regW",
            "regP",
            "samples_used",
            "cycles_used",
            "stats",
            "cycle_stats",
            "kpis",
            "safety",
            "adjustments",
            "optimizer_mode",
            "optimizer_profile",
        )
    }


def _save_attributes(sensor: KaschuetzSensor) -> dict[str, Any]:
    coordinator = sensor.coordinator
    pending = {
        key: value / BURN_PARAM_SCALE[key] for key, value in coordinator.pending_params.items()
    }
    return {
        "remaining_seconds": coordinator.save_remaining_seconds,
        "message": coordinator.save_message,
        "pending_parameters": pending,
        "close_air_shutter": coordinator.close_air_shutter,
        "last_result": coordinator.save_last_result,
    }


SENSOR_DESCRIPTIONS: tuple[KaschuetzSensorDescription, ...] = (
    KaschuetzSensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: parse_param(_data(s).get("Temp")),
    ),
    KaschuetzSensorDescription(
        key="flap_position",
        translation_key="flap_position",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_flap_percent,
    ),
    KaschuetzSensorDescription(
        key="flap_position_raw",
        translation_key="flap_position_raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _data(s).get("Klappe"),
    ),
    KaschuetzSensorDescription(
        key="burn_status",
        translation_key="burn_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(STATE_LABELS.values()),
        value_fn=lambda s: map_state_to_text(_data(s).get("state")),
    ),
    KaschuetzSensorDescription(
        key="error_state_text",
        translation_key="error_state_text",
        device_class=SensorDeviceClass.ENUM,
        options=["none", *ERROR_STATE_LABELS.values(), "unknown"],
        value_fn=lambda s: map_error_state_to_text(_data(s).get("errorState")) if s.coordinator.data else None,
    ),
    KaschuetzSensorDescription(
        key="error_state_code",
        translation_key="error_state_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _data(s).get("errorState"),
    ),
    KaschuetzSensorDescription(
        key="com_error_code",
        translation_key="com_error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _data(s).get("ComError"),
    ),
    KaschuetzSensorDescription(
        key="spr_text",
        translation_key="spr_text",
        device_class=SensorDeviceClass.ENUM,
        options=list(LANGUAGE_LABELS.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: map_language(parse_param(_data(s).get("spr"))),
    ),
    KaschuetzSensorDescription(
        key="save_process",
        translation_key="save_process",
        device_class=SensorDeviceClass.ENUM,
        options=SAVE_STATUSES,
        value_fn=lambda s: s.coordinator.save_status,
        attributes_fn=_save_attributes,
    ),
    KaschuetzSensorDescription(
        key="device_a_temp",
        translation_key="device_a_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_device_param("aTemp"),
    ),
    KaschuetzSensorDescription(
        key="device_sch_w",
        translation_key="device_sch_w",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_device_param("schW"),
    ),
    KaschuetzSensorDescription(
        key="device_reg_w",
        translation_key="device_reg_w",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_device_param("regW"),
    ),
    KaschuetzSensorDescription(
        key="device_reg_p",
        translation_key="device_reg_p",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_device_param("regP"),
    ),
    KaschuetzSensorDescription(
        key="connection_quality",
        translation_key="connection_quality",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.coordinator.connection_quality,
    ),
    KaschuetzSensorDescription(
        key="consecutive_failures",
        translation_key="consecutive_failures",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.coordinator.consecutive_failures,
    ),
    KaschuetzSensorDescription(
        key="last_successful_poll",
        translation_key="last_successful_poll",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.coordinator.last_success,
    ),
    KaschuetzSensorDescription(
        key="optimizer_samples",
        translation_key="optimizer_samples",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.coordinator.optimizer.sample_count(),
    ),
    KaschuetzSensorDescription(
        key="optimizer_cycles",
        translation_key="optimizer_cycles",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.suggestion().get("cycles_used"),
    ),
    KaschuetzSensorDescription(
        key="optimizer_confidence",
        translation_key="optimizer_confidence",
        device_class=SensorDeviceClass.ENUM,
        options=["low", "medium", "high"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.suggestion().get("confidence"),
        attributes_fn=_suggestion_attributes,
        unrecorded=True,
    ),
    KaschuetzSensorDescription(
        key="burn_history_time_s",
        translation_key="burn_history_time_s",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.coordinator.optimizer.history_snapshot(include_arrays=False).get(
            "time_s"
        ),
        attributes_fn=lambda s: s.coordinator.optimizer.history_snapshot(include_arrays=True),
        unrecorded=True,
    ),
    KaschuetzSensorDescription(
        key="kpi_time_to_peak",
        translation_key="kpi_time_to_peak",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_kpi("time_to_peak_s"),
    ),
    KaschuetzSensorDescription(
        key="kpi_peak_temp",
        translation_key="kpi_peak_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_kpi("peak_temp"),
    ),
    KaschuetzSensorDescription(
        key="kpi_overshoot",
        translation_key="kpi_overshoot",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_kpi("overshoot"),
    ),
    KaschuetzSensorDescription(
        key="kpi_cooldown_rate",
        translation_key="kpi_cooldown_rate",
        native_unit_of_measurement="°C/min",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_kpi("cooldown_rate_c_per_min"),
    ),
    KaschuetzSensorDescription(
        key="kpi_flap_oscillation",
        translation_key="kpi_flap_oscillation",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_kpi("flap_oscillation"),
    ),
)

# Sensors removed in 1.5.0 (their mappings were not backed by the device protocol).
OBSOLETE_SENSOR_KEYS = ("com_error_text", "spr_code")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KaschuetzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz sensors from config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        KaschuetzSensor(entry, coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class KaschuetzSensor(KaschuetzEntity, SensorEntity):
    """Single sensor backed by the shared Kaschuetz coordinator."""

    entity_description: KaschuetzSensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: KaschuetzDataCoordinator,
        description: KaschuetzSensorDescription,
    ) -> None:
        super().__init__(coordinator, description)
        self._entry = entry
        if description.unrecorded:
            self._unrecorded_attributes = frozenset({MATCH_ALL})

    def suggestion(self) -> dict[str, Any]:
        """Return the cached optimizer suggestion for this entry."""
        return self.coordinator.suggestion(dict(self._entry.options))

    @property
    def native_value(self) -> Any:
        """Return current sensor value."""
        return self.entity_description.value_fn(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self)
