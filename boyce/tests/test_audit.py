"""
Tests for boyce.audit.AuditLog
"""

import json
from pathlib import Path

import pytest

from boyce.audit import AuditLog


@pytest.fixture
def log(tmp_path):
    return AuditLog(tmp_path)


def test_log_creates_file(log, tmp_path):
    log.log_query(
        query="revenue by product",
        snapshot_name="default",
        snapshot_id="abc123",
        sql="SELECT product, SUM(revenue) FROM orders GROUP BY 1",
        entities_resolved=["orders"],
        validation_status="unchecked",
    )
    assert (tmp_path / "audit.jsonl").exists()


def test_log_is_valid_json(log, tmp_path):
    log.log_query(
        query="total users",
        snapshot_name="default",
        snapshot_id="abc123",
        sql="SELECT COUNT(*) FROM users",
        entities_resolved=["users"],
        validation_status="verified",
    )
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["query"] == "total users"
    assert record["validation_status"] == "verified"


def test_log_appends_multiple_records(log, tmp_path):
    for i in range(3):
        log.log_query(
            query=f"query {i}",
            snapshot_name="default",
            snapshot_id="abc",
            sql=f"SELECT {i}",
            entities_resolved=[],
            validation_status="unchecked",
        )
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3


def test_log_record_has_timestamp(log, tmp_path):
    log.log_query(
        query="test", snapshot_name="s", snapshot_id="x",
        sql="SELECT 1", entities_resolved=[], validation_status="unchecked",
    )
    record = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert "ts" in record
    assert "T" in record["ts"]  # ISO format


def test_log_truncates_snapshot_id(log, tmp_path):
    full_id = "a" * 64
    log.log_query(
        query="test", snapshot_name="s", snapshot_id=full_id,
        sql="SELECT 1", entities_resolved=[], validation_status="unchecked",
    )
    record = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert record["snapshot_id"] == "a" * 16


def test_log_truncates_long_sql(log, tmp_path):
    long_sql = "SELECT " + "x, " * 1000 + "y FROM t"
    log.log_query(
        query="test", snapshot_name="s", snapshot_id="x",
        sql=long_sql, entities_resolved=[], validation_status="unchecked",
    )
    record = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert len(record["sql"]) <= 2000


def test_log_records_error(log, tmp_path):
    log.log_query(
        query="bad query", snapshot_name="s", snapshot_id="x",
        sql="", entities_resolved=[], validation_status="unchecked",
        error="Planner: entity not found",
    )
    record = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert record["error"] == "Planner: entity not found"


def test_log_null_trap_and_compat_counts(log, tmp_path):
    log.log_query(
        query="test", snapshot_name="s", snapshot_id="x",
        sql="SELECT 1", entities_resolved=[],
        validation_status="verified",
        null_trap_count=2,
        compat_risk_count=1,
    )
    record = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert record["null_trap_count"] == 2
    assert record["compat_risk_count"] == 1


def test_tail_returns_empty_when_no_file(log):
    assert log.tail() == []


def test_tail_returns_last_n(log):
    for i in range(10):
        log.log_query(
            query=f"q{i}", snapshot_name="s", snapshot_id="x",
            sql="SELECT 1", entities_resolved=[], validation_status="unchecked",
        )
    result = log.tail(3)
    assert len(result) == 3
    assert result[-1]["query"] == "q9"


def test_log_never_raises_on_bad_path():
    """AuditLog must not propagate write errors — query generation must continue."""
    bad_log = AuditLog(Path("/nonexistent/path/that/cannot/be/created"))
    # Should not raise
    bad_log.log_query(
        query="test", snapshot_name="s", snapshot_id="x",
        sql="SELECT 1", entities_resolved=[], validation_status="unchecked",
    )
