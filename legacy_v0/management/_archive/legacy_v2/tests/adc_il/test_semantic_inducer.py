"""
Test Semantic Inducer

Verifies deterministic BUSINESS_CONCEPT generation and confidence scoring.
"""

import pytest
from datashark_mcp.context.models import Node, Provenance
from datashark_mcp.context.store import GraphStore
from datashark_mcp.agentic.adcil.semantic_inducer import SemanticInducer, ConceptInference
from datetime import datetime


@pytest.fixture
def sample_store():
    """Create a GraphStore with sample nodes."""
    store = GraphStore()
    
    # Add sample nodes
    nodes = [
        Node(
            id="entity:database:revenue_table",
            system="database",
            type="ENTITY",
            name="revenue_table",
            attributes={"table_name": "revenue_table"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            )
        ),
        Node(
            id="field:database:revenue_table:amount",
            system="database",
            type="FIELD",
            name="amount",
            attributes={"type": "decimal", "table": "revenue_table"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
        Node(
            id="field:database:revenue_table:customer_id",
            system="database",
            type="FIELD",
            name="customer_id",
            attributes={"type": "integer", "table": "revenue_table"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
        Node(
            id="field:database:revenue_table:created_at",
            system="database",
            type="FIELD",
            name="created_at",
            attributes={"type": "timestamp", "table": "revenue_table"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
    ]
    
    for node in nodes:
        store.add_node(node)
    
    return store


@pytest.fixture
def concept_catalog():
    """Sample concept catalog."""
    return {
        "Revenue": {
            "description": "Revenue or sales amount",
            "aliases": ["sales", "income", "revenue_amount"]
        },
        "Customer": {
            "description": "Customer or client entity",
            "aliases": ["client", "user", "customer_id"]
        },
        "Date": {
            "description": "Date or timestamp",
            "aliases": ["timestamp", "created_at", "updated_at", "date"]
        }
    }


@pytest.fixture
def enrichment_rules():
    """Sample enrichment rules."""
    return [
        {"pattern": r"(?i)\brevenue\b|\bsales\b|\bincome\b", "concept": "Revenue", "weight": 1.0},
        {"pattern": r"(?i)\bcustomer\b|\bclient\b|\buser\b", "concept": "Customer", "weight": 1.0},
        {"pattern": r"(?i)\bdate\b|\btimestamp\b|\bcreated_at\b|\bupdated_at\b", "concept": "Date", "weight": 1.0}
    ]


def test_semantic_inducer_deterministic(sample_store, concept_catalog, enrichment_rules):
    """Test that semantic inducer produces deterministic results."""
    inducer = SemanticInducer(
        store=sample_store,
        concept_catalog=concept_catalog,
        rules=enrichment_rules,
        confidence_threshold=0.7
    )
    
    # Run inference twice
    inferences1 = inducer.infer_concepts()
    inferences2 = inducer.infer_concepts()
    
    # Should produce identical results
    assert len(inferences1) == len(inferences2)
    
    # Sort by node_id and concept_name for comparison
    inf1_sorted = sorted(inferences1, key=lambda x: (x.node_id, x.concept_name))
    inf2_sorted = sorted(inferences2, key=lambda x: (x.node_id, x.concept_name))
    
    for inf1, inf2 in zip(inf1_sorted, inf2_sorted):
        assert inf1.node_id == inf2.node_id
        assert inf1.concept_name == inf2.concept_name
        assert abs(inf1.confidence - inf2.confidence) < 0.001  # Float comparison
        assert inf1.method == inf2.method


def test_confidence_scores_reproducible(sample_store, concept_catalog, enrichment_rules):
    """Test that confidence scores are reproducible."""
    inducer = SemanticInducer(
        store=sample_store,
        concept_catalog=concept_catalog,
        rules=enrichment_rules,
        confidence_threshold=0.5
    )
    
    inferences = inducer.infer_concepts()
    
    # Check that confidence scores are within expected ranges
    for inf in inferences:
        assert 0.0 <= inf.confidence <= 1.0
        
        # Name matches should have high confidence
        if inf.method == "name_match":
            assert inf.confidence >= 0.85
        
        # Pattern matches should have medium-high confidence
        if inf.method == "pattern":
            assert 0.70 <= inf.confidence <= 0.95
        
        # Statistical matches should have lower confidence
        if inf.method == "statistical":
            assert 0.60 <= inf.confidence <= 0.70


def test_concept_generation(sample_store, concept_catalog, enrichment_rules):
    """Test BUSINESS_CONCEPT node and DESCRIBES edge generation."""
    inducer = SemanticInducer(
        store=sample_store,
        concept_catalog=concept_catalog,
        rules=enrichment_rules,
        confidence_threshold=0.7
    )
    
    inferences = inducer.infer_concepts()
    nodes, edges = inducer.generate_nodes_and_edges(inferences)
    
    # Should generate concept nodes
    concept_nodes = [n for n in nodes if n.type == "BUSINESS_CONCEPT"]
    assert len(concept_nodes) > 0
    
    # Should generate DESCRIBES edges
    assert len(edges) > 0
    assert all(e.type == "DESCRIBES" for e in edges)
    
    # Each edge should have confidence metadata
    for edge in edges:
        assert "confidence" in edge.attributes
        assert "method" in edge.attributes


def test_name_matching(sample_store, concept_catalog):
    """Test exact name and alias matching."""
    inducer = SemanticInducer(
        store=sample_store,
        concept_catalog=concept_catalog,
        rules=[],
        confidence_threshold=0.5
    )
    
    # Field named "customer_id" should match "Customer" concept via alias
    customer_field = sample_store.get_node("field:database:revenue_table:customer_id")
    inferences = inducer._infer_for_node(customer_field)
    
    customer_inf = next((i for i in inferences if i.concept_name == "Customer"), None)
    assert customer_inf is not None
    assert customer_inf.method == "name_match"
    assert customer_inf.confidence >= 0.90


def test_pattern_matching(sample_store, enrichment_rules):
    """Test pattern-based matching."""
    inducer = SemanticInducer(
        store=sample_store,
        concept_catalog={},
        rules=enrichment_rules,
        confidence_threshold=0.5
    )
    
    # Field named "created_at" should match "Date" concept via pattern
    date_field = sample_store.get_node("field:database:revenue_table:created_at")
    inferences = inducer._infer_for_node(date_field)
    
    date_inf = next((i for i in inferences if i.concept_name == "Date"), None)
    assert date_inf is not None
    assert date_inf.method == "pattern"


def test_confidence_threshold_filtering(sample_store, concept_catalog, enrichment_rules):
    """Test that confidence threshold filters low-confidence inferences."""
    # High threshold
    inducer_high = SemanticInducer(
        store=sample_store,
        concept_catalog=concept_catalog,
        rules=enrichment_rules,
        confidence_threshold=0.9
    )
    
    # Low threshold
    inducer_low = SemanticInducer(
        store=sample_store,
        concept_catalog=concept_catalog,
        rules=enrichment_rules,
        confidence_threshold=0.5
    )
    
    inferences_high = inducer_high.infer_concepts()
    inferences_low = inducer_low.infer_concepts()
    
    # Low threshold should produce more inferences
    assert len(inferences_low) >= len(inferences_high)
    
    # All high-threshold inferences should be in low-threshold results
    high_concepts = {(i.node_id, i.concept_name) for i in inferences_high}
    low_concepts = {(i.node_id, i.concept_name) for i in inferences_low}
    assert high_concepts.issubset(low_concepts)

