# Retrieval eval

Run on 2026-11-23 · corpus sha256 `8f0b656302f9` · 30 golden cases ([golden.jsonl](../golden.jsonl))

Share of expected Articles/Annexes found among the top-k retrieved chunks.

| Questions | n | recall@5 | recall@10 |
|---|---|---|---|
| lookup | 10 | 100% | 100% |
| paraphrase | 8 | 69% | 94% |
| multi | 2 | 100% | 100% |
| pushback | 5 | 100% | 100% |
| all | 25 | 90% | 98% |
