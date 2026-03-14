#!/usr/bin/env python3
"""
Boyce — FastMCP Server

Headless reference implementation. Exposes seven MCP tools:

    ingest_source      — Parse + ingest a snapshot from any supported schema format.
    ingest_definition  — Store a certified business definition; injected into planner at query time.
    get_schema         — Return full schema context + StructuredFilter docs (for host-LLM use).
    ask_boyce          — NL or StructuredFilter → SQL with NULL trap detection + EXPLAIN pre-flight.
    validate_sql       — Validate raw SQL through the safety layer without executing it.
    query_database     — Execute a read-only SELECT against the live database.
    profile_data       — Profile a column (null %, distinct count, min/max).

Internal functions (not MCP tools, callable from HTTP API / CLI):
    build_sql          — StructuredFilter → SQL (deterministic, no LLM).
    solve_path         — Find the optimal join path between two entities (Dijkstra).

Run:
    python -m boyce.server
    boyce
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from . import kernel
from .adapters import DatabaseAdapter
from .graph import SemanticGraph
from .planner import QueryPlanner
from .safety import lint_redshift_compat
from .audit import AuditLog
from .store import DefinitionStore, SnapshotStore
from .types import SemanticSnapshot
from .validation import validate_snapshot

# ---------------------------------------------------------------------------
# StructuredFilter documentation — returned by get_schema so the host LLM
# can construct valid filters without needing Boyce's own LLM.
# ---------------------------------------------------------------------------

_STRUCTURED_FILTER_DOCS: str = """\
## StructuredFilter Format

A StructuredFilter is the JSON contract between "intent" and "SQL generation".
Pass one to `ask_boyce` (via the `structured_filter` parameter) and Boyce will
produce deterministic SQL with no LLM call on Boyce's side.

### Shape

```json
{
  "concept_map": {
    "entities":   [{"entity_id": "entity:orders", "entity_name": "orders"}],
    "fields":     [{"field_id": "field:orders:revenue", "field_name": "revenue",
                    "entity_id": "entity:orders"}],
    "metrics":    [{"metric_name": "revenue", "field_id": "field:orders:revenue",
                    "aggregation_type": "SUM"}],
    "dimensions": [{"field_id": "field:orders:status", "field_name": "status",
                    "entity_id": "entity:orders"}],
    "filters":    [{"field_id": "field:orders:status", "operator": "=",
                    "value": "active", "entity_id": "entity:orders"}]
  },
  "join_path":        ["entity:orders", "entity:customers"],
  "grain_context":    {"aggregation_required": true, "grouping_fields": ["field:orders:status"]},
  "policy_context":   {"resolved_predicates": []},
  "temporal_filters": [{"field_id": "field:orders:created_at",
                         "operator": "trailing_interval",
                         "value": {"value": 12, "unit": "month"}}],
  "dialect":          "redshift"
}
```

### Filter Operators
- Equality: `=`, `!=`
- Comparison: `>`, `>=`, `<`, `<=`
- Set: `IN`, `NOT IN` (value is a list)
- Pattern: `LIKE`, `ILIKE`
- Null: `IS NULL`, `IS NOT NULL` (value is null)

### Temporal Operators
- `trailing_interval` — value: `{"value": N, "unit": "day|week|month|quarter|year"}`
- `leading_interval`  — value: `{"value": N, "unit": "..."}`
- `between`           — value: `{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}`
- `on_or_after`       — value: `"YYYY-MM-DD"`
- `on_or_before`      — value: `"YYYY-MM-DD"`
- `equals`            — value: `"YYYY-MM-DD"`

### Aggregation Types
`SUM`, `COUNT`, `COUNT_DISTINCT`, `AVG`, `MIN`, `MAX`

### grain_context keys
- `aggregation_required` — true when metrics are present (triggers GROUP BY)
- `grouping_fields` — list of field_ids to group by
- `date_trunc_field` — field_id of a date/timestamp dimension to truncate (optional)
- `date_trunc_unit` — truncation granularity: `"day"`, `"week"`, `"month"`, `"quarter"`, `"year"` (required if date_trunc_field is set)

When the user asks for time-series aggregation ("monthly counts", "weekly revenue", "by year"), set `date_trunc_field` and `date_trunc_unit` in `grain_context`. Boyce will render `DATE_TRUNC('month', "field")` in both SELECT and GROUP BY.

### Rules
1. Every `entity_id` and `field_id` must exist in the snapshot returned by `get_schema`.
2. `metrics` require `grain_context.aggregation_required = true`.
3. `join_path` is optional — Boyce resolves joins via Dijkstra if omitted.
4. `dialect` defaults to `"redshift"`. Supported: `"redshift"`, `"postgres"`, `"duckdb"`, `"bigquery"`.

### Examples

**Example 1: Simple aggregation**
User question: "Total revenue by product status"
```json
{
  "concept_map": {
    "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
    "fields": [],
    "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue",
                  "aggregation_type": "SUM"}],
    "dimensions": [{"field_id": "field:orders:status", "field_name": "status",
                     "entity_id": "entity:orders"}],
    "filters": []
  },
  "join_path": ["entity:orders"],
  "grain_context": {"aggregation_required": true, "grouping_fields": ["status"]},
  "policy_context": {"resolved_predicates": []},
  "temporal_filters": [],
  "dialect": "redshift"
}
```

**Example 2: Filtered query with temporal range**
User question: "Active customers in the last 6 months"
```json
{
  "concept_map": {
    "entities": [{"entity_id": "entity:customers", "entity_name": "customers"}],
    "fields": [{"field_id": "field:customers:customer_id", "field_name": "customer_id",
                 "entity_id": "entity:customers"}],
    "metrics": [{"metric_name": "customer_id", "field_id": "field:customers:customer_id",
                  "aggregation_type": "COUNT_DISTINCT"}],
    "dimensions": [],
    "filters": [{"field_id": "field:customers:status", "operator": "=",
                  "value": "active", "entity_id": "entity:customers"}]
  },
  "join_path": ["entity:customers"],
  "temporal_filters": [{"field_id": "field:customers:last_login",
                          "operator": "trailing_interval",
                          "value": {"value": 6, "unit": "month"}}],
  "grain_context": {"aggregation_required": true, "grouping_fields": []},
  "policy_context": {"resolved_predicates": []},
  "dialect": "redshift"
}
```

**Example 3: Multi-table join**
User question: "Revenue by customer name"
```json
{
  "concept_map": {
    "entities": [{"entity_id": "entity:orders", "entity_name": "orders"},
                 {"entity_id": "entity:customers", "entity_name": "customers"}],
    "fields": [],
    "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue",
                  "aggregation_type": "SUM"}],
    "dimensions": [{"field_id": "field:customers:name", "field_name": "name",
                     "entity_id": "entity:customers"}],
    "filters": []
  },
  "join_path": ["entity:orders", "entity:customers"],
  "grain_context": {"aggregation_required": true, "grouping_fields": ["name"]},
  "policy_context": {"resolved_predicates": []},
  "temporal_filters": [],
  "dialect": "redshift"
}
```

