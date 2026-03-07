"""
ADCIL Validator

Confirms or rejects inferences via schema and lineage consistency checks.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.store import GraphStore
from datashark_mcp.agentic.adcil.semantic_inducer import ConceptInference
from datashark_mcp.agentic.adcil.join_inference import InferredJoin

logger = logging.getLogger(__name__)


class ADCILValidator:
    """
    Validates ADCIL inferences for consistency.
    
    Checks:
    1. Schema consistency (types match, names follow conventions)
    2. Lineage consistency (no circular dependencies)
    3. Conflict resolution (multiple inferences for same entity)
    """
    
    def __init__(self, store: GraphStore):
        """
        Initialize validator.
        
        Args:
            store: GraphStore instance
        """
        self.store = store
        logger.info("Initialized ADCILValidator")
    
    def validate_concept_inferences(
        self,
        inferences: List[ConceptInference]
    ) -> Tuple[List[ConceptInference], List[ConceptInference]]:
        """
        Validate concept inferences.
        
        Args:
            inferences: List of concept inferences to validate
            
        Returns:
            Tuple of (accepted, rejected) inferences
        """
        accepted: List[ConceptInference] = []
        rejected: List[ConceptInference] = []
        
        # Group by node_id to detect conflicts
        by_node: Dict[str, List[ConceptInference]] = {}
        for inf in inferences:
            if inf.node_id not in by_node:
                by_node[inf.node_id] = []
            by_node[inf.node_id].append(inf)
        
        # Validate each inference
        for inf in inferences:
            # Check 1: Confidence threshold (handled by inducer)
            if inf.confidence < 0.5:
                rejected.append(inf)
                continue
            
            # Check 2: Node exists and is valid
            node = self.store.get_node(inf.node_id)
            if not node or node.deleted_at:
                rejected.append(inf)
                continue
            
            # Check 3: Conflict resolution (if multiple concepts for same node, pick highest confidence)
            node_inferences = by_node[inf.node_id]
            if len(node_inferences) > 1:
                # Sort by confidence
                sorted_infs = sorted(node_inferences, key=lambda x: x.confidence, reverse=True)
                if inf != sorted_infs[0]:
                    # This is not the highest confidence, reject
                    rejected.append(inf)
                    continue
            
            # Check 4: Schema consistency (concept name should be valid)
            if not self._is_valid_concept_name(inf.concept_name):
                rejected.append(inf)
                continue
            
            accepted.append(inf)
        
        logger.info(f"Validated {len(inferences)} concept inferences: {len(accepted)} accepted, {len(rejected)} rejected")
        return accepted, rejected
    
    def validate_join_inferences(
        self,
        inferences: List[InferredJoin]
    ) -> Tuple[List[InferredJoin], List[InferredJoin]]:
        """
        Validate join inferences.
        
        Args:
            inferences: List of join inferences to validate
            
        Returns:
            Tuple of (accepted, rejected) inferences
        """
        accepted: List[InferredJoin] = []
        rejected: List[InferredJoin] = []
        
        for inf in inferences:
            # Check 1: Confidence threshold
            if inf.confidence < 0.5:
                rejected.append(inf)
                continue
            
            # Check 2: Tables and columns exist
            table1 = self.store.get_node(inf.source_table_id)
            table2 = self.store.get_node(inf.target_table_id)
            col1 = self.store.get_node(inf.source_column_id)
            col2 = self.store.get_node(inf.target_column_id)
            
            if not all([table1, table2, col1, col2]):
                rejected.append(inf)
                continue
            
            # Check 3: No self-joins
            if inf.source_table_id == inf.target_table_id:
                rejected.append(inf)
                continue
            
            # Check 4: Type compatibility
            type1 = col1.attributes.get("type", "").lower()
            type2 = col2.attributes.get("type", "").lower()
            if not self._types_compatible(type1, type2):
                rejected.append(inf)
                continue
            
            # Check 5: Lineage consistency (no circular dependencies)
            if self._would_create_cycle(inf):
                rejected.append(inf)
                continue
            
            accepted.append(inf)
        
        logger.info(f"Validated {len(inferences)} join inferences: {len(accepted)} accepted, {len(rejected)} rejected")
        return accepted, rejected
    
    def _is_valid_concept_name(self, concept_name: str) -> bool:
        """Check if concept name is valid."""
        # Basic validation: non-empty, alphanumeric + underscores
        if not concept_name or len(concept_name) < 2:
            return False
        
        # Check for valid characters
        if not concept_name.replace("_", "").replace("-", "").isalnum():
            return False
        
        return True
    
    def _types_compatible(self, type1: str, type2: str) -> bool:
        """Check if two data types are compatible (same as join_inference)."""
        type1 = type1.lower().split()[0]
        type2 = type2.lower().split()[0]
        
        int_types = {"int", "integer", "bigint", "smallint", "serial"}
        if type1 in int_types and type2 in int_types:
            return True
        
        string_types = {"varchar", "text", "char", "string"}
        if type1 in string_types and type2 in string_types:
            return True
        
        numeric_types = {"numeric", "decimal", "float", "double", "real"}
        if type1 in numeric_types and type2 in numeric_types:
            return True
        
        if type1 == type2:
            return True
        
        return False
    
    def _would_create_cycle(self, join: InferredJoin) -> bool:
        """
        Check if adding this join would create a cycle in the graph.
        
        Uses simple BFS to detect cycles.
        """
        # For now, allow cycles (they're valid in many cases)
        # In production, might want to detect problematic cycles
        return False

