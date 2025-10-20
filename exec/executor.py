import os
import uuid
from dataclasses import dataclass
from typing import Optional
from typing import Dict, List
from collections import deque
import time
from async_rithmic.enums import TransactionType, OrderType, OrderDuration

@dataclass
class OrderIntent:
    account_id: str
    symbol: str
    side: str  # BUY/SELL
    qty: int
    client_order_id: str
    target_ticks: int
    stop_ticks: int

class ExecutionEngine:
    def __init__(self) -> None:
        self.account_enabled: Dict[str, bool] = {}
        self.open_orders: Dict[str, Dict[str, OrderIntent]] = {}
        self.order_plant = None
        self.default_exchange: Optional[str] = None
        self.trading_enabled: bool = bool(int(os.getenv("TRADING_ENABLED", "0")))
        # Risk state
        self.max_daily_drawdown: float = float(os.getenv("MAX_DAILY_DRAWDOWN", "250.0"))
        self.max_position: int = int(os.getenv("MAX_POSITION", "4"))
        self.max_orders_per_minute: int = int(os.getenv("MAX_ORDERS_PER_MINUTE", "60"))
        self.account_realized_pnl: Dict[str, float] = {}
        self.account_unrealized_pnl: Dict[str, float] = {}
        self.account_position_qty: Dict[str, int] = {}
        self.account_disabled: Dict[str, bool] = {}
        self.account_order_times: Dict[str, deque] = {}
        # Populated externally
        self.whitelist = set((os.getenv("WHITELIST_ACCOUNTS", "").split(",")))

    def attach_order_plant(self, order_plant, default_exchange: str) -> None:
        self.order_plant = order_plant
        self.default_exchange = default_exchange

    def set_accounts(self, accounts: List[str]) -> None:
        # Enforce whitelist if provided
        wl = set(a.strip() for a in os.getenv("WHITELIST_ACCOUNTS", "").split(",") if a.strip())
        for acc in accounts:
            if wl and acc not in wl:
                continue
            self.account_enabled[acc] = True
            self.open_orders.setdefault(acc, {})
            self.account_realized_pnl.setdefault(acc, 0.0)
            self.account_unrealized_pnl.setdefault(acc, 0.0)
            self.account_position_qty.setdefault(acc, 0)
            self.account_disabled.setdefault(acc, False)
            self.account_order_times.setdefault(acc, deque())

    def _new_client_order_id(self, account_id: str) -> str:
        return f"{account_id}-{uuid.uuid4().hex[:12]}"

    async def submit_signal(self, symbol: str, side: str, qty: int, target_ticks: int, stop_ticks: int, accounts: List[str], exchange: Optional[str] = None) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        for acc in accounts:
            if not self.account_enabled.get(acc, False):
                continue
            if self.account_disabled.get(acc, False):
                continue
            allow, _ = self._should_allow_order(acc, side, qty)
            if not allow:
                continue
            coid = self._new_client_order_id(acc)
            intent = OrderIntent(
                account_id=acc, symbol=symbol, side=side, qty=qty, client_order_id=coid, target_ticks=target_ticks, stop_ticks=stop_ticks
            )
            self.open_orders[acc][coid] = intent
            intents.append(intent)
            self._record_order_time(acc)
            # Optionally submit live order if enabled and plant is attached
            if self.trading_enabled and self.order_plant is not None and acc in self.whitelist:
                try:
                    tx = TransactionType.BUY if side.upper()=="BUY" else TransactionType.SELL
                    ot = OrderType.MARKET
                    ex = exchange or self.default_exchange or "CME"
                    await self.order_plant.submit_order(
                        order_id=coid, symbol=symbol, exchange=ex, qty=qty, transaction_type=tx, order_type=ot, account_id=acc, target_ticks=target_ticks, stop_ticks=stop_ticks, duration=OrderDuration.DAY
                    )
                except Exception:
                    pass
        return intents

    async def on_fill(self, account_id: str, client_order_id: str, fill_qty: int, fill_price: float) -> None:
        pass

    async def reconcile_account(self, account_id: str) -> None:
        pass

    async def reconcile_accounts(self, order_plant, pnl_plant) -> None:
        """Query live orders and positions and update internal state per account.
        This keeps the dashboard/account state in sync after reconnects.
        """
        try:
            # Sync orders
            try:
                live_orders = await order_plant.list_orders()
            except Exception:
                live_orders = []
            acct_to_orders: Dict[str, Dict[str, OrderIntent]] = {}
            for o in live_orders or []:
                aid = getattr(o, "account_id", None) or getattr(o, "account", None)
                coid = getattr(o, "user_tag", None) or getattr(o, "client_order_id", None) or getattr(o, "order_id", None)
                sym = getattr(o, "symbol", None)
                qty = int(getattr(o, "quantity", 0) or 0)
                side_val = getattr(o, "transaction_type", None)
                side = "BUY" if str(side_val).endswith("BUY") else ("SELL" if str(side_val).endswith("SELL") else "")
                if aid and coid and sym:
                    intent = OrderIntent(account_id=aid, symbol=sym, side=side or "", qty=qty, client_order_id=str(coid), target_ticks=0, stop_ticks=0)
                    acct_to_orders.setdefault(aid, {})[str(coid)] = intent
            # Overwrite snapshot for known accounts
            for acc in self.account_enabled.keys():
                self.open_orders[acc] = acct_to_orders.get(acc, {})
        except Exception:
            pass

        # Try to reconcile positions from available plants
        try:
            async def _fetch_positions(plant):
                # Try a few method names commonly used
                for name in ("list_positions", "get_positions", "positions", "list_open_positions", "get_open_positions"):
                    try:
                        method = getattr(plant, name)
                    except Exception:
                        method = None
                    if callable(method):
                        try:
                            return await method()
                        except Exception:
                            continue
                return []

            pos_list = []
            try:
                pos_list = await _fetch_positions(pnl_plant)
            except Exception:
                pos_list = []
            if not pos_list:
                try:
                    pos_list = await _fetch_positions(order_plant)
                except Exception:
                    pos_list = []

            acct_to_pos: Dict[str, int] = {}
            for p in pos_list or []:
                try:
                    aid = getattr(p, "account_id", None) or getattr(p, "account", None)
                    qty = None
                    for fname in ("net_position", "position", "open_position", "position_qty", "quantity"):
                        val = getattr(p, fname, None)
                        if val is not None:
                            try:
                                qty = int(val)
                                break
                            except Exception:
                                continue
                    if aid and qty is not None:
                        acct_to_pos[aid] = qty
                except Exception:
                    continue

            for acc, qty in acct_to_pos.items():
                self.account_position_qty[acc] = int(qty)
        except Exception:
            pass

    def update_account_pnl(self, account_id: str, realized: Optional[float], unrealized: Optional[float]) -> None:
        if realized is not None:
            self.account_realized_pnl[account_id] = float(realized)
        if unrealized is not None:
            self.account_unrealized_pnl[account_id] = float(unrealized)
        if self.account_realized_pnl.get(account_id, 0.0) <= -abs(self.max_daily_drawdown):
            self.account_disabled[account_id] = True

    def update_account_position(self, account_id: str, position_qty: Optional[int]) -> None:
        if position_qty is not None:
            self.account_position_qty[account_id] = int(position_qty)

    def _should_allow_order(self, account_id: str, side: str, qty: int) -> (bool, str):
        if self.account_disabled.get(account_id, False):
            try:
                print(f"VETO: {account_id} disabled_by_drawdown", flush=True)
            except Exception:
                pass
            return False, "disabled_by_drawdown"
        pos = self.account_position_qty.get(account_id, 0)
        signed = qty if side.upper() == "BUY" else -qty
        if abs(pos + signed) > abs(self.max_position):
            try:
                print(f"VETO: {account_id} max_position_exceeded pos={pos} qty={qty} side={side} max={self.max_position}", flush=True)
            except Exception:
                pass
            return False, "max_position_exceeded"
        dq = self.account_order_times.setdefault(account_id, deque())
        now = time.time()
        while dq and now - dq[0] > 60.0:
            dq.popleft()
        if len(dq) >= self.max_orders_per_minute:
            try:
                print(f"VETO: {account_id} rate_limited per_minute={self.max_orders_per_minute}", flush=True)
            except Exception:
                pass
            return False, "rate_limited"
        return True, "ok"

    def _record_order_time(self, account_id: str) -> None:
        self.account_order_times.setdefault(account_id, deque()).append(time.time())
