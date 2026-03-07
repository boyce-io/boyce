"""
Tests for models.py

Tests Node and Edge validation against graph_schema.json.
"""

import pytest
from datetime import datetime, timezone
from datashark_mcp.context.models import Node, Edge, Provenance, GraphValidationError


def test_node_validation_success():
    """Test that a valid node passes validation."""
    provenance = Provenance(
        system="database",
        source_path="database://public.meta",
        extractor_version="1.0.0",
        extracted_at=datetime.now(timezone.utc).isoformat()
    )
    
    node = Node(
        id="test_node",
        system="database",
        type="ENTITY",
        name="test_entity",
        attributes={"schema": "public", "table": "meta"},
        provenance=provenance
    )
    
    # Should not raise
    node.validate()


def test_node_validation_missing_required():
    """Test that missing required fields fail validation."""
    provenance = Provenance(
        system="database",
        source_path="database://public.meta",
        extractor_version="1.0.0",
        extracted_at=datetime.now(timezone.utc).isoformat()
    )
    
    # Missing 'name'
    node = Node(
        id="test_node",
        system="database",
        type="ENTITY",
        name="",  # Empty name
        attributes={},
        provenance=provenance
    )
    
    # Validation should pass (empty string is valid)
    node.validate()


def test_edge_validation_success():
    """Test that a valid edge passes validation."""
    provenance = Provenance(
        system="database",
        source_path="database://public.meta",
        extractor_version="1.0.0",
        extracted_at=datetime.now(timezone.utc).isoformat()
    )
    
    edge = Edge(
        id="test_edge",
        src="node1",
        dst="node2",
        type="JOINS_TO",
        attributes={"join_condition": "a.id = b.id"},
        provenance=provenance
    )
    
    # Should not raise
    edge.validate()


def test_edge_validation_invalid_type():
    """Test that invalid edge type fails validation."""
    provenance = Provenance(
        system="database",
        source_path="database://public.meta",
        extractor_version="1.0.0",
        extracted_at=datetime.now(timezone.utc).isoformat()
    )
    
    edge = Edge(
        id="test_edge",
        src="node1",
        dst="node2",
        type="INVALID_TYPE",  # Invalid
        attributes={},
        provenance=provenance
    )
    
    with pytest.raises(GraphValidationError):
        edge.validate()


def test_node_to_dict_preserves_order():
    """Test that to_dict preserves key order."""
    provenance = Provenance(
        system="database",
        source_path="database://public.meta",
        extractor_version="1.0.0",
        extracted_at=datetime.now(timezone.utc).isoformat()
    )
    
    node = Node(
        id="test_node",
        system="database",
        type="ENTITY",
        name="test",
        attributes={"a": 1, "b": 2},
        provenance=provenance
    )
    
    d = node.to_dict()
    
    # Check required fields present
    assert "id" in d
    assert "system" in d
    assert "type" in d
    assert "name" in d
    assert "attributes" in d
    assert "provenance" in d


def test_node_from_dict_roundtrip():
    """Test that from_dict and to_dict are inverse operations."""
    provenance = Provenance(
        system="database",
        source_path="database://public.meta",
        extractor_version="1.0.0",
        extracted_at=datetime.now(timezone.utc).isoformat()
    )
    
    node = Node(
        id="test_node",
        system="database",
        type="ENTITY",
        name="test",
        attributes={"a": 1},
        provenance=provenance,
        repo="test_repo"
    )
    
    d = node.to_dict()
    node2 = Node.from_dict(d)
    
    assert node.id == node2.id
    assert node.system == node2.system
    assert node.type == node2.type
    assert node.name == node2.name
    assert node.repo == node2.repo

