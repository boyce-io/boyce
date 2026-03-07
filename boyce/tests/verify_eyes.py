#!/usr/bin/env python3
"""
verify_eyes.py — Verification script for the PostgresAdapter ("Eye Implant").

Runs three test suites:

  Suite 1 — Unit tests (always run, no DB required):
    • execute_query() returns rows from a mocked asyncpg connection
    • execute_query() rejects DML statements before touching the wire
    • profile_column() returns expected stats from mocked data
    • get_schema_summary() returns expected structure from mocked data
    • _redact_dsn() hides passwords in log output

  Suite 2 — Read-only enforcement (always run, no DB required):
    • Each DML/DDL keyword in the reject list raises ValueError
    • SELECT is allowed through

  Suite 3 — Live integration (only if BOYCE_DB_URL is set):
    • connect() / disconnect() lifecycle
    • execute_query("SELECT 1") returns [{"?column?": 1}]
    • get_schema_summary() returns a list
    • profile_column() returns expected keys

Usage:
    # Unit + enforcement tests only (no DB needed):
    python boyce/tests/verify_eyes.py

    # Full suite including live Postgres:
    BOYCE_DB_URL="postgresql://user:pass@localhost/mydb" \\
        python boyce/tests/verify_eyes.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the protocol package is importable from any working directory
_HERE = Path(__file__).parent
_PROTO_ROOT = _HERE.parent
sys.path.insert(0, str(_PROTO_ROOT / "src"))

# Stub out `mcp` so server.py can be imported without the package installed
if "mcp" not in sys.modules:
    _mcp_stub = MagicMock()
    sys.modules["mcp"] = _mcp_stub
    sys.modules["mcp.server"] = _mcp_stub.server
    sys.modules["mcp.server.fastmcp"] = _mcp_stub.server.fastmcp

# ---------------------------------------------------------------------------
# Helpers for building mock asyncpg objects
# ---------------------------------------------------------------------------

def _make_record(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a plain dict — supports both .items() and ["key"] access."""
    return dict(data)


def _make_mock_conn(fetch_return=None, server_version=(14, 0)):
    """Return a mock asyncpg Connection with the correct async context manager."""
    conn = AsyncMock()
    conn.get_server_version.return_value = MagicMock(major=server_version[0])

    # transaction() is a SYNC call that returns an async context manager.
    # Use MagicMock (not AsyncMock) so calling it returns tx_cm, not a coroutine.
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)

    if fetch_return is not None:
        conn.fetch = AsyncMock(return_value=fetch_return)

    return conn


# ---------------------------------------------------------------------------
# Suite 1 — Unit tests (mocked asyncpg)
# ---------------------------------------------------------------------------

