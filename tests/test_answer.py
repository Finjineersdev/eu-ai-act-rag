from types import SimpleNamespace as NS

import pytest

from actrag.answer import RefusedError, TruncatedError, answer


class FakeClient:
    def __init__(self, message, rewrite="the use of AI systems to infer emotions in the workplace"):
        self.kw = None
        self.rewrite_kw = None
        self.beta = NS(messages=NS(create=self._create))
        self.messages = NS(create=self._rewrite)
        self._message = message
        self._rewrite_text = rewrite

    def _rewrite(self, **kw):
        self.rewrite_kw = kw
        if isinstance(self._rewrite_text, Exception):
            raise self._rewrite_text
        return NS(content=[NS(type="text", text=self._rewrite_text)])

    def _create(self, **kw):
        self.kw = kw
        return self._message


def message(stop="end_turn", content=None):
    return NS(stop_reason=stop, content=content or [], model="claude-opus-5-5")


def run(retriever, msg, history=()):
    client = FakeClient(msg)
    result = answer("Which AI practices are prohibited?", list(history), retriever, client)
    return client.kw, result


def test_request_shape(retriever):
    kw, _ = run(retriever, message())
    assert kw["model"] == "claude-opus-5-5"
    assert kw["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in kw["betas"]
    assert kw["output_config"] == {"effort": "medium"}
    content = kw["messages"][-1]["content"]
    docs = [b for b in content if b["type"] == "document"]
    assert docs and all(d["citations"] == {"enabled": True} for d in docs)
    assert content[-1] == {"type": "text", "text": "Which AI practices are prohibited?"}


def test_truncation_raises(retriever):
    with pytest.raises(TruncatedError):
        run(retriever, message(stop="max_tokens"))


def test_refusal_raises(retriever):
    with pytest.raises(RefusedError):
        run(retriever, message(stop="refusal"))


def test_not_in_act_tool(retriever):
    tool = NS(type="tool_use", name="not_in_act", input={"reason": "GDPR"})
    _, r = run(retriever, message(stop="tool_use", content=[tool]))
    assert r.status == "not_in_act"


def test_history_is_plain_text(retriever):
    hist = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    kw, _ = run(retriever, message(), hist)
    assert kw["messages"][:2] == hist


def test_cited_answer_round_trip(retriever):
    kw_probe, _ = run(retriever, message())
    first = kw_probe["messages"][-1]["content"][0]["source"]["data"]
    cite = NS(
        type="char_location",
        document_index=0,
        cited_text=first[:50],
        start_char_index=0,
        end_char_index=50,
    )
    _, r = run(retriever, message(content=[NS(type="text", text="Yes.", citations=[cite])]))
    assert r.status == "answered" and r.citations


class SpyRetriever:
    def __init__(self, inner):
        self.inner, self.queries = inner, []

    def search(self, q, k=8):
        self.queries.append(q)
        return self.inner.search(q, k)


def test_search_uses_question_plus_rewrite(retriever):
    spy = SpyRetriever(retriever)
    client = FakeClient(message())
    answer("Can employers use emotion recognition?", [], spy, client)
    expected = "Can employers use emotion recognition?\nthe use of AI systems to infer emotions in the workplace"
    assert spy.queries == [expected]
    assert client.rewrite_kw["model"] == "claude-haiku-5-5"


def test_rewrite_failure_falls_back_to_question(retriever):
    import anthropic

    spy = SpyRetriever(retriever)
    client = FakeClient(message(), rewrite=anthropic.APIConnectionError(request=None))
    answer("What does Article 5 prohibit?", [], spy, client)
    assert spy.queries == ["What does Article 5 prohibit?"]


def test_question_sent_to_model_is_original(retriever):
    kw, _ = run(retriever, message())
    assert kw["messages"][-1]["content"][-1]["text"] == "Which AI practices are prohibited?"


def test_history_markers_stripped(retriever):
    hist = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "Yes [1]. No [2]."}]
    kw, _ = run(retriever, message(), hist)
    assert kw["messages"][1]["content"] == "Yes. No."
