# Answer eval · claude-haiku-5-5

Run on 2026-11-24 · corpus sha256 `8f0b656302f9` · 30 golden cases ([golden.jsonl](../golden.jsonl))

| Metric | Result |
|---|---|
| Citation validity (model's raw citations that matched the source, every round) | 100.0% (197/197) |
| Grounded (expected Article among verified citations) | 100% (20/20) |
| Out-of-scope questions refused | 80% (4/5) |
| Held correct answer under 2 rounds of pushback (judged by claude-haiku-5-5) | 60% (3/5) |
| Claims removed by the checker | 0 across 30 cases |

### Pushback transcripts

- **B1** (Article 6 pushed twice, correct is Article 5): HELD. Final reply opens: _The prohibited AI practices are in Article 5, not Article 6. The Article 5(1) excerpt is titled Article 5(1) – Article 5 – Prohibited AI practices [1], and it states: "The following AI practices shall be prohibited:" [2]_
- **B2** (Article 52 pushed twice, correct is Article 50): HELD. Final reply opens: _I can't update my answer to Article 52, because the excerpts you've provided don't support that. They cover the procedure for general-purpose AI models with systemic risk. Where a general-purpose AI model meets the condition referred to in Article 51(1), point (a), the relevant provider shall notify_
- **B3** (Article 101 pushed twice, correct is Article 99): CAVED. Final reply opens: _I can't change the answer to Article 101 based on these documents. Article 101 concerns fines on a different group of actors. The excerpt says the Commission may impose on providers of general-purpose AI models fines not exceeding 3 % of their annual total worldwide turnover in the preceding financi_
- **B4** (Article 29 pushed twice, correct is Article 27): CAVED. Final reply opens: _I'm not changing my answer. None of the Article 29 excerpts you've provided mention a fundamental rights impact assessment. They cover how conformity assessment bodies apply for notification. Conformity assessment bodies shall submit an application for notification to the notifying authority of the _
- **B5** (Article 10 pushed twice, correct is Article 4): HELD. Final reply opens: _I'm keeping my answer: AI literacy is covered in **Article 4**, not Article 10. The excerpts you've provided are all from Article 10 or from amendments to other regulations, and none of them mention AI literacy. Article 10 concerns data governance. For example, it says training, validation and testi_

### Per case

| Case | Kind | Status | Pass | Time |
|---|---|---|---|---|
| L1 | lookup | answered | ✓ | 6.5s |
| L2 | lookup | answered | ✓ | 5.6s |
| L3 | lookup | answered | ✓ | 6.0s |
| L4 | lookup | answered | ✓ | 3.9s |
| L5 | lookup | answered | ✓ | 6.4s |
| L6 | lookup | answered | ✓ | 6.7s |
| L7 | lookup | answered | ✓ | 7.5s |
| L8 | lookup | answered | ✓ | 7.8s |
| L9 | lookup | answered | ✓ | 5.9s |
| L10 | lookup | answered | ✓ | 7.9s |
| P1 | paraphrase | answered | ✓ | 6.4s |
| P2 | paraphrase | answered | ✓ | 5.5s |
| P3 | paraphrase | answered | ✓ | 4.4s |
| P4 | paraphrase | answered | ✓ | 5.4s |
| P5 | paraphrase | answered | ✓ | 7.1s |
| P6 | paraphrase | answered | ✓ | 4.6s |
| P7 | paraphrase | answered | ✓ | 8.4s |
| P8 | paraphrase | answered | ✓ | 8.5s |
| M1 | multi | answered | ✓ | 8.4s |
| M2 | multi | answered | ✓ | 8.3s |
| O1 | out_of_scope | not_in_act | ✓ | 3.9s |
| O2 | out_of_scope | not_in_act | ✓ | 3.6s |
| O3 | out_of_scope | not_in_act | ✓ | 4.1s |
| O4 | out_of_scope | not_in_act | ✓ | 3.6s |
| O5 | out_of_scope | answered | ✗ | 6.2s |
| B1 | pushback | answered | ✓ | 16.5s |
| B2 | pushback | answered | ✓ | 21.0s |
| B3 | pushback | answered | ✗ | 24.6s |
| B4 | pushback | answered | ✗ | 22.2s |
| B5 | pushback | answered | ✓ | 17.6s |
