"""Tests for staging parameters and the controller save process."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.kaschuetz.const import DOMAIN, EVENT_SAVE_RESULT, RUNTIME_COORDINATOR

from .fake_device import RQ_SAVE_PARAMS_PROCESS, RQ_SET_MENU_PARAMS, FakeDevice


def _eid(hass: HomeAssistant, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"kaschuetz_{key}_192.0.2.10"
    )
    assert entity_id, f"{platform} {key} not registered"
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]


async def _set_number(hass: HomeAssistant, key: str, value: float) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _eid(hass, "number", key), "value": value},
        blocking=True,
    )


async def _wait_for_save(hass: HomeAssistant, coordinator) -> None:
    if coordinator._save_task is not None:
        await coordinator._save_task
    await hass.async_block_till_done()


def _set_requests(device: FakeDevice) -> list[dict]:
    return [r for r in device.requests if int(r["rqType"]) & RQ_SET_MENU_PARAMS]


async def test_entities_show_device_values(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """Numbers show the device values in display units."""
    await _setup(hass, entry)
    assert float(hass.states.get(_eid(hass, "number", "aTemp")).state) == 350
    assert float(hass.states.get(_eid(hass, "number", "schW")).state) == 37.5
    assert float(hass.states.get(_eid(hass, "number", "regW")).state) == 5.0
    assert float(hass.states.get(_eid(hass, "number", "regP")).state) == 150
    assert hass.states.get(_eid(hass, "sensor", "burn_status")).state == "idle"
    assert hass.states.get(_eid(hass, "sensor", "spr_text")).state == "de"
    assert hass.states.get(_eid(hass, "sensor", "save_process")).state == "idle"
    # ComError is constantly 3 on real devices and must not count as a problem.
    assert hass.states.get(_eid(hass, "binary_sensor", "communication_problem")).state == "off"
    assert hass.states.get(_eid(hass, "binary_sensor", "fault")).state == "off"


async def test_number_change_is_staged_not_written(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """Changing a number never writes to the device and snaps to the device grid."""
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    await _set_number(hass, "schW", 40)
    await hass.async_block_till_done()

    assert coordinator.pending_params == {"aTemp": 300, "schW": 400}
    assert not _set_requests(device)
    state = hass.states.get(_eid(hass, "number", "aTemp"))
    assert float(state.state) == 300
    assert state.attributes["device_value"] == 350
    assert state.attributes["pending"] is True

    # Setting a value back to the device value drops the staged change.
    await _set_number(hass, "aTemp", 350)
    assert coordinator.pending_params == {"schW": 400}


async def test_full_save_process(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """Save follows the door prompts and then writes all six values once."""
    coordinator = await _setup(hass, entry)
    events = async_capture_events(hass, EVENT_SAVE_RESULT)
    await _set_number(hass, "regP", 250)

    await hass.services.async_call(
        "button", "press", {"entity_id": _eid(hass, "button", "start_save_process")}, blocking=True
    )
    await _wait_for_save(hass, coordinator)

    writes = _set_requests(device)
    assert len(writes) == 1
    body = writes[0]
    assert body["rqType"] == RQ_SET_MENU_PARAMS | RQ_SAVE_PARAMS_PROCESS
    assert body["saveParamsActive"] is False
    assert body["spr"] == 0
    assert body["closeAirShutter"] is False
    assert {k: body[k] for k in ("aTemp", "schW", "regW", "regP")} == {
        "aTemp": 350,
        "schW": 375,
        "regW": 500,
        "regP": 250,
    }
    # Keep-alive requests precede the write.
    keep_alive = [
        r for r in device.requests if r["rqType"] == RQ_SAVE_PARAMS_PROCESS and r["saveParamsActive"]
    ]
    assert len(keep_alive) >= 4

    assert coordinator.save_status == "success"
    assert coordinator.pending_params == {}
    assert coordinator.data["regP"] == 250
    assert device.params["regP"] == 250
    assert float(hass.states.get(_eid(hass, "number", "regP")).state) == 250
    assert events and events[0].data["status"] == "success"


async def test_save_refused_in_burn_state(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The controller only saves in waiting for active, idle or burn finished."""
    device.state = 9
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    with pytest.raises(HomeAssistantError, match="only be saved"):
        await coordinator.async_start_save()
    assert not _set_requests(device)


