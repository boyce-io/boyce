"""
Unit tests for AuditWriter and AuditRecord.

Tests that audit records are correctly written to JSONL files.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from datashark.core.audit import AuditRecord, AuditWriter, get_audit_writer, log_artifact


def test_audit_record_schema():
    """Test that AuditRecord has correct schema with required fields."""
    record = AuditRecord(
        snapshot_id="abc123",
        input_query="test query",
        generated_sql="SELECT * FROM test"
    )
    
    assert record.version == "1.0"
    assert record.snapshot_id == "abc123"
    assert record.input_query == "test query"
    assert record.generated_sql == "SELECT * FROM test"
    assert record.request_id  # Should be auto-generated UUID
    assert record.timestamp  # Should be auto-generated ISO timestamp
    assert isinstance(record.metadata, dict)
    
    # Test JSON serialization
    record_dict = record.to_dict()
    assert "version" in record_dict
    assert "timestamp" in record_dict
    assert "request_id" in record_dict
    assert "snapshot_id" in record_dict
    assert "input_query" in record_dict
    assert "generated_sql" in record_dict
    assert "metadata" in record_dict
    
    # Test JSON string
    json_str = record.to_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["version"] == "1.0"
    assert parsed["snapshot_id"] == "abc123"


def test_audit_writer_writes_record():
    """Test that AuditWriter writes a record to JSONL file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        writer = AuditWriter(audit_dir=audit_dir)
        
        record = AuditRecord(
            snapshot_id="test_snapshot_123",
            input_query="Show me total sales",
            generated_sql="SELECT SUM(sales) FROM orders"
        )
        
        file_path = writer.write_record(record)
        
        assert file_path is not None
        assert file_path.exists()
        assert file_path.suffix == ".jsonl"
        
        # Read and verify JSONL content
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 1
            
            parsed = json.loads(lines[0])
            assert parsed["version"] == "1.0"
            assert parsed["snapshot_id"] == "test_snapshot_123"
            assert parsed["input_query"] == "Show me total sales"
            assert parsed["generated_sql"] == "SELECT SUM(sales) FROM orders"
            assert "request_id" in parsed
            assert "timestamp" in parsed


def test_audit_writer_creates_directory():
    """Test that AuditWriter creates audit directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "new" / "audit" / "nested"
        
        assert not audit_dir.exists()
        
        writer = AuditWriter(audit_dir=audit_dir)
        
        assert audit_dir.exists()
        assert audit_dir.is_dir()


def test_audit_writer_jsonl_format():
    """Test that AuditWriter writes one record per file (single-line JSONL format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        writer = AuditWriter(audit_dir=audit_dir)
        
        # Write multiple records (each should create a separate file)
        written_files = []
        for i in range(3):
            record = AuditRecord(
                snapshot_id=f"snapshot_{i}",
                input_query=f"query {i}",
                generated_sql=f"SELECT {i}"
            )
            file_path = writer.write_record(record)
            assert file_path is not None
            written_files.append(file_path)
        
        # Verify we got 3 separate files (one per record)
        jsonl_files = list(audit_dir.glob("*.jsonl"))
        assert len(jsonl_files) == 3, f"Expected 3 files, got {len(jsonl_files)}"
        
        # Verify each file has exactly 1 line with valid JSON
        required_keys = ["version", "timestamp", "request_id", "snapshot_id", "input_query", "generated_sql", "metadata"]
        for file_path in jsonl_files:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                assert len(lines) == 1, f"Each file should have exactly 1 line, got {len(lines)} in {file_path.name}"
                
                # Each line should be valid JSON with required keys
                parsed = json.loads(lines[0])
                for key in required_keys:
                    assert key in parsed, f"Required key '{key}' missing from {file_path.name}"


def test_log_artifact_convenience_function():
    """Test that log_artifact convenience function works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        
        with patch("datashark.core.audit.get_audit_writer") as mock_get_writer:
            mock_writer = AuditWriter(audit_dir=audit_dir)
            mock_get_writer.return_value = mock_writer
            
            file_path = log_artifact(
                input_query="test query",
                snapshot_id="snapshot_123",
                generated_sql="SELECT * FROM test"
            )
            
            assert file_path is not None
            assert file_path.exists()


def test_audit_writer_fail_open():
    """Test that AuditWriter fails open (doesn't raise on errors)."""
    # Use a read-only directory to trigger write error
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        audit_dir.mkdir()
        audit_dir.chmod(0o444)  # Read-only
        
        writer = AuditWriter(audit_dir=audit_dir)
        
        record = AuditRecord(
            snapshot_id="test",
            input_query="test",
            generated_sql="SELECT 1"
        )
        
        # Should not raise, but return None
        result = writer.write_record(record)
        assert result is None


def test_get_audit_writer_singleton():
    """Test that get_audit_writer returns a singleton instance."""
    writer1 = get_audit_writer()
    writer2 = get_audit_writer()
    
    assert writer1 is writer2, "get_audit_writer should return the same instance"


def test_audit_record_required_keys():
    """Test that audit record contains all required keys."""
    record = AuditRecord(
        snapshot_id="abc123",
        input_query="test",
        generated_sql="SELECT 1"
    )
    
    record_dict = record.to_dict()
    required_keys = ["version", "timestamp", "request_id", "snapshot_id", "input_query", "generated_sql", "metadata"]
    
    for key in required_keys:
        assert key in record_dict, f"Required key '{key}' missing from audit record"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

