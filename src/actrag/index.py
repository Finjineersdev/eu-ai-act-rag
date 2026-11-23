"""Build the embedding index. Run `python -m actrag.index` after ingest."""

from __future__ import annotations

import numpy as np

from actrag.ingest import DATA, Chunk, load_corpus

EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384-dim, ~67 MB ONNX, English
INDEX = DATA / "index.npz"


def doc_text(c: Chunk) -> str:
    return f"{c.title}\n{c.text}"


def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(EMBED_MODEL)


def build_index(chunks: list[Chunk]) -> None:
    vectors = np.array(list(_model().passage_embed([doc_text(c) for c in chunks])), np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    np.savez_compressed(INDEX, vectors=vectors, ids=np.array([c.id for c in chunks]))


def query_embedder():
    model = _model()

    def embed(text: str) -> np.ndarray:
        v = next(iter(model.query_embed([text]))).astype(np.float32)
        return v / np.linalg.norm(v)

    return embed


if __name__ == "__main__":
    build_index(load_corpus())
    print(f"wrote {INDEX} ({INDEX.stat().st_size / 1e6:.1f} MB)")
