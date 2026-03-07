"""
Capability Test: Kernel Determinism

Scenario: An analyst runs the same query twice. The SQL should be byte-identical
both times. If the kernel is non-deterministic, you can't reproduce results,
can't debug discrepancies, can't audit decisions.

A staff engineer's hallmark: given the same inputs, the same answer. Every time.
No randomness, no model temperature, no cache-dependent behavior in the SQL layer.

This also validates that the kernel correctly refuses invalid inputs rather than
producing garbage SQL — a staff engineer says "I can't do that" rather than
handing you a query that silently returns wrong results.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_PROTO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROTO_ROOT / "src"))

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from boyce.parsers.base import build_snapshot
from boyce import kernel


def _build_ecommerce_snapshot() -> SemanticSnapshot:
    """Standard e-commerce snapshot for determinism testing.

    Uses build_snapshot() to compute a valid SHA-256 snapshot_id,
    which is required by validate_snapshot() in the kernel.
    """
    entities = {
        "entity:orders": Entity(
            id="entity:orders",
            name="orders",
            fields=[
                "field:orders:id",
                "field:orders:customer_id",
                "field:orders:status",
                "field:orders:revenue",
                "field:orders:created_at",
            ],
            grain="id",
        ),
        "entity:customers": Entity(
            id="entity:customers",
            name="customers",
            fields=[
                "field:customers:id",
                "field:customers:name",
                "field:customers:segment",
            ],
            grain="id",
        ),
    }
    fields = {
        "field:orders:id": FieldDef(
            id="field:orders:id",
            entity_id="entity:orders",
            name="id",
            field_type=FieldType.ID,
            data_type="INTEGER",
            primary_key=True,
        ),
        "field:orders:customer_id": FieldDef(
            id="field:orders:customer_id",
            entity_id="entity:orders",
            name="customer_id",
            field_type=FieldType.FOREIGN_KEY,
            data_type="INTEGER",
        ),
        "field:orders:status": FieldDef(
            id="field:orders:status",
            entity_id="entity:orders",
            name="status",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR",
        ),
        "field:orders:revenue": FieldDef(
            id="field:orders:revenue",
            entity_id="entity:orders",
            name="revenue",
            field_type=FieldType.MEASURE,
            data_type="DECIMAL",
        ),
        "field:orders:created_at": FieldDef(
            id="field:orders:created_at",
            entity_id="entity:orders",
            name="created_at",
            field_type=FieldType.TIMESTAMP,
            data_type="TIMESTAMP",
        ),
        "field:customers:id": FieldDef(
            id="field:customers:id",
            entity_id="entity:customers",
            name="id",
            field_type=FieldType.ID,
            data_type="INTEGER",
            primary_key=True,
        ),
        "field:customers:name": FieldDef(
            id="field:customers:name",
            entity_id="entity:customers",
            name="name",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR",
        ),
        "field:customers:segment": FieldDef(
            id="field:customers:segment",
            entity_id="entity:customers",
            name="segment",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR",
        ),
    }
    joins = [
        JoinDef(
            id="join:orders:customers",
            source_entity_id="entity:orders",
            target_entity_id="entity:customers",
            join_type=JoinType.LEFT,
            source_field_id="field:orders:customer_id",
            target_field_id="field:customers:id",
            description="FK: orders.customer_id -> customers.id",
        ),
    ]
    return build_snapshot(
        source_system="test",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={},
    )


class TestKernelDeterminism(unittest.TestCase):
    """Same inputs → same SQL, every time."""

    def test_identical_inputs_identical_sql(self):
        """Running process_request twice with the same inputs must produce identical SQL."""
        snapshot = _build_ecommerce_snapshot()

        structured_filter = {
            "concept_map": {
                "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
                "fields": [],
                "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
                "dimensions": [{"field_id": "field:orders:status", "field_name": "status", "entity_id": "entity:orders"}],
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    }
                ],
            },
            "join_path": ["entity:orders"],
            "grain_context": {
                "aggregation_required": True,
                "grouping_fields": ["status"],
            },
            "dialect": "postgres",
        }

        sql_1 = kernel.process_request(snapshot, structured_filter)
        sql_2 = kernel.process_request(snapshot, structured_filter)

        self.assertEqual(sql_1, sql_2, "Same inputs must produce byte-identical SQL")

    def test_produces_valid_sql_structure(self):
        """The generated SQL must have SELECT, FROM, WHERE, and GROUP BY when appropriate."""
        snapshot = _build_ecommerce_snapshot()

        structured_filter = {
            "concept_map": {
                "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
                "fields": [],
                "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
                "dimensions": [{"field_id": "field:orders:status", "field_name": "status", "entity_id": "entity:orders"}],
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    }
                ],
            },
            "join_path": ["entity:orders"],
            "grain_context": {
                "aggregation_required": True,
                "grouping_fields": ["status"],
            },
            "dialect": "postgres",
        }

        sql = kernel.process_request(snapshot, structured_filter)

        self.assertIn("SELECT", sql.upper())
        self.assertIn("FROM", sql.upper())
        self.assertIn("WHERE", sql.upper())
        self.assertIn("GROUP BY", sql.upper())
        self.assertIn("revenue", sql.lower())
        self.assertIn("status", sql.lower())

    def test_rejects_invalid_snapshot(self):
        """An invalid snapshot must raise ValueError, not produce garbage SQL.

        We build a snapshot with build_snapshot() (valid hash) but then
        manually construct one that references a field that doesn't exist.
        The kernel's validate_snapshot() catches the broken reference.
        """
        # Build a valid snapshot first to get the hash, then break it
        # Actually: just create a snapshot with a bad snapshot_id — simpler
        broken_snapshot = SemanticSnapshot(
            snapshot_id="definitely-not-a-valid-hash",
            source_system="test",
            source_version="1.0",
            entities={
                "entity:orders": Entity(
                    id="entity:orders",
                    name="orders",
                    fields=["field:orders:id"],
                    grain="id",
                ),
            },
            fields={
                "field:orders:id": FieldDef(
                    id="field:orders:id",
                    entity_id="entity:orders",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
            },
            joins=[],
        )

        structured_filter = {
            "concept_map": {
                "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
                "fields": [],
                "metrics": [],
                "dimensions": [],
                "filters": [],
            },
            "join_path": ["entity:orders"],
            "grain_context": {},
            "dialect": "postgres",
        }

        with self.assertRaises(ValueError):
            kernel.process_request(broken_snapshot, structured_filter)

    def test_multi_entity_query_with_join(self):
        """Query spanning two entities must include the correct JOIN."""
        snapshot = _build_ecommerce_snapshot()

        structured_filter = {
            "concept_map": {
                "entities": [
                    {"entity_id": "entity:orders", "entity_name": "orders"},
                    {"entity_id": "entity:customers", "entity_name": "customers"},
                ],
                "fields": [],
                "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
                "dimensions": [{"field_id": "field:customers:segment", "field_name": "segment", "entity_id": "entity:customers"}],
                "filters": [],
            },
            "join_path": ["entity:orders", "entity:customers"],
            "grain_context": {
                "aggregation_required": True,
                "grouping_fields": ["segment"],
            },
            "dialect": "postgres",
        }

        sql = kernel.process_request(snapshot, structured_filter)

        self.assertIn("JOIN", sql.upper())
        self.assertIn("customers", sql.lower())
        self.assertIn("segment", sql.lower())
        self.assertIn("revenue", sql.lower())

    def test_dialect_switch_changes_sql(self):
        """Switching dialect should produce different SQL for the same logical query."""
        snapshot = _build_ecommerce_snapshot()

        base_filter = {
            "concept_map": {
                "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
                "fields": [],
                "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue", "aggregation_type": "SUM"}],
                "dimensions": [{"field_id": "field:orders:status", "field_name": "status", "entity_id": "entity:orders"}],
                "filters": [],
            },
            "join_path": ["entity:orders"],
            "grain_context": {
                "aggregation_required": True,
                "grouping_fields": ["status"],
            },
        }

        filter_pg = {**base_filter, "dialect": "postgres"}
        filter_bq = {**base_filter, "dialect": "bigquery"}

        sql_pg = kernel.process_request(snapshot, filter_pg)
        sql_bq = kernel.process_request(snapshot, filter_bq)

        # Both should be valid SQL, but BigQuery uses backticks for quoting
        self.assertIn("SELECT", sql_pg.upper())
        self.assertIn("SELECT", sql_bq.upper())
        # BigQuery uses backtick quoting, Postgres uses double-quote
        # They should differ in quoting style
        self.assertNotEqual(sql_pg, sql_bq, "Different dialects should produce different SQL")


class TestRedshiftSafety(unittest.TestCase):
    """Does the safety layer catch Redshift-incompatible SQL?"""

    def test_catches_lateral_join(self):
        """Redshift 1.0 doesn't support LATERAL — must flag it."""
        from boyce.safety import lint_redshift_compat

        sql = "SELECT * FROM orders, LATERAL unnest(tags) AS t"
        problems = lint_redshift_compat(sql)

        self.assertTrue(len(problems) > 0, "LATERAL join must be flagged")
        self.assertTrue(
            any("LATERAL" in p for p in problems),
            "Warning should mention LATERAL"
        )

    def test_catches_jsonb(self):
        """Redshift 1.0 doesn't support JSONB — must flag it."""
        from boyce.safety import lint_redshift_compat

        sql = "SELECT data::JSONB FROM events"
        problems = lint_redshift_compat(sql)

        self.assertTrue(len(problems) > 0, "JSONB must be flagged")

    def test_clean_sql_passes(self):
        """Standard SQL should pass with no warnings."""
        from boyce.safety import lint_redshift_compat

        sql = "SELECT status, SUM(revenue) FROM orders WHERE status = 'active' GROUP BY status"
        problems = lint_redshift_compat(sql)

        self.assertEqual(len(problems), 0, "Clean SQL should have no warnings")

    def test_nullif_transformation(self):
        """Numeric casts get NULLIF('') wrapping for Redshift safety."""
        from boyce.safety import transform_sql_for_redshift_safety

        sql = "SELECT CAST(amount AS NUMERIC(10,2)) FROM orders"
        safe_sql = transform_sql_for_redshift_safety(sql)

        self.assertIn("NULLIF", safe_sql, "Numeric cast should get NULLIF wrapping")


if __name__ == "__main__":
    unittest.main(verbosity=2)
