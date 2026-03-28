# Boyce Preliminary Benchmark — Pagila (Tier 1)

**Run:** 2026-03-28 00:08 UTC  
**Model:** openai/gpt-4o-mini  
**Queries:** 12  
**Database:** Pagila (PostgreSQL sample — 29 tables, ~1,000 films, ~600 customers)

---

## Summary

| Metric | With Boyce | Without Boyce |
|---|---|---|
| Row count accuracy | 100% | 83% |
| Top result accuracy | 75% | 75% |
| Join correctness | 75% | 100% |
| EXPLAIN verified | 100% | 92% |
| Average score (0–4) | 3.5 | 3.5 |

---

## Per-Query Results

| ID | Category | With Boyce | Without Boyce | Notes |
|---|---|---|---|---|
| Q01 | single_entity_aggregation | 4/4 | 4/4 | — |
| Q02 | multi_entity_join | 3/4 | 3/4 | — |
| Q03 | complex_join | 3/4 | 4/4 | — |
| Q04 | single_entity_aggregation | 4/4 | 4/4 | — |
| Q05 | multi_entity_join | 3/4 | 4/4 | — |
| Q06 | complex_join | 4/4 | 4/4 | — |
| Q07 | temporal_aggregation | 3/4 | 1/4 | B-err: EXPLAIN failed: column i.rental_duration does not  |
| Q08 | null_trap | 2/4 | 2/4 | Boyce: INNER JOIN (drops rows); Direct: INNER JOIN (drops rows) |
| Q09 | dialect_safety | 4/4 | 4/4 | Boyce: uses ||; Direct: used CONCAT() |
| Q10 | filter_aggregation | 4/4 | 4/4 | — |
| Q11 | simple_aggregation | 4/4 | 4/4 | — |
| Q12 | complex_join_with_filter | 4/4 | 4/4 | — |

---

## What Pagila Tests (and What It Doesn't)

**Demonstrates:**
- Query accuracy (correct tables, joins, columns)
- Join correctness (Dijkstra path resolution vs model-guessed joins)
- Dialect safety (Redshift lint — `||` vs `CONCAT()`)
- EXPLAIN pre-flight (all Boyce queries verified before return)
- Determinism (same prompt → same SQL)

**Does NOT demonstrate (Pagila is too clean):**
- NULL trap detection on pervasive NULLs (Pagila has minimal NULLs outside `original_language_id`)
- Schema ambiguity resolution (Pagila table names are unambiguous)
- Cross-schema join resolution

The full benchmark (Phase 10) runs against a Tier 2 messy warehouse where these failure modes are common.
