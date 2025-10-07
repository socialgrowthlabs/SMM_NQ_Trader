from typing import Dict

class Reconciler:
    def __init__(self) -> None:
        self.account_health: Dict[str, str] = {}

    async def reconcile(self, account_id: str) -> None:
        self.account_health[account_id] = "ok"

    async def global_flatten(self) -> None:
        pass
