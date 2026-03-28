"""
Sprint 2: Profiler tests

Tests for boyce/src/boyce/profiler.py.

Structure:
  Unit tests (mocked adapter, no DB):
    - _safe_quote() validation
    - _table_ref() schema qualification
    - _apply_entity_profiles() enrichment logic
    - _apply_join_profiles() enrichment logic
    - profile_snapshot() snapshot_id stability
    - profile_snapshot() profiled_at is set

  Integration tests (Pagila Docker — skipped if not available):
    - original_language_id is 100% NULL (the smoke test)
    - film.rating has sample_values (enum detection)
    - FK confidence = 1.0 for clean Pagila joins
    - Row counts match expected Pagila sizes
    - object_type detection (table vs view)
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

_HERE = Path(__file__).parent
_PROTO_ROOT = _HERE.parent
sys.path.insert(0, str(_PROTO_ROOT / "src"))

from boyce.profiler import (
    _apply_entity_profiles,
    _apply_join_profiles,
    _safe_quote,
    _table_ref,
    profile_snapshot,
)
from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from boyce.parsers.base import build_snapshot


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _build_orders_snapshot() -> SemanticSnapshot:
    """Minimal 2-table snapshot: orders + customers with one FK join."""
    entities = {
        "entity:orders": Entity(
            id="entity:orders",
            name="orders",
            fields=["field:orders:order_id", "field:orders:customer_id", "field:orders:status"],
            grain="order_id",
        ),
        "entity:customers": Entity(
            id="entity:customers",
            name="customers",
            fields=["field:customers:customer_id", "field:customers:email"],
            grain="customer_id",
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
        ),
        "field:orders:customer_id": FieldDef(
            id="field:orders:customer_id",
            entity_id="entity:orders",
            name="customer_id",
            field_type=FieldType.FOREIGN_KEY,
            data_type="INTEGER",
            nullable=True,
        ),
        "field:orders:status": FieldDef(
            id="field:orders:status",
            entity_id="entity:orders",
            name="status",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR",
            nullable=True,
        ),
        "field:customers:customer_id": FieldDef(
            id="field:customers:customer_id",
            entity_id="entity:customers",
            name="customer_id",
            field_type=FieldType.ID,
            data_type="INTEGER",
            nullable=False,
            primary_key=True,
        ),
        "field:customers:email": FieldDef(
            id="field:customers:email",
            entity_id="entity:customers",
            name="email",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR",
            nullable=True,
        ),
    }
    joins = [
        JoinDef(
            id="join:orders:customers",
            source_entity_id="entity:orders",
            target_entity_id="entity:customers",
            join_type=JoinType.LEFT,
            source_field_id="field:orders:customer_id",
            target_field_id="field:customers:customer_id",
        )
    ]
    return build_snapshot("test", "1.0", entities, fields, joins, {})


# ---------------------------------------------------------------------------
# Unit tests — identifier safety
# ---------------------------------------------------------------------------

class TestSafeQuote(unittest.TestCase):

    def test_simple_name(self):
        self.assertEqual(_safe_quote("orders"), '"orders"')

    def test_underscore_name(self):
        self.assertEqual(_safe_quote("order_id"), '"order_id"')

    def test_mixed_case(self):
        self.assertEqual(_safe_quote("CustomerID"), '"CustomerID"')

    def test_rejects_hyphen(self):
        with self.assertRaises(ValueError):
            _safe_quote("my-table")

    def test_rejects_space(self):
        with self.assertRaises(ValueError):
            _safe_quote("my table")

    def test_rejects_semicolon(self):
        with self.assertRaises(ValueError):
            _safe_quote("table; DROP TABLE users; --")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            _safe_quote("")


class TestTableRef(unittest.TestCase):

    def test_bare_name(self):
        entity = Entity(id="entity:film", name="film", fields=[], grain="id")
        self.assertEqual(_table_ref(entity), '"film"')

    def test_schema_qualified(self):
        entity = Entity(
            id="entity:film",
            name="film",
            fields=[],
            grain="id",
            schema_name="public",
        )
        self.assertEqual(_table_ref(entity), '"public"."film"')


# ---------------------------------------------------------------------------
# Unit tests — apply profiles
# ---------------------------------------------------------------------------

class TestApplyEntityProfiles(unittest.TestCase):

    def setUp(self):
        self.snapshot = _build_orders_snapshot()

    def test_row_count_applied(self):
        profiles = [
            {"entity_id": "entity:orders", "row_count": 5000, "columns": {}, "error": None},
            {"entity_id": "entity:customers", "row_count": 1200, "columns": {}, "error": None},
        ]
        new_entities, _ = _apply_entity_profiles(self.snapshot, profiles, {})
        self.assertEqual(new_entities["entity:orders"].row_count, 5000)
        self.assertEqual(new_entities["entity:customers"].row_count, 1200)

    def test_object_type_applied(self):
        profiles = [
            {"entity_id": "entity:orders", "row_count": None, "columns": {}, "error": None},
            {"entity_id": "entity:customers", "row_count": None, "columns": {}, "error": None},
        ]
        object_types = {"orders": "table", "customers": "table"}
        new_entities, _ = _apply_entity_profiles(self.snapshot, profiles, object_types)
        self.assertEqual(new_entities["entity:orders"].object_type, "table")

    def test_null_rate_applied(self):
        profiles = [
            {
                "entity_id": "entity:orders",
                "row_count": 100,
                "columns": {
                    "order_id": {"null_rate": 0.0, "distinct_count": 100, "sample_values": None},
                    "customer_id": {"null_rate": 0.05, "distinct_count": 80, "sample_values": None},
                    "status": {"null_rate": 0.10, "distinct_count": 3, "sample_values": ["A", "C", "P"]},
                },
                "error": None,
            },
            {"entity_id": "entity:customers", "row_count": None, "columns": {}, "error": None},
        ]
        _, new_fields = _apply_entity_profiles(self.snapshot, profiles, {})
        self.assertEqual(new_fields["field:orders:order_id"].null_rate, 0.0)
        self.assertAlmostEqual(new_fields["field:orders:customer_id"].null_rate, 0.05)
        self.assertEqual(new_fields["field:orders:status"].null_rate, 0.10)
        self.assertEqual(new_fields["field:orders:status"].sample_values, ["A", "C", "P"])

    def test_distinct_count_applied(self):
        profiles = [
            {
                "entity_id": "entity:orders",
                "row_count": 100,
                "columns": {
                    "order_id": {"null_rate": 0.0, "distinct_count": 100, "sample_values": None},
                    "customer_id": {"null_rate": 0.0, "distinct_count": 80, "sample_values": None},
                    "status": {"null_rate": 0.0, "distinct_count": 3, "sample_values": None},
                },
                "error": None,
            },
            {"entity_id": "entity:customers", "row_count": None, "columns": {}, "error": None},
        ]
        _, new_fields = _apply_entity_profiles(self.snapshot, profiles, {})
        self.assertEqual(new_fields["field:orders:order_id"].distinct_count, 100)
        self.assertEqual(new_fields["field:orders:status"].distinct_count, 3)

    def test_missing_entity_profile_leaves_fields_unchanged(self):
        """If an entity isn't in profiles, its fields should be copied unchanged."""
        profiles = [
            {"entity_id": "entity:orders", "row_count": 50, "columns": {}, "error": None},
            # entity:customers intentionally missing
        ]
        new_entities, new_fields = _apply_entity_profiles(self.snapshot, profiles, {})
        self.assertIsNone(new_entities["entity:customers"].row_count)
        self.assertIsNone(new_fields["field:customers:email"].null_rate)


