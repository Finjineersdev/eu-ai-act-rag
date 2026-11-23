# EU AI Act RAG: design

Status: draft for approval · 2026-11-23 · Author: Haseeb Hanif

## Intent

A public portfolio repo that proves one thing to a hiring manager in two minutes:
**this engineer builds LLM systems that fail safely in production.**

The problem is real. Regulation (EU) 2024/1689 (the "AI Act") applies to any company
that puts AI systems on the EU market, including US, UK and remote-first companies.
Product and legal teams keep asking questions like "does our feature count as high-risk?",
"what do we owe as a deployer?" or "when does this apply?", and the answers are spread
across 113 Articles, 13 Annexes and 180 Recitals. Generic chatbots answer confidently and
cite Articles that don't say what they claim.

This service answers questions **only from the official text**. Every claim carries a
citation that the code has checked exists in the source. When the text doesn't support
an answer, the service says so instead of guessing.

It is a research aid, not legal advice. The README and every API response say so.

## Goals

1. `POST /ask` returns an answer in which every claim is tied to an Article, Annex or Recital
   reference plus a quote, each with a link to EUR-Lex.
2. **Every quote is checked in code** against the stored source text before it is returned.
   Unchecked quotes are dropped. If nothing checks out, the response is
   `status: "not_grounded"` with a fixed "the Act's text I retrieved doesn't answer this" message.
3. It handles the production failure modes Haseeb writes about:
   - **truncation**: `stop_reason == "max_tokens"` is never returned as a normal answer.
   - **chunk offsets**: at ingestion, every chunk satisfies `source[start:end] == chunk.text`.
     A violation fails the build.
   - **pushback**: the model changes its answer only when the user points to text, not
     just because the user insists. This is measured by evals.
   - **out-of-scope**: questions not about the Act (e.g. GDPR fines, US law) are refused.
4. **Evals** that run in CI:
   - retrieval recall@k against a hand-labelled golden set. No API key needed, runs on every push.
   - answer evals (citation validity, refusal, pushback). These need an API key, run on manual
     dispatch, and their results are committed to `evals/results/`.
5. A one-command run: `docker compose up` → open `http://localhost:8000` and see a small web page
   for asking questions.
6. A README a recruiter can scan: what it does, a demo GIF, an architecture diagram (Mermaid),
   the eval results table, and how to run it.

## Non-goals (v1)

- The agent that interviews users and classifies their risk tier. That is approach B and a
  separate, second repo.
- Tracking amendments. The corpus is whatever text Cellar serves on the day of ingestion,
  recorded with its date and hash (see "Corpus version" below), and the UI shows that date.
- Other laws (GDPR, DSA…), other languages, logins, multi-user, chat memory beyond one
  follow-up turn.
- A public hosted demo. API costs and abuse make it a v2 decision.
- A React front end. A single static HTML page served by FastAPI is enough for the demo GIF.

## Anti-goals (a failure even if it works)

- Any answer that shows a citation the code didn't check.
- A README that oversells: claims like "legal-grade" or "100% accurate", or numbers that weren't measured.
- A repo that needs three API keys and a GPU to try. One key (Anthropic) is the maximum.
- Over-engineering a recruiter has to wade through: no plugin system, no provider factory,
  no abstraction with only one implementation.

## Constraints

- **Source:** `http://publications.europa.eu/resource/celex/32024R1689` with
  `Accept: application/xhtml+xml`, `Accept-Language: eng` (Cellar). EUR-Lex itself sits
  behind a bot challenge. The XHTML has stable ids: `art_N`, `anx_N`, `rct_N`.
  EU legal texts may be reused with acknowledgement (Commission Decision 2011/833/EU).
  The parsed corpus is committed to the repo, so tests and Docker builds never need network access.
- **Python 3.12**, `uv`, `ruff`, `pytest`. Docker isn't installed on the dev machine, so the Docker
  build is checked in CI (GitHub Actions builds the image and hits `/health`).
