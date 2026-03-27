# Plan: Phase 5 — Agentic Ingestion (Light)
**Status:** NOT STARTED
**Created:** 2026-03-27
**Model:** Opus · high (design), Sonnet · high (build)
**Estimated effort:** ~1-2 days

---

## Goal

Add lightweight agentic ingestion features so distribution copy can say
"agentic ingestion" in the feature list. This is the first half of the
original Phase 10 — enough to claim the feature, not the full architecture.

---

## Deliverables

### 1. Entity.object_type Detection

Add `object_type` field to `Entity` in `types.py`:
```python
object_type: str = "table"  # "table" | "view" | "materialized_view" | "external_table"
```

Parsers that can distinguish (live_db, DDL) populate this. Others default to "table".
`get_schema` surfaces it. Agents can now see "this is a view, not a base table."

### 2. Broader Object Introspection

When ingesting from a live database (`PostgresAdapter`), also introspect:
- Views (already partially there — Pagila has views)
- Materialized views (if Postgres/Redshift)

Mark them with correct `object_type`.

### 3. classification_needed Payload

After ingestion, `ingest_source` analyzes the snapshot and returns a
`classification_needed` list for columns that would benefit from semantic
classification:

```python
{
    "snapshot_name": "...",
    "entities_count": 29,
    # ... existing fields ...
    "classification_needed": [
        {
            "entity": "orders",
            "column": "status",
            "reason": "Low-cardinality string column (3 distinct values) — likely an enum or category. Semantic classification would enable safer filtering.",
            "suggested_type": "enum"
        },
        {
            "entity": "users",
            "column": "role",
            "reason": "Low-cardinality string column — semantic classification would inform access control policies.",
            "suggested_type": "enum"
        }
    ]
}
```

The host LLM can report this to the user. The `enrich_snapshot` tool
(Phase 12) will eventually let the host LLM act on it. For now, the
payload is informational — surfacing intelligence, not requiring action.

### Heuristics for classification_needed

Flag a column when:
- String type + low distinct count relative to row count (likely enum)
- Name contains common semantic patterns: `status`, `type`, `category`, `role`, `tier`, `level`, `priority`
- Nullable + used in joins (potential NULL trap risk)
- Name suggests PII: `email`, `phone`, `ssn`, `address` (future policy hook)

Keep heuristics simple and conservative. Better to under-flag than over-flag.

---

## Files to Modify

| File | Change |
|---|---|
| `boyce/src/boyce/types.py` | Add `object_type` to `Entity` |
| `boyce/src/boyce/adapters/postgres.py` | Detect views/materialized views |
| `boyce/src/boyce/server.py` | Add `classification_needed` to `ingest_source` response |
| `boyce/src/boyce/validation.py` | Classification heuristics |
| `boyce/tests/verify_eyes.py` | Test object_type field |
| `boyce/tests/test_parsers.py` | Verify object_type preserved |

---

## What This Does NOT Include (deferred to Phase 12)

- `enrich_snapshot` MCP tool
- Ingest-time NULL profiling (actual percentages)
- Drift detection on re-ingest
- Policy stubs (pii_flag, access_roles)
- Protocol v0.2

---

## Acceptance Criteria

- [ ] `Entity.object_type` populated by live_db and DDL parsers
- [ ] `get_schema` shows object_type for each entity
- [ ] `ingest_source` returns `classification_needed` list
- [ ] Heuristics flag low-cardinality string columns and semantic name patterns
- [ ] All existing tests pass
- [ ] New tests cover object_type + classification_needed
