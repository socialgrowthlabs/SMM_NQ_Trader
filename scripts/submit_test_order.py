import asyncio
import os
from dotenv import load_dotenv
from async_rithmic import RithmicClient
from async_rithmic.enums import TransactionType, OrderType, OrderDuration
from pathlib import Path
import json
import time


async def main() -> None:
    try:
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
        user = os.getenv("RITHMIC_USERNAME", "")
        password = os.getenv("RITHMIC_PASSWORD", "")
        system_name = os.getenv("RITHMIC_SYSTEM", "")
        app_name = os.getenv("APP_NAME", "SMMNQTrader")
        app_version = os.getenv("APP_VERSION", "0.1.0")
        url = os.getenv("RITHMIC_URL", "")
        exchange = os.getenv("RITHMIC_EXCHANGE", "CME")
        whitelist = set((os.getenv("WHITELIST_ACCOUNTS", "").split(",")))
        account_id = os.getenv("TEST_ACCOUNT_ID", "APEX-196119-167")
        print("ENV:", {"user": user, "system": system_name, "url": url, "exchange": exchange, "account": account_id}, flush=True)
        if account_id not in whitelist:
            raise SystemExit(f"Account {account_id} is not in WHITELIST_ACCOUNTS={whitelist}; aborting test.")

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

        # Setup event logging similar to main client
        state_dir = Path(os.path.join(os.path.dirname(__file__), "..", "storage", "state")).resolve()
        state_dir.mkdir(parents=True, exist_ok=True)
        orders_path = state_dir / "orders.json"

        def write_order_event(kind: str, event_obj) -> None:
            try:
                acct = getattr(event_obj, "account_id", None) or getattr(event_obj, "account", None)
                sym = getattr(event_obj, "symbol", None)
                user_tag = getattr(event_obj, "user_tag", None) or getattr(event_obj, "client_order_id", None) or getattr(event_obj, "order_id", None)
                status = getattr(event_obj, "status", None) or getattr(event_obj, "exchange_order_notification_type", None)
                reject_code = getattr(event_obj, "reject_code", None) or getattr(event_obj, "rq_handler_rp_code", None)
                filled_qty = getattr(event_obj, "filled_quantity", None) or getattr(event_obj, "filled_qty", None)
                leaves_qty = getattr(event_obj, "leaves_quantity", None) or getattr(event_obj, "remaining_qty", None)
                price = getattr(event_obj, "price", None) or getattr(event_obj, "avg_price", None)
                bracket_type = getattr(event_obj, "bracket_type", None)
                st = str(status) if status is not None else ""
                payload = {
                    "ts": time.time(),
                    "kind": kind,
                    "account_id": acct,
                    "symbol": sym,
                    "user_tag": str(user_tag) if user_tag is not None else None,
                    "status": st or None,
                    "reject_code": str(reject_code) if reject_code is not None else None,
                    "filled_qty": int(filled_qty) if filled_qty is not None else None,
                    "leaves_qty": int(leaves_qty) if leaves_qty is not None else None,
                    "price": float(price) if price is not None else None,
                    "bracket_type": str(bracket_type) if bracket_type is not None else None,
                }
                with orders_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(payload) + "\n")
            except Exception:
                pass

        async def on_rithmic_order(evt):
            write_order_event("rithmic_order", evt)
        async def on_exchange_order(evt):
            write_order_event("exchange_order", evt)
        async def on_bracket(evt):
            write_order_event("bracket_update", evt)
        client.on_rithmic_order_notification += on_rithmic_order
        client.on_exchange_order_notification += on_exchange_order
        client.on_bracket_update += on_bracket

        print("CONNECTING...", flush=True)
        await client.connect()
        print("CONNECTED", flush=True)
        try:
            # Resolve MNQ front-month symbol
            try:
                fut = await ticker.get_front_month_contract("MNQ", exchange)
                symbol = getattr(fut, "symbol", None)
            except Exception as e:
                print("FRONT_MONTH_ERR:", repr(e), flush=True)
                symbol = None
            symbol = symbol or os.getenv("TEST_SYMBOL", "MNQ")
            print("TEST_ORDER_SYMBOL:", symbol, flush=True)

            order_id = f"TEST-{account_id}"
            tx = TransactionType.BUY
            ot = OrderType.MARKET
            qty = int(os.getenv("TEST_QTY", "1"))
            target_ticks = int(os.getenv("TEST_TARGET_TICKS", "10"))
            stop_ticks = int(os.getenv("TEST_STOP_TICKS", "12"))

            # Submit bracket market order
            print("SUBMITTING...", flush=True)
            resp = await orders.submit_order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                qty=qty,
                transaction_type=tx,
                order_type=ot,
                account_id=account_id,
                target_ticks=target_ticks,
                stop_ticks=stop_ticks,
                duration=OrderDuration.DAY,
            )
            print("SUBMIT_RESP:", resp, flush=True)
            # Wait briefly for any acks
            await asyncio.sleep(5)
        finally:
            await client.disconnect()
            print("DISCONNECTED", flush=True)
    except SystemExit as e:
        print("EXIT:", e, flush=True)
    except Exception as e:
        import traceback
        print("ERROR:", repr(e), flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())


