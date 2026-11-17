"""Tests for the optimizer and parameter helpers (no Home Assistant instance needed)."""

from __future__ import annotations

import math

from custom_components.kaschuetz.const import BURN_PARAM_LIMITS
from custom_components.kaschuetz.optimizer import BurnOptimizer
from custom_components.kaschuetz.params import parse_burn_params, parse_param, snap_param

CURRENT = {"aTemp": 350, "schW": 375, "regW": 500, "regP": 150}


def test_snap_param_uses_device_grid() -> None:
    assert snap_param("aTemp", 333) == 325
    assert snap_param("aTemp", 999) == 400
    assert snap_param("aTemp", 10) == 75
    assert snap_param("regP", 160) == 150
    assert snap_param("regP", 280) == 300
    assert snap_param("regW", 1200) == 1000
    for key, (low, high, step) in BURN_PARAM_LIMITS.items():
        for value in range(0, 1500, 7):
            snapped = snap_param(key, value)
            assert low <= snapped <= high
            assert (snapped - low) % step == 0


def test_parse_param_unknown() -> None:
    assert parse_param(-1) is None
    assert parse_param("12") == 12
    assert parse_param(None) is None
    assert parse_burn_params({"aTemp": 350, "schW": 375, "regW": 500}) is None
    assert parse_burn_params({"aTemp": 350, "schW": 375, "regW": 500, "regP": -1}) is None


def test_history_is_newest_first_ring_buffer() -> None:
    """TempArr[0] is the newest value; only Time_s/30 + 1 points are valid."""
    optimizer = BurnOptimizer()
    # Burn started 5 minutes ago: 11 valid points, rising temperature.
    chronological = [20 + i * 20 for i in range(11)]
    temp_arr = list(reversed(chronological)) + [0] * 229
    flap_arr = [0] * 240
    optimizer.add_sample(
        {"state": 8, "Temp": 220, "Klappe": 0, "TempArr": temp_arr, "KlappeArr": flap_arr,
         "Time_s": 300, "aTemp": 150}
    )
    snapshot = optimizer.history_snapshot()
    assert snapshot["TempArr"] == chronological
    assert snapshot["sample_step_s"] == 30
    kpis = optimizer.latest_history_kpis()
    assert kpis["peak_temp"] == 220
    assert kpis["time_to_peak_s"] == 300
    assert kpis["overshoot"] == 70


def test_cold_history_keeps_last_kpis() -> None:
    optimizer = BurnOptimizer()
    burn = list(reversed([20 + i * 20 for i in range(11)])) + [0] * 229
    optimizer.add_sample({"TempArr": burn, "KlappeArr": [0] * 240, "Time_s": 300, "aTemp": 150})
    kpis = optimizer.latest_history_kpis()
    optimizer.add_sample({"TempArr": [23] * 240, "KlappeArr": [7] * 240, "Time_s": 90_000})
    assert optimizer.latest_history_kpis() == kpis


def test_burn_states_are_8_and_9() -> None:
    """Samples in searching maximum / burn control feed the optimizer."""
    optimizer = BurnOptimizer()
    for i in range(40):
        optimizer.add_sample({"state": 8 if i < 10 else 9, "Temp": 250 + i, "Klappe": 3})
    suggestion = optimizer.calculate({"aTemp": 350, "schW": 375, "regW": 500, "regP": 150})
    assert suggestion["samples_used"] == 40
    for key, (low, high, step) in BURN_PARAM_LIMITS.items():
        assert low <= suggestion[key] <= high
        assert (suggestion[key] - low) % step == 0


def test_low_sample_suggestion_keeps_current_values() -> None:
    suggestion = BurnOptimizer().calculate({"aTemp": 350, "schW": 375, "regW": 500, "regP": 150})
    assert suggestion["confidence"] == "low"
    assert (suggestion["aTemp"], suggestion["regP"]) == (350, 150)
    # Without known device values there is nothing to suggest.
    assert BurnOptimizer().calculate({})["aTemp"] is None


def test_idle_samples_do_not_fill_the_buffer() -> None:
    optimizer = BurnOptimizer()
    for _ in range(100):
        optimizer.add_sample({"state": 6, "Temp": 23})
    assert optimizer.sample_count() == 0
    for _ in range(10):
        optimizer.add_sample({"state": 9, "Temp": 300})
    for _ in range(100):
        optimizer.add_sample({"state": 6, "Temp": 40})
    # Ten burn samples plus one separator.
    assert optimizer.sample_count() == 11
    restored = BurnOptimizer.from_dict(optimizer.to_dict())
    assert restored.sample_count() == 11


