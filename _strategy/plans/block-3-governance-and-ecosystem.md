# Plan: Block 3 — Data Quality, Agentic Ingestion & Protocol v0.2
**Status:** Pending
**Created:** 2026-02-28
**Updated:** 2026-03-21
**Timeline:** Days 26-35 after name is locked
**Depends on:** Block 2 (Protocol & Parsers) — spec published, parsers operational

## Goal
Data quality becomes a first-class protocol feature. Live warehouse ingestion works on
real-world messy schemas without requiring API keys. Drift detection operational. Policy
stubs in the schema prevent future breaking changes. The protocol self-describes data
trustworthiness — this is the competitive wedge against dbt MCP.

"dbt tells agents what to query. We tell agents whether the answer will be trustworthy."

## Prerequisites
- Block 2 complete: SemanticSnapshot spec published, 10+ parsers, scan CLI
- Real-world deployment providing feedback on gaps
- Null Trap essay published and generating organic traffic

---

## Implementation Steps

### Step 0: Host-LLM Agentic Ingestion (CEO Directive, 2026-03-21)

**Hard requirement:** Full data warehouse ingestion MUST run on the user's host LLM
(the agent that called Boyce), not on a BYOK API key. A junior data analyst's agent
installs Boyce, connects to their warehouse, and the agent does the semantic
classification. No API key prompt. No credentials dialog. No bounce.

**The problem:** `_build_snapshot_from_live_db()` currently does mechanical type
classification — PKs → ID, timestamps → TIMESTAMP, numerics → MEASURE, everything
else → DIMENSION. This works on Pagila (15 clean tables). On a real warehouse
(200+ tables, views, materialized views, naming chaos, no FK constraints):
- `stg_orders_legacy` vs `fact_orders` vs `orders_v2` — which is canonical?
- `amount` column — revenue, cost, quantity, or refund?
- Views that encapsulate business logic vs raw base tables
- Tables with no FK constraints (Redshift) — join inference from names alone
- Wide tables with 50+ columns, most unused

**Architecture — the Mode C pattern applied to ingestion:**

The architecture already exists. Mode C in `ask_boyce` returns structured data for
the host LLM to reason about, then accepts the result back. Ingestion does the same:

```
Step 1: Agent calls ingest_source(postgresql://...)
        Boyce introspects ALL objects (tables, views, mat views, functions, sequences)
        Boyce does mechanical classification (what it can determine from metadata)
        Boyce returns snapshot + classification_needed payload

Step 2: Host LLM reads the classification_needed payload:
        - Entities needing semantic type review (MEASURE vs DIMENSION ambiguity)
        - Candidate entity groups (tables that look like duplicates/versions)
        - Join candidates (columns with matching names across tables, no FK)
        - Object type context (view vs table vs materialized view)

Step 3: Host LLM calls enrich_snapshot(snapshot_name, enrichments):
        - Semantic type overrides (field X is MEASURE, not DIMENSION)
        - Canonical entity flags (fact_orders is canonical, stg_orders is staging)
        - Inferred joins with confidence scores
        - Business name suggestions ("customer_dim" → display as "Customers")

Step 4: Boyce stores enriched classifications in the snapshot.
        All downstream tools (ask_boyce, get_schema, query_database) use them.
```

**No API key at any step.** The MCP protocol IS the communication channel. The agent
that's already connected IS the LLM. This is how MCP is designed to work.

**For non-MCP contexts** (CLI `boyce ask`, HTTP API): the existing QueryPlanner's
BYOK LiteLLM can do classification as a fallback. But this is the secondary path —
same as Mode B in ask_boyce. The primary path is host-LLM mediated.

**Broader object introspection** — `PostgresAdapter.get_schema_summary()` currently
only queries `information_schema.tables` + `information_schema.columns`. Extend to:
- Views (distinguish from base tables via `table_type`)
- Materialized views (Postgres: `pg_matviews`; Redshift: `stv_mv_info`)
- Functions/procedures (signature only, not body — `pg_proc`)
- Sequences (`information_schema.sequences`)
- Custom types/enums (`pg_type` where `typtype = 'e'`)

**Entity type field** — Add `object_type` to `Entity` in `types.py`:
```python
class ObjectType(str, Enum):
    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    EXTERNAL_TABLE = "external_table"
```
This is durable metadata (not LLM-dependent) and critical for the host LLM's
reasoning: "this is a view, so it's a curated analytical surface, not raw data."

**New MCP tool — `enrich_snapshot`:**
```python
@mcp.tool()
async def enrich_snapshot(
    snapshot_name: str = "default",
    enrichments: dict = None,
) -> str:
    """Accept host-LLM classifications to improve snapshot quality."""
```

**Bitter Lesson check:** PASSES. The structural introspection (what objects exist,
their columns, their types) is durable — no model replaces the need for it. The
semantic classification (what they MEAN) is exactly where LLMs add value. This is
the model-compensation layer used correctly — a capability multiplier on a durable
foundation, not scaffolding.

**Files:** `types.py` (ObjectType, Entity.object_type), `adapters/postgres.py`
(broader introspection queries), `server.py` (enrich_snapshot tool,
classification_needed payload in ingest_source response)

### Step 1: Schema Extension — Quality Profile
- Add `quality_profile` to `FieldDef` in `types.py`:
  ```python
  class QualityProfile(BaseModel):
      null_pct: Optional[float] = None
      distinct_count: Optional[int] = None
      cardinality_ratio: Optional[float] = None  # distinct/total
      min_value: Optional[str] = None
      max_value: Optional[str] = None
      freshness_hours: Optional[float] = None
      drift_threshold: Optional[float] = None  # max acceptable null_pct change
      last_profiled_at: Optional[str] = None  # ISO timestamp
  ```
