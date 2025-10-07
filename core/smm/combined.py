from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
        self.main = SMMMainEngine(delta_threshold=delta_threshold)

    def on_bar(self, open_: float, high: float, low: float, close: float, volume: float) -> None:
        # Update dashboard trend state (Heiken Ashi, ATR, MAs)
        self.dashboard.on_bar(open_, high, low, close, volume, use_heiken_ashi=True)

    def evaluate(self, last_price: float, features: FeatureSnapshot) -> CombinedDecision:
        main_decision = self.main.evaluate(last_price, features)
        trend_state = self.dashboard.get_trend_state()
        final_side: Optional[str] = None
        reason = "hold"

        if main_decision.side == "BUY" and trend_state == 1:
            final_side, reason = "BUY", "main_buy & trend_bull"
        elif main_decision.side == "SELL" and trend_state == -1:
            final_side, reason = "SELL", "main_sell & trend_bear"

        return CombinedDecision(side=final_side, reason=reason, main=main_decision, trend_state=trend_state)