**Example 4: Time-series aggregation (monthly counts)**
User question: "Monthly order counts for 1997"
```json
{
  "concept_map": {
    "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
    "fields": [],
    "metrics": [{"metric_name": "order_count", "field_id": "field:orders:order_id",
                  "aggregation_type": "COUNT"}],
    "dimensions": [{"field_id": "field:orders:order_date", "field_name": "order_date",
                     "entity_id": "entity:orders"}],
    "filters": []
  },
  "join_path": ["entity:orders"],
  "grain_context": {
    "aggregation_required": true,
    "grouping_fields": ["field:orders:order_date"],
    "date_trunc_field": "field:orders:order_date",
    "date_trunc_unit": "month"
  },
  "policy_context": {"resolved_predicates": []},
  "temporal_filters": [{"field_id": "field:orders:order_date",
                          "operator": "between",
                          "value": {"start": "1997-01-01", "end": "1997-12-31"}}],
  "dialect": "postgres"
}
```
Boyce renders: `SELECT DATE_TRUNC('month', "order_date") AS "order_date_month", COUNT("order_id") AS "order_count" FROM "orders" WHERE "order_date" BETWEEN '1997-01-01' AND '1997-12-31' GROUP BY DATE_TRUNC('month', "order_date")`
"""


def _validate_structured_filter(
    structured_filter: Dict[str, Any],
    snapshot: "SemanticSnapshot",
) -> List[str]:
    """
    Validate a host-LLM-produced StructuredFilter against the snapshot.

    Returns a list of error strings.  Empty list = valid.
    """
    errors: List[str] = []
    concept_map = structured_filter.get("concept_map")
    if not concept_map or not isinstance(concept_map, dict):
        errors.append("'concept_map' is required and must be a dict")
        return errors  # Nothing else to validate

    # --- entities ---
    entities = concept_map.get("entities", [])
    if not entities:
        errors.append("concept_map.entities must contain at least one entity")
    for ent in entities:
        eid = ent.get("entity_id", "") if isinstance(ent, dict) else ent
        if eid and eid not in snapshot.entities:
            errors.append(f"entity_id '{eid}' not found in snapshot")

    # --- fields ---
    for field in concept_map.get("fields", []):
        fid = field.get("field_id", "") if isinstance(field, dict) else field
        if fid and fid not in snapshot.fields:
            errors.append(f"field_id '{fid}' not found in snapshot")

    # --- metrics ---
    valid_aggs = {"SUM", "COUNT", "COUNT_DISTINCT", "AVG", "MIN", "MAX"}
    for metric in concept_map.get("metrics", []):
        fid = metric.get("field_id", "") if isinstance(metric, dict) else ""
        if fid and fid not in snapshot.fields:
            errors.append(f"metric field_id '{fid}' not found in snapshot")
        agg = metric.get("aggregation_type", "") if isinstance(metric, dict) else ""
        if agg and agg not in valid_aggs:
            errors.append(f"invalid aggregation_type '{agg}'; expected one of {sorted(valid_aggs)}")

    # --- dimensions ---
    for dim in concept_map.get("dimensions", []):
        fid = dim.get("field_id", "") if isinstance(dim, dict) else dim
        if fid and fid not in snapshot.fields:
            errors.append(f"dimension field_id '{fid}' not found in snapshot")

    # --- filters ---
    valid_ops = {"=", "!=", ">", ">=", "<", "<=", "IN", "NOT IN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL"}
    for filt in concept_map.get("filters", []):
        fid = filt.get("field_id", "") if isinstance(filt, dict) else ""
        if fid and fid not in snapshot.fields:
            errors.append(f"filter field_id '{fid}' not found in snapshot")
        op = filt.get("operator", "") if isinstance(filt, dict) else ""
        op = _OPERATOR_ALIASES.get(op, op)  # normalise alias variants
        if op and op not in valid_ops:
            errors.append(f"invalid filter operator '{op}'; expected one of {sorted(valid_ops)}")

    # --- temporal_filters ---
    valid_temporal = {"trailing_interval", "leading_interval", "between", "on_or_after", "on_or_before", "equals"}
    for tf in structured_filter.get("temporal_filters", []):
        fid = tf.get("field_id", "")
        if fid and fid not in snapshot.fields:
            errors.append(f"temporal_filter field_id '{fid}' not found in snapshot")
        op = tf.get("operator", "")
        if op and op not in valid_temporal:
            errors.append(f"invalid temporal operator '{op}'; expected one of {sorted(valid_temporal)}")

    # --- dialect ---
    dialect = structured_filter.get("dialect", "redshift")
    valid_dialects = {"redshift", "postgres", "duckdb", "bigquery"}
    if dialect not in valid_dialects:
        errors.append(f"invalid dialect '{dialect}'; expected one of {sorted(valid_dialects)}")

    return errors


try:
    from .adapters.postgres import PostgresAdapter
    _POSTGRES_AVAILABLE = True
except ImportError:
    _POSTGRES_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------

mcp = FastMCP("Boyce", json_response=True)

# Context dir: _local_context/ relative to the working directory at runtime.
_LOCAL_CONTEXT = Path("_local_context")
_store = SnapshotStore(_LOCAL_CONTEXT)
_definitions = DefinitionStore(_LOCAL_CONTEXT)
_audit = AuditLog(_LOCAL_CONTEXT)
_graph = SemanticGraph()

# Operator aliases — host LLMs often use underscore variants (NOT_IN, IS_NULL).
# Normalise before validation and before the builder's FilterOperator() call.
_OPERATOR_ALIASES: Dict[str, str] = {
    "NOT_IN": "NOT IN",
    "IS_NULL": "IS NULL",
    "IS_NOT_NULL": "IS NOT NULL",
    "ISNULL": "IS NULL",
    "ISNOTNULL": "IS NOT NULL",
    "NOT_EQUALS": "!=",
    "GREATER_THAN": ">",
    "GREATER_THAN_OR_EQUAL": ">=",
    "LESS_THAN": "<",
    "LESS_THAN_OR_EQUAL": "<=",
}

# Lazily initialised once the first query_database call arrives.
_adapter: "DatabaseAdapter | None" = None


# ---------------------------------------------------------------------------
# Planner helpers
# ---------------------------------------------------------------------------


def _get_planner() -> QueryPlanner:
    """
    Instantiate a QueryPlanner from environment variables.

    Required env vars:
        BOYCE_PROVIDER  — LLM provider (e.g. "openai", "anthropic")
        BOYCE_MODEL     — Model name  (e.g. "gpt-4o", "claude-3-5-sonnet-20241022")

    Optional env vars (first match wins):
        OPENAI_API_KEY / ANTHROPIC_API_KEY / LITELLM_API_KEY

    The planner raises ValueError at plan_query() time if any required value
    is missing, so the server boots cleanly even without credentials configured.
    """
    return QueryPlanner(
        provider=os.environ.get("BOYCE_PROVIDER"),
        model=os.environ.get("BOYCE_MODEL"),
    )


# ---------------------------------------------------------------------------
# Pre-flight validation helpers
# ---------------------------------------------------------------------------

# Matches the total cost in a Postgres EXPLAIN line:
#   Seq Scan on orders  (cost=0.00..431.80 rows=1280 width=228)
#                                    ^^^^^^
_EXPLAIN_COST_RE = re.compile(r"\(cost=[\d.]+\.\.([\d.]+)")


def _parse_explain_cost(rows: list) -> Optional[float]:
    """
    Extract the total cost estimate from the first node of EXPLAIN output.

    asyncpg returns rows with a single ``"QUERY PLAN"`` key whose value is a
    plain-text plan line, e.g.::

        {"QUERY PLAN": "Seq Scan on orders  (cost=0.00..431.80 rows=1280 width=228)"}

    Returns the total-cost float, or None if the pattern is not found.
    """
    if not rows:
        return None
    plan_text = rows[0].get("QUERY PLAN", "")
    m = _EXPLAIN_COST_RE.search(plan_text)
    return float(m.group(1)) if m else None


async def _preflight_check(sql: str) -> dict:
    """
    Run ``EXPLAIN <sql>`` against the live database and return a validation dict.

    Returns one of three shapes:

    * ``{"status": "verified", "error": null, "cost_estimate": <float|null>}``
      — EXPLAIN succeeded; the query is structurally valid and all tables exist.

    * ``{"status": "invalid",  "error": "<postgres error>", "cost_estimate": null}``
      — EXPLAIN failed; SQL references a non-existent table or has a syntax error.

    * ``{"status": "unchecked", "error": null, "cost_estimate": null}``
      — No live DB adapter is configured (``BOYCE_DB_URL`` not set).
      The SQL may still be correct — it just hasn't been verified.
    """
    try:
        adapter = await _get_adapter()
    except RuntimeError:
        # No adapter configured — perfectly normal when running without a DB
        return {"status": "unchecked", "error": None, "cost_estimate": None}

    try:
        rows = await adapter.execute_query(f"EXPLAIN {sql}")
        cost = _parse_explain_cost(rows)
        return {"status": "verified", "error": None, "cost_estimate": cost}
    except Exception as e:
        return {"status": "invalid", "error": str(e), "cost_estimate": None}


# ---------------------------------------------------------------------------
# Null Trap detection
# ---------------------------------------------------------------------------

_NULL_TRAP_THRESHOLD_PCT: float = 5.0  # flag when null_pct exceeds this


async def _null_trap_check(
    snapshot: "SemanticSnapshot",
    structured_filter: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Profile columns that appear in equality (=) filters against the live DB.

    An equality predicate silently excludes every NULL row — the result set is
    a subset of the table with no indication that rows were dropped.  When a
    column's real null distribution exceeds _NULL_TRAP_THRESHOLD_PCT, this
    function returns a warning dict so the caller can surface it before the
    query executes.

    Returns:
        List of warning dicts.  Empty if:
          - No live DB is configured (BOYCE_DB_URL not set).
          - No equality filters exist in the structured_filter.
          - All equality-filtered columns are below the threshold.

        Each warning dict has keys:
            table           — schema-qualified or bare table name
            column          — column name
            null_pct        — % of rows where column IS NULL (float, 0–100)
            null_count      — absolute null row count
            row_count       — total rows in the table
            filter_operator — always "=" for this check
            filter_value    — the literal value being compared
            risk            — human-readable explanation of the hazard
    """
    try:
        adapter = await _get_adapter()
    except RuntimeError:
        return []   # No DB configured — same silent behaviour as _preflight_check

    equality_filters = [
        f for f in structured_filter.get("concept_map", {}).get("filters", [])
        if f.get("operator") == "="
    ]
    if not equality_filters:
        return []

    warnings: List[Dict[str, Any]] = []

    for filt in equality_filters:
        field_id  = filt.get("field_id", "")
        entity_id = filt.get("entity_id", "")
        if not field_id or not entity_id:
            continue

        field  = snapshot.fields.get(field_id)
        entity = snapshot.entities.get(entity_id)
        if not field or not entity:
            continue

        # entity.schema_name is the Python attr; the JSON alias is "schema"
        table = (
            f"{entity.schema_name}.{entity.name}"
            if entity.schema_name
            else entity.name
        )
        column = field.name

        try:
            profile = await adapter.profile_column(table, column)
        except Exception as exc:
            logger.debug(
                "_null_trap_check: profile_column failed for %s.%s: %s",
                table, column, exc,
            )
            continue   # Non-fatal — never block SQL generation on a failed profile

        null_pct = profile.get("null_pct", 0.0)
        if null_pct <= _NULL_TRAP_THRESHOLD_PCT:
            continue

        null_count = profile.get("null_count", "?")
        row_count  = profile.get("row_count",  "?")
        val        = filt.get("value", "?")

        warnings.append({
            "table":           table,
            "column":          column,
            "null_pct":        null_pct,
            "null_count":      null_count,
            "row_count":       row_count,
            "filter_operator": "=",
            "filter_value":    val,
            "risk": (
                f"WHERE {column} = '{val}' silently excludes {null_count} NULL rows "
                f"({null_pct:.1f}% of {table}). "
                f"NULL is never equal to any value — those rows vanish without warning. "
                f"Confirm that NULL '{column}' should be excluded before running any "
                f"write or aggregation query against this result set."
            ),
        })

    return warnings


