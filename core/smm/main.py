from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.features import FeatureSnapshot
from core.signals import SignalDecision
from .common import ExponentialMA, AverageTrueRange, MoneyFlowIndex, HeikenAshiState, update_heiken_ashi


@dataclass
class SMMDecision:
    side: Optional[str]
    delta_confidence: float
    ema21: float
    ema21_slope: float
    reason: str
    # Extended diagnostics
    ema8: float = 0.0
    ema13: float = 0.0
    ema55: float = 0.0
    ema55_slope: float = 0.0
    trend_bullish: bool = False
    trend_bearish: bool = False
    mfi: float = float("nan")
    di_plus: float = 0.0
    di_minus: float = 0.0
    strong_bull: bool = False
    strong_bear: bool = False


class SMMMainEngine:
    def __init__(
        self,
        ema_period: int = 21,
        delta_threshold: float = 0.6,
        ema_fast_period: int = 8,
        ema_med_period: int = 13,
        ema_trend_period: int = 55,  # EMA55 for trend filtering
        atr_period: int = 8,
        mfi_period: int = 10,
        ma_filter_period: int = 10,
        use_ma_filter: bool = True,
        use_heiken_ashi: bool = True,
    ) -> None:
        # Core filters
        self.ema21 = ExponentialMA(ema_period)
        self.ema8 = ExponentialMA(ema_fast_period)
        self.ema13 = ExponentialMA(ema_med_period)
        self.ema55 = ExponentialMA(ema_trend_period)  # EMA55 for trend filtering
        self.atr = AverageTrueRange(atr_period)
        self.mfi = MoneyFlowIndex(mfi_period)
        self.ha_state = HeikenAshiState()
        self.use_heiken_ashi = use_heiken_ashi
        self.delta_threshold = float(delta_threshold)
        self.ma_filter_period = ma_filter_period
        self.use_ma_filter = use_ma_filter
        # Rolling prev bars for DI approximation
        self.prev_high: Optional[float] = None
        self.prev_low: Optional[float] = None
        self.prev_close: Optional[float] = None

    def _di_approx(self, high: float, low: float, prev_high: float, prev_low: float) -> tuple[float, float]:
        di_plus_calc = max(high - prev_high, 0.0) if (high - prev_high) > (prev_low - low) else 0.0
        di_minus_calc = max(prev_low - low, 0.0) if (prev_low - low) > (high - prev_high) else 0.0
        true_range = max(high - low, abs(high - (self.prev_close or high)), abs(low - (self.prev_close or low)))
        if true_range <= 0.0:
            return 0.0, 0.0
        di_plus = 100.0 * (di_plus_calc / true_range)
        di_minus = 100.0 * (di_minus_calc / true_range)
        return di_plus, di_minus

    def on_bar(self, open_: float, high: float, low: float, close: float, volume: float) -> None:
        if self.use_heiken_ashi:
            ha_open, ha_high, ha_low, ha_close = update_heiken_ashi(self.ha_state, open_, high, low, close)
            src_o, src_h, src_l, src_c = ha_open, ha_high, ha_low, ha_close
        else:
            src_o, src_h, src_l, src_c = open_, high, low, close

        # Update indicators
        _ = self.ema8.update(src_c)
        _ = self.ema13.update(src_c)
        _ema21 = self.ema21.update(src_c)
        _ema55 = self.ema55.update(src_c)  # Update EMA55 for trend filtering
        _ = self.atr.update(src_h, src_l, src_c)
        _ = self.mfi.update(src_h, src_l, src_c, volume)

        # Maintain prev H/L/C for DI calc
        if self.prev_high is None:
            self.prev_high, self.prev_low, self.prev_close = src_h, src_l, src_c
            return
        di_plus, di_minus = self._di_approx(src_h, src_l, self.prev_high, self.prev_low)
        # Stash for later evaluate use
        self._last_di_plus = di_plus
        self._last_di_minus = di_minus
        self.prev_high, self.prev_low, self.prev_close = src_h, src_l, src_c

    def evaluate(self, last_price: float, features: FeatureSnapshot) -> SMMDecision:
        # Use last known indicator states; update EMAs with last price for slope
        ema21_val = self.ema21.update(last_price)
        ema21_slope = self.ema21.constant1 * (last_price - ema21_val)

        ema8_val = self.ema8.previous_ema if self.ema8.previous_ema is not None else last_price
        ema13_val = self.ema13.previous_ema if self.ema13.previous_ema is not None else last_price
        ema55_val = self.ema55.previous_ema if self.ema55.previous_ema is not None else last_price
        di_plus = getattr(self, "_last_di_plus", 0.0)
        di_minus = getattr(self, "_last_di_minus", 0.0)
        mfi_val = self.mfi.current_value

        # Strong candle heuristics relative to EMAs (using last HA if enabled)
        src_open = self.ha_state.open if (self.use_heiken_ashi and self.ha_state.open is not None) else last_price
        src_low = self.ha_state.low if (self.use_heiken_ashi and self.ha_state.low is not None) else last_price
        src_high = self.ha_state.high if (self.use_heiken_ashi and self.ha_state.high is not None) else last_price
        strong_bull = (last_price > src_open) and (src_open == src_low) and (last_price > ema8_val) and (last_price > ema21_val)
        strong_bear = (last_price < src_open) and (src_open == src_high) and (last_price < ema8_val) and (last_price < ema21_val)

        # EMA55 trend filtering (matches NinjaTrader SMM)
        ema55_slope = self.ema55.constant1 * (last_price - ema55_val)
        trend_bullish = last_price > ema21_val and ema21_slope >= 0.0 and last_price > ema55_val and ema55_slope >= 0.0
        trend_bearish = last_price < ema21_val and ema21_slope <= 0.0 and last_price < ema55_val and ema55_slope <= 0.0
        
        allow_long = trend_bullish
        allow_short = trend_bearish

        # Chop filter via DI and MFI thresholds (close to C# logic)
        can_buy = (di_plus > di_minus and di_plus >= 45.0)
        can_sell = (di_minus > di_plus and di_minus >= 45.0)
        mfi_buy = (mfi_val > 52.0) if mfi_val == mfi_val else True  # NaN-safe
        mfi_sell = (mfi_val < 48.0) if mfi_val == mfi_val else True

        # Optional MA filter: price above/below EMA13 (as a proxy for C# configurable MA)
        ma_buy_ok = True
        ma_sell_ok = True
        if self.use_ma_filter:
            ma_buy_ok = last_price > ema13_val
            ma_sell_ok = last_price < ema13_val

        side: Optional[str] = None
        reason = "hold"

        # Primary SMM signal conditions
        buy_con = allow_long and strong_bull and can_buy and mfi_buy and ma_buy_ok
        sell_con = allow_short and strong_bear and can_sell and mfi_sell and ma_sell_ok

        # Add delta confirmation
        if buy_con and features.delta_confidence >= self.delta_threshold:
            side, reason = "BUY", "SMM+delta>=thr"
        elif sell_con and (1.0 - features.delta_confidence) >= self.delta_threshold:
            side, reason = "SELL", "SMM+delta<=1-thr"

        return SMMDecision(
            side=side,
            delta_confidence=features.delta_confidence,
            ema21=ema21_val,
            ema21_slope=ema21_slope,
            reason=reason,
            ema8=ema8_val,
            ema13=ema13_val,
            ema55=ema55_val,
            ema55_slope=ema55_slope,
            trend_bullish=trend_bullish,
            trend_bearish=trend_bearish,
            mfi=mfi_val,
            di_plus=di_plus,
            di_minus=di_minus,
            strong_bull=strong_bull,
            strong_bear=strong_bear,
        )
