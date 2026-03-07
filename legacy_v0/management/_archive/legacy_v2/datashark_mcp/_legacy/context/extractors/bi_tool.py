"""
BI Tool Extractor

Source-agnostic extractor that reads a generic BI tool definition JSON
and emits nodes/edges with system="bi_tool".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
from datashark_mcp.context.extractors.base import Extractor, write_jsonl
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.id_utils import compute_node_id, compute_edge_id
from datashark_mcp.context.manifest import Manifest


class BIToolExtractor:
    """Extractor for generic BI tool definitions."""
    
    def name(self) -> str:
        return "bi_tool"
    
    def run(self, *, out_dir: str, since: str | None = None, input_path: str | None = None) -> None:
        """
        Extract BI tool data.
        
        Args:
            out_dir: Output directory
            since: Optional timestamp for incremental extraction
            input_path: Path to BI definition JSON file
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Start manifest
        manifest = Manifest.start_run(
            system="bi_tool",
            repo="bi_tool_prod",
            changed_since=since,
            schema_version="0.1.0",
            extractor_version="1.0.0"
        )
        
        # Load input data
        if input_path:
            with open(input_path, "r") as f:
                bi_data = json.load(f)
        else:
            # Default minimal BI definition
            bi_data = {
                "entities": [
                    {
                        "name": "orders_explore",
                        "sql_table_name": "public.orders",
                        "type": "explore"
                    }
                ],
                "metrics": [
                    {
                        "name": "total_revenue",
                        "entity": "orders_explore",
                        "type": "sum",
                        "expression": "SUM(orders.amount)"
                    }
                ]
            }
        
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        entity_id_map: Dict[str, str] = {}  # entity name -> node_id
        
        extracted_at = datetime.now(timezone.utc).isoformat()
        
        # Create entity nodes
        for entity_def in bi_data.get("entities", []):
            entity_name = entity_def["name"]
            entity_id = compute_node_id("ENTITY", "bi_tool", "bi_tool_prod", None, entity_name)
            entity_id_map[entity_name] = entity_id
            
            node = Node(
                id=entity_id,
                system="bi_tool",
                type="ENTITY",
                name=entity_name,
                attributes={
                    "repo": "bi_tool_prod",
                    "entity_type": entity_def.get("type", "explore"),
                    "sql_table_name": entity_def.get("sql_table_name")
                },
                provenance=Provenance(
                    system="bi_tool",
                    source_path=f"bi_tool://entities/{entity_name}",
                    extractor_version="1.0.0",
                    extracted_at=extracted_at
                ),
                repo="bi_tool_prod"
            )
            nodes.append(node.to_dict())
            
            # Create DERIVES_FROM edge if sql_table_name exists
            if entity_def.get("sql_table_name"):
                # Map to database table (assume database schema)
                db_table = entity_def["sql_table_name"]
                db_node_id = compute_node_id("ENTITY", "database", None, None, db_table)
                join_signature = {"source": "sql_table_name"}
                edge_id = compute_edge_id("DERIVES_FROM", entity_id, db_node_id, join_signature)
                
                edge = Edge(
                    id=edge_id,
                    src=entity_id,
                    dst=db_node_id,
                    type="DERIVES_FROM",
                    attributes=join_signature,
                    provenance=Provenance(
                        system="bi_tool",
                        source_path=f"bi_tool://entities/{entity_name}",
                        extractor_version="1.0.0",
                        extracted_at=extracted_at
                    )
                )
                edges.append(edge.to_dict())
        
        # Create metric nodes
        for metric_def in bi_data.get("metrics", []):
            metric_name = metric_def["name"]
            metric_id = compute_node_id("METRIC", "bi_tool", "bi_tool_prod", None, metric_name)
            
            node = Node(
                id=metric_id,
                system="bi_tool",
                type="METRIC",
                name=metric_name,
                attributes={
                    "repo": "bi_tool_prod",
                    "metric_type": metric_def.get("type", "sum"),
                    "expression": metric_def.get("expression")
                },
                provenance=Provenance(
                    system="bi_tool",
                    source_path=f"bi_tool://metrics/{metric_name}",
                    extractor_version="1.0.0",
                    extracted_at=extracted_at
                ),
                repo="bi_tool_prod"
            )
            nodes.append(node.to_dict())
            
            # Create DEPENDS_ON edge to entity
            entity_name = metric_def.get("entity")
            if entity_name and entity_name in entity_id_map:
                entity_id = entity_id_map[entity_name]
                edge_id = compute_edge_id("DEPENDS_ON", metric_id, entity_id)
                
                edge = Edge(
                    id=edge_id,
                    src=metric_id,
                    dst=entity_id,
                    type="DEPENDS_ON",
                    attributes={"source": "metric_definition"},
                    provenance=Provenance(
                        system="bi_tool",
                        source_path=f"bi_tool://metrics/{metric_name}",
                        extractor_version="1.0.0",
                        extracted_at=extracted_at
                    )
                )
                edges.append(edge.to_dict())
        
        # Write artifacts
        write_jsonl(out_path / "nodes.jsonl", nodes)
        write_jsonl(out_path / "edges.jsonl", edges)
        
        # Finalize manifest
        manifest.end_run(
            status="success",
            counts={
                "nodes": len(nodes),
                "edges": len(edges),
                "tombstones": 0
            },
            hash_summaries={
                "nodes_sha256": "",
                "edges_sha256": ""
            }
        )
        
        # Write manifest
        manifest.write_atomic(out_path / "manifest.json")

