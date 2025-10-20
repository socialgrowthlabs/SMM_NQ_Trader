#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from async_rithmic import RithmicClient, DataType

async def main():
    if os.getenv("TEST_ORDER", "0") != "1":
        print("TEST_ORDER not enabled; set TEST_ORDER=1 to run")
        return
    # Load project .env like the main trader does
    try:
        env_path = str((Path(__file__).resolve().parents[1] / ".env"))
        load_dotenv(dotenv_path=env_path)
    except Exception:
        load_dotenv()
    account = os.getenv("WHITELIST_ACCOUNTS", "").split(",")[0].strip()
    if not account:
        print("No WHITELIST_ACCOUNTS set")
        return
    symbol = os.getenv("RITHMIC_SYMBOLS", "NQZ5").split(",")[0].strip()
    user = os.getenv("RITHMIC_USERNAME"); pwd = os.getenv("RITHMIC_PASSWORD"); sysn = os.getenv("RITHMIC_SYSTEM"); url = os.getenv("RITHMIC_URL")
    if not (user and pwd and sysn and url):
        print("Missing Rithmic envs")
        return
    client = RithmicClient(user=user, password=pwd, system_name=sysn, url=url, app_name=os.getenv("APP_NAME","SMMNQTrader"))
    await client.connect()
    try:
        orders = client.plants["order"]
        print(f"TEST ORDER: submitting 1-lot MARKET {symbol} to {account}")
        resp = await orders.submit_order(order_id="TEST-ONE", symbol=symbol, exchange=os.getenv("RITHMIC_EXCHANGE","CME"), qty=1, transaction_type="BUY", order_type="MARKET", account_id=account)
        print(f"TEST ORDER RESP: {resp}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
