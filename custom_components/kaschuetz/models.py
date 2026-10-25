"""Runtime data of a Kaschuetz config entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .coordinator import KaschuetzDataCoordinator
from .optimizer import BurnOptimizer


@dataclass
class KaschuetzRuntimeData:
    """Objects shared by the platforms and services of one controller."""

    coordinator: KaschuetzDataCoordinator
    optimizer: BurnOptimizer
    poll_interval: int


type KaschuetzConfigEntry = ConfigEntry[KaschuetzRuntimeData]
