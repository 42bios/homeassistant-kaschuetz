"""Initialize the Kaschuetz integration."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store

from .const import (
    BURN_PARAM_KEYS,
    CONF_EXPERIMENTAL_AUTO_OPTIMIZE,
    CONF_HOST,
    CONF_SEASON_ENTITY,
    CONF_UPDATE_INTERVAL,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_ORDER,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    RUNTIME_COORDINATOR,
    RUNTIME_ENTRY_DATA,
    RUNTIME_OPTIMIZER,
    RUNTIME_SAVE_OPTIMIZER,
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
from .optimizer import BurnOptimizer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number", "select", "button", "switch"]
SERVICES = (
    SERVICE_CALCULATE_OPTIMIZATION,
    SERVICE_PREVIEW_ONLY,
    SERVICE_APPLY_OPTIMIZATION,
    SERVICE_EXPORT_BURN_HISTORY,
    SERVICE_EXPORT_BURN_HISTORY_FILE,
    SERVICE_OPTIMIZE_AND_APPLY,
    SERVICE_RESET_OPTIMIZATION,
    SERVICE_START_SAVE_PROCESS,
    SERVICE_CANCEL_SAVE_PROCESS,
    SERVICE_DISCARD_PENDING,
)
# Entities removed in 1.5.0; their values were not backed by the device protocol.
OBSOLETE_ENTITY_KEYS = ("com_error_text", "spr_code")
STORAGE_VERSION = 1

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
EXPORT_HISTORY_FILE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("include_arrays", default=True): cv.boolean,
        vol.Optional("max_points", default=240): vol.All(vol.Coerce(int), vol.Range(min=20, max=1000)),
        vol.Optional("format", default="json"): vol.In(["json", "csv"]),
    }
)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload only when the poll interval changed; other options apply live."""
    runtime = hass.data[DOMAIN].get(entry.entry_id)
    interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    if runtime is None or runtime.get(CONF_UPDATE_INTERVAL) != interval:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    runtime[RUNTIME_COORDINATOR].async_update_listeners()


def _storage_key(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_optimizer"


async def _save_optimizer(hass: HomeAssistant, entry_id: str, optimizer: BurnOptimizer) -> None:
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, _storage_key(entry_id))
    await store.async_save(optimizer.to_dict())


async def _load_optimizer(hass: HomeAssistant, entry_id: str) -> BurnOptimizer:
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, _storage_key(entry_id))
    data = await store.async_load()
    return BurnOptimizer.from_dict(data)


def _find_entries(hass: HomeAssistant, entry_id: str | None) -> list[ConfigEntry]:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entry_id:
        return entries
    return [entry for entry in entries if entry.entry_id == entry_id]


