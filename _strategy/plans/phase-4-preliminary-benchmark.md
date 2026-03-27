# Plan: Phase 4 — Preliminary Benchmark (Pagila)
**Status:** NOT STARTED
**Created:** 2026-03-27
**Model:** Opus · high (design), Sonnet · medium (harness build)
**Estimated effort:** ~1-2 days

---

## Goal

Produce concrete "With Boyce / Without Boyce" numbers against Pagila (Tier 1)
for use in distribution copy. This is a preliminary benchmark — the full
benchmark (Phase 10) runs against Tier 2 messy warehouse later.

---

## What This Proves (Pagila Limitations)

Pagila is clean — 29 tables, well-normalized, minimal NULLs outside
`film.original_language_id`. The benchmark will NOT demonstrate:
- NULL trap detection on pervasive NULL columns (Pagila is too clean)
- Schema ambiguity resolution (Pagila names are unambiguous)

It WILL demonstrate:
- Query accuracy (correct tables, joins, columns)
- Join correctness (Dijkstra resolution vs model-guessed joins)
- Dialect safety (Redshift lint catches)
- EXPLAIN pre-flight (all queries verified before return)
- Determinism (same query → same SQL, every time)

---

## Design

### Ground-Truth Query Set (10-15 queries)

Define queries with known-correct SQL and expected results. Categories:
1. Single-entity aggregation (COUNT, SUM, AVG)
2. Multi-entity join (2-3 tables)
3. Complex join (4+ hops)
4. Filter with equality (WHERE status = 'active')
5. Temporal filter (last 12 months)
6. NULL-sensitive query (original_language_id)
7. Dialect-sensitive query (CONCAT vs ||)

Each query: NL prompt, expected SQL pattern, expected row count or shape.

### Benchmark Harness

Script at `boyce/tests/benchmark/run_benchmark.py`:
- Input: query set JSON
- Mode A: "With Boyce" — prompt → ask_boyce → query_database
- Mode B: "Without Boyce" — prompt → raw SQL (model writes directly)
- Output: accuracy score, safety score, per-query results JSON

### Metrics

| Metric | Definition |
|---|---|
| Query accuracy | Correct results vs ground truth |
| Join correctness | Used correct join path |
| NULL safety | Warned about NULL-sensitive columns |
| Dialect safety | No Redshift-incompatible SQL generated |
| EXPLAIN verified | All queries passed EXPLAIN pre-flight |
| Determinism | Same prompt → same SQL across runs |

### Platforms

Preliminary: Claude Code + Cursor (already tested).
Full benchmark (Phase 10): add Codex.

---

## Acceptance Criteria

- [ ] 10-15 ground-truth queries defined with expected results
- [ ] Benchmark harness runs Mode A and Mode B
- [ ] At least one concrete comparison number ready for distribution copy
- [ ] Results written to `_strategy/research/preliminary-benchmark.md`
