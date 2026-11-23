<div align="center">

# EU AI Act, cited

**Ask the EU AI Act a question. Get an answer whose every quote has been checked against the official text.**

[![CI](https://github.com/Finjineersdev/eu-ai-act-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/Finjineersdev/eu-ai-act-rag/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Opus_5.5-D97757)
[![MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

<p align="center"><img src="docs/demo.gif" alt="Asking whether employers can use emotion recognition on staff: the answer cites Article 5(1)(f), Recital 44 and Article 3(39), each marked as found in the source" width="820"></p>

## Why

The EU AI Act applies to anyone who puts AI systems on the EU market, including US, UK and
remote-first companies. Product and legal teams keep asking the same questions:
*is our feature high-risk? what do we owe as a deployer? when does this apply?* The answers are
spread across 113 Articles, 13 Annexes and 180 Recitals.

Generic chatbots answer confidently and cite Articles that don't say what they claim. In a legal
context, a made-up citation is worse than no answer. This service is built around one rule:
**it never shows a citation it hasn't verified.**

## How it works

```mermaid
flowchart TB
    subgraph ingest["Ingest · offline, committed to the repo"]
        direction LR
        A["Official text<br/>EU Publications Office"]:::data --> B["Split by legal structure<br/>Article · point · Annex · Recital"] --> C[("1,016 chunks<br/>+ local embeddings")]:::data
    end

    Q(["Question"]) --> W["Rewrite into the Act's wording<br/><i>Claude Haiku, search only</i>"]:::llm
    W --> R["Hybrid search<br/>BM25 + embeddings, RRF<br/>pins any Article you name"]
    ingest -. loaded at startup .-> R
    R --> L["Claude Opus<br/>each chunk is a citable document"]:::llm
    L --> G{{"Guards"}}
    G --> V{{"Is every quote in its chunk?"}}
    G -- "cut off · declined · other law" --> S["502 truncated · 502 refused<br/>not_in_act"]:::stop
    V -- "verified" --> OK(["Answer + citations<br/>linked to EUR-Lex"]):::ok
    V -- "nothing verified" --> N["not_grounded"]:::stop

    classDef data fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef llm fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
```

<sub>Blue: data · Purple: Claude calls · Red: what it returns instead of guessing · Green: the only path to an answer.</sub>

1. **Ingest** parses the official text into chunks that follow the law's own structure, so every
   citation is precise ("Article 5(1)(f)", "Annex III, point 4"). Each chunk's offsets are checked
   against its source: `source[start:end] == chunk`, or the build fails.
2. **Query rewrite.** People say "employers" and "banned"; the Act says "workplace" and "prohibited".
   Claude Haiku rewrites the question in the Act's vocabulary, and the rewrite is used only to
   search. Without it, "Can employers use emotion recognition on their staff?" ranked Article 5(1)(f)
   90th; with it, 2nd. If the rewrite call fails, search uses the original question.
3. **Retrieval** combines keyword search (BM25, good at "Article 50") with local embeddings (good at
   paraphrases), merged with Reciprocal Rank Fusion. Recitals are capped so the Articles that
   carry obligations aren't crowded out.
4. **Generation** sends each chunk to Claude as a separate citable document (Anthropic Citations).
5. **Verification** checks every returned quote against the chunk it cites. A claim whose quotes
   don't match is removed. If nothing survives, the answer says the text doesn't cover it.

## What it refuses to do

| Situation | Behaviour |
|---|---|
| A quote doesn't appear in the cited chunk | The claim is removed before the response leaves the server |
| The model writes its own `[n]` markers | Stripped; only the checker adds citation numbers. Uncited framing text is shown with no number |
| Nothing in the answer can be verified | `status: "not_grounded"` with a fixed message, no guessing |
| The question needs another law (GDPR rules, US law) | `status: "not_in_act"` |
| The reply hit `max_tokens` | HTTP 502 `truncated`, never a half answer |
| The model declines | Server-side fallback to another model; if all decline, HTTP 502 `refused` |
| The user insists on a wrong Article | The answer changes only if they point to text (measured below) |

## Evals

Measured on 30 golden cases with each model ([Opus report](evals/results/answers.md),
[Haiku report](evals/results/answers-claude-haiku-5-5.md)). The live demo runs Haiku for typed questions.

| Metric | Claude Opus 5.5 | Claude Haiku 5.5 |
|---|---|---|
| Citations the model produced that matched the source text (every round) | **100%** (281/281) | **100%** (197/197) |
| Answers citing the Article the question is about | **100%** (20/20) | **100%** (20/20) |
| Out-of-scope questions refused (GDPR rules, US law, tax) | **100%** (5/5) | 80% (4/5) |
| Held the correct Article through two rounds of user pushback | 80% (4/5) | 60% (3/5) |

Retrieval, without the query rewrite, runs on every push ([report](evals/results/retrieval.md)):

| Questions | recall@5 | recall@10 |
|---|---|---|
| Name an Article ("What does Article 50 require?") | 100% | 100% |
| Plain language ("Can employers use emotion recognition on staff?") | 69% | 94% |
| All 25 with an expected answer | 90% | 98% |

Recall counts whether the right Article or Annex is retrieved; the answer eval is where paragraph-level
precision shows. Pushback is graded by `claude-haiku-5-5` against a one-word rubric, and the opening
of every final reply is in the report so the grading can be checked by eye. Some replies the judge
marked as caved open by rejecting the wrong Article without restating the right one (B2 for Opus;
B3 and B4 for Haiku). Grades are published as the judge gave them.

Golden set: [`evals/golden.jsonl`](evals/golden.jsonl), 30 hand-labelled questions (direct lookups,
plain-language paraphrases, multi-article questions, out-of-scope questions, and two-round pushback
cases). Every expected Article was checked against the text. Retrieval evals run on every push in CI;
answer evals run on demand ([workflow](.github/workflows/evals.yml)).

## Live demo

<!-- LIVE_LINK -->

The public demo keeps the bill bounded:

- The example questions show **saved answers from Claude Opus 5.5** (labelled with their date). No API call.
- Questions you type run on **Claude Haiku 5.5**, up to 5 per visitor per hour and 100 per hour in total.
- Paste your own Anthropic key to run **Claude Opus 5.5**. It is sent with your requests straight to
  Anthropic and never stored or logged.
- If the owner's monthly spend limit is reached, the demo says it is paused and the examples keep working.

All of this is switched on by `DEMO=1`; a local run is unchanged.

## Run it

```bash
cp .env.example .env          # add your ANTHROPIC_API_KEY
docker compose up --build     # http://localhost:8000
```

Without Docker:

```bash
uv sync
uv run uvicorn actrag.api:app --reload
```

Run the tests and evals:

```bash
uv run pytest                              # 57 tests, no network or API key
uv run python evals/run.py --retrieval     # free
uv run python evals/run.py --answers       # calls Claude
```

Rebuild the corpus from the official source (optional; the parsed corpus is committed):

```bash
uv run python -m actrag.ingest && uv run python -m actrag.index
```

## API

```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "Does a customer-service chatbot have to say it is an AI?"}'
```

```json
{
  "status": "answered",
  "answer": "**Generally yes.** If the chatbot talks directly with customers, the AI Act requires that people be told they're dealing with an AI, unless that's already obvious. …",
  "citations": [
    {
      "ref": "Article 50(1)",
      "quote": "Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system, unless this is obvious from the point of view of a natural person who is reasonably well-informed, observant and circumspect, taking into account the circumstances and the context of use.",
      "url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng#art_50"
    },
    "…"
  ],
  "model": "claude-opus-5-5",
  "corpus_date": "2024-10-17",
  "disclaimer": "Research aid based on the text of Regulation (EU) 2024/1689. Not legal advice."
}
```

| Endpoint | |
|---|---|
| `POST /ask` | `{question, history?}`, optional header `X-Anthropic-Key` (history: up to 4 plain-text turns) → `{status, answer, citations[{ref, quote, url}], model, corpus_date, disclaimer}` |
| `GET /health` | `{status, corpus_date, chunks}` |
| `GET /config` | `{demo, model, byok}`: whether demo mode is on and which model typed questions use |
| `GET /examples` | the saved example answers (empty unless generated with `scripts/save_examples.py`) |
| `GET /` | the web page |

## Design decisions

Full design: [`docs/design.md`](docs/design.md). The short version:

- **No vector database.** About 1,000 chunks fit in memory; the index is a 1.4 MB NumPy file. A
  database would add a container and migrations for no measurable gain.
- **Local embeddings** (`BAAI/bge-small-en-v1.5` via fastembed, ONNX, no GPU). One API key is the
  only requirement, and the retrieval evals cost nothing to run in CI.
- **The Anthropic SDK directly, no framework.** The guards depend on `stop_reason` and the raw
  citation blocks; a wrapper would hide exactly what this project is about.
- **Chunks follow the law's structure**, not a fixed character count, so citations are exact.
- **What changed after measuring** is recorded in the design doc and the git history: a larger embedding
  model was tested and gave no gain; long paragraphs were split into lettered points (plain-language
  recall@10 69% → 94%); a too-strict pushback scoring rule was replaced after it marked correct answers
  as failures.

## Source and licence

Text: Regulation (EU) 2024/1689 (Artificial Intelligence Act), as served by the EU Publications
Office ([CELEX 32024R1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng)). The version used is
recorded in [`src/actrag/data/corpus_meta.json`](src/actrag/data/corpus_meta.json) (generation date and SHA-256) and shown
in the app. Amendments after that version are not included. EU legal texts are reused under
Commission Decision 2011/833/EU. Only the Official Journal text is authentic.

**This is a research aid, not legal advice.**

Code: [MIT](LICENSE) © Haseeb Hanif
