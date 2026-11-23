"""HTTP API and the one-page UI."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from actrag import answer as answer_mod
from actrag.answer import RefusedError, TruncatedError, answer
from actrag.ingest import DATA

DISCLAIMER = "Research aid based on the text of Regulation (EU) 2024/1689. Not legal advice."
STATIC = Path(__file__).parent / "static"
META = json.loads((DATA / "corpus_meta.json").read_text())
gen = META.get("generated_on") or ""
CORPUS_DATE = f"{gen[:4]}-{gen[4:6]}-{gen[6:]}" if len(gen) == 8 else META["retrieved_at"]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=8000)]


class Ask(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    history: list[Turn] = Field(default_factory=list, max_length=4)


def create_app(retriever=None, llm=None) -> FastAPI:
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
            app.state.llm = anthropic.Anthropic()
        else:
            app.state.llm = None  # /health and the UI still work; /ask explains what's missing
        yield

    app = FastAPI(title="EU AI Act RAG", lifespan=lifespan)

    @app.post("/ask")
    def ask(body: Ask, request: Request):
        if request.app.state.llm is None:
            return JSONResponse({"error": "no_api_key"}, status_code=503)
        history = [t.model_dump() for t in body.history]
        try:
            r = answer(body.question, history, request.app.state.retriever, request.app.state.llm)
        except TruncatedError:
            return JSONResponse({"error": "truncated"}, status_code=502)
        except RefusedError:
            return JSONResponse({"error": "refused"}, status_code=502)
        except anthropic.APIError:
            return JSONResponse({"error": "upstream"}, status_code=503)
        return {
            "status": r.status,
            "answer": r.answer,
            "citations": [asdict(c) for c in r.citations],
            "model": answer_mod.MODEL,
            "corpus_date": CORPUS_DATE,
            "disclaimer": DISCLAIMER,
        }

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
