from pathlib import Path

from actrag.ingest import normalise, parse, parse_units

FIXTURE = (Path(__file__).parent / "fixtures" / "mini_act.xhtml").read_bytes()


def refs():
    return {c.ref for c in parse(FIXTURE)}


def test_article_paragraph_refs():
    assert {"Article 6(1)", "Article 6(2)"} <= refs()


def test_definitions_split_by_point():
    assert "Article 3, point (1)" in refs()


def test_annex_and_recital_refs():
    chunks = parse(FIXTURE)
    assert "Annex III, point 1" in refs()
    assert "Recital 1" in refs()
    anchors = {c.anchor for c in chunks}
    assert {"anx_III", "rct_1"} <= anchors


def test_offsets_are_exact():
    units = parse_units(FIXTURE)
    for c in parse(FIXTURE):
        assert units[c.anchor][c.start : c.end] == c.text
        assert c.text == normalise(c.text)
        assert c.text


def test_titles():
    c = next(c for c in parse(FIXTURE) if c.ref == "Article 6(1)")
    assert c.title == "Article 6 – Classification rules for high-risk AI systems"


def test_normalise():
    assert normalise("a  b\n c ") == "a b c"


def test_long_paragraph_split_into_points():
    assert {"Article 5(1)(a)", "Article 5(1)(f)"} <= refs()
    assert "Article 5(1)" in refs()  # the intro sentence stays its own chunk


def test_short_paragraph_not_split():
    assert not any(r.startswith("Article 6(1)(") for r in refs())


def test_annex_points_with_span_text_keep_their_text():
    xhtml = b"""<html xmlns="http://www.w3.org/1999/xhtml"><body><div id="anx_I">
    <p class="oj-doc-ti">ANNEX I</p><p class="oj-doc-ti">List of Union harmonisation legislation</p>
    <table><tbody><tr><td/><td><p class="oj-normal">1.</p></td>
    <td><span>Directive 2006/42/EC on machinery (<a href="x">OJ L 157</a>);</span></td>
    </tr></tbody></table></div></body></html>"""
    from actrag.ingest import parse

    (chunk,) = parse(xhtml)
    assert chunk.ref == "Annex I, point 1"
    assert chunk.text == "1. Directive 2006/42/EC on machinery (OJ L 157);"
