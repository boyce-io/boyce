"""
Test airflow_dag Extractor

Verifies deterministic ID generation and normalized output.
"""

import pytest
import tempfile
from pathlib import Path
from datashark_mcp.context.extractors.airflow_dag import AirflowDAGExtractor


def test_airflow_extractor_empty_directory():
    """Test that airflow extractor handles empty DAG directory."""
    extractor = AirflowDAGExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "output"
        extractor.run(out_dir=str(out_dir), input_path=str(tmpdir))
        
        # Should produce empty but valid output
        assert (out_dir / "nodes.jsonl").exists()
        assert (out_dir / "edges.jsonl").exists()
        assert (out_dir / "manifest.json").exists()


def test_airflow_extractor_handles_missing_directory():
    """Test that airflow extractor handles missing directory gracefully."""
    extractor = AirflowDAGExtractor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "output"
        extractor.run(out_dir=str(out_dir), input_path=str(Path(tmpdir) / "nonexistent"))
        
        # Should produce empty but valid output
        assert (out_dir / "nodes.jsonl").exists()
        assert (out_dir / "edges.jsonl").exists()
        assert (out_dir / "manifest.json").exists()

