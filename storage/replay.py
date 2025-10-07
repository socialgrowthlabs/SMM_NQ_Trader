from typing import Iterable, Tuple

class ReplaySource:
    def __init__(self, lines: Iterable[str]) -> None:
        self._lines = iter(lines)

    def __iter__(self):
        return self

    def __next__(self) -> Tuple[str, float, float]:
        line = next(self._lines)
        ts, b, s = line.strip().split(",")
        return ts, float(b), float(s)
