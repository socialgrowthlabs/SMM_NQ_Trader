# SMM NQ Trader

Production-ready, ultra-low latency auto-trading platform for NQ (and MNQ) futures.

## Features
- Single `RithmicClient` per username with multiplexed sub-accounts.
- async-rithmic-based market data, orders, PnL plants with reconnect + re-subscribe. See `async-rithmic` docs: https://async-rithmic.readthedocs.io/en/latest/
- Microstructure feature engine: CVD slope, depth imbalance, depth slope, aggressive trade ratio.
- EMA21 trend filter + deltaConfidence gating; bracket/OCO placeholders.
- Per-account fan-out execution, reconciliation, and risk isolation.
- FastAPI dashboard with WebSocket for live control + monitoring.
- Replay mode for offline testing.

## Setup
1. Install Python 3.12
2. Install deps (Poetry preferred)

```bash
poetry install --no-root
cp .env.example .env
# fill in Rithmic creds
```

## Run
- Dashboard: `uvicorn web.server:app --reload`
- Trader: `python -m rithmic.client`

## Config
- `config/config.yaml`: strategy, risk, subs, backoff
- `accounts/accounts.yaml`: per-username accounts

## Notes
- Ensure only one connection per username; add multiple usernames if needed.
- Re-subscriptions are tracked in `RithmicOrchestrator.desired_subs`.
