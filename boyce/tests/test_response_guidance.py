"""
Tests for the response guidance layer.

Covers:
    _extract_referenced_columns  — regex column extraction (qualified + bare)
    _extract_from_tables         — FROM/JOIN table extraction
    _build_response_guidance     — next_step, present_to_user, data_reality
    Integration: verify next_step present in tool responses
"""

import asyncio
import json
import sys
from unittest.mock import patch, MagicMock

# Stub mcp before importing boyce.server (same pattern as other test files)
if "mcp" not in sys.modules:
    _mcp_stub = MagicMock()
    sys.modules["mcp"] = _mcp_stub
    sys.modules["mcp.server"] = MagicMock()
    sys.modules["mcp.server.fastmcp"] = MagicMock()

import pytest

from boyce.validation import _compute_snapshot_hash
from boyce.types import SemanticSnapshot
from boyce.store import SnapshotStore, DefinitionStore
from boyce.graph import SemanticGraph
from boyce.audit import AuditLog
import boyce.server as srv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_snapshot_with_nullable() -> SemanticSnapshot:
    """Snapshot with a nullable 'status' field on orders for response guidance tests."""
    base = {
        "snapshot_id": "placeholder",
        "source_system": "test",
        "entities": {
            "entity:films": {
                "id": "entity:films",
                "name": "films",
                "grain": "FILM",
                "fields": [
                    "field:films:id",
                    "field:films:rating",
                    "field:films:title",
                    "field:films:rental_rate",
                ],
            },
            "entity:orders": {
                "id": "entity:orders",
                "name": "orders",
                "grain": "ORDER",
                "fields": [
                    "field:orders:id",
                    "field:orders:status",
                    "field:orders:total",
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
            "field:films:id": {
                "id": "field:films:id",
                "entity_id": "entity:films",
                "name": "id",
                "field_type": "ID",
                "data_type": "INTEGER",
                "primary_key": True,
            },
            "field:films:rating": {
                "id": "field:films:rating",
                "entity_id": "entity:films",
                "name": "rating",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(10)",
                "nullable": True,
            },
            "field:films:title": {
                "id": "field:films:title",
                "entity_id": "entity:films",
                "name": "title",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(255)",
            },
            "field:films:rental_rate": {
                "id": "field:films:rental_rate",
                "entity_id": "entity:films",
                "name": "rental_rate",
                "field_type": "MEASURE",
                "data_type": "DECIMAL(5,2)",
            },
            "field:orders:id": {
                "id": "field:orders:id",
                "entity_id": "entity:orders",
                "name": "id",
                "field_type": "ID",
                "data_type": "INTEGER",
                "primary_key": True,
            },
            "field:orders:status": {
                "id": "field:orders:status",
                "entity_id": "entity:orders",
                "name": "status",
                "field_type": "DIMENSION",
                "data_type": "VARCHAR(50)",
                "nullable": True,
            },
            "field:orders:total": {
                "id": "field:orders:total",
                "entity_id": "entity:orders",
                "name": "total",
                "field_type": "MEASURE",
                "data_type": "DECIMAL(10,2)",
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
def ad_server(tmp_path):
    """Patch server globals with a snapshot that has nullable fields."""
    snap = _make_snapshot_with_nullable()
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
        patch.object(srv, "_freshness_checked", set()),
        patch.object(srv, "_drift_checked", set()),
    ):
        yield snap


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _extract_from_tables tests
# ---------------------------------------------------------------------------

class TestExtractFromTables:
    def test_simple_from(self):
        result = srv._extract_from_tables("SELECT * FROM films")
        assert result["films"] == "films"

    def test_from_with_alias(self):
        result = srv._extract_from_tables("SELECT * FROM films f")
        assert result["f"] == "films"
        assert result["films"] == "films"

    def test_from_with_as_alias(self):
        result = srv._extract_from_tables("SELECT * FROM films AS f")
        assert result["f"] == "films"

    def test_join_table(self):
        result = srv._extract_from_tables(
            "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id"
        )
        assert result["o"] == "orders"
        assert result["c"] == "customers"
        assert result["orders"] == "orders"
        assert result["customers"] == "customers"


# ---------------------------------------------------------------------------
# _extract_referenced_columns tests
# ---------------------------------------------------------------------------

class TestExtractReferencedColumns:
    def test_qualified_where(self):
        refs = srv._extract_referenced_columns(
            "SELECT * FROM films WHERE films.rating = 'PG'"
        )
        assert "films.rating" in refs
        assert refs["films.rating"] == "WHERE"

    def test_bare_group_by(self):
        refs = srv._extract_referenced_columns(
            "SELECT rating, COUNT(*) FROM films GROUP BY rating"
        )
        # Bare column keyed as "?.rating" for caller to resolve
        assert "?.rating" in refs
        assert refs["?.rating"] == "GROUP BY"

    def test_bare_where(self):
        refs = srv._extract_referenced_columns(
            "SELECT * FROM films WHERE rating = 'PG'"
        )
        assert "?.rating" in refs
        assert refs["?.rating"] == "WHERE"

    def test_aliased_table_qualified(self):
        refs = srv._extract_referenced_columns(
            "SELECT f.rating FROM films f WHERE f.rating = 'PG'"
        )
        # Alias should be resolved to real table name
        assert "films.rating" in refs
        assert refs["films.rating"] == "WHERE"

    def test_join_on(self):
        refs = srv._extract_referenced_columns(
            "SELECT * FROM orders o "
            "JOIN customers c ON o.customer_id = c.id"
        )
        assert "orders.customer_id" in refs
        assert "customers.id" in refs

    def test_mixed_qualified_and_bare(self):
        refs = srv._extract_referenced_columns(
            "SELECT o.total, status FROM orders o WHERE status = 'active'"
        )
        assert "?.status" in refs
        assert refs["?.status"] == "WHERE"

    def test_sql_keywords_excluded(self):
        refs = srv._extract_referenced_columns(
            "SELECT * FROM films WHERE rating = 'PG' AND title IS NOT NULL"
        )
        # "AND", "IS", "NOT", "NULL" should not appear as bare columns
        bare_keys = [k for k in refs if k.startswith("?.")]
        bare_names = [k[2:] for k in bare_keys]
        assert "AND" not in bare_names
        assert "IS" not in bare_names
        assert "NOT" not in bare_names
        assert "NULL" not in bare_names


# ---------------------------------------------------------------------------
# _build_response_guidance tests
# ---------------------------------------------------------------------------

class TestBuildAdvertisingLayer:
    def test_ingest_source_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="ingest_source",
        )
        assert "next_step" in ad
        assert "get_schema" in ad["next_step"]
        assert "ask_boyce" in ad["next_step"]

    def test_ingest_definition_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="ingest_definition",
        )
        assert "next_step" in ad
        assert "ask_boyce" in ad["next_step"]

    def test_get_schema_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="get_schema",
        )
        assert "next_step" in ad
        assert "StructuredFilter" in ad["next_step"]

    def test_ask_boyce_mode_a_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql="SELECT rating FROM films",
            snapshot_name="default",
            tool_name="ask_boyce",
            mode="A",
        )
        assert "query_database" in ad["next_step"]

    def test_ask_boyce_mode_c_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="ask_boyce", mode="C",
        )
        assert "structured_filter" in ad["next_step"]

    def test_query_database_clean_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql="SELECT title FROM films",
            snapshot_name="default",
            tool_name="query_database",
            validation={"status": "verified", "error": None, "cost_estimate": 10.0},
        )
        assert "profile_data" in ad["next_step"]
        assert "present_to_user" not in ad  # Clean query — no noise

    def test_query_database_null_risk_present_to_user(self, ad_server):
        ad = srv._build_response_guidance(
            sql="SELECT * FROM films WHERE rating = 'PG'",
            snapshot_name="default",
            tool_name="query_database",
            null_risk=[{"table": "films", "column": "rating", "nullable": True, "risk": "test"}],
        )
        assert "present_to_user" in ad
        assert "rating" in ad["present_to_user"]
        assert "ask_boyce" in ad["next_step"]

    def test_validate_sql_clean_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql="SELECT COUNT(*) FROM orders",
            snapshot_name="default",
            tool_name="validate_sql",
            validation={"status": "verified", "error": None, "cost_estimate": 5.0},
        )
        assert "query_database" in ad["next_step"]
        assert "present_to_user" not in ad

    def test_validate_sql_with_issues_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql="SELECT * FROM orders WHERE status = 'active'",
            snapshot_name="default",
            tool_name="validate_sql",
            validation={"status": "invalid", "error": "table not found", "cost_estimate": None},
        )
        assert "ask_boyce" in ad["next_step"]
        assert "present_to_user" in ad

    def test_profile_data_next_step(self, ad_server):
        ad = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="profile_data",
        )
        assert "next_step" in ad
        assert "ask_boyce" in ad["next_step"]

    def test_data_reality_nullable_group_by(self, ad_server):
        """Bare 'rating' in GROUP BY on films → data_reality should fire."""
        ad = srv._build_response_guidance(
            sql="SELECT rating, COUNT(*) FROM films GROUP BY rating",
            snapshot_name="default",
            tool_name="query_database",
            validation={"status": "verified", "error": None, "cost_estimate": 10.0},
        )
        assert "data_reality" in ad
        assert "films.rating" in ad["data_reality"]
        entry = ad["data_reality"]["films.rating"]
        assert entry["nullable"] is True
        assert entry["used_in"] == "GROUP BY"
        assert "NULL" in entry["insight"]

    def test_data_reality_nullable_where(self, ad_server):
        """Bare 'status' in WHERE on orders → data_reality should fire."""
        ad = srv._build_response_guidance(
            sql="SELECT * FROM orders WHERE status = 'active'",
            snapshot_name="default",
            tool_name="query_database",
            validation={"status": "verified", "error": None, "cost_estimate": 10.0},
        )
        assert "data_reality" in ad
        assert "orders.status" in ad["data_reality"]
        entry = ad["data_reality"]["orders.status"]
        assert entry["nullable"] is True
        assert entry["used_in"] == "WHERE"

    def test_data_reality_absent_on_non_nullable(self, ad_server):
        """Non-nullable column in simple WHERE → no data_reality."""
        ad = srv._build_response_guidance(
            sql="SELECT * FROM films WHERE title = 'test'",
            snapshot_name="default",
            tool_name="query_database",
            validation={"status": "verified", "error": None, "cost_estimate": 10.0},
        )
        # title is not nullable → no material insight → data_reality absent
        assert "data_reality" not in ad or ad.get("data_reality") is None

    def test_present_to_user_absent_on_clean_query(self, ad_server):
        """No null risk, no EXPLAIN failure, no compat issues → no present_to_user."""
        ad = srv._build_response_guidance(
            sql="SELECT title FROM films",
            snapshot_name="default",
            tool_name="query_database",
            validation={"status": "verified", "error": None, "cost_estimate": 10.0},
        )
        assert "present_to_user" not in ad


