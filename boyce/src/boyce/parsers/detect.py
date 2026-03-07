"""
Source type detection and unified parse_from_path entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from boyce.types import SemanticSnapshot


def detect_source_type(
    file_path: Optional[Path] = None,
    source_text: Optional[str] = None,
) -> str:
    """
    Detect ingestion source type from path or content.

    Returns one of: "dbt_manifest", "dbt_project", "lookml", "ddl", "sqlite", "unknown".

    For file paths, delegates to the registry for confidence-based detection.
    For source text, uses inline heuristics (no registry support for raw text).
    """
    if file_path:
        from .registry import get_default_registry
        path = Path(file_path)
        candidates = get_default_registry().detect(path)
        if candidates:
            return candidates[0][0].source_type()
        return "unknown"

    if source_text:
        if '"nodes"' in source_text and '"sources"' in source_text:
            return "dbt_manifest"
        if "view:" in source_text or "explore:" in source_text:
            return "lookml"
        if "CREATE TABLE" in source_text.upper() or "CREATE VIEW" in source_text.upper():
            return "ddl"
        if "name:" in source_text and "models:" in source_text:
            return "dbt_project"

    return "unknown"


def parse_from_path(source_path: str | Path) -> SemanticSnapshot:
    """
    Auto-detect and parse a file or directory into a SemanticSnapshot.
    Uses the parser registry for confidence-based dispatch with fallback.

    Supports:
      - dbt manifest.json
      - dbt project directory (contains dbt_project.yml)
      - LookML .lkml / .lookml file
      - SQLite database files (.sqlite, .db, etc.)
      - Raw SQL DDL files (.sql)

    Raises:
        ValueError: If the source type cannot be determined or is unsupported.
    """
    from .registry import get_default_registry

    path = Path(source_path)
    return get_default_registry().parse(path)
