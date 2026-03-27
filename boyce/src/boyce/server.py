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
from .connections import ConnectionStore
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
    # Build the set of entity IDs in scope: concept_map.entities + join_path
    entity_ids_in_scope: set = set()
    for ent in entities:
        eid = ent.get("entity_id", "") if isinstance(ent, dict) else ent
        if eid:
            entity_ids_in_scope.add(eid)
    for eid in structured_filter.get("join_path", []):
        entity_ids_in_scope.add(eid)

    valid_ops = {"=", "!=", ">", ">=", "<", "<=", "IN", "NOT IN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL"}
    for filt in concept_map.get("filters", []):
        if not isinstance(filt, dict):
            continue
        fid = filt.get("field_id", "")
        if fid and fid not in snapshot.fields:
            errors.append(f"filter field_id '{fid}' not found in snapshot")
        op = filt.get("operator", "")
        op = _OPERATOR_ALIASES.get(op, op)  # normalise alias variants
        if op and op not in valid_ops:
            errors.append(f"invalid filter operator '{op}'; expected one of {sorted(valid_ops)}")
        fent_id = filt.get("entity_id", "")
        if fent_id and fent_id in snapshot.entities and fent_id not in entity_ids_in_scope:
            errors.append(
                f"filter entity_id '{fent_id}' is not in concept_map.entities or join_path; "
                f"add '{fent_id}' to join_path to filter on this entity"
            )

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

mcp = FastMCP(
    "Boyce",
    json_response=True,
    instructions=(
        "Boyce is a semantic safety layer for database queries. Every query "
        "compiled through ask_boyce is checked for NULL traps (columns that "
        "silently drop rows), execution plan validity, and dialect compatibility. "
        "Start with ask_boyce for any data question."
    ),
)

# Context dir: _local_context/ relative to the working directory at runtime.
_LOCAL_CONTEXT = Path("_local_context")
_store = SnapshotStore(_LOCAL_CONTEXT)
_definitions = DefinitionStore(_LOCAL_CONTEXT)
_connections = ConnectionStore(_LOCAL_CONTEXT)
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
# DSN stored from ingest_source live-DB path; used as fallback when BOYCE_DB_URL is not set.
_ingest_db_url: str = ""
# First-call-per-session flag for environment suggestions.
_environment_checked: bool = False


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
                f"WHERE {column} = {val!r} silently excludes {null_count} NULL rows "
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


def _build_suggested_filter(
    query_words: set,
    top_entities: List[dict],
    snapshot: "SemanticSnapshot",
) -> Optional[dict]:
    """
    Build a candidate StructuredFilter from keyword overlap with entity/field
    names.  Uses simple heuristics — no LLM.  Returns None if no entities match.

    The host LLM can pass this directly to ask_boyce(structured_filter=...)
    or adjust it before calling back.
    """
    if not top_entities:
        return None

    matched_entities = []
    dimensions = []
    metrics = []
    id_field = None

    for ent_dict in top_entities:
        eid = ent_dict["entity_id"]
        entity = snapshot.entities.get(eid)
        if not entity:
            continue
        matched_entities.append({"entity_id": eid, "entity_name": entity.name})

        for fid in entity.fields:
            field = snapshot.fields.get(fid)
            if not field:
                continue
            name_words = set(re.findall(r"\b\w+\b", field.name.lower()))
            if not name_words & query_words:
                continue
            # Classify by field type
            if field.field_type.value == "MEASURE":
                metrics.append({
                    "metric_name": field.name,
                    "field_id": field.id,
                    "aggregation_type": "SUM",
                })
            elif field.field_type.value in ("DIMENSION", "TIMESTAMP"):
                dimensions.append({
                    "field_id": field.id,
                    "field_name": field.name,
                    "entity_id": eid,
                })
            elif field.field_type.value == "ID" and id_field is None:
                id_field = field

    # If no metrics found but we have an ID, suggest COUNT
    if not metrics and id_field:
        metrics.append({
            "metric_name": f"{id_field.name}_count",
            "field_id": id_field.id,
            "aggregation_type": "COUNT",
        })

    if not matched_entities:
        return None

    has_aggregation = bool(metrics)
    grouping_fields = [d["field_id"] for d in dimensions] if has_aggregation else []

    return {
        "concept_map": {
            "entities": matched_entities,
            "fields": [],
            "metrics": metrics,
            "dimensions": dimensions,
            "filters": [],
        },
        "join_path": [e["entity_id"] for e in matched_entities],
        "grain_context": {
            "aggregation_required": has_aggregation,
            "grouping_fields": grouping_fields,
        },
        "policy_context": {"resolved_predicates": []},
        "temporal_filters": [],
        "dialect": "postgres",
    }


