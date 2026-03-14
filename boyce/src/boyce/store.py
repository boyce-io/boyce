"""
SnapshotStore / DefinitionStore — persist and retrieve protocol objects.

Snapshots are stored as ``<context_dir>/<name>.json``.
Definitions are stored as ``<context_dir>/<name>.definitions.json``.
Validation is run on snapshot load to guarantee only valid snapshots are returned.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from .types import SemanticSnapshot
from .validation import validate_snapshot

logger = logging.getLogger(__name__)


class SnapshotStore:
    """
    File-backed store for SemanticSnapshot objects.

    Each snapshot is persisted as ``<context_dir>/<name>.json``.
    Validation is enforced on load.
    """

    def __init__(self, context_dir: Path) -> None:
        """
        Args:
            context_dir: Directory where snapshot JSON files are stored.
                         Created automatically on first save.
        """
        self.context_dir = context_dir

    def save(self, snapshot: SemanticSnapshot, name: str) -> Path:
        """
        Persist a snapshot to ``<context_dir>/<name>.json``.

        Args:
            snapshot: SemanticSnapshot to persist.
            name: Logical name for the snapshot (used as filename stem).

        Returns:
            Path to the written file.
        """
        self.context_dir.mkdir(parents=True, exist_ok=True)
        path = self.context_dir / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot.model_dump(mode="json"), f, indent=2)
        logger.info("Saved snapshot '%s' to %s", name, path)
        return path

    def load(self, name: str) -> SemanticSnapshot:
        """
        Load and validate a snapshot from ``<context_dir>/<name>.json``.

        Args:
            name: Logical name (filename stem) of the snapshot to load.

        Returns:
            Validated SemanticSnapshot.

        Raises:
            FileNotFoundError: If no file exists for ``name``.
            ValueError: If the loaded data fails validation.
        """
        path = self.context_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Snapshot '{name}' not found in {self.context_dir}"
            )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        errors = validate_snapshot(data)
        if errors:
            raise ValueError(f"Snapshot '{name}' failed validation: {errors}")

        return SemanticSnapshot(**data)


class DefinitionStore:
    """
    File-backed store for certified business definitions.

    Definitions are stored alongside their snapshot as
    ``<context_dir>/<snapshot_name>.definitions.json``.

    Each entry maps a business term to a definition dict::

        {
            "term":           "revenue",
            "definition":     "Total recognized revenue ...",
            "sql_expression": "SUM(CASE WHEN status = 'completed' ...)",  # optional
            "entity_hint":    "orders",   # optional — table the SQL applies to
        }
    """

    def __init__(self, context_dir: Path) -> None:
        self.context_dir = context_dir

    def _path(self, snapshot_name: str) -> Path:
        return self.context_dir / f"{snapshot_name}.definitions.json"

    def upsert(
        self,
        snapshot_name: str,
        term: str,
        definition: str,
        sql_expression: Optional[str] = None,
        entity_hint: Optional[str] = None,
    ) -> int:
        """
        Add or replace a definition entry for ``term``.

        Returns the total number of definitions stored for this snapshot.
        """
        self.context_dir.mkdir(parents=True, exist_ok=True)
        data = self._load_raw(snapshot_name)
        data[term.lower()] = {
            "term": term,
            "definition": definition,
            "sql_expression": sql_expression,
            "entity_hint": entity_hint,
        }
        with open(self._path(snapshot_name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Stored definition '%s' for snapshot '%s'", term, snapshot_name)
        return len(data)

    def load_all(self, snapshot_name: str) -> Dict[str, dict]:
        """Return all definitions for a snapshot. Empty dict if none stored."""
        return self._load_raw(snapshot_name)

    def as_context_string(self, snapshot_name: str) -> Optional[str]:
        """
        Format all definitions as a plain-text block for LLM injection.

        Returns None if no definitions are stored for this snapshot.
        """
        data = self._load_raw(snapshot_name)
        if not data:
            return None

        lines = [
            "Certified Business Definitions — apply these when the user references these terms:"
        ]
        for entry in data.values():
            line = f'  - "{entry["term"]}": {entry["definition"]}'
            if entry.get("sql_expression"):
                hint = f" [table: {entry['entity_hint']}]" if entry.get("entity_hint") else ""
                line += f"\n    SQL: {entry['sql_expression']}{hint}"
            elif entry.get("entity_hint"):
                line += f" [table: {entry['entity_hint']}]"
            lines.append(line)
        return "\n".join(lines)

    def clear(self, snapshot_name: str) -> None:
        """Delete all definitions for snapshot_name (e.g., on snapshot overwrite)."""
        path = self._path(snapshot_name)
        if path.exists():
            path.unlink()
            logger.info("Cleared definitions for snapshot '%s'", snapshot_name)

    def _load_raw(self, snapshot_name: str) -> Dict[str, dict]:
        path = self._path(snapshot_name)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
