"""
Boyce — Audit Log

Append-only JSONL audit trail for every ask_boyce call.
Written to _local_context/audit.jsonl — one record per line.

This is the protocol's paper trail: who asked what, which SQL was generated,
whether it was validated, and what warnings fired. Required for enterprise
compliance and for the provenance layer (Week 6+).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditLog:
    """
    Append-only JSONL audit log stored at ``<context_dir>/audit.jsonl``.

    Each record is a JSON object on a single line with the following fields:

        ts                — ISO-8601 UTC timestamp
        query             — original natural language query
        snapshot_name     — logical snapshot name used
        snapshot_id       — SHA-256 of the snapshot (first 16 chars for readability)
        sql               — generated SQL (truncated to 2000 chars)
        entities_resolved — list of entity names the planner selected
        validation_status — "verified" | "invalid" | "unchecked"
        null_trap_count   — number of NULL trap warnings fired
        compat_risk_count — number of Redshift compat warnings fired
        error             — error message string, or null if successful
    """

    def __init__(self, context_dir: Path) -> None:
        self.context_dir = context_dir

    @property
    def path(self) -> Path:
        return self.context_dir / "audit.jsonl"

    def log_query(
        self,
        query: str,
        snapshot_name: str,
        snapshot_id: str,
        sql: str,
        entities_resolved: List[str],
        validation_status: str,
        null_trap_count: int = 0,
        compat_risk_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """
        Append one query record to the audit log.

        Never raises — a failed write is logged at WARNING level and swallowed
        so that audit errors never interrupt query generation.
        """
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "snapshot_name": snapshot_name,
            "snapshot_id": snapshot_id[:16] if snapshot_id else "",
            "sql": sql[:2000] if sql else "",
            "entities_resolved": entities_resolved,
            "validation_status": validation_status,
            "null_trap_count": null_trap_count,
            "compat_risk_count": compat_risk_count,
            "error": error,
        }
        try:
            self.context_dir.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("AuditLog: failed to write record: %s", exc)

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        """
        Return the last ``n`` audit records as a list of dicts.

        Returns an empty list if the log file does not exist.
        """
        if not self.path.exists():
            return []
        records: List[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records[-n:]
