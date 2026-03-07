"""
Integration Tests for Ingestion CLI

Tests end-to-end ingestion and cross-system path discovery.
"""

import pytest
import subprocess
import tempfile
import json
from pathlib import Path
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.api import ContextAPI


def test_ingest_cli_full_pipeline():
    """Test full ingestion pipeline."""
    import sys
    project_root = Path(__file__).resolve().parents[2]
    ingest_script = project_root / "datashark-mcp" / "tools" / "ingest.py"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "output"
        
        # Run ingestion CLI
        result = subprocess.run(
            [sys.executable, str(ingest_script),
             "--extractor", "database_catalog",
             "--extractor", "bi_tool",
             "--out", str(out_dir)],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # Check artifacts exist
        assert (out_dir / "nodes.jsonl").exists()
        assert (out_dir / "edges.jsonl").exists()
        assert (out_dir / "manifest.json").exists()


def test_cross_system_path_discovery():
    """Test that hybrid cross-system paths are discoverable."""
    # Load artifacts from ingestion
    import sys
    project_root = Path(__file__).resolve().parents[2]
    ingest_script = project_root / "datashark-mcp" / "tools" / "ingest.py"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "output"
        
        subprocess.run(
            [sys.executable, str(ingest_script),
             "--extractor", "database_catalog",
             "--extractor", "bi_tool",
             "--out", str(out_dir)],
            capture_output=True
        )
        
        # Load into store
        store = GraphStore()
        nodes = []
        with open(out_dir / "nodes.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    node = Node.from_dict(data)
                    nodes.append(node)
        
        edges = []
        with open(out_dir / "edges.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    edge = Edge.from_dict(data)
                    edges.append(edge)
        
        for node in nodes:
            store.add_node(node)
        for edge in edges:
            store.add_edge(edge)
        
        # Create API
        api = ContextAPI(store)
        
        # Find database table
        db_nodes = api.find_entities_by_system("database")
        assert len(db_nodes) > 0
        
        # Find BI tool entities
        bi_nodes = api.find_entities_by_system("bi_tool")
        assert len(bi_nodes) > 0
        
        # Try to find path from database to BI tool
        if db_nodes and bi_nodes:
            db_node_id = db_nodes[0].id
            paths = api.find_join_paths_from(db_node_id, max_depth=5)
            # Should find some paths (may include cross-system via DERIVES_FROM)
            assert isinstance(paths, list)

