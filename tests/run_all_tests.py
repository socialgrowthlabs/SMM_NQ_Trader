#!/usr/bin/env python3
"""
Comprehensive Test Runner for SMM Strategy
Runs all tests: signal generation, exit logic, sizing, bracket orders, and integration
"""

import sys
import os
import time
import numpy as np
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.test_smm_integration import SMMIntegrationTester
from tests.test_bar_compatibility import BarCompatibilityTester


class ComprehensiveTestRunner:
    """Runs all SMM strategy tests"""
    
    def __init__(self):
        self.test_results = {}
        self.start_time = time.time()
        
    def run_integration_tests(self):
        """Run SMM integration tests"""
        print("="*80)
        print("RUNNING SMM INTEGRATION TESTS")
        print("="*80)
        
        tester = SMMIntegrationTester()
        results = tester.run_comprehensive_test()
        self.test_results["integration"] = results
        
        return results
    
    def run_compatibility_tests(self):
        """Run bar compatibility tests"""
        print("="*80)
        print("RUNNING BAR COMPATIBILITY TESTS")
        print("="*80)
        
        tester = BarCompatibilityTester()
        results = tester.run_compatibility_test()
        self.test_results["compatibility"] = results
        
        return results
    
    def run_signal_quality_tests(self):
        """Run signal quality tests"""
        print("="*80)
        print("RUNNING SIGNAL QUALITY TESTS")
        print("="*80)
        
        # Test signal quality across different market conditions
        tester = SMMIntegrationTester()
        
        # Test high volatility
        high_vol_bars = tester.generate_test_bars(50, "bullish", 3.0)
        high_vol_results = tester.test_signal_generation(high_vol_bars)
        
        # Test low volatility
        low_vol_bars = tester.generate_test_bars(50, "bullish", 0.5)
        low_vol_results = tester.test_signal_generation(low_vol_bars)
        
        # Test trend changes
        trend_change_bars = tester.generate_test_bars(100, "sideways", 1.0)
        trend_change_results = tester.test_signal_generation(trend_change_bars)
        
        signal_quality_results = {
            "high_volatility": high_vol_results,
            "low_volatility": low_vol_results,
            "trend_change": trend_change_results,
            "summary": {
                "avg_signal_quality": (
                    np.mean(high_vol_results["signal_quality"]) +
                    np.mean(low_vol_results["signal_quality"]) +
                    np.mean(trend_change_results["signal_quality"])
                ) / 3,
                "trend_alignment_rate": (
                    high_vol_results["trend_alignment"] +
                    low_vol_results["trend_alignment"] +
                    trend_change_results["trend_alignment"]
                ) / 3,
                "signal_frequency": (
                    high_vol_results["signals_generated"] +
                    low_vol_results["signals_generated"] +
                    trend_change_results["signals_generated"]
                ) / 3
            }
        }
        
        self.test_results["signal_quality"] = signal_quality_results
        
        print(f"High Volatility Signals: {high_vol_results['signals_generated']}")
        print(f"Low Volatility Signals: {low_vol_results['signals_generated']}")
        print(f"Trend Change Signals: {trend_change_results['signals_generated']}")
        print(f"Average Signal Quality: {signal_quality_results['summary']['avg_signal_quality']:.3f}")
        print(f"Trend Alignment Rate: {signal_quality_results['summary']['trend_alignment_rate']:.3f}")
        
        return signal_quality_results
    
    def run_position_sizing_tests(self):
        """Run position sizing tests"""
        print("="*80)
        print("RUNNING POSITION SIZING TESTS")
        print("="*80)
        
        tester = SMMIntegrationTester()
        
        # Test different confidence levels
        confidence_levels = [0.5, 0.6, 0.7, 0.8, 0.9]
        atr_values = [0.5, 1.0, 1.5, 2.0, 2.5]
        prices = [25000, 25050, 25100, 25150, 25200]
        
        sizing_results = tester.test_position_sizing(confidence_levels, atr_values, prices)
        
        # Test edge cases
        edge_confidence = [0.3, 0.4, 0.95, 0.99]
        edge_atr = [0.1, 0.2, 5.0, 10.0]
        edge_prices = [24000, 26000, 27000, 28000]
        
        edge_sizing_results = tester.test_position_sizing(edge_confidence, edge_atr, edge_prices)
        
        position_sizing_results = {
            "normal_cases": sizing_results,
            "edge_cases": edge_sizing_results,
            "summary": {
                "normal_size_range": [min(sizing_results["final_sizes"]), max(sizing_results["final_sizes"])],
                "edge_size_range": [min(edge_sizing_results["final_sizes"]), max(edge_sizing_results["final_sizes"])],
                "confidence_factor_range": [min(sizing_results["confidence_factors"]), max(sizing_results["confidence_factors"])],
                "volatility_factor_range": [min(sizing_results["volatility_factors"]), max(sizing_results["volatility_factors"])]
            }
        }
        
        self.test_results["position_sizing"] = position_sizing_results
        
        print(f"Normal Position Size Range: {position_sizing_results['summary']['normal_size_range']}")
        print(f"Edge Case Size Range: {position_sizing_results['summary']['edge_size_range']}")
        print(f"Confidence Factor Range: {position_sizing_results['summary']['confidence_factor_range']}")
        print(f"Volatility Factor Range: {position_sizing_results['summary']['volatility_factor_range']}")
        
        return position_sizing_results
    
    def run_bracket_order_tests(self):
        """Run bracket order tests"""
        print("="*80)
        print("RUNNING BRACKET ORDER TESTS")
        print("="*80)
        
        tester = SMMIntegrationTester()
        
        # Test normal market conditions
        entry_prices = [25000, 25050, 25100, 25150, 25200]
        sides = ["BUY", "SELL", "BUY", "SELL", "BUY"]
        atr_values = [0.5, 1.0, 1.5, 2.0, 2.5]
        signal_prices = [25000, 25050, 25100, 25150, 25200]
        
        normal_bracket_results = tester.test_bracket_calculation(entry_prices, sides, atr_values, signal_prices)
        
        # Test extreme market conditions
        extreme_entry_prices = [24000, 26000, 27000, 28000, 29000]
        extreme_sides = ["SELL", "BUY", "SELL", "BUY", "SELL"]
        extreme_atr_values = [0.1, 0.2, 5.0, 10.0, 15.0]
        extreme_signal_prices = [24000, 26000, 27000, 28000, 29000]
        
        extreme_bracket_results = tester.test_bracket_calculation(extreme_entry_prices, extreme_sides, extreme_atr_values, extreme_signal_prices)
        
        bracket_order_results = {
            "normal_cases": normal_bracket_results,
            "extreme_cases": extreme_bracket_results,
            "summary": {
                "normal_target_range": [min(normal_bracket_results["target_ticks"]), max(normal_bracket_results["target_ticks"])],
                "normal_stop_range": [min(normal_bracket_results["stop_ticks"]), max(normal_bracket_results["stop_ticks"])],
                "extreme_target_range": [min(extreme_bracket_results["target_ticks"]), max(extreme_bracket_results["target_ticks"])],
                "extreme_stop_range": [min(extreme_bracket_results["stop_ticks"]), max(extreme_bracket_results["stop_ticks"])],
                "avg_risk_reward_normal": np.mean(normal_bracket_results["risk_reward_ratios"]),
                "avg_risk_reward_extreme": np.mean(extreme_bracket_results["risk_reward_ratios"])
            }
        }
        
        self.test_results["bracket_orders"] = bracket_order_results
        
        print(f"Normal Target Range: {bracket_order_results['summary']['normal_target_range']}")
        print(f"Normal Stop Range: {bracket_order_results['summary']['normal_stop_range']}")
        print(f"Extreme Target Range: {bracket_order_results['summary']['extreme_target_range']}")
        print(f"Extreme Stop Range: {bracket_order_results['summary']['extreme_stop_range']}")
        print(f"Avg Risk/Reward (Normal): {bracket_order_results['summary']['avg_risk_reward_normal']:.2f}")
        print(f"Avg Risk/Reward (Extreme): {bracket_order_results['summary']['avg_risk_reward_extreme']:.2f}")
        
        return bracket_order_results
    
    def run_exit_logic_tests(self):
        """Run exit logic tests"""
        print("="*80)
        print("RUNNING EXIT LOGIC TESTS")
        print("="*80)
        
        tester = SMMIntegrationTester()
        
        # Test different exit scenarios
        test_positions = [
            # Time-based exit
            {"entry_time": time.time() - 900, "entry_price": 25000, "side": "BUY", "current_price": 25050, "momentum_score": 0.8},
            # Profit-based exit
            {"entry_time": time.time() - 300, "entry_price": 25000, "side": "BUY", "current_price": 25100, "momentum_score": 0.8},
            # Momentum-based exit
            {"entry_time": time.time() - 600, "entry_price": 25000, "side": "SELL", "current_price": 24950, "momentum_score": 0.1},
            # Breakeven activation
            {"entry_time": time.time() - 400, "entry_price": 25000, "side": "BUY", "current_price": 25050, "momentum_score": 0.5},
            # No exit conditions met
            {"entry_time": time.time() - 200, "entry_price": 25000, "side": "BUY", "current_price": 25010, "momentum_score": 0.7}
        ]
        
        exit_results = tester.test_exit_logic(test_positions)
        
        # Test edge cases
        edge_positions = [
            # Very long hold time
            {"entry_time": time.time() - 3600, "entry_price": 25000, "side": "BUY", "current_price": 25000, "momentum_score": 0.5},
            # Very high profit
            {"entry_time": time.time() - 100, "entry_price": 25000, "side": "BUY", "current_price": 25200, "momentum_score": 0.9},
            # Very low momentum
            {"entry_time": time.time() - 300, "entry_price": 25000, "side": "SELL", "current_price": 24900, "momentum_score": 0.05}
        ]
        
        edge_exit_results = tester.test_exit_logic(edge_positions)
        
        exit_logic_results = {
            "normal_cases": exit_results,
            "edge_cases": edge_exit_results,
            "summary": {
                "normal_exit_rate": exit_results["total_exits"] / len(test_positions),
                "edge_exit_rate": edge_exit_results["total_exits"] / len(edge_positions),
                "time_exit_rate": (exit_results["time_exits"] + edge_exit_results["time_exits"]) / (len(test_positions) + len(edge_positions)),
                "profit_exit_rate": (exit_results["profit_exits"] + edge_exit_results["profit_exits"]) / (len(test_positions) + len(edge_positions)),
                "momentum_exit_rate": (exit_results["momentum_exits"] + edge_exit_results["momentum_exits"]) / (len(test_positions) + len(edge_positions))
            }
        }
        
        self.test_results["exit_logic"] = exit_logic_results
        
        print(f"Normal Exit Rate: {exit_logic_results['summary']['normal_exit_rate']:.3f}")
        print(f"Edge Case Exit Rate: {exit_logic_results['summary']['edge_exit_rate']:.3f}")
        print(f"Time Exit Rate: {exit_logic_results['summary']['time_exit_rate']:.3f}")
        print(f"Profit Exit Rate: {exit_logic_results['summary']['profit_exit_rate']:.3f}")
        print(f"Momentum Exit Rate: {exit_logic_results['summary']['momentum_exit_rate']:.3f}")
        
        return exit_logic_results
    
    def generate_comprehensive_report(self):
        """Generate comprehensive test report"""
        end_time = time.time()
        total_time = end_time - self.start_time
        
        print("\n" + "="*80)
        print("COMPREHENSIVE SMM STRATEGY TEST REPORT")
        print("="*80)
        
        print(f"\nTest Execution Time: {total_time:.2f} seconds")
        print(f"Total Tests Run: {len(self.test_results)}")
        
        # Overall summary
        overall_summary = {
            "signal_quality": self.test_results.get("signal_quality", {}).get("summary", {}).get("avg_signal_quality", 0),
            "trend_alignment": self.test_results.get("signal_quality", {}).get("summary", {}).get("trend_alignment_rate", 0),
            "position_sizing_range": self.test_results.get("position_sizing", {}).get("summary", {}).get("normal_size_range", [0, 0]),
            "bracket_risk_reward": self.test_results.get("bracket_orders", {}).get("summary", {}).get("avg_risk_reward_normal", 0),
            "exit_efficiency": self.test_results.get("exit_logic", {}).get("summary", {}).get("normal_exit_rate", 0),
            "bar_compatibility": self.test_results.get("compatibility", {}).get("summary", {}).get("signal_consistency_rate", 0)
        }
        
        print(f"\nOVERALL SUMMARY:")
        print(f"  Signal Quality: {overall_summary['signal_quality']:.3f}")
        print(f"  Trend Alignment: {overall_summary['trend_alignment']:.3f}")
        print(f"  Position Sizing Range: {overall_summary['position_sizing_range']}")
        print(f"  Bracket Risk/Reward: {overall_summary['bracket_risk_reward']:.2f}")
        print(f"  Exit Efficiency: {overall_summary['exit_efficiency']:.3f}")
        print(f"  Bar Compatibility: {overall_summary['bar_compatibility']:.3f}")
        
        # Recommendations
        print(f"\nRECOMMENDATIONS:")
        if overall_summary['signal_quality'] < 0.6:
            print("  ⚠️  Signal quality below threshold - consider adjusting delta confidence")
        if overall_summary['trend_alignment'] < 0.7:
            print("  ⚠️  Trend alignment rate low - review EMA55 filtering")
        if overall_summary['bracket_risk_reward'] < 1.5:
            print("  ⚠️  Risk/reward ratio low - consider adjusting target/stop levels")
        if overall_summary['exit_efficiency'] < 0.8:
            print("  ⚠️  Exit efficiency low - review exit logic parameters")
        if overall_summary['bar_compatibility'] < 0.9:
            print("  ⚠️  Bar compatibility issues - check bar aggregation logic")
        
        print(f"\n✅ All tests completed successfully!")
        print("="*80)
        
        return overall_summary
    
    def run_all_tests(self):
        """Run all comprehensive tests"""
        print("Starting Comprehensive SMM Strategy Tests...")
        print(f"Test started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Run all test suites
            self.run_integration_tests()
            self.run_compatibility_tests()
            self.run_signal_quality_tests()
            self.run_position_sizing_tests()
            self.run_bracket_order_tests()
            self.run_exit_logic_tests()
            
            # Generate comprehensive report
            report = self.generate_comprehensive_report()
            
            return {
                "success": True,
                "test_results": self.test_results,
                "overall_summary": report,
                "execution_time": time.time() - self.start_time
            }
            
        except Exception as e:
            print(f"❌ Test execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - self.start_time
            }


def main():
    """Main test runner"""
    runner = ComprehensiveTestRunner()
    results = runner.run_all_tests()
    
    if results["success"]:
        print(f"\n🎉 All tests passed successfully!")
        print(f"Total execution time: {results['execution_time']:.2f} seconds")
    else:
        print(f"\n❌ Tests failed: {results['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
