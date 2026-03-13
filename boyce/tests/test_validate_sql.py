"""
Tests for validate_sql, _scan_null_risk, and schema freshness helpers.

All tests are offline: no DB required.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import boyce.server as srv
from boyce.audit import AuditLog
from boyce.graph import SemanticGraph
from boyce.store import DefinitionStore, SnapshotStore
from boyce.types import SemanticSnapshot
from boyce.validation import _compute_snapshot_hash


# ---------------------------------------------------------------------------
# Snapshot fixture (orders table with nullable status column)
# ---------------------------------------------------------------------------


def _make_nullable_snapshot() -> SemanticSnapshot:
    """Build a minimal SemanticSnapshot with a nullable 'status' column."""
    base = {
        "snapshot_id": "placeholder",
        "source_system": "test",
        "entities": {
            "entity:orders": {
                "id": "entity:orders",
                "name": "orders",
                "grain": "ORDER",
                "fields": ["field:orders:id", "field:orders:status", "field:orders:revenue"],
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
                "nullable": False,
            },
            "field:orders:status": {
                "id": "field:orders:status",
                "entity_id": "entity:orders",
                "name": "status",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(50)",
                "nullable": True,   # <-- this is the trap
            },
            "field:orders:revenue": {
                "id": "field:orders:revenue",
                "entity_id": "entity:orders",
                "name": "revenue",
                "field_type": "MEASURE",
                "data_type": "DECIMAL(10,2)",
                "nullable": False,
            },
        },
        "joins": [],
    }
    tmp = SemanticSnapshot(**base)
    correct_id = _compute_snapshot_hash(tmp)
    base["snapshot_id"] = correct_id
    return SemanticSnapshot(**base)


@pytest.fixture
def wired_server(tmp_path):
    snap = _make_nullable_snapshot()
    store = SnapshotStore(tmp_path)
    store.save(snap, "default")
    graph = SemanticGraph()
    defs = DefinitionStore(tmp_path)
    audit = AuditLog(tmp_path)

    with (
        patch.object(srv, "_store", store),
        patch.object(srv, "_definitions", defs),
        patch.object(srv, "_graph", graph),
        patch.object(srv, "_audit", audit),
        patch.object(srv, "_adapter", None),
        # Reset session-level caches between tests
        patch.object(srv, "_freshness_checked", set()),
        patch.object(srv, "_drift_checked", set()),
    ):
        yield snap, tmp_path


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# validate_sql tests
# ---------------------------------------------------------------------------


def test_validate_sql_basic(wired_server):
    """Valid SQL, no DB → unchecked status, no errors."""
    result = json.loads(_run(srv.validate_sql("SELECT id FROM orders", "default")))
    assert "error" not in result
    assert result["sql"] == "SELECT id FROM orders"
    assert result["validation"]["status"] == "unchecked"
    assert result["snapshot_name"] == "default"


def test_validate_sql_empty(wired_server):
    """Empty SQL → error response."""
    result = json.loads(_run(srv.validate_sql("", "default")))
    assert "error" in result
    assert result["error"]["code"] == -32602


def test_validate_sql_whitespace_only(wired_server):
    """Whitespace-only SQL → error response."""
    result = json.loads(_run(srv.validate_sql("   ", "default")))
    assert "error" in result


def test_validate_sql_compat_risks(wired_server):
    """SQL with LATERAL → compat risk returned for redshift dialect."""
    sql = "SELECT o.id FROM orders o, LATERAL (SELECT 1) AS sub"
    result = json.loads(_run(srv.validate_sql(sql, "default", dialect="redshift")))
    assert "compat_risks" in result
    assert any("LATERAL" in str(r) for r in result["compat_risks"])


def test_validate_sql_no_compat_risks_for_postgres(wired_server):
    """LATERAL in postgres dialect → no compat risks (postgres supports it)."""
    sql = "SELECT o.id FROM orders o, LATERAL (SELECT 1) AS sub"
    result = json.loads(_run(srv.validate_sql(sql, "default", dialect="postgres")))
    # No compat_risks key when empty (lint not run for non-redshift dialects)
    assert "compat_risks" not in result or result.get("compat_risks") == []


def test_validate_sql_null_risk(wired_server):
    """SQL with WHERE status = 'active' against nullable column → null_risk_columns populated."""
    sql = "SELECT id FROM orders WHERE status = 'active'"
    result = json.loads(_run(srv.validate_sql(sql, "default")))
    assert "null_risk_columns" in result
    risks = result["null_risk_columns"]
    assert len(risks) >= 1
    assert risks[0]["column"] == "status"
    assert risks[0]["nullable"] is True


def test_validate_sql_no_null_risk_for_non_nullable(wired_server):
    """WHERE on non-nullable column → no null_risk_columns."""
    sql = "SELECT id FROM orders WHERE id = '1'"
    result = json.loads(_run(srv.validate_sql(sql, "default")))
    assert "null_risk_columns" not in result or result.get("null_risk_columns") == []


def test_validate_sql_no_snapshot(wired_server):
    """Invalid snapshot_name → empty null_risk_columns, no error."""
    sql = "SELECT id FROM orders WHERE status = 'active'"
    result = json.loads(_run(srv.validate_sql(sql, "nonexistent_snapshot")))
    assert "error" not in result
    assert "null_risk_columns" not in result


def test_validate_sql_table_qualified_null_risk(wired_server):
    """Table-qualified column pattern: orders.status = 'active' → detected."""
    sql = "SELECT id FROM orders WHERE orders.status = 'active'"
    result = json.loads(_run(srv.validate_sql(sql, "default")))
    assert "null_risk_columns" in result
    assert result["null_risk_columns"][0]["column"] == "status"


def test_validate_sql_audit_logged(wired_server, tmp_path):
    """validate_sql always writes an audit entry."""
    snap, tmp_path = wired_server
    audit = AuditLog(tmp_path)
    with patch.object(srv, "_audit", audit):
        _run(srv.validate_sql("SELECT 1", "default"))
    entries = audit.tail(10)
    assert len(entries) >= 1
    assert entries[-1]["query"] == "[validate_sql]"


# ---------------------------------------------------------------------------
# Schema freshness Tier 2 tests (_check_snapshot_freshness)
# ---------------------------------------------------------------------------


def test_freshness_check_no_source_path(wired_server, tmp_path):
    """Snapshot without source_path in metadata → returns None."""
    snap, tmp_path = wired_server
    store = SnapshotStore(tmp_path)
    # snap has no source_path (it's a test snapshot with no metadata)
    freshness_checked: set = set()
    with patch.object(srv, "_freshness_checked", freshness_checked):
        result = srv._check_snapshot_freshness("default")
    assert result is None


def test_freshness_check_fresh(tmp_path):
    """Source mtime < snapshot mtime → returns None (fresh)."""
    from boyce.types import SemanticSnapshot
    from boyce.validation import _compute_snapshot_hash

    # Create source file
    source_file = tmp_path / "schema.sql"
    source_file.write_text("CREATE TABLE orders (id INT);")

    # Build snapshot with source_path
    base = {
        "snapshot_id": "placeholder",
        "source_system": "test",
        "entities": {},
        "fields": {},
        "joins": [],
        "metadata": {"source_path": str(source_file)},
    }
    tmp_snap = SemanticSnapshot(**base)
    real_id = _compute_snapshot_hash(tmp_snap)
    base["snapshot_id"] = real_id
    snap = SemanticSnapshot(**base)

    store = SnapshotStore(tmp_path)
    store.save(snap, "fresh_test")

    # Make source file older than snapshot (set mtime to past)
    old_time = time.time() - 3600
    import os
    os.utime(source_file, (old_time, old_time))

    audit = AuditLog(tmp_path)
    freshness_checked: set = set()
    with (
        patch.object(srv, "_store", store),
        patch.object(srv, "_graph", SemanticGraph()),
        patch.object(srv, "_audit", audit),
        patch.object(srv, "_freshness_checked", freshness_checked),
        patch.object(srv, "_LOCAL_CONTEXT", tmp_path),
    ):
        result = srv._check_snapshot_freshness("fresh_test")
    assert result is None


def test_freshness_check_once_per_session(wired_server):
    """Second call for same snapshot returns None (cached)."""
    snap, tmp_path = wired_server
    freshness_checked: set = set()
    with patch.object(srv, "_freshness_checked", freshness_checked):
        # First call
        srv._check_snapshot_freshness("default")
        # Add to cache manually to simulate first call completing
        freshness_checked.add("default")
        # Second call should return None immediately
        result = srv._check_snapshot_freshness("default")
    assert result is None


# ---------------------------------------------------------------------------
# Schema freshness Tier 3 tests (_check_db_drift)
# ---------------------------------------------------------------------------


def test_drift_check_no_adapter(wired_server):
    """No BOYCE_DB_URL → returns None."""
    snap, tmp_path = wired_server
    # _adapter is already patched to None in the fixture
    drift_checked: set = set()
    with patch.object(srv, "_drift_checked", drift_checked):
        result = _run(srv._check_db_drift("default"))
    assert result is None


def test_drift_check_once_per_session(wired_server):
    """Second call for same snapshot returns None (cached)."""
    snap, tmp_path = wired_server
    drift_checked: set = {"default"}  # Pre-populate cache
    with patch.object(srv, "_drift_checked", drift_checked):
        result = _run(srv._check_db_drift("default"))
    assert result is None