- **One secret:** `ANTHROPIC_API_KEY`. The model is configurable through `MODEL`, default `claude-opus-5-5` at `effort: medium`, with server-side refusal fallbacks (`fallbacks: "default"`), so a policy decline is retried on another model, not surfaced as an outage.

## Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| **A** | RAG plus a citation checker | Smallest build that still shows production judgement | **Chosen** |
| B | Agent that interviews the user and classifies risk tier | More visible agent work, roughly 2× the failure surface and build time | Second repo |
| C | A now, B added to the same repo later | One repo grows two concerns | Rejected: two finished repos look better than one big one |

Haseeb picked A and asked for B to be the second public repo.

## How it works

```
ingest (offline, committed output)
  Cellar XHTML ──parse──▶ units: Article / paragraph, Annex section, Recital
                └─chunk──▶ chunks {id, unit_ref, start, end, text, url}
                           assert source[start:end] == text   (build fails otherwise)
                └─embed──▶ data/index.npz  (local embedding model, no API key)

query
  question ─▶ hybrid retrieval: BM25 ∪ embeddings, fused with RRF, top-k chunks
           ─▶ Claude Messages API with the chunks as citable documents
              (Anthropic Citations: cited_text spans come back on each claim)
           ─▶ check: stop_reason == "end_turn"? else → truncated error
           ─▶ check: every cited_text ⊂ its chunk text (whitespace-normalised)?
                     drop anything that fails; no checked citations left → status: not_grounded
           ─▶ response {status, answer, citations[{ref, quote, url}], model, corpus_date, disclaimer}
```

### Decisions (Claude's calls, marked so they can be overridden)

- **Chunking follows the law's structure, not a fixed character count.** One chunk per Article
  paragraph, Annex point or Recital. Units over ~1,500 tokens are split at sub-points (a), (b)…
  This way every chunk has a precise reference ("Article 6(2)"), which is what a citation needs.
- **No vector database.** About 2–3k chunks fit in memory. The index is a NumPy array in a
  `.npz` file plus `rank_bm25`. pgvector would add a container and a migration for nothing
  measurable. *Ceiling:* fine up to roughly 100k chunks; move to pgvector when there's a
  second corpus or concurrent writes.
- **Embeddings run locally with `fastembed`** (ONNX, small model, no torch). This keeps it to a
  single API key and makes the retrieval evals free to run in CI.
- **Hybrid retrieval.** Questions often name an Article directly ("what does Article 50 require?").
  BM25 catches that, embeddings catch paraphrases, and Reciprocal Rank Fusion merges the two.
  There is also a direct shortcut: a regex for `Article \d+` / `Annex [IVX]+` pins that unit into the results.
- **Generation uses the Anthropic SDK directly, with Citations.** Each retrieved chunk is sent as its
  own plain-text `document` block with `citations: {enabled: true}` and the chunk's reference
  (e.g. "Article 6(2)") as the title. The model returns `char_location` citations (`document_index`,
  `start_char_index`, `end_char_index`, `cited_text`), so the checker gets something concrete to verify,
  not prose to parse.
- **No LangChain in this repo** (changed after approval, flagged for Haseeb). Hybrid retrieval is about
  30 lines of `rank_bm25` + NumPy + RRF, and wrapping the model call would hide the `stop_reason` and the
  citation blocks this project exists to show. LangChain/LangGraph will appear in repo B (the agent),
  where they earn their place.
- **The pushback rule** goes in the system prompt: "Change your answer only if the user points to
  text in the provided documents; otherwise restate your answer and its citations."
  The evals measure whether the model follows it. The prompt alone doesn't count as proof.
- **The UI** is one `index.html`: a question box, an answer with numbered citations, and a
  link to EUR-Lex (everything shown has passed the check). No build step.

### API

