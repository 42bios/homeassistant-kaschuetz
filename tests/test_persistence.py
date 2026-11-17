"""Tests for persisting the learned optimizer data while Home Assistant runs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .fake_device import FakeDevice


async def _setup(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.coordinator


async def test_full_buffer_is_still_persisted(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """A full sample buffer keeps its length; new burn samples must still be saved."""
    coordinator = await _setup(hass, entry)
    optimizer = coordinator.optimizer
    device.state, device.temp = 9, 300
    while optimizer.sample_count() < optimizer._samples.maxlen:
        optimizer.add_sample({"state": 9, "Temp": 300})

    with patch("custom_components.kaschuetz.async_save_optimizer", AsyncMock()) as save:
        for _ in range(60):
            await coordinator.async_refresh()
    assert save.await_count >= 2


async def test_finished_burn_is_persisted(
    hass: HomeAssistant, entry: MockConfigEntry, device: FakeDevice
) -> None:
    """The end of a burn is saved right away, not only after a number of samples."""
    coordinator = await _setup(hass, entry)
    with patch("custom_components.kaschuetz.async_save_optimizer", AsyncMock()) as save:
        device.state, device.temp = 9, 300
        for _ in range(5):
            await coordinator.async_refresh()
        assert save.await_count == 0
        device.state, device.temp = 10, 120
        await coordinator.async_refresh()
        assert save.await_count == 1
        # Idle polls add nothing and do not write.
        for _ in range(5):
            await coordinator.async_refresh()
        assert save.await_count == 1
