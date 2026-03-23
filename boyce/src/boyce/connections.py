"""
ConnectionStore — persist database connection DSNs across server restarts.

Connections are stored as ``<context_dir>/connections.json``.
Raw DSNs are stored as-is (``_local_context/`` is gitignored).
Redaction happens only at display time via ``list_all()``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConnectionStore:
    """
    File-backed store for database connection DSNs.

    Each entry maps a snapshot name to its originating DSN, stored in
    ``<context_dir>/connections.json``.  Designed to survive server
    restarts so ``_get_adapter()`` can reconnect without requiring
    ``BOYCE_DB_URL`` to be set in the environment.
    """

    def __init__(self, context_dir: Path) -> None:
        self._path = context_dir / "connections.json"
        self._context_dir = context_dir

    def _read(self) -> Dict[str, Any]:
        """Load the connections file, returning empty dict if missing."""
        if not self._path.exists():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read connections.json: %s", exc)
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        """Write the connections file, creating the directory if needed."""
        self._context_dir.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save(self, snapshot_name: str, dsn: str, source: str = "ingest_source") -> None:
        """
        Write or update a DSN entry for a snapshot.

        Args:
            snapshot_name: Logical name of the snapshot (e.g. "pagila").
            dsn: Raw PostgreSQL DSN (stored as-is — _local_context/ is gitignored).
            source: How this DSN was obtained (e.g. "ingest_source", "boyce_init").
        """
        data = self._read()
        now = datetime.now(timezone.utc).isoformat()
        data[snapshot_name] = {
            "dsn": dsn,
            "source": source,
            "created": data.get(snapshot_name, {}).get("created", now),
            "last_used": now,
        }
        self._write(data)
        logger.info("Saved connection for snapshot '%s'", snapshot_name)

    def load(self, snapshot_name: str) -> Optional[str]:
        """
        Return the raw DSN string for a snapshot, or None if not stored.
        """
        data = self._read()
        entry = data.get(snapshot_name)
        if entry and entry.get("dsn"):
            return entry["dsn"]
        return None

    def touch(self, snapshot_name: str) -> None:
        """Update the last_used timestamp for a connection entry."""
        data = self._read()
        if snapshot_name in data:
            data[snapshot_name]["last_used"] = datetime.now(timezone.utc).isoformat()
            self._write(data)

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Return all stored connections with passwords redacted for display.

        Returns a dict keyed by snapshot name, each value containing
        dsn_redacted, source, created, and last_used.
        """
        from .adapters.postgres import _redact_dsn

        data = self._read()
        result: Dict[str, Dict[str, Any]] = {}
        for name, entry in data.items():
            result[name] = {
                "dsn_redacted": _redact_dsn(entry.get("dsn", "")),
                "source": entry.get("source", "unknown"),
                "created": entry.get("created", ""),
                "last_used": entry.get("last_used", ""),
            }
        return result

    def remove(self, snapshot_name: str) -> bool:
        """
        Remove a connection entry.  Returns True if the entry existed.
        """
        data = self._read()
        if snapshot_name in data:
            del data[snapshot_name]
            self._write(data)
            logger.info("Removed connection for snapshot '%s'", snapshot_name)
            return True
        return False

    def snapshot_names(self) -> List[str]:
        """Return list of snapshot names that have stored connections."""
        return list(self._read().keys())
