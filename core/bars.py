from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, List
from core.smm.common import HeikenAshiState, update_heiken_ashi


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float
    start_ts: float
    end_ts: float


class BarAggregator:
    """Simple bar aggregator supporting time-based bars and tick-count bars.

    mode: "time" or "ticks"
      - time: create a new bar every duration_sec seconds
      - ticks: create a new bar every ticks_per_bar ticks
    """

    def __init__(self, mode: str = "time", duration_sec: int = 60, ticks_per_bar: int = 200) -> None:
        self.mode = mode
        self.duration_sec = int(duration_sec)
        self.ticks_per_bar = int(ticks_per_bar)
        self._open: Optional[float] = None
        self._high: Optional[float] = None
        self._low: Optional[float] = None
        self._close: Optional[float] = None
        self._volume: float = 0.0
        self._start_ts: Optional[float] = None
        self._tick_count: int = 0

    def _reset(self) -> None:
        self._open = None
        self._high = None
        self._low = None
        self._close = None
        self._volume = 0.0
        self._start_ts = None
        self._tick_count = 0

    def update(self, price: float, size: float, ts: Optional[float] = None) -> List[Bar]:
        now = float(ts if ts is not None else time.time())
        bars: List[Bar] = []

        # Initialize current bar if needed
        if self._open is None:
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._volume = float(size)
            self._start_ts = now
            self._tick_count = 1
            return bars

        # Update current bar
        if price > (self._high or price):
            self._high = price
        if price < (self._low or price):
            self._low = price
        self._close = price
        self._volume += float(size)
        self._tick_count += 1

        # Decide if bar completes
        should_close = False
        if self.mode == "time":
            if self._start_ts is not None:
                elapsed = now - self._start_ts
                print(f"BAR AGGREGATOR DEBUG: elapsed={elapsed:.1f}s, duration={self.duration_sec}s, should_close={elapsed >= self.duration_sec}", flush=True)
                if elapsed >= self.duration_sec:
                    should_close = True
        else:  # ticks
            if self._tick_count >= self.ticks_per_bar:
                should_close = True

        if should_close:
            bar = Bar(
                open=self._open or price,
                high=self._high or price,
                low=self._low or price,
                close=self._close or price,
                volume=self._volume,
                start_ts=float(self._start_ts or now),
                end_ts=now,
            )
            bars.append(bar)
            # Start next bar with current state as seed for responsiveness
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._volume = 0.0
            self._start_ts = now
            self._tick_count = 0

        return bars


class TBarsAggregator:
    """Approximation of NT8 TBars with Heiken-Ashi construction.

    Parameters:
    - base_size: controls openOffset (base), trendOffset (value=base/2), reversalOffset (value2=base*2)
    - tick_size: instrument tick size (NQ/MNQ typically 0.25)

    Behavior mirrors the C# TBars: maintains a running HA bar bounded by
    [barMin, barMax]; if price exceeds bounds, closes current bar and opens a
    new one with a synthetic (fake) open shifted by openOffset in the direction
    of the breakout.
    """

    def __init__(self, base_size: int = 12, tick_size: float = 0.25) -> None:
        self.base_size = int(base_size)
        self.tick_size = float(tick_size)

        # Derived offsets
        self.value = self.base_size / 2.0
        self.value2 = self.base_size * 2.0
        self.openOffset = self.base_size * self.tick_size
        self.trendOffset = self.value * self.tick_size
        self.reversalOffset = self.value2 * self.tick_size

        # State
        self._ha = HeikenAshiState()
        self._bar_open: Optional[float] = None
        self._bar_high: Optional[float] = None
        self._bar_low: Optional[float] = None
        self._bar_close: Optional[float] = None
        self._bar_start_ts: Optional[float] = None
        self._bar_dir: int = 0  # -1 bear, 0 flat, 1 bull
        self._bar_max: Optional[float] = None
        self._bar_min: Optional[float] = None

    def _emit_bar(self, end_ts: float) -> Bar:
        bar = Bar(
            open=float(self._ha.open if self._ha.open is not None else (self._bar_open or 0.0)),
            high=float(self._ha.high if self._ha.high is not None else (self._bar_high or 0.0)),
            low=float(self._ha.low if self._ha.low is not None else (self._bar_low or 0.0)),
            close=float(self._ha.close if self._ha.close is not None else (self._bar_close or 0.0)),
            volume=0.0,
            start_ts=float(self._bar_start_ts or end_ts),
            end_ts=end_ts,
        )
        return bar

    def update(self, price: float, size: float, ts: Optional[float] = None) -> List[Bar]:
        now = float(ts if ts is not None else time.time())
        out: List[Bar] = []

        # Initialize first bar
        if self._bar_open is None:
            self._bar_open = price
            self._bar_high = price
            self._bar_low = price
            self._bar_close = price
            self._bar_start_ts = now
            self._bar_max = self._bar_open + self.trendOffset * float(self._bar_dir)
            self._bar_min = self._bar_open - self.trendOffset * float(self._bar_dir)
            # Seed HA with initial OHLC
            update_heiken_ashi(self._ha, price, price, price, price)
            return out

        # Update current HA bar bounds
        high = max(self._bar_high or price, price)
        low = min(self._bar_low or price, price)
        ha_open, ha_high, ha_low, ha_close = update_heiken_ashi(self._ha, self._bar_open or price, high, low, price)

        # Check bounds
        max_exceeded = price > (self._bar_max if self._bar_max is not None else float('inf'))
        min_exceeded = price < (self._bar_min if self._bar_min is not None else float('-inf'))

        if not max_exceeded and not min_exceeded:
            # Continue current bar
            self._bar_high = high
            self._bar_low = low
            self._bar_close = price
            return out

        # Close current bar at bounded price
        close1 = min(price, self._bar_max) if max_exceeded else (max(price, self._bar_min) if min_exceeded else price)
        self._bar_dir = 1 if max_exceeded else (-1 if min_exceeded else 0)

        # Emit closed HA bar snapshot
        self._bar_high = max(self._bar_high or close1, close1)
        self._bar_low = min(self._bar_low or close1, close1)
        self._bar_close = close1
        # Recompute HA close for the final state
        update_heiken_ashi(self._ha, self._bar_open or close1, self._bar_high, self._bar_low, self._bar_close)
        out.append(self._emit_bar(now))

        # Start new bar with fake open shifted by openOffset
        fake_open = close1 - self.openOffset * float(self._bar_dir)
        self._bar_open = fake_open
        self._bar_high = close1 if max_exceeded else fake_open
        self._bar_low = close1 if min_exceeded else fake_open
        self._bar_close = close1
        self._bar_start_ts = now
        self._bar_max = close1 + (self.trendOffset if self._bar_dir > 0 else self.reversalOffset)
        self._bar_min = close1 - (self.reversalOffset if self._bar_dir > 0 else self.trendOffset)
        # Initialize HA for new bar using fake open and prior close
        prev_close = out[-1].close if out else (self._ha.close or fake_open)
        ha_open2 = 0.5 * (fake_open + prev_close)
        ha_high2 = max(ha_open2, self._bar_high)
        ha_low2 = min(ha_open2, self._bar_low)
        update_heiken_ashi(self._ha, ha_open2, ha_high2, ha_low2, close1)

        return out


