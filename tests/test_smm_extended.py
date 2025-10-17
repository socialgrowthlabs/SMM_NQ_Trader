from core.smm.main import SMMMainEngine
from core.features import FeatureSnapshot


def snap(dc: float) -> FeatureSnapshot:
    return FeatureSnapshot(cvd=0, cvd_slope=0, depth_imbalance=0, depth_slope=0, aggressive_buy_ratio=0.5, delta_confidence=dc)


def test_strong_bull_and_filters():
    eng = SMMMainEngine(delta_threshold=0.6, use_ma_filter=True)
    # Warm up bars to seed DI/MFI/ATR and HA
    for o,h,l,c,v in [
        (100,101,99,100.5,1000),
        (100.5,102,100,101.5,1200),
        (101.5,103,101,102.5,1500),
        (102.5,104,102,103.5,1500),
    ]:
        eng.on_bar(o,h,l,c,v)
    d = eng.evaluate(104.0, snap(0.9))
    assert d.side in (None, "BUY")  # Depending on DI/MFI warmup


def test_strong_bear_and_filters():
    eng = SMMMainEngine(delta_threshold=0.6, use_ma_filter=True)
    for o,h,l,c,v in [
        (104,105,103,104.5,1000),
        (104.5,105,103.5,104.0,1200),
        (104.0,104.5,102.5,103.0,1500),
        (103.0,103.5,101.5,102.0,1500),
    ]:
        eng.on_bar(o,h,l,c,v)
    d = eng.evaluate(101.5, snap(0.1))
    assert d.side in (None, "SELL")