# ---------------------------------------------------------------------------
# Shared SQL pipeline — used by both ask_boyce and build_sql
# ---------------------------------------------------------------------------


async def _run_sql_pipeline(
    snapshot: "SemanticSnapshot",
    structured_filter: Dict[str, Any],
    snapshot_name: str,
    dialect: str,
    *,
    query_label: str = "",
) -> dict:
    """
    Execute Stages 2-4 of the Boyce pipeline (deterministic, no LLM):

      Stage 2:   kernel.process_request() → SQL
      Stage 2.5: _null_trap_check()       → NULL hazard warnings
      Stage 3:   _preflight_check()       → EXPLAIN validation
      Stage 4:   lint_redshift_compat()   → Redshift compat risks

    Args:
        snapshot:          SemanticSnapshot to compile against.
        structured_filter: StructuredFilter dict (from planner or host LLM).
        snapshot_name:     Logical name of the snapshot (for audit log).
        dialect:           Target SQL dialect.
        query_label:       Human-readable label for the audit log (e.g. the NL query).

    Returns:
        JSON-serializable dict with keys: sql, snapshot_id, snapshot_name,
        entities_resolved, validation, [compat_risks], [warning], [null_trap_warnings].

    Raises:
        ValueError: Propagated from kernel.process_request on malformed input.
    """
    # Stamp dialect
    structured_filter["dialect"] = dialect

    # Stage 2: deterministic SQL generation
    sql = kernel.process_request(snapshot, structured_filter)

    entities_resolved = [
        e.get("entity_name", e.get("entity_id", ""))
        for e in structured_filter.get("concept_map", {}).get("entities", [])
    ]

    # Stage 2.5: Null Trap check
    null_trap_warnings = await _null_trap_check(snapshot, structured_filter)

    # Stage 3: EXPLAIN pre-flight
    validation = await _preflight_check(sql)

    payload: dict = {
        "sql": sql,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_name": snapshot_name,
        "entities_resolved": entities_resolved,
        "validation": validation,
    }

    if null_trap_warnings:
        payload["warning"] = {
            "code": "NULL_TRAP",
            "severity": "HIGH",
            "message": (
                f"{len(null_trap_warnings)} column(s) in the WHERE clause contain "
                f"significant NULL values that will be silently excluded by this query. "
                "Review 'null_trap_warnings' before executing."
            ),
        }
        payload["null_trap_warnings"] = null_trap_warnings

    # Stage 4: Redshift compat lint
    compat_risks = lint_redshift_compat(sql)
    if compat_risks:
        payload["compat_risks"] = compat_risks

    # Audit
    _audit.log_query(
        query=query_label,
        snapshot_name=snapshot_name,
        snapshot_id=snapshot.snapshot_id,
        sql=sql,
        entities_resolved=entities_resolved,
        validation_status=validation["status"],
        null_trap_count=len(null_trap_warnings),
        compat_risk_count=len(compat_risks) if compat_risks else 0,
    )

    return payload


# ---------------------------------------------------------------------------
# Mode C schema guidance — returned by ask_boyce when no credentials configured
# ---------------------------------------------------------------------------


def _build_schema_guidance(
    query: str,
    snapshot: "SemanticSnapshot",
    snapshot_name: str,
) -> str:
    """
    Mode C fallback for ask_boyce: return schema context + StructuredFilter docs
    so the host LLM can construct a filter and call back with structured_filter.

    Scores entities by keyword overlap with the query (mirrors planner.py:131-138)
    and returns the top-50 most relevant with full field details.
    """
    # Score entities by keyword overlap with query
    query_words = set(re.findall(r"\b\w+\b", query.lower()))
    entity_scores: List[tuple] = []
    for eid, entity in snapshot.entities.items():
        score = sum(1 for w in query_words if w in entity.name.lower())
        if score > 0 or len(snapshot.entities) <= 50:
            entity_scores.append((score, eid))
    entity_scores.sort(reverse=True, key=lambda x: x[0])
    top_entity_ids = [eid for _, eid in entity_scores[:50]]

    # Build entity context with full field details
    entities_out = []
    for eid in top_entity_ids:
        entity = snapshot.entities[eid]
        fields_out = []
        for fid in entity.fields:
            field = snapshot.fields.get(fid)
            if field:
                fields_out.append({
                    "field_id": field.id,
                    "name": field.name,
                    "field_type": field.field_type.value,
                    "data_type": field.data_type,
                    "nullable": field.nullable,
                    "description": field.description,
                })
        entities_out.append({
            "entity_id": eid,
            "name": entity.name,
            "description": entity.description,
            "grain": entity.grain,
            "fields": fields_out,
        })

    definitions_context = _definitions.as_context_string(snapshot_name)

    return json.dumps({
        "mode": "schema_guidance",
        "message": (
            "Boyce has no LLM credentials configured. "
            "Use the schema context and StructuredFilter docs below to construct "
            "a StructuredFilter, then call ask_boyce again with the "
            "structured_filter parameter. No additional credentials are needed."
        ),
        "query": query,
        "snapshot_name": snapshot_name,
        "relevant_entities": entities_out,
        "structured_filter_docs": _STRUCTURED_FILTER_DOCS,
        "definitions_context": definitions_context or None,
    })


