"""
Profiler — Live Database Profiling Engine

Takes a PostgresAdapter (live DB connection) and an existing SemanticSnapshot.
Queries the database to enrich the snapshot with profiling data:
  - Row counts per entity
  - NULL rates per column
  - Low-cardinality enum detection (sample_values when distinct_count <= threshold)
  - Object type detection via information_schema.tables
  - FK confidence + orphan rates per join

Returns a NEW SemanticSnapshot with profiling fields populated.
Does NOT mutate the input snapshot. The snapshot_id is preserved — profiling
fields are excluded from the hash via canonicalize_snapshot_for_hash(), so
structural identity is unchanged across profile runs.

What it does NOT do (deferred):
  - View SQL parsing / lineage (requires SQL parser)
  - Cross-table column similarity detection (Sprint 3+)
  - Any LLM interaction (that's enrich_snapshot, Sprint 3)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from .parsers.base import build_snapshot
from .types import Entity, FieldDef, JoinDef, SemanticSnapshot

logger = logging.getLogger(__name__)

# Identifier safety pattern — matches table and column names safe for quoting.
# Same pattern as PostgresAdapter._SAFE_IDENT_PATTERN.
_SAFE_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# information_schema table_type → profiling object_type mapping
_TABLE_TYPE_MAP: Dict[str, str] = {
    "BASE TABLE": "table",
    "VIEW": "view",
    "FOREIGN": "external_table",
    "FOREIGN TABLE": "external_table",
    "MATERIALIZED VIEW": "materialized_view",
}


def _safe_quote(name: str) -> str:
    """
    Return a double-quoted SQL identifier for a simple (non-schema-qualified) name.

    Validates that the name contains only alphanumeric characters and underscores
    to prevent SQL injection. Raises ValueError for unsafe names.
    """
    if not _SAFE_IDENT.match(name):
        raise ValueError(
            f"Unsafe identifier: {name!r}. "
            "Only alphanumeric characters and underscores are allowed."
        )
    return f'"{name}"'


def _table_ref(entity: Entity) -> str:
    """
    Return the fully-qualified, double-quoted table reference for an entity.
    Uses schema_name if set, otherwise bare table name.
    """
    if entity.schema_name:
        return f"{_safe_quote(entity.schema_name)}.{_safe_quote(entity.name)}"
    return _safe_quote(entity.name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def profile_snapshot(
    adapter: Any,
    snapshot: SemanticSnapshot,
    enum_threshold: int = 25,
) -> SemanticSnapshot:
    """
    Profile a live database and return an enriched SemanticSnapshot.

    Queries the database to populate profiling fields on all entities, fields,
    and joins in the snapshot. The snapshot_id is preserved — profiling fields
    are excluded from the structural hash.

    Args:
        adapter: Connected PostgresAdapter instance.
        snapshot: The SemanticSnapshot to enrich. Not mutated.
        enum_threshold: Columns with distinct_count <= this value get
            their distinct values stored in sample_values. Default: 25.

    Returns:
        New SemanticSnapshot with profiling fields populated and profiled_at set.

    Raises:
        RuntimeError: If the adapter is not connected.
    """
    logger.info(
        "Profiler: starting snapshot '%s' (%d entities, %d fields, %d joins)",
        snapshot.snapshot_id[:12],
        len(snapshot.entities),
        len(snapshot.fields),
        len(snapshot.joins),
    )

    # Step 1: Object types — one batch query for all tables
    object_types = await _fetch_object_types(adapter)
    logger.info("Profiler: fetched %d object type entries", len(object_types))

    # Step 2: Per-entity profiling (row counts + column stats) — parallel
    entity_profiles = await _profile_all_entities(
        adapter, snapshot, enum_threshold
    )
    logger.info("Profiler: profiled %d entities", len(entity_profiles))

    # Step 3: Per-join FK confidence — parallel
    join_profiles = await _profile_all_joins(adapter, snapshot)
    logger.info("Profiler: profiled %d joins", len(join_profiles))

    # Step 4: Assemble enriched models
    enriched_entities, enriched_fields = _apply_entity_profiles(
        snapshot, entity_profiles, object_types
    )
    enriched_joins = _apply_join_profiles(snapshot, join_profiles)

    # Step 5: Build new snapshot (same hash, profiling fields ignored by canonicalizer)
    new_snapshot = build_snapshot(
        source_system=snapshot.source_system,
        source_version=snapshot.source_version or "",
        entities=enriched_entities,
        fields=enriched_fields,
        joins=enriched_joins,
        metadata=dict(snapshot.metadata),
    )

    # Step 6: Stamp profiled_at timestamp (profiling fields are frozen — use model_copy)
    profiled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_snapshot = new_snapshot.model_copy(update={"profiled_at": profiled_at})

    logger.info(
        "Profiler: complete. snapshot_id=%s profiled_at=%s",
        new_snapshot.snapshot_id[:12],
        profiled_at,
    )
    return new_snapshot


# ---------------------------------------------------------------------------
# Step 1: Object type lookup
# ---------------------------------------------------------------------------

async def _fetch_object_types(adapter: Any) -> Dict[str, str]:
    """
    Return {table_name: object_type} for all non-system tables in the database.

    Queries information_schema.tables. Does not include materialized views
    (pg_matviews) — those are a future enhancement.
    """
    try:
        rows = await adapter.execute_query("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema',
                                       'pg_toast', 'pg_temp_1')
            ORDER BY table_name
        """)
    except Exception as exc:
        logger.warning("Profiler: object type query failed: %s", exc)
        return {}

    result: Dict[str, str] = {}
    for row in rows:
        table_name = row.get("table_name", "")
        raw_type = row.get("table_type", "")
        result[table_name] = _TABLE_TYPE_MAP.get(raw_type, "table")
    return result


