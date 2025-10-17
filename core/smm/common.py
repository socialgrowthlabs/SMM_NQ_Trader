from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Optional, Tuple


class ECandleColoringType(str, Enum):
    ProfitWave = "ProfitWave"
    Trend = "Trend"


class EExtendMethod(str, Enum):
    Touch = "Touch"
    Close = "Close"


class ERealPriceLineWidth(str, Enum):
    Thin = "Thin"
    Thick = "Thick"


class ERealCloseSize(str, Enum):
    Auto = "Auto"
    Small = "Small"
    Large = "Large"


class EMode(str, Enum):
    None_ = "None"
    Buy = "Buy"
    Sell = "Sell"


class EMovingAverageType(str, Enum):
    SMA = "SMA"
    EMA = "EMA"


class EDataSource(str, Enum):
    Price = "Price"
    HeikenAshi = "HeikenAshi"


@dataclass
class SupportResistanceLevel:
    is_support: bool
    from_bar: int
    level: float
    upto_bar: int
    is_active: bool = True


class ExponentialMA:
    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("EMA period must be positive")
        self.period = period
        self.constant1 = 2.0 / (1.0 + period)
        self.constant2 = 1.0 - self.constant1
        self.previous_ema: Optional[float] = None

    def update(self, value: float) -> float:
        if self.previous_ema is None:
            self.previous_ema = value
        else:
            self.previous_ema = value * self.constant1 + self.constant2 * self.previous_ema
        return self.previous_ema


class AverageTrueRange:
    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("ATR period must be positive")
        self.period = period
        self.sample_count = 0
        self.previous_close: Optional[float] = None
        self.previous_atr: float = 0.0

    def update(self, high: float, low: float, close: float) -> float:
        if self.previous_close is None:
            true_range = high - low
        else:
            true_range = max(abs(low - self.previous_close), max(high - low, abs(high - self.previous_close)))
        self.sample_count += 1
        window = min(self.sample_count, self.period)
        if self.sample_count == 1:
            atr = true_range
        else:
            atr = ((window - 1) * self.previous_atr + true_range) / window
        self.previous_close = close
        self.previous_atr = atr
        return atr


class MoneyFlowIndex:
    def __init__(self, period: int) -> None:
        if period <= 1:
            raise ValueError("MFI period must be > 1")
        self.period = period
        self.typical_price_window: Deque[float] = deque(maxlen=period + 1)
        self.volume_window: Deque[float] = deque(maxlen=period + 1)
        self.current_value: float = float("nan")

    def update(self, high: float, low: float, close: float, volume: float) -> float:
        typical_price = (high + low + close) / 3.0
        self.typical_price_window.appendleft(typical_price)
        self.volume_window.appendleft(volume)
        if len(self.typical_price_window) < self.period + 1:
            self.current_value = float("nan")
            return self.current_value
        positive_flow = 0.0
        negative_flow = 0.0
        for i in range(self.period):
            tp_curr = self.typical_price_window[i]
            tp_prev = self.typical_price_window[i + 1]
            vol = self.volume_window[i]
            if tp_curr > tp_prev:
                positive_flow += vol * tp_curr
            elif tp_curr < tp_prev:
                negative_flow += vol * tp_curr
        if negative_flow > 0.0:
            mfr = positive_flow / negative_flow
            self.current_value = 100.0 - (100.0 / (1.0 + mfr))
        else:
            self.current_value = 0.0
        return self.current_value


@dataclass
class HeikenAshiState:
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None


def update_heiken_ashi(state: HeikenAshiState, src_open: float, src_high: float, src_low: float, src_close: float) -> Tuple[float, float, float, float]:
    if state.open is None:
        ha_close = (src_open + src_high + src_low + src_close) * 0.25
        ha_open = src_open
        ha_high = src_high
        ha_low = src_low
    else:
        ha_close = (src_open + src_high + src_low + src_close) * 0.25
        ha_open = (state.open + state.close) * 0.5
        ha_high = max(src_high, ha_open)
        ha_low = min(src_low, ha_open)
    state.open, state.high, state.low, state.close = ha_open, ha_high, ha_low, ha_close
    return ha_open, ha_high, ha_low, ha_close
