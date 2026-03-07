"""
Tests for Embedding

Validates reproducibility and stable ordering.
"""

import pytest
from datashark_mcp.context.embedding.embedder import SimpleHashEmbedder
from datashark_mcp.context.embedding.vector_index import VectorIndex
from datashark_mcp.context.models import Node, Provenance
from datetime import datetime, timezone


def create_test_node(node_id: str, name: str) -> Node:
    """Helper to create test nodes."""
    return Node(
        id=node_id,
        system="database",
        type="ENTITY",
        name=name,
        attributes={},
        provenance=Provenance(
            system="database",
            source_path=f"database://{name}",
            extractor_version="1.0.0",
            extracted_at=datetime.now(timezone.utc).isoformat()
        )
    )


def test_hash_embedder_deterministic():
    """Test that hash embedder produces identical vectors for same text."""
    embedder = SimpleHashEmbedder()
    
    vec1 = embedder.embed_text("test")
    vec2 = embedder.embed_text("test")
    
    assert vec1 == vec2, "Embeddings must be deterministic"


def test_hash_embedder_different_texts():
    """Test that different texts produce different vectors."""
    embedder = SimpleHashEmbedder()
    
    vec1 = embedder.embed_text("test1")
    vec2 = embedder.embed_text("test2")
    
    assert vec1 != vec2, "Different texts should produce different vectors"


def test_vector_index_build_and_query():
    """Test vector index build and query."""
    nodes = [
        create_test_node("node1", "revenue"),
        create_test_node("node2", "orders"),
        create_test_node("node3", "customers")
    ]
    
    index = VectorIndex()
    index.build_index(nodes)
    
    # Query
    results = index.query_text("revenue", top_k=2)
    
    assert len(results) > 0
    assert results[0][0].name == "revenue"  # Should match exactly


def test_vector_index_deterministic_ordering():
    """Test that query results are deterministically ordered."""
    nodes = [
        create_test_node("node1", "revenue"),
        create_test_node("node2", "orders"),
        create_test_node("node3", "customers")
    ]
    
    index = VectorIndex()
    index.build_index(nodes)
    
    # Query multiple times
    results1 = index.query_text("revenue", top_k=10)
    results2 = index.query_text("revenue", top_k=10)
    
    # Results should be identical
    assert len(results1) == len(results2)
    for (node1, score1), (node2, score2) in zip(results1, results2):
        assert node1.id == node2.id
        assert abs(score1 - score2) < 0.0001  # Floating point tolerance


def test_vector_index_tie_breaking():
    """Test that tie-breaking uses node ID for deterministic ordering."""
    nodes = [
        create_test_node("node_z", "revenue"),
        create_test_node("node_a", "revenue")  # Same name, different IDs
    ]
    
    index = VectorIndex()
    index.build_index(nodes)
    
    results = index.query_text("revenue", top_k=10)
    
    # Should be sorted by node ID (deterministic)
    node_ids = [node.id for node, _ in results]
    assert node_ids == sorted(node_ids)

