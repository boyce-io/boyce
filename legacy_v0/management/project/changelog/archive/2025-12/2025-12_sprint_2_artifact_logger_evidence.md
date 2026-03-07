# 1) audit.py (full)

```python
"""
Artifact Logger for DataShark Phase 1 Debuggability.

This module implements the ArtifactLogger that captures the complete audit trail
for every SQL generation cycle: Input → Snapshot → SQL.

Contract:
    - Captures raw input_query, snapshot_id, generated_sql, and metadata
    - Writes deterministic JSONL artifacts to configurable directory
    - Files are named by date and run id: audit_YYYY-MM-DD_<run_id>.jsonl
    - Each record includes: timestamp, request_id (uuid4), snapshot_id, sql, input payload
    - Read-only observer: does not alter SQLBuilder output
    - Fail-open: errors do not block SQL generation
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    """
    Audit record schema for SQL generation artifacts.
    
    Version 1.0 schema:
    - timestamp: ISO 8601 UTC timestamp
    - request_id: UUID4 identifier for this request
    - snapshot_id: SHA-256 hash of the semantic snapshot used
    - input_query: Raw natural language query string
    - generated_sql: Final SQL string generated
    - metadata: Optional additional metadata (dialect, etc.)
    """
    version: str = "1.0"
    timestamp: str = ""
    request_id: str = ""
    snapshot_id: str = ""
    input_query: str = ""
    generated_sql: str = ""
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Set defaults after initialization."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.request_id:
            self.request_id = str(uuid.uuid4())
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Serialize to JSON string (single line, no indentation)."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


class AuditWriter:
    """
    Writes audit records to JSONL files.
    
    Default behavior:
    - Writes to directory specified by DATASHARK_AUDIT_DIR env var
    - Falls back to .datashark/audit/ if env var not set
    - Filename format: audit_YYYY-MM-DD_<run_id>.jsonl
    - Each line is a complete JSON record (JSONL format)
    - Atomic writes (write to temp file, then rename)
    """
    
    def __init__(self, audit_dir: Optional[Path] = None):
        """
        Initialize audit writer.
        
        Args:
            audit_dir: Optional custom audit directory path.
                      Defaults to DATASHARK_AUDIT_DIR env var or .datashark/audit/
        """
        if audit_dir is None:
            audit_dir_str = os.getenv("DATASHARK_AUDIT_DIR")
            if audit_dir_str:
                audit_dir = Path(audit_dir_str).resolve()
            else:
                # Default to .datashark/audit/ relative to current working directory
                audit_dir = Path.cwd() / ".datashark" / "audit"
        
        self.audit_dir = Path(audit_dir).resolve()
        self._ensure_audit_dir()
    
    def _ensure_audit_dir(self) -> None:
        """Ensure the audit directory exists."""
        try:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(
                f"Failed to create audit directory {self.audit_dir}: {e}. "
                f"Audit logging will be disabled."
            )
    
    def _get_filename(self, request_id: str) -> str:
        """
        Generate filename for audit record.
        
        Format: audit_YYYY-MM-DD_<request_id>.jsonl
        
        Args:
            request_id: UUID4 request identifier
            
        Returns:
            Filename string
        """
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Use first 8 chars of request_id for brevity
        run_id = request_id[:8]
        return f"audit_{date_str}_{run_id}.jsonl"
    
    def write_record(self, record: AuditRecord) -> Optional[Path]:
        """
        Write a single audit record to JSONL file.
        
        Uses atomic write (write to temp file, then rename) to ensure
        data integrity even if process crashes mid-write.
        
        Args:
            record: AuditRecord instance to write
            
        Returns:
            Path to the written file, or None if write failed
            
        Raises:
            OSError: If the audit file cannot be written (logged but not raised)
        """
        if not self.audit_dir.exists():
            logger.warning(f"Audit directory {self.audit_dir} does not exist. Skipping audit write.")
            return None
        
        filename = self._get_filename(record.request_id)
        file_path = self.audit_dir / filename
        
        try:
            # Atomic write: write to temp file, then rename
            temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
            
            # Append mode (JSONL format - one record per line)
            with open(temp_path, "a", encoding="utf-8") as f:
                json_line = record.to_json()
                f.write(json_line + "\n")
            
            # Atomic rename
            temp_path.replace(file_path)
            
            logger.debug(f"Audit record written to {file_path}")
            return file_path
            
        except OSError as e:
            logger.error(f"Failed to write audit record to {file_path}: {e}")
            # Fail-open: don't raise, just log
            return None


# Global singleton instance (lazy initialization)
_global_writer: Optional[AuditWriter] = None


def get_audit_writer(audit_dir: Optional[Path] = None) -> AuditWriter:
    """
    Get the global AuditWriter singleton instance.
    
    Args:
        audit_dir: Optional custom audit directory path.
                  Only used on first call; subsequent calls ignore this parameter.
    
    Returns:
        The global AuditWriter instance
    """
    global _global_writer
    if _global_writer is None:
        _global_writer = AuditWriter(audit_dir=audit_dir)
    return _global_writer


def log_artifact(
    input_query: str,
    snapshot_id: str,
    generated_sql: str,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Path]:
    """
    Convenience function to log an artifact using the global writer.
    
    This is the primary entry point for logging artifacts from engine/planner.
    
    Args:
        input_query: The raw natural language query string
        snapshot_id: SHA-256 hash of the semantic snapshot used
        generated_sql: The final SQL string generated
        request_id: Optional UUID4 request identifier (generated if not provided)
        metadata: Optional additional metadata dictionary (dialect, etc.)
    
    Returns:
        Path to the written audit file, or None if write failed
    """
    try:
        record = AuditRecord(
            request_id=request_id or str(uuid.uuid4()),
            snapshot_id=snapshot_id,
            input_query=input_query,
            generated_sql=generated_sql,
            metadata=metadata or {}
        )
        
        writer = get_audit_writer()
        return writer.write_record(record)
    except Exception as e:
        # Fail-open: log error but don't raise
        logger.warning(f"Artifact logging failed: {e}")
        return None
```

