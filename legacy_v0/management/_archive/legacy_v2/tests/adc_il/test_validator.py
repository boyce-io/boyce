"""
Test ADCIL Validator

Tests acceptance/rejection logic under edge cases.
"""

import pytest
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.store import GraphStore
from datashark_mcp.agentic.adcil.validator import ADCILValidator
from datashark_mcp.agentic.adcil.semantic_inducer import ConceptInference
from datashark_mcp.agentic.adcil.join_inference import InferredJoin
from datetime import datetime


@pytest.fixture
def sample_store():
    """Create a GraphStore with sample nodes."""
    store = GraphStore()
    
    # Add a table node
    table_node = Node(
        id="entity:database:test_table",
        system="database",
        type="ENTITY",
        name="test_table",
        attributes={},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        )
    )
    store.add_node(table_node)
    
    # Add field nodes
    field1 = Node(
        id="field:database:test_table:field1",
        system="database",
        type="FIELD",
        name="field1",
        attributes={"type": "integer", "table": "test_table"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(field1)
    
    field2 = Node(
        id="field:database:test_table:field2",
        system="database",
        type="FIELD",
        name="field2",
        attributes={"type": "varchar", "table": "test_table"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    store.add_node(field2)
    
    return store


def test_validate_concept_inferences_low_confidence(sample_store):
    """Test that low-confidence inferences are rejected."""
    validator = ADCILValidator(sample_store)
    
    inferences = [
        ConceptInference(
            node_id="field:database:test_table:field1",
            concept_name="TestConcept",
            confidence=0.3,  # Below threshold
            method="statistical",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_concept_inferences(inferences)
    
    assert len(accepted) == 0
    assert len(rejected) == 1
    assert rejected[0].confidence < 0.5


def test_validate_concept_inferences_nonexistent_node(sample_store):
    """Test that inferences for non-existent nodes are rejected."""
    validator = ADCILValidator(sample_store)
    
    inferences = [
        ConceptInference(
            node_id="nonexistent:node",
            concept_name="TestConcept",
            confidence=0.9,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_concept_inferences(inferences)
    
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_concept_inferences_conflict_resolution(sample_store):
    """Test that multiple concepts for same node are resolved (highest confidence wins)."""
    validator = ADCILValidator(sample_store)
    
    node_id = "field:database:test_table:field1"
    
    inferences = [
        ConceptInference(
            node_id=node_id,
            concept_name="ConceptA",
            confidence=0.8,
            method="name_match",
            evidence={}
        ),
        ConceptInference(
            node_id=node_id,
            concept_name="ConceptB",
            confidence=0.95,  # Higher confidence
            method="name_match",
            evidence={}
        ),
        ConceptInference(
            node_id=node_id,
            concept_name="ConceptC",
            confidence=0.7,  # Lower confidence
            method="pattern",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_concept_inferences(inferences)
    
    # Should accept only the highest confidence
    assert len(accepted) == 1
    assert accepted[0].concept_name == "ConceptB"
    assert accepted[0].confidence == 0.95
    
    # Should reject the others
    assert len(rejected) == 2
    rejected_concepts = {inf.concept_name for inf in rejected}
    assert rejected_concepts == {"ConceptA", "ConceptC"}


def test_validate_concept_inferences_invalid_concept_name(sample_store):
    """Test that invalid concept names are rejected."""
    validator = ADCILValidator(sample_store)
    
    # Empty name
    inferences = [
        ConceptInference(
            node_id="field:database:test_table:field1",
            concept_name="",
            confidence=0.9,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_concept_inferences(inferences)
    assert len(accepted) == 0
    assert len(rejected) == 1
    
    # Invalid characters
    inferences = [
        ConceptInference(
            node_id="field:database:test_table:field1",
            concept_name="test@concept#",
            confidence=0.9,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_concept_inferences(inferences)
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_join_inferences_low_confidence(sample_store):
    """Test that low-confidence join inferences are rejected."""
    validator = ADCILValidator(sample_store)
    
    inferences = [
        InferredJoin(
            source_table_id="entity:database:test_table",
            source_column_id="field:database:test_table:field1",
            target_table_id="entity:database:test_table",
            target_column_id="field:database:test_table:field2",
            confidence=0.3,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_join_inferences(inferences)
    
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_join_inferences_nonexistent_entities(sample_store):
    """Test that joins with non-existent tables/columns are rejected."""
    validator = ADCILValidator(sample_store)
    
    inferences = [
        InferredJoin(
            source_table_id="nonexistent:table",
            source_column_id="field:database:test_table:field1",
            target_table_id="entity:database:test_table",
            target_column_id="field:database:test_table:field2",
            confidence=0.9,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_join_inferences(inferences)
    
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_join_inferences_self_join_rejected(sample_store):
    """Test that self-joins are rejected."""
    validator = ADCILValidator(sample_store)
    
    inferences = [
        InferredJoin(
            source_table_id="entity:database:test_table",
            source_column_id="field:database:test_table:field1",
            target_table_id="entity:database:test_table",  # Same table
            target_column_id="field:database:test_table:field2",
            confidence=0.9,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_join_inferences(inferences)
    
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_join_inferences_type_incompatibility(sample_store):
    """Test that type-incompatible joins are rejected."""
    validator = ADCILValidator(sample_store)
    
    # Create another table with incompatible type
    table2 = Node(
        id="entity:database:test_table2",
        system="database",
        type="ENTITY",
        name="test_table2",
        attributes={},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        )
    )
    sample_store.add_node(table2)
    
    field3 = Node(
        id="field:database:test_table2:field3",
        system="database",
        type="FIELD",
        name="field3",
        attributes={"type": "varchar", "table": "test_table2"},
        provenance=Provenance(
            system="database",
            source_path="test.db",
            extractor_version="0.2.0",
            extracted_at=datetime.utcnow().isoformat() + "Z"
        ),
        schema="public"
    )
    sample_store.add_node(field3)
    
    # Try to join integer field with varchar field
    inferences = [
        InferredJoin(
            source_table_id="entity:database:test_table",
            source_column_id="field:database:test_table:field1",  # integer
            target_table_id="entity:database:test_table2",
            target_column_id="field:database:test_table2:field3",  # varchar
            confidence=0.9,
            method="name_match",
            evidence={}
        )
    ]
    
    accepted, rejected = validator.validate_join_inferences(inferences)
    
    assert len(accepted) == 0
    assert len(rejected) == 1

