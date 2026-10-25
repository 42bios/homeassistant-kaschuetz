"""Services of the Kaschuetz integration."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    BURN_PARAM_KEYS,
    CONF_EXPERIMENTAL_AUTO_OPTIMIZE,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_ORDER,
    DOMAIN,
    HISTORY_SAMPLE_STEP_SECONDS,
    SERVICE_APPLY_OPTIMIZATION,
    SERVICE_CALCULATE_OPTIMIZATION,
    SERVICE_CANCEL_SAVE_PROCESS,
    SERVICE_DISCARD_PENDING,
    SERVICE_EXPORT_BURN_HISTORY,
    SERVICE_EXPORT_BURN_HISTORY_FILE,
    SERVICE_OPTIMIZE_AND_APPLY,
    SERVICE_PREVIEW_ONLY,
    SERVICE_RESET_OPTIMIZATION,
    SERVICE_START_SAVE_PROCESS,
)
from .coordinator import KaschuetzDataCoordinator
from .models import KaschuetzConfigEntry
from .storage import async_save_optimizer

_LOGGER = logging.getLogger(__name__)

ENTRY_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})
APPLY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("start_save", default=False): cv.boolean,
        # Deprecated alias of start_save (parameters are never written directly).
        vol.Optional("write_to_device"): cv.boolean,
        vol.Optional("min_confidence", default=CONFIDENCE_LOW): vol.In(
            [CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH]
        ),
    }
)
EXPORT_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("include_arrays", default=True): cv.boolean,
        vol.Optional("max_points", default=240): vol.All(vol.Coerce(int), vol.Range(min=20, max=1000)),
    }
)
EXPORT_HISTORY_FILE_SCHEMA = EXPORT_HISTORY_SCHEMA.extend(
    {vol.Optional("format", default="json"): vol.In(["json", "csv"])}
)


def _loaded_entries(hass: HomeAssistant, call: ServiceCall) -> list[KaschuetzConfigEntry]:
    """Return the loaded entries a service call addresses."""
    entry_id = call.data.get("entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        entries = [entry]
    else:
        entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [entry for entry in entries if entry.state is ConfigEntryState.LOADED]
    if not loaded:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
    return loaded


def _notify(hass: HomeAssistant, lines: list[str], title: str, notification_id: str) -> None:
    message = "\n\n".join(lines)
    _LOGGER.info("%s:\n%s", title, message)
    persistent_notification.async_create(hass, message, title=title, notification_id=notification_id)


def _suggestion_preview_text(
    entry: KaschuetzConfigEntry, suggestion: dict[str, Any], current: dict[str, int] | None
) -> str:
    proposed = {key: suggestion.get(key) for key in BURN_PARAM_KEYS}
    if current is None:
        delta: dict[str, int | None] | str = "unknown (device did not report current parameters)"
    else:
        delta = {
            key: None if proposed[key] is None else proposed[key] - current[key]
            for key in BURN_PARAM_KEYS
        }

    return (
        f"Entry: {entry.entry_id}\n"
        "Preview only: nothing is staged or written.\n"
        f"Samples: {suggestion.get('samples_used')}, Cycles: {suggestion.get('cycles_used')}\n"
        f"Confidence: {suggestion.get('confidence')}\n"
        f"Current (device): {current if current is not None else 'unknown'}\n"
        f"Proposed: {proposed}\n"
        f"Delta: {delta}\n"
        f"Stats: {suggestion.get('stats')}\n"
        f"Cycle stats: {suggestion.get('cycle_stats')}\n"
        f"KPIs: {suggestion.get('kpis')}\n"
        f"Safety: {suggestion.get('safety')}\n"
        f"Adjustments: {suggestion.get('adjustments')}\n"
        f"Profile: {suggestion.get('optimizer_profile')}\n"
        f"Note: {suggestion.get('note', '-')}"
    )


def _write_history_export(
    path: Path, snapshot: dict[str, Any], export_format: str, include_arrays: bool
) -> None:
    """Write a burn history snapshot to disk (blocking, run in executor)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "csv":
        temp_arr = snapshot.get("TempArr", []) if include_arrays else []
        flap_arr = snapshot.get("KlappeArr", []) if include_arrays else []
        step_s = int(snapshot.get("sample_step_s", HISTORY_SAMPLE_STEP_SECONDS))
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "time_offset_s", "temp_c", "flap"])
            for idx, temp in enumerate(temp_arr):
                flap = flap_arr[idx] if idx < len(flap_arr) else None
                writer.writerow([idx, idx * step_s, temp, flap])
    else:
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def _can_apply(suggestion: dict[str, Any], min_confidence: str) -> bool:
    value = CONFIDENCE_ORDER.get(str(suggestion.get("confidence", CONFIDENCE_LOW)), 1)
    required = CONFIDENCE_ORDER.get(min_confidence, 1)
    return value >= required


