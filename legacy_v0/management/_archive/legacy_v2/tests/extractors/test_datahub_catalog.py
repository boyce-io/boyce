"""
Test datahub_catalog Extractor

Verifies deterministic ID generation and normalized output.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datashark_mcp.context.extractors.datahub_catalog import DataHubCatalogExtractor
from datashark_mcp.context.models import Node


@pytest.fixture
def sample_datahub_metadata():
    """Sample DataHub metadata structure."""
    return {
        "entities": [
            {
                "type": "dataset",
                "urn": "urn:li:dataset:(urn:li:dataPlatform:redshift,public.orders,PROD)",
                "name": "orders",
                "description": "Orders table",
                "properties": {
                    "schema": "public"
                },
                "schemaMetadata": {
                    "fields": [
                        {
                            "fieldPath": "order_id",
                            "type": {
                                "type": "integer"
                            },
                            "description": "Order identifier"
                        },
                        {
                            "fieldPath": "customer_id",
                            "type": {
                                "type": "integer"
                            }
                        }
                    ]
                }
            }
        ]
    }


def test_datahub_extractor_deterministic_ids(sample_datahub_metadata):
    """Test that datahub extractor produces deterministic node IDs."""
    extractor = DataHubCatalogExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write metadata
        metadata_path = Path(tmpdir) / "datahub_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(sample_datahub_metadata, f)
        
        # Run extractor twice
        out_dir1 = Path(tmpdir) / "output1"
        out_dir2 = Path(tmpdir) / "output2"
        
        extractor.run(out_dir=str(out_dir1), input_path=str(metadata_path))
        extractor.run(out_dir=str(out_dir2), input_path=str(metadata_path))
        
        # Load nodes
        nodes1 = []
        nodes2 = []
        
        with open(out_dir1 / "nodes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    nodes1.append(json.loads(line))
        
        with open(out_dir2 / "nodes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    nodes2.append(json.loads(line))
        
        # Should produce identical IDs
        ids1 = {n["id"] for n in nodes1}
        ids2 = {n["id"] for n in nodes2}
        
        assert ids1 == ids2, "Node IDs should be deterministic"


def test_datahub_extractor_schema_validation(sample_datahub_metadata):
    """Test that datahub extractor output validates against schema."""
    extractor = DataHubCatalogExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_path = Path(tmpdir) / "datahub_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(sample_datahub_metadata, f)
        
        out_dir = Path(tmpdir) / "output"
        extractor.run(out_dir=str(out_dir), input_path=str(metadata_path))
        
        # Load and validate nodes
        with open(out_dir / "nodes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    node = Node.from_dict(data)
                    node.validate()  # Should not raise

