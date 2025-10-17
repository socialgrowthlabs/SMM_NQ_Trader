from core.features import FeatureSnapshot
from core.smm.combined import SMMCombinedSignal


def make_snap(dc: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        cvd=0.0,
        cvd_slope=0.0,
        depth_imbalance=0.0,
        depth_slope=0.0,
        aggressive_buy_ratio=0.5,
        delta_confidence=dc,
    )


def test_combined_trend_gating():
    comb = SMMCombinedSignal(delta_threshold=0.6)
    # Bullish trend via on_bar
    for p in [100, 101, 102, 103, 104]:
        comb.on_bar(p - 0.5, p + 0.5, p - 1.0, p, 1000)
    d = comb.evaluate(105.0, make_snap(0.9))
    assert d.side == "BUY"

    # Bearish trend
    for p in [104, 103, 102, 101, 100]:
        comb.on_bar(p + 0.5, p + 1.0, p - 0.5, p, 1000)
    d2 = comb.evaluate(99.0, make_snap(0.1))
    assert d2.side == "SELL"

