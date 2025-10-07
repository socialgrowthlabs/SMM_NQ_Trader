import numpy as np
from core.features import FeatureEngine

def test_feature_engine_basic():
    fe = FeatureEngine(window=4)
    fe.update_trades(10, 5)
    fe.update_trades(0, 5)
    fe.update_orderbook(np.array([10, 9]), np.array([8, 7]))
    snap = fe.snapshot()
    assert 0.0 <= snap.delta_confidence <= 1.0
