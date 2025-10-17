#!/usr/bin/env python3
import json, sys
from pathlib import Path

p = Path('storage/state/metrics.json')
if not p.exists():
    print(0)
    sys.exit(0)

last = None
with p.open('r', encoding='utf-8') as f:
    for ln in f:
        last = ln
if not last:
    print(0)
    sys.exit(0)

try:
    m = json.loads(last)
except Exception:
    print(0)
    sys.exit(0)

print(m.get('counts', {}).get('pnl', 0))



