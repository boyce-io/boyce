"""
Tests for get_schema, build_sql, and _validate_structured_filter.

These tests exercise the two new MCP tools designed for host-LLM use
(no Boyce LLM needed — the host reads the schema and constructs the filter).

All tests are offline: no DB, no LLM.
"""

from __future__ import annotations

import asyncio
import json
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
# Snapshot fixture
# ---------------------------------------------------------------------------

def _make_test_snapshot() -> SemanticSnapshot:
    """Build a minimal but fully valid SemanticSnapshot (orders + customers)."""
    # Build without snapshot_id so we can compute the correct hash
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
                    "field:customers:name",
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
            "field:customers:name": {
                "id": "field:customers:name",
                "entity_id": "entity:customers",
                "name": "name",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(255)",
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
def wired_server(tmp_path):
    """
    Patch boyce.server module globals to use isolated tmp_path stores.
    Yields the SemanticSnapshot that was saved as 'default'.
    """
    snap = _make_test_snapshot()
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
        # No DB adapter — all async checks return "unchecked" / []
        patch.object(srv, "_adapter", None),
    ):
        yield snap


def _run(coro):
    """Run a coroutine synchronously in tests (no pytest-asyncio required)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# get_schema tests
# ---------------------------------------------------------------------------


def test_get_schema_returns_entities(wired_server):
    result = json.loads(srv.get_schema("default"))
    assert "entities" in result
    entity_names = [e["name"] for e in result["entities"]]
    assert "orders" in entity_names
    assert "customers" in entity_names


def test_get_schema_entities_include_fields(wired_server):
    result = json.loads(srv.get_schema("default"))
    orders = next(e for e in result["entities"] if e["name"] == "orders")
    field_names = [f["name"] for f in orders["fields"]]
    assert "revenue" in field_names
    assert "status" in field_names
    assert "customer_id" in field_names


def test_get_schema_fields_have_metadata(wired_server):
    result = json.loads(srv.get_schema("default"))
    orders = next(e for e in result["entities"] if e["name"] == "orders")
    revenue = next(f for f in orders["fields"] if f["name"] == "revenue")
    assert revenue["field_type"] == "MEASURE"
    assert revenue["data_type"] == "DECIMAL(10,2)"
    assert "field_id" in revenue


def test_get_schema_returns_joins(wired_server):
    result = json.loads(srv.get_schema("default"))
    assert "joins" in result
    assert len(result["joins"]) >= 1
    join = result["joins"][0]
    assert join["source_entity_id"] == "entity:orders"
    assert join["target_entity_id"] == "entity:customers"
    assert "weight" in join


def test_get_schema_returns_filter_docs(wired_server):
    result = json.loads(srv.get_schema("default"))
    assert "structured_filter_docs" in result
    docs = result["structured_filter_docs"]
    assert "StructuredFilter" in docs
    assert "build_sql" in docs
    assert "trailing_interval" in docs


def test_get_schema_returns_snapshot_id(wired_server):
    snap = wired_server
    result = json.loads(srv.get_schema("default"))  # snap is the SemanticSnapshot
    assert result["snapshot_id"] == snap.snapshot_id
    assert result["snapshot_name"] == "default"


def test_get_schema_includes_definitions(wired_server, tmp_path):
    # Add a definition then check it shows up
    defs = DefinitionStore(tmp_path)
    defs.upsert("default", "revenue", "Total recognized revenue", "SUM(revenue)", "orders")
    with patch.object(srv, "_definitions", defs):
        result = json.loads(srv.get_schema("default"))
    assert len(result["definitions"]) == 1
    assert result["definitions"][0]["term"] == "revenue"


def test_get_schema_missing_snapshot_returns_error(wired_server):
    result = json.loads(srv.get_schema("nonexistent"))
    assert "error" in result
    assert result["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# build_sql tests
# ---------------------------------------------------------------------------

def _minimal_filter(snap: SemanticSnapshot, dialect: str = "postgres") -> dict:
    """Minimal valid StructuredFilter: SUM(revenue) from orders."""
    return {
        "concept_map": {
            "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
            "fields": [
                {"field_id": "field:orders:revenue", "field_name": "revenue",
                 "entity_id": "entity:orders"}
            ],
            "metrics": [
                {"metric_name": "revenue", "field_id": "field:orders:revenue",
                 "aggregation_type": "SUM"}
            ],
            "dimensions": [],
            "filters": [],
        },
        "join_path": [],
        "grain_context": {"aggregation_required": True},
        "policy_context": {"resolved_predicates": []},
        "temporal_filters": [],
        "dialect": dialect,
    }


def test_build_sql_returns_sql(wired_server):
    sf = _minimal_filter(wired_server)
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert "sql" in result
    assert "SELECT" in result["sql"].upper()
    assert "revenue" in result["sql"].lower()


def test_build_sql_is_deterministic(wired_server):
    sf = _minimal_filter(wired_server)
    r1 = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    r2 = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert r1["sql"] == r2["sql"]


def test_build_sql_returns_same_shape_as_ask_boyce(wired_server):
    sf = _minimal_filter(wired_server)
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    # Same required keys as ask_boyce
    for key in ("sql", "snapshot_id", "snapshot_name", "entities_resolved", "validation"):
        assert key in result, f"Missing key: {key}"


def test_build_sql_validation_status_unchecked_without_db(wired_server):
    sf = _minimal_filter(wired_server)
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert result["validation"]["status"] == "unchecked"


def test_build_sql_entities_resolved(wired_server):
    sf = _minimal_filter(wired_server)
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert "orders" in result["entities_resolved"]


def test_build_sql_bad_entity_id_returns_error(wired_server):
    sf = _minimal_filter(wired_server)
    sf["concept_map"]["entities"] = [{"entity_id": "entity:nonexistent", "entity_name": "nonexistent"}]
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert "error" in result
    assert result["error"]["code"] == -32602
    assert "not found" in result["error"]["data"][0]


def test_build_sql_bad_field_id_returns_error(wired_server):
    sf = _minimal_filter(wired_server)
    sf["concept_map"]["metrics"] = [
        {"metric_name": "x", "field_id": "field:orders:nosuchfield", "aggregation_type": "SUM"}
    ]
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert "error" in result
    assert "nosuchfield" in result["error"]["data"][0]


def test_build_sql_bad_operator_returns_error(wired_server):
    sf = _minimal_filter(wired_server)
    sf["concept_map"]["filters"] = [
        {"field_id": "field:orders:status", "operator": "CONTAINS", "value": "active",
         "entity_id": "entity:orders"}
    ]
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert "error" in result
    assert "CONTAINS" in result["error"]["data"][0]


def test_build_sql_missing_snapshot_returns_error(wired_server):
    sf = _minimal_filter(wired_server)
    result = json.loads(_run(srv.build_sql(sf, "nonexistent", "postgres")))
    assert "error" in result
    assert result["error"]["code"] == -32602


def test_build_sql_bad_dialect_returns_error(wired_server):
    sf = _minimal_filter(wired_server)
    sf["dialect"] = "mysql"
    result = json.loads(_run(srv.build_sql(sf, "default", "mysql")))
    assert "error" in result


def test_build_sql_empty_filter_returns_error(wired_server):
    result = json.loads(_run(srv.build_sql({}, "default", "postgres")))
    assert "error" in result


def test_build_sql_with_filter(wired_server):
    sf = _minimal_filter(wired_server)
    sf["concept_map"]["filters"] = [
        {"field_id": "field:orders:status", "operator": "=",
         "value": "active", "entity_id": "entity:orders"}
    ]
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    assert "sql" in result
    assert "active" in result["sql"]


def test_build_sql_with_temporal_filter(wired_server):
    sf = _minimal_filter(wired_server)
    # Need a timestamp field — use status as a stand-in to test the pipeline
    # (in practice a TIMESTAMP field_type would be used)
    sf["temporal_filters"] = [
        {"field_id": "field:orders:status", "operator": "trailing_interval",
         "value": {"value": 30, "unit": "day"}}
    ]
    result = json.loads(_run(srv.build_sql(sf, "default", "postgres")))
    # Either SQL or an error — the key check is no exception is thrown
    assert "sql" in result or "error" in result


# ---------------------------------------------------------------------------
# _validate_structured_filter tests
# ---------------------------------------------------------------------------


def test_validate_ok_returns_empty_list(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    errors = srv._validate_structured_filter(sf, snap)
    assert errors == []


def test_validate_missing_concept_map(wired_server):
    snap = wired_server
    errors = srv._validate_structured_filter({}, snap)
    assert any("concept_map" in e for e in errors)


def test_validate_empty_entities(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["concept_map"]["entities"] = []
    errors = srv._validate_structured_filter(sf, snap)
    assert any("entities" in e for e in errors)


def test_validate_unknown_entity_id(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["concept_map"]["entities"] = [{"entity_id": "entity:ghost", "entity_name": "ghost"}]
    errors = srv._validate_structured_filter(sf, snap)
    assert any("ghost" in e for e in errors)


def test_validate_unknown_field_id_in_metrics(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["concept_map"]["metrics"] = [
        {"metric_name": "x", "field_id": "field:orders:phantom", "aggregation_type": "SUM"}
    ]
    errors = srv._validate_structured_filter(sf, snap)
    assert any("phantom" in e for e in errors)


def test_validate_invalid_aggregation_type(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["concept_map"]["metrics"] = [
        {"metric_name": "x", "field_id": "field:orders:revenue", "aggregation_type": "MEDIAN"}
    ]
    errors = srv._validate_structured_filter(sf, snap)
    assert any("MEDIAN" in e for e in errors)


def test_validate_invalid_filter_operator(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["concept_map"]["filters"] = [
        {"field_id": "field:orders:status", "operator": "CONTAINS",
         "value": "x", "entity_id": "entity:orders"}
    ]
    errors = srv._validate_structured_filter(sf, snap)
    assert any("CONTAINS" in e for e in errors)


def test_validate_invalid_dialect(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["dialect"] = "mysql"
    errors = srv._validate_structured_filter(sf, snap)
    assert any("mysql" in e for e in errors)


def test_validate_bad_temporal_operator(wired_server):
    snap = wired_server
    sf = _minimal_filter(snap)
    sf["temporal_filters"] = [
        {"field_id": "field:orders:status", "operator": "last_n_days",
         "value": {"value": 30, "unit": "day"}}
    ]
    errors = srv._validate_structured_filter(sf, snap)
    assert any("last_n_days" in e for e in errors)
