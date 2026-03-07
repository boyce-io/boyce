"""
Tests for BI Tool Extractor
"""

import pytest
import tempfile
import json
from pathlib import Path
from datashark_mcp.context.extractors.bi_tool import BIToolExtractor
from datashark_mcp.context.models import Node, Edge


def test_extractor_emits_valid_artifacts():
    """Test that extractor emits valid artifacts."""
    extractor = BIToolExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        extractor.run(out_dir=tmpdir)
        
        tmp_path = Path(tmpdir)
        
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
        
        # Check system
        assert all(n.system == "bi_tool" for n in nodes)


def test_no_business_concept_nodes():
    """Test that extractor does not emit BUSINESS_CONCEPT nodes."""
    extractor = BIToolExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        extractor.run(out_dir=tmpdir)
        
        tmp_path = Path(tmpdir)
        
        with open(tmp_path / "nodes.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    assert data["type"] != "BUSINESS_CONCEPT"


def test_cross_system_edges():
    """Test that extractor creates DERIVES_FROM edges to database."""
    extractor = BIToolExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        extractor.run(out_dir=tmpdir)
        
        tmp_path = Path(tmpdir)
        
        edges = []
        with open(tmp_path / "edges.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    edge = Edge.from_dict(data)
                    edges.append(edge)
        
        # Should have DERIVES_FROM edges
        derives_from = [e for e in edges if e.type == "DERIVES_FROM"]
        assert len(derives_from) > 0, "Should create DERIVES_FROM edges to database"

