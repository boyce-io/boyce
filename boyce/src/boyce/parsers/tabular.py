"""
CSV and Parquet tabular parsers.

CSV: stdlib csv module, type inference from sample rows. Zero new dependencies.
Parquet: pyarrow for metadata reading. Optional dependency.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    SemanticSnapshot,
)
from .base import build_snapshot

try:
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    _PYARROW_AVAILABLE = False
    pq = None  # type: ignore


# ---------------------------------------------------------------------------
# CSV type inference
# ---------------------------------------------------------------------------

_BOOLEAN_VALUES = frozenset(
    {"true", "false", "yes", "no", "1", "0", "t", "f"}
)


def _infer_column_type(values: List[str]) -> str:
    """Infer SQL type from a list of string values (non-empty)."""
    if not values:
        return "VARCHAR"
    # Most specific first
    lower = [v.strip().lower() for v in values]
    if all(v in _BOOLEAN_VALUES for v in lower):
        return "BOOLEAN"
    if all(re.match(r"^-?\d+$", v) for v in lower):
        return "INTEGER"
    if all(re.match(r"^-?\d+\.\d+$", v) for v in lower):
        return "DECIMAL"
    if all(re.match(r"^\d{4}-\d{2}-\d{2}$", v) for v in lower):
        return "DATE"
    if all(re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", v) for v in lower):
        return "TIMESTAMP"
    return "VARCHAR"


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_csv_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a CSV file into a SemanticSnapshot.

    One entity per file. Column names from header row.
    Types inferred from up to 100 sample rows.
    """
    file_path = Path(file_path)
    entity_name = file_path.stem
    entity_id = f"entity:{entity_name}"

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader)
        sample_rows: List[List[str]] = []
        for i, row in enumerate(reader):
            if i >= 100:
                break
            sample_rows.append(row)

    col_samples: Dict[int, List[str]] = {i: [] for i in range(len(header))}
    for row in sample_rows:
        for i, val in enumerate(row):
            if i < len(header) and val.strip():
                col_samples[i].append(val.strip())

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    entity_fields: List[str] = []

    for i, col_name in enumerate(header):
        col_name = col_name.strip()
        if not col_name:
            continue

        inferred_type = _infer_column_type(col_samples.get(i, []))

        name_lower = col_name.lower()
        is_id = name_lower == "id" or name_lower.endswith("_id")

        if is_id and i == 0:
            field_type = FieldType.ID
        elif is_id:
            field_type = FieldType.FOREIGN_KEY
        elif inferred_type in ("TIMESTAMP", "DATE"):
            field_type = FieldType.TIMESTAMP
        elif inferred_type in ("DECIMAL", "INTEGER") and any(
            kw in name_lower for kw in (
                "amount", "price", "total", "revenue", "cost", "tax", "discount"
            )
        ):
            field_type = FieldType.MEASURE
        else:
            field_type = FieldType.DIMENSION

        field_id = f"field:{entity_name}:{col_name}"
        fields[field_id] = FieldDef(
            id=field_id,
            entity_id=entity_id,
            name=col_name,
            field_type=field_type,
            data_type=inferred_type,
            nullable=True,
            primary_key=(is_id and i == 0),
        )
        entity_fields.append(field_id)

    first_col = header[0].strip().lower() if header else ""
    grain = header[0].strip() if (first_col == "id" or first_col.endswith("_id")) else "rownum"

    entities[entity_id] = Entity(
        id=entity_id,
        name=entity_name,
        schema_name="csv",
        fields=entity_fields,
        grain=grain,
    )

    return build_snapshot(
        source_system="csv",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=[],
        metadata={
            "source_file": str(file_path),
            "table_count": 1,
            "sample_rows": len(sample_rows),
        },
    )


