"""Hybrid retrieval: BM25 + embeddings fused with Reciprocal Rank Fusion, plus unit pinning."""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
from rank_bm25 import BM25Okapi

from actrag.ingest import Chunk

RRF_K = 60
CANDIDATES = 50
MAX_PINNED = 4
MAX_RECITALS = 2  # recitals explain; the obligations live in Articles and Annexes
MAX_PER_UNIT = 3
PIN = re.compile(r"\b(?:Article\s+(\d+)|Annex\s+([IVXL]+))\b", re.IGNORECASE)


def _tokens(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


class Retriever:
    def __init__(
        self, chunks: list[Chunk], vectors: np.ndarray, embed: Callable[[str], np.ndarray]
    ):
        self.chunks = chunks
        self.vectors = vectors
        self.embed = embed
        self.bm25 = BM25Okapi([_tokens(f"{c.title} {c.text}") for c in chunks])

    @classmethod
    def load(cls) -> Retriever:
        from actrag.index import INDEX, query_embedder
        from actrag.ingest import load_corpus

        chunks = load_corpus()
        data = np.load(INDEX)
        if list(data["ids"]) != [c.id for c in chunks]:
            raise RuntimeError("index.npz is out of date; run python -m actrag.index")
        return cls(chunks, data["vectors"], query_embedder())

    def search(self, question: str, k: int = 8) -> list[Chunk]:
        bm25 = np.argsort(-self.bm25.get_scores(_tokens(question)))[:CANDIDATES]
        dense = np.argsort(-(self.vectors @ self.embed(question)))[:CANDIDATES]
        score: dict[int, float] = {}
        for ranking in (bm25, dense):
            for rank, i in enumerate(ranking):
                score[int(i)] = score.get(int(i), 0.0) + 1 / (RRF_K + rank + 1)
        ranked = sorted(score, key=score.get, reverse=True)

        pinned_anchors = {f"art_{a}" if a else f"anx_{x.upper()}" for a, x in PIN.findall(question)}
        pinned = [i for i in ranked if self.chunks[i].anchor in pinned_anchors]
        # pinned units not reached by either ranking still count
        if len(pinned) < MAX_PINNED:
            pinned += [
                i
                for i, c in enumerate(self.chunks)
                if c.anchor in pinned_anchors and i not in pinned
            ]
        picked = pinned[:MAX_PINNED]
        per_unit: dict[str, int] = {}
        for i in picked:  # pinned chunks count toward their unit's cap
            per_unit[self.chunks[i].anchor] = per_unit.get(self.chunks[i].anchor, 0) + 1
        recitals = 0
        for i in ranked:
            if len(picked) >= k:
                break
            if i in picked:
                continue
            c = self.chunks[i]
            if per_unit.get(c.anchor, 0) >= MAX_PER_UNIT:
                continue
            if c.anchor.startswith("rct_"):
                if recitals >= MAX_RECITALS:
                    continue
                recitals += 1
            per_unit[c.anchor] = per_unit.get(c.anchor, 0) + 1
            picked.append(i)
        return [self.chunks[i] for i in picked[:k]]
