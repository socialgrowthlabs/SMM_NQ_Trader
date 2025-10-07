import numpy as np
from typing import Optional

class RingBuffer:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=np.float64)
        self.index = 0
        self.size = 0

    def append(self, value: float) -> None:
        self.buffer[self.index] = value
        self.index = (self.index + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def values(self) -> np.ndarray:
        if self.size < self.capacity:
            return self.buffer[:self.size]
        return np.concatenate((self.buffer[self.index:], self.buffer[:self.index]))

class Ema:
    def __init__(self, period: int) -> None:
        self.alpha = 2.0 / (period + 1)
        self.prev: Optional[float] = None
        self.prev_prev: Optional[float] = None

    def update(self, price: float) -> float:
        if self.prev is None:
            self.prev = price
            self.prev_prev = price
        else:
            self.prev_prev = self.prev
            self.prev = (price - self.prev) * self.alpha + self.prev
        return self.prev

    def slope(self) -> float:
        if self.prev is None or self.prev_prev is None:
            return 0.0
        return self.prev - self.prev_prev
