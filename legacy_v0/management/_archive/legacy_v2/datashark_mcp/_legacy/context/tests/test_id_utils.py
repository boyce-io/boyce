"""
Tests for id_utils.py

Tests deterministic ID generation and reproducibility.
"""

import pytest
from datashark_mcp.context.id_utils import compute_node_id, compute_edge_id, normalize_json


def test_node_id_deterministic():
    """Test that same inputs produce same node ID."""
    id1 = compute_node_id("ENTITY", "database", None, "public", "meta")
    id2 = compute_node_id("ENTITY", "database", None, "public", "meta")
    
    assert id1 == id2
    assert len(id1) == 64  # SHA-256 hex digest length


def test_node_id_case_insensitive():
    """Test that case differences are normalized."""
    id1 = compute_node_id("ENTITY", "database", None, "public", "meta")
    id2 = compute_node_id("entity", "DATABASE", None, "PUBLIC", "META")
    
    assert id1 == id2


def test_node_id_whitespace_normalized():
    """Test that whitespace is normalized."""
    id1 = compute_node_id("ENTITY", "database", None, "public", "meta")
    id2 = compute_node_id(" ENTITY ", "  database  ", None, "public", "  meta  ")
    
    assert id1 == id2


def test_node_id_repo_none():
    """Test that None repo is handled correctly."""
    id1 = compute_node_id("ENTITY", "database", None, "public", "meta")
    id2 = compute_node_id("ENTITY", "database", "", "public", "meta")
    
    assert id1 == id2


def test_edge_id_deterministic():
    """Test that same inputs produce same edge ID."""
    src_id = compute_node_id("ENTITY", "database", None, "public", "meta")
    dst_id = compute_node_id("ENTITY", "database", None, "public", "users")
    
    id1 = compute_edge_id("JOINS_TO", src_id, dst_id)
    id2 = compute_edge_id("JOINS_TO", src_id, dst_id)
    
    assert id1 == id2
    assert len(id1) == 64


def test_edge_id_with_join_signature():
    """Test edge ID with join signature."""
    src_id = compute_node_id("ENTITY", "database", None, "public", "meta")
    dst_id = compute_node_id("ENTITY", "database", None, "public", "users")
    
    signature = {"join_condition": "meta.id = users.id", "join_type": "inner"}
    
    id1 = compute_edge_id("JOINS_TO", src_id, dst_id, signature)
    id2 = compute_edge_id("JOINS_TO", src_id, dst_id, signature)
    
    assert id1 == id2


def test_normalize_json_stable_order():
    """Test that normalize_json produces stable output."""
    obj1 = {"b": 2, "a": 1, "c": 3}
    obj2 = {"c": 3, "a": 1, "b": 2}
    
    norm1 = normalize_json(obj1)
    norm2 = normalize_json(obj2)
    
    assert norm1 == norm2
    assert norm1 == '{"a":1,"b":2,"c":3}'


def test_cross_machine_determinism():
    """Test that IDs are deterministic across different normalization contexts."""
    # Simulate different normalization scenarios
    inputs = [
        ("ENTITY", "database", None, "public", "meta"),
        ("entity", "DATABASE", None, "PUBLIC", "META"),
        (" ENTITY ", "  database  ", None, "public", "  meta  "),
    ]
    
    ids = [compute_node_id(*inp) for inp in inputs]
    
    # All should produce same ID
    assert len(set(ids)) == 1