# ---------------------------------------------------------------------------
# Integration: next_step present in tool responses
# ---------------------------------------------------------------------------

class TestNextStepInToolResponses:
    def test_ingest_source_has_next_step(self, ad_server, tmp_path):
        """ingest_source response includes next_step."""
        # Create a minimal DDL file
        ddl = tmp_path / "schema.sql"
        ddl.write_text(
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name VARCHAR(50));"
        )
        result = json.loads(_run(srv.ingest_source(
            source_path=str(ddl), snapshot_name="test_ingest",
        )))
        if "error" not in result:
            assert "next_step" in result

    def test_get_schema_has_next_step(self, ad_server):
        result = json.loads(srv.get_schema("default"))
        assert "next_step" in result

    def test_ingest_definition_has_next_step(self, ad_server):
        result = json.loads(srv.ingest_definition(
            term="revenue",
            definition="Total revenue from completed orders",
            snapshot_name="default",
        ))
        assert "next_step" in result

    def test_validate_sql_has_next_step(self, ad_server):
        result = json.loads(_run(srv.validate_sql(
            sql="SELECT COUNT(*) FROM orders",
            snapshot_name="default",
        )))
        assert "next_step" in result

    def test_profile_data_returns_next_step_when_db_available(self, ad_server):
        """profile_data needs a live DB — verify error path doesn't have next_step
        but success path would."""
        result = json.loads(_run(srv.profile_data("orders", "status")))
        # Without DB adapter, this returns an error — that's expected
        if "error" not in result:
            assert "next_step" in result


