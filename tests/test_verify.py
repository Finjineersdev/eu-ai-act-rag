from types import SimpleNamespace as NS

import pytest

from actrag.verify import NOT_GROUNDED, verify


@pytest.fixture
def docs(chunks):
    a = next(c for c in chunks if c.ref == "Article 6(1)")
    b = next(c for c in chunks if c.ref == "Recital 1")
    return [a, b]


def cite(i, quote):
    return NS(
        type="char_location",
        document_index=i,
        cited_text=quote,
        start_char_index=0,
        end_char_index=len(quote),
    )


def block(text, *citations):
    return NS(type="text", text=text, citations=list(citations) or None)


def test_valid_citation_kept(docs):
    quote = docs[0].text[:60]
    r = verify([block("High-risk if both conditions hold.", cite(0, quote))], docs)
    assert r.status == "answered"
    assert r.citations[0].ref == "Article 6(1)"
    assert r.citations[0].url.endswith("#art_6")
    assert "High-risk" in r.answer


def test_fabricated_quote_drops_block(docs):
    good = block("Real.", cite(0, docs[0].text[:40]))
    bad = block("Invented claim.", cite(0, "AI systems are always high-risk"))
    r = verify([good, bad], docs)
    assert "Invented" not in r.answer
    assert r.removed_blocks == 1


def test_out_of_range_document_index(docs):
    r = verify([block("x", cite(99, "anything"))], docs)
    assert r.status == "not_grounded"


def test_whitespace_drift_passes(docs):
    words = docs[0].text.split()[:8]
    drifted = " ".join(words[:4]) + "\n " + " ".join(words[4:])
    r = verify([block("ok", cite(0, drifted))], docs)
    assert r.valid_citations == 1


def test_uncited_text_kept_without_marker(docs):
    intro = block(
        "The retrieved text doesn't settle every part of this question, because the "
        "paragraph that would decide it was not among the excerpts, but here is what "
        "the excerpts do say about it:"
    )
    cited = block("Cited.", cite(0, docs[0].text[:40]))
    r = verify([intro, cited], docs)
    assert r.answer.startswith("The retrieved text")
    assert r.removed_blocks == 0


def test_removed_claim_leaves_no_fragment(docs):
    lead = block("Banned: ")
    bad = block("all AI", cite(0, "not in the source"))
    tail = block(". Also cited.", cite(0, docs[0].text[:30]))
    r = verify([lead, bad, tail], docs)
    assert "all AI" not in r.answer and r.removed_blocks == 1


def test_nothing_valid_is_not_grounded(docs):
    r = verify([block("Unsupported claim.", cite(0, "not in the text at all"))], docs)
    assert r.status == "not_grounded"
    assert r.answer == NOT_GROUNDED
    assert r.citations == []


def test_raw_counts(docs):
    r = verify([block("a", cite(0, docs[0].text[:30]), cite(1, "fake quote here"))], docs)
    assert (r.raw_citations, r.valid_citations) == (2, 1)


def test_duplicate_citations_deduped(docs):
    q = docs[0].text[:30]
    r = verify([block("a", cite(0, q)), block("b", cite(0, q))], docs)
    assert len(r.citations) == 1


def test_model_written_markers_are_stripped(docs):
    forged = block("Uncited claim [1].")
    real = block("Real.", cite(0, docs[0].text[:40]))
    r = verify([forged, real], docs)
    assert "claim [1]" not in r.answer and "Uncited claim." in r.answer
    assert r.answer.count("[1]") == 1
