"""HTTP API helpers for the Kaschuetz (Euromatic) oven controller.

The controller exposes a single endpoint, ``POST /jsonRq``. The ``rqType``
field is a bit mask; several queries can be combined in one request.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BURN_PARAM_KEYS,
    RQ_QUERY_HISTORY,
    RQ_QUERY_MENU_PARAMS,
    RQ_QUERY_TEMP,
    RQ_READ_MENU_PARAMS,
    RQ_SAVE_PARAMS_PROCESS,
    RQ_SET_MENU_PARAMS,
)

_LOCKS: dict[str, asyncio.Lock] = {}


class KaschuetzApiError(Exception):
    """Raised when a Kaschuetz device request fails."""


def _lock_for(host: str) -> asyncio.Lock:
    """Return the request lock for a host; the controller handles one request at a time."""
    lock = _LOCKS.get(host)
    if lock is None:
        lock = _LOCKS[host] = asyncio.Lock()
    return lock


async def async_post_json(
    hass: HomeAssistant, host: str, body: dict[str, Any], timeout: int = 5
) -> dict[str, Any]:
    """Send request body to Kaschuetz and return JSON object."""
    url = f"http://{host}/jsonRq"
    session = async_get_clientsession(hass)
    try:
        async with _lock_for(host), session.post(
            url, json=body, timeout=ClientTimeout(total=timeout)
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
    except (ClientError, TimeoutError, ValueError) as err:
        raise KaschuetzApiError(f"Request to Kaschuetz failed: {err}") from err

    if not isinstance(payload, dict):
        raise KaschuetzApiError("Kaschuetz response is not a JSON object")
    return payload


async def async_fetch_main_data(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Fetch status, burn history and menu parameters in one request.

    Falls back to status + parameters and then status only.
    """
    full = RQ_QUERY_TEMP | RQ_QUERY_HISTORY | RQ_QUERY_MENU_PARAMS
    last_err: KaschuetzApiError | None = None
    for rq_type in (full, RQ_QUERY_TEMP | RQ_QUERY_MENU_PARAMS, RQ_QUERY_TEMP):
        try:
            return await async_post_json(hass, host, {"rqType": rq_type})
        except KaschuetzApiError as err:
            last_err = err
    assert last_err is not None
    raise last_err


async def async_fetch_params(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Fetch current menu parameters (spr, aTemp, schW, regW, regP)."""
    return await async_post_json(hass, host, {"rqType": RQ_QUERY_MENU_PARAMS})


async def async_save_process(
    hass: HomeAssistant, host: str, active: bool
) -> dict[str, Any]:
    """Start/keep alive (active=True) or cancel (active=False) the save process.

    The response carries ``saveParamsState`` (1 wrong state, 2 open door,
    3 keep door open, 4 close door, 10 ready to save).
    """
    return await async_post_json(
        hass,
        host,
        {"rqType": RQ_SAVE_PARAMS_PROCESS, "saveParamsActive": active},
    )


async def async_set_menu_params(
    hass: HomeAssistant,
    host: str,
    params: dict[str, int],
    spr: int,
    close_air_shutter: bool,
) -> bool:
    """Write menu parameters once the save process reports "ready".

    Mirrors the web UI: all parameters plus language and the air shutter flag
    are sent together with ending the save process. Returns whether the
    device confirmed the write.
    """
    body: dict[str, Any] = {
        "rqType": RQ_SET_MENU_PARAMS | RQ_SAVE_PARAMS_PROCESS,
        "saveParamsActive": False,
        "spr": int(spr),
        **{key: int(params[key]) for key in BURN_PARAM_KEYS},
        "closeAirShutter": bool(close_air_shutter),
    }
    response = await async_post_json(hass, host, body)
    return response.get("setMenuParamsResult") == 1


async def async_read_menu_params(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Ask the controller to re-read its stored menu parameters."""
    return await async_post_json(hass, host, {"rqType": RQ_READ_MENU_PARAMS})
