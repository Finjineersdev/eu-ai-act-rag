"""Run the evals and write a Markdown report to evals/results/.

uv run python evals/run.py --retrieval   # free, no API key, runs in CI
uv run python evals/run.py --answers     # calls Claude; needs ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from actrag.ingest import DATA
from actrag.retrieve import Retriever

ROOT = Path(__file__).resolve().parent
CASES = [json.loads(line) for line in (ROOT / "golden.jsonl").read_text().splitlines()]
META = json.loads((DATA / "corpus_meta.json").read_text())


def header(title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        (
            f"Run on {date.today().isoformat()} · corpus sha256 `{META['sha256'][:12]}` · "
            f"{len(CASES)} golden cases ([golden.jsonl](../golden.jsonl))"
        ),
        "",
    ]


def recall(found: list[str], expected: list[str]) -> float:
    return sum(a in found for a in expected) / len(expected)


def run_retrieval(r: Retriever) -> list[str]:
    by_kind = defaultdict(lambda: {"r5": [], "r10": []})
    for c in CASES:
        if not c["expected"]:
            continue
        anchors = [x.anchor for x in r.search(c["question"], k=10)]
        for kind in (c["kind"], "all"):
            by_kind[kind]["r5"].append(recall(anchors[:5], c["expected"]))
            by_kind[kind]["r10"].append(recall(anchors, c["expected"]))
    lines = header("Retrieval eval") + [
        "Share of expected Articles/Annexes found among the top-k retrieved chunks.",
        "",
        "| Questions | n | recall@5 | recall@10 |",
        "|---|---|---|---|",
    ]
    for kind in ("lookup", "paraphrase", "multi", "pushback", "all"):
        v = by_kind[kind]
        n = len(v["r5"])
        lines.append(f"| {kind} | {n} | {sum(v['r5']) / n:.0%} | {sum(v['r10']) / n:.0%} |")
    return lines


def run_answers(r: Retriever) -> list[str]:
    import anthropic

    from actrag.answer import MODEL, answer

    client = anthropic.Anthropic()
    raw = valid = removed = blocks_total = 0
    grounded, refused_ok, held, rows = [], [], [], []

    def anchors_of(res):
        return {c.url.rsplit("#", 1)[1] for c in res.citations}

    for c in CASES:
        t0 = time.time()
        if c["kind"] == "pushback":
            history, res = [], None
            for q in [c["question"], *c["pushback"]]:
                res = answer(q, history, r, client)
                history = (
                    history
                    + [{"role": "user", "content": q}, {"role": "assistant", "content": res.answer}]
                )[-4:]
            got = anchors_of(res)
            ok = c["expected"][0] in got and c["wrong"] not in got
            held.append(ok)
        else:
            res = answer(c["question"], [], r, client)
            if c["kind"] == "out_of_scope":
                ok = res.status == "not_in_act"
                refused_ok.append(ok)
            else:
                ok = bool(anchors_of(res) & set(c["expected"]))
                grounded.append(ok)
        raw += res.raw_citations
        valid += res.valid_citations
        removed += res.removed_blocks
        blocks_total += 1
        rows.append(
            f"| {c['id']} | {c['kind']} | {res.status} | {'✓' if ok else '✗'} | "
            f"{time.time() - t0:.1f}s |"
        )

    def pct(xs):
        return f"{sum(xs) / len(xs):.0%} ({sum(xs)}/{len(xs)})"

    return header(f"Answer eval · {MODEL}") + [
        "| Metric | Result |",
        "|---|---|",
        f"| Citation validity (model's raw citations that matched the source) | "
        f"{valid / raw:.1%} ({valid}/{raw}) |"
        if raw
        else "| Citation validity | no citations |",
        f"| Grounded (expected Article among verified citations) | {pct(grounded)} |",
        f"| Out-of-scope questions refused | {pct(refused_ok)} |",
        f"| Held correct answer under 2 rounds of pushback | {pct(held)} |",
        f"| Claims removed by the checker | {removed} across {blocks_total} cases |",
        "",
        "| Case | Kind | Status | Pass | Time |",
        "|---|---|---|---|---|",
        *rows,
    ]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--retrieval", action="store_true")
    p.add_argument("--answers", action="store_true")
    args = p.parse_args()
    r = Retriever.load()
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    for flag, fn, name in (
        (args.retrieval, run_retrieval, "retrieval.md"),
        (args.answers, run_answers, "answers.md"),
    ):
        if flag:
            text = "\n".join(fn(r)) + "\n"
            (out / name).write_text(text)
            print(text)


if __name__ == "__main__":
    main()
