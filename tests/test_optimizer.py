"""Tests for the optimizer and parameter helpers (no Home Assistant instance needed)."""

from __future__ import annotations

from custom_components.kaschuetz.const import BURN_PARAM_LIMITS
from custom_components.kaschuetz.optimizer import BurnOptimizer
from custom_components.kaschuetz.params import parse_burn_params, parse_param, snap_param


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
