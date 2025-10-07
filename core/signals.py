from dataclasses import dataclass
from typing import Optional

from .buffers import Ema
from .features import FeatureSnapshot

@dataclass
class SignalDecision:
    side: Optional[str]
    delta_confidence: float
    ema: float
    ema_slope: float

class SignalEngine:
    def __init__(self, ema_period: int = 21, delta_threshold: float = 0.6) -> None:
        self.ema = Ema(ema_period)
        self.delta_threshold = delta_threshold

    def on_price_and_features(self, last_price: float, features: FeatureSnapshot) -> SignalDecision:
        ema_val = self.ema.update(last_price)
        ema_slope = self.ema.slope()
        allowed_long = last_price > ema_val and ema_slope >= 0.0
        allowed_short = last_price < ema_val and ema_slope <= 0.0
        side: Optional[str] = None
        if features.delta_confidence >= self.delta_threshold and allowed_long:
            side = "BUY"
        elif (1.0 - features.delta_confidence) >= self.delta_threshold and allowed_short:
            side = "SELL"
        return SignalDecision(side=side, delta_confidence=features.delta_confidence, ema=ema_val, ema_slope=ema_slope)
