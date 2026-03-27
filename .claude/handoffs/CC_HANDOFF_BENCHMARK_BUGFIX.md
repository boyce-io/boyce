# Handoff: Benchmark Bug Fix Pass

**From:** CC (Sonnet) — Phase 4 benchmark execution + root cause analysis
**To:** Opus planning session
**Date:** 2026-03-27
**Purpose:** Review classified bugs, decide scope, produce execution plan for CC to build all fixes in one pass

---

## What Happened

Phase 4 preliminary benchmark ran 12 ground-truth queries against Pagila (gpt-4o-mini).
**Boyce scored 2.33/4 vs direct LLM at 3.5/4.** Root cause analysis traced every
failure to specific bugs in the planner validation, SQL builder, and StructuredFilter
schema.

One finding IS usable for distribution copy: Q08 null trap (Boyce: 1,000 rows via
LEFT JOIN; direct LLM: 0 rows via INNER JOIN on 100%-NULL column).

The rest of the numbers are unusable until the bugs are fixed.

---

## Classified Bugs (7 total)

### CRITICAL

**BUG-A: Metric validation silently drops valid metrics**
- 6/12 queries affected (Q04, Q05, Q06, Q07, Q10, Q11)
- Planner validation at `planner.py:270-289` requires `metric_name == field.name`
  OR (`metric_name in ("count","sum","avg")` AND field is MEASURE type)
- When LLM names a metric "total_revenue" but the column is "amount", validation fails
- `validated_metrics` goes empty → `aggregation_required = False` → no aggregates
- SQL becomes `SELECT col FROM table` instead of `SELECT SUM(col) FROM table GROUP BY`

### HIGH

**BUG-B: No ORDER BY / LIMIT support in builder**
- 3/12 queries affected (Q03, Q05, Q06)
- `SQLBuilder.build_final_sql()` has zero ORDER BY or LIMIT code
- StructuredFilter schema has no `order_by` or `limit` fields
- All "Top N" queries return full result sets
- Fix spans 3 files: planner prompt + output, kernel passthrough, builder rendering

### MEDIUM

**BUG-C: Entity over-scoping causes join resolution failures**
- 1/12 queries affected (Q02)
- LLM includes extraneous entities; join resolver throws ValueError
- Q02 "Top 5 customers by rentals" — LLM added "payment" entity; no join path exists
- Should degrade gracefully (drop unreachable entity) not crash

**BUG-G: Field resolution prefers primary FK over secondary FK**
- 1/12 queries affected (Q08)
- "Original language" resolved to `language_id` instead of `original_language_id`
- Field matching has no keyword overlap scoring
- Produces semantically wrong query (primary language vs original language)

### LOW

**BUG-D: grouping_fields uses bare column names, not field_ids**
- Latent — Pagila names are unambiguous so it doesn't trigger
- Will break on schemas with same-named columns across entities
- `planner.py:356`: `[d["field_name"] for d in validated_dimensions]`

**BUG-E: Harness scoring — LEFT OUTER JOIN not detected**
- Benchmark harness only, not Boyce itself
- `"LEFT JOIN" in sql_upper` doesn't match `"LEFT OUTER JOIN"`
- Q08 incorrectly reports `null_trap_detected: false`

**BUG-F: No expression column support (concatenation, arithmetic)**
- Q09: Boyce returns `SELECT first_name, last_name` instead of `first_name || ' ' || last_name`
- Builder can only render column references and aggregate functions
- This is a feature gap — StructuredFilter has no concept of computed expressions

---

## Per-Query Benchmark Results

| Q | Category | Boyce Score | Direct Score | Boyce SQL Summary | Bugs Hit |
|---|----------|-------------|--------------|-------------------|----------|
| Q01 | single agg | 4/4 | 4/4 | Correct GROUP BY rating | None |
| Q02 | multi join | 0/4 | 3/4 | CRASH: no join path | C |
| Q03 | complex join | 2/4 | 4/4 | Used view, no LIMIT | B |
| Q04 | single agg | 3/4 | 4/4 | No COUNT DISTINCT, no GROUP BY | A |
| Q05 | multi join | 2/4 | 4/4 | No COUNT, no GROUP BY, no LIMIT | A, B |
| Q06 | complex join | 2/4 | 4/4 | Correct 4-table join, no COUNT/GROUP BY/LIMIT | A, B |
| Q07 | temporal agg | 2/4 | 1/4 | Collapsed to single table, no AVG | A |
| Q08 | null trap | 3/4 | 2/4 | LEFT JOIN (good), wrong FK (language_id) | G, E |
| Q09 | dialect | 3/4 | 4/4 | Raw columns, no concatenation | F |
| Q10 | filter agg | 2/4 | 4/4 | IS NULL filter works, no COUNT | A |
| Q11 | simple agg | 2/4 | 4/4 | No SUM, returned all rows | A |
| Q12 | complex filter | 3/4 | 4/4 | Used customer_list view, correct count | None |