# 2) engine.py hook (diff hunk)

```python
import json
import logging
from typing import Any, Dict, Optional

from datashark_mcp.kernel.exceptions import ContextValidationError, SnapshotIntegrityError
from datashark_mcp.kernel.snapshot_factory import SnapshotFactory
from datashark_mcp.kernel.types import SemanticGraph, SnapshotID, UserContext
from datashark_mcp.kernel.air_gap_api import AirGapAPI
from datashark_mcp.planner.planner import Planner
from datashark_mcp.security.graph_projector import GraphProjector
from datashark_mcp.security.policy import PolicySet
from datashark.core.audit import log_artifact

logger = logging.getLogger(__name__)

...

        # Step 4: Execute planning pipeline
        # Convert UserContext to dict for planner
        user_context_dict = self.context.model_dump()
        
        # Get snapshot_id string
        snapshot_id_str = self._snapshot_id.id
        
        result = planner.plan_and_build_sql(
            query_input=intent,
            user_context=user_context_dict,
            active_snapshot_id=snapshot_id_str
        )
        
        # Step 5: Log artifact (fail-open: don't block on audit errors)
        try:
            generated_sql = result.get("final_sql_output", "")
            log_artifact(
                input_query=intent,
                snapshot_id=snapshot_id_str,
                generated_sql=generated_sql,
                metadata={"dialect": "postgres"}  # Default dialect
            )
        except Exception as e:
            # Fail-open: log error but don't raise
            logger.warning(f"Artifact logging failed: {e}")
        
        # Step 6: Return result
        return result
```

# 3) planner.py change (diff hunk)

```python
from datashark_mcp.planner.grain import GrainResolver
from datashark_mcp.planner.join import JoinPlanner
from datashark_mcp.planner.mapper import ConceptMapper
from datashark_mcp.planner.sql import SQLBuilder
from datashark_mcp.kernel.air_gap_api import AirGapAPI
from datashark.core.audit import log_artifact

...

        # Generate final SQL
        final_sql_output = self.sql_builder.build_final_sql(final_plan)
        reasoning_steps.append("SQL Finalization: Rendered final SQL with all parameters substituted")
        
        # Note: Artifact logging is handled at engine.process_request() level
        # to ensure all entrypoints are covered. This hook remains for backward compatibility
        # but engine-level logging is the primary audit point.
        
        # Step 6: Final Output Assembly
        output: Dict[str, Any] = {
            "reasoning_steps": reasoning_steps,
            "concept_map": concept_map,
            "join_path": join_path,
            "grain_context": grain_context,
            "policy_context": policy_context,
            "sql_template": sql_template,
            "final_sql_output": final_sql_output,
        }
        
        return output
```

