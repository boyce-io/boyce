# Agentic Ingestion Sprint — Plan

**Created:** 2026-03-28
**Phase:** Phase 5 (ROADMAP.md)
**Status:** Sprints 0, 1a, 2 COMPLETE. Sprint 3 HITL gate cleared, execution starting.
**Priority order:** Profiling > parsers (standing order, CM MASTER.md)

---

## Sprint Overview

The Phase 4 benchmark revealed the product gap: 10 parsers extract structural
info the LLM already gets from `information_schema`. The snapshot adds zero
knowledge over what the model already sees. The ingestion layer IS the product.

Sprint builds:
1. Haiku regression root cause (Sprint 0)
2. Schema extensions for profiling data (Sprint 1)
3. Live database profiling engine (Sprint 2)
4. Parser deepening for dbt/LookML/ORM semantic extraction (Sprint 3)
5. Optional host-LLM classification loop (Sprint 3)
6. Benchmark validation against dirty fixture (Sprint 4)

---

## Sprint 0 — Haiku Regression Root Cause — COMPLETE

**Status:** COMPLETE (2026-03-28). **Branch A confirmed.**
**Deliverable:** `_strategy/research/sprint0-haiku-diagnosis.md` + `sprint0-diagnosis.json`

**Finding:** Stripped StructuredFilter scored WORSE (2.50) than full (3.42),
not better. Join correctness identical (83%). Field selection improved when
stripped, proving Haiku understands the query but fails to categorize columns
into metrics/dimensions slots. Root cause: planner prompt, not abstraction.
Sprint continues as planned.

### Branch Criteria

Sprint 0 outputs one of two branches. The branch determination gates Sprint 3.

**Branch A — Fixable within existing architecture:** The Haiku regression is
caused by prompt formatting, validation attrition, entity selection errors, or
planner prompt verbosity. The StructuredFilter abstraction itself is not the
problem — the problem is how context is presented to the LLM or how the
planner's validation loop filters results. Fix is localized. Sprint continues
as planned. Sprint 3 may need adaptive context pruning for small models (show
less context, not more), but the architecture holds.

**Branch B — The StructuredFilter abstraction is the tax:** The act of forcing
the LLM to produce a structured JSON with entities, fields, metrics, dimensions,
filters, order_by, limit, and expressions is harder than just writing SQL. The
abstraction itself imposes cognitive load that degrades performance, and adding
more context to that structure will make it worse. If Branch B, the sprint
pauses after Sprint 2. Scope a StructuredFilter simplification pass — reduce
the cognitive load of the abstraction before enriching the snapshot that feeds
into it.

### Diagnostic Test

Run the Haiku benchmark with a stripped-down StructuredFilter — fewer fields,
no metrics/dimensions/expressions, just entities and basic filters. If Haiku's
score recovers toward vanilla (3.83), it's Branch B. If it doesn't recover,
it's Branch A.

---

## Sprint 1 — Schema Extensions — COMPLETE

**Status:** COMPLETE (2026-03-28).

**FieldDef additions:** `null_rate`, `distinct_count`, `sample_values`,
`business_description`, `business_rules`

**Entity additions:** `object_type`, `row_count`, `view_sql`, `view_lineage`

**JoinDef additions:** `join_confidence`, `orphan_rate`

**SemanticSnapshot addition:** `profiled_at` (ISO 8601 timestamp)

**Hash invariant:** All profiling fields excluded from `snapshot_id` hash via
`canonicalize_snapshot_for_hash()` in `validation.py` — both `build_snapshot()`
and `_compute_snapshot_hash()` call this function. 16 new tests. 481 total
tests pass.

---

## Sprint 2 — Live Database Profiling Engine — COMPLETE

**Status:** COMPLETE (2026-03-28).
**Deliverable:** `boyce/src/boyce/profiler.py` — `profile_snapshot(adapter, snapshot)`

**API:** Takes connected PostgresAdapter + SemanticSnapshot → new enriched
SemanticSnapshot. Sequential execution (asyncpg single-connection constraint).

**Signals profiled:**
- Row counts per entity (SELECT COUNT(*))
- NULL rates per column (COUNT(*) - COUNT(col)) / COUNT(*))
- Enum detection: columns with distinct_count ≤ 25 get sample_values populated
- Object type detection via information_schema.tables
- FK confidence + orphan_rate per join (LEFT JOIN match-rate query)

**Validation results against Pagila:**
- original_language_id null_rate = 1.0 ✓ (Opus smoke test passed)
- film.rating sample_values = ['G', 'NC-17', 'PG', 'PG-13', 'R'] ✓
- All Pagila FK joins: confidence=1.0, orphan_rate=0.0 ✓
- snapshot_id preserved across profile runs ✓

**Key design note:** Sequential execution required because asyncpg's single
connection does not support concurrent operations (`asyncio.gather` causes
"another operation is in progress"). Future pool-based adapter could enable
parallelism.

