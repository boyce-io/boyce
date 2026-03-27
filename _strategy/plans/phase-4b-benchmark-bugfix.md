# Plan: Phase 4b — Benchmark Bug Fix Pass

**Status:** NOT STARTED
**Created:** 2026-03-27
**Last updated:** 2026-03-27
**Depends on:** Phase 4 benchmark results (complete)

---

## Context

The Phase 4 preliminary benchmark (12 Pagila queries, gpt-4o-mini, Mode A vs Mode B)
produced a **2.33 vs 3.5 average score** — Boyce underperforms direct LLM on a clean
schema. Root cause analysis traced every failure to specific bugs in the planner
validation logic, the SQL builder, and the StructuredFilter schema. These are
catalogued below.

The benchmark DID prove the Q08 null trap value (Boyce: 1,000 rows via LEFT JOIN;
direct LLM: 0 rows via INNER JOIN on a 100%-NULL column). That finding stands
regardless of these bugs. But the aggregate numbers are unusable for distribution
copy until these bugs are fixed.

---

## Classified Bug List

### BUG-A: Metric validation silently drops valid metrics (CRITICAL)

**Affected queries:** Q04, Q05, Q06, Q07, Q10, Q11 (6 of 12)
**Observed:** SQL has no aggregate functions. `SELECT col FROM table` instead of
`SELECT COUNT(col) FROM table GROUP BY ...`.

**Root cause chain:**
1. The LLM returns a metric like `{"name": "total_revenue", "aggregation_type": "SUM"}`
2. Planner validation (`planner.py:270-289`) tries to match `metric_name` to a field:
   - `field.name == metric_name` — fails when name is "total_revenue" but field is "amount"
   - MEASURE type check — only fires when `metric_name in ("count", "sum", "avg")` AND
     field is typed as MEASURE. Most Pagila fields are DIMENSION/ID/FOREIGN_KEY.
3. Metric is silently dropped. `validated_metrics` is empty.
4. `aggregation_required = len(validated_metrics) > 0` → False
5. Builder renders raw column references instead of `SUM(col)`.

**Fix:** Decouple metric validation from name matching. The metric's `field_id` or
the LLM's `fields` list already identify the target column. If a valid aggregation_type
is present and the referenced field resolves, validate the metric. Use the field_id (not
the metric_name) as the column reference; use metric_name as the alias only.

**Verification:** Q04, Q05, Q06, Q07, Q10, Q11 should produce aggregate SQL after fix.

---

### BUG-B: No ORDER BY / LIMIT support in builder (HIGH)

**Affected queries:** Q03, Q05, Q06 (and any "Top N" query)
**Observed:** Even when aggregation works, all rows are returned — no sorting, no limit.

**Root cause:** `SQLBuilder.build_final_sql()` has no ORDER BY or LIMIT rendering.
The StructuredFilter schema has no `order_by` or `limit` fields. The planner prompt
asks for metrics/dimensions but never "Top N" hints.

**Fix (3 layers):**
1. **StructuredFilter schema:** Add `order_by: [{field_id, direction}]` and `limit: int`
   to the expected shape.
2. **Builder:** Add `_build_order_by_clause()` and LIMIT rendering in `build_final_sql()`.
3. **Planner:** Update LLM prompt to output `order_by` and `limit`. Update planner
   output construction to pass them through.

**Verification:** Q03, Q05, Q06 should produce `ORDER BY ... LIMIT 5` after fix.

---

### BUG-C: Entity over-scoping causes join resolution failures (MEDIUM)

**Affected queries:** Q02
**Observed:** "No join path found from entity:rental to entity:payment". The query
("Top 5 customers by total number of rentals") needs customer + rental, not payment.

**Root cause:** The LLM includes extraneous entities. The planner passes all LLM-selected
entities to `join_path` without checking reachability. The join resolver raises
`ValueError` instead of degrading gracefully.

**Fix (defense in depth):**
1. **Planner:** After entity validation, test join reachability. Drop unreachable
   entities with a warning rather than including them.
2. **Join resolver:** Catch `ValueError` from `find_join_path` and skip unreachable
   entities instead of aborting.

**Verification:** Q02 should produce SQL joining customer + rental only, with COUNT.

---

### BUG-D: grouping_fields uses bare names, not field_ids (LOW)

**Affected queries:** None (Pagila names are unambiguous) — latent bug.
**Root cause:** `planner.py:356` outputs `[d["field_name"] for d in validated_dimensions]`.
The builder's `_resolve_grouping_field()` does a best-effort name lookup that will
break on same-named columns across entities.

**Fix:** Pass field_ids. Low priority — Pagila won't trigger this.

---

### BUG-E: Harness scoring — LEFT OUTER JOIN not detected (LOW)

**Affected queries:** Q08 (harness only, not Boyce)
**Root cause:** `"LEFT JOIN" in sql_upper` doesn't match `"LEFT OUTER JOIN"`.
**Fix:** `re.search(r"LEFT\s+(OUTER\s+)?JOIN", sql, re.IGNORECASE)`.

---

### BUG-F: No expression column support (concatenation, arithmetic) (LOW)

**Affected queries:** Q09
**Root cause:** Builder can only render column references and aggregate functions,
not computed expressions like `first_name || ' ' || last_name`.
**Fix:** Future feature — not blocking for this pass.

