"""
DataHub Catalog Extractor

Consumes DataHub metadata JSONs and normalizes to schema.
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


class DataHubCatalogExtractor:
    """Extractor for DataHub metadata catalogs."""
    
    def name(self) -> str:
        return "datahub_catalog"
    
    def run(self, *, out_dir: str, since: str | None = None, input_path: str | None = None) -> None:
        """
        Extract DataHub catalog data.
        
        Args:
            out_dir: Output directory
            since: Optional timestamp for incremental extraction
            input_path: Path to DataHub metadata JSON file or directory
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Start manifest
        manifest = Manifest.start_run(
            system="datahub",
            repo=None,
            changed_since=since,
            schema_version="0.2.0",
            extractor_version="1.0.0"
        )
        
        # Find DataHub metadata files
        if input_path:
            input_path_obj = Path(input_path).expanduser()
        else:
            input_path_obj = Path("datahub_metadata.json")
        
        if not input_path_obj.exists():
            self._write_empty_output(out_path, manifest)
            return
        
        # Load metadata
        metadata_files = []
        if input_path_obj.is_file():
            metadata_files = [input_path_obj]
        elif input_path_obj.is_dir():
            metadata_files = list(input_path_obj.glob("*.json"))
        
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_id_map: Dict[str, str] = {}
        
        extracted_at = datetime.now(timezone.utc).isoformat()
        
        for metadata_file in metadata_files:
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    datahub_data = json.load(f)
                
                # Extract entities (DataHub uses "entities" key)
                entities = datahub_data.get("entities", [])
                if not entities and isinstance(datahub_data, list):
                    entities = datahub_data
                
                for entity in entities:
                    entity_type = entity.get("type", "")
                    entity_urn = entity.get("urn", "")
                    
                    if entity_type == "dataset":
                        # Create ENTITY node for dataset
                        dataset_name = self._extract_dataset_name(entity)
                        schema = self._extract_schema(entity)
                        
                        node_id = compute_node_id("ENTITY", "datahub", None, schema, dataset_name)
                        node_id_map[entity_urn] = node_id
                        
                        node = Node(
                            id=node_id,
                            system="datahub",
                            type="ENTITY",
                            name=dataset_name,
                            attributes={
                                "urn": entity_urn,
                                "schema": schema,
                                "datahub_type": entity_type,
                                "description": entity.get("description", ""),
                                "properties": entity.get("properties", {})
                            },
                            provenance=Provenance(
                                system="datahub",
                                source_path=str(metadata_file),
                                extractor_version="1.0.0",
                                extracted_at=extracted_at
                            ),
                            schema=schema
                        )
                        nodes.append(node.to_dict())
                        
                        # Extract schema fields (columns)
                        schema_metadata = entity.get("schemaMetadata", {})
                        fields = schema_metadata.get("fields", [])
                        
                        for field in fields:
                            field_name = field.get("fieldPath", "")
                            field_type = field.get("type", {}).get("type", "unknown")
                            
                            field_node_id = compute_node_id(
                                "FIELD", "datahub", None, schema, f"{dataset_name}.{field_name}"
                            )
                            
                            field_node = Node(
                                id=field_node_id,
                                system="datahub",
                                type="FIELD",
                                name=field_name,
                                attributes={
                                    "type": field_type,
                                    "table": dataset_name,
                                    "description": field.get("description", ""),
                                    "datahub_urn": entity_urn
                                },
                                provenance=Provenance(
                                    system="datahub",
                                    source_path=str(metadata_file),
                                    extractor_version="1.0.0",
                                    extracted_at=extracted_at
                                ),
                                schema=schema
                            )
                            nodes.append(field_node.to_dict())
                            
                            # Create CONTAINS edge
                            edge_id = compute_edge_id(node_id, field_node_id, "CONTAINS")
                            edge = Edge(
                                id=edge_id,
                                source=node_id,
                                target=field_node_id,
                                type="CONTAINS",
                                attributes={},
                                provenance=Provenance(
                                    system="datahub",
                                    source_path=str(metadata_file),
                                    extractor_version="1.0.0",
                                    extracted_at=extracted_at
                                )
                            )
                            edges.append(edge.to_dict())
                    
                    elif entity_type == "dataJob" or entity_type == "dataFlow":
                        # Create TRANSFORMATION node for jobs/flows
                        job_name = entity.get("name", entity_urn)
                        
                        job_node_id = compute_node_id("TRANSFORMATION", "datahub", None, None, entity_urn)
                        
                        node = Node(
                            id=job_node_id,
                            system="datahub",
                            type="TRANSFORMATION",
                            name=job_name,
                            attributes={
                                "urn": entity_urn,
                                "datahub_type": entity_type,
                                "description": entity.get("description", "")
                            },
                            provenance=Provenance(
                                system="datahub",
                                source_path=str(metadata_file),
                                extractor_version="1.0.0",
                                extracted_at=extracted_at
                            )
                        )
                        nodes.append(node.to_dict())
                        
                        # Extract dependencies (incoming/outgoing)
                        inputs = entity.get("inputOutputs", {}).get("inputDatasets", [])
                        outputs = entity.get("inputOutputs", {}).get("outputDatasets", [])
                        
                        for input_urn in inputs:
                            if input_urn in node_id_map:
                                edge_id = compute_edge_id(job_node_id, node_id_map[input_urn], "DERIVES_FROM")
                                edge = Edge(
                                    id=edge_id,
                                    source=job_node_id,
                                    target=node_id_map[input_urn],
                                    type="DERIVES_FROM",
                                    attributes={},
                                    provenance=Provenance(
                                        system="datahub",
                                        source_path=str(metadata_file),
                                        extractor_version="1.0.0",
                                        extracted_at=extracted_at
                                    )
                                )
                                edges.append(edge.to_dict())
                        
                        for output_urn in outputs:
                            if output_urn in node_id_map:
                                edge_id = compute_edge_id(node_id_map[output_urn], job_node_id, "DERIVES_FROM")
                                edge = Edge(
                                    id=edge_id,
                                    source=node_id_map[output_urn],
                                    target=job_node_id,
                                    type="DERIVES_FROM",
                                    attributes={},
                                    provenance=Provenance(
                                        system="datahub",
                                        source_path=str(metadata_file),
                                        extractor_version="1.0.0",
                                        extracted_at=extracted_at
                                    )
                                )
                                edges.append(edge.to_dict())
            except Exception as e:
                # Continue on parse errors
                continue
        
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
    
    def _extract_dataset_name(self, entity: Dict[str, Any]) -> str:
        """Extract dataset name from DataHub entity."""
        # Try various fields
        name = entity.get("name", "")
        if name:
            return name
        
        urn = entity.get("urn", "")
        if urn:
            # Parse URN format: urn:li:dataset:(urn:li:dataPlatform:...,name,PROD)
            parts = urn.split(",")
            if len(parts) >= 2:
                return parts[-2]
        
        return "unknown"
    
    def _extract_schema(self, entity: Dict[str, Any]) -> str:
        """Extract schema from DataHub entity."""
        properties = entity.get("properties", {})
        schema = properties.get("schema", "")
        if schema:
            return schema
        
        # Try to extract from URN
        urn = entity.get("urn", "")
        if urn:
            parts = urn.split(",")
            if len(parts) >= 3:
                return parts[-3]
        
        return "default"
    
    def _write_empty_output(self, out_path: Path, manifest: Manifest):
        """Write empty output when no metadata found."""
        manifest.finish_run(
            node_count=0,
            edge_count=0,
            status="success"
        )
        
        write_jsonl(out_path / "nodes.jsonl", [])
        write_jsonl(out_path / "edges.jsonl", [])
        manifest.write(out_path / "manifest.json")