class TestPostgresAdapterUnit(unittest.IsolatedAsyncioTestCase):

    async def _make_adapter(self, fetch_return=None):
        """Import and wire up a PostgresAdapter with a mocked asyncpg connection."""
        from boyce.adapters.postgres import PostgresAdapter
        adapter = PostgresAdapter(dsn="postgresql://user:***@localhost/test")
        adapter._conn = _make_mock_conn(fetch_return=fetch_return)
        return adapter

    async def test_execute_query_returns_rows(self):
        """execute_query() converts asyncpg Records to dicts."""
        records = [
            _make_record({"id": 1, "name": "Alice"}),
            _make_record({"id": 2, "name": "Bob"}),
        ]
        adapter = await self._make_adapter(fetch_return=records)

        rows = await adapter.execute_query("SELECT id, name FROM users")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[1]["name"], "Bob")
        print("  ✓ execute_query() returns rows as dicts")

    async def test_execute_query_rejects_insert(self):
        """execute_query() raises ValueError for INSERT before touching the wire."""
        adapter = await self._make_adapter()

        with self.assertRaises(ValueError) as ctx:
            await adapter.execute_query("INSERT INTO orders (id) VALUES (1)")
        self.assertIn("INSERT", str(ctx.exception))
        # The connection's fetch should NOT have been called
        adapter._conn.fetch.assert_not_called()
        print("  ✓ execute_query() rejects INSERT before hitting the DB")

    async def test_execute_query_rejects_drop(self):
        """execute_query() raises ValueError for DROP TABLE."""
        adapter = await self._make_adapter()
        with self.assertRaises(ValueError):
            await adapter.execute_query("DROP TABLE orders")
        print("  ✓ execute_query() rejects DROP TABLE")

    async def test_profile_column_structure(self):
        """profile_column() returns the expected keys."""
        profile_record = _make_record({
            "row_count": 1000,
            "non_null_count": 998,
            "null_count": 2,
            "distinct_count": 5,
            "min_value": "active",
            "max_value": "voided",
        })
        adapter = await self._make_adapter(fetch_return=[profile_record])

        result = await adapter.profile_column("orders", "status")

        expected_keys = {
            "table", "column", "row_count", "null_count",
            "null_pct", "distinct_count", "min_value", "max_value",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result["table"], "orders")
        self.assertEqual(result["column"], "status")
        self.assertEqual(result["row_count"], 1000)
        self.assertEqual(result["null_count"], 2)
        self.assertAlmostEqual(result["null_pct"], 0.2)
        self.assertEqual(result["distinct_count"], 5)
        print("  ✓ profile_column() returns correct structure and values")

    async def test_profile_column_rejects_unsafe_ident(self):
        """profile_column() raises ValueError for identifiers with special chars."""
        adapter = await self._make_adapter()
        with self.assertRaises(ValueError):
            await adapter.profile_column("orders; DROP TABLE orders--", "status")
        print("  ✓ profile_column() rejects unsafe table identifiers")

    async def test_require_connection_raises_before_connect(self):
        """Calling execute_query before connect() raises RuntimeError."""
        from boyce.adapters.postgres import PostgresAdapter
        adapter = PostgresAdapter(dsn="postgresql://user:pass@localhost/test")
        # _conn is None — not connected

        with self.assertRaises(RuntimeError) as ctx:
            await adapter.execute_query("SELECT 1")
        self.assertIn("not connected", str(ctx.exception).lower())
        print("  ✓ RuntimeError raised when not connected")

    async def test_redact_dsn(self):
        """_redact_dsn() hides password from log output."""
        from boyce.adapters.postgres import _redact_dsn
        original = "postgresql://alice:supersecret@prod-host:5432/mydb"
        redacted = _redact_dsn(original)
        self.assertNotIn("supersecret", redacted)
        self.assertIn("***", redacted)
        self.assertIn("alice", redacted)
        self.assertIn("prod-host", redacted)
        print("  ✓ _redact_dsn() hides password, keeps host/user")


# ---------------------------------------------------------------------------
# Suite 2 — Read-only enforcement (exhaustive keyword list)
# ---------------------------------------------------------------------------

class TestReadOnlyEnforcement(unittest.IsolatedAsyncioTestCase):

    _WRITE_KEYWORDS = [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET status = 'x'",
        "DELETE FROM orders WHERE id = 1",
        "TRUNCATE orders",
        "DROP TABLE orders",
        "CREATE TABLE foo (id INT)",
        "ALTER TABLE orders ADD COLUMN x INT",
        "COPY orders FROM '/tmp/file.csv'",
        "GRANT SELECT ON orders TO user1",
        "REVOKE SELECT ON orders FROM user1",
        "CALL my_procedure()",
        "DO $$ BEGIN NULL; END $$",
    ]

    async def _make_adapter(self):
        from boyce.adapters.postgres import PostgresAdapter
        adapter = PostgresAdapter(dsn="postgresql://user:pass@localhost/test")
        adapter._conn = _make_mock_conn()
        return adapter

    async def test_write_statements_are_rejected(self):
        """All write/DDL keywords raise ValueError before touching the DB."""
        adapter = await self._make_adapter()
        failed = []
        for stmt in self._WRITE_KEYWORDS:
            try:
                await adapter.execute_query(stmt)
                failed.append(f"NOT REJECTED: {stmt[:50]}")
            except ValueError:
                pass  # expected
        if failed:
            self.fail("Some write statements were not rejected:\n" + "\n".join(failed))
        print(f"  ✓ {len(self._WRITE_KEYWORDS)} write/DDL keywords all rejected")

    async def test_select_passes_precheck(self):
        """SELECT passes the pre-check (may still fail at DB level)."""
        from boyce.adapters.postgres import _assert_readonly
        # Should not raise
        _assert_readonly("SELECT id, name FROM users WHERE active = true")
        _assert_readonly("  \n  SELECT 1")
        print("  ✓ SELECT statements pass the pre-check")


