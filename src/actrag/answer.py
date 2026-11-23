"""Ask Claude with the retrieved chunks as citable documents, then verify the citations."""

from __future__ import annotations

import os

from actrag.verify import Result, verify

MODEL = os.environ.get("MODEL", "claude-opus-5-5")
NOT_IN_ACT = "That question is outside the EU AI Act, so I can't answer it from this text."

SYSTEM = """You answer questions about the EU AI Act (Regulation (EU) 2024/1689) using only \
the documents provided, which are excerpts of its official text.

- Cite the documents for every factual sentence. Do not state anything the documents do not support.
- If the documents do not answer the question, say so plainly instead of guessing.
- Call the not_in_act tool only when answering would need the text of a different law \
(for example the GDPR's own rules, US law, or national law). Questions about what the AI Act \
itself says, including how it refers to other laws, are in scope.
- If the user disputes an earlier answer, change it only if they point to text in the documents \
that supports the change. Otherwise restate your answer and its citations politely.
- Be concise: a direct answer first, then the supporting detail."""

TOOLS = [
    {
        "name": "not_in_act",
        "description": "Use when the question cannot be answered from the EU AI Act's text "
        "because it needs another law.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    }
]


class TruncatedError(Exception):
    """The reply hit max_tokens; a partial answer is never returned."""


class RefusedError(Exception):
    """The model (and its fallbacks) declined the request."""


def answer(question: str, history: list[dict], retriever, client, k: int = 8) -> Result:
    docs = retriever.search(question, k=k)
    content = [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": d.text},
            "title": f"{d.ref} – {d.title}",
            "citations": {"enabled": True},
        }
        for d in docs
    ]
    content.append({"type": "text", "text": question})
    messages = [{"role": h["role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": content})

    msg = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        tools=TOOLS,
        tool_choice={"type": "auto"},
        messages=messages,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if msg.stop_reason == "max_tokens":
        raise TruncatedError
    if msg.stop_reason == "refusal":
        raise RefusedError
    if any(b.type == "tool_use" and b.name == "not_in_act" for b in msg.content):
        return Result("not_in_act", NOT_IN_ACT)
    return verify(msg.content, docs)
