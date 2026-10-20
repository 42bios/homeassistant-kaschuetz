"""Helpers for Kaschuetz menu parameter values."""

from __future__ import annotations

from typing import Any

from .const import BURN_PARAM_KEYS, BURN_PARAM_LIMITS, DEVICE_PARAM_UNKNOWN


def parse_param(value: Any) -> int | None:
    """Return a device value, or None if missing or not yet known (-1)."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return None if parsed == DEVICE_PARAM_UNKNOWN else parsed


def parse_burn_params(data: dict[str, Any] | None) -> dict[str, int] | None:
    """Return all four burn parameters from a payload, or None if incomplete."""
    params: dict[str, int] = {}
    for key in BURN_PARAM_KEYS:
        value = parse_param((data or {}).get(key))
        if value is None:
            return None
        params[key] = value
    return params


def snap_param(key: str, value: float) -> int:
    """Clamp a burn parameter to the device range and round it to the device step."""
    min_value, max_value, step = BURN_PARAM_LIMITS[key]
    snapped = min_value + round((float(value) - min_value) / step) * step
    return int(max(min_value, min(max_value, snapped)))
