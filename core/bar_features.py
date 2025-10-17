"""
Bar-based feature calculation for SMM strategy
Calculates delta confidence and other features based on completed bars rather than ticks
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, List
from collections import deque


@dataclass
class BarData:
    """Single bar data"""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0


@dataclass
class BarFeatureSnapshot:
    """Feature snapshot calculated from bars"""
    cvd: float
    cvd_slope: float
    depth_imbalance: float
    depth_slope: float
    aggressive_buy_ratio: float
    delta_confidence: float
    # Bar-based features
    bar_count: int
    avg_bar_size: float
    volume_trend: float
    price_momentum: float


class BarFeatureEngine:
    """Feature engine that calculates metrics from completed bars"""
    
    def __init__(self, window: int = 20) -> None:
        self.window = window
        self.bars: deque = deque(maxlen=window)
        self.cvd_series: deque = deque(maxlen=window)
        self.volume_series: deque = deque(maxlen=window)
        self.price_series: deque = deque(maxlen=window)
        self._cvd = 0.0
        
    def add_bar(self, bar: BarData) -> None:
        """Add a completed bar and update features"""
        self.bars.append(bar)
        
        # Update CVD (Cumulative Volume Delta)
        delta = bar.buy_volume - bar.sell_volume
        self._cvd += delta
        self.cvd_series.append(self._cvd)
        
        # Update series
        self.volume_series.append(bar.volume)
        self.price_series.append(bar.close)
        
    def _calculate_slope(self, series: List[float]) -> float:
        """Calculate slope of a series"""
        if len(series) < 2:
            return 0.0
        
        x = np.arange(len(series), dtype=np.float64)
        y = np.array(series, dtype=np.float64)
        
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        
        numerator = np.dot(x - x_mean, y - y_mean)
        denominator = np.dot(x - x_mean, x - x_mean)
        
        if denominator == 0:
            return 0.0
            
        return float(numerator / denominator)
    
    def _calculate_momentum(self, series: List[float], periods: int = 5) -> float:
        """Calculate momentum over specified periods"""
        if len(series) < periods:
            return 0.0
            
        recent = series[-periods:]
        return float((recent[-1] - recent[0]) / recent[0]) if recent[0] != 0 else 0.0
    
    def snapshot(self) -> BarFeatureSnapshot:
        """Calculate feature snapshot from bars"""
        if len(self.bars) < 2:
            return BarFeatureSnapshot(
                cvd=0.0, cvd_slope=0.0, depth_imbalance=0.0, depth_slope=0.0,
                aggressive_buy_ratio=0.5, delta_confidence=0.5, bar_count=0,
                avg_bar_size=0.0, volume_trend=0.0, price_momentum=0.0
            )
        
        # Calculate CVD slope
        cvd_slope = self._calculate_slope(list(self.cvd_series))
        
        # Calculate volume trend
        volume_trend = self._calculate_slope(list(self.volume_series))
        
        # Calculate price momentum
        price_momentum = self._calculate_momentum(list(self.price_series))
        
        # Calculate aggressive buy ratio from recent bars
        recent_bars = list(self.bars)[-10:]  # Last 10 bars
        total_buy_volume = sum(bar.buy_volume for bar in recent_bars)
        total_sell_volume = sum(bar.sell_volume for bar in recent_bars)
        total_volume = total_buy_volume + total_sell_volume
        
        aggressive_buy_ratio = total_buy_volume / total_volume if total_volume > 0 else 0.5
        
        # Calculate average bar size
        bar_sizes = [bar.high - bar.low for bar in self.bars]
        avg_bar_size = np.mean(bar_sizes) if bar_sizes else 0.0
        
        # Calculate delta confidence using bar-based features
        # Weight the factors based on bar characteristics
        cvd_factor = np.tanh(cvd_slope * 0.01)  # Normalize CVD slope
        volume_factor = np.tanh(volume_trend * 0.1)  # Normalize volume trend
        buy_ratio_factor = (aggressive_buy_ratio - 0.5) * 2.0  # Convert to -1 to 1
        
        # Combine factors with weights
        weights = {
            "cvd_slope": 0.4,
            "volume_trend": 0.3,
            "buy_ratio": 0.3
        }
        
        score = (
            weights["cvd_slope"] * cvd_factor +
            weights["volume_trend"] * volume_factor +
            weights["buy_ratio"] * buy_ratio_factor
        )
        
        # Convert to 0-1 confidence scale
        delta_confidence = max(0.0, min(1.0, 0.5 * (score + 1.0)))
        
        return BarFeatureSnapshot(
            cvd=self._cvd,
            cvd_slope=cvd_slope,
            depth_imbalance=0.0,  # Not applicable for bar-based
            depth_slope=0.0,      # Not applicable for bar-based
            aggressive_buy_ratio=aggressive_buy_ratio,
            delta_confidence=delta_confidence,
            bar_count=len(self.bars),
            avg_bar_size=avg_bar_size,
            volume_trend=volume_trend,
            price_momentum=price_momentum
        )
    
    def get_recent_bars(self, count: int = 5) -> List[BarData]:
        """Get recent bars for analysis"""
        return list(self.bars)[-count:] if len(self.bars) >= count else list(self.bars)
    
    def is_ready(self) -> bool:
        """Check if engine has enough data for reliable calculations"""
        return len(self.bars) >= 5  # Need at least 5 bars
