from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.features import FeatureSnapshot
from core.signals import SignalDecision
from .common import ExponentialMA


@dataclass
class SMMDecision:
    side: Optional[str]
    delta_confidence: float
    ema21: float
    ema21_slope: float
    reason: str


class SMMMainEngine:
    def __init__(self, ema_period: int = 21, delta_threshold: float = 0.6) -> None:
        self.ema = ExponentialMA(ema_period)
        self.delta_threshold = float(delta_threshold)

    def evaluate(self, last_price: float, features: FeatureSnapshot) -> SMMDecision:
        ema_val = self.ema.update(last_price)
        ema_slope = self.ema.constant1 * (last_price - ema_val)  # lightweight slope proxy

        allow_long = last_price > ema_val and ema_slope >= 0.0
        allow_short = last_price < ema_val and ema_slope <= 0.0

        side: Optional[str] = None
        reason = "hold"
        if features.delta_confidence >= self.delta_threshold and allow_long:
            side, reason = "BUY", "delta>=thr & trend_up"
        elif (1.0 - features.delta_confidence) >= self.delta_threshold and allow_short:
            side, reason = "SELL", "delta<=1-thr & trend_dn"

        return SMMDecision(
            side=side,
            delta_confidence=features.delta_confidence,
            ema21=ema_val,
            ema21_slope=ema_slope,
            reason=reason,
        )
