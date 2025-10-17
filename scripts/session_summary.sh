#!/usr/bin/env bash
set +u
set -eo pipefail
LOG=/tmp/session_summary.log
cd '/root/SMM NQ Trader'
while true; do
  {
    printf '===== %s =====\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    for f in storage/state/metrics.json storage/state/signals.json storage/state/orders.json; do
      if [ -f "$f" ]; then
        printf '-- %s lines: %s size: %s\n' "$(basename "$f")" "$(wc -l < "$f" 2>/dev/null || echo 0)" "$(stat -c %s "$f" 2>/dev/null || echo 0)"
        tail -n 5 "$f" || true
      else
        printf '-- %s missing\n' "$(basename "$f")"
      fi
    done
    printf '\n'
  } >> "$LOG" 2>&1
  sleep 120
done

