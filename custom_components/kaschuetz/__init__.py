"""Initialize the Kaschuetz integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store

from .api import KaschuetzApiError, async_send_abbrand_params
from .const import (
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
    SERVICE_OPTIMIZE_AND_APPLY,
    SERVICE_RESET_OPTIMIZATION,
)
from .coordinator import KaschuetzDataCoordinator
from .optimizer import BurnOptimizer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number", "select", "button"]
STORAGE_VERSION = 1

ENTRY_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})
APPLY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("write_to_device", default=False): cv.boolean,
        vol.Optional("min_confidence", default=CONFIDENCE_LOW): vol.In(
            [CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH]
        ),
    }
)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


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


def _suggestion_to_text(entry_id: str, suggestion: dict[str, Any]) -> str:
    return (
        f"Entry: {entry_id}\n"
        f"Samples: {suggestion.get('samples_used')}\n"
        f"Burn cycles: {suggestion.get('cycles_used')}\n"
        f"Confidence: {suggestion.get('confidence')}\n"
        f"aTemp={suggestion.get('aTemp')}, "
        f"schW={suggestion.get('schW')}, "
        f"regW={suggestion.get('regW')}, "
        f"regP={suggestion.get('regP')}\n"
        f"Stats: {suggestion.get('stats')}\n"
        f"Cycle stats: {suggestion.get('cycle_stats')}\n"
        f"Note: {suggestion.get('note', '-')}"
    )


def _can_apply(suggestion: dict[str, Any], min_confidence: str) -> bool:
    value = CONFIDENCE_ORDER.get(str(suggestion.get("confidence", CONFIDENCE_LOW)), 1)
    required = CONFIDENCE_ORDER.get(min_confidence, 1)
    return value >= required


async def _apply_suggestion_to_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    suggestion: dict[str, Any],
    write_to_device: bool,
) -> str:
    applied = {
        "aTemp": int(suggestion["aTemp"]),
        "schW": int(suggestion["schW"]),
        "regW": int(suggestion["regW"]),
        "regP": int(suggestion["regP"]),
    }

    if write_to_device:
        await async_send_abbrand_params(hass, entry.data[CONF_HOST], applied)

    new_options = {**dict(entry.options), **applied}
    hass.config_entries.async_update_entry(entry, options=new_options)
    return f"Entry {entry.entry_id}: applied {applied} (write_to_device={write_to_device})"


async def _async_setup_services(hass: HomeAssistant) -> None:
    async def _handle_calculate_optimization(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        suggestions: list[str] = []

        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue
            optimizer: BurnOptimizer = runtime[RUNTIME_OPTIMIZER]
            suggestion = optimizer.calculate(dict(entry.options))
            suggestions.append(_suggestion_to_text(entry.entry_id, suggestion))

        if not suggestions:
            suggestions.append("No matching Kaschuetz config entry found.")

        message = "\n\n".join(suggestions)
        _LOGGER.info("Kaschuetz optimization result:\n%s", message)
        persistent_notification.async_create(
            hass,
            message,
            title="Kaschuetz Optimization Suggestion",
            notification_id="kaschuetz_optimization",
        )

    async def _handle_apply_optimization(call: ServiceCall) -> None:
        requested_entry_id = call.data.get("entry_id")
        write_to_device = bool(call.data.get("write_to_device", False))
        min_confidence = str(call.data.get("min_confidence", CONFIDENCE_LOW))
        updates: list[str] = []

        for entry in _find_entries(hass, requested_entry_id):
            runtime = hass.data[DOMAIN].get(entry.entry_id)
            if not runtime:
                continue

            optimizer: BurnOptimizer = runtime[RUNTIME_OPTIMIZER]
            suggestion = optimizer.calculate(dict(entry.options))
            if not _can_apply(suggestion, min_confidence):
                updates.append(
                    f"Entry {entry.entry_id}: skipped (confidence={suggestion.get('confidence')} < {min_confidence})"
                )
                continue

            try:
                updates.append(
                    await _apply_suggestion_to_entry(hass, entry, suggestion, write_to_device)
                )
            except KaschuetzApiError as err:
                updates.append(f"Entry {entry.entry_id}: device write failed ({err})")

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
        SERVICE_APPLY_OPTIMIZATION,
        _handle_apply_optimization,
        schema=APPLY_SCHEMA,
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

    coordinator = KaschuetzDataCoordinator(
        hass=hass,
        host=entry.data[CONF_HOST],
        season_entity=entry.data.get(CONF_SEASON_ENTITY),
        poll_interval=int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
        optimizer=optimizer,
        persist_callback=_persist_optimizer,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        RUNTIME_ENTRY_DATA: dict(entry.data),
        RUNTIME_OPTIMIZER: optimizer,
        RUNTIME_SAVE_OPTIMIZER: _persist_optimizer,
        RUNTIME_COORDINATOR: coordinator,
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

        loaded_entries = hass.config_entries.async_entries(DOMAIN)
        if not loaded_entries:
            hass.services.async_remove(DOMAIN, SERVICE_CALCULATE_OPTIMIZATION)
            hass.services.async_remove(DOMAIN, SERVICE_APPLY_OPTIMIZATION)
            hass.services.async_remove(DOMAIN, SERVICE_OPTIMIZE_AND_APPLY)
            hass.services.async_remove(DOMAIN, SERVICE_RESET_OPTIMIZATION)
            hass.data[DOMAIN]["service_registered"] = False
    return unload_ok
