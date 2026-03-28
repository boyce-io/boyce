"""
Sprint 1a: Schema Extensions

Tests for the profiling fields added to FieldDef, Entity, JoinDef, and SemanticSnapshot.

Key invariants:
  1. All new fields are Optional and default to None
  2. Profiling fields do NOT affect the snapshot_id hash
  3. profiled_at timestamp is stored and round-trips correctly
  4. Existing snapshots (built without profiling data) remain valid
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).parent
_PROTO_ROOT = _HERE.parent
sys.path.insert(0, str(_PROTO_ROOT / "src"))

import unittest

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from boyce.parsers.base import build_snapshot
from boyce.validation import (
    validate_snapshot,
    _compute_snapshot_hash,
    canonicalize_snapshot_for_hash,
)


def _minimal_snapshot(profiling_data: bool = False) -> SemanticSnapshot:
    """Build a minimal 2-entity snapshot. Optionally populate profiling fields."""
    entities = {
        "entity:orders": Entity(
            id="entity:orders",
            name="orders",
            fields=["field:orders:order_id", "field:orders:customer_id"],
            grain="order_id",
            object_type="table" if profiling_data else None,
            row_count=10000 if profiling_data else None,
        ),
    }
    fields = {
        "field:orders:order_id": FieldDef(
            id="field:orders:order_id",
            entity_id="entity:orders",
            name="order_id",
            field_type=FieldType.ID,
            data_type="INTEGER",
            nullable=False,
            primary_key=True,
            null_rate=0.0 if profiling_data else None,
            distinct_count=10000 if profiling_data else None,
            sample_values=None,
        ),
        "field:orders:customer_id": FieldDef(
            id="field:orders:customer_id",
            entity_id="entity:orders",
            name="customer_id",
            field_type=FieldType.FOREIGN_KEY,
            data_type="INTEGER",
            nullable=False,
            null_rate=0.02 if profiling_data else None,
            distinct_count=950 if profiling_data else None,
            business_description="FK to customer.customer_id" if profiling_data else None,
            business_rules=["not_null"] if profiling_data else None,
        ),
    }
    return build_snapshot(
        source_system="test",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=[],
        metadata={},
    )


class TestProfilingFieldDefaults(unittest.TestCase):
    """All new profiling fields must be Optional[...] = None by default."""

    def test_fielddef_profiling_fields_default_none(self):
        field = FieldDef(
            id="field:t:col",
            entity_id="entity:t",
            name="col",
            field_type=FieldType.DIMENSION,
            data_type="TEXT",
        )
        self.assertIsNone(field.null_rate)
        self.assertIsNone(field.distinct_count)
        self.assertIsNone(field.sample_values)
        self.assertIsNone(field.business_description)
        self.assertIsNone(field.business_rules)

    def test_entity_profiling_fields_default_none(self):
        entity = Entity(id="entity:t", name="t", fields=[], grain="id")
        self.assertIsNone(entity.object_type)
        self.assertIsNone(entity.row_count)
        self.assertIsNone(entity.view_sql)
        self.assertIsNone(entity.view_lineage)

    def test_joindef_profiling_fields_default_none(self):
        join = JoinDef(
            id="join:a:b",
            source_entity_id="entity:a",
            target_entity_id="entity:b",
            join_type=JoinType.LEFT,
            source_field_id="field:a:fk",
            target_field_id="field:b:pk",
        )
        self.assertIsNone(join.join_confidence)
        self.assertIsNone(join.orphan_rate)

    def test_snapshot_profiled_at_defaults_none(self):
        snap = _minimal_snapshot()
        self.assertIsNone(snap.profiled_at)


class TestProfilingFieldValues(unittest.TestCase):
    """Profiling fields round-trip correctly when set."""

    def test_fielddef_profiling_values_stored(self):
        field = FieldDef(
            id="field:t:status",
            entity_id="entity:t",
            name="status",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR(1)",
            null_rate=0.05,
            distinct_count=4,
            sample_values=["A", "C", "S", "P"],
            business_description="Order status code",
            business_rules=["accepted_values: A, C, S, P"],
        )
        self.assertAlmostEqual(field.null_rate, 0.05)
        self.assertEqual(field.distinct_count, 4)
        self.assertEqual(field.sample_values, ["A", "C", "S", "P"])
        self.assertEqual(field.business_description, "Order status code")
        self.assertEqual(field.business_rules, ["accepted_values: A, C, S, P"])

    def test_entity_profiling_values_stored(self):
        entity = Entity(
            id="entity:orders",
            name="orders",
            fields=[],
            grain="order_id",
            object_type="table",
            row_count=500000,
            view_sql=None,
            view_lineage=None,
        )
        self.assertEqual(entity.object_type, "table")
        self.assertEqual(entity.row_count, 500000)

    def test_joindef_profiling_values_stored(self):
        join = JoinDef(
            id="join:a:b",
            source_entity_id="entity:a",
            target_entity_id="entity:b",
            join_type=JoinType.LEFT,
            source_field_id="field:a:fk",
            target_field_id="field:b:pk",
            join_confidence=0.98,
            orphan_rate=0.02,
        )
        self.assertAlmostEqual(join.join_confidence, 0.98)
        self.assertAlmostEqual(join.orphan_rate, 0.02)

    def test_snapshot_profiled_at_stored(self):
        snap_dict = _minimal_snapshot().model_dump(mode="json")
        snap_dict["profiled_at"] = "2026-03-28T12:00:00Z"
        snap = SemanticSnapshot(**snap_dict)
        self.assertEqual(snap.profiled_at, "2026-03-28T12:00:00Z")


class TestProfilingFieldsExcludedFromHash(unittest.TestCase):
    """Snapshot hash must be stable regardless of profiling data."""

    def test_hash_unchanged_when_profiling_fields_populated(self):
        """Two snapshots with identical structure but different profiling data
        must produce the same snapshot_id."""
        snap_clean = _minimal_snapshot(profiling_data=False)
        snap_profiled = _minimal_snapshot(profiling_data=True)
        self.assertEqual(snap_clean.snapshot_id, snap_profiled.snapshot_id)

    def test_profiled_at_excluded_from_hash(self):
        """Adding profiled_at to a snapshot must not change its hash."""
        snap = _minimal_snapshot()
        snap_dict = snap.model_dump(mode="json")
        snap_dict["profiled_at"] = "2026-03-28T12:00:00Z"
        snap_with_ts = SemanticSnapshot(**snap_dict)

        # Hash must be recalculated — both should match
        self.assertEqual(
            _compute_snapshot_hash(snap),
            _compute_snapshot_hash(snap_with_ts),
        )

    def test_null_rate_excluded_from_hash(self):
        """Setting null_rate on a field must not change the snapshot hash."""
        snap = _minimal_snapshot()
        base_hash = snap.snapshot_id

        # Build same snapshot with null_rate set
        entities = dict(snap.entities)
        fields = {}
        for fid, fdef in snap.fields.items():
            # Use model_copy to override the frozen field (pydantic v2)
            fields[fid] = fdef.model_copy(update={"null_rate": 0.15})

        snap_profiled = build_snapshot(
            source_system=snap.source_system,
            source_version=snap.source_version or "1.0",
            entities=entities,
            fields=fields,
            joins=list(snap.joins),
            metadata=dict(snap.metadata),
        )
        self.assertEqual(snap_profiled.snapshot_id, base_hash)

    def test_sample_values_excluded_from_hash(self):
        """sample_values enum list must not affect the hash."""
        snap_plain = _minimal_snapshot()
        snap_dict = snap_plain.model_dump(mode="json")

        # Inject sample_values into a field
        for fid in snap_dict["fields"]:
            snap_dict["fields"][fid]["sample_values"] = ["X", "Y", "Z"]

        canonical = canonicalize_snapshot_for_hash(snap_dict)
        # After canonicalization, sample_values should be gone
        for fid, fdata in canonical["fields"].items():
            self.assertNotIn("sample_values", fdata)

    def test_join_confidence_excluded_from_hash(self):
        """join_confidence must not appear in the canonical hash dict."""
        snap_dict = {
            "joins": [
                {
                    "id": "join:a:b",
                    "source_entity_id": "entity:a",
                    "target_entity_id": "entity:b",
                    "join_type": "LEFT",
                    "source_field_id": "field:a:fk",
                    "target_field_id": "field:b:pk",
                    "description": None,
                    "join_confidence": 0.97,
                    "orphan_rate": 0.03,
                }
            ]
        }
        canonical = canonicalize_snapshot_for_hash(snap_dict)
        self.assertNotIn("join_confidence", canonical["joins"][0])
        self.assertNotIn("orphan_rate", canonical["joins"][0])
        # Structural fields survive
        self.assertIn("join_type", canonical["joins"][0])

    def test_entity_profiling_fields_excluded_from_canonical(self):
        """object_type, row_count, view_sql, view_lineage not in canonical dict."""
        snap_dict = {
            "entities": {
                "entity:t": {
                    "id": "entity:t",
                    "name": "t",
                    "fields": [],
                    "grain": "id",
                    "object_type": "view",
                    "row_count": 5000,
                    "view_sql": "SELECT * FROM base_table",
                    "view_lineage": ["entity:base_table"],
                }
            }
        }
        canonical = canonicalize_snapshot_for_hash(snap_dict)
        entity = canonical["entities"]["entity:t"]
        for key in ("object_type", "row_count", "view_sql", "view_lineage"):
            self.assertNotIn(key, entity)
        # Structural fields survive
        self.assertIn("name", entity)
        self.assertIn("grain", entity)


class TestExistingSnapshotHashStability(unittest.TestCase):
    """Snapshots built before profiling fields were added must still validate."""

    def test_build_then_validate_round_trip(self):
        """build_snapshot() → validate_snapshot() must succeed."""
        snap = _minimal_snapshot()
        errors = validate_snapshot(snap.model_dump(mode="json"))
        self.assertEqual(errors, [], f"Validation errors: {errors}")

    def test_profiled_snapshot_validates(self):
        """Snapshot with profiling data populated must still validate."""
        snap = _minimal_snapshot(profiling_data=True)
        # Add profiled_at
        snap_dict = snap.model_dump(mode="json")
        snap_dict["profiled_at"] = "2026-03-28T12:00:00Z"
        # snapshot_id was computed without profiling data — should still validate
        errors = validate_snapshot(snap_dict)
        self.assertEqual(errors, [], f"Validation errors: {errors}")


if __name__ == "__main__":
    unittest.main()