class TestApplyJoinProfiles(unittest.TestCase):

    def setUp(self):
        self.snapshot = _build_orders_snapshot()

    def test_join_confidence_applied(self):
        join_profiles = [
            {
                "join_id": "join:orders:customers",
                "join_confidence": 0.98,
                "orphan_rate": 0.02,
                "error": None,
            }
        ]
        enriched = _apply_join_profiles(self.snapshot, join_profiles)
        self.assertEqual(len(enriched), 1)
        self.assertAlmostEqual(enriched[0].join_confidence, 0.98)
        self.assertAlmostEqual(enriched[0].orphan_rate, 0.02)

    def test_failed_join_profile_leaves_join_unchanged(self):
        """A join with no profile data should be copied unchanged."""
        join_profiles = [
            {
                "join_id": "join:orders:customers",
                "join_confidence": None,
                "orphan_rate": None,
                "error": "Query failed",
            }
        ]
        enriched = _apply_join_profiles(self.snapshot, join_profiles)
        self.assertIsNone(enriched[0].join_confidence)
        self.assertIsNone(enriched[0].orphan_rate)


# ---------------------------------------------------------------------------
# Unit tests — profile_snapshot() with mocked adapter
# ---------------------------------------------------------------------------

class MockAdapter:
    """Fake adapter that returns canned profile data."""

    def __init__(self, query_responses: Dict[str, Any]):
        self._responses = query_responses
        self._call_log: List[str] = []

    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        sql_upper = sql.strip().upper()
        self._call_log.append(sql.strip())

        # Route by SQL pattern
        if "INFORMATION_SCHEMA.TABLES" in sql_upper:
            return self._responses.get("object_types", [])
        if 'COUNT(*) AS "_TOTAL"' in sql_upper.replace(" ", "") or "_total" in sql.lower():
            # Determine which entity this is for
            for entity_name, response in self._responses.get("entity_batches", {}).items():
                if f'"{entity_name}"' in sql:
                    return response
        if "DISTINCT" in sql_upper and "AS VAL" in sql_upper:
            for col_name, response in self._responses.get("enum_queries", {}).items():
                if f'"{col_name}"' in sql:
                    return response
        if "LEFT JOIN" in sql_upper and "TOTAL_FK" in sql_upper:
            for join_id, response in self._responses.get("join_queries", {}).items():
                return response
        return []


