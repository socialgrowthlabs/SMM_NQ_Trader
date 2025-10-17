from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import time
import os

from core.features import FeatureSnapshot
from .dashboard import DashboardEngine
from .main import SMMMainEngine, SMMDecision


@dataclass
class CombinedDecision:
    side: Optional[str]
    reason: str
    main: SMMDecision
    trend_state: int


class SMMCombinedSignal:
    def __init__(self, delta_threshold: float = 0.6) -> None:
        self.dashboard = DashboardEngine()
        # Allow env override for delta threshold
        env_thr = os.getenv("DELTA_CONFIDENCE_THRESHOLD")
        try:
            delta_thr_final = float(env_thr) if env_thr is not None else float(delta_threshold)
        except Exception:
            delta_thr_final = float(delta_threshold)
        self.main = SMMMainEngine(delta_threshold=delta_thr_final)
        self._armed: Optional[int] = None  # 1 buy, -1 sell
        # Cross-source confirmation memory
        self._confirm_side_by_source: dict[str, Optional[str]] = {}
        self._confirm_ts_by_source: dict[str, float] = {}
        self._confirm_window_secs: float = 10.0
        # Testing and gating flags (env tunable)
        self.require_cross_source: bool = os.getenv("REQUIRE_XSOURCE", "1") not in ("0", "false", "False")
        self.testing_loose: bool = os.getenv("TESTING_LOOSE", "0") in ("1", "true", "True")
        self.testing_sell_bias: bool = os.getenv("TESTING_SELL_BIAS", "0") in ("1", "true", "True")
        # Optional trend override source: None or 'ema21'
        self.trend_override: Optional[str] = os.getenv("TREND_OVERRIDE") or None

    def on_bar(self, open_: float, high: float, low: float, close: float, volume: float) -> None:
        # Update dashboard trend state (Heiken Ashi, ATR, MAs)
        self.dashboard.on_bar(open_, high, low, close, volume, use_heiken_ashi=True)
        self.main.on_bar(open_, high, low, close, volume)

    def on_bar_source(self, source: str, open_: float, high: float, low: float, close: float, volume: float) -> None:
        """Record per-source confirmation using strong-candle + EMA21 alignment.

        The goal is to support mixed bars (1m, ticks, TBars) and require
        same-direction confirmation within a short time window.
        """
        self.on_bar(open_, high, low, close, volume)
        # Use latest internal EMAs from main
        ema21_val = getattr(self.main.ema21, "previous_ema", close) or close
        ema8_val = getattr(self.main.ema8, "previous_ema", close) or close
        strong_bull = (close > open_) and (low == open_) and (close > ema8_val) and (close > ema21_val)
        strong_bear = (close < open_) and (high == open_) and (close < ema8_val) and (close < ema21_val)
        side: Optional[str] = None
        if strong_bull:
            side = "BUY"
        elif strong_bear:
            side = "SELL"
        # Record confirmation state
        self._confirm_side_by_source[source] = side
        self._confirm_ts_by_source[source] = time.time()

    def evaluate(self, last_price: float, features: FeatureSnapshot) -> CombinedDecision:
        main_decision = self.main.evaluate(last_price, features)
        # EMA55 trend filtering (matches NinjaTrader SMM)
        ema21_val = main_decision.ema21
        ema21_slope = main_decision.ema21_slope
        ema55_val = main_decision.ema55
        ema55_slope = main_decision.ema55_slope
        
        # Use EMA55 trend filtering for primary trend determination
        # No background bands needed - this is signal calculation only
        trend_state = 1 if main_decision.trend_bullish else (-1 if main_decision.trend_bearish else 0)
        final_side: Optional[str] = None
        reason = "hold"

        # Testing mode: relax gating to exercise signal generation quickly
        if self.testing_loose:
            if features.delta_confidence >= self.main.delta_threshold and trend_state == 1:
                return CombinedDecision(side="BUY", reason="test_loose_delta_trend", main=main_decision, trend_state=trend_state)
            if (1.0 - features.delta_confidence) >= self.main.delta_threshold and trend_state == -1:
                return CombinedDecision(side="SELL", reason="test_loose_delta_trend", main=main_decision, trend_state=trend_state)

        # Testing SELL bias: prefer SELLs when background trend is bearish
        if self.testing_sell_bias and trend_state == -1:
            return CombinedDecision(side="SELL", reason="test_sell_bias", main=main_decision, trend_state=trend_state)

        # Prefer main decision if its side agrees with EMA21 trend; otherwise hold
        if main_decision.side == "BUY":
            if trend_state == 1:
                final_side, reason = "BUY", main_decision.reason or "main_buy"
            else:
                reason = "trend_mismatch"
        elif main_decision.side == "SELL":
            if trend_state == -1:
                final_side, reason = "SELL", main_decision.reason or "main_sell"
            else:
                reason = "trend_mismatch"
        else:
            # Fallback gating: delta + trend arms
            if features.delta_confidence >= self.main.delta_threshold and trend_state == 1:
                self._armed = 1
                reason = "armed_buy"
            elif (1.0 - features.delta_confidence) >= self.main.delta_threshold and trend_state == -1:
                self._armed = -1
                reason = "armed_sell"

        # Confirm armed state only when main shows strong candle alignment
        if final_side is None and self._armed is not None:
            if self._armed == 1 and main_decision.strong_bull and trend_state == 1:
                final_side, reason = "BUY", "armed+confirm"
                self._armed = None
            elif self._armed == -1 and main_decision.strong_bear and trend_state == -1:
                final_side, reason = "SELL", "armed+confirm"
                self._armed = None

        # Multi-source confirmation: require recent matching side from TBars12
        # or majority of other sources within window. If no sources recorded yet,
        # skip the cross-source requirement (e.g., unit tests / startup).
        if final_side is not None and self.require_cross_source and len(self._confirm_ts_by_source) > 0:
            now = time.time()
            def recent(source: str, side: str) -> bool:
                s = self._confirm_side_by_source.get(source)
                ts = self._confirm_ts_by_source.get(source, 0.0)
                return (s == side) and ((now - ts) <= self._confirm_window_secs)

            if len(self._confirm_ts_by_source) > 0:
                primary_ok = recent("tbar12", final_side)
                others = [recent("time1m", final_side), recent("ticks233", final_side)]
                majority_ok = sum(1 for x in others if x) >= 1
                if not (primary_ok or majority_ok):
                    # Not enough cross-source confirmation; hold
                    final_side, reason = None, "await_xsource_confirm"

        # Secondary check: if dashboard background trend disagrees with EMA21 trend, hold until aligned
        dash_trend = self.dashboard.get_trend_state()
        if final_side is not None and dash_trend in (-1, 1) and dash_trend != trend_state:
            final_side, reason = None, "dash_trend_mismatch"

        return CombinedDecision(side=final_side, reason=reason, main=main_decision, trend_state=trend_state)
