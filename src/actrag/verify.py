"""Keep only what the source text supports.

Rules (docs/design.md, "Rules settled after review"):
- a citation is valid only if its quote appears in the cited chunk (whitespace-normalised);
- a text block whose citations all fail is removed;
- an uncited block of 25+ words is removed (short connective text is kept);
- no valid citation left -> status "not_grounded" with a fixed message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from actrag.ingest import Chunk, normalise

NOT_GROUNDED = (
    "The parts of the AI Act I retrieved don't answer this. "
    "Try rephrasing, or name the Article you're asking about."
)
EURLEX = "https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng#{anchor}"
MAX_UNCITED_WORDS = 25


@dataclass(frozen=True)
class Citation:
    ref: str
    quote: str
    url: str


@dataclass
class Result:
    status: Literal["answered", "not_in_act", "not_grounded"]
    answer: str
    citations: list[Citation] = field(default_factory=list)
    raw_citations: int = 0
    valid_citations: int = 0
    removed_blocks: int = 0


def _valid(c, docs: list[Chunk]) -> bool:
    i = getattr(c, "document_index", -1)
    return (
        getattr(c, "type", None) == "char_location"
        and isinstance(i, int)
        and 0 <= i < len(docs)
        and bool(normalise(c.cited_text or ""))
        and normalise(c.cited_text) in docs[i].text
    )


def verify(content: list, docs: list[Chunk]) -> Result:
    parts: list[str] = []
    cites: dict[tuple[str, str], Citation] = {}
    raw = valid = removed = 0
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        cs = block.citations or []
        good = [c for c in cs if _valid(c, docs)]
        raw += len(cs)
        valid += len(good)
        if cs and not good:
            removed += 1
            continue
        if not cs and len(block.text.split()) >= MAX_UNCITED_WORDS:
            removed += 1
            continue
        marks = []
        for c in good:
            d = docs[c.document_index]
            quote = normalise(c.cited_text)
            key = (d.ref, quote)
            if key not in cites:
                cites[key] = Citation(d.ref, quote, EURLEX.format(anchor=d.anchor))
            marks.append(list(cites).index(key) + 1)
        parts.append(block.text + "".join(f" [{n}]" for n in dict.fromkeys(marks)))
    if not cites:
        return Result("not_grounded", NOT_GROUNDED, [], raw, valid, removed)
    return Result("answered", "".join(parts).strip(), list(cites.values()), raw, valid, removed)
