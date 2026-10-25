"""Tests for migration, reconfigure, services and diagnostics."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kaschuetz.const import DOMAIN
from custom_components.kaschuetz.diagnostics import async_get_config_entry_diagnostics

from .fake_device import FakeDevice

HOST = "192.0.2.10"


async def test_migration_keeps_entity_ids(hass: HomeAssistant, device: FakeDevice) -> None:
    """Version 1 entries move from host-based to entry-based unique ids."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": HOST}, unique_id=HOST, version=1)
    entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, HOST)}
    )
    temp = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"kaschuetz_temperature_{HOST}",
        config_entry=entry, device_id=device_entry.id,
        suggested_object_id="kaschuetz_oven_temperatur",
    )
    obsolete = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"kaschuetz_com_error_text_{HOST}", config_entry=entry
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    migrated = entity_registry.async_get(temp.entity_id)
    assert migrated is not None
    assert migrated.unique_id == f"kaschuetz_temperature_{entry.entry_id}"
    assert entity_registry.async_get(obsolete.entity_id) is None
    assert any(
        (DOMAIN, entry.entry_id) in d.identifiers
        for d in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    )
    assert hass.states.get(temp.entity_id).state == "23"


async def test_user_flow(hass: HomeAssistant, device: FakeDevice) -> None:
    """A reachable controller creates an entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": f"http://{HOST}/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == HOST


async def test_user_flow_cannot_connect(hass: HomeAssistant, device: FakeDevice) -> None:
    device.fail = True
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_changes_host(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The IP can be changed without losing the entities."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.0.2.20"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.0.2.20"
    assert entry.unique_id == "192.0.2.20"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator.host == "192.0.2.20"
    assert {
        e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    } == entity_ids


async def test_reconfigure_rejects_other_entry_host(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.30"}, unique_id="192.0.2.30", version=2).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": "192.0.2.30"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == HOST


async def test_services_need_loaded_entry(hass: HomeAssistant, device: FakeDevice) -> None:
    """Services are registered at startup and fail cleanly without a loaded entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": HOST}, unique_id=HOST, version=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "start_save_process")
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "start_save_process", {}, blocking=True)
    assert err.value.translation_key == "entry_not_loaded"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "start_save_process", {"entry_id": "missing"}, blocking=True
        )
    assert err.value.translation_key == "entry_not_found"


async def test_diagnostics_redact_host(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    coordinator.last_error = f"Cannot connect to host {HOST}:80"
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert HOST not in str(diag)
    assert diag["last_payload_excerpt"]["burn_params"]["aTemp"] == 350
