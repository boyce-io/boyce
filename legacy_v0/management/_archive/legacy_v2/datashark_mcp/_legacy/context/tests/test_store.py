"""
Tests for store.py

Tests GraphStore query methods and indexing.
"""

import pytest
from datetime import datetime, timezone
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.store import GraphStore


def create_test_node(node_id: str, system: str = "database", repo: str = None, schema: str = None) -> Node:
    """Helper to create test nodes."""
    return Node(
        id=node_id,
        system=system,
        type="ENTITY",
        name=f"test_{node_id}",
        attributes={},
        provenance=Provenance(
            system=system,
            source_path=f"{system}://test",
            extractor_version="1.0.0",
            extracted_at=datetime.now(timezone.utc).isoformat()
        ),
        repo=repo,
        schema=schema
    )


def create_test_edge(edge_id: str, src: str, dst: str, edge_type: str = "JOINS_TO") -> Edge:
    """Helper to create test edges."""
    return Edge(
        id=edge_id,
        src=src,
        dst=dst,
        type=edge_type,
        attributes={},
        provenance=Provenance(
            system="database",
            source_path="database://test",
            extractor_version="1.0.0",
            extracted_at=datetime.now(timezone.utc).isoformat()
        )
    )


def test_add_node():
    """Test adding a node to the store."""
    store = GraphStore()
    node = create_test_node("node1")
    
    store.add_node(node)
    
    retrieved = store.get_node("node1")
    assert retrieved is not None
    assert retrieved.id == "node1"


def test_find_entities_by_system():
    """Test finding entities by system."""
    store = GraphStore()
    
    node1 = create_test_node("node1", system="database")
    node2 = create_test_node("node2", system="database")
    node3 = create_test_node("node3", system="dbt")
    
    store.add_node(node1)
    store.add_node(node2)
    store.add_node(node3)
    
    results = store.find_entities_by_system("database")
    assert len(results) == 2
    assert all(n.system == "database" for n in results)


def test_find_entities_by_repo():
    """Test finding entities by repo."""
    store = GraphStore()
    
    node1 = create_test_node("node1", repo="repo1")
    node2 = create_test_node("node2", repo="repo1")
    node3 = create_test_node("node3", repo="repo2")
    
    store.add_node(node1)
    store.add_node(node2)
    store.add_node(node3)
    
    results = store.find_entities_by_repo("repo1")
    assert len(results) == 2
    assert all(n.repo == "repo1" for n in results)


def test_search():
    """Test search with filters."""
    store = GraphStore()
    
    node1 = create_test_node("node1", system="database", name="orders")
    node2 = create_test_node("node2", system="database", name="customers")
    node3 = create_test_node("node3", system="dbt", name="orders")
    
    store.add_node(node1)
    store.add_node(node2)
    store.add_node(node3)
    
    # Search with system filter
    results = store.search("orders", filters={"system": ["database"]})
    assert len(results) == 1
    assert results[0].id == "node1"
    
    # Search without filter
    results = store.search("orders")
    assert len(results) == 2


def test_find_join_paths_from():
    """Test finding join paths."""
    store = GraphStore()
    
    node1 = create_test_node("node1")
    node2 = create_test_node("node2")
    node3 = create_test_node("node3")
    
    store.add_node(node1)
    store.add_node(node2)
    store.add_node(node3)
    
    edge1 = create_test_edge("edge1", "node1", "node2")
    edge2 = create_test_edge("edge2", "node2", "node3")
    
    store.add_edge(edge1)
    store.add_edge(edge2)
    
    paths = store.find_join_paths_from("node1", max_depth=3)
    assert len(paths) > 0


def test_tombstone_filtering():
    """Test that tombstoned nodes/edges are filtered out."""
    store = GraphStore()
    
    node = create_test_node("node1")
    store.add_node(node)
    
    # Tombstone the node
    from datetime import datetime, timezone
    tombstone = Node(
        id=node.id,
        system=node.system,
        type=node.type,
        name=node.name,
        attributes=node.attributes,
        provenance=node.provenance,
        deleted_at=datetime.now(timezone.utc).isoformat()
    )
    store.add_node(tombstone)
    
    # Should not be found
    results = store.find_entities_by_system("database")
    assert len(results) == 0

