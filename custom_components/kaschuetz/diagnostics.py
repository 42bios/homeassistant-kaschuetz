"""Diagnostics support for Kaschuetz integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, DOMAIN, RUNTIME_COORDINATOR, RUNTIME_OPTIMIZER


def _redact_host(host: str) -> str:
    parts = host.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3] + ["x"])
    return "redacted"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = runtime.get(RUNTIME_COORDINATOR)
    optimizer = runtime.get(RUNTIME_OPTIMIZER)

    data = coordinator.data if coordinator else {}
    com_error = data.get("ComError") if isinstance(data, dict) else None

    return {
        "entry_id": entry.entry_id,
        "host": _redact_host(str(entry.data.get(CONF_HOST, ""))),
        "options": dict(entry.options),
        "last_payload_excerpt": {
            "state": data.get("state") if isinstance(data, dict) else None,
            "temp": data.get("Temp") if isinstance(data, dict) else None,
            "klappe": data.get("Klappe") if isinstance(data, dict) else None,
            "com_error": com_error,
        },
        "coordinator": {
            "available": bool(coordinator),
            "connection_quality": getattr(coordinator, "connection_quality", None),
            "consecutive_failures": getattr(coordinator, "consecutive_failures", None),
            "successful_polls": getattr(coordinator, "successful_polls", None),
            "failed_polls": getattr(coordinator, "failed_polls", None),
            "last_error": getattr(coordinator, "last_error", None),
        },
        "optimizer": {
            "available": bool(optimizer),
            "sample_count": optimizer.sample_count() if optimizer else 0,
            "latest_suggestion": optimizer.calculate(dict(entry.options)) if optimizer else None,
        },
    }