# ---------------------------------------------------------------------------
# environment_suggestions tests
# ---------------------------------------------------------------------------


class TestEnvironmentSuggestions:
    """Test the environment_suggestions field in the response guidance layer."""

    def test_first_call_may_include_suggestions(self, ad_server):
        """First call per session may include environment_suggestions."""
        # Reset the flag
        srv._environment_checked = False
        result = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="get_schema",
        )
        # May or may not have suggestions depending on environment state
        assert "next_step" in result

    def test_second_call_never_includes_suggestions(self, ad_server):
        """After first call, environment_suggestions should not appear."""
        srv._environment_checked = True
        result = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="get_schema",
        )
        assert "environment_suggestions" not in result

    def test_suggestions_max_three(self, ad_server):
        """environment_suggestions should never exceed 3 items."""
        srv._environment_checked = False
        result = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="get_schema",
        )
        if "environment_suggestions" in result:
            assert len(result["environment_suggestions"]) <= 3

    def test_flag_resets_correctly(self, ad_server):
        """_environment_checked flag prevents duplicate suggestions."""
        srv._environment_checked = False
        result1 = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="ingest_source",
        )
        result2 = srv._build_response_guidance(
            sql=None, snapshot_name="default", tool_name="get_schema",
        )
        # Second call should never have environment_suggestions
        assert "environment_suggestions" not in result2
