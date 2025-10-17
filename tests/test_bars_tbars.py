from core.bars import TBarsAggregator


def test_tbars_basic_breakout_sequence():
    tb = TBarsAggregator(base_size=12, tick_size=0.25)
    out = []
    # Seed around 100.0
    for p in [100.0, 100.25, 100.5, 100.25, 100.0]:
        out.extend(tb.update(p, 1))
    # Drive an upside breakout beyond trend/reversal bounds
    for p in [101.0, 102.0, 103.0, 104.0]:
        out.extend(tb.update(p, 1))

    # Expect at least one completed bar emitted
    assert len(out) >= 1
    b = out[-1]
    assert b.high >= b.open and b.high >= b.close
    assert b.low <= b.open and b.low <= b.close
    assert b.end_ts >= b.start_ts


