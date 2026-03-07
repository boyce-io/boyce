"""
Tests for merge.py

Tests merge logic, conflict resolution, and tombstone handling.
"""

import pytest
from datetime import datetime, timezone, timedelta
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.merge import merge_node, merge_edge, merge_nodes_and_edges, MergeResult


def create_test_node(node_id: str, extracted_at: str = None, extractor_version: str = "1.0.0") -> Node:
    """Helper to create test nodes."""
    if extracted_at is None:
        extracted_at = datetime.now(timezone.utc).isoformat()
    
    return Node(
        id=node_id,
        system="database",
        type="ENTITY",
        name=f"test_{node_id}",
        attributes={},
        provenance=Provenance(
            system="database",
            source_path="database://test",
            extractor_version=extractor_version,
            extracted_at=extracted_at
        )
    )


def test_merge_node_new():
    """Test merging a new node."""
    store = GraphStore()
    node = create_test_node("node1")
    
    merged, status = merge_node(None, node, store)
    
    assert status == "new"
    assert merged.id == "node1"
    assert store.get_node("node1") is not None


def test_merge_node_unchanged():
    """Test merging with older timestamp stays unchanged."""
    store = GraphStore()
    
    old_time = datetime.now(timezone.utc).isoformat()
    new_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    
    old_node = create_test_node("node1", extracted_at=old_time)
    store.add_node(old_node)
    
    newer_node = create_test_node("node1", extracted_at=new_time)
    merged, status = merge_node(old_node, newer_node, store)
    
    assert status == "changed"
    assert merged.provenance.extracted_at == new_time


def test_merge_node_version_precedence():
    """Test that extractor_version breaks ties when timestamps equal."""
    store = GraphStore()
    
    time_str = datetime.now(timezone.utc).isoformat()
    
    old_node = create_test_node("node1", extracted_at=time_str, extractor_version="1.0.0")
    store.add_node(old_node)
    
    newer_node = create_test_node("node1", extracted_at=time_str, extractor_version="1.0.1")
    merged, status = merge_node(old_node, newer_node, store)
    
    assert status == "changed"
    assert merged.provenance.extractor_version == "1.0.1"


def test_merge_nodes_and_edges():
    """Test merging lists of nodes and edges."""
    store = GraphStore()
    
    nodes = [
        create_test_node("node1"),
        create_test_node("node2"),
    ]
    
    edges = [
        Edge(
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
    ]
    
    result = merge_nodes_and_edges(nodes, edges, store)
    
    assert result.new_nodes == 2
    assert result.new_edges == 1
    assert result.changed_nodes == 0


def test_merge_tombstones():
    """Test that deletions create tombstones."""
    store = GraphStore()
    
    # Add initial nodes
    node1 = create_test_node("node1")
    node2 = create_test_node("node2")
    store.add_node(node1)
    store.add_node(node2)
    
    # Merge with only node1 (node2 should be tombstoned)
    nodes = [create_test_node("node1")]
    result = merge_nodes_and_edges(nodes, [], store, handle_deletions=True)
    
    assert result.deleted_nodes == 1
    
    # Check that node2 is tombstoned
    node2_retrieved = store.get_node("node2")
    assert node2_retrieved is not None
    assert node2_retrieved.deleted_at is not None

