from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Header, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import os
import json
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

STATE_DIR = Path(__file__).resolve().parents[1] / "storage" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
METRICS_PATH = STATE_DIR / "metrics.json"
CONTROL_PATH = STATE_DIR / "control.json"
SIGNALS_PATH = STATE_DIR / "signals.json"
EXTERNAL_SIGNALS_PATH = STATE_DIR / "external_signals.json"

# Pydantic models for external signals
class ExternalSignal(BaseModel):
    timestamp: float
    symbol: str
    side: str
    signal_type: str
    price: float
    reason: str
    source: str
    confidence_score: float = 0.8
    atr_value: float = 0.0
    exchange: str = "CME"

def _check_password(password: str) -> None:
    if (password or "").strip() != (os.getenv("DASH_PASSWORD", "").strip()):
        raise HTTPException(status_code=401, detail="Unauthorized")

def _read_metrics() -> dict:
    try:
        raw = METRICS_PATH.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return {
            "counts": {"tick": 0, "depth": 0, "pnl": 0}, 
            "last_price": 0.0, 
            "symbols": [],
            "last_tick_ts": 0,
            "last_depth_ts": 0,
            "last_pnl_ts": 0,
            "errors": 0,
            "plants": {"ticker": False, "order": False, "pnl": False},
            "pnl_sum": {"daily": 0.0, "unrealized": 0.0, "num_accounts": 0}
        }

def _read_accounts() -> dict:
    p = STATE_DIR / "accounts.json"
    try:
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return {"accounts": []}

def _read_signals_tail(max_lines: int = 100) -> list:
    p = STATE_DIR / "signals.json"
    out = []
    try:
        with p.open("r", encoding="utf-8") as f:
            # Tail-like read
            lines = f.readlines()[-max_lines:]
            for ln in lines:
                try:
                    signal = json.loads(ln)
                    # Filter out signals with NaN values
                    if _is_valid_signal(signal):
                        out.append(signal)
                except Exception:
                    continue
    except Exception:
        pass
    return out

def _is_valid_signal(signal: dict) -> bool:
    """Check if signal contains valid numeric values (no NaN/inf)"""
    def check_value(obj):
        if isinstance(obj, dict):
            return all(check_value(v) for v in obj.values())
        elif isinstance(obj, list):
            return all(check_value(v) for v in obj)
        elif isinstance(obj, float):
            return obj == obj and obj != float('inf') and obj != float('-inf')
        else:
            return True
    return check_value(signal)

def _read_control() -> dict:
    try:
        raw = CONTROL_PATH.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return {"trading_enabled": bool(int(os.getenv("TRADING_ENABLED", "0")))}

def _append_external_signal(signal: ExternalSignal) -> None:
    """Append external signal to the signals log"""
    try:
        signal_data = signal.dict()
        signal_data["ts"] = signal.timestamp
        signal_data["external"] = True
        
        # Append to main signals file
        with SIGNALS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(signal_data) + "\n")
            
        # Also append to external signals file for tracking
        with EXTERNAL_SIGNALS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(signal_data) + "\n")
            
    except Exception as e:
        print(f"Error appending external signal: {e}")

def _read_external_signals_tail(max_lines: int = 50) -> list:
    """Read recent external signals"""
    try:
        with EXTERNAL_SIGNALS_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-max_lines:]
            signals = []
            for line in lines:
                try:
                    signal = json.loads(line)
                    if _is_valid_signal(signal):
                        signals.append(signal)
                except Exception:
                    continue
            return signals
    except Exception:
        return []

