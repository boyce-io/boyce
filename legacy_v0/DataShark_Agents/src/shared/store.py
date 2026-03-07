"""
Shared vector store: LanceDB-backed storage with fixed 384-d vectors (all-MiniLM-L6-v2).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import lancedb
import pyarrow as pa

# Repo root: absolute path so data/lancedb is always relative to repo, not cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VECTOR_DIM = 384
DB_PATH = _REPO_ROOT / "data" / "lancedb"
TABLE_NAME = "documents"

# PyArrow schema: id (PK), vector[384], text, metadata (JSON string), last_updated (timestamp)
STORE_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
    pa.field("text", pa.string()),
    pa.field("metadata", pa.string()),
    pa.field("last_updated", pa.timestamp("us", tz="UTC")),
])


class VectorStore:
    """LanceDB vector store with upsert-by-id and vector search. Uses lancedb + pyarrow only."""

    def __init__(self, db_path: Path | str | None = None, table_name: str | None = None):
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._table_name = table_name or TABLE_NAME
        self._db: lancedb.DBConnection | None = None

    def initialize_db(self) -> None:
        """
        Create local LanceDB at repo_root/data/lancedb (absolute path from repo root); ensure directory exists.
        Define table with STORE_SCHEMA; create empty table if it does not exist.
        """
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._db_path))
        if self._table_name not in self._db.table_names():
            self._db.create_table(self._table_name, schema=STORE_SCHEMA)

    def _get_table(self):
        if self._db is None:
            self.initialize_db()
        return self._db.open_table(self._table_name)

    def upsert(
        self,
        id: str,
        text: str,
        metadata_dict: dict,
        vector: list[float],
    ) -> None:
        """
        Upsert one record by id: overwrite if exists, insert otherwise.
        metadata_dict is serialized to a JSON string; last_updated set to now (UTC).
        """
        if len(vector) != VECTOR_DIM:
            raise ValueError(f"vector must have length {VECTOR_DIM}, got {len(vector)}")
        now = datetime.now(timezone.utc)
        metadata_str = json.dumps(metadata_dict)
        table = pa.table(
            {
                "id": [id],
                "vector": pa.array([vector], type=pa.list_(pa.float32(), VECTOR_DIM)),
                "text": [text],
                "metadata": [metadata_str],
                "last_updated": pa.array([now], type=pa.timestamp("us", tz="UTC")),
            },
            schema=STORE_SCHEMA,
        )
        tbl = self._get_table()
        tbl.merge_insert("id").when_not_matched_insert_all().when_matched_update_all().execute(table)

    def search(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        """
        Vector search: return list of dicts with 'id', 'text', and 'metadata' for the nearest neighbors.
        metadata is returned as a string (JSON); callers may parse if needed.
        """
        if len(query_vector) != VECTOR_DIM:
            raise ValueError(f"query_vector must have length {VECTOR_DIM}, got {len(query_vector)}")
        tbl = self._get_table()
        results = (
            tbl.search(query_vector)
            .select(["id", "text", "metadata"])
            .limit(limit)
            .to_list()
        )
        return results