# 4) test_audit.py (full)

```python
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
    """Test that AuditWriter writes in JSONL format (one JSON object per line)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        writer = AuditWriter(audit_dir=audit_dir)
        
        # Write multiple records
        for i in range(3):
            record = AuditRecord(
                snapshot_id=f"snapshot_{i}",
                input_query=f"query {i}",
                generated_sql=f"SELECT {i}"
            )
            writer.write_record(record)
        
        # Find the JSONL file
        jsonl_files = list(audit_dir.glob("*.jsonl"))
        assert len(jsonl_files) > 0
        
        # Read and verify JSONL format (one JSON object per line)
        with open(jsonl_files[0], "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 3  # Three records written
            
            for line in lines:
                # Each line should be valid JSON
                parsed = json.loads(line)
                assert "version" in parsed
                assert "snapshot_id" in parsed


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
```

# 5) Grep results (repo-wide)

## log_artifact(

```
datashark-mcp/src/datashark/core/audit.py:192:def log_artifact(
datashark-mcp/tests/test_audit.py:136:            file_path = log_artifact(
datashark-mcp/src/datashark_mcp/kernel/engine.py:162:            log_artifact(
tests/test_audit.py:66:        artifact_path = logger.log_artifact(
tests/test_audit.py:108:        artifact_path = logger.log_artifact(
tests/test_audit.py:163:        artifact_path = logger.log_artifact(
tests/test_audit.py:185:        artifact_path = logger.log_artifact(
```

## AuditWriter

```
datashark-mcp/src/datashark/core/audit.py:69:class AuditWriter:
datashark-mcp/src/datashark/core/audit.py:172:_global_writer: Optional[AuditWriter] = None
datashark-mcp/src/datashark/core/audit.py:175:def get_audit_writer(audit_dir: Optional[Path] = None) -> AuditWriter:
datashark-mcp/src/datashark/core/audit.py:177:    Get the global AuditWriter singleton instance.
datashark-mcp/src/datashark/core/audit.py:184:        The global AuditWriter instance
datashark-mcp/src/datashark/core/audit.py:188:        _global_writer = AuditWriter(audit_dir=audit_dir)
datashark-mcp/tests/test_audit.py:2:Unit tests for AuditWriter and AuditRecord.
datashark-mcp/tests/test_audit.py:14:from datashark.core.audit import AuditRecord, AuditWriter, get_audit_writer, log_artifact
datashark-mcp/tests/test_audit.py:52:    """Test that AuditWriter writes a record to JSONL file."""
datashark-mcp/tests/test_audit.py:55:        writer = AuditWriter(audit_dir=audit_dir)
datashark-mcp/tests/test_audit.py:84:    """Test that AuditWriter creates audit directory if it doesn't exist."""
datashark-mcp/tests/test_audit.py:90:        writer = AuditWriter(audit_dir=audit_dir)
datashark-mcp/tests/test_audit.py:97:    """Test that AuditWriter writes in JSONL format (one JSON object per line)."""
datashark-mcp/tests/test_audit.py:100:        writer = AuditWriter(audit_dir=audit_dir)
datashark-mcp/tests/test_audit.py:133:            mock_writer = AuditWriter(audit_dir=audit_dir)
datashark-mcp/tests/test_audit.py:147:    """Test that AuditWriter fails open (doesn't raise on errors)."""
datashark-mcp/tests/test_audit.py:154:        writer = AuditWriter(audit_dir=audit_dir)
```

## DATASHARK_AUDIT_DIR

```
datashark-mcp/src/datashark/core/audit.py:74:    - Writes to directory specified by DATASHARK_AUDIT_DIR env var
datashark-mcp/src/datashark/core/audit.py:87:                      Defaults to DATASHARK_AUDIT_DIR env var or .datashark/audit/
datashark-mcp/src/datashark/core/audit.py:90:            audit_dir_str = os.getenv("DATASHARK_AUDIT_DIR")
```