- Add `quality_profile: Optional[QualityProfile]` to `FieldDef`
- Update `validate_snapshot()` to accept the new field
- Update `_compute_snapshot_hash()` to include quality data in hash
- Bump protocol version to 0.2
- File: `types.py`, `validation.py`
- Cursor model: **Opus 4.6** (touches the protocol contract — must be precise)

### Step 2: Ingest-Time Profiling
- When `ingest_source` is called with a live database connection (`BOYCE_DB_URL`):
  - Profile each column: null count/pct, distinct count, min/max
  - Store results in the `quality_profile` field of each `FieldDef`
  - This happens once at ingest, not at every query
- When no DB connection: `quality_profile` remains `None` (graceful degradation)
- File: `server.py` (ingest_source), `adapters/postgres.py` (profile method)
- Cursor model: **Opus 4.6** (cross-module: server → adapter → types)

### Step 3: Drift Detection
- On re-ingest of the same source:
  - Compare current quality profile against stored baseline
  - Flag when any metric moves beyond `drift_threshold`
  - Return drift warnings in the ingest response
- Store baseline profiles alongside snapshots in `_local_context/`
- File: `store.py` (baseline persistence), `server.py` (drift comparison)
- Cursor model: **Sonnet 4.6 Thinking** (comparison logic, threshold handling)

### Step 4: Enhanced `ask_boyce` Response
- Include quality signals for all columns referenced in the generated SQL:
  ```json
  {
    "sql": "...",
    "quality_signals": [
      {"field": "orders.status", "null_pct": 0.30, "warning": "NULL_TRAP"},
      {"field": "orders.revenue", "null_pct": 0.0, "status": "clean"}
    ]
  }
  ```
- Agent can reason about data quality without re-hitting the database
- File: `server.py` (ask_boyce response construction)
- Cursor model: **Sonnet 4.6** (response enrichment, straightforward)

### Step 5: Policy Stubs
- Add to `FieldDef` in `types.py`:
  ```python
  pii_flag: Optional[bool] = None
  access_roles: Optional[List[str]] = None
  aggregation_only: Optional[bool] = None
  ```
- Present in schema but NOT enforced yet — prevents breaking changes later
- Document the intended enforcement semantics in the spec
- File: `types.py`
- Cursor model: **Sonnet 4.6** (additive schema change, no logic)

### Step 6: Planner Accuracy Eval Suite
- Build a benchmark of NL queries with known-correct StructuredFilter outputs
- Test planner accuracy: does the planner produce the right entities, fields, filters?
- Categories: simple lookups, aggregations, multi-join, temporal filters, ambiguous queries
- Store benchmarks in `tests/benchmarks/`
- Report: accuracy %, failure modes, per-category breakdown
- File: `tests/benchmarks/planner_eval.py`
- Cursor model: **Opus 4.6** (needs deep understanding of planner contract)

### Step 7: Protocol Version 0.2 Release
- Bundle all schema extensions (quality_profile, policy stubs)
- Publish updated JSON Schema
- Write migration guide: v0.1 → v0.2 (fully backward compatible, all new fields optional)
- Tag release on GitHub, publish updated PyPI version
- Cursor model: **Sonnet 4.6** (docs + version bump)

---

## Acceptance Criteria
- [ ] `ingest_source` on a live DSN returns `classification_needed` payload for host LLM
- [ ] `enrich_snapshot` MCP tool accepts and stores host-LLM classifications
- [ ] Zero API keys required for full warehouse ingestion in MCP context
- [ ] Views, materialized views, functions, sequences introspected alongside tables
- [ ] `Entity.object_type` distinguishes tables from views from materialized views
- [ ] `FieldDef.quality_profile` populated at ingest time when DB is available
- [ ] Drift detection warns when quality metrics change beyond threshold on re-ingest
- [ ] `ask_boyce` response includes quality signals for referenced columns
- [ ] Policy stubs (`pii_flag`, `access_roles`, `aggregation_only`) present in schema
- [ ] Planner eval suite with at least 20 benchmark queries, accuracy measured
- [ ] Protocol v0.2 spec published with migration guide
- [ ] All tests pass (existing + new governance tests)

## Risks / Open Questions
- **Ingest-time profiling performance:** Profiling every column on a large warehouse could be slow. Mitigation: profile only columns referenced in the snapshot's field definitions, not every column in the database. Add `--skip-profiling` flag.
- **Drift threshold calibration:** What's a reasonable default `drift_threshold`? Start with 0.10 (10% change in null_pct triggers warning). Make configurable.
- **Planner eval is model-dependent:** Accuracy will vary by LLM provider. Document which model was used for each benchmark run. Consider running against 2-3 models.
- **Host-LLM classification quality variance:** Different host LLMs will classify differently. The enrichment is optional and additive — the mechanical classification is the baseline, host-LLM enrichment improves it. Bad enrichment can't make things worse than mechanical (store confidence scores, gate on them).
- **Classification payload size:** A 200-table warehouse with 2000+ columns could produce a large classification_needed payload. Cap at most-ambiguous entities (e.g., top 50 needing review) and let the host LLM request more via pagination or a `classify_more` pattern.
- **enrich_snapshot idempotency:** Multiple enrichment calls must merge, not overwrite. Store enrichment provenance (which call provided which classification) so re-enrichment is safe.
