"""
Test Join Inference

Verifies join relationship inference with synthetic tables.
"""

import pytest
from datashark_mcp.context.models import Node, Provenance
from datashark_mcp.context.store import GraphStore
from datashark_mcp.agentic.adcil.join_inference import JoinInference, InferredJoin
from datetime import datetime


@pytest.fixture
def sample_tables_store():
    """Create a GraphStore with synthetic tables for join testing."""
    store = GraphStore()
    
    # Table: products
    products_table = Node(
        id="entity:database:products",
        system="database",
        type="ENTITY",
        name="products",
        attributes={"table_name": "products"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(products_table)
    
    # Columns in products
    product_id_col = Node(
        id="field:database:products:product_id",
        system="database",
        type="FIELD",
        name="product_id",
        attributes={"type": "integer", "table": "products", "primary_key": True},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(product_id_col)
    
    product_name_col = Node(
        id="field:database:products:name",
        system="database",
        type="FIELD",
        name="name",
        attributes={"type": "varchar", "table": "products"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(product_name_col)
    
    # Table: orders
    orders_table = Node(
        id="entity:database:orders",
        system="database",
        type="ENTITY",
        name="orders",
        attributes={"table_name": "orders"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(orders_table)
    
    # Columns in orders
    order_id_col = Node(
        id="field:database:orders:order_id",
        system="database",
        type="FIELD",
        name="order_id",
        attributes={"type": "integer", "table": "orders", "primary_key": True},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(order_id_col)
    
    product_id_fk_col = Node(
        id="field:database:orders:product_id",
        system="database",
        type="FIELD",
        name="product_id",
        attributes={"type": "integer", "table": "orders"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(product_id_fk_col)
    
    # Table: countries
    countries_table = Node(
        id="entity:database:countries",
        system="database",
        type="ENTITY",
        name="countries",
        attributes={"table_name": "countries"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(countries_table)
    
    country_code_col = Node(
        id="field:database:countries:country_code",
        system="database",
        type="FIELD",
        name="country_code",
        attributes={"type": "varchar", "table": "countries", "primary_key": True},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(country_code_col)
    
    return store


def test_join_inference_foreign_key_pattern(sample_tables_store):
    """Test that foreign key naming pattern is detected."""
    join_inference = JoinInference(sample_tables_store, confidence_threshold=0.7)
    
    inferences = join_inference.infer_joins()
    
    # Should detect orders.product_id -> products.product_id
    order_to_product = next(
        (inf for inf in inferences 
         if inf.source_table_id == "entity:database:orders"
         and inf.target_table_id == "entity:database:products"),
        None
    )
    
    assert order_to_product is not None
    assert order_to_product.source_column_id == "field:database:orders:product_id"
    assert order_to_product.target_column_id == "field:database:products:product_id"
    assert order_to_product.confidence >= 0.85
    assert order_to_product.method == "name_match"


def test_join_inference_confidence_ordering(sample_tables_store):
    """Test that inferences are ordered by confidence."""
    join_inference = JoinInference(sample_tables_store, confidence_threshold=0.5)
    
    inferences = join_inference.infer_joins()
    
    # Should be sorted by confidence (descending)
    confidences = [inf.confidence for inf in inferences]
    assert confidences == sorted(confidences, reverse=True)


def test_join_inference_type_compatibility(sample_tables_store):
    """Test that type compatibility is checked."""
    join_inference = JoinInference(sample_tables_store, confidence_threshold=0.5)
    
    # Test type compatibility helper
    assert join_inference._types_compatible("integer", "bigint") == True
    assert join_inference._types_compatible("varchar", "text") == True
    assert join_inference._types_compatible("integer", "varchar") == False
    assert join_inference._types_compatible("numeric", "decimal") == True


def test_join_inference_deterministic(sample_tables_store):
    """Test that join inference is deterministic."""
    join_inference = JoinInference(sample_tables_store, confidence_threshold=0.7)
    
    # Run twice
    inferences1 = join_inference.infer_joins()
    inferences2 = join_inference.infer_joins()
    
    # Should produce identical results
    assert len(inferences1) == len(inferences2)
    
    # Sort for comparison
    inf1_sorted = sorted(inferences1, key=lambda x: (x.source_table_id, x.target_table_id))
    inf2_sorted = sorted(inferences2, key=lambda x: (x.source_table_id, x.target_table_id))
    
    for inf1, inf2 in zip(inf1_sorted, inf2_sorted):
        assert inf1.source_table_id == inf2.source_table_id
        assert inf1.target_table_id == inf2.target_table_id
        assert abs(inf1.confidence - inf2.confidence) < 0.001
        assert inf1.method == inf2.method


def test_join_edge_generation(sample_tables_store):
    """Test that join inferences generate RELATES_TO edges."""
    join_inference = JoinInference(sample_tables_store, confidence_threshold=0.7)
    
    inferences = join_inference.infer_joins()
    edges = join_inference.generate_edges(inferences)
    
    assert len(edges) > 0
    
    # All edges should be RELATES_TO type
    assert all(e.type == "RELATES_TO" for e in edges)
    
    # All edges should have join metadata
    for edge in edges:
        assert "join_type" in edge.attributes
        assert edge.attributes["join_type"] == "inferred"
        assert "confidence" in edge.attributes
        assert "method" in edge.attributes


def test_confidence_threshold_filtering(sample_tables_store):
    """Test that confidence threshold filters low-confidence joins."""
    join_inference_high = JoinInference(sample_tables_store, confidence_threshold=0.9)
    join_inference_low = JoinInference(sample_tables_store, confidence_threshold=0.5)
    
    inferences_high = join_inference_high.infer_joins()
    inferences_low = join_inference_low.infer_joins()
    
    # Low threshold should produce more inferences
    assert len(inferences_low) >= len(inferences_high)
    
    # All high-threshold inferences should be in low-threshold results
    high_joins = {(inf.source_table_id, inf.target_table_id) for inf in inferences_high}
    low_joins = {(inf.source_table_id, inf.target_table_id) for inf in inferences_low}
    assert high_joins.issubset(low_joins)

