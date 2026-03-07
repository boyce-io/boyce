#!/usr/bin/env python3
"""
Boyce — FastMCP Server

Headless reference implementation. Exposes eight tools:

    ingest_source      — Parse + ingest a snapshot from a dbt manifest, dbt project, or LookML file.
    ingest_definition  — Store a certified business definition; injected into planner at query time.
    get_schema         — Return full schema context + StructuredFilter docs (for host-LLM use).
    build_sql          — StructuredFilter → SQL (deterministic, no LLM needed in Boyce).
    solve_path         — Find the optimal join path between two entities (Dijkstra).
    ask_boyce          — NL → SQL via QueryPlanner + kernel; EXPLAIN pre-flight if DB connected.
    query_database     — Execute a read-only SELECT against the live database.
    profile_data       — Profile a column (null %, distinct count, min/max).

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
Pass one to `build_sql` and Boyce will produce deterministic SQL with no LLM call.

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

### Rules
1. Every `entity_id` and `field_id` must exist in the snapshot returned by `get_schema`.
2. `metrics` require `grain_context.aggregation_required = true`.
3. `join_path` is optional — Boyce resolves joins via Dijkstra if omitted.
4. `dialect` defaults to `"redshift"`. Supported: `"redshift"`, `"postgres"`, `"duckdb"`, `"bigquery"`.
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
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def ingest_source(
    source_path: Optional[str] = None,
    snapshot_json: Optional[dict] = None,
    snapshot_name: str = "default",
) -> str:
    """
    Ingest a SemanticSnapshot from a file path or a pre-built JSON dict.

    Provide exactly one of source_path or snapshot_json.

    Args:
        source_path: Path to a dbt manifest.json, dbt project directory
            (containing dbt_project.yml), or a LookML .lkml file.
            Boyce auto-detects the source type and parses it.
        snapshot_json: A dict conforming to the SemanticSnapshot schema.
            Must include a valid snapshot_id (SHA-256 of canonical content).
            Use this to ingest a pre-built snapshot directly.
        snapshot_name: Logical name used to store / retrieve this snapshot.
            Defaults to "default".

    Returns:
        JSON string with keys:
            snapshot_id, snapshot_name, entities_count, fields_count, joins_count,
            source_type (when parsed from file)
    """
    if source_path is not None:
        try:
            from .parsers import parse_from_path
            snapshot = parse_from_path(source_path)
        except Exception as e:
            return json.dumps({
                "error": {"code": -32602, "message": f"Failed to parse source: {e}"}
            })

        try:
            _store.save(snapshot, snapshot_name)
        except Exception as e:
            return json.dumps({
                "error": {"code": -32603, "message": f"Failed to save snapshot: {e}"}
            })

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
        out_path = _store.save(snapshot, snapshot_name)
    except Exception as e:
        return json.dumps({
            "error": {"code": -32603, "message": f"Failed to save snapshot: {e}"}
        })

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
    Return the full schema context for a snapshot, including StructuredFilter documentation.

    Use this tool to understand what entities, fields, joins, and business definitions
    are available before constructing a StructuredFilter for `build_sql`.

    This is designed for MCP hosts (Claude, Cursor, etc.) whose own LLM can read the
    schema, reason about the user's question, and produce a StructuredFilter directly —
    bypassing Boyce's internal LLM entirely.

    Args:
        snapshot_name: Name of a previously ingested snapshot. Defaults to "default".

    Returns:
        JSON string with keys:

            snapshot_id       — SHA-256 id of the snapshot
            snapshot_name     — logical name
            entities          — list of entity dicts with full field details
            joins             — list of join dicts with weights
            definitions       — list of business definition dicts (if any)
            structured_filter_docs — complete documentation for the StructuredFilter format
    """
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

    return json.dumps({
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_name": snapshot_name,
        "entities": entities_out,
        "joins": joins_out,
        "definitions": definitions_out,
        "structured_filter_docs": _STRUCTURED_FILTER_DOCS,
    })


