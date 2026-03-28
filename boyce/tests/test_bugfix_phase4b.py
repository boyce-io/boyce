"""
Phase 4b Bug Fix Tests — StructuredFilter → SQL verification.

Tests the builder, kernel, and planner helper fixes from the Phase 4b benchmark
bug fix pass. All tests are offline: no DB, no LLM.

Bug coverage:
  BUG-A / BUG-I : Metric validation + COUNT(*) rendering
  BUG-B         : ORDER BY / LIMIT
  BUG-D         : grouping_fields field_ids in GROUP BY
  BUG-F         : Expression columns (concatenation)
  BUG-G         : _score_field_match keyword scoring helper
"""

from __future__ import annotations

import pytest

from boyce.planner.planner import _score_field_match
from boyce.sql.builder import SQLBuilder
from boyce.types import SemanticSnapshot
from boyce.validation import _compute_snapshot_hash


# ---------------------------------------------------------------------------
# Minimal snapshot fixture
# ---------------------------------------------------------------------------


def _make_snapshot() -> SemanticSnapshot:
    """Orders + customers snapshot with first_name / last_name for expression tests."""
    base = {
        "snapshot_id": "placeholder",
        "source_system": "test",
        "entities": {
            "entity:orders": {
                "id": "entity:orders",
                "name": "orders",
                "grain": "ORDER",
                "fields": [
                    "field:orders:id",
                    "field:orders:revenue",
                    "field:orders:status",
                    "field:orders:customer_id",
                ],
            },
            "entity:customers": {
                "id": "entity:customers",
                "name": "customers",
                "grain": "CUSTOMER",
                "fields": [
                    "field:customers:id",
                    "field:customers:first_name",
                    "field:customers:last_name",
                ],
            },
        },
        "fields": {
            "field:orders:id": {
                "id": "field:orders:id",
                "entity_id": "entity:orders",
                "name": "id",
                "field_type": "ID",
                "data_type": "INTEGER",
                "primary_key": True,
            },
            "field:orders:revenue": {
                "id": "field:orders:revenue",
                "entity_id": "entity:orders",
                "name": "revenue",
                "field_type": "MEASURE",
                "data_type": "DECIMAL(10,2)",
            },
            "field:orders:status": {
                "id": "field:orders:status",
                "entity_id": "entity:orders",
                "name": "status",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(50)",
            },
            "field:orders:customer_id": {
                "id": "field:orders:customer_id",
                "entity_id": "entity:orders",
                "name": "customer_id",
                "field_type": "FOREIGN_KEY",
                "data_type": "INTEGER",
            },
            "field:customers:id": {
                "id": "field:customers:id",
                "entity_id": "entity:customers",
                "name": "id",
                "field_type": "ID",
                "data_type": "INTEGER",
                "primary_key": True,
            },
            "field:customers:first_name": {
                "id": "field:customers:first_name",
                "entity_id": "entity:customers",
                "name": "first_name",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(100)",
            },
            "field:customers:last_name": {
                "id": "field:customers:last_name",
                "entity_id": "entity:customers",
                "name": "last_name",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(100)",
            },
        },
        "joins": [
            {
                "id": "join:orders:customers",
                "source_entity_id": "entity:orders",
                "target_entity_id": "entity:customers",
                "join_type": "LEFT",
                "source_field_id": "field:orders:customer_id",
                "target_field_id": "field:customers:id",
            }
        ],
    }
    tmp = SemanticSnapshot(**base)
    correct_id = _compute_snapshot_hash(tmp)
    base["snapshot_id"] = correct_id
    return SemanticSnapshot(**base)


@pytest.fixture
def snapshot():
    return _make_snapshot()


@pytest.fixture
def builder():
    b = SQLBuilder()
    b.set_dialect("postgres")
    return b


