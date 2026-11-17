"""Burn optimization helper for Kaschuetz integration."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from .const import (
    BURN_PARAM_KEYS,
    BURN_STATES,
    HISTORY_BUFFER_SIZE,
    HISTORY_SAMPLE_STEP_SECONDS,
    OPTIMIZER_MODE_AGGRESSIVE,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODE_CONSERVATIVE,
    OPTIMIZER_PROFILE_EFFICIENCY,
    OPTIMIZER_PROFILE_FAST_HEATUP,
    OPTIMIZER_PROFILE_STABLE_BURN,
)
from .params import parse_param, snap_param

# "Searching maximum" and "burn control" are the states with an active fire.
ACTIVE_STATES = BURN_STATES
MIN_CYCLE_POINTS = 3
MIN_CYCLE_SECONDS = 210
MIN_CYCLE_DELTA_TEMP = 20.0

# Burn time needed for a suggestion and for the confidence levels. Samples
# arrive in the poll interval, so their number alone says little.
MIN_BURN_SECONDS = 15 * 60
MEDIUM_CONFIDENCE_BURN_SECONDS = 30 * 60
HIGH_CONFIDENCE_BURN_SECONDS = 75 * 60

# Interval assumed for samples without a usable timestamp (data stored by
# versions before timestamps were recorded, or a gap between two burns).
DEFAULT_SAMPLE_INTERVAL_SECONDS = 30
MAX_SAMPLE_GAP_SECONDS = 900

# Unsteadiness is the scatter of the temperature around its mean within this
# time span to either side; a wider span would count the burn curve itself.
UNSTEADINESS_WINDOW_SECONDS = 60
DEFAULT_REG_W = 450


@dataclass(slots=True)
class BurnSample:
    """Single normalized sample from the oven payload."""

    temp: float | None
    flap: int | None
    state: int | None
    com_error: int | None
    # The controller reports "errorState" only while it has a fault.
    fault: bool = False
    # Unix time of the poll; None for samples stored by older versions.
    ts: float | None = None


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

    def add_sample(self, payload: dict[str, Any], now: float | None = None) -> bool:
        """Add a sample from raw device payload; return whether it was kept.

        Only burn samples are kept, plus one non-burn sample after each burn as
        cycle separator, so long idle periods do not push burns out of the buffer.
        """
        sample = BurnSample(
            temp=self._to_float(payload.get("Temp")),
            flap=self._to_int(payload.get("Klappe")),
            state=self._to_int(payload.get("state")),
            com_error=self._to_int(payload.get("ComError")),
            fault=payload.get("errorState") is not None,
            ts=round(time.time() if now is None else now, 1),
        )
        kept = sample.state in ACTIVE_STATES or self.burn_active
        if kept:
            self._samples.append(sample)
        self._update_history(payload)
        return kept

    @property
    def burn_active(self) -> bool:
        """Return whether the newest kept sample belongs to a running burn."""
        return bool(self._samples) and self._samples[-1].state in ACTIVE_STATES

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

        burn_seconds = self._time_offsets(burn_samples)[-1] if burn_samples else 0.0
        if burn_seconds < MIN_BURN_SECONDS:
            safety = self._assess_safety(
                confidence="low",
                error_ratio=0.0,
                temp_spread=0.0,
                adjustments=[],
                history_kpis=history_kpis,
            )
            # Not enough data: suggest keeping the current device values.
            return {
                **{key: parse_param(current_options.get(key)) for key in BURN_PARAM_KEYS},
                "confidence": "low",
                "note": "Too few burn samples. Keep observing for better optimization.",
                "samples_used": len(burn_samples),
                "cycles_used": len(cycles),
                "kpis": history_kpis,
                "safety": safety,
            }

        temps = [s.temp for s in burn_samples if s.temp is not None]
        flaps = [s.flap for s in burn_samples if s.flap is not None]
        # ComError is not an error flag (real controllers constantly report 3).
        errors = [s for s in burn_samples if s.fault]

        avg_temp = mean(temps)
        peak_temp = max(temps)
        temp_spread = pstdev(temps) if len(temps) > 1 else 0.0
        temp_unsteadiness = self._temp_unsteadiness()
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
        a_temp = round(avg_temp * temp_factor)
        sch_w = round(220 + (1.0 - flap_closed_ratio) * 320)
        if temp_unsteadiness is None:
            # Polled too sparsely to judge: keep the value the device has.
            reg_w = parse_param(current_options.get("regW")) or DEFAULT_REG_W
        else:
            reg_w = round(DEFAULT_REG_W + temp_unsteadiness * spread_factor)
        reg_p = round(160 + error_ratio * error_factor)
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

        # Only values the controller accepts (range and step of the web UI).
        a_temp = snap_param("aTemp", a_temp)
        sch_w = snap_param("schW", sch_w)
        reg_w = snap_param("regW", reg_w)
        reg_p = snap_param("regP", reg_p)

        stable_cycles = [cycle for cycle in cycles if cycle.get("peak_temp", 0) >= 120]
        cycle_quality = mean([cycle["stability"] for cycle in stable_cycles]) if stable_cycles else 0.0

        if (
            burn_seconds >= HIGH_CONFIDENCE_BURN_SECONDS
            and error_ratio < 0.1
            and len(stable_cycles) >= 3
        ):
            confidence = "high"
        elif burn_seconds >= MEDIUM_CONFIDENCE_BURN_SECONDS and len(stable_cycles) >= 1:
            confidence = "medium"
        else:
            confidence = "low"
        safety = self._assess_safety(
            confidence=confidence,
            error_ratio=error_ratio,
            temp_spread=temp_spread,
            adjustments=adjustments,
            history_kpis=history_kpis,
        )

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
                "temp_unsteadiness": (
                    None if temp_unsteadiness is None else round(temp_unsteadiness, 1)
                ),
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
            "safety": safety,
        }

    def _extract_cycles(self) -> list[dict[str, float]]:
        """Extract coarse burn cycles based on active/inactive transitions."""
        summary: list[dict[str, float]] = []
        for cycle in self._iter_active_cycles():
            temps = [s.temp for s in cycle if s.temp is not None]
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
        cycles = self._iter_active_cycles()
        result: list[dict[str, Any]] = []
        for idx, cycle in enumerate(cycles[-max_cycles:], start=1):
            temps = [s.temp for s in cycle if s.temp is not None]
            flaps = [s.flap for s in cycle if s.flap is not None]
            if len(temps) < 3:
                continue
            points = min(max_points, len(temps))
            temps_tail = temps[-points:]
            flaps_tail = flaps[-points:] if flaps else []
            offsets = self._time_offsets(cycle[-points:])
            peak = max(temps_tail)
            peak_idx = temps_tail.index(peak)
            result.append(
                {
                    "cycle_index": idx,
                    "points": points,
                    "TempArr": [round(v, 2) for v in temps_tail],
                    "KlappeArr": flaps_tail,
                    "time_offset_s": offsets,
                    "kpis": {
                        "time_to_peak_s": offsets[peak_idx],
                        "peak_temp": round(peak, 1),
                        "flap_oscillation": round(pstdev(flaps_tail), 3)
                        if len(flaps_tail) > 1
                        else 0.0,
                    },
                }
            )
        return result

    def _iter_active_cycles(self) -> list[list[BurnSample]]:
        """Split samples into robust active burn cycles."""
        cycles: list[list[BurnSample]] = []
        current: list[BurnSample] = []
        for sample in self._samples:
            if sample.state in ACTIVE_STATES and sample.temp is not None:
                current.append(sample)
                continue
            if current:
                self._append_cycle_if_valid(cycles, current)
                current = []
        if current:
            self._append_cycle_if_valid(cycles, current)
        return cycles

    def _append_cycle_if_valid(
        self, cycles: list[list[BurnSample]], cycle: list[BurnSample]
    ) -> None:
        """Append cycle when it is long enough and has thermal movement."""
        temps = [s.temp for s in cycle if s.temp is not None]
        if len(temps) < MIN_CYCLE_POINTS:
            return
        if self._time_offsets(cycle)[-1] < MIN_CYCLE_SECONDS:
            return
        if (max(temps) - min(temps)) < MIN_CYCLE_DELTA_TEMP:
            return
        cycles.append(cycle)

    def _temp_unsteadiness(self) -> float | None:
        """Return how far the temperature scatters around its short-term mean.

        The spread over a whole burn mostly measures the rise and fall of the
        burn curve. This compares each sample only with its neighbours in
        time, so a smooth burn yields a value near zero. None without samples
        that have a neighbour on both sides within the window.
        """
        residuals: list[float] = []
        for cycle in self._iter_active_cycles():
            temps = [s.temp for s in cycle if s.temp is not None]
            offsets = self._time_offsets(cycle)
            first = 0
            last = 0
            for idx, offset in enumerate(offsets):
                while offset - offsets[first] > UNSTEADINESS_WINDOW_SECONDS:
                    first += 1
                while (
                    last + 1 < len(offsets)
                    and offsets[last + 1] - offset <= UNSTEADINESS_WINDOW_SECONDS
                ):
                    last += 1
                if first < idx < last:
                    residuals.append(abs(temps[idx] - mean(temps[first : last + 1])))
        return mean(residuals) if residuals else None

    @staticmethod
    def _time_offsets(samples: list[BurnSample]) -> list[float]:
        """Return the seconds from the first sample to each sample."""
        offsets: list[float] = []
        elapsed = 0.0
        previous: BurnSample | None = None
        for sample in samples:
            if previous is not None:
                step = (
                    sample.ts - previous.ts
                    if sample.ts is not None and previous.ts is not None
                    else None
                )
                if step is None or not 0 < step <= MAX_SAMPLE_GAP_SECONDS:
                    step = DEFAULT_SAMPLE_INTERVAL_SECONDS
                elapsed += step
            offsets.append(round(elapsed, 1))
            previous = sample
        return offsets

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
        # The device sends a ring buffer, newest value first. Time_s counts the
        # seconds since the burn started, so only that many points are valid.
        valid = len(temp_arr)
        if time_s is not None:
            valid = min(valid, time_s // HISTORY_SAMPLE_STEP_SECONDS + 1, HISTORY_BUFFER_SIZE)
        temp_arr = list(reversed(temp_arr[:valid]))
        flap_arr = list(reversed(flap_arr[:valid]))

        if time_s is not None and self._last_history_time_s_processed == time_s:
            return

        self._history_temp_arr = self._smooth_temp_outliers(temp_arr)
        self._history_flap_arr = flap_arr
        self._history_time_s = time_s
        self._history_setpoint = setpoint
        self._last_history_time_s_processed = time_s
        # Keep the KPIs of the last real burn while the oven is cold.
        if max(temp_arr) - min(temp_arr) >= MIN_CYCLE_DELTA_TEMP:
            self._latest_history_kpis = self._compute_history_kpis(
                self._history_temp_arr, flap_arr, setpoint
            )

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
        overshoot = peak_temp - setpoint if setpoint is not None else None

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
            "overshoot": round(overshoot, 1) if overshoot is not None else None,
            "cooldown_rate_c_per_min": round(cooldown_rate, 2),
            "flap_oscillation": round(flap_oscillation, 3),
        }

    @staticmethod
    def _smooth_temp_outliers(temp_arr: list[float]) -> list[float]:
        """Suppress implausible jump spikes in history temperature array."""
        if len(temp_arr) < 3:
            return temp_arr
        cleaned = list(temp_arr)
        for idx in range(1, len(cleaned) - 1):
            prev_v = cleaned[idx - 1]
            cur_v = cleaned[idx]
            next_v = cleaned[idx + 1]
            if abs(cur_v - prev_v) > 85 and abs(cur_v - next_v) > 85:
                cleaned[idx] = round((prev_v + next_v) / 2.0, 2)
        return cleaned

    @staticmethod
    def _assess_safety(
        confidence: str,
        error_ratio: float,
        temp_spread: float,
        adjustments: list[str],
        history_kpis: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a safety gate object for recommendation handling."""
        overshoot = BurnOptimizer._to_float(history_kpis.get("overshoot")) or 0.0
        flap_osc = BurnOptimizer._to_float(history_kpis.get("flap_oscillation")) or 0.0
        reasons: list[str] = []

        if error_ratio > 0.25:
            reasons.append("high_error_ratio")
        if overshoot > 120:
            reasons.append("extreme_overshoot")
        if flap_osc > 3.2:
            reasons.append("unstable_flap")

        if reasons:
            return {"level": "unsafe", "reasons": reasons}

        caution = False
        if confidence == "low":
            reasons.append("low_confidence")
            caution = True
        if overshoot > 70:
            reasons.append("overshoot_high")
            caution = True
        if temp_spread > 80:
            reasons.append("temperature_spread_high")
            caution = True
        if len(adjustments) > 4:
            reasons.append("many_adjustments")
            caution = True

        if caution:
            return {"level": "caution", "reasons": reasons}
        return {"level": "safe", "reasons": ["within_expected_bounds"]}

    def to_dict(self) -> dict[str, Any]:
        """Serialize optimizer state for persistence."""
        return {
            "samples": [
                {
                    "temp": sample.temp,
                    "flap": sample.flap,
                    "state": sample.state,
                    "com_error": sample.com_error,
                    "fault": sample.fault,
                    "ts": sample.ts,
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
            sample = BurnSample(
                temp=optimizer._to_float(raw.get("temp")),
                flap=optimizer._to_int(raw.get("flap")),
                state=optimizer._to_int(raw.get("state")),
                com_error=optimizer._to_int(raw.get("com_error")),
                fault=bool(raw.get("fault", False)),
                ts=optimizer._to_float(raw.get("ts")),
            )
            previous_active = (
                bool(optimizer._samples) and optimizer._samples[-1].state in ACTIVE_STATES
            )
            # Older versions stored every poll; keep only burns and separators.
            if sample.state in ACTIVE_STATES or previous_active:
                optimizer._samples.append(sample)

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
    def _closed_ratio(flaps: list[int]) -> float:
        if not flaps:
            return 0.5
        closed = sum(1 for value in flaps if value >= 6)
        return closed / len(flaps)
