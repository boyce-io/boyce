"""
SQLite Direct Introspection Parser

Introspects a .sqlite/.db file via stdlib sqlite3.
Uses PRAGMA table_info() and PRAGMA foreign_key_list() to extract
entities, fields, and FK-based joins.

Zero external dependencies — sqlite3 is stdlib.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from .base import build_snapshot


def _normalize_sqlite_type(declared_type: str) -> str:
    """Normalize SQLite's flexible type names to standard SQL types."""
    t = declared_type.strip().upper()
    if not t:
        return "BLOB"
    # INTEGER affinity
    if t in ("INTEGER", "INT", "BIGINT", "SMALLINT", "TINYINT", "MEDIUMINT", "INT2", "INT8"):
        return "INTEGER"
    # REAL affinity
    if t in ("REAL", "DOUBLE", "DOUBLE PRECISION", "FLOAT"):
        return "REAL"
    # BOOLEAN
    if t == "BOOLEAN":
        return "BOOLEAN"
    # Temporal
    if t in ("DATETIME", "TIMESTAMP"):
        return "TIMESTAMP"
    if t == "DATE":
        return "DATE"
    # BLOB affinity
    if t == "BLOB":
        return "BLOB"
    # NUMERIC affinity — preserve precision if present (e.g. DECIMAL(10,2))
    if t.startswith("DECIMAL") or t.startswith("NUMERIC"):
        return declared_type.strip()  # preserve original precision
    # TEXT affinity — preserve length if present (e.g. VARCHAR(255))
    if any(t.startswith(prefix) for prefix in (
        "TEXT", "CLOB", "CHARACTER", "VARCHAR", "VARYING CHARACTER",
        "NCHAR", "NVARCHAR", "NATIVE CHARACTER",
    )):
        return declared_type.strip()
    # Unknown — return as-is
    return declared_type.strip() or "BLOB"


def _infer_field_type(
    col_name: str,
    normalized_type: str,
    is_pk: bool,
    is_fk: bool,
) -> FieldType:
    """Infer semantic FieldType from column name, SQL type, and key constraints."""
    if is_pk:
        return FieldType.ID
    if is_fk:
        return FieldType.FOREIGN_KEY
    nt = normalized_type.upper()
    name_lower = col_name.lower()
    if nt in ("TIMESTAMP", "DATE") or any(
        kw in name_lower for kw in ("_at", "_date", "timestamp", "datetime")
    ):
        return FieldType.TIMESTAMP
    if any(kw in nt for kw in ("DECIMAL", "REAL", "NUMERIC", "FLOAT")) and any(
        kw in name_lower for kw in ("amount", "price", "total", "revenue", "cost")
    ):
        return FieldType.MEASURE
    return FieldType.DIMENSION


def parse_sqlite_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a SQLite database file and return a SemanticSnapshot.

    Introspects schema via PRAGMA table_info() and PRAGMA foreign_key_list().
    Opens the file in read-only URI mode — does not modify the database.

    Args:
        file_path: Path to a SQLite database file.

    Returns:
        SemanticSnapshot with entities (tables), fields (columns), and joins (FKs).

    Raises:
        ValueError: If the file cannot be opened as a SQLite database.
    """
    file_path = Path(file_path)
    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    try:
        conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        raise ValueError(f"Cannot open SQLite file '{file_path}': {e}") from e

    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [row[0] for row in cursor.fetchall()]

        for table_name in table_names:
            entity_id = f"entity:{table_name}"
            entity_fields: List[str] = []

            # Get FK columns for this table so we can mark FOREIGN_KEY type
            fk_rows = conn.execute(f"PRAGMA foreign_key_list('{table_name}')").fetchall()
            # fk_rows: (id, seq, table, from, to, on_update, on_delete, match)
            fk_source_cols = {row[3] for row in fk_rows}

            col_rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            # col_rows: (cid, name, type, notnull, dflt_value, pk)

            pk_cols: List[str] = []
            for row in col_rows:
                cid, col_name, col_type, notnull, dflt_value, pk = row
                if pk > 0:
                    pk_cols.append((pk, col_name))

            # Sort by pk index for composite PK grain ordering
            pk_cols.sort(key=lambda x: x[0])
            pk_col_names = [name for _, name in pk_cols]

            if len(pk_col_names) == 1:
                grain = pk_col_names[0]
            elif len(pk_col_names) > 1:
                grain = "_".join(pk_col_names)
            else:
                grain = "rowid"

            for row in col_rows:
                cid, col_name, col_type, notnull, dflt_value, pk = row
                field_id = f"field:{table_name}:{col_name}"
                is_pk = pk > 0
                is_fk = col_name in fk_source_cols and not is_pk
                normalized_type = _normalize_sqlite_type(col_type or "")
                field_type = _infer_field_type(col_name, normalized_type, is_pk, is_fk)

                fields[field_id] = FieldDef(
                    id=field_id,
                    entity_id=entity_id,
                    name=col_name,
                    field_type=field_type,
                    data_type=normalized_type,
                    nullable=not bool(notnull),
                    primary_key=is_pk,
                )
                entity_fields.append(field_id)

            entities[entity_id] = Entity(
                id=entity_id,
                name=table_name,
                schema_name="main",
                fields=entity_fields,
                grain=grain,
            )

            # Build JoinDefs from FK constraints
            # Group by FK id to handle multi-column FKs (use first column pair)
            seen_fk_ids: Dict[int, bool] = {}
            join_target_counts: Dict[str, int] = {}

            for fk_row in fk_rows:
                fk_id, seq, target_table, from_col, to_col = fk_row[0], fk_row[1], fk_row[2], fk_row[3], fk_row[4]
                if fk_id in seen_fk_ids:
                    continue  # Skip subsequent columns of multi-column FK
                seen_fk_ids[fk_id] = True

                target_entity_id = f"entity:{target_table}"
                join_target_counts[target_table] = join_target_counts.get(target_table, 0) + 1
                count = join_target_counts[target_table]
                join_id = (
                    f"join:{table_name}:{target_table}"
                    if count == 1
                    else f"join:{table_name}:{target_table}:{from_col}"
                )

                joins.append(JoinDef(
                    id=join_id,
                    source_entity_id=entity_id,
                    target_entity_id=target_entity_id,
                    join_type=JoinType.LEFT,
                    source_field_id=f"field:{table_name}:{from_col}",
                    target_field_id=f"field:{target_table}:{to_col}",
                    description=f"SQLite FK: {table_name}.{from_col} -> {target_table}.{to_col}",
                ))

    finally:
        conn.close()

    return build_snapshot(
        source_system="sqlite",
        source_version=sqlite3.sqlite_version,
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "source_file": str(file_path),
            "table_count": len(entities),
            "sqlite_version": sqlite3.sqlite_version,
        },
    )


class SQLiteParser:
    """SnapshotParser implementation for SQLite database files."""

    EXTENSIONS = {".sqlite", ".db", ".sqlite3", ".db3", ".s3db", ".sl3"}

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix.lower() in self.EXTENSIONS:
            try:
                with open(path, "rb") as f:
                    header = f.read(16)
                if header[:16] == b"SQLite format 3\x00":
                    return 0.95
            except Exception:
                pass
            return 0.4
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_sqlite_file(Path(path))

    def source_type(self) -> str:
        return "sqlite"
