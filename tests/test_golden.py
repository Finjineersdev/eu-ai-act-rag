import json
from collections import Counter
from pathlib import Path

from actrag.ingest import load_corpus

ROOT = Path(__file__).resolve().parents[1]
CASES = [json.loads(line) for line in (ROOT / "evals" / "golden.jsonl").read_text().splitlines()]


def test_every_anchor_exists():
    anchors = {c.anchor for c in load_corpus()}
    for case in CASES:
        for a in case["expected"] + ([case["wrong"]] if "wrong" in case else []):
            assert a in anchors, (case["id"], a)


def test_kind_counts():
    assert Counter(c["kind"] for c in CASES) == {
        "lookup": 10,
        "paraphrase": 8,
        "multi": 2,
        "out_of_scope": 5,
        "pushback": 5,
    }


def test_pushback_cases_complete():
    for c in CASES:
        if c["kind"] == "pushback":
            assert len(c["pushback"]) == 2 and c["wrong"] not in c["expected"]


def test_ids_unique():
    assert len({c["id"] for c in CASES}) == len(CASES)
