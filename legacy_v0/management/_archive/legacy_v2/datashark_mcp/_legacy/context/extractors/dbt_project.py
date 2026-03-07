"""
dbt Project Extractor

Parses dbt manifest.json and maps models/tests to ENTITY nodes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from datashark_mcp.context.extractors.base import Extractor, write_jsonl
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.id_utils import compute_node_id, compute_edge_id
from datashark_mcp.context.manifest import Manifest


class DBTProjectExtractor:
    """Extractor for dbt project manifests."""
    
    def name(self) -> str:
        return "dbt_project"
    
    def run(self, *, out_dir: str, since: str | None = None, input_path: str | None = None) -> None:
        """
        Extract dbt project data from manifest.json.
        
        Args:
            out_dir: Output directory
            since: Optional timestamp for incremental extraction
            input_path: Path to dbt project root (searches for manifest.json)
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Start manifest
        manifest = Manifest.start_run(
            system="dbt",
            repo=None,
            changed_since=since,
            schema_version="0.2.0",
            extractor_version="1.0.0"
        )
        
        # Find manifest.json
        if input_path:
            project_root = Path(input_path).expanduser()
            manifest_path = project_root / "target" / "manifest.json"
            if not manifest_path.exists():
                manifest_path = project_root / "manifest.json"
        else:
            # Default: use current directory
            manifest_path = Path("manifest.json")
        
        if not manifest_path.exists():
            # Create minimal default output
            self._write_empty_output(out_path, manifest)
            return
        
        # Load manifest
        with open(manifest_path, "r", encoding="utf-8") as f:
            dbt_manifest = json.load(f)
        
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_id_map: Dict[str, str] = {}
        
        extracted_at = datetime.now(timezone.utc).isoformat()
        
        # Extract models
        models = dbt_manifest.get("nodes", {})
        for node_key, model_data in models.items():
            resource_type = model_data.get("resource_type")
            
            if resource_type == "model":
                # Create ENTITY node for model
                model_name = model_data.get("name", "")
                schema = model_data.get("schema", "public")
                database = model_data.get("database", "")
                unique_id = model_data.get("unique_id", node_key)
                
                node_id = compute_node_id("ENTITY", "dbt", None, schema, f"{schema}.{model_name}")
                node_id_map[unique_id] = node_id
                
                node = Node(
                    id=node_id,
                    system="dbt",
                    type="ENTITY",
                    name=model_name,
                    attributes={
                        "schema": schema,
                        "database": database,
                        "dbt_unique_id": unique_id,
                        "materialized": model_data.get("config", {}).get("materialized", "view"),
                        "sql": model_data.get("raw_sql", ""),
                        "columns": model_data.get("columns", {})
                    },
                    provenance=Provenance(
                        system="dbt",
                        source_path=str(manifest_path),
                        extractor_version="1.0.0",
                        extracted_at=extracted_at,
                        source_commit=model_data.get("fqn", [])[-1] if model_data.get("fqn") else None
                    ),
                    schema=schema
                )
                nodes.append(node.to_dict())
                
                # Extract columns as FIELD nodes
                columns = model_data.get("columns", {})
                for col_name, col_data in columns.items():
                    col_node_id = compute_node_id(
                        "FIELD", "dbt", None, schema, f"{schema}.{model_name}.{col_name}"
                    )
                    
                    col_node = Node(
                        id=col_node_id,
                        system="dbt",
                        type="FIELD",
                        name=col_name,
                        attributes={
                            "type": col_data.get("data_type", "unknown"),
                            "table": model_name,
                            "description": col_data.get("description", ""),
                            "dbt_unique_id": unique_id
                        },
                        provenance=Provenance(
                            system="dbt",
                            source_path=str(manifest_path),
                            extractor_version="1.0.0",
                            extracted_at=extracted_at
                        ),
                        schema=schema
                    )
                    nodes.append(col_node.to_dict())
                    
                    # Create CONTAINS edge
                    edge_id = compute_edge_id(
                        node_id, col_node_id, "CONTAINS"
                    )
                    edge = Edge(
                        id=edge_id,
                        source=node_id,
                        target=col_node_id,
                        type="CONTAINS",
                        attributes={},
                        provenance=Provenance(
                            system="dbt",
                            source_path=str(manifest_path),
                            extractor_version="1.0.0",
                            extracted_at=extracted_at
                        )
                    )
                    edges.append(edge.to_dict())
            
            elif resource_type == "test":
                # Create TRANSFORMATION node for test
                test_name = model_data.get("name", "")
                test_unique_id = model_data.get("unique_id", node_key)
                
                test_node_id = compute_node_id("TRANSFORMATION", "dbt", None, None, test_unique_id)
                
                node = Node(
                    id=test_node_id,
                    system="dbt",
                    type="TRANSFORMATION",
                    name=test_name,
                    attributes={
                        "test_type": model_data.get("test_metadata", {}).get("name", ""),
                        "dbt_unique_id": test_unique_id,
                        "depends_on": model_data.get("depends_on", {}).get("nodes", [])
                    },
                    provenance=Provenance(
                        system="dbt",
                        source_path=str(manifest_path),
                        extractor_version="1.0.0",
                        extracted_at=extracted_at
                    )
                )
                nodes.append(node.to_dict())
                
                # Create DERIVES_FROM edges to models
                depends_on = model_data.get("depends_on", {}).get("nodes", [])
                for dep_id in depends_on:
                    if dep_id in node_id_map:
                        edge_id = compute_edge_id(
                            test_node_id, node_id_map[dep_id], "DERIVES_FROM"
                        )
                        edge = Edge(
                            id=edge_id,
                            source=test_node_id,
                            target=node_id_map[dep_id],
                            type="DERIVES_FROM",
                            attributes={},
                            provenance=Provenance(
                                system="dbt",
                                source_path=str(manifest_path),
                                extractor_version="1.0.0",
                                extracted_at=extracted_at
                            )
                        )
                        edges.append(edge.to_dict())
        
        # Extract sources
        sources = dbt_manifest.get("sources", {})
        for source_key, source_data in sources.items():
            source_name = source_data.get("source_name", "")
            table_name = source_data.get("name", "")
            schema = source_data.get("schema", "public")
            
            source_node_id = compute_node_id("ENTITY", "dbt", None, schema, f"{schema}.{table_name}")
            
            node = Node(
                id=source_node_id,
                system="dbt",
                type="ENTITY",
                name=f"{source_name}.{table_name}",
                attributes={
                    "schema": schema,
                    "source_name": source_name,
                    "dbt_source": True
                },
                provenance=Provenance(
                    system="dbt",
                    source_path=str(manifest_path),
                    extractor_version="1.0.0",
                    extracted_at=extracted_at
                ),
                schema=schema
            )
            nodes.append(node.to_dict())
        
        # Finalize manifest
        manifest.finish_run(
            node_count=len(nodes),
            edge_count=len(edges),
            status="success"
        )
        
        # Write artifacts
        write_jsonl(out_path / "nodes.jsonl", nodes)
        write_jsonl(out_path / "edges.jsonl", edges)
        manifest.write(out_path / "manifest.json")
    
    def _write_empty_output(self, out_path: Path, manifest: Manifest):
        """Write empty output when manifest.json not found."""
        manifest.finish_run(
            node_count=0,
            edge_count=0,
            status="success"
        )
        
        write_jsonl(out_path / "nodes.jsonl", [])
        write_jsonl(out_path / "edges.jsonl", [])
        manifest.write(out_path / "manifest.json")

