import asyncio
import os
from typing import List

import uvloop
from async_rithmic import RithmicClient, DataType
from dotenv import load_dotenv

async def run_with_smm_subs(seconds: int) -> None:
    user = os.getenv("RITHMIC_USERNAME", "")
    password = os.getenv("RITHMIC_PASSWORD", "")
    system_name = os.getenv("RITHMIC_SYSTEM", "")
    app_name = os.getenv("APP_NAME", "SMMNQTrader")
    app_version = os.getenv("APP_VERSION", "0.1.0")
    url = os.getenv("RITHMIC_URL", "")
    exchange = os.getenv("RITHMIC_EXCHANGE", "CME")
    symbols_env = os.getenv("RITHMIC_SYMBOLS", "NQZ5,MNQZ5")
    symbols: List[str] = [s.strip() for s in symbols_env.split(",") if s.strip()]
    if not (user and password and system_name and url):
        raise RuntimeError("Missing required env: RITHMIC_USERNAME,RITHMIC_PASSWORD,RITHMIC_SYSTEM,RITHMIC_URL")

    client = RithmicClient(user=user, password=password, system_name=system_name, app_name=app_name, app_version=app_version, url=url)

    ticker = client.plants["ticker"]
    orders = client.plants["order"]
    pnl = client.plants["pnl"]

    tick_count = 0
    depth_count = 0
    pnl_count = 0

    # Event wiring
    async def on_tick(data):
        nonlocal tick_count
        tick_count += 1

    async def on_order_book(data):
        nonlocal depth_count
        depth_count += 1

    async def on_account_pnl_update(update):
        nonlocal pnl_count
        pnl_count += 1

    client.on_tick += on_tick
    client.on_order_book += on_order_book
    client.on_market_depth += on_order_book
    client.on_account_pnl_update += on_account_pnl_update

    await client.connect()
    print("CONNECTED", user, system_name, url, flush=True)

    # List accounts via OrderPlant
    try:
        accts = await orders.list_accounts()
        print("ACCOUNTS:", accts, flush=True)
    except Exception as e:
        print("LIST_ACCOUNTS_ERROR:", repr(e), flush=True)

    # Subscribe PnL updates
    await pnl.subscribe_to_pnl_updates()

    # Subscribe market data for symbols (last trade + order book)
    for sym in symbols:
        await ticker.subscribe_to_market_data(sym, exchange, DataType.LAST_TRADE)
        await ticker.subscribe_to_market_depth(sym, exchange, depth_price=10.0)

    try:
        await asyncio.sleep(seconds)
        print(f"COUNTS tick={tick_count} depth={depth_count} pnl={pnl_count}", flush=True)
    finally:
        for sym in symbols:
            try:
                await ticker.unsubscribe_from_market_data(sym, exchange, DataType.LAST_TRADE)
                await ticker.unsubscribe_from_market_depth(sym, exchange, depth_price=10.0)
            except Exception:
                pass
        try:
            await pnl.unsubscribe_from_pnl_updates()
        except Exception:
            pass
        await client.disconnect()
        print("DISCONNECTED", flush=True)

async def main() -> None:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    load_dotenv()
    seconds = int(os.getenv("SUBS_SMOKE_SECS", "20"))
    await run_with_smm_subs(seconds)

if __name__ == "__main__":
    asyncio.run(main())
