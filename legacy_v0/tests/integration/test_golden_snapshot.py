"""
Golden Snapshot Tests

Tests that repeated runs produce byte-identical outputs.
"""

import pytest
import subprocess
import tempfile
import hashlib
from pathlib import Path


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA256 of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        sha256.update(f.read())
    return sha256.hexdigest()


def test_golden_snapshot_determinism():
    """Test that repeated runs produce identical outputs."""
    import sys
    project_root = Path(__file__).resolve().parents[2]
    ingest_script = project_root / "datashark-mcp" / "tools" / "ingest.py"
    
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            out_dir1 = Path(tmpdir1) / "output"
            out_dir2 = Path(tmpdir2) / "output"
            
            # Run ingestion twice
            for out_dir in [out_dir1, out_dir2]:
                subprocess.run(
                    [sys.executable, str(ingest_script),
                     "--extractor", "database_catalog",
                     "--extractor", "bi_tool",
                     "--out", str(out_dir)],
                    capture_output=True
                )
            
            # Compare SHA256 hashes
            nodes_hash1 = compute_file_sha256(out_dir1 / "nodes.jsonl")
            nodes_hash2 = compute_file_sha256(out_dir2 / "nodes.jsonl")
            
            edges_hash1 = compute_file_sha256(out_dir1 / "edges.jsonl")
            edges_hash2 = compute_file_sha256(out_dir2 / "edges.jsonl")
            
            assert nodes_hash1 == nodes_hash2, "Nodes.jsonl must be identical across runs"
            assert edges_hash1 == edges_hash2, "Edges.jsonl must be identical across runs"
            
            # Compare manifest hashes
            import json
            with open(out_dir1 / "manifest.json", "r") as f:
                manifest1 = json.load(f)
            with open(out_dir2 / "manifest.json", "r") as f:
                manifest2 = json.load(f)
            
            assert manifest1["hash_summaries"]["nodes_sha256"] == manifest2["hash_summaries"]["nodes_sha256"]
            assert manifest1["hash_summaries"]["edges_sha256"] == manifest2["hash_summaries"]["edges_sha256"]

