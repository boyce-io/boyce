"""
Tests for Semantic Enrichment

Validates mapping reproducibility and ensures no system-specific vocabulary leaks.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.models import Node, Provenance
from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
from datashark_mcp.context.enrichment.semantic_enricher import SemanticEnricher
from datashark_mcp.context.enrichment.rules import EnrichmentRules
from datashark_mcp.context.id_utils import compute_edge_id


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


def test_concept_catalog_add_and_get():
    """Test adding and retrieving concepts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_file = Path(tmpdir) / "concepts.json"
        catalog = ConceptCatalog(concepts_file=catalog_file)
        
        catalog.add_concept("Revenue", "Total income", aliases=["sales", "income"])
        
        concept = catalog.get_concept("Revenue")
        assert concept is not None
        assert concept.name == "Revenue"
        assert "sales" in concept.aliases


def test_concept_catalog_search():
    """Test concept search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_file = Path(tmpdir) / "concepts.json"
        catalog = ConceptCatalog(concepts_file=catalog_file)
        
        catalog.add_concept("Revenue", "Total income", aliases=["sales"])
        
        results = catalog.search("sales")
        assert len(results) > 0
        assert any(c.name == "Revenue" for c in results)


def test_concept_catalog_deterministic_ordering():
    """Test that concepts are stored in deterministic order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_file = Path(tmpdir) / "concepts.json"
        catalog = ConceptCatalog(concepts_file=catalog_file)
        
        # Add concepts in non-alphabetical order
        catalog.add_concept("Zebra", "Animal")
        catalog.add_concept("Apple", "Fruit")
        catalog.add_concept("Banana", "Fruit")
        
        concepts = catalog.get_all_concepts()
        names = [c.name for c in concepts]
        assert names == sorted(names), "Concepts must be sorted by name"


def test_semantic_enricher_maps_to_concepts():
    """Test that enricher creates DESCRIBES edges."""
    store = GraphStore()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_file = Path(tmpdir) / "concepts.json"
        catalog = ConceptCatalog(concepts_file=catalog_file)
        catalog.add_concept("Revenue", "Total income", aliases=["sales"])
        
        # Add entity node
        node = create_test_node("node1", "revenue_table")
        store.add_node(node)
        
        # Enrich
        enricher = SemanticEnricher(store, catalog)
        metrics = enricher.enrich()
        
        # Should create DESCRIBES edge
        assert metrics["new_edges"] > 0
        
        # Check edge exists (may be concept -> node or node -> concept)
        concept_node = catalog.get_concept("Revenue").to_node()
        edge_id1 = compute_edge_id("DESCRIBES", concept_node.id, node.id)
        edge_id2 = compute_edge_id("DESCRIBES", node.id, concept_node.id)
        edge = store.get_edge(edge_id1) or store.get_edge(edge_id2)
        assert edge is not None
        assert edge.type == "DESCRIBES"


def test_enrichment_deterministic():
    """Test that enrichment is deterministic."""
    store1 = GraphStore()
    store2 = GraphStore()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_file = Path(tmpdir) / "concepts.json"
        catalog1 = ConceptCatalog(concepts_file=catalog_file)
        catalog2 = ConceptCatalog(concepts_file=catalog_file)
        
        catalog1.add_concept("Revenue", "Total income")
        
        # Add same nodes to both stores
        node = create_test_node("node1", "revenue")
        store1.add_node(node)
        store2.add_node(node)
        
        # Enrich both
        enricher1 = SemanticEnricher(store1, catalog1)
        enricher2 = SemanticEnricher(store2, catalog2)
        
        metrics1 = enricher1.enrich()
        metrics2 = enricher2.enrich()
        
        # Metrics should be identical
        assert metrics1 == metrics2
        
        # Edge IDs should be identical
        edges1 = [e.id for e in store1.get_edges_by_type("DESCRIBES")]
        edges2 = [e.id for e in store2.get_edges_by_type("DESCRIBES")]
        assert sorted(edges1) == sorted(edges2)


def test_no_system_specific_vocabulary():
    """Test that enrichment code contains no system-specific vocabulary."""
    import re
    from pathlib import Path
    
    enrichment_dir = Path(__file__).resolve().parents[2]
    tool_names = ["looker", "dbt", "airflow", "tableau", "datahub"]
    
    violations = []
    for file_path in enrichment_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            for line_num, line in enumerate(content.split("\n"), 1):
                for tool_name in tool_names:
                    if re.search(rf"\b{tool_name}\b", line, re.IGNORECASE):
                        if "test" not in line.lower() and "example" not in line.lower():
                            violations.append(f"{file_path.name}:{line_num}: {line.strip()}")
    
    if violations:
        pytest.fail(f"System-specific vocabulary found:\n" + "\n".join(violations))

