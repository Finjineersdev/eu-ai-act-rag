# EU AI Act, cited: design

Current as of v1.3.0. The README covers what the service does and how to run it; this document
records how it is built and why, including what changed after measuring.

## Problem

Regulation (EU) 2024/1689 (the AI Act) applies to anyone who puts AI systems on the EU market. Teams
keep asking "is our feature high-risk?", "what do we owe as a deployer?", "when does this apply?",
and the answers are spread across 113 Articles, 13 Annexes and 180 Recitals. General chatbots
answer fluently and cite Articles that don't say what they claim. In a legal context a wrong
citation is worse than no answer.

The service answers only from the official text, and never shows a citation the code hasn't
checked. When the retrieved text doesn't support an answer, it says so.

## Goals and non-goals

Goals:

- `POST /ask` returns an answer whose cited claims each carry a reference (Article, Annex point or
  Recital), the exact quote, and a EUR-Lex link, all checked in code.
- Production failure modes are handled, not hoped away: truncated replies, refusals, questions
  about other laws, users pushing back on a correct answer, an unreliable corpus build.
- Measured behaviour: retrieval recall in CI on every push, answer evals on demand, numbers in the
  README copied from the reports.
- One command to run (`docker compose up`), one secret (`ANTHROPIC_API_KEY`).
- A public demo whose cost is bounded.

Non-goals: other laws or languages; tracking amendments (the corpus is a recorded version);
accounts or server-side chat history; a JavaScript build step.

## Pipeline

```
ingest (offline; output committed)
  Cellar XHTML ─parse─▶ one chunk per Article paragraph, Annex point or Recital
                        paragraphs over 2,000 characters split into their lettered points
               ─check─▶ each chunk's text is, in order, its unit's text read straight from the XML
                        the download matches the SHA-256 recorded last time (--update to accept a new one)
               ─embed─▶ index.npz (BAAI/bge-small-en-v1.5 via fastembed, local, 384-dim)

query
  question ─▶ rewrite into the Act's vocabulary (Claude Haiku; used for search only)
           ─▶ hybrid search: BM25 + embeddings, Reciprocal Rank Fusion (k=60), top 8
              · an Article or Annex named in the question is pinned (up to 4 units)
              · at most 2 Recitals and 3 chunks per unit, so Articles aren't crowded out
           ─▶ Claude with each chunk as its own citable document (Anthropic Citations)
           ─▶ guards: max_tokens → 502 truncated; refusal → 502 refused; not_in_act tool → not_in_act
           ─▶ verify every citation (below) → answered, or not_grounded
```

## Decisions

- **Chunks follow the law's structure**, not a character count, so every citation has an exact
  reference ("Article 5(1)(f)", "Annex III, point 4"). 306 units become 1,016 chunks.
- **No vector database.** The index is a 1.4 MB NumPy file loaded at startup. A database would add a
  container and migrations for no measured gain. Ceiling: about 100k chunks, or a second corpus with
  concurrent writes, before pgvector earns its place.
- **Local embeddings** keep the project to one API key and make the retrieval eval free in CI. A
  larger embedding model was tried and gave no gain.
- **Query rewrite.** Users say "employers" and "banned"; the Act says "workplace" and "prohibited".
  With the rewrite, "Can employers use emotion recognition on their staff?" moved Article 5(1)(f) from
  90th to 2nd. If the rewrite call fails, search uses the question as asked.
- **The Anthropic SDK directly, no framework.** The guards need `stop_reason` and the raw citation
  blocks; a wrapper would hide exactly what this project is about.
- **Models.** `claude-opus-5-5` at effort `medium` by default (`MODEL` overrides it), with
  server-side fallback so a policy decline is retried on another model. Haiku 5.5 has no server-side
  fallback, so Haiku requests are sent without it.

## Citation rules

- A citation is valid only if its quote, whitespace-normalised, appears in the chunk it cites and
  sits at the character positions the API reports. This proves the quote is real and correctly
  placed. Whether the claim follows from it remains the model's judgement.
- A text block whose citations all fail is removed. Uncited text is kept but never numbered, so it
  is never presented as cited; removing it cut off honest framing such as "the retrieved text
  doesn't settle this".
- Only the checker adds `[n]` markers; markers the model writes, and markers in earlier turns sent
  back as history, are stripped.
