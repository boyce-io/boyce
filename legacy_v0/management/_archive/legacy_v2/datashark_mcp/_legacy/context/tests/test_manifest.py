"""
Tests for manifest.py

Tests Manifest lifecycle and atomic writes.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from datashark_mcp.context.manifest import Manifest, ManifestValidationError


def test_manifest_start_run():
    """Test starting a new run."""
    manifest = Manifest.start_run("database", repo="test_repo")
    
    assert manifest.system == "database"
    assert manifest.repo == "test_repo"
    assert manifest.start_time != ""
    assert manifest.status == "success"
    assert manifest.run_id != ""


def test_manifest_end_run():
    """Test ending a run."""
    manifest = Manifest.start_run("database")
    
    manifest.end_run(
        status="success",
        counts={"nodes": 10, "edges": 20, "tombstones": 0},
        hash_summaries={"nodes_sha256": "abc123", "edges_sha256": "def456"}
    )
    
    assert manifest.end_time != ""
    assert manifest.counts["nodes"] == 10
    assert manifest.hash_summaries["nodes_sha256"] == "abc123"


def test_manifest_to_json():
    """Test manifest serialization."""
    manifest = Manifest.start_run("database")
    manifest.end_run(
        status="success",
        counts={"nodes": 5, "edges": 10, "tombstones": 0},
        hash_summaries={"nodes_sha256": "abc", "edges_sha256": "def"}
    )
    
    json_data = manifest.to_json()
    
    assert "run_id" in json_data
    assert "system" in json_data
    assert "counts" in json_data
    assert "hash_summaries" in json_data


def test_manifest_from_json():
    """Test manifest deserialization."""
    manifest = Manifest.start_run("database")
    manifest.end_run(
        status="success",
        counts={"nodes": 5, "edges": 10, "tombstones": 0},
        hash_summaries={"nodes_sha256": "abc", "edges_sha256": "def"}
    )
    
    json_data = manifest.to_json()
    manifest2 = Manifest.from_json(json_data)
    
    assert manifest2.run_id == manifest.run_id
    assert manifest2.system == manifest.system
    assert manifest2.counts == manifest.counts


def test_manifest_validation():
    """Test manifest validation."""
    manifest = Manifest.start_run("database")
    manifest.end_run(
        status="success",
        counts={"nodes": 5, "edges": 10, "tombstones": 0},
        hash_summaries={"nodes_sha256": "abc", "edges_sha256": "def"}
    )
    
    # Should not raise
    manifest.validate()


def test_manifest_atomic_write():
    """Test atomic write (temp → rename)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        
        manifest = Manifest.start_run("database")
        manifest.end_run(
            status="success",
            counts={"nodes": 5, "edges": 10, "tombstones": 0},
            hash_summaries={"nodes_sha256": "abc", "edges_sha256": "def"}
        )
        
        manifest.write_atomic(manifest_path)
        
        assert manifest_path.exists()
        
        # Verify contents
        import json
        with open(manifest_path, "r") as f:
            data = json.load(f)
            assert data["system"] == "database"