**Tests:** 32 tests (24 unit, 8 Pagila integration). 513 total pass.

---

## Sprint 3 — Host-LLM Classification Loop (enrich_snapshot)

**Status:** HITL gate cleared (2026-03-28). Execution starting.
**Deliverable:** New MCP tool `enrich_snapshot` + `enrichment.py` module.

### Scope

**Job 1 — Enum interpretation (PRIMARY):** Profiled sample_values → host LLM
interprets what they mean (e.g. `['A','C','S','P']` → Active, Cancelled,
Suspended, Pending). Stored in `FieldDef.business_description`.

**Job 2 — NULL interpretation (SECONDARY):** Majority-NULL columns → host LLM
infers whether deprecated, optional, or data quality issue. Readable bonus on
top of the already-critical `null_rate` signal.

**Job 3 — Cross-table disambiguation:** DEFERRED. FK health scoring already
measures actual match rates.

### Classification Trigger

Column enters classification payload if ANY of:
- `sample_values` is populated (distinct_count ≤ 25)
- `null_rate > 0.5` (majority-NULL column)

### Two-Round MCP Flow

**Round 1 — Request:** `enrich_snapshot(snapshot_name)` → generates per-entity
classification prompts from profiling data → returns `classification_needed:
true` with prompts for host LLM to run.

**Round 2 — Store:** `enrich_snapshot(snapshot_name, classifications={...})` →
stores `business_description` into snapshot FieldDef entries → persists.

If no classifiable columns → `classification_needed: false` (no Round 2).
If host LLM skips Round 2 → no harm, snapshot unchanged.
If malformed JSON → skip and log, no error surfaced.

### Prompt Template (per entity)

```
Table: {entity_name}
{entity_description if available}

The following columns have characteristics that benefit from interpretation.
For each column, provide a brief business description based on the column name,
data type, table context, and any sample values shown.

- {column_name} ({data_type}, {null_rate_pct}% null, {distinct_count} distinct values)
  Values: {sample_values}

Respond with JSON only:
{"columns": {"{column_name}": {"business_description": "...", "value_meanings": {...} or null}}}
```

**Response parsing:** `business_description` → `FieldDef.business_description`.
If `value_meanings` provided, format as readable string (e.g. "A=Active,
C=Cancelled") and append to business_description. No new schema fields.

### Hard Constraint: enrich_snapshot Is Optional

Product delivers full value with profiling data alone. Enrichment adds
human-readable descriptions. The planner can use raw `sample_values` without
knowing what they mean.

### What Sprint 3 Does NOT Include
- No planner prompt changes (that's Sprint 4 / benchmark validation)
- No cross-table disambiguation (Job 3, deferred)
- No retry logic (classification is best-effort)
- No new schema fields (uses Sprint 1a's existing `business_description`)

### Parser Deepening (Sprint 1b/c/d) — Parallel, Lower Priority

**Track A (dbt):** Extract descriptions, test assertions → business_description,
business_rules. Test against jaffle_shop.

**Track B (LookML):** Extract dimension descriptions, measure SQL, explore joins.
Test against thelook.

**Track C (ORMs):** Django help_text → business_description, choices →
sample_values. SQLAlchemy docstrings. Prisma `///` comments.

---

## Sprint 4 — Benchmark Validation

### Dirty Fixture Required

Sprint 4 cannot validate against Pagila alone. Pagila is a clean schema — NULL
rates near zero on almost every column, FK health is clean, enum values are
tidy, column names are unambiguous. The profiling engine will find almost
nothing wrong, and the benchmark will show no improvement.

The thesis is that Boyce's value emerges on messy real-world data. Sprint 4
must validate against a dirty fixture. Two approaches:

1. **Augment Pagila** (faster): inject 100% NULL columns, cryptic single-letter
   enum codes, ambiguous cross-table column names that look like joins but
   aren't, orphaned FK records, a high-NULL FK column beyond the existing
   original_language_id. Add 3-5 benchmark queries that specifically target
   scenarios where profiling data changes outcomes.
2. **Build a small dirty schema** (more honest): a 10-15 table schema designed
   to represent common warehouse pathologies.

Workstream CC chooses the approach. Either way, Sprint 4 includes fixture
creation time — it is not a 30-minute sprint.

### Done Condition (Directive #7 Gate)

Enriched SemanticSnapshots must demonstrably beat vanilla LLM SQL generation on
GPT-4o class models. Testing per Directive #7 (CM MASTER.md):
- Recommended tier: match or beat vanilla on every query category, advantage on 3+
- Budget tier: systematic regression is P1 bug, not ship blocker
- Median of 3 runs per model
- Dirty fixture included in benchmark

**Phase 6 (Distribution) unblocks only when this gate passes.**
