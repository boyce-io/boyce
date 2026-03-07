"""
Raw DDL Parser

Parses CREATE TABLE statements from SQL files (.sql).
Handles Postgres, T-SQL (SQL Server), and generic ANSI SQL dialects.
Uses sqlparse (already a project dependency) for statement splitting.

Zero new external dependencies.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import sqlparse

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from .base import build_snapshot


# ---------------------------------------------------------------------------
# Type normalization
# ---------------------------------------------------------------------------

def _normalize_ddl_type(raw_type: str) -> str:
    """Normalize SQL dialect type names to standard SQL types."""
    t = raw_type.strip().strip('"').strip("'")
    tu = t.upper()

    # INTEGER affinity
    if tu in ("INTEGER", "INT", "INT4", "INT2", "INT8", "TINYINT", "MEDIUMINT"):
        return "INTEGER"
    if tu == "SMALLINT":
        return "SMALLINT"
    if tu == "BIGINT":
        return "BIGINT"
    # SERIAL → INTEGER (with PK implication handled separately)
    if tu == "SERIAL":
        return "INTEGER"
    if tu == "BIGSERIAL":
        return "BIGINT"
    # REAL / FLOAT
    if tu in ("REAL", "FLOAT4"):
        return "REAL"
    if tu in ("DOUBLE PRECISION", "FLOAT8", "FLOAT"):
        return "DOUBLE PRECISION"
    # BOOLEAN
    if tu in ("BOOLEAN", "BOOL", "BIT"):
        return "BOOLEAN"
    # Temporal
    if tu in ("TIMESTAMP", "DATETIME", "TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP WITH TIME ZONE"):
        return "TIMESTAMP"
    if tu == "DATE":
        return "DATE"
    # T-SQL MONEY → DECIMAL(19,4)
    if tu == "MONEY":
        return "DECIMAL(19,4)"
    # TEXT / CLOB
    if tu in ("TEXT", "NTEXT", "CLOB"):
        return "TEXT"
    # BLOB / BINARY
    if tu in ("IMAGE", "BYTEA", "BLOB", "BINARY", "VARBINARY"):
        return "BYTEA"
    # DECIMAL / NUMERIC — preserve precision
    if tu.startswith("DECIMAL") or tu.startswith("NUMERIC"):
        return t.upper()
    # DATETIME2(N) → TIMESTAMP
    if tu.startswith("DATETIME"):
        return "TIMESTAMP"
    # VARCHAR family — normalize to VARCHAR(N)
    for prefix in ("NVARCHAR", "VARCHAR", "CHARACTER VARYING", "VARYING CHARACTER"):
        if tu.startswith(prefix):
            # Extract (N) if present
            m = re.search(r"\((\d+)\)", t)
            return f"VARCHAR({m.group(1)})" if m else "VARCHAR"
    # CHAR family
    for prefix in ("NCHAR", "CHAR", "CHARACTER"):
        if tu.startswith(prefix):
            m = re.search(r"\((\d+)\)", t)
            return f"CHAR({m.group(1)})" if m else "CHAR"
    # Unknown — uppercase and return as-is
    return tu if tu else "TEXT"


# ---------------------------------------------------------------------------
# Body extraction — respect nested parens
# ---------------------------------------------------------------------------

def _extract_create_body(stmt_text: str) -> Tuple[str, str]:
    """
    Given a CREATE TABLE statement, return (table_name_raw, body_text).
    body_text is the content between the outermost parentheses.
    Returns ('', '') if not parseable.
    """
    # Capture everything up to the first '('
    m = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(.+?)\s*\(",
        stmt_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ("", "")

    table_name_raw = m.group(1).strip()
    start = m.end()  # position just after the '('

    depth = 1
    pos = start
    while depth > 0 and pos < len(stmt_text):
        ch = stmt_text[pos]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        pos += 1

    body = stmt_text[start : pos - 1] if depth == 0 else stmt_text[start:]
    return (table_name_raw, body)


def _parse_table_name(raw: str) -> Tuple[str, str]:
    """
    Parse a raw table name into (schema, table).
    Handles: [Schema].[Table], "dbo"."Table", public.users, users
    """
    # Strip all brackets and quotes from each part
    def clean(s: str) -> str:
        return s.strip().strip("[]").strip('"').strip("'").strip("`").strip()

    parts = re.split(r"[.\[\]]", raw)
    parts = [clean(p) for p in parts if clean(p)]

    if len(parts) >= 2:
        return (parts[-2], parts[-1])
    elif len(parts) == 1:
        return ("public", parts[0])
    return ("public", raw.strip())


# ---------------------------------------------------------------------------
# Column / constraint splitting — top-level commas only
# ---------------------------------------------------------------------------

def _split_top_level(text: str) -> List[str]:
    """Split `text` on commas that are not inside parentheses."""
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# FK extraction helpers
# ---------------------------------------------------------------------------

_FK_INLINE_RE = re.compile(
    r"REFERENCES\s+(.+?)\s*\((.+?)\)",
    re.IGNORECASE,
)

_FK_CONSTRAINT_RE = re.compile(
    r"(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY\s*\((.+?)\)\s+REFERENCES\s+(.+?)\s*\((.+?)\)",
    re.IGNORECASE | re.DOTALL,
)

_PK_CONSTRAINT_RE = re.compile(
    r"(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*(?:CLUSTERED|NONCLUSTERED)?\s*\((.+?)\)",
    re.IGNORECASE | re.DOTALL,
)


def _clean_col_name(raw: str) -> str:
    """Strip quotes and brackets from a column name."""
    return raw.strip().strip("[]").strip('"').strip("'").strip("`").strip()


def _parse_fk_target(raw: str) -> str:
    """Extract just the table name from a REFERENCES target (strip schema prefix)."""
    parts = re.split(r"[.\[\]]", raw)
    parts = [p.strip().strip("[]").strip('"').strip("'").strip("`") for p in parts if p.strip()]
    parts = [p for p in parts if p]
    return parts[-1] if parts else raw.strip()


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def _strip_sql_comments(text: str) -> str:
    """
    Remove SQL comments (-- line comments and /* block comments */) using regex.
    Much faster than sqlparse.format() and avoids the 10K token limit on large files.
    """
    # Remove block comments /* ... */
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    # Remove line comments -- ...
    text = re.sub(r"--[^\n]*", " ", text)
    return text


def parse_ddl_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse CREATE TABLE statements from a SQL DDL file and return a SemanticSnapshot.

    Supports Postgres, T-SQL (SQL Server), and generic ANSI SQL.
    Handles: SERIAL/BIGSERIAL PKs, inline REFERENCES FKs, constraint-style PKs and FKs,
    composite PKs, NOT NULL, DEFAULT, quoted identifiers, T-SQL GO batch separators.

    Args:
        file_path: Path to a .sql file containing CREATE TABLE statements.

    Returns:
        SemanticSnapshot with entities (tables), fields (columns), and joins (FKs).
    """
    file_path = Path(file_path)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw_sql = f.read()

    # Strip T-SQL GO batch separators
    raw_sql = re.sub(r"\nGO\b", "\n;", raw_sql, flags=re.IGNORECASE)

    statements = sqlparse.split(raw_sql)

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    for stmt_text in statements:
        # Lightweight comment strip — avoid sqlparse.format() which can hit token limits
        # on large INSERT statements. We only need to detect CREATE TABLE.
        stripped = _strip_sql_comments(stmt_text).strip()
        if not re.match(r"CREATE\s+TABLE", stripped, re.IGNORECASE):
            continue

        table_name_raw, body = _extract_create_body(stripped)
        if not table_name_raw or not body:
            continue

        schema_name, table_name = _parse_table_name(table_name_raw)
        entity_id = f"entity:{table_name}"
        entity_fields: List[str] = []

        elements = _split_top_level(body)

        # --- First pass: collect PK columns from constraint lines ---
        pk_cols: Set[str] = set()
        # Also track columns with SERIAL/BIGSERIAL for implicit PK
        serial_cols: Set[str] = set()

        # Collect FK info for second pass
        fk_defs: List[Tuple[str, str, str]] = []  # (source_col, target_table, target_col)

        # Collect inline FK column names for field_type assignment
        fk_source_cols: Set[str] = set()

        for elem in elements:
            eu = elem.strip().upper()
            # Constraint: PRIMARY KEY
            if re.match(r"(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY", eu):
                m = _PK_CONSTRAINT_RE.search(elem)
                if m:
                    for col_part in m.group(1).split(","):
                        col = _clean_col_name(
                            re.sub(r"\s*(ASC|DESC)\s*", "", col_part, flags=re.IGNORECASE)
                        )
                        if col:
                            pk_cols.add(col)
                continue

            # Constraint: FOREIGN KEY
            if re.match(r"(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY", eu):
                m = _FK_CONSTRAINT_RE.search(elem)
                if m:
                    src_col = _clean_col_name(m.group(1).split(",")[0])
                    tgt_table = _parse_fk_target(m.group(2))
                    tgt_col = _clean_col_name(m.group(3).split(",")[0])
                    fk_defs.append((src_col, tgt_table, tgt_col))
                    fk_source_cols.add(src_col)
                continue

            # Skip other constraint/index types
            if re.match(r"(?:CONSTRAINT|UNIQUE|CHECK|INDEX)\b", eu):
                continue

            # Column definition
            # Split off leading column name and type
            parts = elem.strip().split()
            if not parts:
                continue
            col_name = _clean_col_name(parts[0])
            if not col_name:
                continue

            # Check SERIAL / BIGSERIAL
            if len(parts) >= 2:
                type_raw = parts[1].strip('"').upper()
                if type_raw in ("SERIAL", "BIGSERIAL"):
                    serial_cols.add(col_name)

            # Inline REFERENCES on this column
            fk_m = _FK_INLINE_RE.search(elem)
            if fk_m:
                tgt_table = _parse_fk_target(fk_m.group(1))
                tgt_col = _clean_col_name(fk_m.group(2).split(",")[0])
                fk_defs.append((col_name, tgt_table, tgt_col))
                fk_source_cols.add(col_name)

            # Inline PRIMARY KEY
            if re.search(r"\bPRIMARY\s+KEY\b", elem, re.IGNORECASE):
                pk_cols.add(col_name)

        # SERIAL columns without explicit PK keyword → implied PK
        if serial_cols and not pk_cols:
            pk_cols.update(serial_cols)
        elif serial_cols:
            pk_cols.update(serial_cols)

        # Determine grain
        if len(pk_cols) == 1:
            grain = next(iter(pk_cols))
        elif len(pk_cols) > 1:
            # Preserve declaration order
            grain = "_".join(
                col for col in [_clean_col_name(p.split()[0]) for p in elements
                                 if p.strip() and not re.match(
                                     r"(?:CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK|INDEX)\b",
                                     p.strip().upper()
                                 )]
                if col in pk_cols
            )
            if not grain:
                grain = "_".join(sorted(pk_cols))
        else:
            grain = "rowid"

        # --- Second pass: build FieldDef objects ---
        for elem in elements:
            eu = elem.strip().upper()
            if re.match(r"(?:CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|INDEX)\b", eu):
                continue

            parts = elem.strip().split()
            if len(parts) < 2:
                continue

            col_name = _clean_col_name(parts[0])
            if not col_name:
                continue

            # Extract data type — may span multiple tokens until modifier keyword
            type_tokens: List[str] = []
            idx = 1
            while idx < len(parts):
                tok = parts[idx].strip('"').upper()
                if tok in ("NOT", "NULL", "DEFAULT", "PRIMARY", "REFERENCES",
                           "UNIQUE", "CHECK", "CONSTRAINT", "IDENTITY",
                           "AUTOINCREMENT", "AUTO_INCREMENT", "COLLATE",
                           "GENERATED", "ALWAYS", "AS", "ON"):
                    break
                type_tokens.append(parts[idx])
                idx += 1

            raw_type = " ".join(type_tokens)
            # Collapse any paren-wrapped size that got split across tokens
            raw_type = re.sub(r"\s*\(\s*", "(", raw_type)
            raw_type = re.sub(r"\s*\)\s*", ")", raw_type)
            normalized_type = _normalize_ddl_type(raw_type)

            # Nullable — default True (SQL default); NOT NULL makes it False
            nullable = True
            remainder = " ".join(parts[idx:]).upper()
            if "NOT NULL" in remainder:
                nullable = False

            is_pk = col_name in pk_cols
            is_fk = col_name in fk_source_cols and not is_pk

            # Field type inference
            if is_pk:
                field_type = FieldType.ID
            elif is_fk:
                field_type = FieldType.FOREIGN_KEY
            elif normalized_type in ("TIMESTAMP", "DATE") or normalized_type.startswith("TIMESTAMP"):
                field_type = FieldType.TIMESTAMP
            elif any(normalized_type.startswith(p) for p in ("DECIMAL", "MONEY", "NUMERIC", "REAL", "DOUBLE")):
                name_lower = col_name.lower()
                if any(kw in name_lower for kw in (
                    "amount", "price", "total", "revenue", "cost",
                    "freight", "tax", "discount", "unit_price",
                )):
                    field_type = FieldType.MEASURE
                else:
                    field_type = FieldType.DIMENSION
            else:
                field_type = FieldType.DIMENSION

            field_id = f"field:{table_name}:{col_name}"
            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=col_name,
                field_type=field_type,
                data_type=normalized_type,
                nullable=nullable,
                primary_key=is_pk,
            )
            entity_fields.append(field_id)

        entities[entity_id] = Entity(
            id=entity_id,
            name=table_name,
            schema_name=schema_name,
            fields=entity_fields,
            grain=grain,
        )

        # --- Build JoinDefs ---
        join_target_counts: Dict[str, int] = {}
        for src_col, tgt_table, tgt_col in fk_defs:
            tgt_entity_id = f"entity:{tgt_table}"
            join_target_counts[tgt_table] = join_target_counts.get(tgt_table, 0) + 1
            count = join_target_counts[tgt_table]
            join_id = (
                f"join:{table_name}:{tgt_table}"
                if count == 1
                else f"join:{table_name}:{tgt_table}:{src_col}"
            )
            joins.append(JoinDef(
                id=join_id,
                source_entity_id=entity_id,
                target_entity_id=tgt_entity_id,
                join_type=JoinType.LEFT,
                source_field_id=f"field:{table_name}:{src_col}",
                target_field_id=f"field:{tgt_table}:{tgt_col}",
                description=f"FK: {table_name}.{src_col} -> {tgt_table}.{tgt_col}",
            ))

    return build_snapshot(
        source_system="ddl",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "source_file": str(file_path),
            "dialect": "auto",
            "table_count": len(entities),
        },
    )


class DDLParser:
    """SnapshotParser implementation for raw SQL DDL files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix == ".sql":
            try:
                with open(path) as f:
                    content = f.read(2000)
                if "CREATE TABLE" in content.upper():
                    return 0.85
            except Exception:
                pass
            return 0.3
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_ddl_file(Path(path))

    def source_type(self) -> str:
        return "ddl"
