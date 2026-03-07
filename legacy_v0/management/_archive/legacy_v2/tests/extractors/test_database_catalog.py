"""
Tests for Database Catalog Extractor
"""

import pytest
import tempfile
import json
from pathlib import Path
from datashark_mcp.context.extractors.database_catalog import DatabaseCatalogExtractor
from datashark_mcp.context.models import Node, Edge


def test_extractor_emits_valid_artifacts():
    """Test that extractor emits valid nodes.jsonl, edges.jsonl, manifest.json."""
    extractor = DatabaseCatalogExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        extractor.run(out_dir=tmpdir)
        
        tmp_path = Path(tmpdir)
        
        # Check files exist
        assert (tmp_path / "nodes.jsonl").exists()
        assert (tmp_path / "edges.jsonl").exists()
        assert (tmp_path / "manifest.json").exists()
        
        # Validate nodes
        nodes = []
        with open(tmp_path / "nodes.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    node = Node.from_dict(data)
                    node.validate()
                    nodes.append(node)
        
        assert len(nodes) > 0
        
        # Validate edges
        edges = []
        with open(tmp_path / "edges.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    edge = Edge.from_dict(data)
                    edge.validate()
                    edges.append(edge)
        
        # Validate manifest
        with open(tmp_path / "manifest.json", "r") as f:
            manifest = json.load(f)
            assert "run_id" in manifest
            assert "system" in manifest
            assert manifest["system"] == "database"


def test_no_business_concept_nodes():
    """Test that extractor does not emit BUSINESS_CONCEPT nodes."""
    extractor = DatabaseCatalogExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        extractor.run(out_dir=tmpdir)
        
        tmp_path = Path(tmpdir)
        
        with open(tmp_path / "nodes.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    assert data["type"] != "BUSINESS_CONCEPT", "Extractor must not emit BUSINESS_CONCEPT nodes"


def test_stable_ids():
    """Test that same input produces same IDs."""
    extractor = DatabaseCatalogExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir1:
        extractor.run(out_dir=tmpdir1)
        
        with tempfile.TemporaryDirectory() as tmpdir2:
            extractor.run(out_dir=tmpdir2)
            
            # Load IDs from both runs
            ids1 = []
            with open(Path(tmpdir1) / "nodes.jsonl", "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        ids1.append(data["id"])
            
            ids2 = []
            with open(Path(tmpdir2) / "nodes.jsonl", "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        ids2.append(data["id"])
            
            # IDs should be identical
            assert sorted(ids1) == sorted(ids2), "IDs must be deterministic"

