"""
Parser plugin interface and shared utilities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Protocol, runtime_checkable

from boyce.types import (
    Entity,
    FieldDef,
    JoinDef,
    SemanticSnapshot,
)
from boyce.validation import canonicalize_snapshot_for_hash


@runtime_checkable
class SnapshotParser(Protocol):
    """Protocol that all parsers must implement."""

    def detect(self, path: Path) -> float:
        """
        Return confidence (0.0–1.0) that this parser can handle the given path.
        0.0 = definitely cannot parse this.
        1.0 = definitely can parse this.
        """
        ...

    def parse(self, path: Path) -> SemanticSnapshot:
        """Parse the source at `path` and return a SemanticSnapshot."""
        ...

    def source_type(self) -> str:
        """Return a short identifier for this parser type, e.g. 'dbt_manifest'."""
        ...


def build_snapshot(
    source_system: str,
    source_version: str,
    entities: Dict[str, Entity],
    fields: Dict[str, FieldDef],
    joins: List[JoinDef],
    metadata: Dict[str, Any],
) -> SemanticSnapshot:
    """Compute SHA-256 snapshot_id and return a frozen SemanticSnapshot.

    Uses canonicalize_snapshot_for_hash() to strip profiling fields before
    hashing, ensuring the snapshot_id is stable across profile runs.
    """
    payload = {
        "source_system": source_system,
        "source_version": source_version,
        "schema_version": "v0.1",
        "entities": {k: v.model_dump(mode="json") for k, v in entities.items()},
        "fields": {k: v.model_dump(mode="json") for k, v in fields.items()},
        "joins": [j.model_dump(mode="json") for j in joins],
        "metadata": metadata,
    }
    canonical = canonicalize_snapshot_for_hash(payload)
    content = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    snapshot_id = hashlib.sha256(content.encode("utf-8")).hexdigest()
    payload["snapshot_id"] = snapshot_id
    return SemanticSnapshot(**payload)
