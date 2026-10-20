"""Shared DataUpdateCoordinator for Kaschuetz."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    KaschuetzApiError,
    async_fetch_main_data,
    async_fetch_params,
    async_read_menu_params,
    async_save_process,
    async_set_menu_params,
)
from .const import (
    BURN_PARAM_KEYS,
    EVENT_SAVE_RESULT,
    SAVE_ALLOWED_STATES,
    SAVE_DEVICE_STATE_INACTIVE,
    SAVE_DEVICE_STATE_READY,
    SAVE_DEVICE_STATE_TO_STATUS,
    SAVE_PROCESS_POLL_SECONDS,
    SAVE_PROCESS_TIMEOUT_SECONDS,
    SAVE_RELOAD_DELAY_SECONDS,
    SAVE_RESULT_HOLD_SECONDS,
    SAVE_STATUS_CANCELLED,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_IDLE,
    SAVE_STATUS_STARTING,
    SAVE_STATUS_SUCCESS,
    SAVE_STATUS_TIMEOUT,
    SAVE_STATUS_WRITING,
)
from .optimizer import BurnOptimizer
from .params import parse_burn_params, parse_param, snap_param

_LOGGER = logging.getLogger(__name__)

STATE_LABELS: dict[int, str] = {
    0: "init",
    5: "waiting_for_active",
    6: "idle",
    7: "door_open",
    8: "searching_maximum",
    9: "burn_control",
    10: "burn_finished",
    11: "fault",
    40: "waiting",
}

ERROR_STATE_LABELS: dict[int, str] = {
    34: "fault",
    35: "temperature_sensor",
    36: "air_shutter",
    37: "power_supply",
    38: "ks",
    39: "air_shutter_2",
}

LANGUAGE_LABELS: dict[int, str] = {0: "de", 1: "en", 2: "cs", 3: "it", 4: "sk"}

PARAM_KEYS_WITH_LANGUAGE = ("spr", *BURN_PARAM_KEYS)


def map_state_to_text(state: Any) -> str | None:
    """Map device state code to a translation key."""
    return STATE_LABELS.get(state) if isinstance(state, int) else None


def map_error_state_to_text(error_state: Any) -> str:
    """Map device error code to a translation key ("none" without an error)."""
    if error_state is None:
        return "none"
    if isinstance(error_state, int):
        return ERROR_STATE_LABELS.get(error_state, "unknown")
    return "unknown"


def map_language(spr: Any) -> str | None:
    """Map the controller display language code."""
    return LANGUAGE_LABELS.get(spr) if isinstance(spr, int) else None


class KaschuetzDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate polling and the parameter save process of one controller."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        season_entity: str | None,
        poll_interval: int,
        optimizer: BurnOptimizer,
        persist_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
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

        # Parameters staged in Home Assistant until the save process writes them.
        self.pending_params: dict[str, int] = {}
        self.close_air_shutter = False
        self._last_menu_params: dict[str, int] = {}

        self.save_status = SAVE_STATUS_IDLE
        self.save_message: str | None = None
        self.save_last_result: dict[str, Any] | None = None
        self._save_deadline: float | None = None
        self._save_task: asyncio.Task[None] | None = None
        self._suggestion_cache: tuple[Any, dict[str, Any]] | None = None
        self._persisted_count = optimizer.sample_count()
        self._reset_status_unsub: CALLBACK_TYPE | None = None

    # ----------------------------------------------------------------- params

    def device_burn_params(self) -> dict[str, int] | None:
        """Return burn parameters as reported by the device, or None if incomplete."""
        return parse_burn_params(self.data)

    def device_language(self) -> int | None:
        """Return the controller language code (spr)."""
        return parse_param((self.data or {}).get("spr"))

    async def async_current_menu_params(self) -> dict[str, int] | None:
        """Return spr + burn parameters, querying the device if the poll lacks them."""
        params = self.device_burn_params()
        spr = self.device_language()
        if params is None or spr is None:
            try:
                data = await async_fetch_params(self.hass, self.host)
            except KaschuetzApiError as err:
                _LOGGER.warning("Could not read menu parameters from device: %s", err)
                return None
            params = parse_burn_params(data)
            spr = parse_param(data.get("spr"))
            if params is None or spr is None:
                return None
        return {"spr": spr, **params}

    def target_params(self) -> dict[str, int] | None:
        """Return device parameters with staged changes applied."""
        current = self.device_burn_params()
        if current is None:
            return None
        return {**current, **self.pending_params}

    def stage_param(self, key: str, value: float) -> int:
        """Stage one burn parameter (snapped to the device grid) for the next save."""
        snapped = snap_param(key, value)
        current = self.device_burn_params()
        if current is not None and current.get(key) == snapped:
            self.pending_params.pop(key, None)
        else:
            self.pending_params[key] = snapped
        self.async_update_listeners()
        return snapped

    def stage_params(self, params: dict[str, Any]) -> dict[str, int]:
        """Stage several burn parameters at once."""
        staged = {
            key: self.stage_param(key, params[key])
            for key in BURN_PARAM_KEYS
            if params.get(key) is not None
        }
        return staged

    def set_close_air_shutter(self, value: bool) -> None:
        """Stage the "close air shutter" flag for the next save."""
        self.close_air_shutter = bool(value)
        self.async_update_listeners()

    def discard_pending(self) -> None:
        """Drop all staged changes."""
        self.pending_params = {}
        self.close_air_shutter = False
        self.async_update_listeners()

    @property
    def has_pending_changes(self) -> bool:
        """Return whether a save would change anything."""
        return bool(self.pending_params) or self.close_air_shutter

    def suggestion(self, options: dict[str, Any]) -> dict[str, Any]:
        """Return the optimizer suggestion, cached until the next poll."""
        key = (self.last_success, self.optimizer.sample_count(), repr(sorted(options.items())))
        if self._suggestion_cache is None or self._suggestion_cache[0] != key:
            self._suggestion_cache = (
                key,
                self.optimizer.calculate(self.optimizer_input(options)),
            )
        return self._suggestion_cache[1]

    def optimizer_input(self, options: dict[str, Any]) -> dict[str, Any]:
        """Return optimizer input with the device's current burn parameters as baseline."""
        # Burn parameters stored in the options by versions < 1.5 are ignored.
        current = {key: value for key, value in options.items() if key not in BURN_PARAM_KEYS}
        current.update(self.device_burn_params() or {})
        return current

    # ------------------------------------------------------------ save process

    @property
    def save_in_progress(self) -> bool:
        """Return whether the save process is currently running."""
        return self._save_task is not None and not self._save_task.done()

    @property
    def save_remaining_seconds(self) -> int | None:
        """Return the seconds left to complete the door sequence."""
        if not self.save_in_progress or self._save_deadline is None:
            return None
        return max(0, round(self._save_deadline - self.hass.loop.time()))

    async def async_start_save(self) -> None:
        """Start the device save process for the staged parameters.

        The controller only accepts new parameters in the states "waiting for
        active", "idle" or "burn finished", and only after the filling door has
        been opened and closed again at the oven.
        """
        if self.save_in_progress:
            raise HomeAssistantError("A save process is already running")
        state = (self.data or {}).get("state")
        if state not in SAVE_ALLOWED_STATES:
            raise HomeAssistantError(
                "Parameters can only be saved in the states waiting for active, "
                f"idle or burn finished (current state: {map_state_to_text(state) or state})"
            )
        menu = await self.async_current_menu_params()
        if menu is None:
            raise HomeAssistantError(
                "Current parameters were not reported by the device; refusing to write"
            )
        target = {**{key: menu[key] for key in BURN_PARAM_KEYS}, **self.pending_params}
        if target == {key: menu[key] for key in BURN_PARAM_KEYS} and not self.close_air_shutter:
            raise HomeAssistantError("No pending parameter changes to save")

        if self._reset_status_unsub is not None:
            self._reset_status_unsub()
            self._reset_status_unsub = None
        self._save_deadline = self.hass.loop.time() + SAVE_PROCESS_TIMEOUT_SECONDS
        self._set_save_status(SAVE_STATUS_STARTING)
        self._save_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_run_save(target, menu["spr"], self.close_air_shutter),
            name=f"kaschuetz_save_{self.host}",
        )
        # Entities (e.g. button availability) depend on the task being done.
        self._save_task.add_done_callback(lambda _: self.async_update_listeners())

    async def async_cancel_save(self) -> None:
        """Cancel a running save process."""
        if self.save_in_progress and self._save_task is not None:
            self._save_task.cancel()
            # Wait until the device has been told to leave the save mode.
            await asyncio.gather(self._save_task, return_exceptions=True)
            return
        # Nothing running in HA; still make sure the device leaves the save mode.
        try:
            await async_save_process(self.hass, self.host, False)
        except KaschuetzApiError as err:
            raise HomeAssistantError(f"Could not cancel save process: {err}") from err

    async def async_shutdown(self) -> None:
        """Cancel a running save process on unload."""
        if self._reset_status_unsub is not None:
            self._reset_status_unsub()
            self._reset_status_unsub = None
        if self.save_in_progress and self._save_task is not None:
            self._save_task.cancel()
            await asyncio.gather(self._save_task, return_exceptions=True)
        await super().async_shutdown()

    def _set_save_status(self, status: str, message: str | None = None) -> None:
        self.save_status = status
        self.save_message = message
        self.async_update_listeners()

    def _finish_save(self, status: str, params: dict[str, int], message: str | None = None) -> None:
        self.save_last_result = {
            "status": status,
            "params": params,
            "message": message,
            "finished": dt_util.utcnow().isoformat(),
        }
        self._save_deadline = None
        self._set_save_status(status, message)
        self._schedule_status_reset()
        self.hass.bus.async_fire(
            EVENT_SAVE_RESULT,
            {"entry_id": self.config_entry.entry_id, **self.save_last_result},
        )

    def _schedule_status_reset(self) -> None:
        """Return to idle a while after a finished save; last_result keeps the outcome."""
        if self._reset_status_unsub is not None:
            self._reset_status_unsub()

        @callback
        def _reset(_now: Any) -> None:
            self._reset_status_unsub = None
            if not self.save_in_progress:
                self._set_save_status(SAVE_STATUS_IDLE)

        self._reset_status_unsub = async_call_later(
            self.hass, SAVE_RESULT_HOLD_SECONDS, _reset
        )

    async def _async_cancel_device_save(self) -> None:
        try:
            await async_save_process(self.hass, self.host, False)
        except KaschuetzApiError as err:
            _LOGGER.warning("Could not end save process on device: %s", err)

    async def _async_run_save(
        self, target: dict[str, int], spr: int, close_air_shutter: bool
    ) -> None:
        """Drive the save process: keep it alive, follow the door prompts, then write."""
        try:
            while True:
                response = await async_save_process(self.hass, self.host, True)
                device_state = response.get("saveParamsState")

                if device_state == SAVE_DEVICE_STATE_READY:
                    self._set_save_status(SAVE_STATUS_WRITING)
                    ok = await async_set_menu_params(
                        self.hass, self.host, target, spr, close_air_shutter
                    )
                    if not ok:
                        self._finish_save(
                            SAVE_STATUS_FAILED, target, "Device rejected the parameters"
                        )
                        return
                    try:
                        await async_read_menu_params(self.hass, self.host)
                    except KaschuetzApiError as err:
                        _LOGGER.debug("Re-reading menu parameters failed: %s", err)
                    self.pending_params = {
                        key: value
                        for key, value in self.pending_params.items()
                        if value != target.get(key)
                    }
                    self.close_air_shutter = False
                    # Show the confirmed values right away; the refresh below re-reads them.
                    self._last_menu_params = {"spr": spr, **target}
                    self.data = {**(self.data or {}), **target}
                    self._finish_save(SAVE_STATUS_SUCCESS, target)
                    # The controller needs a moment before it reports the new values.
                    await asyncio.sleep(SAVE_RELOAD_DELAY_SECONDS)
                    await self.async_request_refresh()
                    return

                if device_state == SAVE_DEVICE_STATE_INACTIVE:
                    self._finish_save(
                        SAVE_STATUS_FAILED, target, "Save mode was ended by the controller"
                    )
                    return

                status = SAVE_DEVICE_STATE_TO_STATUS.get(device_state, SAVE_STATUS_STARTING)
                if status != self.save_status:
                    self._set_save_status(status)
                else:
                    self.async_update_listeners()  # refresh remaining time

                if self.hass.loop.time() >= (self._save_deadline or 0):
                    await self._async_cancel_device_save()
                    self._finish_save(
                        SAVE_STATUS_TIMEOUT, target, "Door sequence not completed in time"
                    )
                    return
                await asyncio.sleep(SAVE_PROCESS_POLL_SECONDS)
        except asyncio.CancelledError:
            await asyncio.shield(self._async_cancel_device_save())
            self._finish_save(SAVE_STATUS_CANCELLED, target)
            raise
        except KaschuetzApiError as err:
            await self._async_cancel_device_save()
            self._finish_save(SAVE_STATUS_FAILED, target, str(err))

    # ------------------------------------------------------------------ polling

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
                _LOGGER.debug("Season is 'summer'; skipping Kaschuetz device call.")
                return {}

        try:
            data = await async_fetch_main_data(self.hass, self.host)
        except KaschuetzApiError as err:
            self.failed_polls += 1
            self.consecutive_failures += 1
            self.last_error = str(err)
            raise UpdateFailed(f"Error communicating with Kaschuetz: {err}") from err

        # Keep the last known menu parameters if a fallback poll did not include them.
        menu = {key: parse_param(data.get(key)) for key in PARAM_KEYS_WITH_LANGUAGE}
        if all(value is not None for value in menu.values()):
            self._last_menu_params = {key: int(value) for key, value in menu.items()}
        elif self._last_menu_params:
            data = {**data, **self._last_menu_params}

        self.successful_polls += 1
        self.consecutive_failures = 0
        self.last_success = dt_util.utcnow()
        self.last_error = None
        self.optimizer.add_sample(data)

        # Drop staged values the device already has.
        current = parse_burn_params(data) or {}
        self.pending_params = {
            key: value for key, value in self.pending_params.items() if current.get(key) != value
        }

        count = self.optimizer.sample_count()
        if self._persist_callback and count != self._persisted_count and count % 25 == 0:
            self._persisted_count = count
            await self._persist_callback()
        return data
