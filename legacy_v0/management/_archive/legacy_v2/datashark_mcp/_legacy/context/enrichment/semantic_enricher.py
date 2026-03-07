"""
Semantic Enricher

Maps entities to business concepts and creates DESCRIBES edges.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.id_utils import compute_edge_id
from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
from datashark_mcp.context.enrichment.rules import EnrichmentRules
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class SemanticEnricher:
    """Enriches graph with business concept mappings."""
    
    def __init__(self, store: GraphStore, catalog: ConceptCatalog, rules: EnrichmentRules = None):
        """
        Initialize semantic enricher.
        
        Args:
            store: GraphStore instance
            catalog: ConceptCatalog instance
            rules: EnrichmentRules instance (optional, creates default if None)
        """
        self.store = store
        self.catalog = catalog
        self.rules = rules or EnrichmentRules()
        self.metrics = {
            "nodes_enriched": 0,
            "new_edges": 0,
            "new_concepts": 0
        }
    
    def enrich(self) -> Dict[str, Any]:
        """
        Enrich all nodes in store with business concept mappings.
        
        Returns:
            Dict with metrics: nodes_enriched, new_edges, new_concepts
        """
        self.metrics = {
            "nodes_enriched": 0,
            "new_edges": 0,
            "new_concepts": 0
        }
        
        # Get all nodes from store (excluding BUSINESS_CONCEPT nodes)
        all_nodes = self.store.nodes()
        entity_nodes = [n for n in all_nodes if n.type != "BUSINESS_CONCEPT" and not n.deleted_at]
        
        # Load all concepts as nodes
        concept_nodes = self.catalog.to_nodes()
        for concept_node in concept_nodes:
            self.store.add_node(concept_node)
            self.metrics["new_concepts"] += 1
        
        # Enrich each entity node
        for node in entity_nodes:
            enriched = self._enrich_node(node, concept_nodes)
            if enriched:
                self.metrics["nodes_enriched"] += 1
        
        logger.info(f"Semantic enrichment complete: {self.metrics}")
        return self.metrics
    
    def _enrich_node(self, node: Node, concept_nodes: List[Node]) -> bool:
        """
        Enrich a single node with concept mappings.
        
        Args:
            node: Node to enrich
            concept_nodes: List of concept nodes
            
        Returns:
            True if node was enriched, False otherwise
        """
        enriched = False
        
        # Try name/alias match first
        concept = self.catalog.get_concept(node.name)
        if not concept:
            # Try search
            matches = self.catalog.search(node.name)
            if matches:
                concept = matches[0]  # Take first match
        
        # Try pattern rules
        if not concept:
            rule_matches = self.rules.find_matches(node.name)
            if rule_matches:
                concept_name = rule_matches[0].concept
                concept = self.catalog.get_concept(concept_name)
        
        # Create DESCRIBES edge if concept found
        if concept:
            concept_node = concept.to_node()
            
            # Ensure concept node exists in store
            existing = self.store.get_node(concept_node.id)
            if not existing:
                self.store.add_node(concept_node)
            
            # Create DESCRIBES edge (concept describes entity)
            edge_id = compute_edge_id("DESCRIBES", concept_node.id, node.id)
            existing_edge = self.store.get_edge(edge_id)
            
            if not existing_edge:
                edge = Edge(
                    id=edge_id,
                    src=concept_node.id,
                    dst=node.id,
                    type="DESCRIBES",
                    attributes={
                        "confidence": 0.8,  # Default confidence
                        "source": "semantic_enrichment"
                    },
                    provenance=Provenance(
                        system="semantic",
                        source_path="semantic_enrichment",
                        extractor_version="1.0.0",
                        extracted_at=datetime.now(timezone.utc).isoformat()
                    )
                )
                self.store.add_edge(edge)
                self.metrics["new_edges"] += 1
                enriched = True
        
        return enriched

