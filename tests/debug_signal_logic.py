#!/usr/bin/env python3
"""
Debug Signal Logic
Debug why signals are not being generated despite good delta confidence
"""

import sys
import numpy as np
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.smm.main import SMMMainEngine
from core.smm.combined import SMMCombinedSignal
from core.bar_features import BarFeatureEngine, BarData
from core.features import FeatureSnapshot


class SignalDebugger:
    """Debug signal generation logic"""
    
    def __init__(self):
        self.smm_engine = SMMMainEngine(
            ema_period=21,
            ema_trend_period=55,
            delta_threshold=0.65,
            ema_fast_period=8,
            ema_med_period=13,
            atr_period=8,
            mfi_period=10
        )
        self.combined_signal = SMMCombinedSignal(delta_threshold=0.65)
        self.bar_features = BarFeatureEngine(window=20)
        
    def debug_single_bar(self, bar_data: dict):
        """Debug signal generation for a single bar"""
        print(f"\nDebugging Bar: {bar_data}")
        
        # Convert to BarData
        bar = BarData(
            timestamp=bar_data["timestamp"],
            open=bar_data["open"],
            high=bar_data["high"],
            low=bar_data["low"],
            close=bar_data["close"],
            volume=bar_data["volume"],
            buy_volume=bar_data["buy_volume"],
            sell_volume=bar_data["sell_volume"]
        )
        
        # Add to feature engine
        self.bar_features.add_bar(bar)
        
        # Update SMM engine
        self.smm_engine.on_bar(bar.open, bar.high, bar.low, bar.close, bar.volume)
        
        # Check if feature engine is ready
        print(f"Feature engine ready: {self.bar_features.is_ready()}")
        print(f"Bars in feature engine: {len(self.bar_features.bars)}")
        
        if self.bar_features.is_ready():
            bar_snap = self.bar_features.snapshot()
            print(f"Bar snapshot: {bar_snap}")
            
            # Create feature snapshot for SMM
            features = FeatureSnapshot(
                cvd=bar_snap.cvd,
                cvd_slope=bar_snap.cvd_slope,
                depth_imbalance=bar_snap.depth_imbalance,
                depth_slope=bar_snap.depth_slope,
                aggressive_buy_ratio=bar_snap.aggressive_buy_ratio,
                delta_confidence=bar_snap.delta_confidence
            )
            
            print(f"Features: {features}")
            
            # Update combined signal with bar data first
            self.combined_signal.on_bar(bar.open, bar.high, bar.low, bar.close, bar.volume)
            
            # Evaluate SMM decision
            smm_decision = self.smm_engine.evaluate(bar.close, features)
            print(f"SMM Decision: {smm_decision}")
            
            # Evaluate combined decision
            combined_decision = self.combined_signal.evaluate(bar.close, features)
            print(f"Combined Decision: {combined_decision}")
            
            # Debug each condition
            self.debug_smm_conditions(bar.close, features, smm_decision)
            
            return combined_decision
        else:
            print("Feature engine not ready - need more bars")
            return None
    
    def debug_smm_conditions(self, price: float, features: FeatureSnapshot, smm_decision):
        """Debug SMM signal conditions"""
        print(f"\nSMM Conditions Debug:")
        print(f"Price: {price}")
        print(f"Delta Confidence: {features.delta_confidence}")
        print(f"Delta Threshold: {self.smm_engine.delta_threshold}")
        
        # Check trend conditions
        print(f"Trend Bullish: {smm_decision.trend_bullish}")
        print(f"Trend Bearish: {smm_decision.trend_bearish}")
        print(f"EMA21: {smm_decision.ema21}")
        print(f"EMA55: {smm_decision.ema55}")
        print(f"EMA21 Slope: {smm_decision.ema21_slope}")
        print(f"EMA55 Slope: {smm_decision.ema55_slope}")
        
        # Check strong candle conditions
        print(f"Strong Bull: {smm_decision.strong_bull}")
        print(f"Strong Bear: {smm_decision.strong_bear}")
        
        # Check chop filters
        print(f"DI Plus: {smm_decision.di_plus}")
        print(f"DI Minus: {smm_decision.di_minus}")
        print(f"MFI: {smm_decision.mfi}")
        
        # Check signal conditions
        print(f"SMM Side: {smm_decision.side}")
        print(f"SMM Reason: {smm_decision.reason}")
        
        # Check if delta confidence meets threshold
        delta_meets_threshold = features.delta_confidence >= self.smm_engine.delta_threshold
        print(f"Delta meets threshold: {delta_meets_threshold}")
        
        # Check combined conditions
        if smm_decision.side == "BUY":
            print("BUY signal conditions:")
            print(f"  Trend bullish: {smm_decision.trend_bullish}")
            print(f"  Strong bull: {smm_decision.strong_bull}")
            print(f"  Delta confidence >= threshold: {delta_meets_threshold}")
        elif smm_decision.side == "SELL":
            print("SELL signal conditions:")
            print(f"  Trend bearish: {smm_decision.trend_bearish}")
            print(f"  Strong bear: {smm_decision.strong_bear}")
            print(f"  (1 - delta confidence) >= threshold: {(1.0 - features.delta_confidence) >= self.smm_engine.delta_threshold}")
        else:
            print("No signal - checking why:")
            print(f"  Trend bullish: {smm_decision.trend_bullish}")
            print(f"  Trend bearish: {smm_decision.trend_bearish}")
            print(f"  Strong bull: {smm_decision.strong_bull}")
            print(f"  Strong bear: {smm_decision.strong_bear}")
            print(f"  Delta confidence: {features.delta_confidence}")
            print(f"  Delta threshold: {self.smm_engine.delta_threshold}")
    
    def run_debug_test(self):
        """Run debug test with realistic data"""
        print("Running Signal Generation Debug Test...")
        
        # Generate realistic bullish bar
        bullish_bar = {
            "timestamp": time.time(),
            "open": 25000.0,
            "high": 25010.0,
            "low": 24995.0,
            "close": 25005.0,
            "volume": 500.0,
            "buy_volume": 350.0,  # 70% buy volume
            "sell_volume": 150.0
        }
        
        # Generate multiple bars to build up data
        bars = []
        base_price = 25000.0
        
        for i in range(25):  # Generate 25 bars
            # Create bullish trend
            open_price = base_price + i * 2
            high_price = open_price + 5
            low_price = open_price - 2
            close_price = open_price + 3
            
            bar = {
                "timestamp": time.time() + i * 60,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 500.0,
                "buy_volume": 350.0,  # 70% buy volume
                "sell_volume": 150.0
            }
            
            bars.append(bar)
            base_price = close_price
        
        # Debug each bar
        for i, bar in enumerate(bars):
            print(f"\n{'='*50}")
            print(f"Debugging Bar {i+1}/{len(bars)}")
            print(f"{'='*50}")
            
            result = self.debug_single_bar(bar)
            
            if result and result.side:
                print(f"✅ Signal generated: {result.side} at {bar['close']}")
                break
            elif i == len(bars) - 1:
                print("❌ No signals generated after all bars")
        
        return bars


def main():
    """Run signal generation debug"""
    debugger = SignalDebugger()
    bars = debugger.run_debug_test()
    
    return bars


if __name__ == "__main__":
    main()
