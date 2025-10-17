from __future__ import annotations

from datetime import datetime
from typing import Tuple


_QUARTER_CODES = {1: "H", 2: "M", 3: "U", 4: "Z"}


def _quarter_of_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def resolve_front_month(symbol_root: str, now: datetime | None = None) -> Tuple[str, str]:
    """Resolve front-month CME equity index symbol for a root like 'NQ' or 'MNQ'.

    Simplified quarterly mapping: H (Mar), M (Jun), U (Sep), Z (Dec).
    Uses the current calendar quarter code with 1-digit year (e.g., 2025 -> '5').

    Returns a tuple of (front_root_symbol, front_symbol), e.g., ('NQ', 'NQZ5').
    """
    now = now or datetime.utcnow()
    q = _quarter_of_month(now.month)
    code = _QUARTER_CODES[q]
    year_digit = str(now.year)[-1]
    return symbol_root, f"{symbol_root}{code}{year_digit}"



