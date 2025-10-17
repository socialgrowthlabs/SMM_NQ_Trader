# SMM Signal Calculation - Exact Logic

## Overview
The SMM strategy uses a multi-layered signal calculation system with EMA55 trend filtering and delta confidence confirmation.

## Signal Calculation Flow

### 1. Main SMM Engine (`core/smm/main.py`)

#### Input Data
- `last_price`: Current market price
- `features`: FeatureSnapshot with delta_confidence
- EMA values: EMA8, EMA13, EMA21, EMA55
- Indicators: ATR, MFI, DI+/DI-

#### Step 1: EMA55 Trend Filtering
```python
# Calculate EMA slopes
ema21_slope = ema21.constant1 * (last_price - ema21_val)
ema55_slope = ema55.constant1 * (last_price - ema55_val)

# Determine trend alignment
trend_bullish = (last_price > ema21_val and ema21_slope >= 0.0 and 
                 last_price > ema55_val and ema55_slope >= 0.0)
trend_bearish = (last_price < ema21_val and ema21_slope <= 0.0 and 
                 last_price < ema55_val and ema55_slope <= 0.0)
```

#### Step 2: Strong Candle Detection
```python
# Using Heiken Ashi or regular OHLC
src_open = ha_state.open if use_heiken_ashi else last_price
src_low = ha_state.low if use_heiken_ashi else last_price
src_high = ha_state.high if use_heiken_ashi else last_price

# Strong candle conditions
strong_bull = (last_price > src_open) and (src_open == src_low) and 
              (last_price > ema8_val) and (last_price > ema21_val)
strong_bear = (last_price < src_open) and (src_open == src_high) and 
              (last_price < ema8_val) and (last_price < ema21_val)
```

#### Step 3: Chop Filters
```python
# Directional Index filter
can_buy = (di_plus > di_minus and di_plus >= 45.0)
can_sell = (di_minus > di_plus and di_minus >= 45.0)

# Money Flow Index filter
mfi_buy = (mfi_val > 52.0) if mfi_val == mfi_val else True
mfi_sell = (mfi_val < 48.0) if mfi_val == mfi_val else True

# MA filter (EMA13)
ma_buy_ok = last_price > ema13_val
ma_sell_ok = last_price < ema13_val
```

#### Step 4: Combined Conditions
```python
# Primary SMM signal conditions
buy_con = trend_bullish and strong_bull and can_buy and mfi_buy and ma_buy_ok
sell_con = trend_bearish and strong_bear and can_sell and mfi_sell and ma_sell_ok
```

#### Step 5: Delta Confidence Confirmation
```python
# Final signal generation
if buy_con and features.delta_confidence >= 0.65:
    side = "BUY"
    reason = "SMM+delta>=thr"
elif sell_con and (1.0 - features.delta_confidence) >= 0.65:
    side = "SELL"
    reason = "SMM+delta<=1-thr"
else:
    side = None
    reason = "hold"
```

### 2. Combined Signal Engine (`core/smm/combined.py`)

#### Step 1: Get Main Decision
```python
main_decision = self.main.evaluate(last_price, features)
```

#### Step 2: Determine Trend State
```python
# Use EMA55 trend filtering (no background bands needed)
trend_state = 1 if main_decision.trend_bullish else (-1 if main_decision.trend_bearish else 0)
```

#### Step 3: Final Signal Logic
```python
# Prefer main decision if its side agrees with trend
if main_decision.side == "BUY" and trend_state == 1:
    final_side = "BUY"
    reason = main_decision.reason or "main_buy"
elif main_decision.side == "SELL" and trend_state == -1:
    final_side = "SELL"
    reason = main_decision.reason or "main_sell"
else:
    final_side = None
    reason = "trend_mismatch" or "hold"
```

## Signal Requirements Summary

### BUY Signal Requirements
1. **Trend Alignment**: `trend_bullish = True`
   - Price > EMA21 AND EMA21 slope ≥ 0
   - Price > EMA55 AND EMA55 slope ≥ 0

2. **Strong Candle**: `strong_bull = True`
   - Price > open AND open == low
   - Price > EMA8 AND Price > EMA21

3. **Chop Filters**: All must pass
   - `can_buy = True` (DI+ > DI- AND DI+ ≥ 45)
   - `mfi_buy = True` (MFI > 52)
   - `ma_buy_ok = True` (Price > EMA13)

4. **Delta Confidence**: `delta_confidence ≥ 0.65`

5. **Final Check**: `trend_state == 1` (bullish)

### SELL Signal Requirements
1. **Trend Alignment**: `trend_bearish = True`
   - Price < EMA21 AND EMA21 slope ≤ 0
   - Price < EMA55 AND EMA55 slope ≤ 0

2. **Strong Candle**: `strong_bear = True`
   - Price < open AND open == high
   - Price < EMA8 AND Price < EMA21

3. **Chop Filters**: All must pass
   - `can_sell = True` (DI- > DI+ AND DI- ≥ 45)
   - `mfi_sell = True` (MFI < 48)
   - `ma_sell_ok = True` (Price < EMA13)

4. **Delta Confidence**: `(1.0 - delta_confidence) ≥ 0.65`

5. **Final Check**: `trend_state == -1` (bearish)

## Key Parameters

### Thresholds
- **Delta Confidence**: 0.65 (65%)
- **DI Threshold**: 45.0
- **MFI Buy**: 52.0
- **MFI Sell**: 48.0

### EMA Periods
- **EMA8**: 8 periods
- **EMA13**: 13 periods  
- **EMA21**: 21 periods
- **EMA55**: 55 periods (trend filter)

### Signal Generation
- **Heiken Ashi**: Enabled by default
- **MA Filter**: EMA13-based
- **Trend Override**: EMA21+EMA55 alignment

## Testing Modes

### Loose Testing (`TESTING_LOOSE=1`)
```python
if features.delta_confidence >= 0.65 and trend_state == 1:
    return "BUY"
if (1.0 - features.delta_confidence) >= 0.65 and trend_state == -1:
    return "SELL"
```

### Sell Bias Testing (`TESTING_SELL_BIAS=1`)
```python
if trend_state == -1:
    return "SELL"
```

## Signal Quality Factors

### High Quality Signals
- All conditions met simultaneously
- Strong trend alignment (EMA21 + EMA55)
- High delta confidence (≥0.65)
- Clear strong candle pattern
- All chop filters passing

### Signal Rejection Reasons
- `trend_mismatch`: Main signal doesn't align with trend
- `hold`: Conditions not met
- `delta_too_low`: Confidence below threshold
- `chop_filter_fail`: DI/MFI/MA filters not passing

## Current Configuration
- **Delta Threshold**: 0.65
- **EMA55 Trend Filter**: Enabled
- **Heiken Ashi**: Enabled
- **MA Filter**: EMA13-based
- **Testing Modes**: Disabled
- **Cross-Source Confirmation**: Enabled
