import pytest
from fastapi.testclient import TestClient

from actrag import api
from actrag.answer import RefusedError, TruncatedError
from actrag.verify import Citation, Result


@pytest.fixture
def client(monkeypatch, retriever):
    calls = {}

    def fake_answer(question, history, retriever, client, model=None):
        calls["history"] = history
        if question == "truncate":
            raise TruncatedError
        if question == "refuse":
            raise RefusedError
        return Result("answered", "Yes. [1]", [Citation("Article 5(1)", "q", "https://x#art_5")])

    monkeypatch.setattr(api, "answer", fake_answer)
    app = api.create_app(retriever=retriever, llm=object())
    with TestClient(app) as c:
        c.calls = calls
        yield c


def test_ask_ok_shape(client):
    r = client.post("/ask", json={"question": "Which practices are banned?"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "answer", "citations", "model", "corpus_date", "disclaimer"}
    assert body["citations"][0] == {"ref": "Article 5(1)", "quote": "q", "url": "https://x#art_5"}
    assert body["disclaimer"] == (
        "Research aid based on the text of Regulation (EU) 2024/1689. Not legal advice."
    )


def test_empty_question_422(client):
    assert client.post("/ask", json={"question": "   "}).status_code == 422


def test_too_long_question_422(client):
    assert client.post("/ask", json={"question": "x" * 2001}).status_code == 422


def test_history_over_4_422(client):
    h = [{"role": "user", "content": "a"}] * 5
    assert client.post("/ask", json={"question": "q", "history": h}).status_code == 422


def test_history_passed_as_plain_dicts(client):
    h = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    client.post("/ask", json={"question": "q", "history": h})
    assert client.calls["history"] == h


def test_truncated_502(client):
    r = client.post("/ask", json={"question": "truncate"})
    assert (r.status_code, r.json()) == (502, {"error": "truncated"})


def test_refused_502(client):
    r = client.post("/ask", json={"question": "refuse"})
    assert (r.status_code, r.json()) == (502, {"error": "refused"})


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["chunks"] > 0 and body["corpus_date"]


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "EU AI Act" in r.text


def test_upstream_error_503(monkeypatch, retriever):
    import anthropic

    def boom(*a, **k):
        raise anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(api, "answer", boom)
    with TestClient(api.create_app(retriever=retriever, llm=object())) as c:
        r = c.post("/ask", json={"question": "q"})
    assert (r.status_code, r.json()) == (503, {"error": "upstream"})


def test_missing_key_503(monkeypatch, retriever):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with TestClient(api.create_app(retriever=retriever)) as c:
        r = c.post("/ask", json={"question": "q"})
    assert (r.status_code, r.json()) == (503, {"error": "no_api_key"})


def test_long_assistant_history_truncated_not_rejected(client):
    h = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "x" * 20000}]
    r = client.post("/ask", json={"question": "q", "history": h})
    assert r.status_code == 200
    assert len(client.calls["history"][1]["content"]) == 8000


def test_history_must_alternate_starting_with_user(client):
    h = [{"role": "assistant", "content": "a"}]
    assert client.post("/ask", json={"question": "q", "history": h}).status_code == 422


# --- demo mode -------------------------------------------------------------------------

import anthropic
import httpx

from actrag.demo import DEMO_MODEL, FULL_MODEL

KEY = "sk-ant-visitor-secret-123"


def status_error(cls, status, message):
    r = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com"))
    return cls(message, response=r, body=None)


@pytest.fixture
def demo(monkeypatch, retriever):
    monkeypatch.setenv("DEMO", "1")
    seen = {"clients": []}

    def fake_answer(question, history, retriever, client, model=None):
        seen["model"], seen["client"] = model, client
        if question == "spend":
            raise status_error(anthropic.RateLimitError, 429, "monthly spend limit reached")
        if question == "badkey":
            raise status_error(anthropic.AuthenticationError, 401, "invalid x-api-key")
        return Result("answered", "Yes. [1]", [Citation("Article 5(1)", "q", "https://x#art_5")])

    def factory(api_key):
        seen["clients"].append(api_key)
        return ("visitor-client", api_key)

    monkeypatch.setattr(api, "answer", fake_answer)
    app = api.create_app(retriever=retriever, llm="owner-client", client_factory=factory)
    with TestClient(app) as c:
        c.seen = seen
        yield c


def test_demo_uses_haiku_without_key(demo):
    r = demo.post("/ask", json={"question": "q"})
    assert r.status_code == 200 and r.json()["model"] == DEMO_MODEL
    assert demo.seen["model"] == DEMO_MODEL and demo.seen["client"] == "owner-client"


def test_demo_rate_limited_after_5(demo):
    codes = [demo.post("/ask", json={"question": "q"}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert demo.post("/ask", json={"question": "q"}).json() == {"error": "rate_limited"}


def test_byok_uses_opus_and_skips_limit(demo):
    for _ in range(5):
        demo.post("/ask", json={"question": "q"})
    r = demo.post("/ask", json={"question": "q"}, headers={"X-Anthropic-Key": KEY})
    assert r.status_code == 200 and r.json()["model"] == FULL_MODEL
    assert demo.seen["clients"] == [KEY] and demo.seen["model"] == FULL_MODEL


def test_bad_key_401_never_echoed(demo):
    r = demo.post("/ask", json={"question": "badkey"}, headers={"X-Anthropic-Key": KEY})
    assert r.status_code == 401 and r.json() == {"error": "bad_key"}
    assert KEY not in r.text


def test_spend_cap_paused(demo):
    r = demo.post("/ask", json={"question": "spend"})
    assert r.status_code == 503 and r.json() == {"error": "paused"}


def test_config_endpoint(demo):
    assert demo.get("/config").json() == {"demo": True, "model": DEMO_MODEL, "byok": True}


def test_demo_off_unchanged(client):
    assert all(client.post("/ask", json={"question": "q"}).status_code == 200 for _ in range(7))
    assert client.get("/config").json()["demo"] is False
