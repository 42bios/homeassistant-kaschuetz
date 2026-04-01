"""Burn optimization helper for Kaschuetz integration."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from .const import (
    DEFAULT_A_TEMP,
    DEFAULT_REGP,
    DEFAULT_REGW,
    DEFAULT_SCHW,
    OPTIMIZER_MODE_AGGRESSIVE,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODE_CONSERVATIVE,
)

ACTIVE_STATES = {3, 4, 9}


@dataclass(slots=True)
class BurnSample:
    """Single normalized sample from the oven payload."""

    temp: float | None
    flap: int | None
    state: int | None
    com_error: int | None


class BurnOptimizer:
    """Collect burn history and create parameter suggestions."""

    def __init__(self, max_samples: int = 4000) -> None:
        self._samples: deque[BurnSample] = deque(maxlen=max_samples)

    def add_sample(self, payload: dict[str, Any]) -> None:
        """Add a sample from raw device payload."""
        self._samples.append(
            BurnSample(
                temp=self._to_float(payload.get("Temp")),
                flap=self._to_int(payload.get("Klappe")),
                state=self._to_int(payload.get("state")),
                com_error=self._to_int(payload.get("ComError")),
            )
        )

    def sample_count(self) -> int:
        """Return total number of collected samples."""
        return len(self._samples)

    def clear(self) -> None:
        """Remove all learned samples."""
        self._samples.clear()

    def calculate(self, current_options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Calculate optimized abbrand parameters from collected samples."""
        current_options = current_options or {}
        burn_samples = [s for s in self._samples if s.state in ACTIVE_STATES and s.temp is not None]
        cycles = self._extract_cycles()

        if len(burn_samples) < 30:
            return {
                "aTemp": self._default_from_options(current_options, "aTemp", DEFAULT_A_TEMP),
                "schW": self._default_from_options(current_options, "schW", DEFAULT_SCHW),
                "regW": self._default_from_options(current_options, "regW", DEFAULT_REGW),
                "regP": self._default_from_options(current_options, "regP", DEFAULT_REGP),
                "confidence": "low",
                "note": "Too few burn samples. Keep observing for better optimization.",
                "samples_used": len(burn_samples),
                "cycles_used": len(cycles),
            }

        temps = [s.temp for s in burn_samples if s.temp is not None]
        flaps = [s.flap for s in burn_samples if s.flap is not None]
        errors = [s for s in burn_samples if s.com_error not in (None, 0)]

        avg_temp = mean(temps)
        peak_temp = max(temps)
        temp_spread = pstdev(temps) if len(temps) > 1 else 0.0
        flap_closed_ratio = self._closed_ratio(flaps)
        error_ratio = len(errors) / len(burn_samples)
        mode = str(current_options.get("optimizer_mode", OPTIMIZER_MODE_BALANCED))

        if mode == OPTIMIZER_MODE_CONSERVATIVE:
            temp_factor = 0.80
            spread_factor = 22
            error_factor = 300
        elif mode == OPTIMIZER_MODE_AGGRESSIVE:
            temp_factor = 0.90
            spread_factor = 14
            error_factor = 180
        else:
            temp_factor = 0.85
            spread_factor = 18
            error_factor = 240

        # Heuristic baseline: can later be replaced by trained model predictions.
        a_temp = self._clamp_int(round(avg_temp * temp_factor), 120, 320)
        sch_w = self._clamp_int(round(220 + (1.0 - flap_closed_ratio) * 320), 120, 700)
        reg_w = self._clamp_int(round(450 + temp_spread * spread_factor), 200, 1200)
        reg_p = self._clamp_int(round(160 + error_ratio * error_factor), 120, 600)

        stable_cycles = [cycle for cycle in cycles if cycle.get("peak_temp", 0) >= 120]
        cycle_quality = mean([cycle["stability"] for cycle in stable_cycles]) if stable_cycles else 0.0

        if len(burn_samples) >= 150 and error_ratio < 0.1 and len(stable_cycles) >= 3:
            confidence = "high"
        elif len(burn_samples) >= 60 and len(stable_cycles) >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "aTemp": a_temp,
            "schW": sch_w,
            "regW": reg_w,
            "regP": reg_p,
            "confidence": confidence,
            "samples_used": len(burn_samples),
            "cycles_used": len(cycles),
            "stats": {
                "avg_temp": round(avg_temp, 1),
                "peak_temp": round(peak_temp, 1),
                "temp_spread": round(temp_spread, 1),
                "flap_closed_ratio": round(flap_closed_ratio, 3),
                "error_ratio": round(error_ratio, 3),
            },
            "cycle_stats": {
                "stable_cycles": len(stable_cycles),
                "cycle_quality": round(cycle_quality, 3),
            },
            "optimizer_mode": mode,
        }

    def _extract_cycles(self) -> list[dict[str, float]]:
        """Extract coarse burn cycles based on active/inactive transitions."""
        cycles: list[list[BurnSample]] = []
        current: list[BurnSample] = []

        for sample in self._samples:
            if sample.state in ACTIVE_STATES and sample.temp is not None:
                current.append(sample)
                continue
            if current:
                cycles.append(current)
                current = []
        if current:
            cycles.append(current)

        summary: list[dict[str, float]] = []
        for cycle in cycles:
            temps = [s.temp for s in cycle if s.temp is not None]
            if len(temps) < 5:
                continue
            spread = pstdev(temps) if len(temps) > 1 else 0.0
            summary.append(
                {
                    "peak_temp": max(temps),
                    "avg_temp": mean(temps),
                    "stability": 1.0 / (1.0 + spread),
                }
            )
        return summary

    def to_dict(self) -> dict[str, Any]:
        """Serialize optimizer state for persistence."""
        return {
            "samples": [
                {
                    "temp": sample.temp,
                    "flap": sample.flap,
                    "state": sample.state,
                    "com_error": sample.com_error,
                }
                for sample in self._samples
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BurnOptimizer":
        """Create optimizer from persisted data."""
        optimizer = cls()
        if not data:
            return optimizer

        raw_samples = data.get("samples")
        if not isinstance(raw_samples, list):
            return optimizer

        for raw in raw_samples:
            if not isinstance(raw, dict):
                continue
            optimizer._samples.append(
                BurnSample(
                    temp=optimizer._to_float(raw.get("temp")),
                    flap=optimizer._to_int(raw.get("flap")),
                    state=optimizer._to_int(raw.get("state")),
                    com_error=optimizer._to_int(raw.get("com_error")),
                )
            )
        return optimizer

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clamp_int(value: int, min_value: int, max_value: int) -> int:
        return max(min_value, min(max_value, value))

    @staticmethod
    def _default_from_options(options: dict[str, Any], key: str, fallback: int) -> int:
        try:
            return int(options.get(key, fallback))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _closed_ratio(flaps: list[int]) -> float:
        if not flaps:
            return 0.5
        closed = sum(1 for value in flaps if value >= 6)
        return closed / len(flaps)