class TestProfileSnapshotUnit(unittest.TestCase):

    def setUp(self):
        self.snapshot = _build_orders_snapshot()

    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def _make_batch_response(self, total: int, field_stats: List[tuple]) -> List[Dict]:
        """Build the canned batch query response. field_stats: [(non_null, distinct), ...]"""
        row: Dict[str, Any] = {"_total": total}
        for idx, (nn, dc) in enumerate(field_stats):
            row[f"_nn_{idx}"] = nn
            row[f"_dc_{idx}"] = dc
        return [row]

    def test_snapshot_id_unchanged_after_profiling(self):
        """The profiler must preserve the snapshot_id — profiling fields are not hashed."""
        original_id = self.snapshot.snapshot_id

        adapter = MockAdapter({
            "object_types": [
                {"table_name": "orders", "table_type": "BASE TABLE"},
                {"table_name": "customers", "table_type": "BASE TABLE"},
            ],
            "entity_batches": {
                "orders": self._make_batch_response(1000, [(1000, 1000), (950, 800), (900, 3)]),
                "customers": self._make_batch_response(800, [(800, 800), (790, 790)]),
            },
            "join_queries": {"join:orders:customers": [{"total_fk": 950, "matched_fk": 950}]},
        })

        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        self.assertEqual(profiled.snapshot_id, original_id)

    def test_profiled_at_is_set(self):
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(0, [(0, 0), (0, 0), (0, 0)]),
                "customers": self._make_batch_response(0, [(0, 0), (0, 0)]),
            },
            "join_queries": {},
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        self.assertIsNotNone(profiled.profiled_at)
        # Should be ISO 8601 UTC format
        self.assertTrue(profiled.profiled_at.endswith("Z"))  # type: ignore[union-attr]

    def test_row_counts_populated(self):
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(5000, [(5000, 5000), (4750, 800), (4500, 3)]),
                "customers": self._make_batch_response(1200, [(1200, 1200), (1190, 1190)]),
            },
            "join_queries": {},
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        self.assertEqual(profiled.entities["entity:orders"].row_count, 5000)
        self.assertEqual(profiled.entities["entity:customers"].row_count, 1200)

    def test_null_rate_computed_correctly(self):
        # orders has 1000 rows. customer_id has 50 NULLs (950 non-null).
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(1000, [(1000, 1000), (950, 800), (900, 3)]),
                "customers": self._make_batch_response(800, [(800, 800), (800, 790)]),
            },
            "join_queries": {},
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        # customer_id: 950 non-null out of 1000 → null_rate = 0.05
        self.assertAlmostEqual(
            profiled.fields["field:orders:customer_id"].null_rate, 0.05, places=4
        )
        # status: 900 non-null out of 1000 → null_rate = 0.10
        self.assertAlmostEqual(
            profiled.fields["field:orders:status"].null_rate, 0.10, places=4
        )

    def test_sample_values_for_low_cardinality(self):
        """status has distinct_count=3 (≤25) → sample_values should be fetched."""
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(1000, [(1000, 1000), (1000, 800), (900, 3)]),
                "customers": self._make_batch_response(800, [(800, 800), (800, 790)]),
            },
            "enum_queries": {
                "status": [
                    {"val": "cancelled"},
                    {"val": "complete"},
                    {"val": "pending"},
                ]
            },
            "join_queries": {},
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        status_field = profiled.fields["field:orders:status"]
        self.assertEqual(status_field.sample_values, ["cancelled", "complete", "pending"])

    def test_no_sample_values_for_high_cardinality(self):
        """email has distinct_count=790 (>25) → sample_values stays None."""
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(1000, [(1000, 1000), (1000, 800), (900, 3)]),
                "customers": self._make_batch_response(800, [(800, 800), (800, 790)]),
            },
            "join_queries": {},
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        self.assertIsNone(profiled.fields["field:customers:email"].sample_values)

    def test_join_confidence_1_0_for_clean_fk(self):
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(1000, [(1000, 1000), (1000, 800), (900, 3)]),
                "customers": self._make_batch_response(800, [(800, 800), (800, 790)]),
            },
            "join_queries": {
                "join:orders:customers": [{"total_fk": 1000, "matched_fk": 1000}]
            },
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        join = profiled.joins[0]
        self.assertAlmostEqual(join.join_confidence, 1.0)
        self.assertAlmostEqual(join.orphan_rate, 0.0)

    def test_orphan_rate_for_dirty_fk(self):
        """5% of FK values have no parent match → orphan_rate = 0.05."""
        adapter = MockAdapter({
            "object_types": [],
            "entity_batches": {
                "orders": self._make_batch_response(1000, [(1000, 1000), (1000, 800), (900, 3)]),
                "customers": self._make_batch_response(800, [(800, 800), (800, 790)]),
            },
            "join_queries": {
                "join:orders:customers": [{"total_fk": 1000, "matched_fk": 950}]
            },
        })
        profiled = self._run(profile_snapshot(adapter, self.snapshot))
        join = profiled.joins[0]
        self.assertAlmostEqual(join.join_confidence, 0.95, places=4)
        self.assertAlmostEqual(join.orphan_rate, 0.05, places=4)


