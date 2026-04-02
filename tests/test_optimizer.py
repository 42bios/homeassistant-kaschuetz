from custom_components.kaschuetz.optimizer import BurnOptimizer


def test_optimizer_low_confidence_with_few_samples() -> None:
    optimizer = BurnOptimizer()
    for _ in range(10):
        optimizer.add_sample({"state": 3, "Temp": 120, "Klappe": 5, "ComError": 0})

    result = optimizer.calculate({})
    assert result["confidence"] == "low"
    assert result["samples_used"] == 10
    assert result["safety"]["level"] == "caution"


def test_optimizer_cycle_detection_improves_confidence() -> None:
    optimizer = BurnOptimizer()

    for _ in range(3):
        for temp in range(80, 190):
            optimizer.add_sample({"state": 3, "Temp": temp, "Klappe": 4, "ComError": 0})
        for _ in range(10):
            optimizer.add_sample({"state": 6, "Temp": 40, "Klappe": 7, "ComError": 0})

    result = optimizer.calculate({"optimizer_mode": "balanced"})
    assert result["samples_used"] >= 300
    assert result["cycles_used"] >= 3
    assert result["confidence"] in {"medium", "high"}


def test_history_kpis_from_temp_and_flap_arrays() -> None:
    optimizer = BurnOptimizer()
    payload = {
        "state": 3,
        "Temp": 180,
        "Klappe": 5,
        "ComError": 0,
        "aTemp": 180,
        "Time_s": 1000,
        "TempArr": [80, 110, 140, 180, 220, 205, 190, 175],
        "KlappeArr": [4, 4, 5, 5, 6, 7, 7, 7],
    }
    optimizer.add_sample(payload)
    kpis = optimizer.latest_history_kpis()

    assert kpis["peak_temp"] == 220.0
    assert kpis["time_to_peak_s"] == 32.0
    assert kpis["overshoot"] == 40.0


def test_history_snapshot_includes_arrays_and_kpis() -> None:
    optimizer = BurnOptimizer()
    optimizer.add_sample(
        {
            "state": 3,
            "Temp": 160,
            "Klappe": 5,
            "ComError": 0,
            "aTemp": 170,
            "Time_s": 2000,
            "TempArr": [100, 120, 150, 175],
            "KlappeArr": [3, 4, 5, 6],
        }
    )
    snapshot = optimizer.history_snapshot(max_points=3, include_arrays=True)

    assert snapshot["points"] == 3
    assert snapshot["TempArr"] == [120.0, 150.0, 175.0]
    assert snapshot["KlappeArr"] == [4, 5, 6]
    assert "kpis" in snapshot


def test_temp_outlier_is_filtered_in_history_kpis() -> None:
    optimizer = BurnOptimizer()
    optimizer.add_sample(
        {
            "state": 3,
            "Temp": 180,
            "Klappe": 5,
            "ComError": 0,
            "aTemp": 180,
            "Time_s": 3000,
            "TempArr": [100, 120, 999, 140, 160],
            "KlappeArr": [3, 4, 5, 6, 7],
        }
    )
    snapshot = optimizer.history_snapshot(max_points=5, include_arrays=True)
    assert snapshot["TempArr"][2] != 999
