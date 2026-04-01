"""HTTP API helpers for the Kaschuetz integration."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class KaschuetzApiError(Exception):
    """Raised when a Kaschuetz device request fails."""


async def async_post_json(
    hass: HomeAssistant, host: str, body: dict[str, Any], timeout: int = 5
) -> dict[str, Any]:
    """Send request body to Kaschuetz and return JSON object."""
    url = f"http://{host}/jsonRq"
    session = async_get_clientsession(hass)
    try:
        async with session.post(url, json=body, timeout=timeout) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
    except (ClientError, TimeoutError, ValueError) as err:
        raise KaschuetzApiError(f"Request to Kaschuetz failed: {err}") from err

    if not isinstance(payload, dict):
        raise KaschuetzApiError("Kaschuetz response is not a JSON object")
    return payload


async def async_fetch_main_data(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Fetch main status payload using rqType=1."""
    return await async_post_json(hass, host, {"rqType": 1})


async def async_fetch_params(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Fetch current burn parameters using rqType=4."""
    return await async_post_json(hass, host, {"rqType": 4})


async def async_send_abbrand_params(
    hass: HomeAssistant, host: str, params: dict[str, int]
) -> None:
    """Send burn parameters to device using rqType=8."""
    if any(value < 0 for value in params.values()):
        raise KaschuetzApiError(f"Invalid negative parameter in payload: {params}")

    await async_post_json(
        hass,
        host,
        {
            "rqType": 8,
            "aTemp": params.get("aTemp"),
            "schW": params.get("schW"),
            "regW": params.get("regW"),
            "regP": params.get("regP"),
        },
    )
