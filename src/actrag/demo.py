"""Public demo mode (env DEMO=1): rate limit, visitor keys, spend-cap detection."""

from __future__ import annotations

import os
import threading
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
        self.lock = threading.Lock()  # requests run on a thread pool

    def check(self, ip: str) -> str | None:
        """None if allowed (and recorded); else "rate_limited" (this visitor) or "busy" (everyone)."""
        with self.lock:
            now = self.clock()
            cutoff = now - self.window
            while self.all and self.all[0] <= cutoff:
                self.all.popleft()
            if len(self.hits) > self.total:  # every live visitor holds a global slot
                self.hits = {k: q for k, q in self.hits.items() if q and q[-1] > cutoff}
            mine = self.hits.get(ip)  # .get: a denied visitor never creates an entry
            while mine and mine[0] <= cutoff:
                mine.popleft()
            if mine is not None and not mine:
                del self.hits[ip]
                mine = None
            if mine and len(mine) >= self.per_ip:
                return "rate_limited"
            if len(self.all) >= self.total:
                return "busy"
            self.hits.setdefault(ip, deque()).append(now)
            self.all.append(now)
            return None

    def allow(self, ip: str) -> bool:
        return self.check(ip) is None


def client_ip(request) -> str:
    """The visitor's address as added by the hosting proxy.

    Proxies append to X-Forwarded-For, so the trustworthy entry is PROXY_HOPS from the right;
    anything further left was sent by the visitor and can be faked.
    """
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    try:
        n = max(1, int(os.environ.get("PROXY_HOPS", "1")))
    except ValueError:
        n = 1
    if not hops:
        return request.client.host
    return hops[-n] if len(hops) >= n else hops[0]


def visitor_key(request) -> str | None:
    return request.headers.get("x-anthropic-key", "").strip() or None


def is_spend_cap(err: anthropic.APIStatusError) -> bool:
    """The owner's key hit the Console spend limit, a tier spend cap, or a billing problem."""
    if err.status_code == 402:
        return True
    error = (err.body or {}).get("error", {}) if isinstance(err.body, dict) else {}
    if (error.get("details") or {}).get("error_code") == "enforced_spend_limit_reached":
        return True
    # the Console limit you set yourself comes back as a 400 with this message (account or workspace)
    message = error.get("message") or str(err)
    return err.status_code == 400 and message.startswith("You have reached your specified")
