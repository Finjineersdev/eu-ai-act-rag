"""HTTP API and the one-page UI."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from actrag import answer as answer_mod
from actrag.answer import RefusedError, TruncatedError, answer
from actrag.demo import (
    DEMO_MODEL,
    FULL_MODEL,
    Limiter,
    client_ip,
    demo_on,
    is_spend_cap,
    visitor_key,
)
from actrag.ingest import DATA

log = logging.getLogger("actrag")
DISCLAIMER = "Research aid based on the text of Regulation (EU) 2024/1689. Not legal advice."
STATIC = Path(__file__).parent / "static"
META = json.loads((DATA / "corpus_meta.json").read_text())
gen = META.get("generated_on") or ""
CORPUS_DATE = f"{gen[:4]}-{gen[4:6]}-{gen[6:]}" if len(gen) == 8 else META["retrieved_at"]


MAX_TURN_CHARS = 8000


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def clip(cls, v: str) -> str:  # long earlier answers are clipped, not rejected
        return v[:MAX_TURN_CHARS]


class Ask(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    history: list[Turn] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def alternating(self):
        if any(t.role != ("user", "assistant")[i % 2] for i, t in enumerate(self.history)):
            raise ValueError("history must alternate user/assistant, starting with user")
        return self


def create_app(retriever=None, llm=None, client_factory=anthropic.Anthropic) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if retriever is None:
            from actrag.retrieve import Retriever

            app.state.retriever = Retriever.load()
        else:
            app.state.retriever = retriever
        if llm is not None:
            app.state.llm = llm
        elif os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            # in the demo, a capped key should fail fast instead of retrying
            app.state.llm = anthropic.Anthropic(max_retries=1 if demo_on() else 2)
        else:
            app.state.llm = None  # /health and the UI still work; /ask explains what's missing
        app.state.limiter = Limiter()
        app.state.key_limiter = Limiter(per_ip=30, total=10**6)
        yield

    app = FastAPI(title="EU AI Act RAG", lifespan=lifespan)

    @app.post("/ask")
    def ask(body: Ask, request: Request):
        key = visitor_key(request)  # a visitor's own key: never logged, stored or echoed
        if key:
            # their key, their cost; a looser limit still stops junk keys from burning our CPU
            if request.app.state.key_limiter.check(client_ip(request)):
                return JSONResponse({"error": "rate_limited"}, status_code=429)
            llm, model = client_factory(api_key=key), FULL_MODEL
        elif request.app.state.llm is None:
            return JSONResponse({"error": "no_api_key"}, status_code=503)
        elif demo_on():
            ip = client_ip(request)
            denied = request.app.state.limiter.check(ip)
            if denied:
                log.warning("demo %s for %s", denied, ip)  # owner-only logs; checks PROXY_HOPS
                return JSONResponse({"error": denied}, status_code=429)
            llm, model = request.app.state.llm, DEMO_MODEL
        else:
            llm, model = request.app.state.llm, answer_mod.MODEL
        history = [t.model_dump() for t in body.history]
        try:
            r = answer(body.question, history, request.app.state.retriever, llm, model=model)
        except TruncatedError:
            return JSONResponse({"error": "truncated"}, status_code=502)
        except RefusedError:
            return JSONResponse({"error": "refused"}, status_code=502)
        except anthropic.APIStatusError as e:
            # their key is wrong, can't run this, or is out of credit: retrying won't help
            if key and (e.status_code in (401, 402, 403) or is_spend_cap(e)):
                return JSONResponse({"error": "bad_key"}, status_code=401)
            paused = not key and is_spend_cap(e)
            return JSONResponse({"error": "paused" if paused else "upstream"}, status_code=503)
        except anthropic.APIError:
            return JSONResponse({"error": "upstream"}, status_code=503)
        return {
            "status": r.status,
            "answer": r.answer,
            "citations": [asdict(c) for c in r.citations],
            "model": model,
            "corpus_date": CORPUS_DATE,
            "disclaimer": DISCLAIMER,
        }

    @app.get("/config")
    def config():
        demo = demo_on()
        return {"demo": demo, "model": DEMO_MODEL if demo else answer_mod.MODEL, "byok": demo}

    @app.get("/examples")
    def examples():
        f = STATIC / "examples.json"
        return json.loads(f.read_text()) if f.exists() else []

    @app.get("/health")
    def health(request: Request):
        return {
            "status": "ok",
            "corpus_date": CORPUS_DATE,
            "chunks": len(request.app.state.retriever.chunks),
        }

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def __getattr__(name):  # `uvicorn actrag.api:app` builds the real app on first access
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