async def test_save_refused_without_changes(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """Nothing staged means nothing to save."""
    coordinator = await _setup(hass, entry)
    with pytest.raises(HomeAssistantError, match="No pending"):
        await coordinator.async_start_save()


async def test_save_refused_without_device_params(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """Without reported parameters nothing is written (no fallback defaults)."""
    device.supports_params = False
    coordinator = await _setup(hass, entry)
    assert hass.states.get(_eid(hass, "number", "aTemp")).state == "unknown"
    await _set_number(hass, "aTemp", 300)
    with pytest.raises(HomeAssistantError, match="not reported"):
        await coordinator.async_start_save()
    assert not _set_requests(device)


async def test_save_rejected_by_device(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """A rejected write is reported and the staged values are kept."""
    device.reject_write = True
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    await coordinator.async_start_save()
    await _wait_for_save(hass, coordinator)
    assert coordinator.save_status == "failed"
    assert coordinator.pending_params == {"aTemp": 300}
    assert device.params["aTemp"] == 350


async def test_save_timeout_cancels_on_device(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice, monkeypatch
) -> None:
    """If the door is never closed, the process ends and the device is told so."""
    monkeypatch.setattr("custom_components.kaschuetz.coordinator.SAVE_PROCESS_TIMEOUT_SECONDS", 0)
    device.door_sequence = [2]
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    await coordinator.async_start_save()
    await _wait_for_save(hass, coordinator)
    assert coordinator.save_status == "timeout"
    assert device.requests[-1] == {"rqType": RQ_SAVE_PARAMS_PROCESS, "saveParamsActive": False}
    assert not _set_requests(device)


async def test_cancel_save(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice, monkeypatch
) -> None:
    """Cancelling stops the process and ends it on the device."""
    monkeypatch.setattr("custom_components.kaschuetz.coordinator.SAVE_PROCESS_POLL_SECONDS", 0.05)
    device.door_sequence = [2, 3]
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    await coordinator.async_start_save()
    assert coordinator.save_in_progress
    await hass.services.async_call(DOMAIN, "cancel_save_process", {}, blocking=True)
    await hass.async_block_till_done()
    assert not coordinator.save_in_progress
    assert coordinator.save_status == "cancelled"
    assert device.requests[-1] == {"rqType": RQ_SAVE_PARAMS_PROCESS, "saveParamsActive": False}
    assert not _set_requests(device)


async def test_close_air_shutter_only_when_waiting(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The air shutter flag needs the state waiting for active and is sent on save."""
    coordinator = await _setup(hass, entry)
    switch = _eid(hass, "switch", "close_air_shutter")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)

    device.state = 5
    await coordinator.async_refresh()
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await coordinator.async_start_save()
    await _wait_for_save(hass, coordinator)
    assert _set_requests(device)[0]["closeAirShutter"] is True
    assert coordinator.close_air_shutter is False


async def test_options_flow_does_not_write(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The options flow no longer touches burn parameters."""
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "aTemp" not in result["data_schema"].schema
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"update_interval": 30}
    )
    await hass.async_block_till_done()
    assert not _set_requests(device)


async def test_apply_optimization_only_stages(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    """apply_optimization stages the suggestion; it never writes directly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.0.2.10"},
        options={"experimental_auto_optimize": True},
        unique_id="192.0.2.10",
    )
    coordinator = await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "apply_optimization", {}, blocking=True)
    # Too few samples: the suggestion equals the device values, nothing to stage.
    assert coordinator.pending_params == {}
    assert not _set_requests(device)


async def test_communication_problem(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """A failed poll flags the communication problem sensor."""
    coordinator = await _setup(hass, entry)
    device.fail = True
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(_eid(hass, "binary_sensor", "communication_problem")).state == "on"


async def test_export_file(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice, tmp_path
) -> None:
    """The file export works through the executor."""
    hass.config.config_dir = str(tmp_path)
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN, "export_burn_history_file", {"format": "csv"}, blocking=True
    )
    files = list((tmp_path / "kaschuetz_exports").glob("*.csv"))
    assert len(files) == 1
    assert files[0].read_text().startswith("index,time_offset_s,temp_c,flap")


async def test_save_ended_by_controller(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """If the controller leaves save mode on its own, the save fails right away."""
    device.door_sequence = [2, 0]
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    await coordinator.async_start_save()
    await _wait_for_save(hass, coordinator)
    assert coordinator.save_status == "failed"
    assert not _set_requests(device)


async def test_save_button_available_again_after_save(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The save button is offered again as soon as the process ended."""
    device.reject_write = True
    coordinator = await _setup(hass, entry)
    button = _eid(hass, "button", "start_save_process")
    await _set_number(hass, "aTemp", 300)
    await coordinator.async_start_save()
    await _wait_for_save(hass, coordinator)
    assert hass.states.get(button).state != "unavailable"


async def test_status_returns_to_idle(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The finished status is shown for a while, then the sensor is idle again."""
    coordinator = await _setup(hass, entry)
    await _set_number(hass, "aTemp", 300)
    await coordinator.async_start_save()
    await _wait_for_save(hass, coordinator)
    assert coordinator.save_status == "success"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=121))
    await hass.async_block_till_done()
    assert coordinator.save_status == "idle"
    assert coordinator.save_last_result["status"] == "success"