# ---------------------------------------------------------------------------
# Schema freshness helpers (Tier 2: mtime check, Tier 3: live DB drift)
# ---------------------------------------------------------------------------

# Track which snapshots have been freshness-checked this session
_freshness_checked: set = set()
_drift_checked: set = set()


def _check_snapshot_freshness(snapshot_name: str) -> Optional[str]:
    """
    Check if a snapshot's source file has been modified since the snapshot was saved.

    Returns a message string if the snapshot was auto-refreshed or is stale,
    None if fresh or unable to check. Only runs once per snapshot per server session.

    Tier 2 of schema freshness: session-start mtime check.
    """
    if snapshot_name in _freshness_checked:
        return None
    _freshness_checked.add(snapshot_name)

    try:
        snapshot = _store.load(snapshot_name)
    except (FileNotFoundError, ValueError):
        return None

    source_path_str = snapshot.metadata.get("source_path")
    if not source_path_str:
        return None

    source_path = Path(source_path_str)
    if not source_path.exists():
        logger.warning(
            "Snapshot '%s' source file no longer exists: %s",
            snapshot_name, source_path,
        )
        return None  # Don't warn — file might have been moved intentionally

    # Compare source file mtime to snapshot file mtime
    snapshot_file = _LOCAL_CONTEXT / f"{snapshot_name}.json"
    if not snapshot_file.exists():
        return None

    source_mtime = source_path.stat().st_mtime
    snapshot_mtime = snapshot_file.stat().st_mtime

    if source_mtime <= snapshot_mtime:
        return None  # Snapshot is fresh

    age_seconds = source_mtime - snapshot_mtime
    age_human = (
        f"{int(age_seconds // 3600)}h {int((age_seconds % 3600) // 60)}m"
        if age_seconds > 3600
        else f"{int(age_seconds // 60)}m"
    )
    warning = (
        f"Source file '{source_path.name}' has been modified since snapshot "
        f"'{snapshot_name}' was created ({age_human} newer). "
        f"Run ingest_source to refresh."
    )
    logger.info("Snapshot freshness: %s", warning)

    # Attempt auto re-ingest
    try:
        from .parsers import parse_from_path  # noqa: PLC0415
        new_snapshot = parse_from_path(str(source_path))
        if new_snapshot.snapshot_id != snapshot.snapshot_id:
            _store.save(new_snapshot, snapshot_name)
            if new_snapshot.snapshot_id not in _graph.snapshots:
                _graph.add_snapshot(new_snapshot)
            logger.info(
                "Auto re-ingested '%s': snapshot_id changed %s → %s",
                snapshot_name, snapshot.snapshot_id[:12], new_snapshot.snapshot_id[:12],
            )
            return (
                f"Snapshot '{snapshot_name}' was auto-refreshed from "
                f"'{source_path.name}' (source was modified)."
            )
        else:
            return None  # Source file changed but snapshot content is the same
    except Exception as exc:
        logger.warning("Auto re-ingest failed for '%s': %s", snapshot_name, exc)
        return warning  # Return stale warning since we couldn't auto-refresh


async def _check_db_drift(snapshot_name: str) -> Optional[Dict[str, Any]]:
    """
    Compare snapshot entities/fields against live database information_schema.

    Returns a drift report dict if discrepancies found, None otherwise.
    Only runs once per snapshot per server session. Requires BOYCE_DB_URL.

    Tier 3 of schema freshness: live DB drift detection.
    """
    if snapshot_name in _drift_checked:
        return None
    _drift_checked.add(snapshot_name)

    try:
        adapter = await _get_adapter()
    except RuntimeError:
        return None  # No DB configured

    try:
        snapshot = _store.load(snapshot_name)
    except (FileNotFoundError, ValueError):
        return None

    # Query information_schema for all columns in public schema
    try:
        rows = await adapter.execute_query(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "ORDER BY table_name, ordinal_position"
        )
    except Exception as exc:
        logger.debug("Drift check query failed: %s", exc)
        return None

    # Build set of (table, column) from live DB
    live_columns: set = set()
    for row in rows:
        live_columns.add((row["table_name"], row["column_name"]))

    # Build set of (table, column) from snapshot
    snapshot_columns: set = set()
    for entity_id, entity in snapshot.entities.items():
        for field_id in entity.fields:
            field = snapshot.fields.get(field_id)
            if field:
                snapshot_columns.add((entity.name, field.name))

    new_in_db = live_columns - snapshot_columns
    missing_from_db = snapshot_columns - live_columns

    if not new_in_db and not missing_from_db:
        return None

    new_by_table: Dict[str, List[str]] = {}
    for table, column in sorted(new_in_db):
        new_by_table.setdefault(table, []).append(column)

    missing_by_table: Dict[str, List[str]] = {}
    for table, column in sorted(missing_from_db):
        missing_by_table.setdefault(table, []).append(column)

    report: Dict[str, Any] = {
        "new_in_db": new_by_table,
        "missing_from_db": missing_by_table,
        "message": (
            f"Snapshot '{snapshot_name}' may be stale: "
            f"{len(new_in_db)} column(s) in the live database are not in the snapshot"
            + (f", {len(missing_from_db)} column(s) in the snapshot are not in the database"
               if missing_from_db else "")
            + ". Run ingest_source to refresh."
        ),
    }

    logger.info("DB drift detected for '%s': %s", snapshot_name, report["message"])
    return report


# ---------------------------------------------------------------------------
# Live-DB schema ingestion helper
# ---------------------------------------------------------------------------


