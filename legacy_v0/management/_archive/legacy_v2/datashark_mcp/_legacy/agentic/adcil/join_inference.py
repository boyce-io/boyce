"""
Join Inference

Uses statistical and naming heuristics to suggest foreign key relationships
and JOIN paths between tables.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.store import GraphStore

logger = logging.getLogger(__name__)


@dataclass
class InferredJoin:
    """Represents an inferred join relationship."""
    source_table_id: str
    source_column_id: str
    target_table_id: str
    target_column_id: str
    confidence: float
    method: str  # "name_match" | "type_match" | "statistical" | "pattern"
    evidence: Dict[str, any]


class JoinInference:
    """
    Infers join relationships between tables using:
    1. Column name matching (e.g., "user_id" -> "users.id")
    2. Type matching (same data types)
    3. Statistical patterns (common foreign key patterns)
    4. Naming conventions (PK/FK patterns)
    """
    
    def __init__(self, store: GraphStore, confidence_threshold: float = 0.7):
        """
        Initialize join inference.
        
        Args:
            store: GraphStore instance
            confidence_threshold: Minimum confidence for acceptance
        """
        self.store = store
        self.confidence_threshold = confidence_threshold
        
        logger.info("Initialized JoinInference")
    
    def infer_joins(self, table_ids: Optional[List[str]] = None) -> List[InferredJoin]:
        """
        Infer join relationships.
        
        Args:
            table_ids: Specific table IDs to process (None = all tables)
            
        Returns:
            List of join inferences
        """
        inferences: List[InferredJoin] = []
        
        # Get all TABLE/ENTITY nodes
        if table_ids:
            tables = [self.store.get_node(tid) for tid in table_ids if self.store.get_node(tid)]
        else:
            all_nodes = self.store.nodes()
            tables = [n for n in all_nodes if n.type in ("ENTITY", "TABLE") and not n.deleted_at]
        
        # Get all columns
        columns_by_table: Dict[str, List[Node]] = {}
        all_nodes = self.store.nodes()
        for node in all_nodes:
            if node.type == "FIELD" and node.schema and not node.deleted_at:
                # Extract table ID from column (schema:table format)
                table_key = f"{node.schema}:{node.attributes.get('table', 'unknown')}"
                if table_key not in columns_by_table:
                    columns_by_table[table_key] = []
                columns_by_table[table_key].append(node)
        
        logger.info(f"Inferring joins for {len(tables)} tables")
        
        # Compare pairs of tables
        for i, table1 in enumerate(tables):
            for table2 in tables[i+1:]:
                table_inferences = self._infer_joins_between_tables(
                    table1, table2, columns_by_table
                )
                inferences.extend(table_inferences)
        
        # Filter by confidence
        inferences = [i for i in inferences if i.confidence >= self.confidence_threshold]
        
        logger.info(f"Generated {len(inferences)} join inferences")
        return inferences
    
    def _infer_joins_between_tables(
        self,
        table1: Node,
        table2: Node,
        columns_by_table: Dict[str, List[Node]]
    ) -> List[InferredJoin]:
        """Infer joins between two tables."""
        inferences: List[InferredJoin] = []
        
        # Get columns for each table
        table1_key = self._get_table_key(table1)
        table2_key = self._get_table_key(table2)
        
        cols1 = columns_by_table.get(table1_key, [])
        cols2 = columns_by_table.get(table2_key, [])
        
        if not cols1 or not cols2:
            return inferences
        
        # Compare columns
        for col1 in cols1:
            for col2 in cols2:
                inference = self._infer_join_between_columns(table1, col1, table2, col2)
                if inference:
                    inferences.append(inference)
        
        return inferences
    
    def _infer_join_between_columns(
        self,
        table1: Node,
        col1: Node,
        table2: Node,
        col2: Node
    ) -> Optional[InferredJoin]:
        """Infer if two columns form a join relationship."""
        col1_name = col1.name.lower()
        col2_name = col2.name.lower()
        table1_name = table1.name.lower()
        table2_name = table2.name.lower()
        
        # Method 1: Name pattern matching (e.g., "user_id" -> "users.id")
        # Pattern: <table>_id -> <table>.id
        if col1_name.endswith("_id"):
            potential_table = col1_name[:-3]  # Remove "_id"
            if potential_table == table2_name or potential_table in table2_name:
                # Also check if col2 is likely a primary key
                if col2_name == "id" or col2_name == f"{table2_name}_id":
                    return InferredJoin(
                        source_table_id=table1.id,
                        source_column_id=col1.id,
                        target_table_id=table2.id,
                        target_column_id=col2.id,
                        confidence=0.85,
                        method="name_match",
                        evidence={
                            "pattern": "foreign_key_naming",
                            "col1": col1_name,
                            "col2": col2_name
                        }
                    )
        
        # Reverse check
        if col2_name.endswith("_id"):
            potential_table = col2_name[:-3]
            if potential_table == table1_name or potential_table in table1_name:
                if col1_name == "id" or col1_name == f"{table1_name}_id":
                    return InferredJoin(
                        source_table_id=table2.id,
                        source_column_id=col2.id,
                        target_table_id=table1.id,
                        target_column_id=col1.id,
                        confidence=0.85,
                        method="name_match",
                        evidence={
                            "pattern": "foreign_key_naming",
                            "col1": col2_name,
                            "col2": col1_name
                        }
                    )
        
        # Method 2: Exact name match with type compatibility
        if col1_name == col2_name:
            # Check if types are compatible
            type1 = col1.attributes.get("type", "").lower()
            type2 = col2.attributes.get("type", "").lower()
            
            if self._types_compatible(type1, type2):
                # Lower confidence for exact name match (could be coincidence)
                return JoinInference(
                    source_table_id=table1.id,
                    source_column_id=col1.id,
                    target_table_id=table2.id,
                    target_column_id=col2.id,
                    confidence=0.70,
                    method="name_match",
                    evidence={
                        "pattern": "exact_name_match",
                        "type1": type1,
                        "type2": type2
                    }
                )
        
        return None
    
    def _get_table_key(self, table: Node) -> str:
        """Get key for table lookup in columns_by_table."""
        if table.schema:
            return f"{table.schema}:{table.name}"
        return f":{table.name}"
    
    def _types_compatible(self, type1: str, type2: str) -> bool:
        """Check if two data types are compatible for joins."""
        # Normalize types
        type1 = type1.lower().split()[0]  # Take first word
        type2 = type2.lower().split()[0]
        
        # Integer types
        int_types = {"int", "integer", "bigint", "smallint", "serial"}
        if type1 in int_types and type2 in int_types:
            return True
        
        # String types
        string_types = {"varchar", "text", "char", "string"}
        if type1 in string_types and type2 in string_types:
            return True
        
        # Numeric types
        numeric_types = {"numeric", "decimal", "float", "double", "real"}
        if type1 in numeric_types and type2 in numeric_types:
            return True
        
        # Exact match
        if type1 == type2:
            return True
        
        return False
    
    def generate_edges(self, inferences: List[InferredJoin]) -> List[Edge]:
        """Generate JOIN edges from inferences."""
        # Note: We don't create JOIN edge type in the base schema
        # Instead, we create RELATES_TO edges with join metadata
        edges: List[Edge] = []
        
        from datetime import datetime
        from datashark_mcp.context.models import Provenance
        
        for inference in inferences:
            edge_id = f"joins:{inference.source_table_id}:{inference.target_table_id}"
            
            edge = Edge(
                id=edge_id,
                source=inference.source_table_id,
                target=inference.target_table_id,
                type="RELATES_TO",
                attributes={
                    "join_type": "inferred",
                    "source_column": inference.source_column_id,
                    "target_column": inference.target_column_id,
                    "confidence": inference.confidence,
                    "method": inference.method,
                    "evidence": inference.evidence
                },
                provenance=Provenance(
                    system="adcil",
                    source_path="join_inference",
                    extractor_version="0.2.0",
                    extracted_at=datetime.utcnow().isoformat() + "Z"
                )
            )
            edges.append(edge)
        
        logger.info(f"Generated {len(edges)} join edges")
        return edges

