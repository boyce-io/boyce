"""
Extractor Base Interface

Defines the contract all extractors must follow.
"""

from __future__ import annotations

from typing import Protocol
from pathlib import Path


class Extractor(Protocol):
    """Protocol for extractor implementations."""
    
    def name(self) -> str:
        """
        Return extractor name.
        
        Returns:
            Extractor name (e.g., "database_catalog", "bi_tool")
        """
        ...
    
    def run(self, *, out_dir: str, since: str | None = None, input_path: str | None = None) -> None:
        """
        Run extraction and emit artifacts.
        
        Args:
            out_dir: Output directory for nodes.jsonl, edges.jsonl, manifest.json
            since: Optional ISO timestamp for incremental extraction
            input_path: Optional input data path (format depends on extractor)
        """
        ...


def write_jsonl(path: Path, items: list[dict]) -> None:
    """
    Write JSONL file atomically (temp → rename).
    
    Args:
        path: Output path
        items: List of dicts to write (one per line)
    """
    import json
    import os
    
    # Create parent directory
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file
    temp_path = path.parent / f".{path.name}.tmp"
    
    temp_file = None
    try:
        temp_file = open(temp_path, "w", encoding="utf-8")
        for item in items:
            json.dump(item, temp_file, sort_keys=True, separators=(",", ":"))
            temp_file.write("\n")
        
        # Sync and atomic rename
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        temp_file = None
        os.rename(temp_path, path)
    except Exception:
        # Clean up on error
        if temp_file:
            try:
                temp_file.close()
            except:
                pass
        if temp_path.exists():
            temp_path.unlink()
        raise

