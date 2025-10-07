import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional

from .buffers import RingBuffer

@dataclass
class FeatureSnapshot:
    cvd: float
    cvd_slope: float
    depth_imbalance: float
    depth_slope: float
    aggressive_buy_ratio: float
    delta_confidence: float

class FeatureEngine:
    def __init__(self, window: int = 256, weights: Optional[Dict[str, float]] = None) -> None:
        self.buy_volume = RingBuffer(window)
        self.sell_volume = RingBuffer(window)
        self.cvd_series = RingBuffer(window)
        self.depth_imbalance_series = RingBuffer(window)
        self.depth_slope_series = RingBuffer(window)
        self.weights = weights or {
            "cvd_slope": 0.4,
            "depth_imbalance": 0.3,
            "aggressive_buy_ratio": 0.3,
        }
        self._cvd = 0.0

    def update_trades(self, buy_qty: float, sell_qty: float) -> None:
        self.buy_volume.append(buy_qty)
        self.sell_volume.append(sell_qty)
        self._cvd += (buy_qty - sell_qty)
        self.cvd_series.append(self._cvd)

    def update_orderbook(self, bid_qty_levels: np.ndarray, ask_qty_levels: np.ndarray) -> None:
        bid_sum = float(np.sum(bid_qty_levels)) + 1e-9
        ask_sum = float(np.sum(ask_qty_levels)) + 1e-9
        depth_imbalance = (bid_sum - ask_sum) / (bid_sum + ask_sum)
        self.depth_imbalance_series.append(depth_imbalance)

        weights = np.arange(1, len(bid_qty_levels) + 1, dtype=np.float64)
        bid_weighted = float(np.dot(bid_qty_levels, weights))
        ask_weighted = float(np.dot(ask_qty_levels, weights))
        depth_slope = (bid_weighted - ask_weighted) / (bid_weighted + ask_weighted + 1e-9)
        self.depth_slope_series.append(depth_slope)

    def _slope(self, series: RingBuffer) -> float:
        vals = series.values()
        if len(vals) < 2:
            return 0.0
        x = np.arange(len(vals), dtype=np.float64)
        x_mean = np.mean(x)
        y_mean = np.mean(vals)
        num = float(np.dot(x - x_mean, vals - y_mean))
        den = float(np.dot(x - x_mean, x - x_mean)) + 1e-9
        return num / den

    def snapshot(self) -> FeatureSnapshot:
        cvd_slope = self._slope(self.cvd_series)
        depth_imbalance = (self.depth_imbalance_series.values()[-1] if self.depth_imbalance_series.size else 0.0)
        depth_slope = (self.depth_slope_series.values()[-1] if self.depth_slope_series.size else 0.0)
        buys = self.buy_volume.values()
        sells = self.sell_volume.values()
        total_buys = float(np.sum(buys))
        total_sells = float(np.sum(sells))
        aggressive_buy_ratio = total_buys / (total_buys + total_sells + 1e-9)

        def squash(x: float) -> float:
            return 1.0 / (1.0 + np.exp(-x))

        w = self.weights
        score = (
            w["cvd_slope"] * (squash(cvd_slope) - 0.5) * 2.0 +
            w["depth_imbalance"] * depth_imbalance +
            w["aggressive_buy_ratio"] * (aggressive_buy_ratio - 0.5) * 2.0
        )
        delta_confidence = max(0.0, min(1.0, 0.5 * (score + 1.0)))

        return FeatureSnapshot(
            cvd=self._cvd,
            cvd_slope=cvd_slope,
            depth_imbalance=depth_imbalance,
            depth_slope=depth_slope,
            aggressive_buy_ratio=aggressive_buy_ratio,
            delta_confidence=delta_confidence,
        )