def _planner_output(
    snapshot: SemanticSnapshot,
    metrics=None,
    dimensions=None,
    filters=None,
    order_by=None,
    limit=None,
    expressions=None,
    entities=None,
    fields=None,
) -> dict:
    """Build a minimal planner_output for builder tests."""
    ents = entities or [{"entity_id": "entity:orders", "entity_name": "orders"}]
    return {
        "concept_map": {
            "entities": ents,
            "fields": fields or [],
            "metrics": metrics or [],
            "dimensions": dimensions or [],
            "filters": filters or [],
            "expressions": expressions or [],
        },
        "join_path": [e["entity_id"] for e in ents],
        "grain_context": {
            "aggregation_required": bool(metrics),
            "grouping_fields": [d["field_id"] for d in (dimensions or [])],
        },
        "policy_context": {"resolved_predicates": []},
        "temporal_filters": [],
        "order_by": order_by or [],
        "limit": limit,
        "expressions": expressions or [],
    }


# ---------------------------------------------------------------------------
# BUG-A / BUG-I — COUNT(*) rendering
# ---------------------------------------------------------------------------


def test_count_star_sentinel_renders_correctly(snapshot, builder):
    """Empty field_id + COUNT aggregation → COUNT(*) in SELECT."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_rentals", "field_id": "", "aggregation_type": "COUNT"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert 'COUNT(*) AS "total_rentals"' in sql


def test_sum_with_field_id_renders_correctly(snapshot, builder):
    """Metric with valid field_id + SUM → SUM(col) AS alias."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert 'SUM("orders"."revenue") AS "total_revenue"' in sql


def test_count_distinct_renders_correctly(snapshot, builder):
    """COUNT_DISTINCT → COUNT(DISTINCT col) AS alias."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "unique_orders", "field_id": "field:orders:id", "aggregation_type": "COUNT_DISTINCT"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert 'COUNT(DISTINCT "orders"."id") AS "unique_orders"' in sql


def test_scalar_aggregate_no_group_by(snapshot, builder):
    """Metrics with no dimensions → aggregation_required True but no GROUP BY."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
        dimensions=[],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert "SUM" in sql
    assert "GROUP BY" not in sql


# ---------------------------------------------------------------------------
# BUG-B — ORDER BY / LIMIT
# ---------------------------------------------------------------------------


