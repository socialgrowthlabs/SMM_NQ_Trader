"""
Enhanced SMM Strategy Implementation
Implements DI+/DI- chop filter, delta surge detection, and debounce logic
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
from dataclasses import dataclass
from collections import deque


@dataclass
class EnhancedSignalConfig:
    """Configuration for enhanced SMM signals"""
    # Chop filter parameters
    di_len: int = 14
    di_thresh: float = 45.0
    
    # Delta surge parameters
    delta_lookback: int = 50
    delta_z: float = 2.0
    
    # Debounce parameters
    confirm_bars: int = 2
    cooldown: int = 3
    
    # Price bias parameters
    use_heiken: bool = True
    use_profitwave: bool = True
    profitwave_fast: int = 34
    profitwave_slow: int = 144
    
    # Optional filters
    atr_len: int = 14


@dataclass
class EnhancedSignalResult:
    """Result of enhanced signal generation"""
    di_plus: float
    di_minus: float
    chop_long_gate: bool
    chop_short_gate: bool
    delta: float
    delta_z: float
    delta_surge_long: bool
    delta_surge_short: bool
    price_bias_long: bool
    price_bias_short: bool
    long_signal: bool
    short_signal: bool
    signal_side: Optional[str]  # "BUY", "SELL", or None


class EnhancedSMMEngine:
    """Enhanced SMM strategy engine with chop filter, delta surge, and debounce"""
    
    def __init__(self, config: EnhancedSignalConfig):
        self.config = config
        self.bars = deque(maxlen=max(config.delta_lookback, config.profitwave_slow) + 10)
        self.delta_history = deque(maxlen=config.delta_lookback)
        
        # State tracking for debounce and cooldown
        self.long_confirmation_count = 0
        self.short_confirmation_count = 0
        self.cooldown_long = 0
        self.cooldown_short = 0
        self.last_signal_side = None
        
    def add_bar(self, open_price: float, high: float, low: float, close: float, 
                volume: float, delta: Optional[float] = None, 
                ask_vol: Optional[float] = None, bid_vol: Optional[float] = None):
        """Add a new bar to the engine"""
        # Calculate delta if not provided
        if delta is None:
            if ask_vol is not None and bid_vol is not None:
                delta = ask_vol - bid_vol
            else:
                delta = 0.0  # Fallback
        
        bar = {
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'delta': delta
        }
        
        self.bars.append(bar)
        self.delta_history.append(delta)
        
    def _calculate_di(self, bars: list) -> tuple[float, float]:
        """Calculate DI+ and DI- using Wilder's method"""
        if len(bars) < self.config.di_len:
            return 0.0, 0.0
        
        # Convert to pandas for easier calculation
        df = pd.DataFrame(bars)
        
        # Calculate directional movement
        up_move = df['high'].diff()
        dn_move = -df['low'].diff()
        
        plus_dm = ((up_move > dn_move) & (up_move > 0)).astype(float) * up_move.clip(lower=0.0)
        minus_dm = ((dn_move > up_move) & (dn_move > 0)).astype(float) * dn_move.clip(lower=0.0)
        
        # Calculate True Range
        tr = np.maximum(df['high'] - df['low'], 
                       np.maximum((df['high'] - df['close'].shift()).abs(),
                                 (df['low'] - df['close'].shift()).abs()))
        
        # Wilder smoothing (EMA with alpha = 1/length)
        alpha = 1.0 / self.config.di_len
        tr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_dm_smooth = plus_dm.ewm(alpha=alpha, adjust=False).mean()
        minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False).mean()
        
        # Calculate DI+ and DI-
        di_plus = np.where(tr_smooth != 0, 100.0 * (plus_dm_smooth / tr_smooth), 0.0)
        di_minus = np.where(tr_smooth != 0, 100.0 * (minus_dm_smooth / tr_smooth), 0.0)
        
        return float(di_plus[-1]), float(di_minus[-1])
    
    def _calculate_heiken_ashi(self, bars: list) -> tuple[float, float]:
        """Calculate Heiken-Ashi close and open"""
        if len(bars) < 2:
            return bars[-1]['close'], bars[-1]['open']
        
        current = bars[-1]
        previous = bars[-2]
        
        # HA Close = (O + H + L + C) / 4
        ha_close = (current['open'] + current['high'] + current['low'] + current['close']) / 4
        
        # HA Open = (Previous HA Open + Previous HA Close) / 2
        if len(bars) == 2:
            ha_open = (previous['open'] + previous['close']) / 2
        else:
            # For simplicity, use regular open for first bar
            ha_open = (previous['open'] + previous['close']) / 2
        
        return ha_close, ha_open
    
    def _calculate_ema(self, values: list, length: int) -> float:
        """Calculate EMA for given values"""
        if len(values) < length:
            return values[-1] if values else 0.0
        
        series = pd.Series(values)
        ema = series.ewm(span=length, adjust=False).mean()
        return float(ema.iloc[-1])
    
    def _calculate_delta_zscore(self, delta: float) -> float:
        """Calculate z-score for delta surge detection"""
        if len(self.delta_history) < self.config.delta_lookback // 2:
            return 0.0
        
        values = list(self.delta_history)
        mean = np.mean(values)
        std = np.std(values, ddof=0)
        
        if std == 0:
            return 0.0
        
        return (delta - mean) / std
    
    def generate_signal(self) -> EnhancedSignalResult:
        """Generate enhanced signal based on current bar data"""
        if len(self.bars) < max(self.config.di_len, self.config.confirm_bars):
            print(f"Enhanced SMM: Not ready, bars={len(self.bars)}, need={max(self.config.di_len, self.config.confirm_bars)}", flush=True)
            return EnhancedSignalResult(
                di_plus=0.0, di_minus=0.0,
                chop_long_gate=False, chop_short_gate=False,
                delta=0.0, delta_z=0.0,
                delta_surge_long=False, delta_surge_short=False,
                price_bias_long=False, price_bias_short=False,
                long_signal=False, short_signal=False,
                signal_side=None
            )
        
        current_bar = self.bars[-1]
        delta = current_bar['delta']
        
        # Calculate DI+ and DI-
        di_plus, di_minus = self._calculate_di(list(self.bars))
        
        # Chop filter gates - fixed logic
        chop_long_gate = (di_plus > di_minus) and (di_plus >= self.config.di_thresh)
        chop_short_gate = (di_minus > di_plus) and (di_minus >= self.config.di_thresh)
        print(f"CHOP DEBUG: di_plus={di_plus:.1f}, di_minus={di_minus:.1f}, thresh={self.config.di_thresh}, long_gate={chop_long_gate}, short_gate={chop_short_gate}", flush=True)
        
        # Delta surge detection
        delta_z = self._calculate_delta_zscore(delta)
        delta_surge_long = delta_z >= self.config.delta_z
        delta_surge_short = delta_z <= -self.config.delta_z
        print(f"DEBUG: delta_z={delta_z}, config.delta_z={self.config.delta_z}, surge_long={delta_surge_long}, surge_short={delta_surge_short}", flush=True)
        
        # Price bias (Heiken-Ashi and/or Profit-Wave) - RESTORED PROPER LOGIC
        if self.config.use_heiken:
            ha_close, ha_open = self._calculate_heiken_ashi(list(self.bars))
            price_bias_long = ha_close > ha_open
            price_bias_short = ha_close < ha_open
        else:
            # Light bias using EMA(3)
            closes = [bar['close'] for bar in self.bars]
            ema3 = self._calculate_ema(closes, 3)
            price_bias_long = current_bar['close'] > ema3
            price_bias_short = current_bar['close'] < ema3
        
        if self.config.use_profitwave:
            closes = [bar['close'] for bar in self.bars]
            ema_fast = self._calculate_ema(closes, self.config.profitwave_fast)
            ema_slow = self._calculate_ema(closes, self.config.profitwave_slow)
            
            price_bias_long = price_bias_long and (current_bar['close'] >= ema_fast) and (ema_fast >= ema_slow)
            price_bias_short = price_bias_short and (current_bar['close'] <= ema_fast) and (ema_fast <= ema_slow)
        
        # Raw signal conditions
        long_raw = chop_long_gate and delta_surge_long and price_bias_long
        short_raw = chop_short_gate and delta_surge_short and price_bias_short
        
        # Debounce (confirmation)
        if long_raw:
            self.long_confirmation_count += 1
            self.short_confirmation_count = 0
        elif short_raw:
            self.short_confirmation_count += 1
            self.long_confirmation_count = 0
        else:
            self.long_confirmation_count = 0
            self.short_confirmation_count = 0
        
        long_confirmed = self.long_confirmation_count >= self.config.confirm_bars
        short_confirmed = self.short_confirmation_count >= self.config.confirm_bars
        
        # Hysteresis/Cooldown
        if self.cooldown_long > 0:
            self.cooldown_long -= 1
        if self.cooldown_short > 0:
            self.cooldown_short -= 1
        
        # Apply cooldown blocks
        long_signal = long_confirmed and self.cooldown_long == 0
        short_signal = short_confirmed and self.cooldown_short == 0
        
        # Mutual exclusion - prefer higher |delta_z|
        signal_side = None
        if long_signal and short_signal:
            if abs(delta_z) == 0:
                long_signal = False
                short_signal = False
            else:
                if delta_z > 0:
                    short_signal = False
                    signal_side = "BUY"
                else:
                    long_signal = False
                    signal_side = "SELL"
        elif long_signal:
            signal_side = "BUY"
            self.cooldown_short = self.config.cooldown
        elif short_signal:
            signal_side = "SELL"
            self.cooldown_long = self.config.cooldown
        
        # Debug logging
        if signal_side:
            print(f"Enhanced SMM Signal: {signal_side} | DI+={di_plus:.1f}, DI-={di_minus:.1f} | delta_z={delta_z:.2f} | chop_long={chop_long_gate}, chop_short={chop_short_gate} | surge_long={delta_surge_long}, surge_short={delta_surge_short} | bias_long={price_bias_long}, bias_short={price_bias_short}", flush=True)
        else:
            # Debug why no signal
            print(f"Enhanced SMM No Signal: DI+={di_plus:.1f}, DI-={di_minus:.1f} | delta_z={delta_z:.2f} | chop_long={chop_long_gate}, chop_short={chop_short_gate} | surge_long={delta_surge_long}, surge_short={delta_surge_short} | bias_long={price_bias_long}, bias_short={price_bias_short} | long_raw={long_raw}, short_raw={short_raw} | long_conf={long_confirmed}, short_conf={short_confirmed}", flush=True)
        
        return EnhancedSignalResult(
            di_plus=di_plus,
            di_minus=di_minus,
            chop_long_gate=chop_long_gate,
            chop_short_gate=chop_short_gate,
            delta=delta,
            delta_z=delta_z,
            delta_surge_long=delta_surge_long,
            delta_surge_short=delta_surge_short,
            price_bias_long=price_bias_long,
            price_bias_short=price_bias_short,
            long_signal=long_signal,
            short_signal=short_signal,
            signal_side=signal_side
        )
    
    def is_ready(self) -> bool:
        """Check if engine has enough data for reliable signals"""
        return len(self.bars) >= max(self.config.di_len, self.config.confirm_bars)


def create_enhanced_config(config_dict: Optional[Dict[str, Any]] = None) -> EnhancedSignalConfig:
    """Create enhanced signal configuration from config or defaults"""
    if config_dict is None:
        config_dict = {}
    
    return EnhancedSignalConfig(
        di_len=config_dict.get("di_len", 14),
        di_thresh=config_dict.get("di_thresh", 25.0),  # Restored threshold for chop filter
        delta_lookback=config_dict.get("delta_lookback", 50),
        delta_z=config_dict.get("delta_z", 1.5),  # Restored threshold for delta surge
        confirm_bars=config_dict.get("confirm_bars", 2),
        cooldown=config_dict.get("cooldown", 3),
        use_heiken=config_dict.get("use_heiken", True),
        use_profitwave=config_dict.get("use_profitwave", True),
        profitwave_fast=config_dict.get("profitwave_fast", 34),
        profitwave_slow=config_dict.get("profitwave_slow", 144),
        atr_len=config_dict.get("atr_len", 14)
    )
