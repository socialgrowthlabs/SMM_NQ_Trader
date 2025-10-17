#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

ORDERS = Path('storage/state/orders.json')
ACCOUNTS = {"APEX-196119-166", "APEX-196119-167"}

summary = {a: {"action": Counter(), "status": Counter(), "bracket_type": Counter()} for a in ACCOUNTS}
if ORDERS.exists():
    with ORDERS.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            a = o.get('account_id')
            if a not in ACCOUNTS:
                continue
            summary[a]['action'][str(o.get('action'))] += 1
            summary[a]['status'][str(o.get('status'))] += 1
            summary[a]['bracket_type'][str(o.get('bracket_type'))] += 1

for a in sorted(ACCOUNTS):
    s = summary[a]
    print(f"{a}:")
    print("  actions:", dict(s['action']))
    print("  status :", dict(s['status']))
    print("  brackets:", dict(s['bracket_type']))



