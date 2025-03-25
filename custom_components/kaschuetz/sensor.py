"""Kaschuetz sensor platform with DataUpdateCoordinator."""
from __future__ import annotations

import logging
import requests
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
    UpdateFailed,
)
from .const import DOMAIN, DEFAULT_NAME, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

def map_state_to_text(state: int | None) -> str:
    """Convert numeric states to text labels."""
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
    return state_map.get(state, "unknown") if state is not None else "unknown"

def _fetch_kaschuetz_data(host: str) -> dict:
    """Perform a single request to the device to get main Temp/State."""
    url = f"http://{host}/jsonRq"
    try:
        resp = requests.post(url, json={"rqType": 1}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as err:
        raise UpdateFailed(f"Error communicating with Kaschuetz: {err}") from err

class KaschuetzDataCoordinator(DataUpdateCoordinator[dict]):
    """Coordinates fetching device data in regular intervals."""

    def __init__(self, hass: HomeAssistant, host: str, season_entity: str | None, poll_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Kaschuetz Data Coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.host = host
        self.season_entity = season_entity

    async def _async_update_data(self) -> dict:
        """Fetch data. If season=summer, skip requests."""
        if self.season_entity:
            season_state = self.hass.states.get(self.season_entity)
            if season_state and season_state.state.lower() == "summer":
                _LOGGER.info("Season is 'summer'; skipping Kaschuetz device call.")
                return {}
        return await self.hass.async_add_executor_job(_fetch_kaschuetz_data, self.host)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.data
    host = data["host"]
    season_entity = data.get("season_entity")

    # Lese das Update-Intervall aus den Options
    # Falls nichts drin, nimm DEFAULT_UPDATE_INTERVAL
    poll_interval = entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL)

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
    """Represents a single sensor reading from the shared DataUpdateCoordinator."""

    def __init__(self, coordinator: KaschuetzDataCoordinator, sensor_type: str) -> None:
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"kaschuetz_{sensor_type}_{coordinator.host}"
        self._attr_name = f"{DEFAULT_NAME} {sensor_type.capitalize()}"

    @property
    def native_value(self):
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
            return map_state_to_text(st)
        elif self._sensor_type == "error":
            return data.get("errorState", "none")
        return None
