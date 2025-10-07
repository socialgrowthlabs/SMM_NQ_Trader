import uuid
from dataclasses import dataclass
from typing import Dict, List

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

    def set_accounts(self, accounts: List[str]) -> None:
        for acc in accounts:
            self.account_enabled[acc] = True
            self.open_orders.setdefault(acc, {})

    def _new_client_order_id(self, account_id: str) -> str:
        return f"{account_id}-{uuid.uuid4().hex[:12]}"

    async def submit_signal(self, symbol: str, side: str, qty: int, target_ticks: int, stop_ticks: int, accounts: List[str]) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        for acc in accounts:
            if not self.account_enabled.get(acc, False):
                continue
            coid = self._new_client_order_id(acc)
            intent = OrderIntent(
                account_id=acc, symbol=symbol, side=side, qty=qty, client_order_id=coid, target_ticks=target_ticks, stop_ticks=stop_ticks
            )
            self.open_orders[acc][coid] = intent
            intents.append(intent)
        return intents

    async def on_fill(self, account_id: str, client_order_id: str, fill_qty: int, fill_price: float) -> None:
        pass

    async def reconcile_account(self, account_id: str) -> None:
        pass
