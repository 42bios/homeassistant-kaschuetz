"""Kaschuetz number platform for burn parameters."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import KaschuetzApiError, async_send_abbrand_params
from .const import (
    CONF_HOST,
    DEFAULT_NAME,
    DOMAIN,
    RUNTIME_COORDINATOR,
)
from .coordinator import KaschuetzDataCoordinator


@dataclass(frozen=True, kw_only=True)
class KaschuetzNumberDescription(NumberEntityDescription):
    """Metadata for a writable Kaschuetz number entity."""

    key: str
    native_min_value: int
    native_max_value: int
    native_step: int


NUMBER_DESCRIPTIONS: tuple[KaschuetzNumberDescription, ...] = (
    KaschuetzNumberDescription(
        key="aTemp",
        translation_key="a_temp",
        native_min_value=120,
        native_max_value=320,
        native_step=1,
    ),
    KaschuetzNumberDescription(
        key="schW",
        translation_key="sch_w",
        native_min_value=120,
        native_max_value=700,
        native_step=1,
    ),
    KaschuetzNumberDescription(
        key="regW",
        translation_key="reg_w",
        native_min_value=200,
        native_max_value=1200,
        native_step=1,
    ),
    KaschuetzNumberDescription(
        key="regP",
        translation_key="reg_p",
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
    """Writable number entity mapped to a device burn parameter."""

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
    def native_value(self) -> float | None:
        """Return the burn parameter as currently reported by the device."""
        value = (self.coordinator.data or {}).get(self.entity_description.key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Push the changed parameter to the device, keeping the others as reported."""
        current = await self.coordinator.async_current_burn_params()
        if current is None:
            raise HomeAssistantError(
                "Current burn parameters were not reported by the device; refusing to write"
            )

        applied = {**current, self.entity_description.key: round(value)}

        try:
            await async_send_abbrand_params(self.hass, self._entry.data[CONF_HOST], applied)
        except KaschuetzApiError as err:
            raise HomeAssistantError(f"Failed writing burn parameters: {err}") from err

        await self.coordinator.async_request_refresh()