- Nothing valid left → `not_grounded` with a fixed message.
- The eval's citation validity is measured on the model's raw output, before anything is removed.

## Scope and pushback

- Questions about what the AI Act says, including where it refers to the GDPR or other laws, are
  answered from its text. Questions that need another law's own text are refused through a
  `not_in_act` tool call.
- The system prompt says to change an answer only if the user points to text in the documents. The
  eval measures whether the model follows it, with two rounds of pushback per case. The first
  scoring rule ("doesn't cite the wrongly pushed unit") scored correct answers as failures, because
  the model cites that unit to explain why it isn't the answer; Haiku now grades HELD or CAVED
  against a fixed rubric, and each reply's opening is published so the grade can be checked.

## Public demo

Switched on by `DEMO=1`; a local run is unchanged.

- Example questions return saved Opus answers (`static/examples.json`, regenerated with
  `scripts/save_examples.py`) with no API call.
- Typed questions run on Haiku 5.5, limited per visitor (5 an hour) and in total (100 an hour) by
  an in-memory sliding window. The limiter is thread-safe and single-process.
- The visitor's address comes from a header the host's proxy sets and overwrites
  (`CLIENT_IP_HEADER`; on Render, Cloudflare's `CF-Connecting-IP`), or otherwise the entry
  `PROXY_HOPS` from the right of `X-Forwarded-For`. Entries further left can be faked by the visitor.
  On Render the right-most entries are Render's and Cloudflare's own, which is why the header is used.
- A visitor may send their own key in `X-Anthropic-Key` to use Opus. It is used for that request
  only, under a looser per-visitor limit, and never logged, stored or echoed; the client made for it
  is closed after the request. Errors on it map to `401 bad_key`.
- When the owner's key reaches its Console spend limit (a 400 "You have reached your specified…", a
  429 with `enforced_spend_limit_reached`, or a 402), the response is `503 paused` and the page
  says the examples still work. The owner's client retries once, not twice.
- A failed call to Anthropic logs its error type and status, and whose key it was, never the key.

## Security

- Every reply carries a Content-Security-Policy that allows only the page's own inline script (by
  hash), no framing, no external origins; plus `X-Content-Type-Options: nosniff` and
  `Referrer-Policy: no-referrer`. The page renders model output with `textContent` only.
- Request bodies over 256 KB, or without a length, are refused before parsing. Questions are capped
  at 2,000 characters, history at 4 turns; earlier answers are accepted up to 20,000 characters and
  clipped to 8,000 before the model sees them.
- The history is client-held (the server keeps no state), so a caller can edit it. It can't make
  the checker accept a citation, but it can steer the model's wording.
- The XHTML is parsed with `defusedxml`. The container runs as a non-root user with the embedding
  model baked in and `HF_HUB_OFFLINE=1`; CI checks it starts with no network.
- CI actions and base images are pinned by SHA and digest, with Dependabot to update them, and
  workflows default to read-only tokens. Release images are pushed with the workflow's own token.

## Evals

- `evals/golden.jsonl`: 30 hand-labelled questions (direct lookups, plain-language paraphrases,
  multi-article questions, 5 out of scope, 5 two-round pushback cases), each with the Articles or
  Annexes the answer must come from, checked against the text.
- Retrieval recall@5 and @10 run on every push (no API key). Answer evals (citation validity,
  expected Article cited, out-of-scope refusal, pushback) run on demand per model:
  `evals/results/answers.md` for Opus, `answers-<model>.md` for others.
- Long paragraphs split into lettered points raised plain-language recall@10 from 69% to 94%.

## Layout

```
src/actrag/  ingest.py  index.py  retrieve.py  answer.py  verify.py  api.py  demo.py  web.py
             data/ (corpus.jsonl, corpus_meta.json, index.npz)  static/ (index.html, examples.json)
evals/       golden.jsonl  run.py  results/
scripts/     save_examples.py
tests/       one file per module; the model is faked, so tests need no network or key
```

## Corpus version

The service uses whatever text Cellar serves on the day of ingestion and records its retrieval
date, generation date and SHA-256 in `data/corpus_meta.json`; the page, `/health` and every answer
show that date. Cellar answers https requests by redirecting to plain http, so the recorded hash is
the integrity check: a re-ingest that gets different bytes stops unless `--update` is passed.
