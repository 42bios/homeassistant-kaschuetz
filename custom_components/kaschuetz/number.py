"""Kaschuetz number platform for burn parameters.

Changing a number only stages the value in Home Assistant. The controller
accepts new parameters exclusively through its save process (filling door
open/close at the oven), which is started with the "Save parameters" button.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BURN_PARAM_LIMITS, BURN_PARAM_SCALE, DOMAIN, RUNTIME_COORDINATOR
from .coordinator import KaschuetzDataCoordinator
from .entity import KaschuetzEntity


@dataclass(frozen=True, kw_only=True)
class KaschuetzNumberDescription(NumberEntityDescription):
    """Metadata for a burn parameter; limits come from the device web UI."""

    param: str


NUMBER_DESCRIPTIONS: tuple[KaschuetzNumberDescription, ...] = (
    KaschuetzNumberDescription(
        key="aTemp",
        param="aTemp",
        translation_key="a_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    KaschuetzNumberDescription(
        key="schW",
        param="schW",
        translation_key="sch_w",
        native_unit_of_measurement=PERCENTAGE,
    ),
    KaschuetzNumberDescription(
        key="regW",
        param="regW",
        translation_key="reg_w",
        native_unit_of_measurement=PERCENTAGE,
    ),
    KaschuetzNumberDescription(
        key="regP",
        param="regP",
        translation_key="reg_p",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz number entities."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    async_add_entities(
        KaschuetzNumberEntity(coordinator, description) for description in NUMBER_DESCRIPTIONS
    )


class KaschuetzNumberEntity(KaschuetzEntity, NumberEntity):
    """Burn parameter: shows the staged value, or the device value without changes."""

    entity_description: KaschuetzNumberDescription
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: KaschuetzDataCoordinator, description: KaschuetzNumberDescription
    ) -> None:
        super().__init__(coordinator, description)
        min_value, max_value, step = BURN_PARAM_LIMITS[description.param]
        self._scale = BURN_PARAM_SCALE[description.param]
        self._attr_native_min_value = min_value / self._scale
        self._attr_native_max_value = max_value / self._scale
        self._attr_native_step = step / self._scale

    def _device_raw(self) -> int | None:
        params = self.coordinator.device_burn_params()
        return params.get(self.entity_description.param) if params else None

    @property
    def native_value(self) -> float | None:
        """Return the staged value, otherwise the value reported by the device."""
        raw = self.coordinator.pending_params.get(self.entity_description.param)
        if raw is None:
            raw = self._device_raw()
        return None if raw is None else raw / self._scale

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the device value and whether a change is staged."""
        device_raw = self._device_raw()
        return {
            "device_value": None if device_raw is None else device_raw / self._scale,
            "pending": self.entity_description.param in self.coordinator.pending_params,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Stage the new value for the next save process."""
        if self.coordinator.save_in_progress:
            raise HomeAssistantError("Cannot change parameters while a save is running")
        self.coordinator.stage_param(self.entity_description.param, value * self._scale)
