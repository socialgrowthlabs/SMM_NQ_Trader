"""
External Signal Processor for SMM NQ Trader
Processes external signals from NinjaTrader and integrates with SMM execution engine
"""

import asyncio
import json
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from exec.enhanced_executor import EnhancedExecutionEngine
from core.symbols import SymbolManager
from core.account_sync_manager import AccountSyncManager, get_sync_manager


@dataclass
class ExternalSignalData:
    """External signal data structure"""
    timestamp: float
    symbol: str
    side: str
    signal_type: str
    price: float
    reason: str
    source: str
    confidence_score: float
    atr_value: float
    exchange: str
    processed: bool = False


class ExternalSignalProcessor:
    """Processes external signals and integrates with SMM execution engine"""
    
    def __init__(self, state_dir: str = "storage/state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.external_signals_path = self.state_dir / "external_signals.json"
        self.signal_filters_path = self.state_dir / "signal_filters.json"
        self.processed_signals_path = self.state_dir / "processed_external_signals.json"
        
        # Initialize execution engine and sync manager
        self.executor = EnhancedExecutionEngine()
        self.sync_manager = get_sync_manager()
        
        # Signal processing state
        self.last_processed_timestamp = 0.0
        self.signal_cooldown_seconds = 5.0  # Minimum time between processing signals
        self.max_signals_per_minute = 10
        
        # Filter controls
        self.long_signals_enabled = True
        self.short_signals_enabled = True
        
        # Load configuration
        self._load_filters()
        
        # Track processed signals to avoid duplicates
        self.processed_signals: Dict[str, float] = {}
        
    def _load_filters(self) -> None:
        """Load signal filter settings"""
        try:
            if self.signal_filters_path.exists():
                with self.signal_filters_path.open("r") as f:
                    filters = json.load(f)
                    self.long_signals_enabled = filters.get("long_signals_enabled", True)
                    self.short_signals_enabled = filters.get("short_signals_enabled", True)
        except Exception as e:
            print(f"Error loading filters: {e}")
            self.long_signals_enabled = True
            self.short_signals_enabled = True
    
    def _should_process_signal(self, signal: ExternalSignalData) -> bool:
        """Check if signal should be processed based on filters and cooldown"""
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_processed_timestamp < self.signal_cooldown_seconds:
            return False
        
        # Check signal filters
        if signal.side.upper() == "BUY" and not self.long_signals_enabled:
            return False
        if signal.side.upper() == "SELL" and not self.short_signals_enabled:
            return False
        
        # Check for duplicate signals
        signal_key = f"{signal.source}_{signal.symbol}_{signal.side}_{signal.signal_type}_{signal.timestamp}"
        if signal_key in self.processed_signals:
            return False
        
        # Check rate limiting
        recent_signals = sum(1 for ts in self.processed_signals.values() 
                           if current_time - ts < 60.0)
        if recent_signals >= self.max_signals_per_minute:
            return False
        
        return True
    
    def _get_active_accounts(self) -> List[str]:
        """Get list of active trading accounts using sync manager"""
        try:
            # Use sync manager to get enabled accounts
            enabled_accounts = self.sync_manager.get_enabled_accounts()
            if enabled_accounts:
                return enabled_accounts
            
            # Fallback to direct file reading
            accounts_path = self.state_dir / "accounts.json"
            if accounts_path.exists():
                with accounts_path.open("r") as f:
                    accounts_data = json.load(f)
                    accounts = accounts_data.get("accounts", [])
                    return [acc["account_id"] for acc in accounts if acc.get("enabled", False)]
        except Exception as e:
            print(f"Error loading accounts: {e}")
        return []
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price for symbol"""
        try:
            # Try to get from metrics file
            metrics_path = self.state_dir / "metrics.json"
            if metrics_path.exists():
                with metrics_path.open("r") as f:
                    metrics = json.load(f)
                    if metrics.get("last_price", 0) > 0:
                        return metrics["last_price"]
        except Exception as e:
            print(f"Error getting current price: {e}")
        return None
    
    def _calculate_atr_value(self, symbol: str) -> float:
        """Calculate ATR value for position sizing"""
        # Default ATR value - in production this would be calculated from market data
        return 0.25  # 1 tick for NQ
    
    async def _process_entry_signal(self, signal: ExternalSignalData) -> None:
        """Process entry signal with account synchronization"""
        try:
            accounts = self._get_active_accounts()
            if not accounts:
                print("No active accounts found for signal processing")
                return
            
            current_price = self._get_current_price(signal.symbol)
            if current_price is None:
                current_price = signal.price
            
            atr_value = self._calculate_atr_value(signal.symbol)
            
            # Prepare signal data for synchronization
            signal_data = {
                "symbol": signal.symbol,
                "side": signal.side,
                "signal_type": signal.signal_type,
                "price": current_price,
                "signal_price": signal.price,
                "confidence_score": signal.confidence_score,
                "atr_value": atr_value,
                "exchange": signal.exchange,
                "reason": signal.reason,
                "source": signal.source
            }
            
            # Synchronize signal execution across accounts
            sync_results = await self.sync_manager.synchronize_accounts(accounts, signal_data)
            
            successful_accounts = [acc for acc, success in sync_results.items() if success]
            failed_accounts = [acc for acc, success in sync_results.items() if not success]
            
            if successful_accounts:
                print(f"Processed {signal.signal_type} signal: {signal.side} {signal.symbol} at {current_price}")
                print(f"Successfully synchronized across {len(successful_accounts)} accounts: {successful_accounts}")
                
                # Submit signal to execution engine for successful accounts
                intents = await self.executor.submit_enhanced_signal(
                    symbol=signal.symbol,
                    side=signal.side,
                    confidence_score=signal.confidence_score,
                    atr_value=atr_value,
                    current_price=current_price,
                    accounts=successful_accounts,
                    signal_price=signal.price,
                    exchange=signal.exchange
                )
                
                if intents:
                    print(f"Generated {len(intents)} order intents")
                else:
                    print(f"No order intents generated for signal: {signal.side} {signal.symbol}")
            
            if failed_accounts:
                print(f"Failed to synchronize signal for {len(failed_accounts)} accounts: {failed_accounts}")
                
        except Exception as e:
            print(f"Error processing entry signal: {e}")
    
    async def _process_exit_signal(self, signal: ExternalSignalData) -> None:
        """Process exit signal"""
        try:
            # For exit signals, we need to close existing positions
            # This would integrate with the position management system
            print(f"Processing exit signal: {signal.side} {signal.symbol} at {signal.price}")
            
            # TODO: Implement position closing logic
            # This would involve:
            # 1. Finding open positions for the symbol
            # 2. Determining which positions to close
            # 3. Submitting close orders
            
        except Exception as e:
            print(f"Error processing exit signal: {e}")
    
    async def process_signal(self, signal: ExternalSignalData) -> bool:
        """Process a single external signal"""
        try:
            if not self._should_process_signal(signal):
                return False
            
            # Mark signal as processed
            signal_key = f"{signal.source}_{signal.symbol}_{signal.side}_{signal.signal_type}_{signal.timestamp}"
            self.processed_signals[signal_key] = time.time()
            self.last_processed_timestamp = time.time()
            
            # Process based on signal type
            if signal.signal_type.upper() == "ENTRY":
                await self._process_entry_signal(signal)
            elif signal.signal_type.upper() == "EXIT":
                await self._process_exit_signal(signal)
            else:
                print(f"Unknown signal type: {signal.signal_type}")
                return False
            
            # Record processed signal
            self._record_processed_signal(signal)
            return True
            
        except Exception as e:
            print(f"Error processing signal: {e}")
            return False
    
    def _record_processed_signal(self, signal: ExternalSignalData) -> None:
        """Record processed signal for tracking"""
        try:
            processed_data = {
                "timestamp": signal.timestamp,
                "symbol": signal.symbol,
                "side": signal.side,
                "signal_type": signal.signal_type,
                "price": signal.price,
                "reason": signal.reason,
                "source": signal.source,
                "confidence_score": signal.confidence_score,
                "processed_at": time.time()
            }
            
            with self.processed_signals_path.open("a") as f:
                f.write(json.dumps(processed_data) + "\n")
                
        except Exception as e:
            print(f"Error recording processed signal: {e}")
    
    def load_new_signals(self) -> List[ExternalSignalData]:
        """Load new external signals from file"""
        signals = []
        try:
            if not self.external_signals_path.exists():
                return signals
            
            with self.external_signals_path.open("r") as f:
                lines = f.readlines()
                
            for line in lines:
                try:
                    signal_data = json.loads(line.strip())
                    
                    # Skip if already processed
                    if signal_data.get("processed", False):
                        continue
                    
                    # Skip if timestamp is older than our last processed
                    if signal_data.get("timestamp", 0) <= self.last_processed_timestamp:
                        continue
                    
                    signal = ExternalSignalData(
                        timestamp=signal_data.get("timestamp", 0),
                        symbol=signal_data.get("symbol", ""),
                        side=signal_data.get("side", ""),
                        signal_type=signal_data.get("signal_type", ""),
                        price=signal_data.get("price", 0.0),
                        reason=signal_data.get("reason", ""),
                        source=signal_data.get("source", ""),
                        confidence_score=signal_data.get("confidence_score", 0.8),
                        atr_value=signal_data.get("atr_value", 0.0),
                        exchange=signal_data.get("exchange", "CME")
                    )
                    
                    signals.append(signal)
                    
                except Exception as e:
                    print(f"Error parsing signal line: {e}")
                    continue
            
            # Sort by timestamp
            signals.sort(key=lambda x: x.timestamp)
            
        except Exception as e:
            print(f"Error loading signals: {e}")
        
        return signals
    
    async def process_new_signals(self) -> int:
        """Process all new external signals"""
        signals = self.load_new_signals()
        processed_count = 0
        
        for signal in signals:
            if await self.process_signal(signal):
                processed_count += 1
        
        return processed_count
    
    async def process_signal_from_data(self, signal_data: Dict[str, Any]) -> bool:
        """Process signal from dictionary data (from web API)"""
        try:
            signal = ExternalSignalData(
                timestamp=signal_data.get("timestamp", time.time()),
                symbol=signal_data.get("symbol", ""),
                side=signal_data.get("side", ""),
                signal_type=signal_data.get("signal_type", ""),
                price=signal_data.get("price", 0.0),
                reason=signal_data.get("reason", ""),
                source=signal_data.get("source", ""),
                confidence_score=signal_data.get("confidence_score", 0.8),
                atr_value=signal_data.get("atr_value", 0.0),
                exchange=signal_data.get("exchange", "CME")
            )
            
            return await self.process_signal(signal)
            
        except Exception as e:
            print(f"Error processing signal from data: {e}")
            return False
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get signal processing statistics"""
        current_time = time.time()
        
        # Count recent signals
        recent_signals = sum(1 for ts in self.processed_signals.values() 
                           if current_time - ts < 300.0)  # Last 5 minutes
        
        return {
            "last_processed_timestamp": self.last_processed_timestamp,
            "signals_processed_last_5min": recent_signals,
            "long_signals_enabled": self.long_signals_enabled,
            "short_signals_enabled": self.short_signals_enabled,
            "signal_cooldown_seconds": self.signal_cooldown_seconds,
            "max_signals_per_minute": self.max_signals_per_minute,
            "total_processed_signals": len(self.processed_signals)
        }
    
    def update_filters(self, long_enabled: bool, short_enabled: bool) -> None:
        """Update signal filter settings"""
        self.long_signals_enabled = long_enabled
        self.short_signals_enabled = short_enabled
        
        # Save to file
        try:
            filter_config = {
                "long_signals_enabled": long_enabled,
                "short_signals_enabled": short_enabled,
                "updated_at": time.time()
            }
            
            with self.signal_filters_path.open("w") as f:
                json.dump(filter_config, f)
                
            print(f"Updated signal filters: Long={long_enabled}, Short={short_enabled}")
                
        except Exception as e:
            print(f"Error saving filters: {e}")
    
    def get_filter_status(self) -> Dict[str, Any]:
        """Get current filter status"""
        return {
            "long_signals_enabled": self.long_signals_enabled,
            "short_signals_enabled": self.short_signals_enabled,
            "last_updated": time.time()
        }
    
    def enable_long_signals(self) -> None:
        """Enable long signals"""
        self.update_filters(True, self.short_signals_enabled)
    
    def disable_long_signals(self) -> None:
        """Disable long signals"""
        self.update_filters(False, self.short_signals_enabled)
    
    def enable_short_signals(self) -> None:
        """Enable short signals"""
        self.update_filters(self.long_signals_enabled, True)
    
    def disable_short_signals(self) -> None:
        """Disable short signals"""
        self.update_filters(self.long_signals_enabled, False)
    
    def enable_all_signals(self) -> None:
        """Enable all signals"""
        self.update_filters(True, True)
    
    def disable_all_signals(self) -> None:
        """Disable all signals"""
        self.update_filters(False, False)


# Global processor instance
_processor_instance: Optional[ExternalSignalProcessor] = None

def get_signal_processor() -> ExternalSignalProcessor:
    """Get global signal processor instance"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = ExternalSignalProcessor()
    return _processor_instance

async def process_external_signals_loop():
    """Background loop to process external signals"""
    processor = get_signal_processor()
    
    while True:
        try:
            processed_count = await processor.process_new_signals()
            if processed_count > 0:
                print(f"Processed {processed_count} external signals")
            
            # Wait before next check
            await asyncio.sleep(1.0)
            
        except Exception as e:
            print(f"Error in signal processing loop: {e}")
            await asyncio.sleep(5.0)
