"""Pytest setup for isolated optimizer unit tests.

This prevents importing the integration package __init__.py (which depends on
Home Assistant runtime modules) when loading submodules like optimizer.py.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


def pytest_sessionstart() -> None:
    root = Path(__file__).resolve().parents[1]
    custom_components_dir = root / "custom_components"
    kaschuetz_dir = custom_components_dir / "kaschuetz"

    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(custom_components_dir)]  # type: ignore[attr-defined]
    sys.modules.setdefault("custom_components", custom_components)

    kaschuetz = types.ModuleType("custom_components.kaschuetz")
    kaschuetz.__path__ = [str(kaschuetz_dir)]  # type: ignore[attr-defined]
    sys.modules.setdefault("custom_components.kaschuetz", kaschuetz)
