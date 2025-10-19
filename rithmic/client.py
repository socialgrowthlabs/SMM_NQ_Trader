import asyncio
import os
from typing import List

import uvloop
import traceback
from async_rithmic import RithmicClient, DataType
from dotenv import load_dotenv
import yaml
import json
import time
from pathlib import Path
import numpy as np
from core.features import FeatureEngine
from core.bar_features import BarFeatureEngine, BarData
from core.signals import SignalEngine
from exec.executor import ExecutionEngine
from exec.enhanced_executor import EnhancedExecutionEngine
from core.smm.combined import SMMCombinedSignal
from core.smm.main import SMMMainEngine
from core.smm.enhanced import EnhancedSMMEngine, create_enhanced_config
from core.bars import BarAggregator, TBarsAggregator

async def run_trader(seconds: int) -> None:
    print(f"BOOT: run_trader seconds={seconds}", flush=True)
    user = os.getenv("RITHMIC_USERNAME", "")
    password = os.getenv("RITHMIC_PASSWORD", "")
    system_name = os.getenv("RITHMIC_SYSTEM", "")
    app_name = os.getenv("APP_NAME", "SMMNQTrader")
    app_version = os.getenv("APP_VERSION", "0.1.0")
    url = os.getenv("RITHMIC_URL", "")
    exchange = os.getenv("RITHMIC_EXCHANGE", "CME")
    symbols_env = os.getenv("RITHMIC_SYMBOLS", "NQZ5,MNQZ5")
    symbols: List[str] = [s.strip() for s in symbols_env.split(",") if s.strip()]
    depth_tick = float(os.getenv("DEPTH_TICK", "0.25"))
    if not (user and password and system_name and url):
        raise RuntimeError("Missing required env: RITHMIC_USERNAME,RITHMIC_PASSWORD,RITHMIC_SYSTEM,RITHMIC_URL")

    client = RithmicClient(
        user=user,
        password=password,
        system_name=system_name,
        app_name=app_name,
        app_version=app_version,
        url=url,
    )

    ticker = client.plants["ticker"]
    orders = client.plants["order"]
    pnl = client.plants["pnl"]

    # Load strategy params from config
    strategy_ema = 21
    strategy_ema_trend = 55  # EMA55 for trend filtering
    delta_thresh = 0.6
    try:
        with open("config/config.yaml", "r") as f:
            cfg = yaml.safe_load(f) or {}
            usernames = cfg.get("usernames") or []
            strat = (usernames[0] or {}).get("strategy", {}) if usernames else {}
            strategy_ema = int(strat.get("ema_period", strategy_ema))
            strategy_ema_trend = int(strat.get("ema_trend_period", strategy_ema_trend))
            delta_thresh = float(strat.get("delta_confidence_threshold", delta_thresh))
    except Exception:
        pass

    features = FeatureEngine(window=256)
    bar_features = BarFeatureEngine(window=20)  # Bar-based features
    signals = SignalEngine(ema_period=strategy_ema, delta_threshold=delta_thresh)
    
    # Bar-level delta accumulation
    current_bar_buy_volume = 0.0
    current_bar_sell_volume = 0.0
    
    # Initialize Enhanced SMM Engine with chop filter, delta surge, and debounce
    enhanced_config_dict = {}
    try:
        with open("config/config.yaml", "r") as f:
            cfg = yaml.safe_load(f) or {}
            enhanced_config_dict = cfg.get("strategy", {}).get("enhanced_smm", {})
    except Exception:
        pass
    
    enhanced_config = create_enhanced_config(enhanced_config_dict)
    enhanced_smm = EnhancedSMMEngine(enhanced_config)
    
    # Keep original SMM for compatibility
    combined = SMMCombinedSignal(delta_threshold=delta_thresh)
    combined.main = SMMMainEngine(
        ema_period=strategy_ema,
        ema_trend_period=strategy_ema_trend,
        delta_threshold=delta_thresh
    )
    # Live trading configuration - use configured thresholds
    print(f"Live trading: delta threshold set to {delta_thresh}", flush=True)
    # Use enhanced executor for optimized strategy
    executor = EnhancedExecutionEngine()
    executor.attach_order_plant(orders, exchange)
    # Aggregators: 1-minute bars and TBars (e.g., 233 ticks)
    bars_time = BarAggregator(mode="time", duration_sec=60)
    bars_ticks = BarAggregator(mode="ticks", ticks_per_bar=int(os.getenv("TBAR_TICKS", "233")))
    bars_t12 = TBarsAggregator(base_size=int(os.getenv("TBAR_BASE_SIZE", "12")), tick_size=float(os.getenv("TICK_SIZE", "0.25")))

    tick_count = 0
    depth_count = 0
    pnl_count = 0
    last_price: float = 0.0
    last_tick_ts: float = 0.0
    last_depth_ts: float = 0.0
    last_pnl_ts: float = 0.0
    # Track last best bid/ask for aggressor inference when missing
    last_best_bid: float = 0.0
    last_best_ask: float = 0.0
    tick_size: float = float(os.getenv("TICK_SIZE", "0.25"))
    start_ts: float = time.time()
    error_count: int = 0
    plant_status = {"ticker": False, "order": False, "pnl": False}
    diag_tick_dumped = 0
    diag_depth_dumped = 0
    diag_tick_written = False
    diag_depth_written = False
    diag_pnl_written = False

    state_dir = Path("storage/state")
    state_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = state_dir / "metrics.json"
    orders_path = state_dir / "orders.json"
    accounts_path = state_dir / "accounts.json"
    signals_path = state_dir / "signals.json"
    accounts_state: dict = {}

    def write_metrics():
        # Aggregate PnL across accounts for status logging
        try:
            daily_sum = 0.0
            unreal_sum = 0.0
            accs = list(accounts_state.values())
            # Fallback: read from accounts.json if in-memory is empty
            if not accs:
                try:
                    raw = accounts_path.read_text(encoding="utf-8")
                    accs = (json.loads(raw) or {}).get("accounts", [])
                except Exception:
                    accs = []
            for st in accs:
                try:
                    daily_sum += float(st.get("daily_pnl", 0.0) or 0.0)
                    unreal_sum += float(st.get("unrealized_pnl", 0.0) or 0.0)
                except Exception:
                    pass
            pnl_sum = {"daily": daily_sum, "unrealized": unreal_sum, "num_accounts": len(accs)}
        except Exception:
            pnl_sum = {"daily": 0.0, "unrealized": 0.0, "num_accounts": 0}
        payload = {
            "ts": time.time(),
            "symbols": symbols,
            "counts": {"tick": tick_count, "depth": depth_count, "pnl": pnl_count},
            "last_price": last_price,
            "last_tick_ts": last_tick_ts,
            "last_depth_ts": last_depth_ts,
            "last_pnl_ts": last_pnl_ts,
            "start_ts": start_ts,
            "errors": error_count,
            "plants": plant_status,
            "pnl_sum": pnl_sum,
        }
        try:
            metrics_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    def to_field_map(obj) -> dict:
        """Convert event object to a field-name -> value map.
        Supports dicts and protobuf messages; falls back to getattr for known fields.
        """
        try:
            # Protobuf-like object
            if hasattr(obj, "ListFields"):
                out = {}
                for desc, val in obj.ListFields():
                    try:
                        out[desc.name] = val
                    except Exception:
                        pass
                return out
        except Exception:
            pass
        try:
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        # Fallback: collect a few common attributes if present
        fields = {}
        for name in (
            "symbol",
            "instrument_id",
            "price",
            "last_price",
            "trade_price",
            "size",
            "last_size",
            "trade_size",
            "quantity",
            "bid_price_levels",
            "ask_price_levels",
            "bid_qty_levels",
            "ask_qty_levels",
        ):
            if hasattr(obj, name):
                try:
                    fields[name] = getattr(obj, name)
                except Exception:
                    pass
        return fields

    def extract_numeric_like(obj, name_hints: tuple[str, ...]) -> float | int | None:
        """Best-effort extraction of a numeric attribute whose name contains any of the hints.
        Useful for vendor events with inconsistent field naming.
        """
        try:
            for attr in dir(obj):
                if attr.startswith("_"):
                    continue
                low = attr.lower()
                if any(h in low for h in name_hints):
                    try:
                        val = getattr(obj, attr)
                        if isinstance(val, (int, float)):
                            return val
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def first_numeric(fields: dict, candidates: tuple) -> float:
        for key in candidates:
            if key in fields and fields[key] is not None:
                try:
                    val = float(fields[key])
                    if val != 0.0:
                        return val
                except Exception:
                    continue
        return 0.0

    def first_sequence(fields: dict, candidates: tuple):
        for key in candidates:
            if key in fields and fields[key] is not None:
                try:
                    seq = list(fields[key])
                    if len(seq) > 0:
                        return seq
                except Exception:
                    continue
        return None

    def parse_number(val):
        try:
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                s = val.replace(",", "").strip()
                return float(s)
        except Exception:
            return None
        return None

    def write_signal(symbol: str, price: float, snap_obj, combined_obj) -> None:
        try:
            main = getattr(combined_obj, "main", None)
            payload = {
                "ts": time.time(),
                "symbol": symbol,
                "price": price,
                "delta_confidence": getattr(snap_obj, "delta_confidence", None),
                "cvd_slope": getattr(snap_obj, "cvd_slope", None),
                "depth_imbalance": getattr(snap_obj, "depth_imbalance", None),
                "aggr_buy_ratio": getattr(snap_obj, "aggressive_buy_ratio", None),
                "side": getattr(combined_obj, "side", None),
                "reason": getattr(combined_obj, "reason", None),
                "trend_state": getattr(combined_obj, "trend_state", None),
                # SMM decision diagnostics
                "ema21": getattr(main, "ema21", None) if main else None,
                "ema21_slope": getattr(main, "ema21_slope", None) if main else None,
                "ema8": getattr(main, "ema8", None) if main else None,
                "ema13": getattr(main, "ema13", None) if main else None,
                "mfi": getattr(main, "mfi", None) if main else None,
                "di_plus": getattr(main, "di_plus", None) if main else None,
                "di_minus": getattr(main, "di_minus", None) if main else None,
                "strong_bull": getattr(main, "strong_bull", None) if main else None,
                "strong_bear": getattr(main, "strong_bear", None) if main else None,
                # Signal source identification
                "source": "smm_internal",
                "signal_type": "ENTRY" if getattr(combined_obj, "side", None) else "HOLD",
                "external": False,
                "processed": False
            }
            with signals_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            try:
                print(f"WRITE_SIGNAL ERROR: {type(e).__name__}: {e}", flush=True)
            except Exception:
                pass

    def write_order_event(kind: str, event_obj) -> None:
        try:
            # Extract common fields safely
            acct = getattr(event_obj, "account_id", None) or getattr(event_obj, "account", None)
            sym = getattr(event_obj, "symbol", None)
            user_tag = getattr(event_obj, "user_tag", None) or getattr(event_obj, "client_order_id", None) or getattr(event_obj, "order_id", None)
            status = getattr(event_obj, "status", None) or getattr(event_obj, "exchange_order_notification_type", None)
            reject_code = getattr(event_obj, "reject_code", None) or getattr(event_obj, "rq_handler_rp_code", None)
            filled_qty = getattr(event_obj, "filled_quantity", None) or getattr(event_obj, "filled_qty", None)
            leaves_qty = getattr(event_obj, "leaves_quantity", None) or getattr(event_obj, "remaining_qty", None)
            price = getattr(event_obj, "price", None) or getattr(event_obj, "avg_price", None)
            bracket_type = getattr(event_obj, "bracket_type", None)
            tx_type = getattr(event_obj, "transaction_type", None)
            action = None
            st = str(status) if status is not None else ""
            if "REJECT" in st.upper() or (str(reject_code or "") not in ("", "0")):
                action = "rejected"
            elif "ACCEPT" in st.upper():
                action = "accepted"
            elif "CANCEL" in st.upper():
                action = "canceled"
            elif "FILL" in st.upper() or (filled_qty and int(filled_qty) > 0 and not leaves_qty):
                action = "filled"
            payload = {
                "ts": time.time(),
                "kind": kind,
                "account_id": acct,
                "symbol": sym,
                "user_tag": str(user_tag) if user_tag is not None else None,
                "status": st or None,
                "action": action,
                "reject_code": str(reject_code) if reject_code is not None else None,
                "filled_qty": int(filled_qty) if filled_qty is not None else None,
                "leaves_qty": int(leaves_qty) if leaves_qty is not None else None,
                "price": float(price) if price is not None else None,
                "bracket_type": str(bracket_type) if bracket_type is not None else None,
                "transaction_type": str(tx_type) if tx_type is not None else None,
            }
            # Append line-delimited JSON for readability
            with orders_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass

    def write_accounts():
        try:
            accounts_payload = {"ts": time.time(), "accounts": list(accounts_state.values())}
            accounts_path.write_text(json.dumps(accounts_payload), encoding="utf-8")
        except Exception:
            pass

    def update_account_entry(account_id: str, unrealized: float | None = None, realized: float | None = None, position_qty: int | None = None) -> None:
        st = accounts_state.setdefault(account_id, {
            "account_id": account_id,
            "enabled": executor.account_enabled.get(account_id, False),
            "position_qty": 0,
            "position_side": "FLAT",
            "unrealized_pnl": 0.0,
            "daily_pnl": 0.0,
        })
        if unrealized is not None:
            try:
                st["unrealized_pnl"] = float(unrealized)
            except Exception:
                pass
        if realized is not None:
            try:
                st["daily_pnl"] = float(realized)
            except Exception:
                pass
        if position_qty is not None:
            try:
                q = int(position_qty)
                st["position_qty"] = q
                st["position_side"] = ("LONG" if q > 0 else ("SHORT" if q < 0 else "FLAT"))
                try:
                    executor.update_account_position(account_id, q)
                except Exception:
                    pass
            except Exception:
                pass
        accounts_state[account_id] = st

    def map_fields_to_pnl(fmap: dict) -> tuple[float | None, float | None, int | None]:
        # daily pnl
        daily = None
        for k in ("day_pnl", "day_closed_pnl", "closed_position_pnl", "realized_pnl", "account_realized_pnl"):
            if k in fmap:
                val = parse_number(fmap.get(k))
                if val is not None:
                    daily = val
                    break
        # unrealized pnl
        unreal = None
        for k in ("open_position_pnl", "day_open_pnl", "unrealized_pnl", "account_unrealized_pnl"):
            if k in fmap:
                val = parse_number(fmap.get(k))
                if val is not None:
                    unreal = val
                    break
        # position qty
        qty = None
        for k in ("net_quantity", "open_position_quantity", "net_position", "position", "position_qty"):
            if k in fmap:
                try:
                    qv = parse_number(fmap.get(k))
                    qty = int(qv) if qv is not None else None
                    break
                except Exception:
                    continue
        return unreal, daily, qty

    async def on_market_depth(data):
        """Handle market depth events for bid/ask volume extraction"""
        try:
            f = to_field_map(data)
            sym = f.get("symbol") or f.get("instrument_id")
            
            # Extract bid/ask volumes from market depth events
            bid_vol = first_numeric(f, ("bid_size", "bid_volume", "bid_qty", "bid_quantity", "depth_size"))
            ask_vol = first_numeric(f, ("ask_size", "ask_volume", "ask_qty", "ask_quantity", "depth_size"))
            
            # Check if this is a bid or ask update based on transaction_type
            tx_type = f.get("transaction_type")
            if tx_type is not None:
                if "BUY" in str(tx_type).upper() or "BID" in str(tx_type).upper():
                    bid_vol = bid_vol or 0
                    ask_vol = 0
                elif "SELL" in str(tx_type).upper() or "ASK" in str(tx_type).upper():
                    ask_vol = ask_vol or 0
                    bid_vol = 0
            
            if bid_vol is not None and ask_vol is not None:
                print(f"MARKET_DEPTH DEBUG: {sym} bid_vol={bid_vol}, ask_vol={ask_vol}, tx_type={tx_type}, fields={list(f.keys())}", flush=True)
                
                # Update features with real bid/ask volumes
                features.update_trades(bid_vol, ask_vol)
        except Exception as e:
            print(f"Error in on_market_depth: {e}", flush=True)

    async def on_tick(data):
        nonlocal tick_count, last_price, last_tick_ts, diag_tick_dumped, diag_tick_written, current_bar_buy_volume, current_bar_sell_volume, last_best_bid, last_best_ask
        tick_count += 1
        try:
            plant_status["ticker"] = True
            # One-time: write full attribute list to file for mapping
            if not diag_tick_written:
                try:
                    with open("/tmp/tick_event_dump.txt", "w", encoding="utf-8") as df:
                        sample_fields = to_field_map(data)
                        df.write(json.dumps({
                            "ts": time.time(),
                            "attrs": [a for a in dir(data) if not a.startswith("_")],
                            "keys": list(sample_fields.keys()),
                            "sample": {k: (sample_fields[k] if k in sample_fields else None) for k in list(sample_fields.keys())[:10]},
                        }) + "\n")
                except Exception:
                    pass
                diag_tick_written = True
            f = to_field_map(data)
            sym = f.get("symbol") or f.get("instrument_id")
            
            # Check if this is a BBO event (bid/ask data)
            is_bbo = hasattr(data, 'data_type') and str(data.data_type) == 'DataType.BBO'
            if is_bbo:
                # Update last best bid/ask from BBO fields for inference
                try:
                    bb_seq = first_sequence(f, ("bid_price_levels", "bid_prices", "best_bid_price"))
                    ba_seq = first_sequence(f, ("ask_price_levels", "ask_prices", "best_ask_price"))
                    bb = None
                    ba = None
                    if bb_seq is not None:
                        bb = float(bb_seq[0] if isinstance(bb_seq, (list, tuple)) else bb_seq)
                    if ba_seq is not None:
                        ba = float(ba_seq[0] if isinstance(ba_seq, (list, tuple)) else ba_seq)
                    if bb is None:
                        sb = f.get("bid_price")
                        if sb is not None:
                            bb = float(sb)
                    if ba is None:
                        sa = f.get("ask_price")
                        if sa is not None:
                            ba = float(sa)
                    if bb is not None and ba is not None and bb > 0 and ba > 0:
                        last_best_bid = bb
                        last_best_ask = ba
                except Exception:
                    pass
            
            # Be robust to various field names across events
            price = first_numeric(f, ("last_price", "trade_price", "price", "last_trade_price", "close", "bid_price", "ask_price"))
            size = first_numeric(f, ("size", "last_size", "trade_size", "quantity", "bid_size", "ask_size"))
            
            # Extract bid/ask volumes for delta calculation using aggressor field
            aggressor = f.get("aggressor")
            trade_size = first_numeric(f, ("trade_size", "size", "quantity"))
            
            if aggressor is not None and trade_size is not None:
                # aggressor: 1 = buyer (bid hit), 2 = seller (ask hit)
                if aggressor == 1:  # Buyer - bid volume
                    bid_vol = trade_size
                    ask_vol = 0
                elif aggressor == 2:  # Seller - ask volume  
                    bid_vol = 0
                    ask_vol = trade_size
                else:
                    bid_vol = trade_size * 0.5
                    ask_vol = trade_size * 0.5
                print(f"AGGRESSOR DEBUG: {sym} aggressor={aggressor}, trade_size={trade_size}, bid_vol={bid_vol}, ask_vol={ask_vol}", flush=True)
            else:
                # Infer aggressor when missing using best bid/ask and price change
                inferred = None
                reason = None
                tsz = trade_size if trade_size is not None else size
                tsz = tsz if tsz is not None else 0.0
                try:
                    if price and last_best_bid and last_best_ask:
                        eps = max(tick_size * 0.5, 1e-9)
                        if price >= (last_best_ask - eps):
                            inferred, reason = 1, "touch_ask"
                        elif price <= (last_best_bid + eps):
                            inferred, reason = 2, "touch_bid"
                    if inferred is None and price and last_price:
                        if price > last_price:
                            inferred, reason = 1, "uptick"
                        elif price < last_price:
                            inferred, reason = 2, "downtick"
                except Exception:
                    inferred = None
                if inferred is not None and tsz > 0:
                    if inferred == 1:
                        bid_vol, ask_vol = tsz, 0
                    else:
                        bid_vol, ask_vol = 0, tsz
                    print(f"AGGRESSOR DEBUG: {sym} inferred={inferred} reason={reason}, trade_size={tsz}, bid_vol={bid_vol}, ask_vol={ask_vol}, last_bid={last_best_bid}, last_ask={last_best_ask}", flush=True)
                else:
                    print(f"AGGRESSOR DEBUG: {sym} Missing aggressor or trade_size - aggressor={aggressor}, trade_size={trade_size}", flush=True)
                    bid_vol = None
                    ask_vol = None
            if price:
                last_price = price
                last_tick_ts = time.time()
                try:
                    print(f"TICK {sym}: {price}", flush=True)
                except Exception:
                    pass
            else:
                # One-time diagnostics to discover actual field names
                if diag_tick_dumped < 1:
                    try:
                        attrs = [a for a in dir(data) if not a.startswith("_")]
                        print("TICK_ATTRS:", attrs, flush=True)
                    except Exception:
                        pass
                    diag_tick_dumped += 1
            # Use bid/ask volumes if available, otherwise split evenly
            if bid_vol is not None and ask_vol is not None:
                features.update_trades(bid_vol, ask_vol)
                # Accumulate for bar-level delta calculation
                current_bar_buy_volume += bid_vol
                current_bar_sell_volume += ask_vol
            else:
                features.update_trades(size * 0.5, size * 0.5)
                # Accumulate for bar-level delta calculation
                current_bar_buy_volume += size * 0.5
                current_bar_sell_volume += size * 0.5
            if price > 0:
                # Update aggregators and feed completed bars to SMM
                signal_generated = False
                completed_bars = bars_time.update(price, size, time.time())
                if completed_bars:
                    print(f"Found {len(completed_bars)} completed bars", flush=True)
                else:
                    print(f"BAR DEBUG: No completed bars, price={price}, size={size}", flush=True)
                for bar in completed_bars:
                    print(f"Completed 1-minute bar: O={bar.open}, H={bar.high}, L={bar.low}, C={bar.close}, V={bar.volume}", flush=True)
                    
                    # Use accumulated bar-level delta
                    buy_vol = current_bar_buy_volume
                    sell_vol = current_bar_sell_volume
                    bar_delta = buy_vol - sell_vol
                    print(f"BAR DELTA: buy_vol={buy_vol:.1f}, sell_vol={sell_vol:.1f}, delta={bar_delta:.1f}", flush=True)
                    
                    # Reset for next bar
                    current_bar_buy_volume = 0.0
                    current_bar_sell_volume = 0.0
                    
                    bar_data = BarData(
                        timestamp=time.time(),
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        buy_volume=buy_vol,
                        sell_volume=sell_vol
                    )
                    
                    # Add to bar feature engine
                    bar_features.add_bar(bar_data)
                    
                    # Update Enhanced SMM Engine with bar data
                    enhanced_smm.add_bar(
                        open_price=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        delta=bar_delta  # Use accumulated bar-level delta
                    )
                    print(f"Enhanced SMM bars count: {len(enhanced_smm.bars)}", flush=True)
                    
                    # Update original SMM for compatibility
                    combined.on_bar_source("time1m", bar.open, bar.high, bar.low, bar.close, bar.volume)
                    
                    # Generate signal only on completed 1-minute bars with sufficient data
                    if bar_features.is_ready():
                        bar_snap = bar_features.snapshot()
                        
                        # Use bar-based features for original signal generation
                        decision = signals.on_price_and_features(bar.close, bar_snap)
                        gated = combined.evaluate(bar.close, bar_snap)
                        
                        # Check if enhanced SMM is ready and use it
                        if enhanced_smm.is_ready():
                            print(f"Enhanced SMM ready: bars={len(enhanced_smm.bars)}", flush=True)
                            # Use Enhanced SMM Engine for signal generation
                            enhanced_result = enhanced_smm.generate_signal()
                            
                            # Use enhanced signal if available, otherwise fall back to original
                            if enhanced_result.signal_side:
                                gated.side = enhanced_result.signal_side
                                gated.reason = f"enhanced_{enhanced_result.signal_side.lower()}"
                                print(f"Enhanced signal: {enhanced_result.signal_side}", flush=True)
                        else:
                            print(f"Enhanced SMM not ready: bars={len(enhanced_smm.bars)}", flush=True)
                        
                        signal_generated = True
                        # Defer logging vars until defined below
                for bar in bars_ticks.update(price, size):
                    combined.on_bar_source("ticks233", bar.open, bar.high, bar.low, bar.close, bar.volume)
                for bar in bars_t12.update(price, size):
                    combined.on_bar_source("tbar12", bar.open, bar.high, bar.low, bar.close, bar.volume)
                
                # Only evaluate signals on completed bars, not every tick
                final_side = None
                if signal_generated:
                    # Log every evaluation for diagnostics
                    if sym:
                        write_signal(sym, price, bar_snap, gated)
                    try:
                        # Diagnostic: decision and trends
                        print(
                            f"COMBINED DECISION: side={getattr(gated,'side',None)} reason={getattr(gated,'reason',None)} trend_state={getattr(gated,'trend_state',None)}",
                            flush=True
                        )
                    except Exception:
                        pass
                    final_side = gated.side or decision.side
                else:
                    try:
                        # Diagnostic: features not ready yet
                        print(f"BAR_FEATURES: count={len(bar_features.bars)} ready={bar_features.is_ready()} (no signal)", flush=True)
                    except Exception:
                        pass
                # Respect dashboard control file toggle
                control = {}
                try:
                    control = json.loads((state_dir / "control.json").read_text(encoding="utf-8"))
                except Exception:
                    pass
                trading_ok = bool(control.get("trading_enabled", bool(int(os.getenv("TRADING_ENABLED", "0")))))
                print(f"TRADING DEBUG: final_side={final_side}, trading_ok={trading_ok}, control={control}", flush=True)
                if final_side and trading_ok:
                    # Use only accounts that are explicitly enabled
                    accounts = [acc for acc, enabled in executor.account_enabled.items() if enabled]
                    if not accounts:
                        try:
                            accts = await orders.list_accounts()
                            for a in accts or []:
                                aid = getattr(a, "account_id", None) or str(a)
                                if aid:
                                    accounts.append(aid)
                            if accounts:
                                executor.set_accounts(accounts)
                        except Exception:
                            accounts = []
                    # Fallback: use env whitelist if still no accounts
                    if not accounts:
                        try:
                            env_whitelist = os.getenv("WHITELIST_ACCOUNTS", "")
                            env_accounts = [a.strip() for a in env_whitelist.replace(",", " ").split() if a.strip()]
                            if env_accounts:
                                print(f"ACCOUNTS FALLBACK: using WHITELIST_ACCOUNTS={env_accounts}", flush=True)
                                accounts = env_accounts
                                executor.set_accounts(accounts)
                        except Exception:
                            pass
                    # Secondary fallback: use configured test_accounts
                    if not accounts:
                        try:
                            cfg_accounts = list(getattr(executor, "test_accounts", []))
                            if cfg_accounts:
                                print(f"ACCOUNTS FALLBACK: using config test_accounts={cfg_accounts}", flush=True)
                                accounts = cfg_accounts
                                executor.set_accounts(accounts)
                        except Exception:
                            pass
                    if accounts:
                        # Use enhanced signal submission with bar-based confidence, ATR, and SMM signal price
                        confidence_score = bar_snap.delta_confidence
                        atr_value = getattr(combined.main.atr, 'current_value', 0.0) or 0.0
                        signal_price = price  # Use current price as SMM signal price
                        # Determine symbol safely (prefer current tick symbol if available)
                        try:
                            symbol_for_order = sym if sym else (symbols[0] if symbols else None)
                        except Exception:
                            symbol_for_order = sym if sym else None
                        if symbol_for_order:
                            print(f"ORDER SUBMISSION: submitting {final_side} signal for {symbol_for_order} to accounts {accounts}", flush=True)
                            await executor.submit_enhanced_signal(
                                symbol_for_order, final_side, confidence_score, atr_value, price, accounts, signal_price
                            )
                        else:
                            try:
                                print("ORDER SUBMISSION SKIP: no symbol available for submission", flush=True)
                            except Exception:
                                pass
        except Exception:
            error_count += 1
        write_metrics()

    async def on_order_book(data):
        nonlocal depth_count, last_price, last_depth_ts, diag_depth_dumped, diag_depth_written, last_best_bid, last_best_ask
        depth_count += 1
        try:
            plant_status["ticker"] = True
            if not diag_depth_written:
                try:
                    with open("/tmp/md_event_dump.txt", "w", encoding="utf-8") as df:
                        fmap = to_field_map(data)
                        df.write(json.dumps({
                            "ts": time.time(),
                            "attrs": [a for a in dir(data) if not a.startswith("_")],
                            "keys": list(fmap.keys()),
                            "sample_data": fmap,
                        }) + "\n")
                except Exception:
                    pass
                diag_depth_written = True
            fmap = to_field_map(data)
            bids = np.array(fmap.get("bid_qty_levels") or fmap.get("bid_qty") or [], dtype=float)
            asks = np.array(fmap.get("ask_qty_levels") or fmap.get("ask_qty") or [], dtype=float)
            
            # Enhanced logging for Level 2 data
            sym = fmap.get("symbol") or fmap.get("instrument_id")
            if bids.size and asks.size:
                bid_sum = float(np.sum(bids))
                ask_sum = float(np.sum(asks))
                depth_imbalance = (bid_sum - ask_sum) / (bid_sum + ask_sum) if (bid_sum + ask_sum) > 0 else 0.0
                print(f"LEVEL2 DEBUG: {sym} bid_sum={bid_sum:.1f}, ask_sum={ask_sum:.1f}, imbalance={depth_imbalance:.3f}, bid_levels={len(bids)}, ask_levels={len(asks)}", flush=True)
                features.update_orderbook(bids, asks)
            else:
                print(f"LEVEL2 DEBUG: {sym} No bid/ask data - bids.size={bids.size}, asks.size={asks.size}, fields={list(fmap.keys())}", flush=True)
            # Update last_price from best bid/ask mid if available
            bid_prices = first_sequence(fmap, ("bid_price_levels", "bid_prices", "best_bid_price"))
            ask_prices = first_sequence(fmap, ("ask_price_levels", "ask_prices", "best_ask_price"))
            try:
                if bid_prices and ask_prices:
                    bb = float(bid_prices[0] if isinstance(bid_prices, (list, tuple)) else bid_prices)
                    ba = float(ask_prices[0] if isinstance(ask_prices, (list, tuple)) else ask_prices)
                    if bb > 0 and ba > 0:
                        last_best_bid = bb
                        last_best_ask = ba
                        last_price = (bb + ba) * 0.5
                        last_depth_ts = time.time()
                else:
                    # Fallback to scalar fields if provided
                    sb = fmap.get("bid_price")
                    sa = fmap.get("ask_price")
                    if sb is not None and sa is not None:
                        bb = float(sb)
                        ba = float(sa)
                        if bb > 0 and ba > 0:
                            last_best_bid = bb
                            last_best_ask = ba
                            last_price = (bb + ba) * 0.5
                            last_depth_ts = time.time()
            except Exception:
                pass
            # One-time diagnostics to discover depth field names
            if diag_depth_dumped < 1:
                try:
                    attrs = [a for a in dir(data) if not a.startswith("_")]
                    print("DEPTH_ATTRS:", attrs, flush=True)
                except Exception:
                    pass
                diag_depth_dumped += 1
        except Exception:
            error_count += 1
        write_metrics()

    async def on_account_pnl_update(update):
        nonlocal pnl_count
        pnl_count += 1
        # Update per-account state for dashboard
        try:
            plant_status["pnl"] = True
            nonlocal last_pnl_ts
            last_pnl_ts = time.time()
            # One-time diagnostics to discover account/PnL field names
            nonlocal diag_pnl_written
            if not diag_pnl_written:
                try:
                    with open("/tmp/pnl_event_dump.txt", "w", encoding="utf-8") as df:
                        fmap = to_field_map(update)
                        df.write(json.dumps({"ts": time.time(), "fields": fmap}, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                diag_pnl_written = True
            aid = getattr(update, "account_id", None) or getattr(update, "account", None)
            if aid:
                fmap = to_field_map(update)
                # Map Rithmic fields (often numeric strings)
                # daily_pnl: prefer day_pnl
                daily = None
                for k in ("day_pnl", "day_closed_pnl", "closed_position_pnl"):
                    if k in fmap:
                        daily = parse_number(fmap.get(k))
                        if daily is not None:
                            break
                # unrealized: open_position_pnl or day_open_pnl
                unreal = None
                for k in ("open_position_pnl", "day_open_pnl"):
                    if k in fmap:
                        unreal = parse_number(fmap.get(k))
                        if unreal is not None:
                            break
                # qty: net_quantity or open_position_quantity
                qty = None
                for k in ("net_quantity", "open_position_quantity", "net_position"):
                    if k in fmap:
                        try:
                            qty = int(parse_number(fmap.get(k)) or 0)
                            break
                        except Exception:
                            continue
                # Fallbacks
                if unreal is None:
                    unreal = parse_number(getattr(update, "unrealized_pnl", None) or getattr(update, "account_unrealized_pnl", None) or extract_numeric_like(update, ("unreal",)))
                if daily is None:
                    daily = parse_number(getattr(update, "realized_pnl", None) or getattr(update, "account_realized_pnl", None) or extract_numeric_like(update, ("realized", "realise", "real")))
                if qty is None:
                    v = getattr(update, "position", None) or getattr(update, "net_position", None) or getattr(update, "open_position", None) or getattr(update, "position_qty", None)
                    try:
                        qty = int(v) if v is not None else None
                    except Exception:
                        qty = None
                update_account_entry(aid, unrealized=unreal, realized=daily, position_qty=(int(qty) if qty is not None else None))
                # Append raw pnl update sample for diagnostics
                try:
                    with open("storage/state/pnl_updates.jsonl", "a", encoding="utf-8") as pf:
                        pf.write(json.dumps({
                            "ts": time.time(),
                            "account_id": aid,
                            "unrealized_pnl": accounts_state.get(aid, {}).get("unrealized_pnl"),
                            "daily_pnl": accounts_state.get(aid, {}).get("daily_pnl"),
                            "position_qty": accounts_state.get(aid, {}).get("position_qty"),
                        }) + "\n")
                except Exception:
                    pass
                write_accounts()
                # Feed risk manager
                try:
                    st = accounts_state.get(aid, {})
                    executor.update_account_pnl(aid, st.get("daily_pnl"), st.get("unrealized_pnl"))
                except Exception:
                    pass
        except Exception:
            error_count += 1
        write_metrics()

    async def on_instrument_pnl_update(update):
        # Log instrument-level pnl/position updates for diagnostics
        try:
            nonlocal last_pnl_ts
            last_pnl_ts = time.time()
            fmap = to_field_map(update)
            aid = fmap.get("account_id") or getattr(update, "account_id", None) or getattr(update, "account", None)
            sym = fmap.get("symbol") or getattr(update, "symbol", None) or fmap.get("instrument_id")
            daily = None
            for k in ("day_pnl", "day_closed_pnl", "closed_position_pnl"):
                if k in fmap:
                    daily = parse_number(fmap.get(k))
                    if daily is not None:
                        break
            unreal = None
            for k in ("open_position_pnl", "day_open_pnl"):
                if k in fmap:
                    unreal = parse_number(fmap.get(k))
                    if unreal is not None:
                        break
            qty = None
            for k in ("net_quantity", "open_position_quantity", "net_position"):
                if k in fmap:
                    try:
                        qty = int(parse_number(fmap.get(k)) or 0)
                        break
                    except Exception:
                        continue
            payload = {
                "ts": time.time(),
                "account_id": aid,
                "symbol": sym,
                "realized_pnl": daily,
                "unrealized_pnl": unreal,
                "position_qty": qty,
            }
            with open("storage/state/instrument_pnl.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
            # Update account entry aggregating instrument snapshot (prefer latest instrument values)
            if aid:
                update_account_entry(aid, unrealized=payload.get("unrealized_pnl"), realized=payload.get("realized_pnl"), position_qty=payload.get("position_qty"))
                write_accounts()
        except Exception:
            pass

    client.on_tick += on_tick
    client.on_market_depth += on_market_depth
    # Also attempt to bind to other market data callbacks if exposed by the SDK
    try:
        client.on_market_data += on_tick  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        client.on_last_trade += on_tick  # type: ignore[attr-defined]
    except Exception:
        pass
    client.on_order_book += on_order_book
    client.on_market_depth += on_order_book
    client.on_account_pnl_update += on_account_pnl_update
    try:
        client.on_instrument_pnl_update += on_instrument_pnl_update  # type: ignore[attr-defined]
    except Exception:
        pass

    # Order-related event logging for audit trail
    async def on_rithmic_order(evt):
        try:
            plant_status["order"] = True
        except Exception:
            pass
        write_order_event("rithmic_order", evt)
    async def on_exchange_order(evt):
        try:
            plant_status["order"] = True
        except Exception:
            pass
        write_order_event("exchange_order", evt)
    async def on_bracket(evt):
        write_order_event("bracket_update", evt)
    client.on_rithmic_order_notification += on_rithmic_order
    client.on_exchange_order_notification += on_exchange_order
    client.on_bracket_update += on_bracket

    async def on_disconnected_notifier(plant_type):
        try:
            if isinstance(plant_type, str) and plant_type in plant_status:
                plant_status[plant_type] = False
        except Exception:
            pass
        print("DISCONNECT/LOGOUT:", plant_type, flush=True)
    client.on_disconnected += on_disconnected_notifier

    await client.connect()
    print("CONNECTED", user, system_name, url, flush=True)

    # Enumerate accounts and enable executor
    try:
        accts = await orders.list_accounts()
        ids: List[str] = []
        for a in accts or []:
            aid = getattr(a, "account_id", None) or str(a)
            if aid:
                ids.append(aid)
        if ids:
            executor.set_accounts(ids)
            for aid in ids:
                accounts_state.setdefault(aid, {
                    "account_id": aid,
                    "enabled": executor.account_enabled.get(aid, False),
                    "position_qty": 0,
                    "position_side": "FLAT",
                    "unrealized_pnl": 0.0,
                    "daily_pnl": 0.0,
                })
            write_accounts()
            # Pull initial PnL snapshot per account to seed balances/positions
            for aid in ids:
                try:
                    snap_list = await client.list_account_summary(account_id=aid)
                except Exception:
                    snap_list = None
                try:
                    snap = (snap_list or [None])[0]
                    if snap is not None:
                        st = accounts_state.get(aid) or {}
                        # Map common fields from snapshot
                        unreal = getattr(snap, "unrealized_pnl", None) or getattr(snap, "account_unrealized_pnl", None)
                        reald = getattr(snap, "realized_pnl", None) or getattr(snap, "account_realized_pnl", None)
                        qty = getattr(snap, "net_position", None) or getattr(snap, "position", None) or getattr(snap, "open_position", None) or getattr(snap, "position_qty", None)
                        if unreal is not None:
                            st["unrealized_pnl"] = float(unreal)
                        if reald is not None:
                            st["daily_pnl"] = float(reald)
                        if qty is not None:
                            q = int(qty)
                            st["position_qty"] = q
                            st["position_side"] = ("LONG" if q > 0 else ("SHORT" if q < 0 else "FLAT"))
                            try:
                                executor.update_account_position(aid, q)
                            except Exception:
                                pass
                        accounts_state[aid] = st
                except Exception:
                    pass
            write_accounts()
        print("ACCOUNTS:", accts, flush=True)
    except Exception as e:
        print("LIST_ACCOUNTS_ERROR:", repr(e), flush=True)

    # Resolve front-month contracts for root symbols if roots provided (e.g., NQ, MNQ)
    try:
        resolved: List[str] = []
        for root in list(symbols):
            try:
                fut = await ticker.get_front_month_contract(root, exchange)
                sym = getattr(fut, "symbol", None)
                if sym:
                    resolved.append(sym)
            except Exception:
                pass
        if resolved:
            symbols = resolved
            print("RESOLVED_SYMBOLS:", symbols, flush=True)
    except Exception as e:
        print("FRONT_MONTH_RESOLVE_ERROR:", repr(e), flush=True)

    # Subscribe streams (prefer client api for PnL per docs, fallback to plant)
    try:
        await client.subscribe_to_pnl_updates()
    except Exception:
        await pnl.subscribe_to_pnl_updates()
    for sym in symbols:
        await ticker.subscribe_to_market_data(sym, exchange, DataType.LAST_TRADE)
        await ticker.subscribe_to_market_data(sym, exchange, DataType.BBO)
        await ticker.subscribe_to_market_depth(sym, exchange, depth_price=depth_tick)

    # Reconcile per-account state against live orders after (re)connect
    try:
        await executor.reconcile_accounts(orders, pnl)
    except Exception:
        pass

    # Heartbeat writer: ensure metrics are refreshed periodically
    stop_heartbeat = False
    async def heartbeat_writer():
        while not stop_heartbeat:
            try:
                write_metrics()
            except Exception:
                pass
            await asyncio.sleep(5)
    hb_task = asyncio.create_task(heartbeat_writer())

    # Periodic account summary refresher to keep PnL in sync
    stop_pnl_refresh = False
    async def pnl_snapshot_refresher():
        while not stop_pnl_refresh:
            try:
                ids = list(executor.account_enabled.keys())
                for aid in ids:
                    try:
                        snap_list = await client.list_account_summary(account_id=aid)
                    except Exception:
                        snap_list = None
                    try:
                        snap = (snap_list or [None])[0]
                        if snap is not None:
                            unreal = getattr(snap, "unrealized_pnl", None) or getattr(snap, "account_unrealized_pnl", None)
                            reald = getattr(snap, "realized_pnl", None) or getattr(snap, "account_realized_pnl", None)
                            qty = getattr(snap, "net_position", None) or getattr(snap, "position", None) or getattr(snap, "open_position", None) or getattr(snap, "position_qty", None)
                            update_account_entry(aid, unrealized=unreal, realized=reald, position_qty=(int(qty) if qty is not None else None))
                    except Exception:
                        pass
                write_accounts()
            except Exception:
                pass
            await asyncio.sleep(30)
    pnl_task = asyncio.create_task(pnl_snapshot_refresher())

    try:
        if seconds and seconds > 0:
            await asyncio.sleep(seconds)
            print(f"COUNTS tick={tick_count} depth={depth_count} pnl={pnl_count}", flush=True)
        else:
            # Infinite run; park the task
            while True:
                await asyncio.sleep(5)
    finally:
        stop_heartbeat = True
        stop_pnl_refresh = True
        try:
            hb_task.cancel()
        except Exception:
            pass
        try:
            pnl_task.cancel()
        except Exception:
            pass
        for sym in symbols:
            try:
                await ticker.unsubscribe_from_market_data(sym, exchange, DataType.LAST_TRADE)
                await ticker.unsubscribe_from_market_data(sym, exchange, DataType.BBO)
                await ticker.unsubscribe_from_market_depth(sym, exchange, depth_price=depth_tick)
            except Exception:
                pass
        try:
            await client.unsubscribe_from_pnl_updates()
        except Exception:
            try:
                await pnl.unsubscribe_from_pnl_updates()
            except Exception:
                pass
        await client.disconnect()
        print("DISCONNECTED", flush=True)

async def main() -> None:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    # Use project .env explicitly to avoid dotenv find errors
    try:
        env_path = str((Path(__file__).resolve().parents[1] / ".env"))
        load_dotenv(dotenv_path=env_path)
    except Exception:
        load_dotenv()
    print("ENV READY user=", os.getenv("RITHMIC_USERNAME", ""), "url=", os.getenv("RITHMIC_URL", ""), flush=True)
    seconds = int(os.getenv("RUN_WINDOW_SECS", "12"))
    try:
        await run_trader(seconds)
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
