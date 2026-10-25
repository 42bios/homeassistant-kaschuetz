"""Persistence of the learned optimizer data."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .optimizer import BurnOptimizer

STORAGE_VERSION = 1


def _store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_optimizer")


async def async_load_optimizer(hass: HomeAssistant, entry_id: str) -> BurnOptimizer:
    """Load the optimizer of a config entry."""
    return BurnOptimizer.from_dict(await _store(hass, entry_id).async_load())


async def async_save_optimizer(
    hass: HomeAssistant, entry_id: str, optimizer: BurnOptimizer
) -> None:
    """Persist the optimizer of a config entry."""
    await _store(hass, entry_id).async_save(optimizer.to_dict())


async def async_remove_optimizer(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the stored optimizer data of a removed config entry."""
    await _store(hass, entry_id).async_remove()