@mcp.tool()
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


@mcp.tool()
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
    natural_language_query: str,
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
    """
    Generate SQL from a natural language query using a saved snapshot.

    Runs a three-stage pipeline:
      1. QueryPlanner (LiteLLM) — NL → StructuredFilter (grounded to graph).
      2. kernel.process_request  — StructuredFilter → deterministic SQL (no LLM).
      3. Pre-flight check        — EXPLAIN against live DB if BOYCE_DB_URL is set.

    Args:
        natural_language_query: Free-form question (e.g. "revenue by product last 12 months").
        snapshot_name: Name of a previously ingested snapshot to query against.
        dialect: Target SQL dialect. Defaults to "redshift".
            Supported: "redshift", "postgres", "duckdb", "bigquery".

    Returns:
        JSON string with keys:

            sql               — generated SQL string
            snapshot_id       — SHA-256 id of the snapshot used
            snapshot_name     — logical name of the snapshot
            entities_resolved — list of entity names the planner selected
            validation        — pre-flight result object:
                status        — "verified" | "invalid" | "unchecked"
                error         — Postgres error message if invalid, else null
                cost_estimate — planner cost from EXPLAIN if verified, else null
            compat_risks      — list of Redshift compatibility warnings (if any)

            warning           — present only when a NULL trap is detected:
                code          — "NULL_TRAP"
                severity      — "HIGH"
                message       — summary of the hazard
            null_trap_warnings — list of per-column trap dicts (see _null_trap_check);
                                 present only when at least one column exceeds the
                                 null_pct threshold.  Each item has:
                                   table, column, null_pct, null_count, row_count,
                                   filter_operator, filter_value, risk

        On planning/config error: returns JSON with an "error" key.

    Requires env vars for planning:
        BOYCE_PROVIDER  (e.g. "openai")
        BOYCE_MODEL     (e.g. "gpt-4o")
        OPENAI_API_KEY / ANTHROPIC_API_KEY / LITELLM_API_KEY

    Optional env var for pre-flight:
        BOYCE_DB_URL    — asyncpg DSN; omit to skip validation (status: "unchecked")
    """
    if not natural_language_query:
        return json.dumps({
            "error": {"code": -32602, "message": "natural_language_query is required"}
        })

    # Load snapshot
    try:
        snapshot = _store.load(snapshot_name)
    except FileNotFoundError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})

    # Ensure snapshot is in the graph so the planner can traverse it
    if snapshot.snapshot_id not in _graph.snapshots:
        _graph.add_snapshot(snapshot)

    # Stage 1: NL → StructuredFilter via QueryPlanner (LiteLLM)
    # Load certified business definitions and inject into planner context
    definitions_context = _definitions.as_context_string(snapshot_name)

    planner = _get_planner()
    try:
        structured_filter = planner.plan_query(
            natural_language_query, _graph, definitions_context=definitions_context
        )
    except ValueError as e:
        _audit.log_query(
            query=natural_language_query, snapshot_name=snapshot_name,
            snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
            validation_status="unchecked", error=f"Planner error: {e}",
        )
        return json.dumps({"error": {"code": -32603, "message": f"Planner error: {e}"}})
    except Exception as e:
        logger.exception("Unexpected error in plan_query")
        _audit.log_query(
            query=natural_language_query, snapshot_name=snapshot_name,
            snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
            validation_status="unchecked", error=f"Planner error: {e}",
        )
        return json.dumps({"error": {"code": -32603, "message": f"Planner error: {e}"}})

    # Stages 2-4: deterministic SQL pipeline (shared with build_sql)
    try:
        payload = await _run_sql_pipeline(
            snapshot, structured_filter, snapshot_name, dialect,
            query_label=natural_language_query,
        )
    except ValueError as e:
        _audit.log_query(
            query=natural_language_query, snapshot_name=snapshot_name,
            snapshot_id=snapshot.snapshot_id, sql="", entities_resolved=[],
            validation_status="unchecked", error=str(e),
        )
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

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
