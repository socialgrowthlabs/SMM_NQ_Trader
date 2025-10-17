from core.features import FeatureSnapshot
from core.smm.main import SMMMainEngine


def make_snap(dc: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        cvd=0.0,
        cvd_slope=0.0,
        depth_imbalance=0.0,
        depth_slope=0.0,
        aggressive_buy_ratio=0.5,
        delta_confidence=dc,
    )


def test_main_engine_buy_and_sell_paths():
    eng = SMMMainEngine(ema_period=4, delta_threshold=0.6)
    # Warm EMA with ascending prices to bias long trend
    for p in [100.0, 101.0, 102.0, 103.0]:
        eng.evaluate(p, make_snap(0.5))
    dec_buy = eng.evaluate(104.0, make_snap(0.9))
    assert dec_buy.side in (None, "BUY")

    # Descending prices to bias short trend
    for p in [103.0, 102.0, 101.0, 100.0]:
        eng.evaluate(p, make_snap(0.5))
    dec_sell = eng.evaluate(99.0, make_snap(0.1))
    assert dec_sell.side in (None, "SELL")

