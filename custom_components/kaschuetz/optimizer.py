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
    OPTIMIZER_PROFILE_EFFICIENCY,
    OPTIMIZER_PROFILE_FAST_HEATUP,
    OPTIMIZER_PROFILE_STABLE_BURN,
)

ACTIVE_STATES = {3, 4, 9}
HISTORY_SAMPLE_STEP_SECONDS = 8


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
        self._history_temp_arr: list[float] = []
        self._history_flap_arr: list[int] = []
        self._history_time_s: int | None = None
        self._history_setpoint: int | None = None
        self._last_history_time_s_processed: int | None = None
        self._latest_history_kpis: dict[str, Any] = {}

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
        self._update_history(payload)

    def sample_count(self) -> int:
        """Return total number of collected samples."""
        return len(self._samples)

    def clear(self) -> None:
        """Remove all learned samples."""
        self._samples.clear()
        self._history_temp_arr = []
        self._history_flap_arr = []
        self._history_time_s = None
        self._history_setpoint = None
        self._last_history_time_s_processed = None
        self._latest_history_kpis = {}

    def calculate(self, current_options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Calculate optimized abbrand parameters from collected samples."""
        current_options = current_options or {}
        burn_samples = [s for s in self._samples if s.state in ACTIVE_STATES and s.temp is not None]
        cycles = self._extract_cycles()
        history_kpis = self.latest_history_kpis()

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
                "kpis": history_kpis,
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
        profile = str(current_options.get("optimizer_profile", "default"))

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
        adjustments: list[str] = []

        # Additional optimization informed by chart history KPIs.
        overshoot = self._to_float(history_kpis.get("overshoot"))
        time_to_peak_s = self._to_float(history_kpis.get("time_to_peak_s"))
        flap_oscillation = self._to_float(history_kpis.get("flap_oscillation"))
        cooldown_rate = self._to_float(history_kpis.get("cooldown_rate_c_per_min"))

        if overshoot is not None and overshoot > 60:
            a_temp -= 8
            sch_w += 15
            adjustments.append("high_overshoot")
        if time_to_peak_s is not None and time_to_peak_s > 1600:
            a_temp += 5
            reg_w += 20
            adjustments.append("slow_heatup")
        if flap_oscillation is not None and flap_oscillation > 1.8:
            reg_p += 20
            adjustments.append("flap_oscillation")
        if cooldown_rate is not None and cooldown_rate < -35:
            sch_w -= 10
            adjustments.append("fast_cooldown")

        if profile == OPTIMIZER_PROFILE_FAST_HEATUP:
            a_temp += 5
            reg_w += 15
            adjustments.append("profile_fast_heatup")
        elif profile == OPTIMIZER_PROFILE_STABLE_BURN:
            reg_p += 20
            sch_w += 8
            adjustments.append("profile_stable_burn")
        elif profile == OPTIMIZER_PROFILE_EFFICIENCY:
            a_temp -= 5
            sch_w += 10
            adjustments.append("profile_efficiency")

        a_temp = self._clamp_int(a_temp, 120, 320)
        sch_w = self._clamp_int(sch_w, 120, 700)
        reg_w = self._clamp_int(reg_w, 200, 1200)
        reg_p = self._clamp_int(reg_p, 120, 600)

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
            "kpis": history_kpis,
            "adjustments": adjustments,
            "optimizer_mode": mode,
            "optimizer_profile": profile,
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

    def latest_history_kpis(self) -> dict[str, Any]:
        """Return latest KPI snapshot from TempArr/KlappeArr history."""
        return dict(self._latest_history_kpis)

    def history_snapshot(self, max_points: int = 240, include_arrays: bool = True) -> dict[str, Any]:
        """Return a history export object for diagnostics/services."""
        max_points = max(1, int(max_points))
        temp_tail = self._history_temp_arr[-max_points:]
        flap_tail = self._history_flap_arr[-max_points:]
        recent_cycle_series = self._extract_cycle_series(max_cycles=6, max_points=max_points)
        payload: dict[str, Any] = {
            "time_s": self._history_time_s,
            "sample_step_s": HISTORY_SAMPLE_STEP_SECONDS,
            "points": len(temp_tail),
            "kpis": self.latest_history_kpis(),
            "recent_cycles": self._extract_cycles()[-10:],
            "recent_cycle_series": recent_cycle_series,
        }
        if include_arrays:
            payload["TempArr"] = [round(value, 2) for value in temp_tail]
            payload["KlappeArr"] = flap_tail
        return payload

    def _extract_cycle_series(
        self, max_cycles: int = 6, max_points: int = 240
    ) -> list[dict[str, Any]]:
        """Extract per-cycle curve arrays from sampled active periods."""
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

        result: list[dict[str, Any]] = []
        for idx, cycle in enumerate(cycles[-max_cycles:], start=1):
            temps = [s.temp for s in cycle if s.temp is not None]
            flaps = [s.flap for s in cycle if s.flap is not None]
            if len(temps) < 3:
                continue
            points = min(max_points, len(temps))
            temps_tail = temps[-points:]
            flaps_tail = flaps[-points:] if flaps else []
            peak = max(temps_tail)
            peak_idx = temps_tail.index(peak)
            result.append(
                {
                    "cycle_index": idx,
                    "points": points,
                    "TempArr": [round(v, 2) for v in temps_tail],
                    "KlappeArr": flaps_tail,
                    "time_offset_s": [i * HISTORY_SAMPLE_STEP_SECONDS for i in range(points)],
                    "kpis": {
                        "time_to_peak_s": round(peak_idx * HISTORY_SAMPLE_STEP_SECONDS, 1),
                        "peak_temp": round(peak, 1),
                        "flap_oscillation": round(pstdev(flaps_tail), 3)
                        if len(flaps_tail) > 1
                        else 0.0,
                    },
                }
            )
        return result

    def _update_history(self, payload: dict[str, Any]) -> None:
        """Update TempArr/KlappeArr based history cache when provided."""
        raw_temp = payload.get("TempArr")
        raw_flap = payload.get("KlappeArr")
        time_s = self._to_int(payload.get("Time_s"))
        setpoint = self._to_int(payload.get("aTemp"))

        temp_arr = self._to_float_list(raw_temp)
        flap_arr = self._to_int_list(raw_flap)
        if not temp_arr or not flap_arr or len(temp_arr) != len(flap_arr):
            return

        if time_s is not None and self._last_history_time_s_processed == time_s:
            return

        self._history_temp_arr = temp_arr
        self._history_flap_arr = flap_arr
        self._history_time_s = time_s
        self._history_setpoint = setpoint
        self._last_history_time_s_processed = time_s
        self._latest_history_kpis = self._compute_history_kpis(temp_arr, flap_arr, setpoint)

    @staticmethod
    def _compute_history_kpis(
        temp_arr: list[float],
        flap_arr: list[int],
        setpoint: int | None,
    ) -> dict[str, Any]:
        """Compute KPI set used by diagnostics and optimizer."""
        if len(temp_arr) < 3:
            return {}

        peak_temp = max(temp_arr)
        peak_idx = temp_arr.index(peak_temp)
        time_to_peak_s = peak_idx * HISTORY_SAMPLE_STEP_SECONDS
        active_setpoint = setpoint if setpoint is not None else DEFAULT_A_TEMP
        overshoot = peak_temp - active_setpoint

        tail_count = max(0, len(temp_arr) - peak_idx - 1)
        if tail_count > 0:
            cooldown_min = (tail_count * HISTORY_SAMPLE_STEP_SECONDS) / 60.0
            cooldown_rate = (temp_arr[-1] - peak_temp) / cooldown_min if cooldown_min > 0 else 0.0
        else:
            cooldown_rate = 0.0

        flap_oscillation = pstdev(flap_arr) if len(flap_arr) > 1 else 0.0
        return {
            "time_to_peak_s": round(time_to_peak_s, 1),
            "peak_temp": round(peak_temp, 1),
            "overshoot": round(overshoot, 1),
            "cooldown_rate_c_per_min": round(cooldown_rate, 2),
            "flap_oscillation": round(flap_oscillation, 3),
        }

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
            ],
            "history": {
                "TempArr": self._history_temp_arr,
                "KlappeArr": self._history_flap_arr,
                "Time_s": self._history_time_s,
                "setpoint": self._history_setpoint,
                "kpis": self._latest_history_kpis,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BurnOptimizer:
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

        history = data.get("history")
        if isinstance(history, dict):
            optimizer._history_temp_arr = optimizer._to_float_list(history.get("TempArr"))
            optimizer._history_flap_arr = optimizer._to_int_list(history.get("KlappeArr"))
            optimizer._history_time_s = optimizer._to_int(history.get("Time_s"))
            optimizer._history_setpoint = optimizer._to_int(history.get("setpoint"))
            kpis = history.get("kpis")
            if isinstance(kpis, dict):
                optimizer._latest_history_kpis = dict(kpis)
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

    @classmethod
    def _to_int_list(cls, value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        out: list[int] = []
        for item in value:
            parsed = cls._to_int(item)
            if parsed is not None:
                out.append(parsed)
        return out

    @classmethod
    def _to_float_list(cls, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        out: list[float] = []
        for item in value:
            parsed = cls._to_float(item)
            if parsed is not None:
                out.append(parsed)
        return out

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
