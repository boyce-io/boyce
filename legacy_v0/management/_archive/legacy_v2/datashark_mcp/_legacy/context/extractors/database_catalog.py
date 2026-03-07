"""
Database Catalog Extractor

Source-agnostic extractor that reads a generic database catalog JSON
and emits nodes/edges with system="database".
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


class DatabaseCatalogExtractor:
    """Extractor for generic database catalogs."""
    
    def name(self) -> str:
        return "database_catalog"
    
    def run(self, *, out_dir: str, since: str | None = None, input_path: str | None = None) -> None:
        """
        Extract database catalog data.
        
        Args:
            out_dir: Output directory
            since: Optional timestamp for incremental extraction
            input_path: Path to catalog JSON file
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Start manifest
        manifest = Manifest.start_run(
            system="database",
            repo=None,
            changed_since=since,
            schema_version="0.1.0",
            extractor_version="1.0.0"
        )
        
        # Load input data
        if input_path:
            with open(input_path, "r") as f:
                catalog_data = json.load(f)
        else:
            # Default minimal catalog
            catalog_data = {
                "tables": [
                    {
                        "schema": "public",
                        "table": "orders",
                        "columns": ["id", "customer_id", "amount", "created_at"]
                    },
                    {
                        "schema": "public",
                        "table": "customers",
                        "columns": ["id", "name", "email"]
                    }
                ],
                "foreign_keys": [
                    {
                        "from_schema": "public",
                        "from_table": "orders",
                        "from_column": "customer_id",
                        "to_schema": "public",
                        "to_table": "customers",
                        "to_column": "id"
                    }
                ]
            }
        
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_id_map: Dict[str, str] = {}  # (schema, table) -> node_id
        
        # Extract timestamp
        extracted_at = datetime.now(timezone.utc).isoformat()
        
        # Create table nodes
        for table_def in catalog_data.get("tables", []):
            schema = table_def.get("schema", "public")
            table = table_def["table"]
            
            # Create table node
            node_id = compute_node_id("ENTITY", "database", None, schema, f"{schema}.{table}")
            node_id_map[(schema, table)] = node_id
            
            node = Node(
                id=node_id,
                system="database",
                type="ENTITY",
                name=f"{schema}.{table}",
                attributes={
                    "schema": schema,
                    "table": table,
                    "columns": table_def.get("columns", [])
                },
                provenance=Provenance(
                    system="database",
                    source_path=f"database://{schema}.{table}",
                    extractor_version="1.0.0",
                    extracted_at=extracted_at
                ),
                schema=schema
            )
            nodes.append(node.to_dict())
            
            # Create field nodes for columns
            for column in table_def.get("columns", []):
                field_id = compute_node_id("FIELD", "database", None, schema, f"{schema}.{table}.{column}")
                field_node = Node(
                    id=field_id,
                    system="database",
                    type="FIELD",
                    name=f"{schema}.{table}.{column}",
                    attributes={
                        "schema": schema,
                        "table": table,
                        "column": column
                    },
                    provenance=Provenance(
                        system="database",
                        source_path=f"database://{schema}.{table}.{column}",
                        extractor_version="1.0.0",
                        extracted_at=extracted_at
                    ),
                    schema=schema
                )
                nodes.append(field_node.to_dict())
        
        # Create foreign key edges
        for fk in catalog_data.get("foreign_keys", []):
            from_schema = fk["from_schema"]
            from_table = fk["from_table"]
            to_schema = fk["to_schema"]
            to_table = fk["to_table"]
            
            src_id = node_id_map.get((from_schema, from_table))
            dst_id = node_id_map.get((to_schema, to_table))
            
            if src_id and dst_id:
                join_signature = {
                    "join_condition": f"{from_table}.{fk['from_column']} = {to_table}.{fk['to_column']}",
                    "join_type": "inner",
                    "source": "foreign_key"
                }
                edge_id = compute_edge_id("JOINS_TO", src_id, dst_id, join_signature)
                
                edge = Edge(
                    id=edge_id,
                    src=src_id,
                    dst=dst_id,
                    type="JOINS_TO",
                    attributes=join_signature,
                    provenance=Provenance(
                        system="database",
                        source_path=f"database://{from_schema}.{from_table}",
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
                "nodes_sha256": "",  # Will be computed by CLI
                "edges_sha256": ""
            }
        )
        
        # Write manifest
        manifest.write_atomic(out_path / "manifest.json")