# ---------------------------------------------------------------------------
# Step 2: Per-entity profiling
# ---------------------------------------------------------------------------

async def _profile_entity(
    adapter: Any,
    entity: Entity,
    fields: List[FieldDef],
    enum_threshold: int,
) -> Dict[str, Any]:
    """
    Profile one entity: row count + per-column NULL rates and distinct counts.

    Returns a dict:
    {
        "entity_id": str,
        "row_count": int | None,
        "columns": {
            col_name: {"null_rate": float, "distinct_count": int, "sample_values": list | None}
        },
        "error": str | None,
    }
    """
    result: Dict[str, Any] = {
        "entity_id": entity.id,
        "row_count": None,
        "columns": {},
        "error": None,
    }

    # Skip entities with unsafe names
    try:
        tref = _table_ref(entity)
    except ValueError as exc:
        result["error"] = str(exc)
        logger.warning("Profiler: skipping entity %s — unsafe name: %s", entity.id, exc)
        return result

    # Filter to safe-named fields only
    safe_fields = []
    for f in fields:
        try:
            _safe_quote(f.name)
            safe_fields.append(f)
        except ValueError:
            logger.warning("Profiler: skipping field %s — unsafe name", f.name)

    if not safe_fields:
        # Nothing to profile but still get row count
        try:
            rows = await adapter.execute_query(
                f"SELECT COUNT(*) AS _total FROM {tref}"
            )
            if rows:
                result["row_count"] = int(rows[0]["_total"])
        except Exception as exc:
            result["error"] = str(exc)
            logger.warning("Profiler: row count failed for %s: %s", entity.name, exc)
        return result

    # Build a single query: COUNT(*) + COUNT(col) + COUNT(DISTINCT col) per field
    # Alias format: "_nn_{idx}" (non-null count), "_dc_{idx}" (distinct count)
    # Using integer indices avoids alias collisions for long column names.
    select_parts = ["COUNT(*) AS _total"]
    for idx, f in enumerate(safe_fields):
        qcol = _safe_quote(f.name)
        select_parts.append(f"COUNT({qcol}) AS _nn_{idx}")
        select_parts.append(f"COUNT(DISTINCT {qcol}) AS _dc_{idx}")

    batch_sql = f"SELECT {', '.join(select_parts)} FROM {tref}"

    try:
        rows = await adapter.execute_query(batch_sql)
    except Exception as exc:
        result["error"] = str(exc)
        logger.warning("Profiler: batch profile failed for %s: %s", entity.name, exc)
        return result

    if not rows:
        return result

    row = rows[0]
    total = int(row.get("_total", 0))
    result["row_count"] = total

    # Extract per-column stats
    for idx, f in enumerate(safe_fields):
        non_null = int(row.get(f"_nn_{idx}", 0))
        distinct = int(row.get(f"_dc_{idx}", 0))
        null_rate = (total - non_null) / total if total > 0 else 0.0

        result["columns"][f.name] = {
            "null_rate": round(null_rate, 6),
            "distinct_count": distinct,
            "sample_values": None,
        }

    # Fetch sample values for low-cardinality columns
    enum_candidates = [
        f for f in safe_fields
        if result["columns"][f.name]["distinct_count"] <= enum_threshold
        and result["columns"][f.name]["distinct_count"] > 0
    ]

    for f in enum_candidates:
        qcol = _safe_quote(f.name)
        enum_sql = (
            f"SELECT DISTINCT {qcol}::TEXT AS val "
            f"FROM {tref} "
            f"WHERE {qcol} IS NOT NULL "
            f"ORDER BY val"
        )
        try:
            enum_rows = await adapter.execute_query(enum_sql)
            result["columns"][f.name]["sample_values"] = [
                r["val"] for r in enum_rows if r["val"] is not None
            ]
        except Exception as exc:
            logger.warning(
                "Profiler: enum fetch failed for %s.%s: %s",
                entity.name, f.name, exc,
            )

    return result


