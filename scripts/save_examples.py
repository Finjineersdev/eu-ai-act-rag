"""Answer the page's example questions once with the full model and save them for the demo.

set -a; . ./.env; set +a; uv run python scripts/save_examples.py      # calls Claude
"""

import json
from dataclasses import asdict
from datetime import date

import anthropic

from actrag.answer import answer
from actrag.api import CORPUS_DATE, DISCLAIMER, STATIC
from actrag.demo import FULL_MODEL
from actrag.retrieve import Retriever

QUESTIONS = [
    "Which AI practices are prohibited?",
    "When is an AI system high-risk?",
    "What must deployers of high-risk AI systems do?",
    "What are the fines for breaking the rules?",
]


def main() -> None:
    retriever, client, out = Retriever.load(), anthropic.Anthropic(), []
    for q in QUESTIONS:
        r = answer(q, [], retriever, client, model=FULL_MODEL)
        assert r.status == "answered" and r.citations, (q, r.status)
        out.append(
            {
                "question": q,
                "saved_on": date.today().isoformat(),
                "status": r.status,
                "answer": r.answer,
                "citations": [asdict(c) for c in r.citations],
                "model": FULL_MODEL,
                "corpus_date": CORPUS_DATE,
                "disclaimer": DISCLAIMER,
            }
        )
        print(f"{q}: {len(r.citations)} citations", flush=True)
    (STATIC / "examples.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
