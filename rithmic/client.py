import asyncio
import os
from dataclasses import dataclass, field
from typing import Dict

import uvloop

# from async_rithmic import RithmicClient, TickerPlant, OrderPlant, PnLPlant

@dataclass
class Subscription:
    symbol: str
    depth: int
    mbo: bool

@dataclass
class UsernameSession:
    username: str
    password: str
    system: str
    location: str
    connected: bool = False
    desired_subs: Dict[str, Subscription] = field(default_factory=dict)

class RithmicOrchestrator:
    def __init__(self) -> None:
        self.sessions: Dict[str, UsernameSession] = {}

    async def ensure_session(self, username: str, password: str, system: str, location: str) -> UsernameSession:
        sess = self.sessions.get(username)
        if not sess:
            sess = UsernameSession(username=username, password=password, system=system, location=location)
            self.sessions[username] = sess
        if not sess.connected:
            # Connect RithmicClient and plants, attach callbacks, start tasks
            sess.connected = True
        return sess

    async def subscribe(self, username: str, symbol: str, depth: int, mbo: bool) -> None:
        sess = self.sessions[username]
        sess.desired_subs[symbol] = Subscription(symbol=symbol, depth=depth, mbo=mbo)
        # On reconnect, iterate desired_subs to re-register

    async def run(self) -> None:
        while True:
            await asyncio.sleep(0.5)

async def main() -> None:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    username = os.getenv("RITHMIC_USERNAME", "")
    password = os.getenv("RITHMIC_PASSWORD", "")
    system = os.getenv("RITHMIC_SYSTEM", "Rithmic01PaperTrading")
    location = os.getenv("RITHMIC_LOCATION", "Chicago_Azure")

    orch = RithmicOrchestrator()
    await orch.ensure_session(username, password, system, location)
    await orch.run()

if __name__ == "__main__":
    asyncio.run(main())