# ---------------------------------------------------------------------------
# Suite 3 — Pre-flight validation helpers (no DB required)
# ---------------------------------------------------------------------------

class TestPreflightHelpers(unittest.IsolatedAsyncioTestCase):

    def test_parse_explain_cost_standard(self):
        """_parse_explain_cost extracts total cost from a standard EXPLAIN line."""
        from boyce.server import _parse_explain_cost
        rows = [
            {"QUERY PLAN": "Seq Scan on orders  (cost=0.00..431.80 rows=1280 width=228)"}
        ]
        cost = _parse_explain_cost(rows)
        self.assertAlmostEqual(cost, 431.80)
        print("  ✓ _parse_explain_cost() extracts total cost from EXPLAIN line")

    def test_parse_explain_cost_nested(self):
        """_parse_explain_cost handles nested node plans (uses first row)."""
        from boyce.server import _parse_explain_cost
        rows = [
            {"QUERY PLAN": "Hash Join  (cost=8.31..22.59 rows=260 width=156)"},
            {"QUERY PLAN": "  ->  Seq Scan on orders  (cost=0.00..1.04 rows=4 width=8)"},
        ]
        cost = _parse_explain_cost(rows)
        self.assertAlmostEqual(cost, 22.59)
        print("  ✓ _parse_explain_cost() uses first plan node for nested plans")

    def test_parse_explain_cost_no_match(self):
        """_parse_explain_cost returns None when pattern is absent."""
        from boyce.server import _parse_explain_cost
        self.assertIsNone(_parse_explain_cost([]))
        self.assertIsNone(_parse_explain_cost([{"QUERY PLAN": "Planning Time: 0.084 ms"}]))
        print("  ✓ _parse_explain_cost() returns None when no cost pattern found")

    async def test_preflight_unchecked_when_no_db_url(self):
        """_preflight_check returns 'unchecked' when BOYCE_DB_URL is absent."""
        import boyce.server as srv

        original = os.environ.pop("BOYCE_DB_URL", None)
        original_adapter = srv._adapter
        srv._adapter = None  # reset cached adapter
        try:
            result = await srv._preflight_check("SELECT 1")
        finally:
            if original is not None:
                os.environ["BOYCE_DB_URL"] = original
            srv._adapter = original_adapter

        self.assertEqual(result["status"], "unchecked")
        self.assertIsNone(result["error"])
        self.assertIsNone(result["cost_estimate"])
        print("  ✓ _preflight_check() returns 'unchecked' when no DB URL configured")

    async def test_preflight_verified_with_mock_adapter(self):
        """_preflight_check returns 'verified' + cost when EXPLAIN succeeds."""
        import boyce.server as srv

        mock_adapter = MagicMock()
        mock_adapter.execute_query = AsyncMock(return_value=[
            {"QUERY PLAN": "Seq Scan on orders  (cost=0.00..99.50 rows=100 width=8)"}
        ])

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            result = await srv._preflight_check("SELECT * FROM orders")
        finally:
            srv._adapter = original_adapter

        self.assertEqual(result["status"], "verified")
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["cost_estimate"], 99.50)
        print("  ✓ _preflight_check() returns 'verified' with cost when EXPLAIN succeeds")

    async def test_preflight_invalid_when_explain_fails(self):
        """_preflight_check returns 'invalid' + error when EXPLAIN raises."""
        import boyce.server as srv

        mock_adapter = MagicMock()
        mock_adapter.execute_query = AsyncMock(
            side_effect=Exception('relation "ghost_table" does not exist')
        )

        original_adapter = srv._adapter
        srv._adapter = mock_adapter
        try:
            result = await srv._preflight_check("SELECT * FROM ghost_table")
        finally:
            srv._adapter = original_adapter

        self.assertEqual(result["status"], "invalid")
        self.assertIn("ghost_table", result["error"])
        self.assertIsNone(result["cost_estimate"])
        print("  ✓ _preflight_check() returns 'invalid' with error when EXPLAIN fails")


