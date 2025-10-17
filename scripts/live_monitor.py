#!/usr/bin/env python3
"""
Live Signal Monitoring Script
Monitors live signal generation and system health
"""

import time
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz

def get_current_time():
    """Get current time in ET"""
    et_tz = pytz.timezone('America/New_York')
    return datetime.now(et_tz)

def is_trading_window():
    """Check if current time is within trading window"""
    now = get_current_time()
    start_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    end_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    return start_time <= now <= end_time

def read_signals():
    """Read recent signals from storage"""
    signals_file = Path("storage/state/signals.json")
    if not signals_file.exists():
        return []
    
    try:
        with open(signals_file, 'r') as f:
            signals = json.load(f)
        return signals[-10:] if signals else []  # Last 10 signals
    except Exception:
        return []

def read_metrics():
    """Read current metrics"""
    metrics_file = Path("storage/state/metrics.json")
    if not metrics_file.exists():
        return {}
    
    try:
        with open(metrics_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def format_signal(signal):
    """Format signal for display"""
    timestamp = signal.get('timestamp', '')
    symbol = signal.get('symbol', '')
    side = signal.get('side', '')
    price = signal.get('price', 0)
    confidence = signal.get('delta_confidence', 0)
    reason = signal.get('reason', '')
    
    return f"{timestamp} | {symbol} | {side} | ${price:.2f} | {confidence:.3f} | {reason}"

def monitor_live_signals():
    """Monitor live signal generation"""
    print("="*80)
    print("SMM LIVE SIGNAL MONITOR")
    print("="*80)
    print(f"Started at: {get_current_time().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"Trading Window: {'ACTIVE' if is_trading_window() else 'INACTIVE'}")
    print("="*80)
    
    last_signal_count = 0
    signal_count = 0
    start_time = time.time()
    
    while True:
        try:
            # Get current status
            now = get_current_time()
            trading_active = is_trading_window()
            
            # Read signals and metrics
            signals = read_signals()
            metrics = read_metrics()
            
            # Count signals since start
            current_signal_count = len(signals)
            if current_signal_count > last_signal_count:
                signal_count += (current_signal_count - last_signal_count)
                last_signal_count = current_signal_count
            
            # Calculate runtime
            runtime = time.time() - start_time
            runtime_hours = runtime / 3600
            
            # Clear screen and show status
            os.system('clear')
            print("="*80)
            print("SMM LIVE SIGNAL MONITOR")
            print("="*80)
            print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S ET')}")
            print(f"Trading Window: {'ACTIVE' if trading_active else 'INACTIVE'}")
            print(f"Runtime: {runtime_hours:.2f} hours")
            print(f"Signals Generated: {signal_count}")
            print(f"Signal Rate: {signal_count/max(runtime_hours, 0.01):.2f} signals/hour")
            print("="*80)
            
            # Show recent signals
            if signals:
                print("\nRECENT SIGNALS:")
                print("-" * 80)
                for signal in signals[-5:]:  # Last 5 signals
                    print(format_signal(signal))
            else:
                print("\nNo signals generated yet...")
            
            # Show system metrics
            if metrics:
                print(f"\nSYSTEM METRICS:")
                print("-" * 80)
                print(f"Last Tick: {metrics.get('last_tick_ts', 'N/A')}")
                print(f"Ticker Plant: {'UP' if metrics.get('plants', {}).get('ticker', False) else 'DOWN'}")
                print(f"Order Plant: {'UP' if metrics.get('plants', {}).get('orders', False) else 'DOWN'}")
                print(f"PnL Plant: {'UP' if metrics.get('plants', {}).get('pnl', False) else 'DOWN'}")
                print(f"Errors: {metrics.get('errors', 0)}")
            
            print("\n" + "="*80)
            print("Press Ctrl+C to stop monitoring")
            print("="*80)
            
            # Wait before next update
            time.sleep(30)  # Update every 30 seconds
            
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(30)

if __name__ == "__main__":
    monitor_live_signals()
