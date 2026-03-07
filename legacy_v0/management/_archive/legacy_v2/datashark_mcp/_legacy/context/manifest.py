"""
Manifest Lifecycle

Implements Manifest dataclass with lifecycle methods.
Ensures atomic writes (temp → rename) and validation.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from jsonschema import validate, ValidationError as SchemaValidationError


class ManifestValidationError(Exception):
    """Raised when manifest fails schema validation."""
    pass


def _load_manifest_schema() -> Dict[str, Any]:
    """Load manifest_schema.json using robust schema loader."""
    from datashark_mcp.context.schema_loader import load_manifest_schema
    return load_manifest_schema()


@dataclass
class Manifest:
    """
    Ingestion manifest matching manifest_schema.json.
    
    Tracks run metadata, counts, versions, and hash summaries.
    """
    run_id: str
    system: str
    start_time: str  # ISO 8601
    end_time: str  # ISO 8601
    counts: Dict[str, int]  # nodes, edges, tombstones
    versions: Dict[str, str]  # schema_version, extractor_version
    hash_summaries: Dict[str, str]  # nodes_sha256, edges_sha256
    status: str  # "success", "warning", "failure"
    repo: Optional[str] = None
    changed_since: Optional[str] = None  # ISO 8601
    
    @classmethod
    def start_run(
        cls,
        system: str,
        repo: Optional[str] = None,
        changed_since: Optional[str] = None,
        schema_version: str = "0.1.0",
        extractor_version: str = "1.0.0"
    ) -> Manifest:
        """
        Start a new extraction run.
        
        Args:
            system: Source system identifier
            repo: Repository identifier (optional)
            changed_since: Watermark for incremental runs (optional)
            schema_version: Graph schema version
            extractor_version: Extractor version
            
        Returns:
            New Manifest with start_time set
        """
        run_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc).isoformat()
        
        return cls(
            run_id=run_id,
            system=system,
            repo=repo,
            start_time=start_time,
            end_time="",  # Will be set in end_run
            counts={"nodes": 0, "edges": 0, "tombstones": 0},
            versions={
                "schema_version": schema_version,
                "extractor_version": extractor_version
            },
            hash_summaries={"nodes_sha256": "", "edges_sha256": ""},
            status="success",
            changed_since=changed_since
        )
    
    def end_run(
        self,
        status: str,
        counts: Dict[str, int],
        hash_summaries: Dict[str, str]
    ) -> None:
        """
        Finalize manifest with run results.
        
        Args:
            status: "success", "warning", or "failure"
            counts: Dict with nodes, edges, tombstones counts
            hash_summaries: Dict with nodes_sha256, edges_sha256
        """
        self.end_time = datetime.now(timezone.utc).isoformat()
        self.status = status
        self.counts = counts
        self.hash_summaries = hash_summaries
    
    def to_json(self) -> Dict[str, Any]:
        """Convert to dict matching manifest_schema.json."""
        result = {
            "run_id": self.run_id,
            "system": self.system,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "counts": self.counts,
            "versions": self.versions,
            "hash_summaries": self.hash_summaries,
            "status": self.status,
        }
        if self.repo is not None:
            result["repo"] = self.repo
        if self.changed_since is not None:
            result["changed_since"] = self.changed_since
        return result
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> Manifest:
        """Create Manifest from dict."""
        return cls(
            run_id=data["run_id"],
            system=data["system"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            counts=data["counts"],
            versions=data["versions"],
            hash_summaries=data["hash_summaries"],
            status=data["status"],
            repo=data.get("repo"),
            changed_since=data.get("changed_since")
        )
    
    def validate(self) -> None:
        """Validate manifest against manifest_schema.json."""
        schema = _load_manifest_schema()
        try:
            validate(instance=self.to_json(), schema=schema)
        except SchemaValidationError as e:
            raise ManifestValidationError(f"Manifest validation failed: {e.message}") from e
    
    def write_atomic(self, manifest_path: Path) -> None:
        """
        Write manifest to file atomically (temp → rename).
        
        Args:
            manifest_path: Path to write manifest.json
        """
        # Create parent directory if needed
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file
        temp_path = manifest_path.parent / f".manifest.{self.run_id}.tmp"
        
        temp_file = None
        try:
            # Write JSON
            temp_file = open(temp_path, "w", encoding="utf-8")
            json.dump(self.to_json(), temp_file, indent=2, sort_keys=True)
            
            # Sync to disk
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            temp_file = None
            
            # Atomic rename
            os.rename(temp_path, manifest_path)
        except Exception:
            # Clean up temp file on error
            if temp_file:
                try:
                    temp_file.close()
                except:
                    pass
            if temp_path.exists():
                temp_path.unlink()
            raise

