from types import SimpleNamespace as NS

import anthropic
import httpx

from actrag.demo import Limiter, client_ip, is_spend_cap, visitor_key


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_limiter_per_ip():
    clock = Clock()
    lim = Limiter(per_ip=5, total=100, window=3600, clock=clock)
    assert all(lim.allow("a") for _ in range(5))
    assert not lim.allow("a")
    assert lim.allow("b")
    clock.t = 3601
    assert lim.allow("a")


def test_limiter_total():
    lim = Limiter(per_ip=5, total=100, clock=Clock())
    assert all(lim.allow(f"ip{i}") for i in range(100))
    assert not lim.allow("ip100")


def test_denied_call_not_counted():
    clock = Clock()
    lim = Limiter(per_ip=1, total=100, window=10, clock=clock)
    assert lim.allow("a")
    clock.t = 5
    assert not lim.allow("a")  # denied: must not extend the window
    clock.t = 10.5
    assert lim.allow("a")


def req(headers=None, host="9.9.9.9"):
    return NS(headers=headers or {}, client=NS(host=host))


def test_client_ip_uses_hop_added_by_proxy(monkeypatch):
    spoofed = {
        "x-forwarded-for": "6.6.6.6, 1.2.3.4"
    }  # visitor sent 6.6.6.6; proxy appended 1.2.3.4
    assert client_ip(req(spoofed)) == "1.2.3.4"
    monkeypatch.setenv("PROXY_HOPS", "2")
    assert client_ip(req({"x-forwarded-for": "6.6.6.6, 1.2.3.4, 10.0.0.1"})) == "1.2.3.4"
    assert client_ip(req({"x-forwarded-for": "1.2.3.4"})) == "1.2.3.4"  # fewer hops than expected
    assert client_ip(req()) == "9.9.9.9"


def test_visitor_key_blank_is_none():
    assert visitor_key(req({"x-anthropic-key": "  "})) is None
    assert visitor_key(req()) is None
    assert visitor_key(req({"x-anthropic-key": " sk-ant-x "})) == "sk-ant-x"


def err(status, message):
    r = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.APIStatusError(message, response=r, body=None)


def test_is_spend_cap():
    assert is_spend_cap(err(402, "billing problem"))
    assert is_spend_cap(err(429, "You have reached your monthly spend limit"))
    assert not is_spend_cap(err(429, "Rate limit exceeded: 50 requests per minute"))
    assert not is_spend_cap(err(500, "internal"))


def test_limiter_memory_bounded():
    clock = Clock()
    lim = Limiter(per_ip=5, total=3, window=10, clock=clock)
    for i in range(1000):  # spoofed IPs after the global cap is hit
        lim.allow(f"fake{i}")
    assert len(lim.hits) == 3
    clock.t = 11
    lim.allow("new")
    assert len(lim.hits) <= 4  # expired visitors are dropped


def test_limiter_survives_emptied_visitor():
    clock = Clock()
    lim = Limiter(per_ip=5, total=2, window=10, clock=clock)
    lim.allow("a")
    clock.t = 11
    lim.allow("b")
    lim.allow("b")  # global cap full; hits = {a, b}
    assert not lim.allow("a")  # a's old hit expires, a is denied: no empty entry may remain
    clock.t = 21.5
    assert lim.allow("e")
    assert lim.allow("f")  # cleanup runs over every stored visitor and must not crash
    assert all(lim.hits.values())
