"""Shared DataUpdateCoordinator for Kaschuetz."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import KaschuetzApiError, async_fetch_main_data
from .optimizer import BurnOptimizer

_LOGGER = logging.getLogger(__name__)

STATE_LABELS: dict[int, str] = {
    1: "Standby",
    2: "Start",
    3: "Betrieb",
    4: "Glutphase",
    5: "Warte auf Aktiv",
    6: "Ruhezustand",
    7: "Fuelltuere offen",
    8: "Suche Maximum",
    9: "Abbrandregelung",
    10: "Abbrand beendet",
}

COM_ERROR_LABELS: dict[int, str] = {
    0: "ok",
    1: "minor_communication_issue",
    2: "communication_retry",
    3: "device_not_ready",
    4: "sensor_problem",
    5: "actuator_problem",
    6: "thermal_guard",
    7: "controller_fault",
    8: "configuration_problem",
    9: "communication_lost",
}


def map_state_to_text(state: int | None) -> str:
    """Map integer state into readable text."""
    return STATE_LABELS.get(state, "unknown")


def map_com_error_to_text(com_error: int | None) -> str:
    """Map communication error code into readable text."""
    if com_error is None:
        return "unknown"
    return COM_ERROR_LABELS.get(com_error, f"unknown_{com_error}")


class KaschuetzDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate periodic polling of Kaschuetz device data."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        season_entity: str | None,
        poll_interval: int,
        optimizer: BurnOptimizer,
        persist_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Kaschuetz Data Coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.host = host
        self.season_entity = season_entity
        self.optimizer = optimizer
        self._persist_callback = persist_callback
        self.successful_polls = 0
        self.failed_polls = 0
        self.consecutive_failures = 0
        self.last_success: datetime | None = None
        self.last_error: str | None = None

    @property
    def connection_quality(self) -> float:
        """Return success ratio in percent."""
        total = self.successful_polls + self.failed_polls
        if total == 0:
            return 100.0
        return round((self.successful_polls / total) * 100.0, 1)

    async def _async_update_data(self) -> dict[str, Any]:
        if self.season_entity:
            season_state = self.hass.states.get(self.season_entity)
            if season_state and season_state.state.lower() == "summer":
                _LOGGER.info("Season is 'summer'; skipping Kaschuetz device call.")
                return {}

        try:
            data = await async_fetch_main_data(self.hass, self.host)
        except KaschuetzApiError as err:
            self.failed_polls += 1
            self.consecutive_failures += 1
            self.last_error = str(err)
            raise UpdateFailed(f"Error communicating with Kaschuetz: {err}") from err

        self.successful_polls += 1
        self.consecutive_failures = 0
        self.last_success = dt_util.utcnow()
        self.optimizer.add_sample(data)

        if self._persist_callback and self.optimizer.sample_count() % 25 == 0:
            await self._persist_callback()
        return data
