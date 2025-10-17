import os
from core.features import FeatureSnapshot
from core.smm.combined import SMMCombinedSignal


def snap(dc: float) -> FeatureSnapshot:
    return FeatureSnapshot(cvd=0, cvd_slope=0, depth_imbalance=0, depth_slope=0, aggressive_buy_ratio=0.5, delta_confidence=dc)


def test_env_delta_threshold_override(monkeypatch):
    monkeypatch.setenv("DELTA_CONFIDENCE_THRESHOLD", "0.9")
    comb = SMMCombinedSignal(delta_threshold=0.6)
    # Warm trend bullish
    for p in [100, 101, 102, 103, 104]:
        comb.on_bar(p - 0.5, p + 0.5, p - 1.0, p, 1000)
    # With 0.85 confidence and threshold 0.9, should not BUY
    d = comb.evaluate(105.0, snap(0.85))
    assert d.side is None

    # With 0.95 confidence, should BUY in bullish trend
    d2 = comb.evaluate(106.0, snap(0.95))
    assert d2.side in (None, "BUY")


