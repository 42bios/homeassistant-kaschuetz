"""Kaschuetz sensor platform with DataUpdateCoordinator.

Provides temperature, door_status, flap_position, burn_status, and error sensors.
"""

from __future__ import annotations

import logging
import requests
from datetime import timedelta
from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
    UpdateFailed,
)
from .const import (
    DOMAIN, DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

def map_state_to_text(state: Optional[int]) -> str:
    """
    Convert numeric states to text labels.
    If state is None or unknown, return "unknown".
    """
    state_map = {
        1: "Standby",
        2: "Start",
        3: "Betrieb",
        4: "Glutphase",
        5: "Warte auf Aktiv",
        6: "Ruhezustand",
        7: "Fülltür offen",
        8: "Suche Maximum",
        9: "Abbrandregelung",
        10: "Abbrand beendet",
    }
    return state_map.get(state, "unknown")

def _fetch_kaschuetz_data(host: str) -> dict[str, Any]:
    """
    Perform a single request to the device to get main Temp/State (rqType=1).
    Return a dict with keys like: {"Temp": 22, "state":3, "ComError":9, ...}
    """
    url = f"http://{host}/jsonRq"
    try:
        resp = requests.post(url, json={"rqType": 1}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        _LOGGER.debug("Fetched main data from device: %s", data)
        return data
    except requests.RequestException as err:
        raise UpdateFailed(f"Error communicating with Kaschuetz: {err}") from err

class KaschuetzDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates fetching device data in regular intervals."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        season_entity: str | None,
        poll_interval: int
    ) -> None:
        """
        Initialize the coordinator.

        :param host: IP or hostname of the device
        :param season_entity: optional entity_id for season (if 'summer' => skip)
        :param poll_interval: how often in seconds we poll the device
        """
        super().__init__(
            hass,
            _LOGGER,
            name="Kaschuetz Data Coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.host = host
        self.season_entity = season_entity

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Fetch data from the device. If season=summer, skip requests to avoid errors.
        Return an empty dict if skipping or if device offline.
        """
        if self.season_entity:
            season_state = self.hass.states.get(self.season_entity)
            if season_state and season_state.state.lower() == "summer":
                _LOGGER.info("Season is 'summer'; skipping Kaschuetz device call.")
                return {}

        return await self.hass.async_add_executor_job(_fetch_kaschuetz_data, self.host)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """
    Set up Kaschuetz sensors from a config entry.

    This is called after the user configures the integration in the UI.
    """
    data = entry.data
    host: str = data["host"]
    season_entity: str | None = data.get("season_entity")

    poll_interval = entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL)
    _LOGGER.debug("Kaschuetz sensor setup with poll interval: %s", poll_interval)

    coordinator = KaschuetzDataCoordinator(hass, host, season_entity, poll_interval)
    await coordinator.async_config_entry_first_refresh()

    sensors = [
        KaschuetzSensor(coordinator, "temperature"),
        KaschuetzSensor(coordinator, "door_status"),
        KaschuetzSensor(coordinator, "flap_position"),
        KaschuetzSensor(coordinator, "burn_status"),
        KaschuetzSensor(coordinator, "error"),
    ]
    async_add_entities(sensors, update_before_add=True)

class KaschuetzSensor(CoordinatorEntity, SensorEntity):
    """
    A single sensor reading from the shared DataUpdateCoordinator.

    sensor_type can be one of:
      - 'temperature'
      - 'door_status'
      - 'flap_position'
      - 'burn_status'
      - 'error'
    """

    def __init__(
        self,
        coordinator: KaschuetzDataCoordinator,
        sensor_type: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"kaschuetz_{sensor_type}_{coordinator.host}"
        self._attr_name = f"{DEFAULT_NAME} {sensor_type.capitalize()}"

    @property
    def native_value(self) -> str | int | None:
        """Return the sensor's value from coordinator data, or None if not available."""
        data = self.coordinator.data
        if not data:
            return None

        if self._sensor_type == "temperature":
            return data.get("Temp")
        elif self._sensor_type == "door_status":
            st = data.get("state")
            return "open" if st == 7 else "closed"
        elif self._sensor_type == "flap_position":
            return data.get("Klappe")
        elif self._sensor_type == "burn_status":
            st = data.get("state")
            return map_state_to_text(st if isinstance(st, int) else None)
        elif self._sensor_type == "error":
            return data.get("errorState", "none")

        return None
