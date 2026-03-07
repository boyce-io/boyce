# Plan: Block 3 — Data Quality & Protocol v0.2
**Status:** Pending
**Created:** 2026-02-28
**Timeline:** Days 26-35 after name is locked
**Depends on:** Block 2 (Protocol & Parsers) — spec published, parsers operational

## Goal
Data quality becomes a first-class protocol feature. Drift detection operational. Policy
stubs in the schema prevent future breaking changes. The protocol self-describes data
trustworthiness — this is the competitive wedge against dbt MCP.

"dbt tells agents what to query. We tell agents whether the answer will be trustworthy."

## Prerequisites
- Block 2 complete: SemanticSnapshot spec published, 10+ parsers, scan CLI
- Real-world deployment providing feedback on gaps
- Null Trap essay published and generating organic traffic

---

## Implementation Steps

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