async def _profile_all_entities(
    adapter: Any,
    snapshot: SemanticSnapshot,
    enum_threshold: int,
) -> List[Dict[str, Any]]:
    """Profile all entities sequentially.

    asyncpg connections do not support concurrent queries — only one operation
    may be in progress at a time per connection. Sequential execution is required.
    """
    results: List[Dict[str, Any]] = []
    for entity in snapshot.entities.values():
        entity_fields = [
            snapshot.fields[fid]
            for fid in entity.fields
            if fid in snapshot.fields
        ]
        result = await _profile_entity(adapter, entity, entity_fields, enum_threshold)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Step 3: Per-join FK confidence
# ---------------------------------------------------------------------------

async def _profile_join(
    adapter: Any,
    join: JoinDef,
    snapshot: SemanticSnapshot,
) -> Dict[str, Any]:
    """
    Compute FK confidence and orphan rate for one join.

    join_confidence = fraction of FK values (in child) that have a matching
                      parent key. 1.0 = clean FK, no orphans.
    orphan_rate     = 1.0 - join_confidence.

    Returns:
    {
        "join_id": str,
        "join_confidence": float | None,
        "orphan_rate": float | None,
        "error": str | None,
    }
    """
    result: Dict[str, Any] = {
        "join_id": join.id,
        "join_confidence": None,
        "orphan_rate": None,
        "error": None,
    }

    child_entity = snapshot.entities.get(join.source_entity_id)
    parent_entity = snapshot.entities.get(join.target_entity_id)
    fk_field = snapshot.fields.get(join.source_field_id)
    pk_field = snapshot.fields.get(join.target_field_id)

    if not all([child_entity, parent_entity, fk_field, pk_field]):
        result["error"] = "Missing entity or field in snapshot for join"
        return result

    try:
        child_ref = _table_ref(child_entity)   # type: ignore[arg-type]
        parent_ref = _table_ref(parent_entity)  # type: ignore[arg-type]
        fk_col = _safe_quote(fk_field.name)     # type: ignore[union-attr]
        pk_col = _safe_quote(pk_field.name)     # type: ignore[union-attr]
    except ValueError as exc:
        result["error"] = str(exc)
        logger.warning("Profiler: skipping join %s — unsafe identifier: %s", join.id, exc)
        return result

    # LEFT JOIN approach: counts distinct FK values that have (or don't have) a parent match.
    # Works on Postgres and Redshift (no FILTER clause).
    sql = f"""
        SELECT
            COUNT(DISTINCT c.{fk_col}) AS total_fk,
            COUNT(DISTINCT CASE WHEN p.{pk_col} IS NOT NULL THEN c.{fk_col} END) AS matched_fk
        FROM {child_ref} c
        LEFT JOIN {parent_ref} p ON c.{fk_col} = p.{pk_col}
        WHERE c.{fk_col} IS NOT NULL
    """

    try:
        rows = await adapter.execute_query(sql)
    except Exception as exc:
        result["error"] = str(exc)
        logger.warning("Profiler: FK confidence query failed for join %s: %s", join.id, exc)
        return result

    if not rows:
        return result

    total_fk = int(rows[0].get("total_fk", 0))
    matched_fk = int(rows[0].get("matched_fk", 0))

    if total_fk == 0:
        # No FK values → no orphan risk. Confidence is vacuously 1.0.
        result["join_confidence"] = 1.0
        result["orphan_rate"] = 0.0
    else:
        confidence = matched_fk / total_fk
        result["join_confidence"] = round(confidence, 6)
        result["orphan_rate"] = round(1.0 - confidence, 6)

    return result