class CSVParser:
    """SnapshotParser implementation for CSV files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix.lower() == ".csv":
            return 0.9
        if path.suffix.lower() == ".tsv":
            return 0.8
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_csv_file(Path(path))

    def source_type(self) -> str:
        return "csv"


# ---------------------------------------------------------------------------
# Parquet helpers (pyarrow)
# ---------------------------------------------------------------------------

def _arrow_type_to_sql(arrow_type) -> str:
    """Map PyArrow data type to normalized SQL type string."""
    import pyarrow as pa
    t = arrow_type
    if pa.types.is_boolean(t):
        return "BOOLEAN"
    if pa.types.is_int8(t) or pa.types.is_int16(t) or pa.types.is_int32(t) or pa.types.is_int64(t):
        return "INTEGER"
    if pa.types.is_uint8(t) or pa.types.is_uint16(t) or pa.types.is_uint32(t) or pa.types.is_uint64(t):
        return "INTEGER"
    if pa.types.is_float16(t) or pa.types.is_float32(t) or pa.types.is_float64(t):
        return "DOUBLE PRECISION"
    if pa.types.is_decimal(t):
        return f"DECIMAL({t.precision},{t.scale})"
    if pa.types.is_date(t):
        return "DATE"
    if pa.types.is_timestamp(t):
        return "TIMESTAMP"
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "VARCHAR"
    if pa.types.is_binary(t) or pa.types.is_large_binary(t):
        return "BYTEA"
    return "VARCHAR"


def parse_parquet_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a Parquet file into a SemanticSnapshot.

    Reads schema metadata only — does NOT load row data into memory.
    Requires pyarrow.
    """
    if not _PYARROW_AVAILABLE:
        raise ImportError(
            "pyarrow is required to parse Parquet files: pip install pyarrow"
        )

    file_path = Path(file_path)
    pf = pq.ParquetFile(file_path)
    schema = pf.schema_arrow
    num_rows = pf.metadata.num_rows

    entity_name = file_path.stem
    entity_id = f"entity:{entity_name}"

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    entity_fields: List[str] = []

    for i, field in enumerate(schema):
        col_name = field.name
        sql_type = _arrow_type_to_sql(field.type)
        name_lower = col_name.lower()
        is_id = name_lower == "id" or name_lower.endswith("_id")

        if is_id and i == 0:
            field_type = FieldType.ID
        elif is_id:
            field_type = FieldType.FOREIGN_KEY
        elif sql_type in ("TIMESTAMP", "DATE"):
            field_type = FieldType.TIMESTAMP
        elif sql_type in ("DOUBLE PRECISION", "DECIMAL") or (
            sql_type == "INTEGER" and any(
                kw in name_lower for kw in (
                    "amount", "price", "total", "revenue", "cost", "tax", "discount"
                )
            )
        ):
            field_type = FieldType.MEASURE
        else:
            field_type = FieldType.DIMENSION

        field_id = f"field:{entity_name}:{col_name}"
        fields[field_id] = FieldDef(
            id=field_id,
            entity_id=entity_id,
            name=col_name,
            field_type=field_type,
            data_type=sql_type,
            nullable=True,
            primary_key=(is_id and i == 0),
        )
        entity_fields.append(field_id)

    first_col = schema.field(0).name.lower() if schema else ""
    grain = (
        schema.field(0).name
        if (first_col == "id" or first_col.endswith("_id"))
        else "rownum"
    )

    entities[entity_id] = Entity(
        id=entity_id,
        name=entity_name,
        schema_name="parquet",
        fields=entity_fields,
        grain=grain,
    )

    return build_snapshot(
        source_system="parquet",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=[],
        metadata={
            "source_file": str(file_path),
            "table_count": 1,
            "num_rows": num_rows,
        },
    )


class ParquetParser:
    """SnapshotParser implementation for Parquet files."""

    def detect(self, path: Path) -> float:
        if not _PYARROW_AVAILABLE:
            return 0.0
        path = Path(path)
        if path.suffix.lower() == ".parquet":
            return 0.95
        if path.is_file():
            try:
                with open(path, "rb") as f:
                    magic = f.read(4)
                if magic == b"PAR1":
                    return 0.9
            except Exception:
                pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_parquet_file(Path(path))

    def source_type(self) -> str:
        return "parquet"
