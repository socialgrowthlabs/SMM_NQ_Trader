"""
Comprehensive SMM Strategy Integration Tests
Tests signal generation, exit logic, sizing, and bracket orders across different bar sizes
"""

import pytest
import numpy as np
import time
from unittest.mock import Mock, AsyncMock
from dataclasses import dataclass
from typing import List, Dict, Optional

from core.smm.main import SMMMainEngine, SMMDecision
from core.smm.combined import SMMCombinedSignal, CombinedDecision
from core.bar_features import BarFeatureEngine, BarData, BarFeatureSnapshot
from core.features import FeatureSnapshot
from exec.enhanced_executor import EnhancedExecutionEngine, EnhancedOrderIntent
from core.bars import BarAggregator, TBarsAggregator


@dataclass
class TestBar:
    """Test bar data"""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_volume: float
    sell_volume: float


class SMMIntegrationTester:
    """Comprehensive SMM strategy integration tester"""
    
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
        self.executor = EnhancedExecutionEngine()
        self.test_results = []
        
    def generate_test_bars(self, count: int, trend: str = "bullish", volatility: float = 1.0) -> List[TestBar]:
        """Generate synthetic test bars with specified trend and volatility"""
        bars = []
        base_price = 25000.0
        current_price = base_price
        
        for i in range(count):
            # Generate OHLC based on trend
            if trend == "bullish":
                open_price = current_price
                high_price = current_price + (volatility * np.random.uniform(0.5, 2.0))
                low_price = current_price - (volatility * np.random.uniform(0.1, 0.5))
                close_price = current_price + (volatility * np.random.uniform(0.2, 1.0))
            elif trend == "bearish":
                open_price = current_price
                high_price = current_price + (volatility * np.random.uniform(0.1, 0.5))
                low_price = current_price - (volatility * np.random.uniform(0.5, 2.0))
                close_price = current_price - (volatility * np.random.uniform(0.2, 1.0))
            else:  # sideways
                open_price = current_price
                high_price = current_price + (volatility * np.random.uniform(0.1, 1.0))
                low_price = current_price - (volatility * np.random.uniform(0.1, 1.0))
                close_price = current_price + (volatility * np.random.uniform(-0.5, 0.5))
            
            # Generate volume data
            volume = np.random.uniform(100, 1000)
            buy_volume = volume * np.random.uniform(0.3, 0.7)
            sell_volume = volume - buy_volume
            
            bar = TestBar(
                timestamp=time.time() + i * 60,  # 1-minute intervals
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                buy_volume=buy_volume,
                sell_volume=sell_volume
            )
            
            bars.append(bar)
            current_price = close_price
            
        return bars
    
    def test_signal_generation(self, bars: List[TestBar]) -> Dict:
        """Test signal generation across different bar scenarios"""
        results = {
            "total_bars": len(bars),
            "signals_generated": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "signal_quality": [],
            "delta_confidence_range": [1.0, 0.0],
            "trend_alignment": 0
        }
        
        for bar in bars:
            # Convert to BarData
            bar_data = BarData(
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                buy_volume=bar.buy_volume,
                sell_volume=bar.sell_volume
            )
            
            # Add to feature engine
            self.bar_features.add_bar(bar_data)
            
            # Update SMM engine and combined signal
            self.smm_engine.on_bar(bar.open, bar.high, bar.low, bar.close, bar.volume)
            self.combined_signal.on_bar(bar.open, bar.high, bar.low, bar.close, bar.volume)
            
            # Generate signal if enough data
            if self.bar_features.is_ready():
                bar_snap = self.bar_features.snapshot()
                
                # Create mock feature snapshot for SMM
                mock_features = FeatureSnapshot(
                    cvd=bar_snap.cvd,
                    cvd_slope=bar_snap.cvd_slope,
                    depth_imbalance=bar_snap.depth_imbalance,
                    depth_slope=bar_snap.depth_slope,
                    aggressive_buy_ratio=bar_snap.aggressive_buy_ratio,
                    delta_confidence=bar_snap.delta_confidence
                )
                
                # Evaluate signal
                smm_decision = self.smm_engine.evaluate(bar.close, mock_features)
                combined_decision = self.combined_signal.evaluate(bar.close, mock_features)
                
                if combined_decision.side:
                    results["signals_generated"] += 1
                    if combined_decision.side == "BUY":
                        results["buy_signals"] += 1
                    else:
                        results["sell_signals"] += 1
                    
                    # Track signal quality
                    quality_score = bar_snap.delta_confidence
                    results["signal_quality"].append(quality_score)
                    results["delta_confidence_range"][0] = min(results["delta_confidence_range"][0], quality_score)
                    results["delta_confidence_range"][1] = max(results["delta_confidence_range"][1], quality_score)
                    
                    # Check trend alignment
                    if (combined_decision.side == "BUY" and smm_decision.trend_bullish) or \
                       (combined_decision.side == "SELL" and smm_decision.trend_bearish):
                        results["trend_alignment"] += 1
        
        return results
    
    def test_position_sizing(self, confidence_scores: List[float], atr_values: List[float], prices: List[float]) -> Dict:
        """Test position sizing logic"""
        results = {
            "position_sizes": [],
            "confidence_factors": [],
            "volatility_factors": [],
            "final_sizes": []
        }
        
        for i, (confidence, atr, price) in enumerate(zip(confidence_scores, atr_values, prices)):
            # Test position sizing calculation
            base_size = 1
            confidence_factor = min(confidence / 0.6, 1.5) if confidence > 0.6 else 1.0
            volatility_factor = max(0.5, 1.0 - (atr / price) * 100) if atr > 0 else 1.0
            
            final_size = max(1, min(int(base_size * confidence_factor * volatility_factor), 2))
            
            results["position_sizes"].append(base_size)
            results["confidence_factors"].append(confidence_factor)
            results["volatility_factors"].append(volatility_factor)
            results["final_sizes"].append(final_size)
        
        return results
    
    def test_bracket_calculation(self, entry_prices: List[float], sides: List[str], atr_values: List[float], signal_prices: List[float]) -> Dict:
        """Test dynamic bracket order calculation"""
        results = {
            "target_ticks": [],
            "stop_ticks": [],
            "risk_reward_ratios": [],
            "atr_based": [],
            "signal_based": []
        }
        
        for entry_price, side, atr, signal_price in zip(entry_prices, sides, atr_values, signal_prices):
            # Test ATR-based calculation
            if atr > 0:
                atr_target_ticks = max(8, int(atr * 1.5 / 0.25))
                atr_stop_ticks = max(4, int(atr * 0.8 / 0.25))
            else:
                atr_target_ticks = 16
                atr_stop_ticks = 8
            
            # Test signal-based calculation
            if signal_price > 0:
                if side.upper() == "BUY":
                    target_price = signal_price * 1.5
                    stop_price = signal_price * 0.8
                else:
                    target_price = signal_price * 0.8
                    stop_price = signal_price * 1.5
                
                signal_target_ticks = max(4, int(abs(target_price - entry_price) / 0.25))
                signal_stop_ticks = max(4, int(abs(stop_price - entry_price) / 0.25))
            else:
                signal_target_ticks = 16
                signal_stop_ticks = 8
            
            # Calculate risk/reward ratio
            risk_reward = atr_target_ticks / atr_stop_ticks if atr_stop_ticks > 0 else 0
            
            results["target_ticks"].append(atr_target_ticks)
            results["stop_ticks"].append(atr_stop_ticks)
            results["risk_reward_ratios"].append(risk_reward)
            results["atr_based"].append((atr_target_ticks, atr_stop_ticks))
            results["signal_based"].append((signal_target_ticks, signal_stop_ticks))
        
        return results
    
    def test_exit_logic(self, positions: List[Dict]) -> Dict:
        """Test exit logic and position management"""
        results = {
            "time_exits": 0,
            "profit_exits": 0,
            "breakeven_activations": 0,
            "momentum_exits": 0,
            "total_exits": 0
        }
        
        for position in positions:
            # Simulate position over time
            entry_time = position["entry_time"]
            entry_price = position["entry_price"]
            side = position["side"]
            current_time = time.time()
            current_price = position["current_price"]
            momentum_score = position.get("momentum_score", 0.5)
            
            # Calculate unrealized P&L
            if side == "BUY":
                unrealized_pnl = (current_price - entry_price) * 0.25  # Convert to ticks
            else:
                unrealized_pnl = (entry_price - current_price) * 0.25
            
            # Test exit conditions
            time_in_position = (current_time - entry_time) / 60  # minutes
            
            if time_in_position >= 15:  # Max hold time
                results["time_exits"] += 1
                results["total_exits"] += 1
            elif unrealized_pnl >= 8:  # Early profit target
                results["profit_exits"] += 1
                results["total_exits"] += 1
            elif unrealized_pnl >= 6:  # Breakeven activation
                results["breakeven_activations"] += 1
            elif momentum_score < 0.3:  # Momentum exit
                results["momentum_exits"] += 1
                results["total_exits"] += 1
        
        return results
    
    def run_comprehensive_test(self) -> Dict:
        """Run comprehensive integration test"""
        print("Running SMM Strategy Integration Tests...")
        
        # Test 1: Signal Generation
        print("1. Testing Signal Generation...")
        bullish_bars = self.generate_test_bars(100, "bullish", 1.0)
        bearish_bars = self.generate_test_bars(100, "bearish", 1.0)
        sideways_bars = self.generate_test_bars(100, "sideways", 0.5)
        
        bullish_results = self.test_signal_generation(bullish_bars)
        bearish_results = self.test_signal_generation(bearish_bars)
        sideways_results = self.test_signal_generation(sideways_bars)
        
        # Test 2: Position Sizing
        print("2. Testing Position Sizing...")
        confidence_scores = [0.5, 0.6, 0.7, 0.8, 0.9]
        atr_values = [0.5, 1.0, 1.5, 2.0, 2.5]
        prices = [25000, 25050, 25100, 25150, 25200]
        
        sizing_results = self.test_position_sizing(confidence_scores, atr_values, prices)
        
        # Test 3: Bracket Calculation
        print("3. Testing Bracket Calculation...")
        entry_prices = [25000, 25050, 25100, 25150, 25200]
        sides = ["BUY", "SELL", "BUY", "SELL", "BUY"]
        atr_values_bracket = [0.5, 1.0, 1.5, 2.0, 2.5]
        signal_prices = [25000, 25050, 25100, 25150, 25200]
        
        bracket_results = self.test_bracket_calculation(entry_prices, sides, atr_values_bracket, signal_prices)
        
        # Test 4: Exit Logic
        print("4. Testing Exit Logic...")
        test_positions = [
            {"entry_time": time.time() - 900, "entry_price": 25000, "side": "BUY", "current_price": 25050, "momentum_score": 0.2},
            {"entry_time": time.time() - 300, "entry_price": 25000, "side": "BUY", "current_price": 25100, "momentum_score": 0.8},
            {"entry_time": time.time() - 600, "entry_price": 25000, "side": "SELL", "current_price": 24950, "momentum_score": 0.1},
        ]
        
        exit_results = self.test_exit_logic(test_positions)
        
        # Compile results
        comprehensive_results = {
            "signal_generation": {
                "bullish": bullish_results,
                "bearish": bearish_results,
                "sideways": sideways_results
            },
            "position_sizing": sizing_results,
            "bracket_calculation": bracket_results,
            "exit_logic": exit_results,
            "summary": {
                "total_tests": 4,
                "signal_quality_avg": np.mean(bullish_results["signal_quality"] + bearish_results["signal_quality"] + sideways_results["signal_quality"]),
                "trend_alignment_rate": (bullish_results["trend_alignment"] + bearish_results["trend_alignment"] + sideways_results["trend_alignment"]) / 3,
                "position_sizing_range": [min(sizing_results["final_sizes"]), max(sizing_results["final_sizes"])],
                "bracket_risk_reward_avg": np.mean(bracket_results["risk_reward_ratios"]),
                "exit_efficiency": exit_results["total_exits"] / len(test_positions) if test_positions else 0
            }
        }
        
        return comprehensive_results
    
    def print_test_results(self, results: Dict):
        """Print comprehensive test results"""
        print("\n" + "="*60)
        print("SMM STRATEGY INTEGRATION TEST RESULTS")
        print("="*60)
        
        # Signal Generation Results
        print("\n1. SIGNAL GENERATION:")
        for trend, data in results["signal_generation"].items():
            print(f"   {trend.upper()}:")
            print(f"     Total Bars: {data['total_bars']}")
            print(f"     Signals Generated: {data['signals_generated']}")
            print(f"     Buy Signals: {data['buy_signals']}")
            print(f"     Sell Signals: {data['sell_signals']}")
            print(f"     Avg Signal Quality: {np.mean(data['signal_quality']):.3f}")
            print(f"     Trend Alignment: {data['trend_alignment']}")
        
        # Position Sizing Results
        print("\n2. POSITION SIZING:")
        sizing = results["position_sizing"]
        print(f"   Position Size Range: {min(sizing['final_sizes'])} - {max(sizing['final_sizes'])}")
        print(f"   Avg Confidence Factor: {np.mean(sizing['confidence_factors']):.3f}")
        print(f"   Avg Volatility Factor: {np.mean(sizing['volatility_factors']):.3f}")
        
        # Bracket Calculation Results
        print("\n3. BRACKET CALCULATION:")
        bracket = results["bracket_calculation"]
        print(f"   Target Ticks Range: {min(bracket['target_ticks'])} - {max(bracket['target_ticks'])}")
        print(f"   Stop Ticks Range: {min(bracket['stop_ticks'])} - {max(bracket['stop_ticks'])}")
        print(f"   Avg Risk/Reward Ratio: {np.mean(bracket['risk_reward_ratios']):.2f}")
        
        # Exit Logic Results
        print("\n4. EXIT LOGIC:")
        exit_logic = results["exit_logic"]
        print(f"   Time Exits: {exit_logic['time_exits']}")
        print(f"   Profit Exits: {exit_logic['profit_exits']}")
        print(f"   Breakeven Activations: {exit_logic['breakeven_activations']}")
        print(f"   Momentum Exits: {exit_logic['momentum_exits']}")
        print(f"   Total Exits: {exit_logic['total_exits']}")
        
        # Summary
        print("\n5. SUMMARY:")
        summary = results["summary"]
        print(f"   Total Tests: {summary['total_tests']}")
        print(f"   Avg Signal Quality: {summary['signal_quality_avg']:.3f}")
        print(f"   Trend Alignment Rate: {summary['trend_alignment_rate']:.3f}")
        print(f"   Position Sizing Range: {summary['position_sizing_range']}")
        print(f"   Avg Risk/Reward Ratio: {summary['bracket_risk_reward_avg']:.2f}")
        print(f"   Exit Efficiency: {summary['exit_efficiency']:.3f}")
        
        print("\n" + "="*60)


def main():
    """Run comprehensive SMM integration tests"""
    tester = SMMIntegrationTester()
    results = tester.run_comprehensive_test()
    tester.print_test_results(results)
    
    # Return results for further analysis
    return results


if __name__ == "__main__":
    main()