def _build_snapshot_from_live_db(
    schema_summary: list,
    fk_rows: list,
    db_url: str,
) -> "SemanticSnapshot":
    """
    Convert PostgresAdapter.get_schema_summary() + get_foreign_keys() output
    into a SemanticSnapshot.

    FK columns are classified as FOREIGN_KEY; PKs as ID; timestamps/dates as
    TIMESTAMP; numeric types as MEASURE; everything else as DIMENSION.
    """
    from .parsers.base import build_snapshot
    from .types import Entity, FieldDef, FieldType, JoinDef, JoinType
    from .adapters.postgres import _redact_dsn

    def _classify(data_type: str, is_pk: bool) -> FieldType:
        if is_pk:
            return FieldType.ID
        dt = data_type.lower()
        if any(t in dt for t in ("timestamp", "date", "time")):
            return FieldType.TIMESTAMP
        if any(t in dt for t in ("numeric", "decimal", "real", "double", "float", "money")):
            return FieldType.MEASURE
        return FieldType.DIMENSION

    # FK lookup: (src_schema, src_table, src_column) → (tgt_table, tgt_column)
    fk_lookup: Dict[tuple, tuple] = {}
    for row in fk_rows:
        key = (row["src_schema"], row["src_table"], row["src_column"])
        fk_lookup[key] = (row["tgt_table"], row["tgt_column"])

    entities: Dict[str, Any] = {}
    fields: Dict[str, Any] = {}
    joins: List[Any] = []

    for table_info in schema_summary:
        schema_name = table_info["schema"]
        table_name = table_info["table"]
        entity_id = f"entity:{table_name}"
        entity_field_ids: List[str] = []
        grain: Optional[str] = None
        join_target_counts: Dict[str, int] = {}

        for col in table_info["columns"]:
            col_name = col["name"]
            is_pk = col["primary_key"]
            fk_key = (schema_name, table_name, col_name)
            is_fk = fk_key in fk_lookup
            ft = FieldType.FOREIGN_KEY if is_fk else _classify(col["data_type"], is_pk)
            field_id = f"field:{table_name}:{col_name}"

            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=col_name,
                field_type=ft,
                data_type=col["data_type"].upper(),
                nullable=col["nullable"],
                primary_key=is_pk,
            )
            entity_field_ids.append(field_id)

            if is_pk and grain is None:
                grain = col_name

            if is_fk:
                tgt_table, tgt_col = fk_lookup[fk_key]
                tgt_entity_id = f"entity:{tgt_table}"
                join_target_counts[tgt_entity_id] = join_target_counts.get(tgt_entity_id, 0) + 1
                count = join_target_counts[tgt_entity_id]
                join_id = (
                    f"join:{table_name}:{tgt_table}"
                    if count == 1
                    else f"join:{table_name}:{tgt_table}:{col_name}"
                )
                joins.append(JoinDef(
                    id=join_id,
                    source_entity_id=entity_id,
                    target_entity_id=tgt_entity_id,
                    join_type=JoinType.LEFT,
                    source_field_id=field_id,
                    target_field_id=f"field:{tgt_table}:{tgt_col}",
                    description=f"FK: {table_name}.{col_name} → {tgt_table}.{tgt_col}",
                ))

        entities[entity_id] = Entity(
            id=entity_id,
            name=table_name,
            schema_name=schema_name,
            fields=entity_field_ids,
            grain=grain or "id",
        )

    return build_snapshot(
        source_system="postgres_live",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "source_type": "live_db",
            "db_url": _redact_dsn(db_url),
        },
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def ingest_source(
    source_path: Optional[str] = None,
    snapshot_json: Optional[dict] = None,
    snapshot_name: str = "default",
) -> str:
    """
    Ingest a database schema and store it as a named snapshot. Call this FIRST
    before using ask_boyce or build_sql.

    Provide exactly one of source_path or snapshot_json.

    Args:
        source_path: Either a file/directory path OR a live PostgreSQL DSN.
            File formats auto-detected: .sql DDL files, dbt manifest.json, dbt
            project directories (dbt_project.yml), LookML .lkml files, SQLite
            .db/.sqlite files, Django models.py, SQLAlchemy models, Prisma
            .prisma files, CSV/Parquet data files, pre-built SemanticSnapshot
            .json files.
            Live DB: pass a postgresql:// or postgres:// DSN — Boyce introspects
            the schema directly (requires asyncpg + BOYCE_DB_URL or inline DSN).
        snapshot_json: A dict conforming to the SemanticSnapshot schema.
            Must include a valid snapshot_id (SHA-256 of canonical content).
            Use this to ingest a pre-built snapshot directly.
        snapshot_name: Logical name used to store / retrieve this snapshot.
            Defaults to "default".

    Returns:
        JSON string with keys:
            snapshot_id, snapshot_name, entities_count, fields_count, joins_count,
            source_type ("parsed" for file sources, "live_db" for DSN ingestion)
    """
    if source_path is not None:
        # Live-DB path: DSN → introspect via PostgresAdapter
        if source_path.startswith(("postgresql://", "postgres://")):
            if not _POSTGRES_AVAILABLE:
                return json.dumps({
                    "error": {
                        "code": -32602,
                        "message": (
                            "asyncpg is not installed. "
                            'Install it with: pip install "boyce[postgres]"'
                        ),
                    }
                })
            try:
                from .adapters.postgres import PostgresAdapter
                tmp_adapter = PostgresAdapter(source_path)
                await tmp_adapter.connect()
                try:
                    schema_summary = await tmp_adapter.get_schema_summary()
                    fk_rows = await tmp_adapter.get_foreign_keys()
                finally:
                    await tmp_adapter.disconnect()
                snapshot = _build_snapshot_from_live_db(schema_summary, fk_rows, source_path)
            except Exception as e:
                return json.dumps({
                    "error": {"code": -32602, "message": f"Failed to introspect live DB: {e}"}
                })
        else:
            # File / directory path
            try:
                from .parsers import parse_from_path
                snapshot = parse_from_path(source_path)
            except Exception as e:
                return json.dumps({
                    "error": {"code": -32602, "message": f"Failed to parse source: {e}"}
                })

        errors = validate_snapshot(snapshot.model_dump())
        if errors:
            return json.dumps({
                "error": {
                    "code": -32602,
                    "message": f"Parsed snapshot failed validation: {errors}",
                    "data": errors,
                }
            })

        try:
            _store.save(snapshot, snapshot_name)
        except Exception as e:
            return json.dumps({
                "error": {"code": -32603, "message": f"Failed to save snapshot: {e}"}
            })

        # Clear stale definitions from the previous occupant of this snapshot slot.
        _definitions.clear(snapshot_name)

        if snapshot.snapshot_id not in _graph.snapshots:
            _graph.add_snapshot(snapshot)

        return json.dumps({
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_name": snapshot_name,
            "entities_count": len(snapshot.entities),
            "fields_count": len(snapshot.fields),
            "joins_count": len(snapshot.joins),
            "source_type": snapshot.metadata.get("source_type", "parsed"),
        })

    if snapshot_json is None:
        return json.dumps({
            "error": {
                "code": -32602,
                "message": "Provide either source_path (file/directory) or snapshot_json.",
            }
        })

    errors = validate_snapshot(snapshot_json)
    if errors:
        return json.dumps({
            "error": {
                "code": -32602,
                "message": "Snapshot failed validation",
                "data": errors,
            }
        })

    try:
        snapshot = SemanticSnapshot(**snapshot_json)
    except Exception as e:
        return json.dumps({
            "error": {"code": -32602, "message": f"Failed to construct snapshot: {e}"}
        })

    try:
        _store.save(snapshot, snapshot_name)
    except Exception as e:
        return json.dumps({
            "error": {"code": -32603, "message": f"Failed to save snapshot: {e}"}
        })

    _definitions.clear(snapshot_name)

    if snapshot.snapshot_id not in _graph.snapshots:
        _graph.add_snapshot(snapshot)

    return json.dumps({
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_name": snapshot_name,
        "entities_count": len(snapshot.entities),
        "fields_count": len(snapshot.fields),
        "joins_count": len(snapshot.joins),
    })


@mcp.tool()
def ingest_definition(
    term: str,
    definition: str,
    sql_expression: Optional[str] = None,
    entity_hint: Optional[str] = None,
    snapshot_name: str = "default",
) -> str:
    """
    Store a certified business definition that Boyce will apply at query time.

    Business definitions encode *what your data means* — the logic that lives in
    analysts' heads or scattered across docs but is never in the schema itself.
    Once stored, Boyce injects these definitions into the planner so they are
    applied automatically whenever the term appears in a natural language query.

    Examples:
        term="revenue", definition="Total recognized revenue — SUM of order_total
          for completed, non-refunded orders", sql_expression="SUM(CASE WHEN
          status = 'completed' AND is_refunded = false THEN order_total ELSE 0 END)",
          entity_hint="orders"

        term="active user", definition="A user who placed at least one order in the
          last 30 days", entity_hint="users"

        term="churn rate", definition="Percentage of subscribers whose status changed
          to 'cancelled' in the reporting period"

    Args:
        term: The business term to define (e.g. "revenue", "active user", "churn rate").
            Case-insensitive for matching; stored as provided.
        definition: Plain-language definition of the term. Be specific — include
            the exact business logic, edge cases, and what is included vs. excluded.
        sql_expression: Optional SQL expression that implements this definition.
            Boyce will use this as the authoritative SQL for this concept.
            Use column names that exist in the schema. Example:
            "SUM(CASE WHEN status = 'completed' THEN order_total ELSE 0 END)"
        entity_hint: Optional table name that this definition applies to.
            Helps the planner ground the sql_expression to the correct table.
        snapshot_name: Snapshot these definitions apply to. Defaults to "default".

    Returns:
        JSON string with keys:
            term, snapshot_name, definitions_count
    """
    if not term or not term.strip():
        return json.dumps({"error": {"code": -32602, "message": "'term' is required"}})
    if not definition or not definition.strip():
        return json.dumps({"error": {"code": -32602, "message": "'definition' is required"}})

    try:
        count = _definitions.upsert(
            snapshot_name=snapshot_name,
            term=term.strip(),
            definition=definition.strip(),
            sql_expression=sql_expression,
            entity_hint=entity_hint,
        )
    except Exception as e:
        return json.dumps({"error": {"code": -32603, "message": f"Failed to store definition: {e}"}})

    return json.dumps({
        "term": term.strip(),
        "snapshot_name": snapshot_name,
        "definitions_count": count,
    })


