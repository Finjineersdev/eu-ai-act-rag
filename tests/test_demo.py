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


def test_client_ip_forwarded():
    assert client_ip(req({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})) == "1.2.3.4"
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