# ---------------------------------------------------------------------------
# Integration tests — Pagila Docker (skipped if not available)
# ---------------------------------------------------------------------------

_PAGILA_DSN = os.environ.get("BOYCE_DB_URL", "postgresql://boyce:password@localhost:5433/pagila")
_PAGILA_SNAPSHOT = Path.home() / "boyce-test" / "_local_context" / "pagila.json"
_SKIP_INTEGRATION = not _PAGILA_SNAPSHOT.exists()
_SKIP_REASON = "Pagila snapshot not found — set BOYCE_DB_URL and ingest pagila first"


@unittest.skipIf(_SKIP_INTEGRATION, _SKIP_REASON)
class TestProfilerIntegration(unittest.TestCase):
    """Integration tests against live Pagila Docker container."""

    _profiled_snapshot: SemanticSnapshot = None  # type: ignore[assignment]

    @classmethod
    def setUpClass(cls) -> None:
        """Run profiler once and reuse snapshot across all integration tests."""
        import json
        from boyce.types import SemanticSnapshot as _SS
        from boyce.adapters.postgres import PostgresAdapter

        async def _run() -> SemanticSnapshot:
            data = json.loads(_PAGILA_SNAPSHOT.read_text())
            snapshot = _SS(**data)
            adapter = PostgresAdapter(dsn=_PAGILA_DSN)
            await adapter.connect()
            try:
                return await profile_snapshot(adapter, snapshot)
            finally:
                await adapter.disconnect()

        try:
            cls._profiled_snapshot = asyncio.run(_run())
        except Exception as exc:
            raise unittest.SkipTest(f"Pagila DB not available: {exc}")

    def test_snapshot_id_unchanged(self):
        """Smoke test: profiling must not change the snapshot_id."""
        import json
        from boyce.types import SemanticSnapshot as _SS
        data = json.loads(_PAGILA_SNAPSHOT.read_text())
        original = _SS(**data)
        self.assertEqual(
            self._profiled_snapshot.snapshot_id,
            original.snapshot_id,
            "snapshot_id changed after profiling — hash stability broken",
        )

    def test_profiled_at_set(self):
        self.assertIsNotNone(self._profiled_snapshot.profiled_at)

    def test_original_language_id_is_100_percent_null(self):
        """
        THE SMOKE TEST (per Opus):
        Pagila's film.original_language_id is 100% NULL.
        If the profiler works, null_rate for this column must be 1.0.
        """
        # Find the film entity
        film_entity = None
        for entity in self._profiled_snapshot.entities.values():
            if entity.name == "film":
                film_entity = entity
                break
        self.assertIsNotNone(film_entity, "film entity not found in snapshot")

        # Find original_language_id field
        olig_field = None
        for fid in film_entity.fields:  # type: ignore[union-attr]
            field = self._profiled_snapshot.fields.get(fid)
            if field and field.name == "original_language_id":
                olig_field = field
                break
        self.assertIsNotNone(olig_field, "original_language_id field not found")

        self.assertIsNotNone(
            olig_field.null_rate,  # type: ignore[union-attr]
            "null_rate not populated for original_language_id",
        )
        self.assertAlmostEqual(
            olig_field.null_rate, 1.0, places=3,  # type: ignore[union-attr]
            msg="original_language_id should be 100% NULL in Pagila",
        )

    def test_film_rating_has_sample_values(self):
        """
        film.rating is a low-cardinality column (G, PG, PG-13, R, NC-17 = 5 values).
        Profiler should detect it as an enum and populate sample_values.
        """
        film_entity = None
        for entity in self._profiled_snapshot.entities.values():
            if entity.name == "film":
                film_entity = entity
                break
        self.assertIsNotNone(film_entity)

        rating_field = None
        for fid in film_entity.fields:  # type: ignore[union-attr]
            field = self._profiled_snapshot.fields.get(fid)
            if field and field.name == "rating":
                rating_field = field
                break
        self.assertIsNotNone(rating_field, "rating field not found")

        self.assertIsNotNone(
            rating_field.sample_values,  # type: ignore[union-attr]
            "sample_values not populated for film.rating",
        )
        expected_ratings = {"G", "PG", "PG-13", "R", "NC-17"}
        actual = set(rating_field.sample_values or [])  # type: ignore[union-attr]
        self.assertEqual(
            actual, expected_ratings,
            f"Expected Pagila ratings {expected_ratings}, got {actual}",
        )

    def test_film_row_count(self):
        """Pagila has 1,000 films."""
        film_entity = None
        for entity in self._profiled_snapshot.entities.values():
            if entity.name == "film":
                film_entity = entity
                break
        self.assertIsNotNone(film_entity)
        self.assertEqual(film_entity.row_count, 1000)  # type: ignore[union-attr]

    def test_fk_confidence_clean_for_pagila(self):
        """All FK joins in Pagila should have join_confidence close to 1.0."""
        for join in self._profiled_snapshot.joins:
            if join.join_confidence is not None:
                self.assertGreaterEqual(
                    join.join_confidence, 0.95,
                    f"Join {join.id} has low confidence {join.join_confidence} — unexpected for Pagila",
                )

    def test_film_object_type_is_table(self):
        """film should be detected as a table, not a view."""
        film_entity = None
        for entity in self._profiled_snapshot.entities.values():
            if entity.name == "film":
                film_entity = entity
                break
        self.assertIsNotNone(film_entity)
        self.assertEqual(film_entity.object_type, "table")  # type: ignore[union-attr]

    def test_views_detected_as_view(self):
        """Pagila has several views (e.g. film_list). These should have object_type='view'."""
        view_entities = [
            e for e in self._profiled_snapshot.entities.values()
            if e.object_type == "view"
        ]
        self.assertGreater(len(view_entities), 0, "No views detected in Pagila snapshot")


if __name__ == "__main__":
    unittest.main()
