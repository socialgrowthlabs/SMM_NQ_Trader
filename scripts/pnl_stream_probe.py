#!/usr/bin/env python3
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from async_rithmic import RithmicClient


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


async def main():
    load_dotenv()
    user = os.getenv("RITHMIC_USERNAME", "")
    password = os.getenv("RITHMIC_PASSWORD", "")
    system_name = os.getenv("RITHMIC_SYSTEM", "")
    app_name = os.getenv("APP_NAME", "SMMNQTrader")
    app_version = os.getenv("APP_VERSION", "0.1.0")
    url = os.getenv("RITHMIC_URL", "")
    if not (user and password and system_name and url):
        raise RuntimeError("Missing Rithmic env: RITHMIC_USERNAME,RITHMIC_PASSWORD,RITHMIC_SYSTEM,RITHMIC_URL")

    account_dump = Path("/tmp/pnl_probe_account.json")
    instrument_dump = Path("/tmp/pnl_probe_instrument.json")

    client = RithmicClient(
        user=user,
        password=password,
        system_name=system_name,
        app_name=app_name,
        app_version=app_version,
        url=url,
    )

    first_account = True
    first_instrument = True

    async def on_account(evt):
        nonlocal first_account
        if not first_account:
            return
        first_account = False
        try:
            payload = {
                "attrs": [a for a in dir(evt) if not a.startswith("_")],
                "fields": to_field_map(evt),
            }
            account_dump.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    async def on_instrument(evt):
        nonlocal first_instrument
        if not first_instrument:
            return
        first_instrument = False
        try:
            payload = {
                "attrs": [a for a in dir(evt) if not a.startswith("_")],
                "fields": to_field_map(evt),
            }
            instrument_dump.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    await client.connect()
    client.on_account_pnl_update += on_account
    client.on_instrument_pnl_update += on_instrument
    await client.subscribe_to_pnl_updates()
    try:
        await asyncio.sleep(15)
    finally:
        try:
            await client.unsubscribe_from_pnl_updates()
        except Exception:
            pass
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())