@app.get("/")
async def root():
    html = """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>SMM NQ Trader - Login</title>
  <style>
    body { font-family: sans-serif; margin: 40px; }
    .card { max-width: 360px; margin: 0 auto; padding: 24px; border: 1px solid #ddd; border-radius: 8px; }
    input { width: 100%; padding: 10px; margin: 8px 0; }
    button { padding: 10px 14px; }
  </style>
  <script>
    function go() {
      const pwd = document.getElementById('pwd').value;
      if (!pwd) return false;
      window.location.href = '/ui?password=' + encodeURIComponent(pwd);
      return false;
    }
  </script>
  </head>
<body>
  <div class=\"card\">
    <h2>SMM NQ Trader - Dashboard Login</h2>
    <form onsubmit=\"return go()\">
      <label>Password</label>
      <input id=\"pwd\" type=\"password\" placeholder=\"Enter dashboard password\" autocomplete=\"current-password\" />
      <button type=\"submit\">Enter</button>
    </form>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html)

@app.get("/favicon.ico")
async def favicon():
    # Avoid proxying favicon to unrelated upstream
    return JSONResponse(status_code=204, content=None)

@app.get("/status")
async def status(password: str = Query(""), x_dash_pass: Optional[str] = Header(default=None)):
    _check_password(password or (x_dash_pass or ""))
    metrics = _read_metrics()
    control = _read_control()
    accounts = _read_accounts()
    signals = _read_signals_tail(50)
    return JSONResponse({"metrics": metrics, "control": control, "accounts": accounts, "signals": signals})

@app.post("/control/stop")
async def control_stop(password: str = Query(""), x_dash_pass: Optional[str] = Header(default=None)):
    _check_password(password or (x_dash_pass or ""))
    CONTROL_PATH.write_text(json.dumps({"trading_enabled": False}), encoding="utf-8")
    return {"ok": True, "trading_enabled": False}

@app.post("/control/start")
async def control_start(password: str = Query(""), x_dash_pass: Optional[str] = Header(default=None)):
    _check_password(password or (x_dash_pass or ""))
    CONTROL_PATH.write_text(json.dumps({"trading_enabled": True}), encoding="utf-8")
    return {"ok": True, "trading_enabled": True}

@app.post("/api/signals/external")
async def receive_external_signal(
    signal: ExternalSignal,
    x_dash_pass: Optional[str] = Header(default=None)
):
    """Receive external signals from NinjaTrader or other sources"""
    try:
        # Validate signal
        if not signal.symbol or not signal.side or not signal.signal_type:
            raise HTTPException(status_code=400, detail="Invalid signal data")
        
        # Add timestamp if not provided
        if signal.timestamp == 0:
            signal.timestamp = time.time()
        
        # Store the signal
        _append_external_signal(signal)
        
        # Trigger signal processing in background
        try:
            from core.external_signal_processor import get_signal_processor
            processor = get_signal_processor()
            # Process signal asynchronously
            import asyncio
            asyncio.create_task(processor.process_signal_from_data(signal.dict()))
        except Exception as e:
            print(f"Error triggering signal processing: {e}")
        
        return {
            "ok": True,
            "message": "Signal received successfully",
            "signal_id": f"{signal.source}_{signal.timestamp}",
            "timestamp": signal.timestamp
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing signal: {str(e)}")

@app.get("/api/signals/external")
async def get_external_signals(
    limit: int = Query(50, ge=1, le=200),
    x_dash_pass: Optional[str] = Header(default=None)
):
    """Get recent external signals"""
    signals = _read_external_signals_tail(limit)
    return {"signals": signals, "count": len(signals)}

@app.post("/api/control/filters")
async def update_signal_filters(
    long_enabled: bool = Query(True),
    short_enabled: bool = Query(True),
    x_dash_pass: Optional[str] = Header(default=None)
):
    """Update signal filter controls"""
    try:
        # Update filters using signal processor
        from core.external_signal_processor import get_signal_processor
        processor = get_signal_processor()
        processor.update_filters(long_enabled, short_enabled)
        
        return {
            "ok": True,
            "message": "Signal filters updated",
            "filters": processor.get_filter_status()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating filters: {str(e)}")

@app.get("/api/control/filters")
async def get_signal_filters(x_dash_pass: Optional[str] = Header(default=None)):
    """Get current signal filter settings"""
    try:
        from core.external_signal_processor import get_signal_processor
        processor = get_signal_processor()
        return processor.get_filter_status()
    except Exception:
        return {
            "long_signals_enabled": True,
            "short_signals_enabled": True,
            "updated_at": 0
        }

@app.post("/api/control/filters/long/enable")
async def enable_long_signals(x_dash_pass: Optional[str] = Header(default=None)):
    """Enable long signals"""
    try:
        from core.external_signal_processor import get_signal_processor
        processor = get_signal_processor()
        processor.enable_long_signals()
        return {"ok": True, "message": "Long signals enabled", "filters": processor.get_filter_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enabling long signals: {str(e)}")

@app.post("/api/control/filters/long/disable")
async def disable_long_signals(x_dash_pass: Optional[str] = Header(default=None)):
    """Disable long signals"""
    try:
        from core.external_signal_processor import get_signal_processor
        processor = get_signal_processor()
        processor.disable_long_signals()
        return {"ok": True, "message": "Long signals disabled", "filters": processor.get_filter_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error disabling long signals: {str(e)}")

@app.post("/api/control/filters/short/enable")
async def enable_short_signals(x_dash_pass: Optional[str] = Header(default=None)):
    """Enable short signals"""
    try:
        from core.external_signal_processor import get_signal_processor
        processor = get_signal_processor()
        processor.enable_short_signals()
        return {"ok": True, "message": "Short signals enabled", "filters": processor.get_filter_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enabling short signals: {str(e)}")

@app.post("/api/control/filters/short/disable")
async def disable_short_signals(x_dash_pass: Optional[str] = Header(default=None)):
    """Disable short signals"""
    try:
        from core.external_signal_processor import get_signal_processor
        processor = get_signal_processor()
        processor.disable_short_signals()
        return {"ok": True, "message": "Short signals disabled", "filters": processor.get_filter_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error disabling short signals: {str(e)}")

@app.get("/api/control/sync/stats")
async def get_sync_stats(x_dash_pass: Optional[str] = Header(default=None)):
    """Get account synchronization statistics"""
    try:
        from core.account_sync_manager import get_sync_manager
        sync_manager = get_sync_manager()
        return sync_manager.get_sync_statistics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting sync stats: {str(e)}")

@app.get("/api/control/sync/positions")
async def get_sync_positions(x_dash_pass: Optional[str] = Header(default=None)):
    """Get account positions summary for synchronization"""
    try:
        from core.account_sync_manager import get_sync_manager
        sync_manager = get_sync_manager()
        return sync_manager.get_account_positions_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting sync positions: {str(e)}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # Expect password in the query params
        params = dict(websocket.query_params)
        _check_password(params.get("password", ""))
        # Stream metrics periodically
        while True:
            payload = {"type": "status", "metrics": _read_metrics(), "control": _read_control(), "accounts": _read_accounts(), "signals": _read_signals_tail(20)}
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except HTTPException:
        try:
            await websocket.send_json({"error": "Unauthorized"})
        except Exception:
            pass
        await websocket.close()

@app.get("/ui")
async def ui(password: str = Query("")):
    # Lightweight HTML to display accounts, metrics, and controls
    _check_password(password)
    html = """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>SMM NQ Trader - Dashboard</title>
  <style>
    body {{ font-family: sans-serif; margin: 20px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background: #f3f3f3; text-align: left; }}
    .green {{ color: #0a0; }} .red {{ color: #a00; }}
  </style>
  <script>
    const passParam = new URLSearchParams(window.location.search).get('password') || '';
    async function refresh() {{
      try {{
        const r = await fetch('status?password=' + encodeURIComponent(passParam));
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        document.getElementById('lastPrice').textContent = data.metrics.last_price || 0;
        document.getElementById('ticks').textContent = data.metrics.counts.tick;
        document.getElementById('depth').textContent = data.metrics.counts.depth;
        document.getElementById('pnlCount').textContent = data.metrics.counts.pnl;
        document.getElementById('trading').textContent = data.control.trading_enabled ? 'ENABLED' : 'DISABLED';
        const tbody = document.getElementById('acctBody');
        tbody.innerHTML = '';
        for (const a of (data.accounts.accounts || [])) {{
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${a.account_id || ''}</td>
            <td>${a.enabled ? 'Yes' : 'No'}</td>
            <td>${a.position_side || 'FLAT'}</td>
            <td>${a.position_qty ?? 0}</td>
            <td class="${(a.unrealized_pnl||0)>=0?'green':'red'}">${a.unrealized_pnl ?? 0}</td>
            <td class="${(a.daily_pnl||0)>=0?'green':'red'}">${a.daily_pnl ?? 0}</td>
          `;
          tbody.appendChild(tr);
        }}
      }} catch(e) {{ console.error(e); }}
    }}
    async function setTrading(on) {{
      await fetch(on ? 'control/start?password=' + encodeURIComponent(passParam) : 'control/stop?password=' + encodeURIComponent(passParam), { method: 'POST' });
      await refresh();
    }}
    window.addEventListener('load', () => {{
      refresh();
      setInterval(refresh, 1000);
      try {{
        const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + location.pathname.replace(/\/ui$/, '/ws') + '?password=' + encodeURIComponent(passParam));
        ws.onmessage = () => refresh();
      }} catch(e) {{ console.warn('WS failed', e); }}
    }});
  </script>
</head>
<body>
  <h2>SMM NQ Trader - Dashboard</h2>
  <div class="grid">
    <div>
      <h3>Metrics</h3>
      <p>Last Price: <b id="lastPrice">0</b></p>
      <p>Ticks: <b id="ticks">0</b> | Depth: <b id="depth">0</b> | PnL updates: <b id="pnlCount">0</b></p>
      <p>Last Tick: <b id="lastTickTs">-</b> | Last Depth: <b id="lastDepthTs">-</b></p>
      <p>Errors: <b id="errorsCount">0</b></p>
      <p>Plants: ticker=<b id="plantTicker">-</b> order=<b id="plantOrder">-</b> pnl=<b id="plantPnl">-</b></p>
      <p>Trading: <b id="trading">-</b></p>
      <button onclick="setTrading(true)">Start</button>
      <button onclick="setTrading(false)">Stop</button>
    </div>
    <div>
      <h3>Accounts</h3>
      <table>
        <thead><tr><th>Account</th><th>Enabled</th><th>Side</th><th>Qty</th><th>Unrealized</th><th>Daily P&L</th></tr></thead>
        <tbody id="acctBody"></tbody>
      </table>
    </div>
  </div>
  <div>
    <h3>Signals (latest)</h3>
    <table>
      <thead><tr><th>Time</th><th>Symbol</th><th>Price</th><th>Delta</th><th>Side</th><th>Reason</th></tr></thead>
      <tbody id="sigBody"></tbody>
    </table>
  </div>
  <script>
    async function refreshSignals(data) {
      const tbody = document.getElementById('sigBody');
      if (!tbody) return;
      const sigs = (data && data.signals) ? data.signals : [];
      tbody.innerHTML = '';
      for (const s of sigs) {
        const tr = document.createElement('tr');
        const ts = s.ts ? new Date(s.ts*1000).toLocaleTimeString() : '';
        tr.innerHTML = `<td>${ts}</td><td>${s.symbol||''}</td><td>${s.price||0}</td><td>${(s.delta_confidence??'').toString().slice(0,5)}</td><td>${s.side||''}</td><td>${s.reason||''}</td>`;
        tbody.appendChild(tr);
      }
    }
    async function refresh() {
      try {
        const r = await fetch('status?password=' + encodeURIComponent(passParam));
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        document.getElementById('lastPrice').textContent = data.metrics.last_price || 0;
        document.getElementById('ticks').textContent = data.metrics.counts.tick;
        document.getElementById('depth').textContent = data.metrics.counts.depth;
        document.getElementById('pnlCount').textContent = data.metrics.counts.pnl;
        const ltt = data.metrics.last_tick_ts ? new Date(data.metrics.last_tick_ts*1000).toLocaleTimeString() : '-';
        const ldt = data.metrics.last_depth_ts ? new Date(data.metrics.last_depth_ts*1000).toLocaleTimeString() : '-';
        document.getElementById('lastTickTs').textContent = ltt;
        document.getElementById('lastDepthTs').textContent = ldt;
        document.getElementById('errorsCount').textContent = data.metrics.errors ?? 0;
        const plants = data.metrics.plants || {};
        document.getElementById('plantTicker').textContent = plants.ticker ? 'up' : 'down';
        document.getElementById('plantOrder').textContent = plants.order ? 'up' : 'down';
        document.getElementById('plantPnl').textContent = plants.pnl ? 'up' : 'down';
        document.getElementById('trading').textContent = data.control.trading_enabled ? 'ENABLED' : 'DISABLED';
        const tbody = document.getElementById('acctBody');
        tbody.innerHTML = '';
        for (const a of (data.accounts.accounts || [])) {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${a.account_id || ''}</td>
            <td>${a.enabled ? 'Yes' : 'No'}</td>
            <td>${a.position_side || 'FLAT'}</td>
            <td>${a.position_qty ?? 0}</td>
            <td class="${(a.unrealized_pnl||0)>=0?'green':'red'}">${a.unrealized_pnl ?? 0}</td>
            <td class="${(a.daily_pnl||0)>=0?'green':'red'}">${a.daily_pnl ?? 0}</td>
          `;
          tbody.appendChild(tr);
        }
        refreshSignals(data);
      } catch(e) { console.error(e); }
    }
    window.addEventListener('load', () => {
      refresh();
      setInterval(refresh, 1000);
      try {
        const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + location.pathname.replace(/\/ui$/, '/ws') + '?password=' + encodeURIComponent(passParam));
        ws.onmessage = (ev) => {
          try { const data = JSON.parse(ev.data); refreshSignals(data); } catch(e) {}
        };
      } catch(e) { console.warn('WS failed', e); }
    });
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
