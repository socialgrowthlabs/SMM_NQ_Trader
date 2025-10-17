#!/usr/bin/env python3
"""
Strategy Performance Monitor
Tracks win rate, drawdown, and position metrics for the enhanced SMM strategy
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import argparse


class StrategyMonitor:
    def __init__(self, state_dir: str = "storage/state"):
        self.state_dir = Path(state_dir)
        self.metrics_file = self.state_dir / "metrics.json"
        self.accounts_file = self.state_dir / "accounts.json"
        self.signals_file = self.state_dir / "signals.json"
        self.orders_file = self.state_dir / "orders.json"
        
    def get_current_metrics(self) -> Dict:
        """Get current system metrics"""
        try:
            with open(self.metrics_file) as f:
                return json.load(f)
        except Exception:
            return {}
    
    def get_account_status(self) -> Dict:
        """Get current account status"""
        try:
            with open(self.accounts_file) as f:
                return json.load(f)
        except Exception:
            return {}
    
    def get_recent_signals(self, limit: int = 50) -> List[Dict]:
        """Get recent signals"""
        signals = []
        try:
            with open(self.signals_file) as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        signals.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass
        return signals
    
    def get_recent_orders(self, limit: int = 50) -> List[Dict]:
        """Get recent orders"""
        orders = []
        try:
            with open(self.orders_file) as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        orders.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass
        return orders
    
    def analyze_performance(self) -> Dict:
        """Analyze strategy performance metrics"""
        metrics = self.get_current_metrics()
        accounts = self.get_account_status()
        signals = self.get_recent_signals(100)
        orders = self.get_recent_orders(100)
        
        # Calculate win rate from signals
        total_signals = len(signals)
        buy_signals = len([s for s in signals if s.get('side') == 'BUY'])
        sell_signals = len([s for s in signals if s.get('side') == 'SELL'])
        
        # Calculate account performance
        account_performance = {}
        total_daily_pnl = 0.0
        total_unrealized_pnl = 0.0
        
        for account in accounts.get('accounts', []):
            account_id = account.get('account_id', '')
            daily_pnl = account.get('daily_pnl', 0.0)
            unrealized_pnl = account.get('unrealized_pnl', 0.0)
            position_qty = account.get('position_qty', 0)
            
            if account_id in ['APEX-196119-166', 'APEX-196119-167']:  # Test accounts
                account_performance[account_id] = {
                    'daily_pnl': daily_pnl,
                    'unrealized_pnl': unrealized_pnl,
                    'position_qty': position_qty,
                    'total_pnl': daily_pnl + unrealized_pnl
                }
                total_daily_pnl += daily_pnl
                total_unrealized_pnl += unrealized_pnl
        
        # Calculate confidence distribution
        confidence_scores = [s.get('delta_confidence', 0) for s in signals if 'delta_confidence' in s]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        # Check if within trading window
        now = datetime.now(timezone.utc)
        trading_window_active = self._is_trading_window_active(now)
        
        return {
            'timestamp': time.time(),
            'trading_window_active': trading_window_active,
            'total_signals': total_signals,
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'avg_confidence': avg_confidence,
            'account_performance': account_performance,
            'total_daily_pnl': total_daily_pnl,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_pnl': total_daily_pnl + total_unrealized_pnl,
            'plants_status': metrics.get('plants', {}),
            'last_pnl_update': metrics.get('last_pnl_ts', 0),
            'system_health': {
                'ticker_up': metrics.get('plants', {}).get('ticker', False),
                'order_up': metrics.get('plants', {}).get('order', False),
                'pnl_up': metrics.get('plants', {}).get('pnl', False),
                'errors': metrics.get('errors', 0)
            }
        }
    
    def _is_trading_window_active(self, now: datetime) -> bool:
        """Check if current time is within trading window (9:30-10:00 AM ET)"""
        try:
            # Convert to ET
            et_tz = timezone.utc  # Simplified - would need pytz for proper ET
            et_time = now.astimezone(et_tz).time()
            
            start_time = datetime.strptime("09:30", "%H:%M").time()
            end_time = datetime.strptime("10:00", "%H:%M").time()
            
            return start_time <= et_time <= end_time
        except Exception:
            return False
    
    def print_status(self):
        """Print current strategy status"""
        perf = self.analyze_performance()
        
        print(f"\n=== SMM Strategy Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        print(f"Trading Window Active: {'YES' if perf['trading_window_active'] else 'NO'}")
        print(f"System Health: {'OK' if all(perf['system_health'].values()) else 'ISSUES'}")
        
        print(f"\nSignal Metrics:")
        print(f"  Total Signals: {perf['total_signals']}")
        print(f"  Buy Signals: {perf['buy_signals']}")
        print(f"  Sell Signals: {perf['sell_signals']}")
        print(f"  Avg Confidence: {perf['avg_confidence']:.3f}")
        
        print(f"\nAccount Performance (Test Accounts):")
        for account_id, data in perf['account_performance'].items():
            print(f"  {account_id}:")
            print(f"    Daily P&L: ${data['daily_pnl']:.2f}")
            print(f"    Unrealized P&L: ${data['unrealized_pnl']:.2f}")
            print(f"    Total P&L: ${data['total_pnl']:.2f}")
            print(f"    Position: {data['position_qty']}")
        
        print(f"\nTotal Performance:")
        print(f"  Daily P&L: ${perf['total_daily_pnl']:.2f}")
        print(f"  Unrealized P&L: ${perf['total_unrealized_pnl']:.2f}")
        print(f"  Total P&L: ${perf['total_pnl']:.2f}")
        
        print(f"\nSystem Status:")
        health = perf['system_health']
        print(f"  Ticker Plant: {'UP' if health['ticker_up'] else 'DOWN'}")
        print(f"  Order Plant: {'UP' if health['order_up'] else 'DOWN'}")
        print(f"  PnL Plant: {'UP' if health['pnl_up'] else 'DOWN'}")
        print(f"  Errors: {health['errors']}")
        
        if perf['last_pnl_update'] > 0:
            last_update = datetime.fromtimestamp(perf['last_pnl_update'])
            print(f"  Last PnL Update: {last_update.strftime('%H:%M:%S')}")


def main():
    parser = argparse.ArgumentParser(description='Monitor SMM Strategy Performance')
    parser.add_argument('--watch', action='store_true', help='Watch mode - continuously monitor')
    parser.add_argument('--interval', type=int, default=10, help='Watch interval in seconds')
    args = parser.parse_args()
    
    monitor = StrategyMonitor()
    
    if args.watch:
        try:
            while True:
                monitor.print_status()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
    else:
        monitor.print_status()


if __name__ == "__main__":
    main()

