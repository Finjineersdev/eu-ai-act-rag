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
