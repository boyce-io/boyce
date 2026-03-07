"""
Tests for Query DSL

Validates deterministic parsing and execution.
"""

import pytest
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.query.dsl_parser import DSLParser, QueryType
from datashark_mcp.context.query.executor import QueryExecutor
from datashark_mcp.context.models import Node, Provenance
from datetime import datetime, timezone


def create_test_node(node_id: str, name: str, system: str = "database") -> Node:
    """Helper to create test nodes."""
    return Node(
        id=node_id,
        system=system,
        type="ENTITY",
        name=name,
        attributes={},
        provenance=Provenance(
            system=system,
            source_path=f"{system}://{name}",
            extractor_version="1.0.0",
            extracted_at=datetime.now(timezone.utc).isoformat()
        )
    )


def test_parser_find_query():
    """Test parsing FIND queries."""
    parser = DSLParser()
    
    ast = parser.parse("FIND ENTITY WHERE system='database'")
    
    assert ast.query_type == QueryType.FIND
    assert ast.entity_type == "ENTITY"
    assert len(ast.filters) == 1
    assert ast.filters[0].field == "system"
    assert ast.filters[0].value == "database"


def test_parser_path_query():
    """Test parsing PATH queries."""
    parser = DSLParser()
    
    ast = parser.parse("PATH FROM 'node1' TO 'node2'")
    
    assert ast.query_type == QueryType.PATH
    assert ast.path_from == "node1"
    assert ast.path_to == "node2"


def test_parser_search_query():
    """Test parsing SEARCH queries."""
    parser = DSLParser()
    
    ast = parser.parse("SEARCH 'revenue'")
    
    assert ast.query_type == QueryType.SEARCH
    assert ast.search_term == "revenue"


def test_executor_find():
    """Test executing FIND queries."""
    store = GraphStore()
    api = ContextAPI(store)
    executor = QueryExecutor(api)
    
    # Add test nodes
    node1 = create_test_node("node1", "revenue", system="database")
    node2 = create_test_node("node2", "orders", system="database")
    store.add_node(node1)
    store.add_node(node2)
    
    parser = DSLParser()
    ast = parser.parse("FIND ENTITY WHERE system='database'")
    result = executor.execute(ast)
    
    assert result["stats"]["count"] == 2
    assert len(result["nodes"]) == 2


def test_executor_path():
    """Test executing PATH queries."""
    store = GraphStore()
    api = ContextAPI(store)
    executor = QueryExecutor(api)
    
    # Add nodes and edge
    node1 = create_test_node("node1", "revenue")
    node2 = create_test_node("node2", "orders")
    store.add_node(node1)
    store.add_node(node2)
    
    from datashark_mcp.context.models import Edge
    edge = Edge(
        id="edge1",
        src="node1",
        dst="node2",
        type="JOINS_TO",
        attributes={},
        provenance=Provenance(
            system="database",
            source_path="database://test",
            extractor_version="1.0.0",
            extracted_at=datetime.now(timezone.utc).isoformat()
        )
    )
    store.add_edge(edge)
    
    parser = DSLParser()
    ast = parser.parse("PATH FROM 'node1' TO 'node2'")
    result = executor.execute(ast)
    
    # Should find path
    assert result["stats"]["query_type"] == "PATH"


def test_deterministic_parsing():
    """Test that parsing is deterministic."""
    parser = DSLParser()
    
    query = "FIND ENTITY WHERE system='database' AND name~'revenue'"
    
    ast1 = parser.parse(query)
    ast2 = parser.parse(query)
    
    assert ast1.query_type == ast2.query_type
    assert ast1.entity_type == ast2.entity_type
    assert len(ast1.filters) == len(ast2.filters)

