import pytest
from fastapi.testclient import TestClient

from actrag import api
from actrag.answer import RefusedError, TruncatedError
from actrag.verify import Citation, Result


@pytest.fixture
def client(monkeypatch, retriever):
    calls = {}

    def fake_answer(question, history, retriever, client):
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
