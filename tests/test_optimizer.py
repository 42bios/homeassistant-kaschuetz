from custom_components.kaschuetz.optimizer import BurnOptimizer


def test_optimizer_low_confidence_with_few_samples() -> None:
    optimizer = BurnOptimizer()
    for _ in range(10):
        optimizer.add_sample({"state": 3, "Temp": 120, "Klappe": 5, "ComError": 0})

    result = optimizer.calculate({})
    assert result["confidence"] == "low"
    assert result["samples_used"] == 10


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
