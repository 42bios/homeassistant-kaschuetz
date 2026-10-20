"""Fixtures for Kaschuetz tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kaschuetz.api import KaschuetzApiError
from custom_components.kaschuetz.const import CONF_HOST, DOMAIN

from .fake_device import FakeDevice


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration."""
    return


@pytest.fixture
def device() -> Generator[FakeDevice]:
    """Patch the HTTP layer with the simulated controller."""
    fake = FakeDevice()

    async def _post(hass, host, body, timeout=5):
        try:
            return fake.handle(body)
        except ConnectionError as err:
            raise KaschuetzApiError(str(err)) from err

    with (
        patch("custom_components.kaschuetz.api.async_post_json", side_effect=_post),
        patch("custom_components.kaschuetz.config_flow.async_post_json", side_effect=_post),
        patch("custom_components.kaschuetz.coordinator.SAVE_PROCESS_POLL_SECONDS", 0),
        patch("custom_components.kaschuetz.coordinator.SAVE_RELOAD_DELAY_SECONDS", 0),
    ):
        yield fake


@pytest.fixture
def entry() -> MockConfigEntry:
    """Return a config entry for the simulated controller."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kaschuetz Oven",
        data={CONF_HOST: "192.0.2.10"},
        unique_id="192.0.2.10",
    )