async def _apply_suggestion_to_entry(
    entry: KaschuetzConfigEntry,
    coordinator: KaschuetzDataCoordinator,
    suggestion: dict[str, Any],
    start_save: bool,
) -> str:
    """Stage the suggested parameters and optionally start the save process."""
    staged = coordinator.stage_params(suggestion)
    if not staged:
        return f"Entry {entry.entry_id}: nothing to stage (no suggested values)"
    message = f"Entry {entry.entry_id}: staged {staged}"
    if start_save:
        try:
            await coordinator.async_start_save()
        except HomeAssistantError as err:
            return f"{message}; save process not started ({err})"
        message += "; save process started - open and close the filling door at the oven"
    return message


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""

    def _previews(call: ServiceCall) -> list[str]:
        previews = []
        for entry in _loaded_entries(hass, call):
            coordinator = entry.runtime_data.coordinator
            suggestion = coordinator.suggestion(dict(entry.options))
            previews.append(
                _suggestion_preview_text(entry, suggestion, coordinator.device_burn_params())
            )
        return previews

    async def _handle_calculate_optimization(call: ServiceCall) -> None:
        _notify(hass, _previews(call), "Kaschuetz Optimization Suggestion", "kaschuetz_optimization")

    async def _handle_preview_only(call: ServiceCall) -> None:
        _notify(hass, _previews(call), "Kaschuetz Preview Only", "kaschuetz_preview_only")

    async def _handle_apply_optimization(call: ServiceCall) -> None:
        start_save = bool(call.data.get("start_save", call.data.get("write_to_device", False)))
        min_confidence = str(call.data.get("min_confidence", CONFIDENCE_LOW))
        updates: list[str] = []

        for entry in _loaded_entries(hass, call):
            if not entry.options.get(CONF_EXPERIMENTAL_AUTO_OPTIMIZE, False):
                updates.append(
                    f"Entry {entry.entry_id}: skipped (experimental_auto_optimize is disabled)"
                )
                continue
            coordinator = entry.runtime_data.coordinator
            if coordinator.device_burn_params() is None:
                updates.append(
                    f"Entry {entry.entry_id}: skipped (device did not report current parameters)"
                )
                continue
            suggestion = coordinator.suggestion(dict(entry.options))
            if not _can_apply(suggestion, min_confidence):
                updates.append(
                    f"Entry {entry.entry_id}: skipped (confidence={suggestion.get('confidence')} < {min_confidence})"
                )
                continue
            updates.append(
                await _apply_suggestion_to_entry(entry, coordinator, suggestion, start_save)
            )

        _notify(hass, updates, "Kaschuetz Optimization Applied", "kaschuetz_apply_optimization")

    async def _handle_export_burn_history(call: ServiceCall) -> None:
        include_arrays = bool(call.data.get("include_arrays", True))
        max_points = int(call.data.get("max_points", 240))
        summaries: list[str] = []

        for entry in _loaded_entries(hass, call):
            snapshot = entry.runtime_data.optimizer.history_snapshot(
                max_points=max_points, include_arrays=include_arrays
            )
            hass.bus.async_fire(
                f"{DOMAIN}_burn_history_export",
                {"entry_id": entry.entry_id, **snapshot},
            )
            summaries.append(
                f"Entry {entry.entry_id}: exported points={snapshot.get('points')} "
                f"time_s={snapshot.get('time_s')} kpis={snapshot.get('kpis')}"
            )

        _notify(hass, summaries, "Kaschuetz Burn History Export", "kaschuetz_export_burn_history")

    async def _handle_export_burn_history_file(call: ServiceCall) -> None:
        include_arrays = bool(call.data.get("include_arrays", True))
        max_points = int(call.data.get("max_points", 240))
        export_format = str(call.data.get("format", "json")).lower()
        export_dir = Path(hass.config.path("kaschuetz_exports"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lines: list[str] = []

        for entry in _loaded_entries(hass, call):
            snapshot = entry.runtime_data.optimizer.history_snapshot(
                max_points=max_points, include_arrays=include_arrays
            )
            suffix = "csv" if export_format == "csv" else "json"
            path = export_dir / f"{DOMAIN}_{entry.entry_id}_{timestamp}.{suffix}"
            try:
                await hass.async_add_executor_job(
                    _write_history_export, path, snapshot, export_format, include_arrays
                )
            except OSError as err:
                lines.append(f"Entry {entry.entry_id}: export failed ({err})")
                continue
            lines.append(f"Entry {entry.entry_id}: exported to {path}")

        _notify(hass, lines, "Kaschuetz Burn History File Export", "kaschuetz_export_burn_history_file")

    async def _handle_reset_optimization(call: ServiceCall) -> None:
        lines: list[str] = []
        for entry in _loaded_entries(hass, call):
            optimizer = entry.runtime_data.optimizer
            before = optimizer.sample_count()
            optimizer.clear()
            await async_save_optimizer(hass, entry.entry_id, optimizer)
            lines.append(f"Entry {entry.entry_id}: reset {before} samples")
        _notify(hass, lines, "Kaschuetz Optimization Reset", "kaschuetz_reset_optimization")

    async def _handle_start_save_process(call: ServiceCall) -> None:
        for entry in _loaded_entries(hass, call):
            await entry.runtime_data.coordinator.async_start_save()

    async def _handle_cancel_save_process(call: ServiceCall) -> None:
        for entry in _loaded_entries(hass, call):
            await entry.runtime_data.coordinator.async_cancel_save()

    async def _handle_discard_pending(call: ServiceCall) -> None:
        for entry in _loaded_entries(hass, call):
            coordinator = entry.runtime_data.coordinator
            if coordinator.save_in_progress:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="save_in_progress"
                )
            coordinator.discard_pending()

    for service, handler, schema in (
        (SERVICE_CALCULATE_OPTIMIZATION, _handle_calculate_optimization, ENTRY_SCHEMA),
        (SERVICE_PREVIEW_ONLY, _handle_preview_only, ENTRY_SCHEMA),
        (SERVICE_APPLY_OPTIMIZATION, _handle_apply_optimization, APPLY_SCHEMA),
        (SERVICE_OPTIMIZE_AND_APPLY, _handle_apply_optimization, APPLY_SCHEMA),
        (SERVICE_EXPORT_BURN_HISTORY, _handle_export_burn_history, EXPORT_HISTORY_SCHEMA),
        (SERVICE_EXPORT_BURN_HISTORY_FILE, _handle_export_burn_history_file, EXPORT_HISTORY_FILE_SCHEMA),
        (SERVICE_RESET_OPTIMIZATION, _handle_reset_optimization, ENTRY_SCHEMA),
        (SERVICE_START_SAVE_PROCESS, _handle_start_save_process, ENTRY_SCHEMA),
        (SERVICE_CANCEL_SAVE_PROCESS, _handle_cancel_save_process, ENTRY_SCHEMA),
        (SERVICE_DISCARD_PENDING, _handle_discard_pending, ENTRY_SCHEMA),
    ):
        async_register_admin_service(hass, DOMAIN, service, handler, schema=schema)