def test_order_by_field_id_desc(snapshot, builder):
    """ORDER BY with a field_id reference renders table-qualified column."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
        order_by=[{"field_id": "field:orders:revenue", "direction": "DESC"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert 'ORDER BY "orders"."revenue" DESC' in sql


def test_order_by_metric_alias(snapshot, builder):
    """ORDER BY with a metric_name (aggregate alias) reference."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
        order_by=[{"metric_name": "total_revenue", "direction": "DESC"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert 'ORDER BY "total_revenue" DESC' in sql


def test_limit(snapshot, builder):
    """LIMIT N renders correctly."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "cnt", "field_id": "", "aggregation_type": "COUNT"}],
        limit=5,
    )
    sql = builder.build_final_sql(po, snapshot)
    assert "LIMIT 5" in sql


def test_group_by_order_by_limit_together(snapshot, builder):
    """GROUP BY, ORDER BY, LIMIT all appear together in correct order."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
        dimensions=[{"field_id": "field:orders:status", "field_name": "status", "entity_id": "entity:orders"}],
        order_by=[{"metric_name": "total_revenue", "direction": "DESC"}],
        limit=5,
    )
    sql = builder.build_final_sql(po, snapshot)
    assert "GROUP BY" in sql
    assert "ORDER BY" in sql
    assert "LIMIT 5" in sql
    # ORDER must come after GROUP BY and before LIMIT
    gb_pos = sql.index("GROUP BY")
    ob_pos = sql.index("ORDER BY")
    lim_pos = sql.index("LIMIT")
    assert gb_pos < ob_pos < lim_pos


def test_no_order_by_when_not_specified(snapshot, builder):
    """No ORDER BY or LIMIT rendered when not in planner output."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert "ORDER BY" not in sql
    assert "LIMIT" not in sql


# ---------------------------------------------------------------------------
# BUG-D — grouping_fields uses field_ids (table-qualified GROUP BY)
# ---------------------------------------------------------------------------


def test_grouping_by_field_id_produces_qualified_column(snapshot, builder):
    """GROUP BY with field_id produces table.column reference."""
    po = _planner_output(
        snapshot,
        metrics=[{"metric_name": "total_revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
        dimensions=[{"field_id": "field:orders:status", "field_name": "status", "entity_id": "entity:orders"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    # Should be GROUP BY "orders"."status" not GROUP BY "status"
    assert 'GROUP BY "orders"."status"' in sql


# ---------------------------------------------------------------------------
# BUG-F — Expression columns (concatenation)
# ---------------------------------------------------------------------------


def test_expression_concatenation_with_separator(snapshot, builder):
    """Two fields joined with a space separator → col1 || ' ' || col2 AS alias."""
    po = _planner_output(
        snapshot,
        entities=[{"entity_id": "entity:customers", "entity_name": "customers"}],
        expressions=[{
            "name": "full_name",
            "expression_type": "concatenation",
            "fields": [
                {"field_id": "field:customers:first_name", "field_name": "first_name"},
                {"field_id": "field:customers:last_name", "field_name": "last_name"},
            ],
            "separator": " ",
        }],
    )
    po["join_path"] = ["entity:customers"]
    sql = builder.build_final_sql(po, snapshot)
    assert "|| ' ' ||" in sql
    assert '"full_name"' in sql


def test_expression_concatenation_without_separator(snapshot, builder):
    """Two fields with no separator → col1 || col2."""
    po = _planner_output(
        snapshot,
        entities=[{"entity_id": "entity:customers", "entity_name": "customers"}],
        expressions=[{
            "name": "combined",
            "expression_type": "concatenation",
            "fields": [
                {"field_id": "field:customers:first_name", "field_name": "first_name"},
                {"field_id": "field:customers:last_name", "field_name": "last_name"},
            ],
            "separator": "",
        }],
    )
    po["join_path"] = ["entity:customers"]
    sql = builder.build_final_sql(po, snapshot)
    # Should contain || without a separator string between the columns
    assert " || " in sql
    assert "|| ' ' ||" not in sql


def test_no_expressions_no_change_to_select(snapshot, builder):
    """No expressions in input → clean SELECT without concatenation."""
    po = _planner_output(
        snapshot,
        fields=[{"field_id": "field:orders:id", "field_name": "id", "entity_id": "entity:orders"}],
    )
    sql = builder.build_final_sql(po, snapshot)
    assert "||" not in sql


# ---------------------------------------------------------------------------
# BUG-G — _score_field_match keyword overlap scoring
# ---------------------------------------------------------------------------


def test_score_exact_match_words():
    """Scoring splits on underscores — language_id → {"language", "id"}."""
    # language_id vs language_id: {"language","id"} ∩ {"language","id"} = 2
    assert _score_field_match("language_id", "language_id") == 2
    # In the planner, exact name equality bypasses scoring via the 999 fast path.


def test_score_prefers_original_language():
    """'original language' query scores original_language_id higher than language_id."""
    score_original = _score_field_match("original_language", "original_language_id")
    score_primary = _score_field_match("original_language", "language_id")
    # original_language → {"original", "language"}
    # original_language_id → {"original", "language", "id"} → overlap 2
    # language_id → {"language", "id"} → overlap 1
    assert score_original > score_primary


def test_score_no_overlap():
    """Completely different names score zero."""
    assert _score_field_match("status", "revenue") == 0


def test_score_single_word_overlap():
    """Partial overlap returns count of overlapping words."""
    assert _score_field_match("rental_date", "return_date") == 1  # "date"