---

## Key Source Files (read these for context)

### Planner (where BUG-A, C, D, G live)
- `boyce/src/boyce/planner/planner.py` — full file, 363 lines
  - Lines 68-106: `plan_query()` signature and docstring
  - Lines 127-158: Entity scoring + context building
  - Lines 163-185: LLM prompt (the instructions the model follows)
  - Lines 242-320: Validation loop (entities → fields → metrics → dimensions → filters)
  - Lines 270-289: **Metric validation — BUG-A root cause**
  - Lines 344-363: StructuredFilter assembly (grain_context, join_path)

### Kernel (passthrough — BUG-B touches this)
- `boyce/src/boyce/kernel.py` — 100 lines total
  - Simple passthrough: extracts concept_map, assembles planner_output dict, calls builder

### SQL Builder (where BUG-B, D, F live)
- `boyce/src/boyce/sql/builder.py` — 568 lines
  - Lines 160-231: `build_final_sql()` — main assembly (SELECT, FROM/JOIN, WHERE, GROUP BY)
  - Lines 313-398: `_build_select_clause()` — metrics rendering, aggregation_required gate
  - Lines 543-567: `_build_group_by_clause()` — grouping_fields resolution
  - **No ORDER BY or LIMIT methods exist anywhere**

### Join Resolver (where BUG-C manifests)
- `boyce/src/boyce/sql/join_resolver.py`
  - Line 152-154: Hard ValueError on unreachable entity pairs

### Benchmark Harness (BUG-E)
- `boyce/tests/benchmark/run_benchmark.py` — scoring logic
- `boyce/tests/benchmark/queries.json` — 12 ground-truth queries

### Benchmark Results
- `_strategy/research/preliminary-benchmark.json` — raw per-query data with actual SQL
- `_strategy/research/preliminary-benchmark.md` — markdown summary table

### Bug Fix Plan (CC's initial proposal)
- `_strategy/plans/phase-4b-benchmark-bugfix.md` — classified bugs + 7-step plan
  - Written by Sonnet; Opus should review, expand, and potentially restructure

### StructuredFilter Contract (reference)
- `CLAUDE.md` — architecture section documents the expected StructuredFilter shape
- `kernel.py` docstring (lines 1-42) — the shape the kernel expects

### Type System
- `boyce/src/boyce/types.py` — SemanticSnapshot, Entity, FieldDef, JoinDef, FieldType

---

## What Opus Should Decide

1. **Scope:** Fix all 7 bugs in one pass, or defer BUG-F (expression columns) as a
   feature? BUG-F requires adding a new concept (computed expressions) to the
   StructuredFilter schema — it's the biggest change.

2. **Diagnostic first?** CC proposed a diagnostic capture step (instrument planner to
   dump raw StructuredFilter for all 12 queries). Opus can decide if this is worth the
   time or if the root causes are sufficiently clear from code reading.

3. **Additional bugs?** Are there failure modes CC missed? The planner prompt, validation
   loop, and builder assembly are all exposed above. Opus should scan for:
   - HAVING clause support (GROUP BY exists but HAVING doesn't)
   - DISTINCT support (Q04 needs COUNT DISTINCT — does the builder handle it?)
   - Subquery support
   - Alias collision in multi-table queries
   - The planner's entity scoring heuristic (line 131-138) — is it adequate?

4. **Test strategy:** Unit tests per bug, or a broader refactor of the test suite to
   include StructuredFilter → SQL golden tests?

5. **StructuredFilter schema evolution:** BUG-B adds `order_by` + `limit`. BUG-F would
   add `computed_expressions`. BUG-D changes grouping_fields format. Should these be
   bundled into a schema version bump?

---

## Current Project State

- **Phase 4:** Benchmark complete, results captured, bugs classified
- **Git:** Clean on main, all work pushed (commit fdbb21b)
- **Tests:** 448 passed, 6 skipped (11s, no DB)
- **Benchmark dir:** `boyce/tests/benchmark/` (queries.json + run_benchmark.py)
- **ROADMAP.md:** Phase 4 status = "not started" (needs update to reflect benchmark
  completion + bug discovery)