def _burn(optimizer: BurnOptimizer, start: float, points: int, step: float, **extra) -> float:
    """Feed one burn (rise to 350 degC and back) plus its separator; return the end time."""
    for i in range(points):
        temp = 100 + 250 * math.sin(math.pi * i / (points - 1))
        optimizer.add_sample(
            {"state": 9, "Temp": temp, "Klappe": 3, "ComError": 3, **extra}, now=start + i * step
        )
    end = start + points * step
    optimizer.add_sample({"state": 10, "Temp": 80, "Klappe": 7, "ComError": 3}, now=end)
    return end


def test_normal_com_error_is_not_an_error() -> None:
    """ComError is constantly 3 on real devices; it must not make suggestions unsafe."""
    optimizer = BurnOptimizer()
    now = 1_000_000.0
    for _ in range(4):
        now = _burn(optimizer, now, points=60, step=30) + 3600
    suggestion = optimizer.calculate(CURRENT)
    assert suggestion["stats"]["error_ratio"] == 0
    assert suggestion["safety"]["level"] != "unsafe"
    assert suggestion["confidence"] == "high"
    assert suggestion["regP"] == 150


def test_reported_error_state_counts_as_error() -> None:
    optimizer = BurnOptimizer()
    _burn(optimizer, 1_000_000.0, points=60, step=30, errorState=35)
    suggestion = optimizer.calculate(CURRENT)
    assert suggestion["stats"]["error_ratio"] == 1
    assert suggestion["safety"] == {"level": "unsafe", "reasons": ["high_error_ratio"]}


def test_cycle_time_axis_follows_the_poll_interval() -> None:
    """Samples arrive in the poll interval, which is not always 30 s."""
    optimizer = BurnOptimizer()
    _burn(optimizer, 1_000_000.0, points=21, step=120)
    restored = BurnOptimizer.from_dict(optimizer.to_dict())
    for candidate in (optimizer, restored):
        series = candidate.history_snapshot()["recent_cycle_series"][0]
        assert series["time_offset_s"][:3] == [0, 120, 240]
        assert series["kpis"]["time_to_peak_s"] == 1200


def test_confidence_depends_on_burn_time_not_on_sample_count() -> None:
    # 5 s polling: 100 samples are only eight minutes of fire.
    fast = BurnOptimizer()
    _burn(fast, 1_000_000.0, points=100, step=5)
    assert fast.calculate(CURRENT)["confidence"] == "low"
    assert "note" in fast.calculate(CURRENT)

    # 300 s polling: three burns of 50 minutes are plenty, although only 30 samples.
    slow = BurnOptimizer()
    now = 1_000_000.0
    for _ in range(3):
        now = _burn(slow, now, points=10, step=300) + 3600
    assert slow.calculate(CURRENT)["confidence"] == "high"


def test_samples_without_timestamp_assume_the_default_interval() -> None:
    """Data stored by older versions has no timestamps."""
    optimizer = BurnOptimizer()
    _burn(optimizer, 1_000_000.0, points=21, step=120)
    stored = optimizer.to_dict()
    for sample in stored["samples"]:
        del sample["ts"]
    series = BurnOptimizer.from_dict(stored).history_snapshot()["recent_cycle_series"][0]
    assert series["time_offset_s"][:3] == [0, 30, 60]


def test_smooth_burn_keeps_the_control_value_baseline() -> None:
    """The rise and fall of a normal burn is not unsteadiness."""
    optimizer = BurnOptimizer()
    now = 1_000_000.0
    for _ in range(4):
        now = _burn(optimizer, now, points=60, step=30) + 3600
    suggestion = optimizer.calculate(CURRENT)
    assert suggestion["stats"]["temp_unsteadiness"] < 1
    assert suggestion["regW"] == 450


def test_unsteady_burn_raises_the_control_value_without_saturating() -> None:
    optimizer = BurnOptimizer()
    now = 1_000_000.0
    for _ in range(4):
        for i in range(60):
            temp = 100 + 250 * math.sin(math.pi * i / 59) + (15 if i % 2 else -15)
            optimizer.add_sample({"state": 9, "Temp": temp, "Klappe": 3}, now=now + i * 30)
        now += 60 * 30
        optimizer.add_sample({"state": 10, "Temp": 80, "Klappe": 7}, now=now)
        now += 3600
    suggestion = optimizer.calculate(CURRENT)
    assert suggestion["stats"]["temp_unsteadiness"] > 5
    assert 450 < suggestion["regW"] < 1000


def test_sparse_polling_leaves_the_control_value_unchanged() -> None:
    """With samples minutes apart, unsteadiness cannot be told from the burn curve."""
    optimizer = BurnOptimizer()
    now = 1_000_000.0
    for _ in range(3):
        now = _burn(optimizer, now, points=10, step=300) + 3600
    suggestion = optimizer.calculate(CURRENT)
    assert suggestion["stats"]["temp_unsteadiness"] is None
    assert suggestion["regW"] == CURRENT["regW"]
