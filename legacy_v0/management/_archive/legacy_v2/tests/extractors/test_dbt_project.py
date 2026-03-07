"""
Test dbt_project Extractor

Verifies deterministic ID generation, schema validation, and normalized output.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datashark_mcp.context.extractors.dbt_project import DBTProjectExtractor
from datashark_mcp.context.models import Node, Edge


@pytest.fixture
def sample_dbt_manifest():
    """Sample dbt manifest.json structure."""
    return {
        "nodes": {
            "model.dbt_project.customers": {
                "resource_type": "model",
                "name": "customers",
                "schema": "public",
                "database": "analytics",
                "unique_id": "model.dbt_project.customers",
                "raw_sql": "SELECT * FROM raw.customers",
                "config": {
                    "materialized": "table"
                },
                "columns": {
                    "customer_id": {
                        "name": "customer_id",
                        "data_type": "integer",
                        "description": "Customer identifier"
                    },
                    "name": {
                        "name": "name",
                        "data_type": "varchar",
                        "description": "Customer name"
                    }
                },
                "fqn": ["dbt_project", "customers"]
            },
            "test.dbt_project.not_null_customers_customer_id": {
                "resource_type": "test",
                "name": "not_null_customers_customer_id",
                "unique_id": "test.dbt_project.not_null_customers_customer_id",
                "test_metadata": {
                    "name": "not_null"
                },
                "depends_on": {
                    "nodes": ["model.dbt_project.customers"]
                }
            }
        },
        "sources": {}
    }


def test_dbt_extractor_deterministic_ids(sample_dbt_manifest):
    """Test that dbt extractor produces deterministic node IDs."""
    extractor = DBTProjectExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write manifest
        manifest_path = Path(tmpdir) / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(sample_dbt_manifest, f)
        
        # Run extractor twice
        out_dir1 = Path(tmpdir) / "output1"
        out_dir2 = Path(tmpdir) / "output2"
        
        extractor.run(out_dir=str(out_dir1), input_path=str(tmpdir))
        extractor.run(out_dir=str(out_dir2), input_path=str(tmpdir))
        
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


def test_dbt_extractor_schema_validation(sample_dbt_manifest):
    """Test that dbt extractor output validates against schema."""
    extractor = DBTProjectExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(sample_dbt_manifest, f)
        
        out_dir = Path(tmpdir) / "output"
        extractor.run(out_dir=str(out_dir), input_path=str(tmpdir))
        
        # Load and validate nodes
        with open(out_dir / "nodes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    node = Node.from_dict(data)
                    node.validate()  # Should not raise


def test_dbt_extractor_normalized_output(sample_dbt_manifest):
    """Test that dbt extractor produces normalized output."""
    extractor = DBTProjectExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(sample_dbt_manifest, f)
        
        out_dir = Path(tmpdir) / "output"
        extractor.run(out_dir=str(out_dir), input_path=str(tmpdir))
        
        # Check artifacts exist
        assert (out_dir / "nodes.jsonl").exists()
        assert (out_dir / "edges.jsonl").exists()
        assert (out_dir / "manifest.json").exists()
        
        # Load manifest
        with open(out_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        assert manifest["system"] == "dbt"
        assert manifest["status"] == "success"