- `POST /ask` `{question: str, history?: [{role, content}] (max 4 turns)}` → `200 {status, answer, citations[{ref, quote, url}], model, corpus_date, disclaimer}`
  - `status` is one of `answered`, `not_in_act` (out of scope, refused by the model), or `not_grounded` (no citation survived the check)
  - `502 {error: "truncated"}` when `stop_reason` is `max_tokens`
  - `422` for an empty question or one over 2,000 characters
- `GET /health` → `{status, corpus_date, chunks}`

### Evals

- `evals/golden.jsonl`: about 30 hand-written questions. Each has the Articles/Annexes the
  answer must come from, checked by reading the Act. Mix: direct lookups, paraphrases,
  multi-article questions, 5 out-of-scope questions, 5 pushback cases (correct answer → user
  disputes → user disputes again).
- Metrics: retrieval recall@5 and @10; citation validity rate (checked citations / citations
  returned); groundedness (the expected Article appears among the checked citations);
  refusal accuracy on out-of-scope questions; hold rate under pushback.
- `make eval` writes `evals/results/<date>.md`, and the README table is copied from it.
  Only measured numbers go in the README.

### Repo layout

```
src/actrag/  ingest.py  index.py  retrieve.py  answer.py  verify.py  api.py  static/index.html
data/        corpus.jsonl  index.npz
evals/       golden.jsonl  run.py  results/
tests/       test_ingest.py (offsets)  test_verify.py  test_api.py (model mocked)
docs/        design.md  demo.gif
Dockerfile  docker-compose.yml  .github/workflows/ci.yml  pyproject.toml  README.md  LICENSE (MIT)
```

### Rules settled after review (Claude's calls)

- **Failed citations.** The model's answer comes back as text blocks, each optionally carrying citations.
  If any citation on a block fails the check, it is removed. If *all* of a block's citations fail,
  the whole block (the claim) is removed. Blocks with no citations are kept and shown without a
  citation number (changed after the first live run: removing long uncited text cut off honest
  framing such as "the retrieved text doesn't settle this" and left broken sentences). Everything that is returned
  has been checked, so the response has no `verified` flag. If nothing cited survives, the status is `not_grounded`.
- **Citation validity rate** is measured on the model's raw output, *before* anything is removed
  (checked citations / all citations the model produced), so it measures the model, not the filter.
  A second metric, removed-claim rate, shows how often the filter had to act.
- **Pushback evals** call `answer()` directly with the full 3-turn history. The API's `history`
  takes up to 4 turns, so the same flow works there too. A case counts as **held** when the final
  reply still commits to the correct Article. *Changed after the first eval run:* the original
  deterministic rule ("doesn't cite the wrongly pushed unit") scored 0/5 because the model cites
  that unit to explain why it isn't the answer. Holding is now graded by claude-haiku-5-5 against a
  fixed one-word rubric (HELD/CAVED), and the opening of each final reply is published in the
  results so the grading can be checked by eye.
- **Out-of-scope.** The model decides, guided by the system prompt, and signals it with a
  `not_in_act` tool call, which maps to `status: not_in_act`. **Where the line falls:** questions about
  what the AI Act says, including where it refers to the GDPR or other laws (e.g. Article 10
  data governance), are answered from the Act's text. Questions that need another law's own text
  (e.g. "when is a GDPR DPIA required?") are refused.
- **Corpus version.** Accept what Cellar serves, and record the retrieval date, the document's
  generation date and the SHA-256 in `data/corpus_meta.json`. The UI, `/health` and the README show
  those values, not a promised 12 July 2024 text. If Cellar's text changes, re-ingesting shows up
  as a diff in `corpus.jsonl`, and the golden set is checked again.

## Left to the builder

- The exact embedding model (pick a small English model fastembed supports, and record its name and size in the README).
- The top-k value and RRF constant (tune against recall@k, and record the choice).
- Wording of the system prompt and the refusal text.
- Recording the demo GIF. This needs a real API key. Haseeb's key is used locally and never committed.
