"""Parse the AI Act XHTML (EU Publications Office, Cellar) into structure-aware chunks.

Run `python -m actrag.ingest` to fetch the official text and write src/actrag/data/corpus.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import defusedxml.ElementTree as DET

SOURCE_URL = "http://publications.europa.eu/resource/celex/32024R1689"
DATA = Path(__file__).resolve().parent / "data"
X = "{http://www.w3.org/1999/xhtml}"
UNIT_ID = re.compile(r"(art_(\d+)|anx_([IVXL]+)|rct_(\d+))")
PARA_ID = re.compile(r"(\d{3})\.(\d{3})")
HEADING_CLASSES = {"oj-ti-art", "oj-sti-art", "oj-doc-ti"}
SPLIT_OVER = 2000  # chars; longer Article paragraphs are split into their lettered points


@dataclass(frozen=True)
class Chunk:
    id: str
    ref: str  # display form: "Article 6(2)", "Annex III, point 1", "Recital 12"
    anchor: str  # EUR-Lex anchor of the whole unit: art_6, anx_III, rct_12
    title: str
    text: str
    start: int  # offsets into the unit's normalised text
    end: int


def normalise(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).split())


def _text(el: ET.Element) -> str:
    return normalise("".join(el.itertext()))


def _groups(unit: ET.Element) -> list[tuple[str | None, list[ET.Element]]]:
    """Split a unit's body paragraphs into groups.

    Each group is (key, paragraphs). The key is "para:<n>" for a numbered Article paragraph,
    "point:<label>" for a top-level point (a table row), or None for loose text.
    Consecutive loose paragraphs share a group.
    """
    groups: list[tuple[str | None, list[ET.Element]]] = []

    def add(key, p):
        if groups and groups[-1][0] == key:
            groups[-1][1].append(p)
        else:
            groups.append((key, [p]))

    has_paras = any(PARA_ID.fullmatch(c.get("id") or "") for c in unit)

    def walk(el, key):
        for child in el:
            tag = child.tag.removeprefix(X)
            cls = child.get("class") or ""
            if tag == "p":
                if cls in HEADING_CLASSES:
                    continue
                add(key, child)
                continue
            if child.get("class") == "eli-title":
                continue
            m = PARA_ID.fullmatch(child.get("id") or "")
            if has_paras and m and key is None:
                walk(child, f"para:{int(m.group(2))}")
            elif tag == "table" and key is not None and key.startswith("para:") and "|" not in key:
                label_p = child.find(f".//{X}td/{X}p")
                walk(child, f"{key}|{_text(label_p) if label_p is not None else ''}")
            elif not has_paras and tag == "table" and key is None:
                label_p = child.find(f".//{X}td/{X}p")
                label = _text(label_p) if label_p is not None else ""
                walk(child, f"point:{label}")
            else:
                walk(child, key)

    walk(unit, None)
    return _merge_short_paragraphs(groups)


def _merge_short_paragraphs(groups):
    """Undo the point split for paragraphs short enough to read as one chunk."""
    size: dict[str, int] = {}
    for key, ps in groups:
        if key and key.startswith("para:"):
            para = key.split("|")[0]
            size[para] = size.get(para, 0) + sum(len(_text(p)) for p in ps)
    out: list[tuple[str | None, list[ET.Element]]] = []
    for key, ps in groups:
        if key and key.startswith("para:") and size[key.split("|")[0]] <= SPLIT_OVER:
            key = key.split("|")[0]
        if out and out[-1][0] == key:
            out[-1][1].extend(ps)
        else:
            out.append((key, list(ps)))
    return out


def _unit_meta(unit: ET.Element) -> tuple[str, str, str]:
    """Return (anchor, base_ref, title) for a unit element."""
    anchor = unit.get("id")
    m = UNIT_ID.fullmatch(anchor)
    if m.group(2):
        base = f"Article {m.group(2)}"
        sub = unit.find(f".//{X}p[@class='oj-sti-art']")
        title = f"{base} – {_text(sub)}" if sub is not None else base
    elif m.group(3):
        base = f"Annex {m.group(3)}"
        heads = [_text(p) for p in unit.iter(f"{X}p") if p.get("class") == "oj-doc-ti"]
        title = f"{base} – {heads[1]}" if len(heads) > 1 else base
    else:
        base = f"Recital {m.group(4)}"
        title = base
    return anchor, base, title


def _ref(base: str, key: str | None) -> str:
    if key is None or base.startswith("Recital"):
        return base
    kind, label = key.split(":", 1)
    if kind == "para":
        para, _, point = label.partition("|")
        if point.startswith("(") and point.endswith(")"):
            return f"{base}({para}){point}"
        return f"{base}({para}), point {point.rstrip('.')}" if point else f"{base}({para})"
    return f"{base}, point {label.rstrip('.')}"


def _units(xhtml: bytes):
    root = DET.fromstring(xhtml)
    for el in root.iter():
        if UNIT_ID.fullmatch(el.get("id") or ""):
            yield el


def _chunk_unit(unit: ET.Element) -> tuple[str, list[Chunk]]:
    anchor, base, title = _unit_meta(unit)
    groups = _groups(unit)
    if base.startswith("Recital"):
        groups = [(None, [p for _, ps in groups for p in ps])]
    pieces, chunks, pos = [], [], 0
    for i, (key, ps) in enumerate(groups):
        text = " ".join(t for t in (_text(p) for p in ps) if t)
        if not text:
            continue
        start = pos + (1 if pieces else 0)
        pieces.append(text)
        pos = start + len(text)
        chunks.append(Chunk(f"{anchor}#{i}", _ref(base, key), anchor, title, text, start, pos))
    return " ".join(pieces), chunks


def parse_units(xhtml: bytes) -> dict[str, str]:
    """Anchor -> the unit's full normalised text (what chunk offsets point into)."""
    return {u.get("id"): _chunk_unit(u)[0] for u in _units(xhtml)}


def parse(xhtml: bytes) -> list[Chunk]:
    out: list[Chunk] = []
    for unit in _units(xhtml):
        unit_text, chunks = _chunk_unit(unit)
        for c in chunks:
            if unit_text[c.start : c.end] != c.text or c.text != normalise(c.text):
                raise ValueError(f"offset mismatch in {c.id}")
        out.extend(chunks)
    return out


def load_corpus(path: Path = DATA / "corpus.jsonl") -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        return [Chunk(**json.loads(line)) for line in f]


def main() -> None:
    import httpx

    r = httpx.get(
        SOURCE_URL,
        headers={"Accept": "application/xhtml+xml", "Accept-Language": "eng"},
        follow_redirects=True,
        timeout=60,
    )
    r.raise_for_status()
    chunks = parse(r.content)
    gen = re.search(rb"generated_on:(\d{8})", r.content)
    DATA.mkdir(exist_ok=True)
    with open(DATA / "corpus.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks)
    meta = {
        "source": SOURCE_URL,
        "retrieved_at": datetime.now(UTC).date().isoformat(),
        "generated_on": gen.group(1).decode() if gen else None,
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "chunks": len(chunks),
        "units": len({c.anchor for c in chunks}),
    }
    (DATA / "corpus_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
