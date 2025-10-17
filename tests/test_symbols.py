from datetime import datetime
from core.symbols import resolve_front_month


def test_resolve_front_month_quarters():
    roots = ["NQ", "MNQ"]
    months = {
        1: "H", 2: "H", 3: "H",
        4: "M", 5: "M", 6: "M",
        7: "U", 8: "U", 9: "U",
        10: "Z", 11: "Z", 12: "Z",
    }
    for m, code in months.items():
        for r in roots:
            _, sym = resolve_front_month(r, now=datetime(2025, m, 15))
            assert sym.startswith(r + code)



