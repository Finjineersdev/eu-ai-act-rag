import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from actrag.ingest import parse

FIXTURE = (Path(__file__).parent / "fixtures" / "mini_act.xhtml").read_bytes()


def fake_embed(text: str) -> np.ndarray:
    """Hashed bag-of-words vector: deterministic, no model download."""
    v = np.zeros(256, dtype=np.float32)
    for w in re.findall(r"\w+", text.lower()):
        v[int(hashlib.md5(w.encode(), usedforsecurity=False).hexdigest(), 16) % 256] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


@pytest.fixture(scope="session")
def chunks():
    return parse(FIXTURE)


@pytest.fixture(scope="session")
def retriever(chunks):
    from actrag.retrieve import Retriever

    vectors = np.stack([fake_embed(f"{c.title} {c.text}") for c in chunks])
    return Retriever(chunks, vectors, fake_embed)
