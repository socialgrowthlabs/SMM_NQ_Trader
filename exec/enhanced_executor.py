import os
import uuid
import time
import pytz
from datetime import datetime, time as dt_time
from dataclasses import dataclass
from typing import Optional, Dict, List
from collections import deque
import yaml
import json
from pathlib import Path

from async_rithmic.enums import TransactionType, OrderType, OrderDuration
from exec.executor import ExecutionEngine, OrderIntent


@dataclass
class EnhancedOrderIntent(OrderIntent):
    """Enhanced order intent with additional strategy parameters"""
    entry_time: float
    max_hold_time: float
    breakeven_price: Optional[float] = None
    trail_price: Optional[float] = None
    momentum_exit_threshold: float = 0.3
    atr_value: float = 0.0
    confidence_score: float = 0.0


class EnhancedExecutionEngine(ExecutionEngine):
    """Enhanced execution engine with optimized position sizing, bracket sizing, and exit strategies"""
    
    def __init__(self) -> None:
        super().__init__()
        self.config = self._load_config()
        self.test_accounts = set(self.config.get("strategy", {}).get("test_accounts", []))
        self.trading_window_enabled = self.config.get("strategy", {}).get("trading_window", {}).get("enabled", False)
        self.trading_start_time = self.config.get("strategy", {}).get("trading_window", {}).get("start_time", "09:30")
        self.trading_end_time = self.config.get("strategy", {}).get("trading_window", {}).get("end_time", "10:00")
        self.timezone = pytz.timezone(self.config.get("strategy", {}).get("trading_window", {}).get("timezone", "America/New_York"))
        
        # Position sizing parameters
        self.position_config = self.config.get("strategy", {}).get("position_sizing", {})
        self.base_size = self.position_config.get("base_size", 1)
        self.max_size = self.position_config.get("max_size", 2)
        self.volatility_adjustment = self.position_config.get("volatility_adjustment", True)
        self.confidence_multiplier = self.position_config.get("confidence_multiplier", True)
        
        # Bracket parameters
        self.bracket_config = self.config.get("strategy", {}).get("bracket", {})
        self.target_ticks = self.bracket_config.get("target_ticks", 16)
        self.stop_ticks = self.bracket_config.get("stop_ticks", 8)
        self.dynamic_sizing = self.bracket_config.get("dynamic_sizing", True)
        self.atr_multiplier_target = self.bracket_config.get("atr_multiplier_target", 1.5)
        self.atr_multiplier_stop = self.bracket_config.get("atr_multiplier_stop", 0.8)
        
        # Exit strategy parameters
        self.exit_config = self.config.get("strategy", {}).get("exit_strategy", {})
        self.time_based_exit = self.exit_config.get("time_based_exit", True)
        self.max_hold_minutes = self.exit_config.get("max_hold_minutes", 15)
        self.profit_target_early = self.exit_config.get("profit_target_early", 8)
        self.breakeven_activation = self.exit_config.get("breakeven_activation", 6)
        self.momentum_exit = self.exit_config.get("momentum_exit", True)
        self.momentum_threshold = self.exit_config.get("momentum_threshold", 0.3)
        
        # Track active positions for exit management
        self.active_positions: Dict[str, EnhancedOrderIntent] = {}
        self.position_entry_times: Dict[str, float] = {}
        
    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        try:
            with open("config/config.yaml", "r") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def _is_trading_window_active(self) -> bool:
        """Check if current time is within the trading window"""
        if not self.trading_window_enabled:
            return True
            
        try:
            now = datetime.now(self.timezone).time()
            start_time = dt_time.fromisoformat(self.trading_start_time)
            end_time = dt_time.fromisoformat(self.trading_end_time)
            return start_time <= now <= end_time
        except Exception:
            return True  # Default to allowing trading if time check fails
    
    def _calculate_position_size(self, account_id: str, confidence_score: float, atr_value: float, current_price: float) -> int:
        """Calculate optimal position size based on confidence, volatility, and risk parameters"""
        if account_id not in self.test_accounts:
            try:
                print(f"QTY DEBUG: account {account_id} not in test_accounts => size=0", flush=True)
            except Exception:
                pass
            return 0
            
        base_size = self.base_size
        
        # Confidence multiplier (scale with delta confidence)
        if self.confidence_multiplier:
            confidence_factor = min(confidence_score / 0.6, 1.5)  # Scale up to 1.5x for high confidence
            base_size = int(base_size * confidence_factor)
        
        # Volatility adjustment (reduce size in high volatility)
        if self.volatility_adjustment and atr_value > 0:
            volatility_factor = max(0.5, 1.0 - (atr_value / current_price) * 100)  # Reduce size if ATR > 1% of price
            base_size = int(base_size * volatility_factor)
        
        # Ensure within bounds
        qty = max(1, min(base_size, self.max_size))
        try:
            print(f"QTY DEBUG: account={account_id} qty={qty} base={self.base_size} conf={confidence_score:.3f} atr={atr_value:.5f}", flush=True)
        except Exception:
            pass
        return qty
    
    def _calculate_bracket_levels(self, entry_price: float, side: str, atr_value: float, signal_price: Optional[float] = None) -> tuple[int, int]:
        """Calculate dynamic bracket levels based on SMM signal prices or ATR"""
        use_signal_targets = self.bracket_config.get("use_signal_targets", True)
        
        if use_signal_targets and signal_price is not None:
            # Use SMM signal-based targets (matches NinjaTrader approach)
            target_multiplier = self.bracket_config.get("target_multiplier", 1.5)
            stop_multiplier = self.bracket_config.get("stop_multiplier", 0.8)
            
            if side.upper() == "BUY":
                target_price = signal_price * target_multiplier
                stop_price = signal_price * stop_multiplier
            else:  # SELL
                target_price = signal_price * stop_multiplier  # Target is lower for SELL
                stop_price = signal_price * target_multiplier   # Stop is higher for SELL
            
            # Convert to ticks
            target_ticks = max(4, int(abs(target_price - entry_price) / 0.25))
            stop_ticks = max(4, int(abs(stop_price - entry_price) / 0.25))
        elif self.dynamic_sizing and atr_value > 0:
            # Use ATR-based sizing
            target_ticks = max(8, int(atr_value * self.atr_multiplier_target / 0.25))  # Convert to ticks
            stop_ticks = max(4, int(atr_value * self.atr_multiplier_stop / 0.25))
        else:
            # Use fallback fixed sizing
            target_ticks = self.bracket_config.get("fallback_target_ticks", 16)
            stop_ticks = self.bracket_config.get("fallback_stop_ticks", 8)
            
        return target_ticks, stop_ticks
    
    def _should_allow_order(self, account_id: str, side: str, qty: int) -> tuple[bool, str]:
        """Enhanced order validation with account restrictions and time window"""
        # Check if account is in test accounts
        if self.test_accounts and account_id not in self.test_accounts:
            return False, "not_test_account"
            
        # Check trading window
        if not self._is_trading_window_active():
            return False, "outside_trading_window"
            
        # Use parent validation
        return super()._should_allow_order(account_id, side, qty)
    
    async def submit_enhanced_signal(
        self, 
        symbol: str, 
        side: str, 
        confidence_score: float,
        atr_value: float,
        current_price: float,
        accounts: List[str],
        signal_price: Optional[float] = None,
        exchange: Optional[str] = None
    ) -> List[EnhancedOrderIntent]:
        """Submit signal with enhanced position sizing and bracket optimization"""
        intents: List[EnhancedOrderIntent] = []
        try:
            print(f"ENHANCED SUBMIT: symbol={symbol} side={side} accounts={accounts}", flush=True)
        except Exception:
            pass
        
        for acc in accounts:
            if not self.account_enabled.get(acc, False):
                try:
                    print(f"SUBMIT SKIP: account {acc} not enabled", flush=True)
                except Exception:
                    pass
                continue
                
            # Calculate optimal position size
            qty = self._calculate_position_size(acc, confidence_score, atr_value, current_price)
            if qty <= 0:
                try:
                    print(f"SUBMIT SKIP: account {acc} qty<=0", flush=True)
                except Exception:
                    pass
                continue
                
            # Calculate dynamic bracket levels using SMM signal price
            target_ticks, stop_ticks = self._calculate_bracket_levels(current_price, side, atr_value, signal_price)
            
            # Check if order should be allowed
            allow, reason = self._should_allow_order(acc, side, qty)
            if not allow:
                try:
                    print(f"SUBMIT SKIP: account {acc} not allowed reason={reason}", flush=True)
                except Exception:
                    pass
                continue
                
            coid = self._new_client_order_id(acc)
            entry_time = time.time()
            max_hold_time = entry_time + (self.max_hold_minutes * 60)
            
            intent = EnhancedOrderIntent(
                account_id=acc,
                symbol=symbol,
                side=side,
                qty=qty,
                client_order_id=coid,
                target_ticks=target_ticks,
                stop_ticks=stop_ticks,
                entry_time=entry_time,
                max_hold_time=max_hold_time,
                atr_value=atr_value,
                confidence_score=confidence_score
            )
            
            self.open_orders[acc][coid] = intent
            self.active_positions[coid] = intent
            self.position_entry_times[coid] = entry_time
            intents.append(intent)
            self._record_order_time(acc)
            
            # Submit live order if enabled
            if self.trading_enabled and self.order_plant is not None and acc in self.whitelist:
                try:
                    print(f"LIVE SUBMIT: acc={acc} coid={coid} qty={qty} target={target_ticks} stop={stop_ticks} exch={exchange or self.default_exchange}", flush=True)
                except Exception:
                    pass
                try:
                    tx = TransactionType.BUY if side.upper() == "BUY" else TransactionType.SELL
                    ot = OrderType.MARKET
                    ex = exchange or self.default_exchange or "CME"
                    await self.order_plant.submit_order(
                        order_id=coid,
                        symbol=symbol,
                        exchange=ex,
                        qty=qty,
                        transaction_type=tx,
                        order_type=ot,
                        account_id=acc,
                        target_ticks=target_ticks,
                        stop_ticks=stop_ticks,
                        duration=OrderDuration.DAY
                    )
                except Exception:
                    pass
            else:
                try:
                    print(f"LIVE SUBMIT SKIP: acc={acc} trading_enabled={self.trading_enabled} plant={self.order_plant is not None} whitelisted={acc in self.whitelist}", flush=True)
                except Exception:
                    pass
                    
        return intents
    
    def update_position_momentum(self, client_order_id: str, momentum_score: float) -> None:
        """Update momentum score for position exit decisions"""
        if client_order_id in self.active_positions:
            self.active_positions[client_order_id].momentum_exit_threshold = momentum_score
    
    def check_exit_conditions(self, client_order_id: str, current_price: float, unrealized_pnl: float) -> Optional[str]:
        """Check if position should be exited based on various conditions"""
        if client_order_id not in self.active_positions:
            return None
            
        intent = self.active_positions[client_order_id]
        current_time = time.time()
        
        # Time-based exit
        if self.time_based_exit and current_time >= intent.max_hold_time:
            return "time_exit"
            
        # Early profit target
        if unrealized_pnl >= self.profit_target_early * 0.25:  # Convert ticks to dollars
            return "early_profit"
            
        # Breakeven activation
        if intent.breakeven_price is None and unrealized_pnl >= self.breakeven_activation * 0.25:
            intent.breakeven_price = intent.entry_time  # Set breakeven at entry
            return "breakeven_activated"
            
        # Momentum-based exit
        if self.momentum_exit and intent.momentum_exit_threshold < self.momentum_threshold:
            return "momentum_exit"
            
        return None
    
    def get_active_positions_summary(self) -> Dict[str, dict]:
        """Get summary of all active positions for monitoring"""
        summary = {}
        current_time = time.time()
        
        for coid, intent in self.active_positions.items():
            time_in_position = current_time - intent.entry_time
            summary[coid] = {
                "account_id": intent.account_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": intent.qty,
                "entry_time": intent.entry_time,
                "time_in_position_minutes": time_in_position / 60,
                "target_ticks": intent.target_ticks,
                "stop_ticks": intent.stop_ticks,
                "confidence_score": intent.confidence_score,
                "atr_value": intent.atr_value,
                "breakeven_price": intent.breakeven_price,
                "trail_price": intent.trail_price
            }
            
        return summary

