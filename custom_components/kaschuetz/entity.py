"""Base entity for the Kaschuetz integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import KaschuetzDataCoordinator


class KaschuetzEntity(CoordinatorEntity[KaschuetzDataCoordinator]):
    """Entity bound to one Kaschuetz controller."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: KaschuetzDataCoordinator, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"kaschuetz_{description.key}_{entry_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=DEFAULT_NAME,
            manufacturer="Kaschuetz",
            model="Euromatic oven controller",
            configuration_url=f"http://{coordinator.host}/",
        )
