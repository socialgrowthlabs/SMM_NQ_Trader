# Enhanced SMM Strategy - High Win Rate & Low Drawdown

## Overview
The enhanced SMM (Simple Money Metrics) strategy has been optimized for high win rate and low drawdown, specifically targeting the 9:30-10:00 AM ET trading window on test accounts 166 and 167.

## Key Optimizations

### 1. Position Sizing Strategy
- **Base Size**: 1 contract (configurable)
- **Max Size**: 2 contracts (reduced from 4)
- **Volatility Adjustment**: Scales position size based on ATR
- **Confidence Multiplier**: Increases position size with higher delta confidence (up to 1.5x)

### 2. Bracket Order Optimization
- **Target**: 16 ticks (reduced from 20)
- **Stop**: 8 ticks (reduced from 12)
- **Dynamic Sizing**: Uses ATR-based calculations
  - Target = 1.5 × ATR
  - Stop = 0.8 × ATR
- **Trailing**: Activates after 4 ticks profit, trails in 2-tick steps

### 3. Exit Strategy Enhancements
- **Time-based Exit**: Maximum 15 minutes hold time
- **Early Profit Target**: Take profit at 8 ticks
- **Breakeven Activation**: Move to breakeven after 6 ticks profit
- **Momentum Exit**: Exit if momentum drops below 0.3 threshold

### 4. Time Window Restrictions
- **Active Window**: 9:30-10:00 AM ET only
- **Timezone**: America/New_York
- **Outside Window**: No trading allowed

### 5. Account Restrictions
- **Test Accounts**: Only APEX-196119-166 and APEX-196119-167
- **Whitelist**: Controlled via WHITELIST_ACCOUNTS environment variable

### 6. Risk Management
- **Daily Drawdown**: Reduced to $150 (from $250)
- **Position Limit**: 2 contracts max
- **Order Frequency**: 30 orders/minute max
- **Slippage Control**: 1 tick maximum

## Configuration Files

### config/config.yaml
```yaml
strategy:
  delta_confidence_threshold: 0.65  # Higher threshold
  trading_window:
    enabled: true
    start_time: "09:30"
    end_time: "10:00"
    timezone: "America/New_York"
  test_accounts: ["APEX-196119-166", "APEX-196119-167"]
  position_sizing:
    base_size: 1
    max_size: 2
    volatility_adjustment: true
    confidence_multiplier: true
  bracket:
    target_ticks: 16
    stop_ticks: 8
    dynamic_sizing: true
    atr_multiplier_target: 1.5
    atr_multiplier_stop: 0.8
  exit_strategy:
    time_based_exit: true
    max_hold_minutes: 15
    profit_target_early: 8
    breakeven_activation: 6
    momentum_exit: true
    momentum_threshold: 0.3
```

### config/strategy_config.yaml
Additional strategy configuration with environment overrides.

## Monitoring Tools

### Strategy Monitor
```bash
# Check current status
python3 scripts/strategy_monitor.py

# Watch mode (continuous monitoring)
python3 scripts/strategy_monitor.py --watch --interval 10
```

### Key Metrics Tracked
- Trading window status
- Signal generation (buy/sell counts)
- Average confidence scores
- Account performance (P&L, positions)
- System health (plants status)
- Error counts

## Implementation Details

### Enhanced Execution Engine
- **File**: `exec/enhanced_executor.py`
- **Features**:
  - Dynamic position sizing
  - ATR-based bracket calculations
  - Time window validation
  - Account restrictions
  - Exit condition monitoring

### Client Integration
- **File**: `rithmic/client.py`
- **Changes**:
  - Uses `EnhancedExecutionEngine`
  - Passes confidence scores and ATR values
  - Integrates with SMM strategy engine

## Expected Performance

### Win Rate Target
- **Goal**: 70%+ win rate
- **Method**: Higher confidence threshold (0.65), tighter targets/stops

### Drawdown Control
- **Goal**: <$150 daily drawdown
- **Method**: Smaller position sizes, tighter stops, time-based exits

### Risk/Reward
- **Target**: 16 ticks
- **Stop**: 8 ticks
- **Ratio**: 2:1 risk/reward

## Usage Instructions

1. **Start the Enhanced Client**:
   ```bash
   cd '/root/SMM NQ Trader'
   python3 -m rithmic.client
   ```

2. **Monitor Performance**:
   ```bash
   python3 scripts/strategy_monitor.py --watch
   ```

3. **Check Trading Window**:
   - Strategy only trades between 9:30-10:00 AM ET
   - Outside this window, no signals will be executed

4. **Account Management**:
   - Only accounts 166 and 167 will receive orders
   - Other accounts are ignored for testing

## Environment Variables

```bash
# Core trading settings
TRADING_ENABLED=1
DELTA_CONFIDENCE_THRESHOLD=0.65
TREND_OVERRIDE=ema21
REQUIRE_XSOURCE=1

# Testing flags
TESTING_LOOSE=0
TESTING_SELL_BIAS=0

# Account whitelist
WHITELIST_ACCOUNTS=APEX-196119-166,APEX-196119-167
```

## Troubleshooting

### Common Issues
1. **No Signals Generated**: Check confidence threshold and market conditions
2. **Orders Not Executed**: Verify trading window and account whitelist
3. **High Drawdown**: Check position sizing and stop levels
4. **System Health Issues**: Monitor plant status in strategy monitor

### Logs
- Client logs: `/tmp/client_run.log`
- Strategy monitor: Real-time status display
- Dashboard: `http://74.63.231.90/` (password: letmein)

## Future Enhancements

### Planned Improvements
1. **Machine Learning**: Confidence score optimization
2. **Market Regime Detection**: Adjust parameters based on market conditions
3. **Portfolio Heat**: Dynamic position sizing based on correlation
4. **Advanced Exits**: Trailing stops with momentum confirmation

### Performance Optimization
1. **Latency Reduction**: Faster signal processing
2. **Slippage Control**: Better order routing
3. **Risk Controls**: Real-time position monitoring
4. **Backtesting**: Historical performance validation

