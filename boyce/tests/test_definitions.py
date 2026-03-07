"""
Tests for DefinitionStore and ingest_definition planner injection.
"""

import json
import tempfile
from pathlib import Path

import pytest

from boyce.store import DefinitionStore


@pytest.fixture
def store(tmp_path):
    return DefinitionStore(tmp_path)


# ---------------------------------------------------------------------------
# DefinitionStore — storage
# ---------------------------------------------------------------------------


def test_upsert_returns_count(store):
    count = store.upsert("snap", "revenue", "Total recognized revenue")
    assert count == 1


def test_upsert_second_term_increments(store):
    store.upsert("snap", "revenue", "Total recognized revenue")
    count = store.upsert("snap", "churn rate", "Cancelled subscribers in period")
    assert count == 2


def test_upsert_same_term_overwrites(store):
    store.upsert("snap", "revenue", "Old definition")
    count = store.upsert("snap", "revenue", "New definition")
    assert count == 1  # still one entry
    data = store.load_all("snap")
    assert data["revenue"]["definition"] == "New definition"


def test_load_all_empty_when_no_file(store):
    assert store.load_all("nonexistent") == {}


def test_upsert_stores_all_fields(store):
    store.upsert(
        "snap",
        term="revenue",
        definition="SUM of completed orders",
        sql_expression="SUM(CASE WHEN status='completed' THEN total ELSE 0 END)",
        entity_hint="orders",
    )
    data = store.load_all("snap")
    entry = data["revenue"]
    assert entry["term"] == "revenue"
    assert entry["definition"] == "SUM of completed orders"
    assert entry["sql_expression"] == "SUM(CASE WHEN status='completed' THEN total ELSE 0 END)"
    assert entry["entity_hint"] == "orders"


def test_term_stored_lowercase_key(store):
    store.upsert("snap", "Active User", "User with login in last 30 days")
    data = store.load_all("snap")
    assert "active user" in data
    assert data["active user"]["term"] == "Active User"


def test_file_written_to_correct_path(store, tmp_path):
    store.upsert("mysnap", "revenue", "Some definition")
    expected = tmp_path / "mysnap.definitions.json"
    assert expected.exists()


def test_definitions_isolated_by_snapshot_name(store):
    store.upsert("snap_a", "revenue", "Definition A")
    store.upsert("snap_b", "cost", "Definition B")
    assert "revenue" in store.load_all("snap_a")
    assert "cost" not in store.load_all("snap_a")
    assert "cost" in store.load_all("snap_b")


# ---------------------------------------------------------------------------
# DefinitionStore — as_context_string
# ---------------------------------------------------------------------------


def test_as_context_string_none_when_empty(store):
    assert store.as_context_string("snap") is None


def test_as_context_string_contains_term(store):
    store.upsert("snap", "revenue", "SUM of completed order totals")
    ctx = store.as_context_string("snap")
    assert ctx is not None
    assert "revenue" in ctx
    assert "SUM of completed order totals" in ctx


def test_as_context_string_includes_sql_expression(store):
    store.upsert(
        "snap",
        "revenue",
        "Total revenue",
        sql_expression="SUM(order_total)",
        entity_hint="orders",
    )
    ctx = store.as_context_string("snap")
    assert "SUM(order_total)" in ctx
    assert "orders" in ctx


def test_as_context_string_multiple_terms(store):
    store.upsert("snap", "revenue", "Completed order totals")
    store.upsert("snap", "active user", "Logged in last 30 days")
    ctx = store.as_context_string("snap")
    assert "revenue" in ctx
    assert "active user" in ctx


def test_as_context_string_starts_with_header(store):
    store.upsert("snap", "revenue", "Some definition")
    ctx = store.as_context_string("snap")
    assert ctx.startswith("Certified Business Definitions")