@mcp.tool()
def get_schema(
    snapshot_name: str = "default",
) -> str:
    """
    Return the full schema context for a snapshot — entities, fields, joins,
    business definitions, and StructuredFilter documentation.

    **Call this first** when you need to understand a database before generating SQL.
    Read the schema to learn what entities (tables), fields (columns), joins, and
    business definitions are available. Use the StructuredFilter documentation to
    construct a filter for `ask_boyce`.

    If you are an MCP host with your own LLM: read this schema, reason about the
    user's question, construct a StructuredFilter, and pass it to `ask_boyce`.
    No additional credentials or API keys are needed.

    Args:
        snapshot_name: Name of a previously ingested snapshot. Defaults to "default".

    Returns:
        JSON string with keys:

            snapshot_id            — SHA-256 id of the snapshot
            snapshot_name          — logical name
            entities               — list of entity dicts with full field details
            joins                  — list of join dicts with weights
            definitions            — list of business definition dicts (if any)
            structured_filter_docs — complete StructuredFilter format documentation
                                     with examples for constructing an `ask_boyce` call
    """
    # Tier 2: session-start freshness check (sync — only runs once per snapshot per session)
    freshness_warning = _check_snapshot_freshness(snapshot_name)

    try:
        snapshot = _store.load(snapshot_name)
    except FileNotFoundError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})

    # Ensure graph is populated
    if snapshot.snapshot_id not in _graph.snapshots:
        _graph.add_snapshot(snapshot)

    # Build entity details with full field info
    entities_out = []
    for eid, entity in snapshot.entities.items():
        fields_out = []
        for fid in entity.fields:
            field = snapshot.fields.get(fid)
            if field:
                fields_out.append({
                    "field_id": field.id,
                    "name": field.name,
                    "field_type": field.field_type.value,
                    "data_type": field.data_type,
                    "nullable": field.nullable,
                    "primary_key": field.primary_key,
                    "description": field.description,
                    "valid_values": field.valid_values,
                })
        entities_out.append({
            "entity_id": eid,
            "name": entity.name,
            "schema": entity.schema_name,
            "description": entity.description,
            "grain": entity.grain,
            "fields": fields_out,
        })

    # Build join details with weights
    joins_out = []
    for join in snapshot.joins:
        weight = 1.0
        src, tgt = join.source_entity_id, join.target_entity_id
        if src in _graph.graph and tgt in _graph.graph[src] and join.id in _graph.graph[src][tgt]:
            weight = _graph.graph[src][tgt][join.id].get("weight", 1.0)
        joins_out.append({
            "join_id": join.id,
            "source_entity_id": join.source_entity_id,
            "target_entity_id": join.target_entity_id,
            "join_type": join.join_type.value,
            "source_field_id": join.source_field_id,
            "target_field_id": join.target_field_id,
            "weight": weight,
            "description": join.description,
        })

    # Business definitions
    definitions_raw = _definitions.load_all(snapshot_name)
    definitions_out = list(definitions_raw.values()) if definitions_raw else []

    result: Dict[str, Any] = {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_name": snapshot_name,
        "entities": entities_out,
        "joins": joins_out,
        "definitions": definitions_out,
        "structured_filter_docs": _STRUCTURED_FILTER_DOCS,
    }
    if freshness_warning:
        result["freshness_warning"] = freshness_warning
    return json.dumps(result)


async def build_sql(
    structured_filter: dict,
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
    """
    Generate SQL from a StructuredFilter — deterministic, no LLM needed in Boyce.

    This is `ask_boyce` minus the LLM call. The host LLM (Claude, Cursor, etc.)
    reads the schema via `get_schema`, constructs a StructuredFilter, and passes it
    here. Boyce compiles it to SQL deterministically.

    Pipeline: validate filter → kernel.process_request() → NULL trap check →
    EXPLAIN pre-flight → Redshift lint → audit.

    Args:
        structured_filter: A StructuredFilter dict. See `get_schema` output for
            the complete format documentation. All entity_id and field_id values
            must exist in the target snapshot.
        snapshot_name: Name of a previously ingested snapshot. Defaults to "default".
        dialect: Target SQL dialect. Defaults to "redshift".
            Supported: "redshift", "postgres", "duckdb", "bigquery".

    Returns:
        JSON string with the same shape as `ask_boyce`:

            sql               — generated SQL string
            snapshot_id       — SHA-256 id of the snapshot used
            snapshot_name     — logical name of the snapshot
            entities_resolved — list of entity names selected
            validation        — pre-flight result object
            compat_risks      — list of Redshift compatibility warnings (if any)
            warning           — NULL trap warning (if detected)
            null_trap_warnings — per-column trap details (if any)

        On validation error: returns JSON with an "error" key.
    """
    if not structured_filter or not isinstance(structured_filter, dict):
        return json.dumps({
            "error": {"code": -32602, "message": "structured_filter is required and must be a dict"}
        })

    # Load snapshot
    try:
        snapshot = _store.load(snapshot_name)
    except FileNotFoundError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})

    # Ensure graph is populated
    if snapshot.snapshot_id not in _graph.snapshots:
        _graph.add_snapshot(snapshot)

    # Validate filter against snapshot
    validation_errors = _validate_structured_filter(structured_filter, snapshot)
    if validation_errors:
        return json.dumps({
            "error": {
                "code": -32602,
                "message": "StructuredFilter validation failed",
                "data": validation_errors,
            }
        })

    # Run deterministic pipeline
    try:
        payload = await _run_sql_pipeline(
            snapshot, structured_filter, snapshot_name, dialect,
            query_label="[build_sql]",
        )
    except ValueError as e:
        _audit.log_query(
            query="[build_sql]", snapshot_name=snapshot_name,
            snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
            validation_status="unchecked", error=str(e),
        )
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    return json.dumps(payload)


