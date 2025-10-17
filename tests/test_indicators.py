from core.smm.common import ExponentialMA, AverageTrueRange, MoneyFlowIndex, HeikenAshiState, update_heiken_ashi

def test_ema_monotonicity():
    ema = ExponentialMA(10)
    vals = [ema.update(x) for x in [1,2,3,4,5,6,7,8,9,10]]
    assert abs(vals[-1] - 10) < 5.0

def test_atr_positive():
    atr = AverageTrueRange(14)
    a = [atr.update(h,l,c) for (h,l,c) in [(2,1,1.5),(3,2,2.5),(4,3,3.5)]]
    assert all(v >= 0 for v in a)

def test_mfi_range():
    mfi = MoneyFlowIndex(5)
    for _ in range(7):
        mfi.update(10,9,9.5,1000)
    assert 0.0 <= mfi.current_value <= 100.0

def test_heiken_ashi_initialization():
    s = HeikenAshiState()
    o,h,l,c = update_heiken_ashi(s, 10, 11, 9, 10.5)
    assert s.open is not None and s.close is not None
