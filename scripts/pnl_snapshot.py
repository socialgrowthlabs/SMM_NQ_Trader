#!/usr/bin/env python3
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from async_rithmic import RithmicClient


STATE_DIR = Path(__file__).resolve().parents[1] / "storage" / "state"
ACCOUNTS_PATH = STATE_DIR / "accounts.json"


def load_accounts() -> List[Dict[str, Any]]:
    try:
        raw = ACCOUNTS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return list(data.get("accounts", []))
    except Exception:
        return []


def save_accounts(accounts: List[Dict[str, Any]]) -> None:
    ACCOUNTS_PATH.write_text(json.dumps({"ts": __import__("time").time(), "accounts": accounts}), encoding="utf-8")


def to_field_map(obj: Any) -> Dict[str, Any]:
    try:
        if hasattr(obj, "ListFields"):
            out: Dict[str, Any] = {}
            for desc, val in obj.ListFields():
                try:
                    out[desc.name] = val
                except Exception:
                    pass
            return out
    except Exception:
        pass
    return {}


def find_numeric_attr(obj: Any, name_hints: List[str]) -> Optional[float]:
    # Prefer protobuf fields
    fmap = to_field_map(obj)
    for k, v in fmap.items():
        low = k.lower()
        if any(h in low for h in name_hints):
            try:
                if isinstance(v, (int, float)):
                    return float(v)
            except Exception:
                continue
    try:
        for attr in dir(obj):
            if attr.startswith("_"):
                continue
            low = attr.lower()
            if any(h in low for h in name_hints):
                try:
                    val = getattr(obj, attr)
                    if isinstance(val, (int, float)):
                        return float(val)
                except Exception:
                    continue
    except Exception:
        pass
    return None


async def fetch_snapshots() -> None:
    load_dotenv()
    user = os.getenv("RITHMIC_USERNAME", "")
    password = os.getenv("RITHMIC_PASSWORD", "")
    system_name = os.getenv("RITHMIC_SYSTEM", "")
    app_name = os.getenv("APP_NAME", "SMMNQTrader")
    app_version = os.getenv("APP_VERSION", "0.1.0")
    url = os.getenv("RITHMIC_URL", "")
    if not (user and password and system_name and url):
        raise RuntimeError("Missing Rithmic env: RITHMIC_USERNAME, RITHMIC_PASSWORD, RITHMIC_SYSTEM, RITHMIC_URL")

    accounts = load_accounts()
    if not accounts:
        print("No accounts in accounts.json; nothing to refresh.")
        return
    account_ids = [str(a.get("account_id")) for a in accounts if a.get("account_id")]
    if not account_ids:
        print("No account_ids present in accounts.json; nothing to refresh.")
        return

    client = RithmicClient(
        user=user,
        password=password,
        system_name=system_name,
        app_name=app_name,
        app_version=app_version,
        url=url,
    )
    await client.connect()
    try:
        # Pull snapshots per account
        id_to_snap: Dict[str, Dict[str, Any]] = {}
        debug_dump: Dict[str, Any] = {"accounts": []}
        for aid in account_ids:
            try:
                snaps = await client.list_account_summary(account_id=aid)
            except Exception:
                snaps = None
            if not snaps:
                continue
            snap = snaps[0]
            # Collect first 30 simple attributes for debugging
            attrs = [a for a in dir(snap) if not a.startswith("_")]
            sample: Dict[str, Any] = {}
            for a in attrs[:30]:
                try:
                    v = getattr(snap, a)
                    if isinstance(v, (int, float, str)):
                        sample[a] = v
                except Exception:
                    pass
            debug_dump["accounts"].append({"account_id": aid, "attrs": attrs, "sample": sample})
            # Extract PnL/position with robust attribute matching (protobuf-aware)
            fmap = to_field_map(snap)
            unreal = None
            reald = None
            qty = None
            # Prefer day fields and open position fields per probe
            for key in ("day_pnl", "day_closed_pnl", "closed_position_pnl"):
                if key in fmap:
                    reald = fmap[key]
                    break
            for key in ("open_position_pnl", "day_open_pnl"):
                if key in fmap:
                    unreal = fmap[key]
                    break
            for key in ("net_quantity", "open_position_quantity", "net_position"):
                if key in fmap:
                    qty = fmap[key]
                    break
            # Secondary: traditional names
            if unreal is None:
                for key in ("unrealized_pnl", "account_unrealized_pnl", "unrealizedpnl", "unrlzd_pnl"):
                    if key in fmap:
                        unreal = fmap[key]
                        break
            if reald is None:
                for key in ("realized_pnl", "account_realized_pnl", "realizedpnl", "rlzd_pnl"):
                    if key in fmap:
                        reald = fmap[key]
                        break
            if qty is None:
                for key in ("net_position", "position", "open_position", "position_qty", "netpos"):
                    if key in fmap:
                        qty = fmap[key]
                        break
            # fallback by hints
            if unreal is None:
                unreal = find_numeric_attr(snap, ["unreal"])
            if reald is None:
                reald = find_numeric_attr(snap, ["realized", "realise", "real"])
            if qty is None:
                qty = find_numeric_attr(snap, ["position", "netpos"])  # may be float; will cast below
            try:
                q_int = int(qty) if qty is not None else None
            except Exception:
                q_int = None
            id_to_snap[aid] = {
                "unrealized_pnl": float(unreal) if unreal is not None else None,
                "daily_pnl": float(reald) if reald is not None else None,
                "position_qty": q_int,
            }

        # Merge into accounts.json
        out: List[Dict[str, Any]] = []
        for a in accounts:
            aid = str(a.get("account_id", ""))
            upd = id_to_snap.get(aid)
            if upd:
                if upd.get("unrealized_pnl") is not None:
                    a["unrealized_pnl"] = upd["unrealized_pnl"]
                if upd.get("daily_pnl") is not None:
                    a["daily_pnl"] = upd["daily_pnl"]
                if upd.get("position_qty") is not None:
                    q = int(upd["position_qty"])  # type: ignore[arg-type]
                    a["position_qty"] = q
                    a["position_side"] = ("LONG" if q > 0 else ("SHORT" if q < 0 else "FLAT"))
            out.append(a)
        save_accounts(out)
        try:
            Path('/tmp/account_summary_dump.json').write_text(json.dumps(debug_dump), encoding='utf-8')
        except Exception:
            pass
        print("Snapshots merged for:", ", ".join(sorted(id_to_snap.keys())))
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(fetch_snapshots())