def solve_path(
    source: str,
    target: str,
    snapshot_name: str | None = None,
) -> str:
    """
    Find the optimal semantic join path between two entities and return SQL.

    Args:
        source: Source entity ID or bare name (e.g. "orders" or "entity:orders").
        target: Target entity ID or bare name.
        snapshot_name: If provided, load this snapshot into the graph first.

    Returns:
        JSON string with keys:
            source_entity, target_entity, path_length, semantic_cost, joins, sql
    """
    if not source or not target:
        return json.dumps({
            "error": {
                "code": -32602,
                "message": "Both 'source' and 'target' entity IDs are required",
            }
        })

    src = source if source.startswith("entity:") else f"entity:{source}"
    tgt = target if target.startswith("entity:") else f"entity:{target}"

    if snapshot_name:
        try:
            snap = _store.load(snapshot_name)
            if snap.snapshot_id not in _graph.snapshots:
                _graph.add_snapshot(snap)
        except FileNotFoundError:
            return json.dumps({
                "error": {
                    "code": -32602,
                    "message": f"Snapshot '{snapshot_name}' not found in {_LOCAL_CONTEXT}/",
                }
            })
        except ValueError as e:
            return json.dumps({"error": {"code": -32602, "message": str(e)}})

    try:
        path = _graph.find_path(src, tgt)
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})

    if not path and src == tgt:
        try:
            sql = _graph.generate_join_sql([], src)
        except Exception as e:
            return json.dumps({"error": {"code": -32603, "message": str(e)}})
        return json.dumps({
            "source_entity": src,
            "target_entity": tgt,
            "path_length": 0,
            "semantic_cost": 0.0,
            "joins": [],
            "sql": sql,
        })

    if not path:
        return json.dumps({
            "error": {
                "code": -32603,
                "message": f"No path found between {src} and {tgt}",
            }
        })

    try:
        join_sql = _graph.generate_join_sql(path, src)
    except Exception as e:
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    total_cost = sum(
        _graph.graph[p.source_entity_id][p.target_entity_id][p.id].get("weight", 1.0)
        for p in path
    )
    joins = [
        {
            "id": j.id,
            "source": j.source_entity_id,
            "target": j.target_entity_id,
            "type": j.join_type.value,
            "weight": _graph.graph[j.source_entity_id][j.target_entity_id][j.id].get("weight", 1.0),
        }
        for j in path
    ]

    return json.dumps({
        "source_entity": src,
        "target_entity": tgt,
        "path_length": len(path),
        "semantic_cost": total_cost,
        "joins": joins,
        "sql": join_sql,
    })


@mcp.tool()
async def ask_boyce(
    natural_language_query: str = "",
    structured_filter: Optional[dict] = None,
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
    """
    Generate safe, deterministic SQL from either a natural language question or a
    StructuredFilter.

    **For MCP hosts (Claude, Cursor, Copilot, etc.):** Call `get_schema` first to
    understand the database. Construct a StructuredFilter from the schema and pass
    it here via the `structured_filter` parameter. No additional credentials needed.
    Boyce compiles deterministic SQL and runs safety checks (NULL trap detection,
    EXPLAIN pre-flight, Redshift compatibility lint).

    **For standalone use (CLI, HTTP API):** Pass a `natural_language_query` and
    configure BOYCE_PROVIDER + BOYCE_MODEL environment variables.

    If called with only a natural language query and no LLM credentials are configured,
    returns relevant schema context so you can construct the filter and call back.

    Operates in three modes:

    **Mode A — StructuredFilter provided (zero credentials needed):**
        ask_boyce(structured_filter={...}, snapshot_name="default")
        Skips the planner entirely. Runs deterministic pipeline only.

    **Mode B — NL query with credentials configured:**
        ask_boyce(natural_language_query="revenue by product", snapshot_name="default")
        Runs QueryPlanner (LiteLLM) then deterministic pipeline.

    **Mode C — NL query with no credentials:**
        ask_boyce(natural_language_query="revenue by product", snapshot_name="default")
        Returns schema guidance so the host LLM can construct a StructuredFilter
        and call back. Two round-trips, zero configuration.

    Args:
        natural_language_query: Free-form question. Optional when structured_filter
            is provided. Required for Mode B and C.
        structured_filter: A StructuredFilter dict. See `get_schema` for format
            documentation. When provided, the planner is bypassed entirely.
        snapshot_name: Name of a previously ingested snapshot. Defaults to "default".
        dialect: Target SQL dialect. Defaults to "redshift".
            Supported: "redshift", "postgres", "duckdb", "bigquery".

    Returns:
        Mode A/B — JSON string with keys:
            sql, snapshot_id, snapshot_name, entities_resolved, validation,
            [compat_risks], [warning], [null_trap_warnings]

            The returned SQL does not include ORDER BY or LIMIT. If the user's
            question implies ranking ("top 5", "most expensive", "least common")
            or a row cap, append ORDER BY and LIMIT to the SQL yourself before
            passing it to query_database.

        Mode C — JSON string with keys:
            mode="schema_guidance", message, query, snapshot_name,
            relevant_entities, structured_filter_docs, [definitions_context]

        On error: JSON with "error" key.
    """
    # Must have at least one of the two inputs
    if not structured_filter and not natural_language_query:
        return json.dumps({
            "error": {
                "code": -32602,
                "message": "Provide natural_language_query or structured_filter",
            }
        })

    # Tier 2: session-start freshness check (sync — only runs once per snapshot per session)
    freshness_warning = _check_snapshot_freshness(snapshot_name)

    # Load snapshot
    try:
        snapshot = _store.load(snapshot_name)
    except FileNotFoundError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})

    # Ensure snapshot is in the graph
    if snapshot.snapshot_id not in _graph.snapshots:
        _graph.add_snapshot(snapshot)

    # Tier 3: live DB drift check (async — only runs once per snapshot per session)
    drift_report = await _check_db_drift(snapshot_name)

    # ------------------------------------------------------------------
    # Mode A: StructuredFilter provided — deterministic, no LLM
    # ------------------------------------------------------------------
    if structured_filter is not None:
        if not isinstance(structured_filter, dict):
            return json.dumps({
                "error": {"code": -32602, "message": "structured_filter must be a dict"}
            })

        validation_errors = _validate_structured_filter(structured_filter, snapshot)
        if validation_errors:
            return json.dumps({
                "error": {
                    "code": -32602,
                    "message": "StructuredFilter validation failed",
                    "data": validation_errors,
                }
            })

        try:
            payload = await _run_sql_pipeline(
                snapshot, structured_filter, snapshot_name, dialect,
                query_label=natural_language_query or "[structured_filter]",
            )
        except ValueError as e:
            _audit.log_query(
                query=natural_language_query or "[structured_filter]",
                snapshot_name=snapshot_name,
                snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
                validation_status="unchecked", error=str(e),
            )
            return json.dumps({"error": {"code": -32603, "message": str(e)}})

        if freshness_warning:
            payload["freshness_warning"] = freshness_warning
        if drift_report:
            payload["drift_warning"] = drift_report
        return json.dumps(payload)

    # ------------------------------------------------------------------
    # Modes B and C: NL query path
    # ------------------------------------------------------------------
    definitions_context = _definitions.as_context_string(snapshot_name)
    planner = _get_planner()

    try:
        planned_filter = planner.plan_query(
            natural_language_query, _graph, definitions_context=definitions_context
        )
    except ValueError:
        # Mode C: credentials not configured — return schema guidance for host LLM
        return _build_schema_guidance(natural_language_query, snapshot, snapshot_name)
    except Exception as e:
        # Actual LLM error (bad key, network failure, parse error)
        logger.exception("Unexpected error in plan_query")
        _audit.log_query(
            query=natural_language_query, snapshot_name=snapshot_name,
            snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
            validation_status="unchecked", error=f"Planner error: {e}",
        )
        return json.dumps({"error": {"code": -32603, "message": f"Planner error: {e}"}})

    # Mode B: run deterministic pipeline with planner output
    try:
        payload = await _run_sql_pipeline(
            snapshot, planned_filter, snapshot_name, dialect,
            query_label=natural_language_query,
        )
    except ValueError as e:
        _audit.log_query(
            query=natural_language_query, snapshot_name=snapshot_name,
            snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
            validation_status="unchecked", error=str(e),
        )
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    if freshness_warning:
        payload["freshness_warning"] = freshness_warning
    if drift_report:
        payload["drift_warning"] = drift_report
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# validate_sql helpers
# ---------------------------------------------------------------------------

_EQUALITY_FILTER_RE = re.compile(
    r"(\w+)\.(\w+)\s*=\s*'[^']*'"   # table.column = 'value'
    r"|(\w+)\s*=\s*'[^']*'",         # column = 'value'
    re.IGNORECASE,
)