---

### BUG-G: Field resolution prefers primary FK over secondary FK (MEDIUM)

**Affected queries:** Q08
**Root cause:** Planner resolved "original language" to `film.language_id`
(primary language) instead of `film.original_language_id`. The field matching
heuristic doesn't rank keyword overlap.
**Fix:** Score field candidates by keyword overlap with the NL query. "original
language" should score higher for `original_language_id` than `language_id`.

---

## Execution Plan

### Step 1: Diagnostic Capture (Sonnet · medium)
Instrument the planner to log the raw LLM response AND the validated StructuredFilter
for each of the 12 benchmark queries. Write results to
`_strategy/research/benchmark-structured-filters.json`. This confirms our bug
hypotheses and may reveal additional issues.

**Acceptance:** 12 StructuredFilter dicts captured. Every failure explained.

### Step 2: Fix BUG-A — Metric Validation (Sonnet · high)
Rewrite the metric validation loop in `planner.py:270-289`. The new logic:
- If `metric.aggregation_type` is valid AND the field resolves, validate.
- Match field by: exact field_id → LLM fields list → field_name in entity → MEASURE fallback.
- metric_name becomes the alias, not the validation key.

Also fix `_build_select_clause` to fall back correctly when metrics are present but
grouping_fields are empty (e.g., Q11: `SUM(amount)` with no GROUP BY should produce
a scalar aggregate).

**Tests:** Add unit tests covering:
- Metric with invented name + valid field → validates
- Metric with "count"/"sum" keywords → validates via MEASURE path
- Empty dimensions + metrics → aggregation_required True, no GROUP BY, scalar aggregate
- All 12 benchmark NL prompts → expected aggregation presence (integration-level)

**Acceptance:** Q04, Q05, Q06, Q07, Q10, Q11 produce aggregate SQL. Existing 448 tests pass.

### Step 3: Fix BUG-B — ORDER BY / LIMIT (Sonnet · high)
Three files changed:
- `planner.py`: Update LLM prompt to request `order_by` and `limit`. Update output
  construction.
- `kernel.py`: Pass `order_by` and `limit` through to builder.
- `sql/builder.py`: Add `_build_order_by_clause()`, add LIMIT rendering.

**Tests:** Add unit tests:
- ORDER BY single field ascending/descending
- ORDER BY aggregate expression (e.g., `ORDER BY COUNT(*) DESC`)
- LIMIT N
- Combination: GROUP BY + ORDER BY + LIMIT
- No ORDER BY/LIMIT when not specified (regression)

**Acceptance:** Q03, Q05, Q06 produce `ORDER BY ... DESC LIMIT 5`. Existing tests pass.

### Step 4: Fix BUG-C — Entity Over-Scoping (Sonnet · medium)
- Planner: Before building `join_path`, test each entity pair for reachability via
  `snapshot.find_join_path()`. Drop unreachable entities with logging.
- Join resolver: Catch ValueError from unreachable pairs and continue with the
  reachable subset.

**Tests:** Add test: planner given entities [A, B, C] where B→C has no join path →
StructuredFilter contains only [A, B], SQL generates.

**Acceptance:** Q02 produces valid SQL. No more "No join path found" crashes.

### Step 5: Fix BUG-E — Harness Scoring (Sonnet · low)
One-line regex fix in `run_benchmark.py`.

**Acceptance:** Q08 Mode A correctly reports `null_trap_detected: true`.

### Step 6: Fix BUG-G — Field Resolution (Sonnet · medium)
Score field candidates by keyword overlap with the NL query. When the query says
"original language", `original_language_id` should outscore `language_id`.

**Tests:** Add test: NL "original language" resolves to `original_language_id`, not
`language_id`.

**Acceptance:** Q08 joins on `original_language_id`.

### Step 7: Re-run Benchmark (Sonnet · low)
Execute `run_benchmark.py` with the same model (gpt-4o-mini) and Pagila.
Write updated results to `_strategy/research/preliminary-benchmark.md`.

**Acceptance criteria:**
- Mode A average score >= 3.0/4 (up from 2.33)
- Mode A row count accuracy >= 75% (up from 33%)
- Mode A join correctness >= 83% (up from 67%)
- Q08 null_trap_detected = true
- Q09 dialect_safe = true
- All 12 queries produce valid SQL (no crashes)

---

## Deferred (not in this pass)

- BUG-D (grouping_fields field_ids) — latent, Pagila-safe
- BUG-F (expression columns) — feature gap, not a bug

---

## Model Assignments

| Step | Model | Effort | Reason |
|------|-------|--------|--------|
| 1. Diagnostic capture | Sonnet | medium | Mechanical instrumentation |
| 2. BUG-A metric fix | Sonnet | high | Logic rewrite in validation |
| 3. BUG-B ORDER BY/LIMIT | Sonnet | high | New feature across 3 files |
| 4. BUG-C entity scoping | Sonnet | medium | Defensive logic |
| 5. BUG-E harness fix | Sonnet | low | One-line regex |
| 6. BUG-G field resolution | Sonnet | medium | Heuristic scoring |
| 7. Re-run benchmark | Sonnet | low | Mechanical execution |
