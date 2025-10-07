from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .common import ExponentialMA, AverageTrueRange, MoneyFlowIndex, HeikenAshiState, update_heiken_ashi, EMode


@dataclass
class DashboardState:
    ema_fast_period: int = 8
    ema_slow_period: int = 21
    atr_period: int = 8
    mfi_period: int = 10

    ema_fast: ExponentialMA = ExponentialMA(8)
    ema_slow: ExponentialMA = ExponentialMA(21)
    atr: AverageTrueRange = AverageTrueRange(8)
    mfi: MoneyFlowIndex = MoneyFlowIndex(10)
    ha: HeikenAshiState = HeikenAshiState()

    trend_switch: int = 1  # 1 bullish, -1 bearish
    background_trend: int = 0  # 1 bull, -1 bear, 0 neutral
    current_mode: EMode = EMode.None_


class DashboardEngine:
    def __init__(self, state: Optional[DashboardState] = None) -> None:
        self.s = state or DashboardState()

    def on_bar(self, open_: float, high: float, low: float, close: float, volume: float, use_heiken_ashi: bool = True) -> None:
        if use_heiken_ashi:
            ha_open, ha_high, ha_low, ha_close = update_heiken_ashi(self.s.ha, open_, high, low, close)
            src_open, src_high, src_low, src_close = ha_open, ha_high, ha_low, ha_close
        else:
            src_open, src_high, src_low, src_close = open_, high, low, close

        ema_fast = self.s.ema_fast.update(src_close)
        ema_slow = self.s.ema_slow.update(src_close)
        _ = self.s.atr.update(src_high, src_low, src_close)
        _ = self.s.mfi.update(src_high, src_low, src_close, volume)

        up = (src_high + src_low) / 2.0 - (1.3 * self.s.atr.previous_atr)
        dn = (src_high + src_low) / 2.0 + (1.3 * self.s.atr.previous_atr)

        prev_trend_up = getattr(self, "_trend_up_prev", up)
        prev_trend_dn = getattr(self, "_trend_dn_prev", dn)
        trend_up = max(up, prev_trend_up) if src_close > prev_trend_up else up
        trend_dn = min(dn, prev_trend_dn) if src_close < prev_trend_dn else dn
        self._trend_up_prev = trend_up
        self._trend_dn_prev = trend_dn

        self.s.trend_switch = 1 if src_close > prev_trend_dn else (-1 if src_close < prev_trend_up else self.s.trend_switch)
        self.s.background_trend = 1 if self.s.trend_switch == 1 else -1

        if self.s.current_mode == EMode.Buy and close < ema_slow and src_close < ema_slow:
            self.s.current_mode = EMode.None_
        elif self.s.current_mode == EMode.Sell and close > ema_slow and src_close > ema_slow:
            self.s.current_mode = EMode.None_

    def get_trend_state(self) -> int:
        return self.s.background_trend
