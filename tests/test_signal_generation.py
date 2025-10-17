#!/usr/bin/env python3
"""
Focused Signal Generation Test
Tests signal generation with sufficient data and proper bar aggregation
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
from core.bars import BarAggregator


class SignalGenerationTester:
    """Focused signal generation tester"""
    
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
        self.bars_1m = BarAggregator(mode="time", duration_sec=60)
        
    def generate_realistic_bars(self, count: int, trend: str = "bullish") -> list:
        """Generate realistic bar data with proper OHLC relationships"""
        bars = []
        base_price = 25000.0
        current_price = base_price
        
        for i in range(count):
            # Generate realistic OHLC
            if trend == "bullish":
                # Bullish bar: close > open, high > close, low < open
                open_price = current_price
                low_price = current_price - np.random.uniform(0.5, 2.0)
                high_price = current_price + np.random.uniform(1.0, 3.0)
                close_price = current_price + np.random.uniform(0.5, 2.0)
            elif trend == "bearish":
                # Bearish bar: close < open, high < open, low < close
                open_price = current_price
                high_price = current_price + np.random.uniform(0.1, 0.5)
                low_price = current_price - np.random.uniform(1.0, 3.0)
                close_price = current_price - np.random.uniform(0.5, 2.0)
            else:  # sideways
                # Sideways bar: close ≈ open
                open_price = current_price
                high_price = current_price + np.random.uniform(0.5, 1.5)
                low_price = current_price - np.random.uniform(0.5, 1.5)
                close_price = current_price + np.random.uniform(-0.5, 0.5)
            
            # Generate volume with trend bias
            if trend == "bullish":
                buy_volume = np.random.uniform(60, 80)  # 60-80% buy volume
            elif trend == "bearish":
                buy_volume = np.random.uniform(20, 40)  # 20-40% buy volume
            else:
                buy_volume = np.random.uniform(40, 60)  # 40-60% buy volume
            
            total_volume = np.random.uniform(100, 1000)
            buy_volume = total_volume * (buy_volume / 100)
            sell_volume = total_volume - buy_volume
            
            bar = {
                "timestamp": time.time() + i * 60,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": total_volume,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume
            }
            
            bars.append(bar)
            current_price = close_price
            
        return bars
    
    def test_signal_generation_with_data(self, bars: list) -> dict:
        """Test signal generation with sufficient data"""
        results = {
            "total_bars": len(bars),
            "signals_generated": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "signal_details": [],
            "delta_confidence_scores": [],
            "trend_alignment_count": 0,
            "ema55_alignment_count": 0
        }
        
        for i, bar in enumerate(bars):
            # Convert to BarData
            bar_data = BarData(
                timestamp=bar["timestamp"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
                buy_volume=bar["buy_volume"],
                sell_volume=bar["sell_volume"]
            )
            
            # Add to feature engine
            self.bar_features.add_bar(bar_data)
            
            # Update SMM engine and combined signal
            self.smm_engine.on_bar(bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
            self.combined_signal.on_bar(bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])
            
            # Generate signal if enough data
            if self.bar_features.is_ready():
                bar_snap = self.bar_features.snapshot()
                
                # Create feature snapshot for SMM
                features = FeatureSnapshot(
                    cvd=bar_snap.cvd,
                    cvd_slope=bar_snap.cvd_slope,
                    depth_imbalance=bar_snap.depth_imbalance,
                    depth_slope=bar_snap.depth_slope,
                    aggressive_buy_ratio=bar_snap.aggressive_buy_ratio,
                    delta_confidence=bar_snap.delta_confidence
                )
                
                # Evaluate signal
                smm_decision = self.smm_engine.evaluate(bar["close"], features)
                combined_decision = self.combined_signal.evaluate(bar["close"], features)
                
                # Track delta confidence
                results["delta_confidence_scores"].append(bar_snap.delta_confidence)
                
                if combined_decision.side:
                    results["signals_generated"] += 1
                    
                    signal_detail = {
                        "bar_index": i,
                        "side": combined_decision.side,
                        "price": bar["close"],
                        "delta_confidence": bar_snap.delta_confidence,
                        "reason": combined_decision.reason,
                        "trend_bullish": smm_decision.trend_bullish,
                        "trend_bearish": smm_decision.trend_bearish,
                        "ema21": smm_decision.ema21,
                        "ema55": smm_decision.ema55,
                        "ema21_slope": smm_decision.ema21_slope,
                        "ema55_slope": smm_decision.ema55_slope
                    }
                    
                    results["signal_details"].append(signal_detail)
                    
                    if combined_decision.side == "BUY":
                        results["buy_signals"] += 1
                        if smm_decision.trend_bullish:
                            results["trend_alignment_count"] += 1
                    else:
                        results["sell_signals"] += 1
                        if smm_decision.trend_bearish:
                            results["trend_alignment_count"] += 1
                    
                    # Check EMA55 alignment
                    if smm_decision.ema55 > 0:  # EMA55 is initialized
                        if (combined_decision.side == "BUY" and bar["close"] > smm_decision.ema55) or \
                           (combined_decision.side == "SELL" and bar["close"] < smm_decision.ema55):
                            results["ema55_alignment_count"] += 1
        
        return results
    
    def run_focused_test(self):
        """Run focused signal generation test"""
        print("Running Focused Signal Generation Test...")
        
        # Test 1: Bullish trend
        print("\n1. Testing Bullish Trend (100 bars)...")
        bullish_bars = self.generate_realistic_bars(100, "bullish")
        bullish_results = self.test_signal_generation_with_data(bullish_bars)
        
        # Test 2: Bearish trend
        print("2. Testing Bearish Trend (100 bars)...")
        bearish_bars = self.generate_realistic_bars(100, "bearish")
        bearish_results = self.test_signal_generation_with_data(bearish_bars)
        
        # Test 3: Sideways trend
        print("3. Testing Sideways Trend (100 bars)...")
        sideways_bars = self.generate_realistic_bars(100, "sideways")
        sideways_results = self.test_signal_generation_with_data(sideways_bars)
        
        # Compile results
        all_results = {
            "bullish": bullish_results,
            "bearish": bearish_results,
            "sideways": sideways_results,
            "summary": {
                "total_signals": bullish_results["signals_generated"] + bearish_results["signals_generated"] + sideways_results["signals_generated"],
                "total_buy_signals": bullish_results["buy_signals"] + bearish_results["buy_signals"] + sideways_results["buy_signals"],
                "total_sell_signals": bullish_results["sell_signals"] + bearish_results["sell_signals"] + sideways_results["sell_signals"],
                "avg_delta_confidence": np.mean(
                    bullish_results["delta_confidence_scores"] + 
                    bearish_results["delta_confidence_scores"] + 
                    sideways_results["delta_confidence_scores"]
                ),
                "trend_alignment_rate": (
                    bullish_results["trend_alignment_count"] + 
                    bearish_results["trend_alignment_count"] + 
                    sideways_results["trend_alignment_count"]
                ) / max(1, bullish_results["signals_generated"] + bearish_results["signals_generated"] + sideways_results["signals_generated"]),
                "ema55_alignment_rate": (
                    bullish_results["ema55_alignment_count"] + 
                    bearish_results["ema55_alignment_count"] + 
                    sideways_results["ema55_alignment_count"]
                ) / max(1, bullish_results["signals_generated"] + bearish_results["signals_generated"] + sideways_results["signals_generated"])
            }
        }
        
        return all_results
    
    def print_focused_results(self, results: dict):
        """Print focused test results"""
        print("\n" + "="*60)
        print("FOCUSED SIGNAL GENERATION TEST RESULTS")
        print("="*60)
        
        # Individual trend results
        for trend, data in results.items():
            if trend == "summary":
                continue
                
            print(f"\n{trend.upper()} TREND:")
            print(f"  Total Bars: {data['total_bars']}")
            print(f"  Signals Generated: {data['signals_generated']}")
            print(f"  Buy Signals: {data['buy_signals']}")
            print(f"  Sell Signals: {data['sell_signals']}")
            print(f"  Avg Delta Confidence: {np.mean(data['delta_confidence_scores']):.3f}")
            print(f"  Trend Alignment: {data['trend_alignment_count']}")
            print(f"  EMA55 Alignment: {data['ema55_alignment_count']}")
            
            # Show signal details
            if data['signal_details']:
                print(f"  Signal Details:")
                for detail in data['signal_details'][:3]:  # Show first 3 signals
                    print(f"    {detail['side']} at {detail['price']:.2f} (confidence: {detail['delta_confidence']:.3f})")
        
        # Summary
        print(f"\nSUMMARY:")
        summary = results["summary"]
        print(f"  Total Signals: {summary['total_signals']}")
        print(f"  Total Buy Signals: {summary['total_buy_signals']}")
        print(f"  Total Sell Signals: {summary['total_sell_signals']}")
        print(f"  Average Delta Confidence: {summary['avg_delta_confidence']:.3f}")
        print(f"  Trend Alignment Rate: {summary['trend_alignment_rate']:.3f}")
        print(f"  EMA55 Alignment Rate: {summary['ema55_alignment_rate']:.3f}")
        
        # Analysis
        print(f"\nANALYSIS:")
        if summary['total_signals'] > 0:
            print(f"  ✅ Signal generation working - {summary['total_signals']} signals generated")
            if summary['trend_alignment_rate'] > 0.7:
                print(f"  ✅ Good trend alignment - {summary['trend_alignment_rate']:.1%}")
            else:
                print(f"  ⚠️  Low trend alignment - {summary['trend_alignment_rate']:.1%}")
            
            if summary['ema55_alignment_rate'] > 0.7:
                print(f"  ✅ Good EMA55 alignment - {summary['ema55_alignment_rate']:.1%}")
            else:
                print(f"  ⚠️  Low EMA55 alignment - {summary['ema55_alignment_rate']:.1%}")
                
            if summary['avg_delta_confidence'] > 0.6:
                print(f"  ✅ Good delta confidence - {summary['avg_delta_confidence']:.3f}")
            else:
                print(f"  ⚠️  Low delta confidence - {summary['avg_delta_confidence']:.3f}")
        else:
            print(f"  ❌ No signals generated - check signal generation logic")
        
        print("="*60)


def main():
    """Run focused signal generation test"""
    tester = SignalGenerationTester()
    results = tester.run_focused_test()
    tester.print_focused_results(results)
    
    return results


if __name__ == "__main__":
    main()
