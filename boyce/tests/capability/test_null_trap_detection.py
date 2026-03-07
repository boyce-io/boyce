"""
Capability Test: NULL Trap Detection

Scenario: A table has a "status" column where 30% of rows are NULL.
A query filters WHERE status = 'active'. That silently excludes every NULL row
from the result — the analyst never sees them, never knows they existed.

A junior analyst runs the query and reports "500 active users."
A staff engineer runs the query and says: "500 active, but 300 rows have NULL status —
are those active users whose status wasn't set, or are they something else? We need
to investigate before this number goes in the board deck."

The NULL trap detector IS the staff engineer behavior.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Ensure importability
_HERE = Path(__file__).parent
_PROTO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROTO_ROOT))

# Stub mcp if not installed
if "mcp" not in sys.modules:
    _mcp_stub = MagicMock()
    sys.modules["mcp"] = _mcp_stub
    sys.modules["mcp.server"] = _mcp_stub.server
    sys.modules["mcp.server.fastmcp"] = _mcp_stub.server.fastmcp

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    SemanticSnapshot,
)


def _build_orders_snapshot() -> SemanticSnapshot:
    """Build a snapshot representing the classic NULL trap scenario.

    Table: orders (1000 rows)
        - id: INTEGER PK
        - status: VARCHAR (nullable) — 30% NULL
        - revenue: DECIMAL
    """
    return SemanticSnapshot(
        snapshot_id="test-null-trap-001",
        source_system="test",
        source_version="1.0",
        entities={
            "entity:orders": Entity(
                id="entity:orders",
                name="orders",
                schema_name="public",
                fields=[
                    "field:orders:id",
                    "field:orders:status",
                    "field:orders:revenue",
                ],
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
                nullable=False,
                primary_key=True,
            ),
            "field:orders:status": FieldDef(
                id="field:orders:status",
                entity_id="entity:orders",
                name="status",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR",
                nullable=True,
                primary_key=False,
            ),
            "field:orders:revenue": FieldDef(
                id="field:orders:revenue",
                entity_id="entity:orders",
                name="revenue",
                field_type=FieldType.MEASURE,
                data_type="DECIMAL",
                nullable=False,
                primary_key=False,
            ),
        },
        joins=[],
        metadata={"source_type": "test"},
    )


class TestNullTrapDetection(unittest.IsolatedAsyncioTestCase):
    """Does the system catch silent NULL exclusion in equality filters?"""

    async def test_warns_when_null_pct_exceeds_threshold(self):
        """30% NULL on a filtered column MUST trigger a warning."""
        import boyce.server as srv

        snapshot = _build_orders_snapshot()

        structured_filter = {
            "concept_map": {
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    }
                ],
            },
        }

        # Mock adapter: profile_column returns 30% NULL
        mock_adapter = MagicMock()
        mock_adapter.profile_column = AsyncMock(return_value={
            "table": "public.orders",
            "column": "status",
            "row_count": 1000,
            "null_count": 300,
            "null_pct": 30.0,
            "distinct_count": 3,
            "min_value": "active",
            "max_value": "voided",
        })

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            warnings = await srv._null_trap_check(snapshot, structured_filter)
        finally:
            srv._adapter = original_adapter

        # Staff engineer behavior: there MUST be a warning
        self.assertEqual(len(warnings), 1, "Expected exactly one NULL trap warning")

        w = warnings[0]
        self.assertEqual(w["column"], "status")
        self.assertAlmostEqual(w["null_pct"], 30.0)
        self.assertEqual(w["null_count"], 300)
        self.assertEqual(w["row_count"], 1000)
        self.assertEqual(w["filter_value"], "active")
        self.assertIn("NULL", w["risk"])
        self.assertIn("300", w["risk"])

    async def test_silent_when_null_pct_below_threshold(self):
        """1% NULL is normal — no warning needed."""
        import boyce.server as srv

        snapshot = _build_orders_snapshot()

        structured_filter = {
            "concept_map": {
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    }
                ],
            },
        }

        mock_adapter = MagicMock()
        mock_adapter.profile_column = AsyncMock(return_value={
            "table": "public.orders",
            "column": "status",
            "row_count": 1000,
            "null_count": 10,
            "null_pct": 1.0,
            "distinct_count": 3,
            "min_value": "active",
            "max_value": "voided",
        })

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            warnings = await srv._null_trap_check(snapshot, structured_filter)
        finally:
            srv._adapter = original_adapter

        self.assertEqual(len(warnings), 0, "1% NULL should not trigger a warning")

    async def test_ignores_non_equality_filters(self):
        """A > operator doesn't silently exclude NULLs the same way = does.
        (NULLs are excluded too, but that's expected with range comparisons.)
        The NULL trap specifically targets = because users expect it to be exhaustive."""
        import boyce.server as srv

        snapshot = _build_orders_snapshot()

        structured_filter = {
            "concept_map": {
                "filters": [
                    {
                        "field_id": "field:orders:revenue",
                        "operator": ">",
                        "value": 100,
                        "entity_id": "entity:orders",
                    }
                ],
            },
        }

        mock_adapter = MagicMock()
        # Should never be called — non-equality filters are skipped
        mock_adapter.profile_column = AsyncMock()

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            warnings = await srv._null_trap_check(snapshot, structured_filter)
        finally:
            srv._adapter = original_adapter

        self.assertEqual(len(warnings), 0, "Non-equality filters should not trigger NULL trap check")
        mock_adapter.profile_column.assert_not_called()

    async def test_no_db_returns_empty_gracefully(self):
        """Without a live DB, the system can't profile — but it must not crash."""
        import boyce.server as srv

        snapshot = _build_orders_snapshot()
        structured_filter = {
            "concept_map": {
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    }
                ],
            },
        }

        original_adapter = srv._adapter
        srv._adapter = None
        try:
            warnings = await srv._null_trap_check(snapshot, structured_filter)
        finally:
            srv._adapter = original_adapter

        self.assertEqual(len(warnings), 0, "No DB should return empty warnings, not crash")

    async def test_multiple_equality_filters_checked_independently(self):
        """Each equality filter column is profiled independently.
        A staff engineer checks every one, not just the first."""
        import boyce.server as srv

        snapshot = SemanticSnapshot(
            snapshot_id="test-null-trap-multi",
            source_system="test",
            source_version="1.0",
            entities={
                "entity:orders": Entity(
                    id="entity:orders",
                    name="orders",
                    schema_name="public",
                    fields=[
                        "field:orders:id",
                        "field:orders:status",
                        "field:orders:region",
                    ],
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
                "field:orders:status": FieldDef(
                    id="field:orders:status",
                    entity_id="entity:orders",
                    name="status",
                    field_type=FieldType.DIMENSION,
                    data_type="VARCHAR",
                    nullable=True,
                ),
                "field:orders:region": FieldDef(
                    id="field:orders:region",
                    entity_id="entity:orders",
                    name="region",
                    field_type=FieldType.DIMENSION,
                    data_type="VARCHAR",
                    nullable=True,
                ),
            },
            joins=[],
        )

        structured_filter = {
            "concept_map": {
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    },
                    {
                        "field_id": "field:orders:region",
                        "operator": "=",
                        "value": "US",
                        "entity_id": "entity:orders",
                    },
                ],
            },
        }

        call_count = 0

        async def mock_profile(table, column):
            nonlocal call_count
            call_count += 1
            if column == "status":
                return {
                    "table": table, "column": column,
                    "row_count": 1000, "null_count": 300,
                    "null_pct": 30.0, "distinct_count": 3,
                    "min_value": "active", "max_value": "voided",
                }
            else:  # region — clean, no trap
                return {
                    "table": table, "column": column,
                    "row_count": 1000, "null_count": 5,
                    "null_pct": 0.5, "distinct_count": 10,
                    "min_value": "APAC", "max_value": "US",
                }

        mock_adapter = MagicMock()
        mock_adapter.profile_column = AsyncMock(side_effect=mock_profile)

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            warnings = await srv._null_trap_check(snapshot, structured_filter)
        finally:
            srv._adapter = original_adapter

        # Both columns checked
        self.assertEqual(call_count, 2, "Both equality-filtered columns must be profiled")
        # Only status triggers warning
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["column"], "status")

    async def test_profile_failure_non_fatal(self):
        """If profiling a column fails (permissions, table doesn't exist yet),
        the system continues with other filters. A staff engineer doesn't
        give up because one table was locked."""
        import boyce.server as srv

        snapshot = _build_orders_snapshot()
        structured_filter = {
            "concept_map": {
                "filters": [
                    {
                        "field_id": "field:orders:status",
                        "operator": "=",
                        "value": "active",
                        "entity_id": "entity:orders",
                    }
                ],
            },
        }

        mock_adapter = MagicMock()
        mock_adapter.profile_column = AsyncMock(
            side_effect=Exception("permission denied for table orders")
        )

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            warnings = await srv._null_trap_check(snapshot, structured_filter)
        finally:
            srv._adapter = original_adapter

        # Graceful degradation: empty warnings, no crash
        self.assertEqual(len(warnings), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