async def _profile_all_joins(
    adapter: Any,
    snapshot: SemanticSnapshot,
) -> List[Dict[str, Any]]:
    """Profile all joins sequentially.

    Same asyncpg single-connection constraint as entity profiling.
    """
    if not snapshot.joins:
        return []
    results: List[Dict[str, Any]] = []
    for join in snapshot.joins:
        result = await _profile_join(adapter, join, snapshot)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Step 4 + 5: Assemble enriched models
# ---------------------------------------------------------------------------

def _apply_entity_profiles(
    snapshot: SemanticSnapshot,
    entity_profiles: List[Dict[str, Any]],
    object_types: Dict[str, str],
) -> tuple[Dict[str, Entity], Dict[str, FieldDef]]:
    """
    Build enriched Entity and FieldDef dicts from profiling results.

    Returns (new_entities, new_fields) with profiling data applied.
    Entities and fields not covered by profiling data are copied unchanged.
    """
    # Index entity profiles by entity_id
    profile_by_entity: Dict[str, Dict[str, Any]] = {
        p["entity_id"]: p for p in entity_profiles
    }

    new_entities: Dict[str, Entity] = {}
    new_fields: Dict[str, FieldDef] = dict(snapshot.fields)  # start with copy

    for eid, entity in snapshot.entities.items():
        ep = profile_by_entity.get(eid, {})

        # object_type from information_schema lookup
        raw_object_type = object_types.get(entity.name)

        new_entities[eid] = entity.model_copy(update={
            "object_type": raw_object_type,
            "row_count": ep.get("row_count"),
        })

        # Enrich each field belonging to this entity
        col_stats: Dict[str, Dict[str, Any]] = ep.get("columns", {})
        for fid in entity.fields:
            field = snapshot.fields.get(fid)
            if field is None:
                continue
            stats = col_stats.get(field.name)
            if stats is None:
                continue
            new_fields[fid] = field.model_copy(update={
                "null_rate": stats.get("null_rate"),
                "distinct_count": stats.get("distinct_count"),
                "sample_values": stats.get("sample_values"),
            })

    return new_entities, new_fields


def _apply_join_profiles(
    snapshot: SemanticSnapshot,
    join_profiles: List[Dict[str, Any]],
) -> List[JoinDef]:
    """
    Build enriched JoinDef list from FK confidence profiling results.
    """
    profile_by_id: Dict[str, Dict[str, Any]] = {
        jp["join_id"]: jp for jp in join_profiles
    }

    enriched: List[JoinDef] = []
    for join in snapshot.joins:
        jp = profile_by_id.get(join.id, {})
        if jp.get("join_confidence") is not None:
            enriched.append(join.model_copy(update={
                "join_confidence": jp["join_confidence"],
                "orphan_rate": jp["orphan_rate"],
            }))
        else:
            enriched.append(join)
    return enriched
