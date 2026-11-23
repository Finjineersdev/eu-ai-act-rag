def test_article_pin(retriever):
    assert retriever.search("What does Article 6 say?")[0].anchor == "art_6"


def test_annex_pin(retriever):
    assert retriever.search("Explain Annex III")[0].anchor == "anx_III"


def test_missing_article_does_not_crash(retriever):
    assert len(retriever.search("What does Article 140 say?")) <= 8


def test_keyword_hit(retriever):
    refs = [c.ref for c in retriever.search("subliminal techniques")]
    assert any(r.startswith("Article 5(1)") for r in refs)


def test_k_respected(retriever):
    assert len(retriever.search("high-risk", k=3)) == 3


def test_recitals_capped():
    import numpy as np

    from actrag.ingest import Chunk
    from actrag.retrieve import Retriever
    from tests.conftest import fake_embed

    cs = [
        Chunk(
            f"rct_{i}#0", f"Recital {i}", f"rct_{i}", f"Recital {i}", "market rules for AI", 0, 19
        )
        for i in range(6)
    ]
    cs.append(Chunk("art_9#0", "Article 9(1)", "art_9", "Article 9", "risk management", 0, 15))
    r = Retriever(cs, np.stack([fake_embed(c.text) for c in cs]), fake_embed)
    got = r.search("market rules for AI", k=5)
    assert sum(c.anchor.startswith("rct_") for c in got) <= 2
    assert any(c.anchor == "art_9" for c in got)


def test_unit_diversity(retriever):
    from collections import Counter

    got = retriever.search("prohibited AI practices", k=8)
    assert max(Counter(c.anchor for c in got).values()) <= 3
