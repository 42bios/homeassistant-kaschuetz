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
        self._attr_unique_id = f"kaschuetz_{description.key}_{coordinator.host}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name=DEFAULT_NAME,
            manufacturer="Kaschuetz",
            model="Euromatic oven controller",
            configuration_url=f"http://{coordinator.host}/",
        )