def _build_schema_guidance(
    query: str,
    snapshot: "SemanticSnapshot",
    snapshot_name: str,
) -> str:
    """
    Mode C fallback for ask_boyce: return schema context + a suggested
    StructuredFilter so the host LLM can call back immediately.

    Scores entities by keyword overlap with the query (mirrors planner.py:131-138)
    and returns the top-50 most relevant with full field details.  Also constructs
    a candidate StructuredFilter from matched entities/fields — the host LLM can
    relay it directly to ask_boyce(structured_filter=...) without understanding
    the full spec.
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

    # Build a candidate StructuredFilter from keyword-matched entities/fields
    suggested = _build_suggested_filter(query_words, entities_out, snapshot)

    result: dict = {
        "mode": "schema_guidance",
        "message": (
            "Ready-to-use filter constructed from your query.  "
            "Call ask_boyce(structured_filter=ready_filter) to compile "
            "validated SQL with NULL trap detection and EXPLAIN pre-flight.  "
            "No modification needed, no credentials required.  One call."
        ),
        "query": query,
        "snapshot_name": snapshot_name,
        "relevant_entities": entities_out,
        "structured_filter_docs": _STRUCTURED_FILTER_DOCS,
        "definitions_context": definitions_context or None,
    }
    if suggested:
        result["ready_filter"] = suggested
    ad = _build_response_guidance(
        sql=None, snapshot_name=snapshot_name, tool_name="ask_boyce", mode="C",
    )
    result = {**ad, **result}
    return json.dumps(result)


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
        adapter = await _get_adapter(snapshot_name)
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
    Teach Boyce about a database — point it at any schema source and get a semantic snapshot.

    Accepts 10+ formats (DDL, dbt, LookML, SQLite, Django, SQLAlchemy, Prisma,
    CSV, Parquet, live PostgreSQL DSN) — auto-detected from the path. Snapshots
    persist across sessions. Provide exactly one of source_path or snapshot_json.

    **Call this first.** All other tools (ask_boyce, get_schema, validate_sql,
    query_database, profile_data) require a snapshot.

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
                # Store DSN so query_database/profile_data can connect
                # without requiring BOYCE_DB_URL to be set separately.
                global _ingest_db_url
                _ingest_db_url = source_path
                _connections.save(snapshot_name, source_path, source="ingest_source")
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

        ad = _build_response_guidance(
            sql=None, snapshot_name=snapshot_name, tool_name="ingest_source",
        )
        return json.dumps({
            **ad,
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

    ad = _build_response_guidance(
        sql=None, snapshot_name=snapshot_name, tool_name="ingest_source",
    )
    return json.dumps({
        **ad,
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
    Store a certified business definition that Boyce applies automatically at query time.

    Business definitions encode what your data *means* — the logic that lives in
    analysts' heads or scattered across docs but never in the schema. Once stored,
    Boyce injects them into the planner whenever the term appears in a query.

    **Upstream of ask_boyce:** definitions are applied automatically during query
    planning — no extra steps needed after storing them.

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

    ad = _build_response_guidance(
        sql=None, snapshot_name=snapshot_name, tool_name="ingest_definition",
    )
    return json.dumps({
        **ad,
        "term": term.strip(),
        "snapshot_name": snapshot_name,
        "definitions_count": count,
    })


@mcp.tool()
def get_schema(
    snapshot_name: str = "default",
) -> str:
    """
    See what the database actually contains before writing a query.

    Returns full schema context — every table, column, type, nullable flag,
    join path with confidence weight, and certified business definition.
    Without this, your SQL is guessing at column names, types, and
    relationships. Includes StructuredFilter documentation with examples
    so you can construct a validated query for ask_boyce.

    **Upstream of ask_boyce:** construct a StructuredFilter from this schema,
    then pass it to ask_boyce for deterministic, safety-checked SQL.

    Args:
        snapshot_name: Name of a previously ingested snapshot. Defaults to "default".

    Returns:
        JSON string with keys:

            snapshot_id            — SHA-256 id of the snapshot
            snapshot_name          — logical name
            entities               — list of entity dicts with full field details
            joins                  — list of join dicts with confidence weights
            definitions            — list of certified business definitions (if any)
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

    ad = _build_response_guidance(
        sql=None, snapshot_name=snapshot_name, tool_name="get_schema",
    )
    fields_count = sum(len(e["fields"]) for e in entities_out)
    result: Dict[str, Any] = {
        **ad,
        "authority": (
            f"Complete schema: {len(entities_out)} entities, "
            f"{fields_count} fields, {len(joins_out)} joins with confidence "
            f"weights. Reflects full live database as of ingest — no additional "
            f"metadata queries (information_schema, pg_catalog) needed."
        ),
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
    Answer data questions with SQL that has been safety-checked against the
    actual data. Handles counts, totals, averages, rankings, comparisons,
    joins, filters, time series — any question about database tables.

    You can write SQL yourself. But you cannot know that the column you are
    filtering on is 30% NULL and will silently drop rows, or that the join
    you picked was inferred with low confidence and may produce duplicates.
    This tool checks your query against data reality before you run it.

    **Recommended flow:** Call `get_schema` first, construct a StructuredFilter
    from the schema, pass it here. No API keys needed. Boyce compiles
    deterministic SQL and runs NULL trap detection, EXPLAIN pre-flight, and
    compatibility checks.

    If called with a natural language query and no StructuredFilter, Boyce
    returns a ready_filter — call ask_boyce(structured_filter=ready_filter)
    to compile validated SQL. One extra round-trip, zero configuration.

    **MCP host path — StructuredFilter provided (zero credentials, recommended):**
        ask_boyce(structured_filter={...}, snapshot_name="default")
        Deterministic SQL pipeline. No LLM needed.

    **CLI/HTTP path — NL query with LLM credentials configured:**
        ask_boyce(natural_language_query="revenue by product", snapshot_name="default")
        QueryPlanner translates to StructuredFilter, then deterministic pipeline.

    **Schema guidance fallback — NL query without credentials:**
        ask_boyce(natural_language_query="revenue by product", snapshot_name="default")
        Returns a ready_filter — call ask_boyce(structured_filter=ready_filter).
        Two round-trips, zero configuration.

    **Pass the returned SQL to query_database to execute it.**

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

        ad = _build_response_guidance(
            sql=payload.get("sql"),
            snapshot_name=snapshot_name,
            tool_name="ask_boyce",
            validation=payload.get("validation"),
            null_trap_warnings=payload.get("null_trap_warnings"),
            compat_risks=payload.get("compat_risks"),
            mode="A",
        )
        payload = {**ad, **payload}
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
        # Auth errors → Mode C fallback (bad key ≡ no key for the user's purpose)
        err_type = type(e).__name__
        if "Auth" in err_type or "Permission" in err_type:
            logger.warning("LLM credentials invalid — Mode C fallback: %s", e)
            return _build_schema_guidance(natural_language_query, snapshot, snapshot_name)
        # Non-auth errors (network failure, parse error) — hard error
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

    ad = _build_response_guidance(
        sql=payload.get("sql"),
        snapshot_name=snapshot_name,
        tool_name="ask_boyce",
        validation=payload.get("validation"),
        null_trap_warnings=payload.get("null_trap_warnings"),
        compat_risks=payload.get("compat_risks"),
        mode="B",
    )
    payload = {**ad, **payload}
    if freshness_warning:
        payload["freshness_warning"] = freshness_warning
    if drift_report:
        payload["drift_warning"] = drift_report
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Response guidance layer
# ---------------------------------------------------------------------------

# SQL clause patterns for extracting referenced columns
_WHERE_COL_RE = re.compile(
    r"\bWHERE\b(.+?)(?:\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_JOIN_ON_COL_RE = re.compile(
    r"\bON\b\s+\"?(\w+)\"?\.\"?(\w+)\"?\s*=\s*\"?(\w+)\"?\.\"?(\w+)\"?",
    re.IGNORECASE,
)
_GROUP_BY_COL_RE = re.compile(
    r"\bGROUP\s+BY\b\s+(.+?)(?:\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_COL_REF_RE = re.compile(r"\"?(\w+)\"?\.\"?(\w+)\"?")
_BARE_COL_RE = re.compile(r"\b([a-zA-Z_]\w*)\b")
_FROM_TABLE_RE = re.compile(
    r"\bFROM\b\s+\"?(\w+)\"?(?:\s+(?:AS\s+)?\"?(\w+)\"?)?",
    re.IGNORECASE,
)
_JOIN_TABLE_RE = re.compile(
    r"\bJOIN\b\s+\"?(\w+)\"?(?:\s+(?:AS\s+)?\"?(\w+)\"?)?",
    re.IGNORECASE,
)
# SQL keywords to exclude from bare-column matching
_SQL_KEYWORDS = frozenset({
    "select", "from", "where", "and", "or", "not", "in", "is", "null",
    "like", "ilike", "between", "exists", "case", "when", "then", "else",
    "end", "as", "on", "join", "inner", "left", "right", "full", "outer",
    "cross", "group", "by", "order", "asc", "desc", "limit", "offset",
    "having", "union", "all", "distinct", "count", "sum", "avg", "min",
    "max", "true", "false", "cast", "coalesce", "nullif",
})


def _extract_from_tables(sql: str) -> Dict[str, str]:
    """
    Extract table names from FROM and JOIN clauses.

    Returns dict mapping alias (or table name if no alias) → real table name.
    E.g. ``FROM films f`` → ``{"f": "films", "films": "films"}``.
    """
    tables: Dict[str, str] = {}
    for pattern in (_FROM_TABLE_RE, _JOIN_TABLE_RE):
        for m in pattern.finditer(sql):
            real_name = m.group(1)
            alias = m.group(2)
            tables[real_name] = real_name
            if alias:
                tables[alias] = real_name
    return tables


def _extract_referenced_columns(sql: str) -> Dict[str, str]:
    """
    Extract columns referenced in WHERE, JOIN ON, and GROUP BY clauses.

    Returns dict keyed by "table.column" → clause type ("WHERE", "JOIN ON",
    "GROUP BY").  Handles both qualified (``table.column``) and bare
    (``column``) references.  Bare names are keyed as ``"?.column"`` — the
    caller is responsible for resolving them against a snapshot.

    Lightweight heuristic — not a full SQL parser.
    """
    refs: Dict[str, str] = {}
    # Resolve aliases: map alias → real table name
    table_map = _extract_from_tables(sql)

    def _add_qualified(table: str, col: str, clause: str) -> None:
        real = table_map.get(table, table)
        refs.setdefault(f"{real}.{col}", clause)

    def _add_bare(col: str, clause: str) -> None:
        if col.lower() in _SQL_KEYWORDS:
            return
        refs.setdefault(f"?.{col}", clause)

    def _extract_from_body(body: str, clause: str) -> None:
        """Extract both qualified and bare column refs from a clause body."""
        # First pass: find all qualified refs (table.column)
        qualified_cols: set = set()
        for m in _COL_REF_RE.finditer(body):
            _add_qualified(m.group(1), m.group(2), clause)
            qualified_cols.add(m.group(2))
            qualified_cols.add(m.group(1))  # table name, not a bare col
        # Second pass: find bare column names not already captured
        for m in _BARE_COL_RE.finditer(body):
            word = m.group(1)
            if word not in qualified_cols:
                _add_bare(word, clause)

    # WHERE clause
    where_match = _WHERE_COL_RE.search(sql)
    if where_match:
        _extract_from_body(where_match.group(1), "WHERE")

    # JOIN ON columns (qualified only — ON clauses are almost always table.col)
    for m in _JOIN_ON_COL_RE.finditer(sql):
        _add_qualified(m.group(1), m.group(2), "JOIN ON")
        _add_qualified(m.group(3), m.group(4), "JOIN ON")

    # GROUP BY clause
    gb_match = _GROUP_BY_COL_RE.search(sql)
    if gb_match:
        _extract_from_body(gb_match.group(1), "GROUP BY")

    return refs


def _check_environment_suggestions() -> List[str]:
    """
    Lightweight first-call-per-session environment check.

    Returns a list of actionable suggestion strings (max 3).
    Only runs once per server process — subsequent calls return empty.
    """
    global _environment_checked
    if _environment_checked:
        return []
    _environment_checked = True

    suggestions: List[str] = []

    # 0. Version lifecycle checks (highest priority)
    try:
        from .version_check import get_version_info  # noqa: PLC0415

        vi = get_version_info(_LOCAL_CONTEXT)

        # Stale process — highest priority
        if vi.get("restart_required"):
            suggestions.append(
                f"Boyce was upgraded to {vi['installed']} but the running "
                f"server is still {vi['running']}. Restart your editor."
            )
        # Update available (minor/major only, respect cooldown)
        elif (
            vi.get("update_available")
            and vi.get("update_type") in ("major", "minor")
            and not vi.get("cooldown_active")
        ):
            suggestions.append(
                f"Boyce {vi['latest']} available — run `boyce update` to upgrade."
            )
    except Exception:
        pass  # Non-fatal

    # 1. Check if environment.json exists and is recent
    env_path = _LOCAL_CONTEXT / "environment.json"
    if env_path.exists():
        try:
            import json as _json
            from datetime import datetime as _dt, timezone as _tz
            with open(env_path) as f:
                env_data = _json.load(f)
            last_doctor = env_data.get("last_doctor", "")
            if last_doctor:
                dt = _dt.fromisoformat(last_doctor)
                age_hours = (_dt.now(_tz.utc) - dt).total_seconds() / 3600
                if age_hours > 24:
                    suggestions.append(
                        "Run `boyce doctor` to check environment health "
                        f"(last run {age_hours:.0f}h ago)."
                    )
        except Exception:
            pass
    elif _LOCAL_CONTEXT.exists():
        # Has snapshots but never ran doctor
        suggestions.append(
            "Run `boyce doctor` to check environment health."
        )

    # 2. Quick snapshot staleness check
    if _LOCAL_CONTEXT.exists():
        from datetime import datetime as _dt2, timezone as _tz2
        for path in _LOCAL_CONTEXT.glob("*.json"):
            if path.name in ("connections.json", "environment.json", "version_check.json") or \
                    path.name.endswith(".definitions.json"):
                continue
            mtime = _dt2.fromtimestamp(path.stat().st_mtime, tz=_tz2.utc)
            age_hours = (_dt2.now(_tz2.utc) - mtime).total_seconds() / 3600
            if age_hours > 168:  # 7 days
                suggestions.append(
                    f"Snapshot '{path.stem}' is {age_hours / 24:.0f} days old. "
                    f"Call ingest_source to refresh."
                )
                break  # Only flag the first stale snapshot

    return suggestions[:3]  # Noise fatigue protection


def _build_response_guidance(
    sql: Optional[str],
    snapshot_name: str,
    tool_name: str,
    validation: Optional[dict] = None,
    null_risk: Optional[List[Dict[str, Any]]] = None,
    mode: Optional[str] = None,
    compat_risks: Optional[list] = None,
    null_trap_warnings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build response guidance: present_to_user, data_reality, next_step.

    Every successful tool response merges this dict ABOVE its primary payload
    so the consuming model reads the guidance fields first.
    """
    present_to_user: Optional[str] = None
    data_reality: Optional[Dict[str, Any]] = None
    next_step: str = ""

    # --- present_to_user: loss-aversion framing, only when material ---
    messages: List[str] = []

    # NULL risk from _scan_null_risk (query_database, validate_sql)
    if null_risk:
        cols = ", ".join(f"`{r['column']}`" for r in null_risk)
        messages.append(
            f"Nullable column(s) {cols} in equality filter — rows with NULL "
            f"values are silently excluded. Resubmit through ask_boyce for "
            f"automatic NULL handling."
        )

    # NULL trap warnings from _null_trap_check (ask_boyce pipeline)
    if null_trap_warnings:
        for w in null_trap_warnings:
            pct = w.get("null_pct", 0)
            col = w.get("column", "?")
            tbl = w.get("table", "?")
            messages.append(
                f"`{tbl}.{col}` is {pct:.0f}% NULL — equality filter excludes "
                f"those rows silently."
            )

    # EXPLAIN issues
    if validation and validation.get("status") == "invalid":
        err = validation.get("error", "unknown error")
        messages.append(
            f"EXPLAIN pre-flight failed: {err}. ask_boyce generates "
            f"validated SQL that passes EXPLAIN."
        )

    # Compat risks
    if compat_risks:
        messages.append(
            f"{len(compat_risks)} Redshift compatibility issue(s) detected. "
            f"ask_boyce generates dialect-safe SQL."
        )

    # NOTE: present_to_user is assembled after data_reality, because the
    # nullable-sibling-FK check below may append additional messages.

    # --- data_reality: gift pattern, snapshot-based metadata only ---
    if sql:
        raw_refs = _extract_referenced_columns(sql)
        if raw_refs:
            try:
                snapshot = _store.load(snapshot_name)

                # Resolve bare "?.column" refs against FROM tables + snapshot
                from_tables = _extract_from_tables(sql)
                real_table_names = set(from_tables.values())
                refs: Dict[str, str] = {}
                for ref_key, clause in raw_refs.items():
                    if ref_key.startswith("?."):
                        # Bare column — resolve against snapshot fields in FROM tables
                        col_name = ref_key[2:]
                        matches = []
                        for field in snapshot.fields.values():
                            if field.name != col_name:
                                continue
                            entity = snapshot.entities.get(field.entity_id)
                            if entity and entity.name in real_table_names:
                                matches.append(entity.name)
                        if len(matches) == 1:
                            refs.setdefault(f"{matches[0]}.{col_name}", clause)
                        # Ambiguous (>1) or unresolvable (0) — skip
                    else:
                        refs[ref_key] = clause

                reality: Dict[str, Any] = {}
                for ref_key, clause in refs.items():
                    parts = ref_key.split(".", 1)
                    if len(parts) != 2:
                        continue
                    table_name, col_name = parts
                    # Find field in snapshot
                    for field in snapshot.fields.values():
                        if field.name != col_name:
                            continue
                        entity = snapshot.entities.get(field.entity_id)
                        if entity and entity.name != table_name:
                            continue
                        # Build insight based on context
                        insight_parts: List[str] = []
                        if field.nullable and clause == "WHERE":
                            insight_parts.append(
                                "Nullable column in WHERE — NULL rows excluded by equality filters."
                            )
                        elif field.nullable and clause == "GROUP BY":
                            insight_parts.append(
                                "Nullable column in GROUP BY — NULLs form a separate group or are excluded."
                            )
                        elif field.nullable and clause == "JOIN ON":
                            insight_parts.append(
                                "Nullable column in JOIN — NULL keys never match, dropping rows."
                            )
                        elif not field.nullable:
                            # Non-nullable in a critical clause — safe, skip unless join
                            if clause == "JOIN ON":
                                insight_parts.append("Non-nullable. Join key is safe.")
                            else:
                                break  # No material insight — omit
                        if insight_parts:
                            reality[ref_key] = {
                                "nullable": field.nullable,
                                "used_in": clause,
                                "insight": " ".join(insight_parts),
                            }
                        break

                # Add join confidence for JOIN ON columns
                for ref_key, clause in refs.items():
                    if clause != "JOIN ON" or ref_key not in reality:
                        continue
                    parts = ref_key.split(".", 1)
                    if len(parts) != 2:
                        continue
                    # Check graph for join weight
                    for join in snapshot.joins:
                        src_entity = snapshot.entities.get(join.source_entity_id)
                        tgt_entity = snapshot.entities.get(join.target_entity_id)
                        if not src_entity or not tgt_entity:
                            continue
                        src_field = snapshot.fields.get(join.source_field_id)
                        tgt_field = snapshot.fields.get(join.target_field_id)
                        if not src_field or not tgt_field:
                            continue
                        if (src_entity.name == parts[0] and src_field.name == parts[1]) or \
                           (tgt_entity.name == parts[0] and tgt_field.name == parts[1]):
                            weight = 1.0
                            if join.source_entity_id in _graph.graph and \
                               join.target_entity_id in _graph.graph[join.source_entity_id] and \
                               join.id in _graph.graph[join.source_entity_id][join.target_entity_id]:
                                weight = _graph.graph[join.source_entity_id][join.target_entity_id][join.id].get("weight", 1.0)
                            confidence_label = (
                                "explicit relationship" if weight <= 0.5
                                else "foreign key" if weight <= 1.0
                                else "inferred by name match — verify before production use" if weight <= 2.0
                                else "many-to-many — high duplication risk"
                            )
                            reality[ref_key]["join_confidence"] = weight
                            reality[ref_key]["insight"] += f" Confidence: {weight} ({confidence_label})."
                            break

                if reality:
                    data_reality = reality
            except (FileNotFoundError, ValueError):
                pass  # No snapshot available — skip data_reality

    # --- Nullable sibling FK detection ---
    # When SQL joins entity A → B, warn about OTHER nullable FK columns
    # from A → B that aren't in the SQL. Catches the "original_language_id
    # is 100% NULL" scenario even when the model bypasses ask_boyce.
    if sql and tool_name in ("query_database", "validate_sql"):
        try:
            snapshot = _store.load(snapshot_name)
            from_tables = _extract_from_tables(sql)
            real_table_names = set(from_tables.values())
            all_refs = _extract_referenced_columns(sql)
            # Columns actually referenced in the SQL (fully qualified)
            cols_in_sql = set()
            for ref_key in all_refs:
                if not ref_key.startswith("?."):
                    cols_in_sql.add(ref_key)
            # Also resolve bare refs
            for ref_key in all_refs:
                if ref_key.startswith("?."):
                    col_name = ref_key[2:]
                    for field in snapshot.fields.values():
                        if field.name != col_name:
                            continue
                        entity = snapshot.entities.get(field.entity_id)
                        if entity and entity.name in real_table_names:
                            cols_in_sql.add(f"{entity.name}.{col_name}")

            for join_def in snapshot.joins:
                src_entity = snapshot.entities.get(join_def.source_entity_id)
                tgt_entity = snapshot.entities.get(join_def.target_entity_id)
                if not src_entity or not tgt_entity:
                    continue
                # Both entities must be in the FROM clause
                if src_entity.name not in real_table_names or \
                   tgt_entity.name not in real_table_names:
                    continue
                src_field = snapshot.fields.get(join_def.source_field_id)
                if not src_field:
                    continue
                ref_key = f"{src_entity.name}.{src_field.name}"
                if src_field.nullable and ref_key not in cols_in_sql:
                    messages.append(
                        f"`{src_entity.name}.{src_field.name}` is also a "
                        f"join key to `{tgt_entity.name}` but is nullable — "
                        f"queries joining or filtering on it risk silently "
                        f"dropping rows. Use ask_boyce for safe join-path "
                        f"selection."
                    )
        except (FileNotFoundError, ValueError):
            pass

    if messages:
        present_to_user = " ".join(messages)

    # --- next_step: directive language, always present ---
    next_step_map: Dict[str, str] = {
        "ingest_source": (
            f"Snapshot '{snapshot_name}' is ready. Use get_schema to explore "
            f"tables, or ask_boyce with a natural language question to query immediately."
        ),
        "ingest_definition": (
            "Definition stored. ask_boyce will apply it automatically — "
            "no additional steps needed."
        ),
        "get_schema": (
            "Use this schema to construct a StructuredFilter for ask_boyce. "
            "Specify table, columns, and conditions."
        ),
        "ask_boyce_success": (
            "Pass the SQL above to query_database to execute it."
        ),
        "ask_boyce_mode_c": (
            "Call ask_boyce(structured_filter=ready_filter) now. "
            "The filter is complete — pass it directly, no changes needed."
        ),
        "validate_sql_clean": (
            "SQL passed all checks. Pass to query_database to execute."
        ),
        "validate_sql_issues": (
            "Issues detected. Resubmit the original question through ask_boyce "
            "for automatic remediation, or fix manually and re-validate."
        ),
        "query_database_clean": (
            "Query complete. Use profile_data on any column to inspect "
            "distributions before building downstream logic."
        ),
        "query_database_null_risk": (
            "Results may be incomplete — see present_to_user. Resubmit through "
            "ask_boyce for NULL-safe compilation."
        ),
        "profile_data": (
            "Use these distributions to inform your next ask_boyce query "
            "or validate assumptions before joining."
        ),
    }

    # Resolve tool_name to the right next_step key
    if tool_name == "ask_boyce":
        if mode == "C":
            next_step = next_step_map["ask_boyce_mode_c"]
        else:
            next_step = next_step_map["ask_boyce_success"]
    elif tool_name == "validate_sql":
        has_issues = bool(null_risk) or bool(compat_risks) or (
            validation and validation.get("status") == "invalid"
        )
        next_step = next_step_map["validate_sql_issues" if has_issues else "validate_sql_clean"]
    elif tool_name == "query_database":
        has_risk = bool(null_risk)
        next_step = next_step_map["query_database_null_risk" if has_risk else "query_database_clean"]
    else:
        next_step = next_step_map.get(tool_name, "")

    result: Dict[str, Any] = {
        "next_step": next_step,
    }
    if present_to_user is not None:
        result["present_to_user"] = present_to_user
    if data_reality is not None:
        result["data_reality"] = data_reality

    # Environment suggestions — first call per session only
    env_suggestions = _check_environment_suggestions()
    if env_suggestions:
        result["environment_suggestions"] = env_suggestions

    # Graceful self-termination after upgrade (gated behind env var).
    # If the MCP host does not auto-respawn stdio servers, the user will
    # lose Boyce until they manually restart.  Default: off.
    if os.environ.get("BOYCE_AUTO_RESTART_ON_UPDATE"):
        try:
            from .version_check import check_running_vs_installed  # noqa: PLC0415

            rv = check_running_vs_installed()
            if rv["restart_required"]:
                import threading

                def _delayed_exit() -> None:
                    import time
                    time.sleep(0.5)
                    sys.exit(0)

                threading.Thread(target=_delayed_exit, daemon=True).start()
        except Exception:
            pass

    return result


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
    Check SQL against data reality before running it. If you wrote SQL yourself
    — or want to verify SQL from any source — this catches three classes of
    problems invisible to schema inspection alone:

    1. **NULL traps:** Columns in WHERE clauses that are mostly NULL. Rows
       silently vanish from results with no error.
    2. **Broken execution plans:** SQL that parses fine but fails EXPLAIN
       pre-flight — the database cannot execute it as written.
    3. **Dialect traps:** Redshift compatibility issues (CONCAT, STRING_AGG,
       RECURSIVE CTEs) that work on Postgres but fail on Redshift.

    Does NOT execute the query. **Use this before passing hand-written SQL to
    query_database** — it is the safety gate for SQL that did not come through
    ask_boyce.

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

    ad = _build_response_guidance(
        sql=sql,
        snapshot_name=snapshot_name,
        tool_name="validate_sql",
        validation=validation,
        null_risk=null_risk_columns or None,
        compat_risks=compat_risks or None,
    )
    payload: Dict[str, Any] = {
        **ad,
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


async def _get_adapter(snapshot_name: str = "default") -> "DatabaseAdapter":
    """
    Return the module-level adapter, connecting lazily on first call.

    DSN resolution order:
        1. BOYCE_DB_URL env var
        2. In-memory _ingest_db_url (set during current session by ingest_source)
        3. Persistent _connections store (survives server restarts)

    Raises:
        RuntimeError: If no DSN is available or asyncpg is missing.
    """
    global _adapter

    if _adapter is not None:
        return _adapter

    if not _POSTGRES_AVAILABLE:
        raise RuntimeError(
            "asyncpg is not installed. "
            'Install it with: pip install "boyce[postgres]"'
        )

    db_url = (
        os.environ.get("BOYCE_DB_URL", "")
        or _ingest_db_url
        or _connections.load(snapshot_name)
        or ""
    )
    if not db_url:
        raise RuntimeError(
            "No database connection available. "
            "Call check_health to diagnose, or call ingest_source "
            "with a PostgreSQL DSN to connect."
        )

    adapter = PostgresAdapter(db_url)
    await adapter.connect()
    _adapter = adapter
    _connections.touch(snapshot_name)
    return _adapter


# ---------------------------------------------------------------------------
# Live database tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def query_database(
    sql: str,
    reason: str,
    snapshot_name: str = "default",
) -> str:
    """
    Run SQL against the live database — read-only, with safety pre-flight.

    Every query is scanned for NULL traps and validated via EXPLAIN before
    execution. Write operations are rejected at two levels: keyword pre-check
    and a read-only transaction guard.

    **Downstream of ask_boyce:** use this to execute SQL generated by ask_boyce.
    For hand-written SQL, run validate_sql first to catch problems before they
    reach the database.

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
        snapshot_name: Snapshot used for NULL risk analysis (matching WHERE
            clause columns against snapshot field metadata). Defaults to "default".

    Returns:
        JSON string. On success::

            {"rows": [...], "row_count": N, "reason": "...",
             "validation": {...}, "null_risk_columns": [...]}

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
        adapter = await _get_adapter(snapshot_name)
    except RuntimeError as e:
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    # Safety pre-flight: NULL risk scan (snapshot-based, lightweight)
    null_risk_columns = _scan_null_risk(sql, snapshot_name)

    # Live NULL trap profiling for equality-filtered nullable columns.
    # Reuses the adapter we already connected to. Caps at 3 columns to
    # bound latency.  Non-fatal — never blocks query execution.
    live_null_warnings: List[Dict[str, Any]] = []
    if null_risk_columns:
        try:
            for risk in null_risk_columns[:3]:
                table_name = risk.get("table", "")
                column_name = risk.get("column", "")
                if not table_name or not column_name:
                    continue
                profile = await adapter.profile_column(table_name, column_name)
                null_pct = profile.get("null_pct", 0.0)
                if null_pct > _NULL_TRAP_THRESHOLD_PCT:
                    live_null_warnings.append({
                        "table": table_name,
                        "column": column_name,
                        "null_pct": null_pct,
                        "null_count": profile.get("null_count", "?"),
                        "row_count": profile.get("row_count", "?"),
                        "risk": (
                            f"WHERE {column_name} = '...' silently excludes "
                            f"{profile.get('null_count', '?')} NULL rows "
                            f"({null_pct:.1f}% of {table_name}). "
                            f"Those rows vanish without warning."
                        ),
                    })
        except Exception:
            pass  # Non-fatal — never block query execution on a failed profile

    # Safety pre-flight: EXPLAIN validation
    validation = await _preflight_check(sql)
    if validation["status"] == "invalid":
        ad = _build_response_guidance(
            sql=sql, snapshot_name=snapshot_name, tool_name="query_database",
            validation=validation, null_risk=null_risk_columns or None,
            null_trap_warnings=live_null_warnings or None,
        )
        payload: Dict[str, Any] = {
            **ad,
            "error": {
                "code": -32602,
                "message": f"EXPLAIN pre-flight failed: {validation['error']}",
            },
            "validation": validation,
        }
        if null_risk_columns:
            payload["null_risk_columns"] = null_risk_columns
        if live_null_warnings:
            payload["null_trap_warnings"] = live_null_warnings
        return json.dumps(payload)

    try:
        rows = await adapter.execute_query(sql)
    except ValueError as e:
        # Write-operation rejection from the pre-check
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except Exception as e:
        logger.exception("query_database: database error")
        return json.dumps({"error": {"code": -32603, "message": f"Database error: {e}"}})

    ad = _build_response_guidance(
        sql=sql, snapshot_name=snapshot_name, tool_name="query_database",
        validation=validation, null_risk=null_risk_columns or None,
        null_trap_warnings=live_null_warnings or None,
    )

    # Detect metadata table queries — model is duplicating get_schema work
    sql_lower = sql.lower()
    if "information_schema" in sql_lower or "pg_catalog" in sql_lower:
        metadata_note = (
            "get_schema already provides this metadata enriched with "
            "join confidence weights, NULL risk flags, and certified "
            "business definitions that information_schema does not contain."
        )
        if ad.get("present_to_user"):
            ad["present_to_user"] += " " + metadata_note
        else:
            ad["present_to_user"] = metadata_note

    result: Dict[str, Any] = {
        **ad,
        "rows": rows,
        "row_count": len(rows),
        "reason": reason,
        "validation": validation,
    }
    if null_risk_columns:
        result["null_risk_columns"] = null_risk_columns
    if live_null_warnings:
        result["null_trap_warnings"] = live_null_warnings

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Data profiling tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def profile_data(table: str, column: str) -> str:
    """
    See how a column actually behaves — null rate, distinct count, min/max.

    Use this before filtering or joining on a column to know whether it will
    do what you expect. A column named "status" might be 40% NULL. A column
    named "email" might have 3 distinct values. The schema tells you types.
    This tells you truth.

    **Inspect before filtering or joining.** Complements get_schema (structure)
    with real data distributions.

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

    ad = _build_response_guidance(
        sql=None, snapshot_name="default", tool_name="profile_data",
    )
    return json.dumps({**ad, **result})


# ---------------------------------------------------------------------------
# MCP tool: check_health
# ---------------------------------------------------------------------------


@mcp.tool()
async def check_health(snapshot_name: str = "default") -> str:
    """
    Check Boyce's operational health — database connectivity, snapshot
    freshness, and schema drift.

    Call this when a query fails unexpectedly, when you suspect stale
    data, or when Boyce suggests running a health check.  Returns
    actionable diagnostics with specific fix commands.

    **Use this before debugging query failures yourself.** A failed
    EXPLAIN or missing table often means the snapshot is stale, not
    that your SQL is wrong.

    Args:
        snapshot_name: Snapshot to check health for.  Defaults to "default".

    Returns:
        JSON with status ("ok" | "warnings" | "errors"), database
        connectivity, snapshot freshness, server health, and a
        suggestions list with fix commands.
    """
    from .doctor import check_database, check_server, check_snapshots

    db_result = await check_database(_LOCAL_CONTEXT)
    snap_result = check_snapshots(_LOCAL_CONTEXT)
    server_result = check_server(_LOCAL_CONTEXT)

    # Aggregate suggestions
    suggestions: List[str] = []
    for check in (db_result, snap_result, server_result):
        for item in check.get("items", []):
            fix = item.get("fix")
            if fix:
                suggestions.append(fix)

    # Overall status
    statuses = [db_result.get("status", "ok"), snap_result.get("status", "ok"),
                server_result.get("status", "ok")]
    if "error" in statuses:
        status = "errors"
    elif "warning" in statuses:
        status = "warnings"
    else:
        status = "ok"

    # Build response guidance
    ad: Dict[str, Any] = {}
    if suggestions:
        ad["next_step"] = f"Fix the most critical issue: {suggestions[0]}"
        ad["present_to_user"] = (
            f"Boyce health check found {len(suggestions)} issue(s). "
            f"Most critical: {suggestions[0]}"
        )
    else:
        ad["next_step"] = (
            "Environment is healthy. Use get_schema to explore tables, "
            "or ask_boyce with a natural language question."
        )

    # Version info
    version_info: Dict[str, Any] = {}
    try:
        from .version_check import get_version_info  # noqa: PLC0415

        vi = get_version_info(_LOCAL_CONTEXT)
        version_info = {
            "current": vi.get("current"),
            "latest": vi.get("latest"),
            "installed": vi.get("installed"),
            "update_available": vi.get("update_available", False),
            "restart_required": vi.get("restart_required", False),
        }
        if vi.get("restart_required"):
            suggestions.insert(0,
                f"Restart editor (running {vi['running']}, "
                f"installed {vi['installed']})",
            )
        elif vi.get("update_available"):
            suggestions.append(
                f"Boyce {vi['latest']} available — run `boyce update`",
            )
    except Exception:
        pass

    result = {
        **ad,
        "status": status,
        "version": version_info,
        "database": db_result,
        "snapshot": snap_result,
        "server": server_result,
        "suggestions": suggestions,
    }
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
