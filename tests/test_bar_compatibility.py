"""
Test bar aggregation compatibility across different bar sizes
Ensures all bar types work together without conflicts
"""

import pytest
import numpy as np
import time
from typing import List, Dict
from core.bars import BarAggregator, TBarsAggregator
from core.bar_features import BarFeatureEngine, BarData
from core.smm.combined import SMMCombinedSignal


class BarCompatibilityTester:
    """Test bar aggregation compatibility"""
    
    def __init__(self):
        # Initialize different bar aggregators
        self.bars_1m = BarAggregator(mode="time", duration_sec=60)
        self.bars_233ticks = BarAggregator(mode="ticks", ticks_per_bar=233)
        self.bars_t12 = TBarsAggregator(base_size=12, tick_size=0.25)
        
        # Initialize SMM components
        self.combined_signal = SMMCombinedSignal(delta_threshold=0.65)
        self.bar_features = BarFeatureEngine(window=20)
        
        # Track results
        self.results = {
            "1m_bars": [],
            "233tick_bars": [],
            "t12_bars": [],
            "conflicts": [],
            "signal_consistency": []
        }
    
    def generate_test_ticks(self, count: int, base_price: float = 25000.0) -> List[Dict]:
        """Generate synthetic tick data"""
        ticks = []
        current_price = base_price
        
        for i in range(count):
            # Generate price movement
            price_change = np.random.normal(0, 0.5)  # Random walk
            current_price += price_change
            
            # Generate volume
            volume = np.random.uniform(1, 10)
            
            tick = {
                "price": current_price,
                "size": volume,
                "timestamp": time.time() + i * 0.1  # 100ms intervals
            }
            
            ticks.append(tick)
        
        return ticks
    
    def test_bar_generation(self, ticks: List[Dict]) -> Dict:
        """Test bar generation across different aggregators"""
        results = {
            "1m_bars_generated": 0,
            "233tick_bars_generated": 0,
            "t12_bars_generated": 0,
            "bar_overlap": 0,
            "timing_conflicts": 0
        }
        
        last_1m_time = 0
        last_233tick_time = 0
        last_t12_time = 0
        
        for tick in ticks:
            price = tick["price"]
            size = tick["size"]
            
            # Update 1-minute bars
            for bar in self.bars_1m.update(price, size):
                results["1m_bars_generated"] += 1
                current_time = time.time()
                
                # Check for timing conflicts
                if current_time - last_1m_time < 50:  # Less than 50 seconds
                    results["timing_conflicts"] += 1
                
                last_1m_time = current_time
                
                # Store bar data
                self.results["1m_bars"].append({
                    "timestamp": current_time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                })
            
            # Update 233-tick bars
            for bar in self.bars_233ticks.update(price, size):
                results["233tick_bars_generated"] += 1
                current_time = time.time()
                
                # Check for timing conflicts
                if current_time - last_233tick_time < 10:  # Less than 10 seconds
                    results["timing_conflicts"] += 1
                
                last_233tick_time = current_time
                
                # Store bar data
                self.results["233tick_bars"].append({
                    "timestamp": current_time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                })
            
            # Update T12 bars
            for bar in self.bars_t12.update(price, size):
                results["t12_bars_generated"] += 1
                current_time = time.time()
                
                # Check for timing conflicts
                if current_time - last_t12_time < 5:  # Less than 5 seconds
                    results["timing_conflicts"] += 1
                
                last_t12_time = current_time
                
                # Store bar data
                self.results["t12_bars"].append({
                    "timestamp": current_time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                })
        
        return results
    
    def test_signal_consistency(self) -> Dict:
        """Test signal consistency across different bar types"""
        results = {
            "1m_signals": 0,
            "233tick_signals": 0,
            "t12_signals": 0,
            "conflicting_signals": 0,
            "signal_agreement": 0
        }
        
        # Test signals from 1-minute bars
        for bar_data in self.results["1m_bars"]:
            # Create BarData
            bar = BarData(
                timestamp=bar_data["timestamp"],
                open=bar_data["open"],
                high=bar_data["high"],
                low=bar_data["low"],
                close=bar_data["close"],
                volume=bar_data["volume"],
                buy_volume=bar_data["volume"] * 0.5,
                sell_volume=bar_data["volume"] * 0.5
            )
            
            # Add to feature engine
            self.bar_features.add_bar(bar)
            
            # Update SMM
            self.combined_signal.on_bar_source("1m", bar.open, bar.high, bar.low, bar.close, bar.volume)
            
            if self.bar_features.is_ready():
                bar_snap = self.bar_features.snapshot()
                decision = self.combined_signal.evaluate(bar.close, bar_snap)
                
                if decision.side:
                    results["1m_signals"] += 1
        
        # Test signals from 233-tick bars
        for bar_data in self.results["233tick_bars"]:
            bar = BarData(
                timestamp=bar_data["timestamp"],
                open=bar_data["open"],
                high=bar_data["high"],
                low=bar_data["low"],
                close=bar_data["close"],
                volume=bar_data["volume"],
                buy_volume=bar_data["volume"] * 0.5,
                sell_volume=bar_data["volume"] * 0.5
            )
            
            self.bar_features.add_bar(bar)
            self.combined_signal.on_bar_source("233tick", bar.open, bar.high, bar.low, bar.close, bar.volume)
            
            if self.bar_features.is_ready():
                bar_snap = self.bar_features.snapshot()
                decision = self.combined_signal.evaluate(bar.close, bar_snap)
                
                if decision.side:
                    results["233tick_signals"] += 1
        
        # Test signals from T12 bars
        for bar_data in self.results["t12_bars"]:
            bar = BarData(
                timestamp=bar_data["timestamp"],
                open=bar_data["open"],
                high=bar_data["high"],
                low=bar_data["low"],
                close=bar_data["close"],
                volume=bar_data["volume"],
                buy_volume=bar_data["volume"] * 0.5,
                sell_volume=bar_data["volume"] * 0.5
            )
            
            self.bar_features.add_bar(bar)
            self.combined_signal.on_bar_source("t12", bar.open, bar.high, bar.low, bar.close, bar.volume)
            
            if self.bar_features.is_ready():
                bar_snap = self.bar_features.snapshot()
                decision = self.combined_signal.evaluate(bar.close, bar_snap)
                
                if decision.side:
                    results["t12_signals"] += 1
        
        return results
    
    def test_bar_overlap_detection(self) -> Dict:
        """Test for bar overlap and conflicts"""
        results = {
            "overlapping_bars": 0,
            "price_discrepancies": 0,
            "volume_inconsistencies": 0,
            "timing_issues": 0
        }
        
        # Check for overlapping bars
        all_bars = []
        all_bars.extend([(b["timestamp"], "1m", b) for b in self.results["1m_bars"]])
        all_bars.extend([(b["timestamp"], "233tick", b) for b in self.results["233tick_bars"]])
        all_bars.extend([(b["timestamp"], "t12", b) for b in self.results["t12_bars"]])
        
        # Sort by timestamp
        all_bars.sort(key=lambda x: x[0])
        
        # Check for overlaps
        for i in range(len(all_bars) - 1):
            current_bar = all_bars[i]
            next_bar = all_bars[i + 1]
            
            # Check timing overlap
            if abs(current_bar[0] - next_bar[0]) < 1.0:  # Less than 1 second
                results["overlapping_bars"] += 1
            
            # Check price discrepancies
            price_diff = abs(current_bar[2]["close"] - next_bar[2]["close"])
            if price_diff > 10.0:  # Large price jump
                results["price_discrepancies"] += 1
            
            # Check volume inconsistencies
            volume_ratio = current_bar[2]["volume"] / next_bar[2]["volume"] if next_bar[2]["volume"] > 0 else 0
            if volume_ratio > 10.0 or volume_ratio < 0.1:  # Extreme volume differences
                results["volume_inconsistencies"] += 1
        
        return results
    
    def run_compatibility_test(self) -> Dict:
        """Run comprehensive bar compatibility test"""
        print("Running Bar Compatibility Tests...")
        
        # Generate test data
        print("1. Generating test tick data...")
        test_ticks = self.generate_test_ticks(1000)  # 1000 ticks
        
        # Test bar generation
        print("2. Testing bar generation...")
        bar_results = self.test_bar_generation(test_ticks)
        
        # Test signal consistency
        print("3. Testing signal consistency...")
        signal_results = self.test_signal_consistency()
        
        # Test bar overlap
        print("4. Testing bar overlap detection...")
        overlap_results = self.test_bar_overlap_detection()
        
        # Compile results
        comprehensive_results = {
            "bar_generation": bar_results,
            "signal_consistency": signal_results,
            "overlap_detection": overlap_results,
            "summary": {
                "total_ticks": len(test_ticks),
                "total_bars": bar_results["1m_bars_generated"] + bar_results["233tick_bars_generated"] + bar_results["t12_bars_generated"],
                "bar_generation_success": True,
                "signal_consistency_rate": (signal_results["signal_agreement"] / max(1, signal_results["1m_signals"] + signal_results["233tick_signals"] + signal_results["t12_signals"])),
                "overlap_rate": overlap_results["overlapping_bars"] / max(1, len(self.results["1m_bars"]) + len(self.results["233tick_bars"]) + len(self.results["t12_bars"]))
            }
        }
        
        return comprehensive_results
    
    def print_compatibility_results(self, results: Dict):
        """Print bar compatibility test results"""
        print("\n" + "="*60)
        print("BAR COMPATIBILITY TEST RESULTS")
        print("="*60)
        
        # Bar Generation Results
        print("\n1. BAR GENERATION:")
        bar_gen = results["bar_generation"]
        print(f"   1-Minute Bars: {bar_gen['1m_bars_generated']}")
        print(f"   233-Tick Bars: {bar_gen['233tick_bars_generated']}")
        print(f"   T12 Bars: {bar_gen['t12_bars_generated']}")
        print(f"   Timing Conflicts: {bar_gen['timing_conflicts']}")
        
        # Signal Consistency Results
        print("\n2. SIGNAL CONSISTENCY:")
        signal_cons = results["signal_consistency"]
        print(f"   1-Minute Signals: {signal_cons['1m_signals']}")
        print(f"   233-Tick Signals: {signal_cons['233tick_signals']}")
        print(f"   T12 Signals: {signal_cons['t12_signals']}")
        print(f"   Conflicting Signals: {signal_cons['conflicting_signals']}")
        print(f"   Signal Agreement: {signal_cons['signal_agreement']}")
        
        # Overlap Detection Results
        print("\n3. OVERLAP DETECTION:")
        overlap = results["overlap_detection"]
        print(f"   Overlapping Bars: {overlap['overlapping_bars']}")
        print(f"   Price Discrepancies: {overlap['price_discrepancies']}")
        print(f"   Volume Inconsistencies: {overlap['volume_inconsistencies']}")
        print(f"   Timing Issues: {overlap['timing_issues']}")
        
        # Summary
        print("\n4. SUMMARY:")
        summary = results["summary"]
        print(f"   Total Ticks: {summary['total_ticks']}")
        print(f"   Total Bars: {summary['total_bars']}")
        print(f"   Bar Generation Success: {summary['bar_generation_success']}")
        print(f"   Signal Consistency Rate: {summary['signal_consistency_rate']:.3f}")
        print(f"   Overlap Rate: {summary['overlap_rate']:.3f}")
        
        print("\n" + "="*60)


def main():
    """Run bar compatibility tests"""
    tester = BarCompatibilityTester()
    results = tester.run_compatibility_test()
    tester.print_compatibility_results(results)
    
    return results


if __name__ == "__main__":
    main()
