"""Per-user token bucket: `rate_per_min` requests per minute, bursts up to the same size."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(self, rate_per_min: int, clock: Callable[[], float] = time.monotonic):
        self.capacity = float(rate_per_min)
        self.refill_per_s = rate_per_min / 60.0
        self.clock = clock
        self._state: dict[str, tuple[float, float]] = {}  # user -> (tokens, last)
        self._lock = threading.Lock()

    def take(self, user: str) -> tuple[bool, int]:
        """(allowed, retry_after_seconds)."""
        with self._lock:
            now = self.clock()
            tokens, last = self._state.get(user, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_s)
            if tokens >= 1.0:
                self._state[user] = (tokens - 1.0, now)
                return True, 0
            self._state[user] = (tokens, now)
            return False, max(1, math.ceil((1.0 - tokens) / self.refill_per_s))