def _suggestion_preview_text(
    entry: ConfigEntry, suggestion: dict[str, Any], current: dict[str, int] | None
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
        step_s = int(snapshot.get("sample_step_s", 8))
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


def _experimental_auto_optimize_enabled(entry: ConfigEntry) -> bool:
    """Return whether experimental auto optimization is enabled for this entry."""
    return bool(entry.options.get(CONF_EXPERIMENTAL_AUTO_OPTIMIZE, False))


async def _apply_suggestion_to_entry(
    entry: ConfigEntry,
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


async def _async_setup_services(hass: HomeAssistant) -> None:
    async def _build_preview_messages(requested_entry_id: str | None) -> list[str]:
        messages: list[str] = []
        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue
            coordinator: KaschuetzDataCoordinator = runtime[RUNTIME_COORDINATOR]
            suggestion = coordinator.suggestion(dict(entry.options))
            messages.append(
                _suggestion_preview_text(entry, suggestion, coordinator.device_burn_params())
            )
        if not messages:
            messages.append("No matching Kaschuetz config entry found.")
        return messages

    async def _handle_calculate_optimization(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        suggestions = await _build_preview_messages(requested_entry_id)
        message = "\n\n".join(suggestions)
        _LOGGER.info("Kaschuetz optimization result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Optimization Suggestion",
            notification_id="kaschuetz_optimization",
        )

    async def _handle_preview_only(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        previews = await _build_preview_messages(requested_entry_id)
        message = "\n\n".join(previews)
        _LOGGER.info("Kaschuetz preview-only result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Preview Only",
            notification_id="kaschuetz_preview_only",
        )

    async def _handle_apply_optimization(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        start_save = bool(call.data.get("start_save", call.data.get("write_to_device", False)))
        min_confidence = str(call.data.get("min_confidence", CONFIDENCE_LOW))
        updates: list[str] = []

        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue
            if not _experimental_auto_optimize_enabled(entry):
                updates.append(
                    f"Entry {entry.entry_id}: skipped (experimental_auto_optimize is disabled)"
                )
                continue

            coordinator: KaschuetzDataCoordinator = runtime[RUNTIME_COORDINATOR]
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

        if not updates:
            updates.append("No matching Kaschuetz config entry found.")

        message = "\n".join(updates)
        _LOGGER.info("Kaschuetz apply optimization result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Optimization Applied",
            notification_id="kaschuetz_apply_optimization",
        )

    async def _handle_export_burn_history(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        include_arrays = bool(call.data.get("include_arrays", True))
        max_points = int(call.data.get("max_points", 240))
        summaries: list[str] = []

        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue

            optimizer: BurnOptimizer = runtime[RUNTIME_OPTIMIZER]
            snapshot = optimizer.history_snapshot(max_points=max_points, include_arrays=include_arrays)
            hass.bus.async_fire(
                f"{DOMAIN}_burn_history_export",
                {"entry_id": entry.entry_id, **snapshot},
            )
            summaries.append(
                f"Entry {entry.entry_id}: exported points={snapshot.get('points')} "
                f"time_s={snapshot.get('time_s')} kpis={snapshot.get('kpis')}"
            )

        if not summaries:
            summaries.append("No matching Kaschuetz config entry found.")

        message = "\n".join(summaries)
        _LOGGER.info("Kaschuetz burn history export result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Burn History Export",
            notification_id="kaschuetz_export_burn_history",
        )

    async def _handle_export_burn_history_file(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        include_arrays = bool(call.data.get("include_arrays", True))
        max_points = int(call.data.get("max_points", 240))
        export_format = str(call.data.get("format", "json")).lower()
        export_dir = Path(hass.config.path("kaschuetz_exports"))
        lines: list[str] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue
            optimizer: BurnOptimizer = runtime[RUNTIME_OPTIMIZER]
            snapshot = optimizer.history_snapshot(max_points=max_points, include_arrays=include_arrays)

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

        if not lines:
            lines.append("No matching Kaschuetz config entry found.")

        message = "\n".join(lines)
        _LOGGER.info("Kaschuetz burn history file export result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Burn History File Export",
            notification_id="kaschuetz_export_burn_history_file",
        )

    def _coordinators(call: ServiceCall) -> list[KaschuetzDataCoordinator]:
        coordinators = [
            hass.data[DOMAIN][entry.entry_id][RUNTIME_COORDINATOR]
            for entry in _find_entries(hass, call.data.get("entry_id"))
            if entry.entry_id in hass.data[DOMAIN]
        ]
        if not coordinators:
            raise HomeAssistantError("No matching Kaschuetz config entry found")
        return coordinators

    async def _handle_start_save_process(call: ServiceCall) -> None:
        for coordinator in _coordinators(call):
            await coordinator.async_start_save()

    async def _handle_cancel_save_process(call: ServiceCall) -> None:
        for coordinator in _coordinators(call):
            await coordinator.async_cancel_save()

    async def _handle_discard_pending(call: ServiceCall) -> None:
        for coordinator in _coordinators(call):
            if coordinator.save_in_progress:
                raise HomeAssistantError("Cannot discard changes while a save is running")
            coordinator.discard_pending()

    async def _handle_optimize_and_apply(call: ServiceCall) -> None:
        await _handle_apply_optimization(call)

    async def _handle_reset_optimization(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        lines: list[str] = []

        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue
            optimizer: BurnOptimizer = runtime[RUNTIME_OPTIMIZER]
            before = optimizer.sample_count()
            optimizer.clear()
            await _save_optimizer(hass, entry.entry_id, optimizer)
            lines.append(f"Entry {entry.entry_id}: reset {before} samples")

        if not lines:
            lines.append("No matching Kaschuetz config entry found.")

        message = "\n".join(lines)
        _LOGGER.info("Kaschuetz reset optimization result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Optimization Reset",
            notification_id="kaschuetz_reset_optimization",
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CALCULATE_OPTIMIZATION,
        _handle_calculate_optimization,
        schema=ENTRY_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_PREVIEW_ONLY,
        _handle_preview_only,
        schema=ENTRY_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_APPLY_OPTIMIZATION,
        _handle_apply_optimization,
        schema=APPLY_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EXPORT_BURN_HISTORY,
        _handle_export_burn_history,
        schema=EXPORT_HISTORY_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EXPORT_BURN_HISTORY_FILE,
        _handle_export_burn_history_file,
        schema=EXPORT_HISTORY_FILE_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_OPTIMIZE_AND_APPLY,
        _handle_optimize_and_apply,
        schema=APPLY_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_RESET_OPTIMIZATION,
        _handle_reset_optimization,
        schema=ENTRY_SCHEMA,
    )
    for service, handler in (
        (SERVICE_START_SAVE_PROCESS, _handle_start_save_process),
        (SERVICE_CANCEL_SAVE_PROCESS, _handle_cancel_save_process),
        (SERVICE_DISCARD_PENDING, _handle_discard_pending),
    ):
        async_register_admin_service(hass, DOMAIN, service, handler, schema=ENTRY_SCHEMA)


def _remove_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities of earlier versions that no longer exist."""
    registry = er.async_get(hass)
    for key in OBSOLETE_ENTITY_KEYS:
        unique_id = f"kaschuetz_{key}_{entry.data[CONF_HOST]}"
        if entity_id := registry.async_get_entity_id("sensor", DOMAIN, unique_id):
            registry.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kaschuetz from a config entry."""
    _LOGGER.debug("Setting up Kaschuetz entry: %s", entry.as_dict())

    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("service_registered"):
        await _async_setup_services(hass)
        hass.data[DOMAIN]["service_registered"] = True

    optimizer = await _load_optimizer(hass, entry.entry_id)

    async def _persist_optimizer() -> None:
        await _save_optimizer(hass, entry.entry_id, optimizer)

    _remove_obsolete_entities(hass, entry)

    poll_interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    coordinator = KaschuetzDataCoordinator(
        hass=hass,
        entry=entry,
        host=entry.data[CONF_HOST],
        season_entity=entry.data.get(CONF_SEASON_ENTITY),
        poll_interval=poll_interval,
        optimizer=optimizer,
        persist_callback=_persist_optimizer,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        RUNTIME_ENTRY_DATA: dict(entry.data),
        RUNTIME_OPTIMIZER: optimizer,
        RUNTIME_SAVE_OPTIMIZER: _persist_optimizer,
        RUNTIME_COORDINATOR: coordinator,
        CONF_UPDATE_INTERVAL: poll_interval,
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Kaschuetz config entry."""
    _LOGGER.debug("Unloading Kaschuetz entry: %s", entry.as_dict())
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime and RUNTIME_OPTIMIZER in runtime:
            await _save_optimizer(hass, entry.entry_id, runtime[RUNTIME_OPTIMIZER])

        other_loaded = [
            other
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
        ]
        if not other_loaded:
            for service in SERVICES:
                hass.services.async_remove(DOMAIN, service)
            hass.data[DOMAIN]["service_registered"] = False
    return unload_ok
