"""Kaschuetz button platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_EXPERIMENTAL_AUTO_OPTIMIZE,
    DOMAIN,
    SERVICE_CANCEL_SAVE_PROCESS,
    SERVICE_DISCARD_PENDING,
    SERVICE_START_SAVE_PROCESS,
)
from .coordinator import KaschuetzDataCoordinator
from .entity import KaschuetzEntity
from .models import KaschuetzConfigEntry


@dataclass(frozen=True, kw_only=True)
class KaschuetzButtonDescription(ButtonEntityDescription):
    """Description for Kaschuetz action buttons."""

    key: str
    service: str
    service_data: dict[str, Any]
    entity_category: EntityCategory | None = None


BUTTONS: tuple[KaschuetzButtonDescription, ...] = (
    KaschuetzButtonDescription(
        key="start_save_process",
        translation_key="start_save_process",
        service=SERVICE_START_SAVE_PROCESS,
        service_data={},
    ),
    KaschuetzButtonDescription(
        key="cancel_save_process",
        translation_key="cancel_save_process",
        service=SERVICE_CANCEL_SAVE_PROCESS,
        service_data={},
    ),
    KaschuetzButtonDescription(
        key="discard_pending_parameters",
        translation_key="discard_pending_parameters",
        service=SERVICE_DISCARD_PENDING,
        service_data={},
    ),
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
        service_data={"start_save": False, "min_confidence": "medium"},
        entity_category=EntityCategory.CONFIG,
    ),
    KaschuetzButtonDescription(
        key="apply_optimization_device",
        translation_key="apply_optimization_device",
        service="apply_optimization",
        service_data={"start_save": True, "min_confidence": "high"},
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
    entry: KaschuetzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz button entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        KaschuetzActionButton(entry, coordinator, description) for description in BUTTONS
    )


class KaschuetzActionButton(KaschuetzEntity, ButtonEntity):
    """Action button triggering Kaschuetz services for the current entry."""

    entity_description: KaschuetzButtonDescription

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: KaschuetzDataCoordinator,
        description: KaschuetzButtonDescription,
    ) -> None:
        super().__init__(coordinator, description)
        self._entry = entry
        self._attr_entity_category = description.entity_category

    async def async_press(self) -> None:
        """Trigger configured service."""
        data = {"entry_id": self._entry.entry_id, **self.entity_description.service_data}
        await self.hass.services.async_call(
            DOMAIN,
            self.entity_description.service,
            data,
            blocking=True,
        )

    @property
    def available(self) -> bool:
        """Only offer actions that make sense right now."""
        if not super().available:
            return False
        key = self.entity_description.key
        if key in {"apply_optimization_safe", "apply_optimization_device"}:
            return bool(self._entry.options.get(CONF_EXPERIMENTAL_AUTO_OPTIMIZE, False))
        if key == "start_save_process":
            return not self.coordinator.save_in_progress
        if key == "cancel_save_process":
            return self.coordinator.save_in_progress
        if key == "discard_pending_parameters":
            return self.coordinator.has_pending_changes and not self.coordinator.save_in_progress
        return True
