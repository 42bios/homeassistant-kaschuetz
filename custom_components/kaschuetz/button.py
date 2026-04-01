"""Kaschuetz button platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, RUNTIME_COORDINATOR
from .coordinator import KaschuetzDataCoordinator


@dataclass(frozen=True, kw_only=True)
class KaschuetzButtonDescription(ButtonEntityDescription):
    """Description for Kaschuetz action buttons."""

    key: str
    service: str
    service_data: dict[str, Any]
    entity_category: EntityCategory | None = None


BUTTONS: tuple[KaschuetzButtonDescription, ...] = (
    KaschuetzButtonDescription(
        key="calculate_optimization",
        translation_key="calculate_optimization",
        service="calculate_optimization",
        service_data={},
        entity_category=EntityCategory.CONFIG,
    ),
    KaschuetzButtonDescription(
        key="apply_optimization_safe",
        translation_key="apply_optimization_safe",
        service="apply_optimization",
        service_data={"write_to_device": False, "min_confidence": "medium"},
        entity_category=EntityCategory.CONFIG,
    ),
    KaschuetzButtonDescription(
        key="apply_optimization_device",
        translation_key="apply_optimization_device",
        service="apply_optimization",
        service_data={"write_to_device": True, "min_confidence": "high"},
        entity_category=EntityCategory.CONFIG,
    ),
    KaschuetzButtonDescription(
        key="reset_optimization_data",
        translation_key="reset_optimization_data",
        service="reset_optimization_data",
        service_data={},
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz button entities."""
    coordinator: KaschuetzDataCoordinator = hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
    async_add_entities(
        [
            KaschuetzActionButton(hass, entry, coordinator, description)
            for description in BUTTONS
        ]
    )


class KaschuetzActionButton(CoordinatorEntity[KaschuetzDataCoordinator], ButtonEntity):
    """Action button triggering Kaschuetz services for the current entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: KaschuetzDataCoordinator,
        description: KaschuetzButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"kaschuetz_{description.key}_{coordinator.host}"
        self._attr_has_entity_name = True
        self._attr_entity_category = description.entity_category
        self._attr_device_info = {
            "identifiers": {("kaschuetz", coordinator.host)},
            "name": DEFAULT_NAME,
            "manufacturer": "Kaschuetz",
            "model": "Oven Controller",
        }

    async def async_press(self) -> None:
        """Trigger configured service."""
        data = {"entry_id": self._entry.entry_id, **self.entity_description.service_data}
        await self.hass.services.async_call(
            DOMAIN,
            self.entity_description.service,
            data,
            blocking=True,
        )
