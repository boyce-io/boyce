"""
ADCIL Persistence

Writes accepted inferences into instance manifests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Dict, Any
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.store import GraphStore

logger = logging.getLogger(__name__)


class ADCILPersistence:
    """
    Persists ADCIL-generated nodes and edges to manifests.
    
    Writes:
    - BUSINESS_CONCEPT nodes
    - DESCRIBES edges
    - JOIN/RELATES_TO edges
    """
    
    def __init__(self, store: GraphStore, output_dir: Path):
        """
        Initialize persistence layer.
        
        Args:
            store: GraphStore instance (already contains inferred nodes/edges)
            output_dir: Directory to write manifest files
        """
        self.store = store
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized ADCILPersistence with output_dir: {output_dir}")
    
    def persist_inferences(
        self,
        concept_nodes: List[Node],
        concept_edges: List[Edge],
        join_edges: List[Edge]
    ) -> Dict[str, Any]:
        """
        Persist inferred nodes and edges to manifest files.
        
        Args:
            concept_nodes: BUSINESS_CONCEPT nodes to persist
            concept_edges: DESCRIBES edges to persist
            join_edges: JOIN/RELATES_TO edges to persist
            
        Returns:
            Summary dict with counts
        """
        import json
        
        # Write nodes (append to existing nodes.jsonl)
        nodes_path = self.output_dir / "nodes.jsonl"
        adcil_nodes_path = self.output_dir / "adcil_nodes.jsonl"
        
        # Write ADCIL-specific nodes to separate file for tracking
        with open(adcil_nodes_path, "w", encoding="utf-8") as f:
            for node in concept_nodes:
                f.write(json.dumps(node.to_dict(), ensure_ascii=False) + "\n")
        
        # Also add to main nodes file
        with open(nodes_path, "a", encoding="utf-8") as f:
            for node in concept_nodes:
                f.write(json.dumps(node.to_dict(), ensure_ascii=False) + "\n")
        
        # Write edges (append to existing edges.jsonl)
        edges_path = self.output_dir / "edges.jsonl"
        adcil_edges_path = self.output_dir / "adcil_edges.jsonl"
        
        all_edges = concept_edges + join_edges
        
        # Write ADCIL-specific edges to separate file for tracking
        with open(adcil_edges_path, "w", encoding="utf-8") as f:
            for edge in all_edges:
                f.write(json.dumps(edge.to_dict(), ensure_ascii=False) + "\n")
        
        # Also add to main edges file
        with open(edges_path, "a", encoding="utf-8") as f:
            for edge in all_edges:
                f.write(json.dumps(edge.to_dict(), ensure_ascii=False) + "\n")
        
        # Update manifest metadata
        self._update_manifest(concept_nodes, all_edges)
        
        summary = {
            "concept_nodes": len(concept_nodes),
            "concept_edges": len(concept_edges),
            "join_edges": len(join_edges),
            "total_nodes": len(concept_nodes),
            "total_edges": len(all_edges)
        }
        
        logger.info(f"Persisted ADCIL inferences: {summary}")
        return summary
    
    def _update_manifest(self, nodes: List[Node], edges: List[Edge]):
        """Update manifest.json with ADCIL metadata."""
        import json
        from datetime import datetime
        
        manifest_path = self.output_dir / "manifest.json"
        
        # Load existing manifest or create new
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        else:
            manifest = {
                "graph_schema_version": "0.2.0",
                "build_timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "extractor_count": 0,
                "node_count": 0,
                "edge_count": 0
            }
        
        # Add ADCIL metadata
        manifest["adcil"] = {
            "enabled": True,
            "inference_timestamp": datetime.utcnow().isoformat() + "Z",
            "concept_nodes": len([n for n in nodes if n.type == "BUSINESS_CONCEPT"]),
            "concept_edges": len([e for e in edges if e.type == "DESCRIBES"]),
            "join_edges": len([e for e in edges if e.type == "RELATES_TO" and e.attributes.get("join_type") == "inferred"])
        }
        
        # Update counts
        manifest["node_count"] = manifest.get("node_count", 0) + len(nodes)
        manifest["edge_count"] = manifest.get("edge_count", 0) + len(edges)
        
        # Write updated manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

