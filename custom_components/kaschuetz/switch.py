"""Kaschuetz switch platform ("close air shutter" flag of the save process)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CLOSE_AIR_SHUTTER_ALLOWED_STATES, DOMAIN
from .entity import KaschuetzEntity
from .models import KaschuetzConfigEntry

CLOSE_AIR_SHUTTER = SwitchEntityDescription(
    key="close_air_shutter",
    translation_key="close_air_shutter",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KaschuetzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaschuetz switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([KaschuetzCloseAirShutterSwitch(coordinator, CLOSE_AIR_SHUTTER)])


class KaschuetzCloseAirShutterSwitch(KaschuetzEntity, SwitchEntity):
    """Send "close air shutter" with the next save (web UI: "Zuluft zu").

    The controller only allows this in the state "waiting for active". The
    flag is reset after the save.
    """

    @property
    def is_on(self) -> bool:
        """Return whether the flag is staged."""
        return self.coordinator.close_air_shutter

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Stage the flag."""
        state = (self.coordinator.data or {}).get("state")
        if state not in CLOSE_AIR_SHUTTER_ALLOWED_STATES:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="close_air_shutter_not_allowed"
            )
        self.coordinator.set_close_air_shutter(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the flag."""
        self.coordinator.set_close_air_shutter(False)
