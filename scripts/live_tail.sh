#!/usr/bin/env bash
set +u
set -eo pipefail

cd '/root/SMM NQ Trader' || exit 1

echo $$ >/tmp/live_tail_terminal.pid

while true; do
  printf '%s\n' "===== $(date -u '+%Y-%m-%dT%H:%M:%SZ') ====="
  for f in storage/state/metrics.json storage/state/signals.json storage/state/orders.json storage/state/accounts.json; do
    printf '%s\n' "-- $(basename "$f") (tail 5)"
    if [ -f "$f" ]; then
      tail -n 5 "$f"
    else
      echo 'missing'
    fi
    echo
  done
  printf '%s\n' "-- dashboard /status"
  curl -sS -m 2 http://127.0.0.1:7110/status | head -c 800 || true
  echo
  sleep 10
done