def _scan_null_risk(sql: str, snapshot_name: str) -> List[Dict[str, Any]]:
    """
    Parse WHERE clause for equality filters and check if those columns
    are nullable in the snapshot.

    This is a lightweight heuristic — not a full SQL parser. It catches
    common patterns like `status = 'active'` and `orders.status = 'active'`.

    Returns list of dicts with keys: table, column, nullable, risk.
    """
    try:
        snapshot = _store.load(snapshot_name)
    except (FileNotFoundError, ValueError):
        return []

    risks = []
    for match in _EQUALITY_FILTER_RE.finditer(sql):
        if match.group(1) and match.group(2):
            table_name: Optional[str] = match.group(1)
            column_name: str = match.group(2)
        elif match.group(3):
            table_name = None
            column_name = match.group(3)
        else:
            continue

        for field in snapshot.fields.values():
            if field.name != column_name:
                continue
            if table_name:
                entity = snapshot.entities.get(field.entity_id)
                if entity and entity.name != table_name:
                    continue
            if field.nullable:
                entity = snapshot.entities.get(field.entity_id)
                entity_name = entity.name if entity else "unknown"
                risks.append({
                    "table": entity_name,
                    "column": column_name,
                    "nullable": True,
                    "risk": (
                        f"Column '{column_name}' is nullable. "
                        f"Equality filter (= 'value') silently excludes NULL rows."
                    ),
                })
            break  # found the column, move on

    return risks


# ---------------------------------------------------------------------------
# validate_sql tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def validate_sql(
    sql: str,
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
    """
    Validate a SQL query through Boyce's safety layer without executing it.

    Use this when you've written SQL directly (without using a StructuredFilter) and
    want to check it before running. Returns:
    - EXPLAIN pre-flight result (verified/invalid/unchecked)
    - Redshift compatibility warnings
    - NULL risk analysis for equality-filtered columns (when parseable from WHERE clause)

    Does NOT execute the query. Use `query_database` to run it after validation.

    Args:
        sql: A SELECT statement to validate.
        snapshot_name: Name of a previously ingested snapshot (used for NULL risk
            analysis — matching WHERE clause columns against snapshot field metadata).
            Defaults to "default".
        dialect: Target SQL dialect for compatibility linting. Defaults to "redshift".
            Supported: "redshift", "postgres", "duckdb", "bigquery".

    Returns:
        JSON string with keys:

            sql               — the SQL as provided (echoed back)
            validation        — pre-flight EXPLAIN result:
                status        — "verified" | "invalid" | "unchecked"
                error         — Postgres error message if invalid, else null
                cost_estimate — planner cost if verified, else null
            compat_risks      — list of Redshift compatibility warnings (if any)
            null_risk_columns — list of columns in WHERE equality filters that are
                                nullable in the snapshot (potential NULL trap risk)
            snapshot_name     — snapshot used for NULL risk analysis
    """
    if not sql or not sql.strip():
        return json.dumps({
            "error": {"code": -32602, "message": "sql is required"}
        })

    logger.info("validate_sql called | sql=%r", sql[:200])

    # Stage 1: Redshift compat lint
    compat_risks = lint_redshift_compat(sql) if dialect == "redshift" else []

    # Stage 2: EXPLAIN pre-flight
    validation = await _preflight_check(sql)

    # Stage 3: Lightweight NULL risk scan
    null_risk_columns = _scan_null_risk(sql, snapshot_name)

    payload: Dict[str, Any] = {
        "sql": sql,
        "validation": validation,
        "snapshot_name": snapshot_name,
    }
    if compat_risks:
        payload["compat_risks"] = compat_risks
    if null_risk_columns:
        payload["null_risk_columns"] = null_risk_columns

    # Audit
    _audit.log_query(
        query="[validate_sql]",
        snapshot_name=snapshot_name,
        snapshot_id="",
        sql=sql,
        entities_resolved=[],
        validation_status=validation["status"],
    )

    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------


async def _get_adapter() -> "DatabaseAdapter":
    """
    Return the module-level adapter, connecting lazily on first call.

    Requires:
        BOYCE_DB_URL env var (asyncpg DSN).
        asyncpg installed:  pip install "boyce[postgres]"

    Raises:
        RuntimeError: If BOYCE_DB_URL is not set or asyncpg is missing.
    """
    global _adapter

    if _adapter is not None:
        return _adapter

    if not _POSTGRES_AVAILABLE:
        raise RuntimeError(
            "asyncpg is not installed. "
            'Install it with: pip install "boyce[postgres]"'
        )

    db_url = os.environ.get("BOYCE_DB_URL", "")
    if not db_url:
        raise RuntimeError(
            "BOYCE_DB_URL environment variable is not set. "
            "Provide an asyncpg DSN, e.g. "
            "postgresql://user:pass@localhost:5432/mydb"
        )

    adapter = PostgresAdapter(db_url)
    await adapter.connect()
    _adapter = adapter
    return _adapter


# ---------------------------------------------------------------------------
# Live database tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def query_database(sql: str, reason: str) -> str:
    """
    Execute a READ-ONLY SQL query against the live database.

    Use this to verify schema assumptions or profile data distribution.
    NOT for creating tables, inserting rows, or any write operation.

    Args:
        sql: A SELECT statement to run against the live database.
            INSERT, UPDATE, DELETE, DDL and other write operations are
            rejected at two levels:
              1. Pre-check: obvious DML/DDL keywords are refused immediately.
              2. readonly transaction: the database refuses any write the
                 pre-check might have missed.
        reason: Brief human-readable explanation of why this query is needed
            (e.g. "verify row count for orders table before building filter").
            Logged for auditability — does not affect query execution.

    Returns:
        JSON string. On success::

            {"rows": [...], "row_count": N, "reason": "..."}

        On error::

            {"error": {"code": -32603, "message": "..."}}

    Requires:
        BOYCE_DB_URL environment variable (asyncpg DSN).
        asyncpg installed: pip install "boyce[postgres]"
    """
    if not sql or not sql.strip():
        return json.dumps({
            "error": {"code": -32602, "message": "sql is required"}
        })

    logger.info("query_database called | reason=%r | sql=%r", reason, sql[:200])

    try:
        adapter = await _get_adapter()
    except RuntimeError as e:
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    try:
        rows = await adapter.execute_query(sql)
    except ValueError as e:
        # Write-operation rejection from the pre-check
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except Exception as e:
        logger.exception("query_database: database error")
        return json.dumps({"error": {"code": -32603, "message": f"Database error: {e}"}})

    return json.dumps({
        "rows": rows,
        "row_count": len(rows),
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# Data profiling tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def profile_data(table: str, column: str) -> str:
    """
    Analyze a specific column in the live database.

    Returns null count, distinct count, min/max values. Use this to understand
    data distribution before writing complex filters.

    Args:
        table: Table name. Accepts bare name (e.g. "orders") or schema-qualified
            (e.g. "public.orders"). Only alphanumeric characters, underscores,
            and dots are allowed — injection attempts are rejected.
        column: Column name (same character restrictions apply).

    Returns:
        JSON string with keys:

            table          — table name as provided
            column         — column name as provided
            row_count      — total rows in the table
            null_count     — rows where column IS NULL
            null_pct       — percentage of nulls (0.0–100.0)
            distinct_count — COUNT(DISTINCT column)
            min_value      — MIN cast to text (lexicographic for non-numeric types)
            max_value      — MAX cast to text

        On error::

            {"error": {"code": -32603, "message": "..."}}

    Requires:
        BOYCE_DB_URL environment variable (asyncpg DSN).
        asyncpg installed: pip install "boyce[postgres]"
    """
    if not table or not column:
        return json.dumps({
            "error": {"code": -32602, "message": "Both 'table' and 'column' are required"}
        })

    logger.info("profile_data called | table=%r | column=%r", table, column)

    try:
        adapter = await _get_adapter()
    except RuntimeError as e:
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    try:
        result = await adapter.profile_column(table, column)
    except ValueError as e:
        # Unsafe identifier
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except Exception as e:
        logger.exception("profile_data: database error")
        return json.dumps({"error": {"code": -32603, "message": f"Database error: {e}"}})

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
