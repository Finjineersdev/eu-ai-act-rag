"""Public demo mode (env DEMO=1): rate limit, visitor keys, spend-cap detection."""

from __future__ import annotations

import os
import time
from collections import deque

import anthropic

DEMO_MODEL = "claude-haiku-5-5"  # visitors without a key
FULL_MODEL = "claude-opus-5-5"  # saved examples and visitors who bring a key


def demo_on() -> bool:
    return os.environ.get("DEMO") == "1"


class Limiter:
    """Sliding-window limit per visitor IP and across all visitors.

    # ponytail: in-memory, one process; move to Redis if the demo ever runs more than one replica.
    """

    def __init__(
        self, per_ip: int = 5, total: int = 100, window: float = 3600, clock=time.monotonic
    ):
        self.per_ip, self.total, self.window, self.clock = per_ip, total, window, clock
        self.hits: dict[str, deque] = {}
        self.all: deque = deque()

    def allow(self, ip: str) -> bool:
        now = self.clock()
        cutoff = now - self.window
        while self.all and self.all[0] <= cutoff:
            self.all.popleft()
        if (
            len(self.hits) > self.total
        ):  # every live visitor holds a global slot, so this bounds memory
            self.hits = {k: q for k, q in self.hits.items() if q[-1] > cutoff}
        mine = self.hits.get(ip)  # .get: a denied visitor never creates an entry
        while mine and mine[0] <= cutoff:
            mine.popleft()
        if len(self.all) >= self.total or (mine and len(mine) >= self.per_ip):
            return False
        self.hits.setdefault(ip, deque()).append(now)
        self.all.append(now)
        return True


def client_ip(request) -> str:
    # Left-most hop = the visitor as the Space's proxy saw it. Spoofable, but a spoofer only gets
    # their own extra quota: the global cap (the cost bound) still holds.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or request.client.host


def visitor_key(request) -> str | None:
    return request.headers.get("x-anthropic-key", "").strip() or None


def is_spend_cap(err: anthropic.APIStatusError) -> bool:
    """The owner's key hit a billing problem or the Console monthly spend limit."""
    if err.status_code == 402:
        return True
    text = str(err).lower()
    return err.status_code == 429 and any(w in text for w in ("spend", "credit", "billing"))
