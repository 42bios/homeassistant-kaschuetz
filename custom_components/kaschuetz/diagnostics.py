"""Diagnostics support for Kaschuetz integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_HOST
from .models import KaschuetzConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KaschuetzConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    optimizer = entry.runtime_data.optimizer
    data = coordinator.data or {}
    host = entry.data.get(CONF_HOST, "")
    last_error = coordinator.last_error
    if last_error and host:
        last_error = last_error.replace(host, REDACTED)

    return {
        "entry_id": entry.entry_id,
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_payload_excerpt": {
            "state": data.get("state"),
            "temp": data.get("Temp"),
            "klappe": data.get("Klappe"),
            "com_error": data.get("ComError"),
            "error_state": data.get("errorState"),
            "time_s": data.get("Time_s"),
            "spr": data.get("spr"),
            "burn_params": coordinator.device_burn_params(),
        },
        "coordinator": {
            "connection_quality": coordinator.connection_quality,
            "consecutive_failures": coordinator.consecutive_failures,
            "successful_polls": coordinator.successful_polls,
            "failed_polls": coordinator.failed_polls,
            "last_error": last_error,
        },
        "save_process": {
            "status": coordinator.save_status,
            "pending_params": dict(coordinator.pending_params),
            "close_air_shutter": coordinator.close_air_shutter,
            "last_result": coordinator.save_last_result,
        },
        "optimizer": {
            "sample_count": optimizer.sample_count(),
            "latest_suggestion": coordinator.suggestion(dict(entry.options)),
        },
    }
