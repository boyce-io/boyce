"""
Semantic Inducer

Generates inferred BUSINESS_CONCEPT nodes and DESCRIBES edges based on:
- Name/alias matching
- Pattern rules
- Text similarity (via embeddings)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.store import GraphStore

logger = logging.getLogger(__name__)


@dataclass
class ConceptInference:
    """Represents an inferred concept mapping."""
    node_id: str
    concept_name: str
    confidence: float
    method: str  # "name_match" | "pattern" | "similarity" | "statistical"
    evidence: Dict[str, any]
    

class SemanticInducer:
    """
    Infers BUSINESS_CONCEPT nodes and DESCRIBES edges from extracted nodes.
    
    Methods:
    1. Name/alias matching against concept catalog
    2. Regex/pattern rules (from rules.yaml)
    3. Text similarity (embedding-based, future)
    4. Statistical co-occurrence patterns
    """
    
    def __init__(
        self,
        store: GraphStore,
        concept_catalog: Optional[Dict[str, Dict[str, any]]] = None,
        rules: Optional[List[Dict[str, any]]] = None,
        confidence_threshold: float = 0.8
    ):
        """
        Initialize semantic inducer.
        
        Args:
            store: GraphStore instance
            concept_catalog: Pre-defined concept mappings (name -> {aliases, description})
            rules: Pattern-based rules for matching
            confidence_threshold: Minimum confidence for acceptance
        """
        self.store = store
        self.concept_catalog = concept_catalog or {}
        self.rules = rules or []
        self.confidence_threshold = confidence_threshold
        
        # Compile rules for efficiency
        self._compiled_rules: List[Tuple[re.Pattern, str, float]] = []
        for rule in self.rules:
            pattern = rule.get("pattern")
            concept = rule.get("concept")
            weight = rule.get("weight", 1.0)
            if pattern and concept:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    self._compiled_rules.append((compiled, concept, weight))
                except re.error as e:
                    logger.warning(f"Invalid regex pattern: {pattern}: {e}")
        
        logger.info(f"Initialized SemanticInducer with {len(self.concept_catalog)} concepts, {len(self._compiled_rules)} rules")
    
    def infer_concepts(self, node_ids: Optional[List[str]] = None) -> List[ConceptInference]:
        """
        Infer concepts for nodes.
        
        Args:
            node_ids: Specific node IDs to process (None = all nodes)
            
        Returns:
            List of concept inferences with confidence scores
        """
        inferences: List[ConceptInference] = []
        
        # Get nodes to process
        if node_ids:
            nodes = [self.store.get_node(nid) for nid in node_ids if self.store.get_node(nid)]
        else:
            nodes = self.store.nodes()
        
        # Filter out BUSINESS_CONCEPT nodes (we don't infer concepts for concepts)
        nodes = [n for n in nodes if n.type != "BUSINESS_CONCEPT" and not n.deleted_at]
        
        logger.info(f"Inferring concepts for {len(nodes)} nodes")
        
        for node in nodes:
            node_inferences = self._infer_for_node(node)
            inferences.extend(node_inferences)
        
        logger.info(f"Generated {len(inferences)} concept inferences")
        return inferences
    
    def _infer_for_node(self, node: Node) -> List[ConceptInference]:
        """Infer concepts for a single node."""
        inferences: List[ConceptInference] = []
        
        # Method 1: Name/alias matching
        name_match = self._match_by_name(node)
        if name_match:
            inferences.append(name_match)
        
        # Method 2: Pattern matching
        pattern_match = self._match_by_pattern(node)
        if pattern_match and not any(i.concept_name == pattern_match.concept_name for i in inferences):
            inferences.append(pattern_match)
        
        # Method 3: Statistical co-occurrence (future: embedding similarity)
        # For now, skip if we have high-confidence matches
        if not inferences or max(i.confidence for i in inferences) < 0.7:
            statistical_match = self._match_by_statistics(node)
            if statistical_match:
                inferences.append(statistical_match)
        
        # Filter by confidence threshold
        inferences = [i for i in inferences if i.confidence >= self.confidence_threshold]
        
        return inferences
    
    def _match_by_name(self, node: Node) -> Optional[ConceptInference]:
        """Match node to concept via name/alias."""
        node_name_lower = node.name.lower()
        
        for concept_name, concept_info in self.concept_catalog.items():
            # Exact match
            if node_name_lower == concept_name.lower():
                return ConceptInference(
                    node_id=node.id,
                    concept_name=concept_name,
                    confidence=0.95,
                    method="name_match",
                    evidence={"match_type": "exact", "node_name": node.name}
                )
            
            # Check aliases
            aliases = concept_info.get("aliases", [])
            for alias in aliases:
                if node_name_lower == alias.lower():
                    return ConceptInference(
                        node_id=node.id,
                        concept_name=concept_name,
                        confidence=0.90,
                        method="name_match",
                        evidence={"match_type": "alias", "alias": alias, "node_name": node.name}
                    )
        
        return None
    
    def _match_by_pattern(self, node: Node) -> Optional[ConceptInference]:
        """Match node to concept via regex patterns."""
        node_name = node.name
        node_name_lower = node_name.lower()
        
        best_match: Optional[Tuple[str, float]] = None
        
        for pattern, concept_name, weight in self._compiled_rules:
            if pattern.search(node_name_lower):
                # Base confidence from pattern match
                confidence = 0.75 * weight
                
                # Boost if pattern matches strongly (full word boundaries)
                if pattern.search(r'\b' + re.escape(node_name_lower) + r'\b'):
                    confidence = min(0.95, confidence * 1.2)
                
                if best_match is None or confidence > best_match[1]:
                    best_match = (concept_name, confidence)
        
        if best_match:
            concept_name, confidence = best_match
            return ConceptInference(
                node_id=node.id,
                concept_name=concept_name,
                confidence=confidence,
                method="pattern",
                evidence={"pattern_matched": True, "node_name": node_name}
            )
        
        return None
    
    def _match_by_statistics(self, node: Node) -> Optional[ConceptInference]:
        """
        Match via statistical patterns (co-occurrence, naming conventions).
        
        This is a placeholder for future embedding-based similarity.
        For now, uses simple heuristics.
        """
        # Simple heuristic: check if node name contains common concept keywords
        # In production, this would use embeddings or co-occurrence analysis
        
        node_name_lower = node.name.lower()
        
        # Common patterns that suggest concepts
        concept_keywords = {
            "revenue": ["revenue", "sales", "income"],
            "customer": ["customer", "client", "user"],
            "date": ["date", "time", "timestamp", "created", "updated"],
            "country": ["country", "nation", "region"],
            "amount": ["amount", "value", "price", "cost"]
        }
        
        for concept_name, keywords in concept_keywords.items():
            if any(keyword in node_name_lower for keyword in keywords):
                # Low confidence for statistical matches
                return ConceptInference(
                    node_id=node.id,
                    concept_name=concept_name,
                    confidence=0.65,  # Lower confidence for statistical
                    method="statistical",
                    evidence={"keywords_found": [k for k in keywords if k in node_name_lower]}
                )
        
        return None
    
    def generate_nodes_and_edges(
        self,
        inferences: List[ConceptInference]
    ) -> Tuple[List[Node], List[Edge]]:
        """
        Generate BUSINESS_CONCEPT nodes and DESCRIBES edges from inferences.
        
        Args:
            inferences: List of concept inferences
            
        Returns:
            Tuple of (nodes, edges) to add to graph
        """
        nodes: List[Node] = []
        edges: List[Edge] = []
        
        # Group by concept name to create unique concept nodes
        concept_nodes: Dict[str, Node] = {}
        
        for inference in inferences:
            # Get or create concept node
            if inference.concept_name not in concept_nodes:
                concept_id = f"business_concept:{inference.concept_name}"
                concept_node = Node(
                    id=concept_id,
                    system="semantic",
                    type="BUSINESS_CONCEPT",
                    name=inference.concept_name,
                    attributes={
                        "description": self.concept_catalog.get(inference.concept_name, {}).get("description", ""),
                        "inferred": True,
                        "confidence_avg": inference.confidence
                    },
                    provenance=Provenance(
                        system="semantic",
                        source_path="adcil_inference",
                        extractor_version="0.2.0",
                        extracted_at=datetime.utcnow().isoformat() + "Z"
                    )
                )
                concept_nodes[inference.concept_name] = concept_node
                nodes.append(concept_node)
            
            # Create DESCRIBES edge
            source_node = self.store.get_node(inference.node_id)
            if source_node:
                edge_id = f"describes:{source_node.id}:{concept_nodes[inference.concept_name].id}"
                edge = Edge(
                    id=edge_id,
                    source=source_node.id,
                    target=concept_nodes[inference.concept_name].id,
                    type="DESCRIBES",
                    attributes={
                        "confidence": inference.confidence,
                        "method": inference.method,
                        "evidence": inference.evidence
                    },
                    provenance=Provenance(
                        system="semantic",
                        source_path="adcil_inference",
                        extractor_version="0.2.0",
                        extracted_at=datetime.utcnow().isoformat() + "Z"
                    )
                )
                edges.append(edge)
        
        logger.info(f"Generated {len(nodes)} concept nodes, {len(edges)} DESCRIBES edges")
        return nodes, edges