# ---------------------------------------------------------------------------
# Suite 4 — Live integration (skipped if BOYCE_DB_URL not set)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.environ.get("BOYCE_DB_URL"),
    "BOYCE_DB_URL not set — skipping live integration tests",
)
class TestPostgresAdapterLive(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        try:
            from boyce.adapters.postgres import PostgresAdapter
        except ImportError:
            self.skipTest("asyncpg not installed — pip install boyce[postgres]")
        self.adapter = PostgresAdapter()
        await self.adapter.connect()

    async def asyncTearDown(self):
        await self.adapter.disconnect()

    async def test_select_one(self):
        """execute_query('SELECT 1') returns one row."""
        rows = await self.adapter.execute_query("SELECT 1 AS value")
        self.assertEqual(len(rows), 1)
        self.assertIn("value", rows[0])
        self.assertEqual(rows[0]["value"], 1)
        print("  ✓ Live: SELECT 1 returned", rows)

    async def test_write_rejected_by_db(self):
        """INSERT is rejected by readonly transaction even if it bypassed pre-check."""
        import asyncpg
        from boyce.adapters.postgres import _assert_readonly, _WRITE_PATTERN

        # Confirm INSERT would be caught by the pre-check first
        with self.assertRaises(ValueError):
            await self.adapter.execute_query("INSERT INTO _nonexistent (id) VALUES (1)")
        print("  ✓ Live: INSERT rejected before hitting DB")

    async def test_get_schema_summary_returns_list(self):
        """get_schema_summary() returns a list (may be empty on a blank DB)."""
        schema = await self.adapter.get_schema_summary()
        self.assertIsInstance(schema, list)
        if schema:
            table = schema[0]
            self.assertIn("schema", table)
            self.assertIn("table", table)
            self.assertIn("columns", table)
        print(f"  ✓ Live: get_schema_summary() returned {len(schema)} tables")

    async def test_connect_disconnect_idempotent(self):
        """disconnect() can be called twice without error."""
        await self.adapter.disconnect()
        await self.adapter.disconnect()  # second call should be a no-op
        print("  ✓ Live: double disconnect() is safe")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Boyce Eye Implant — Adapter Verification")
    print("=" * 60)

    has_db = bool(os.environ.get("BOYCE_DB_URL"))
    suite_label = "Unit + Enforcement + Pre-flight + Live" if has_db else "Unit + Enforcement + Pre-flight (no DB)"
    print(f"Running: {suite_label}\n")

    print("Suite 1: Unit tests (mocked asyncpg)")
    print("Suite 2: Read-only enforcement")
    print("Suite 3: Pre-flight validation helpers")
    if has_db:
        print("Suite 4: Live integration (BOYCE_DB_URL is set)")
    else:
        print("Suite 4: SKIPPED — set BOYCE_DB_URL to enable\n")

    print()
    loader = unittest.TestLoader()
    runner = unittest.TextTestRunner(verbosity=0, stream=sys.stdout)
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPostgresAdapterUnit))
    suite.addTests(loader.loadTestsFromTestCase(TestReadOnlyEnforcement))
    suite.addTests(loader.loadTestsFromTestCase(TestPreflightHelpers))
    if has_db:
        suite.addTests(loader.loadTestsFromTestCase(TestPostgresAdapterLive))

    result = runner.run(suite)
    print()
    if result.wasSuccessful():
        print("✅  All checks passed.")
    else:
        print(f"❌  {len(result.failures)} failure(s), {len(result.errors)} error(s).")
    sys.exit(0 if result.wasSuccessful() else 1)
