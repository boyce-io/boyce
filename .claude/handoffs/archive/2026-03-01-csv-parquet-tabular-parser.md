# Handoff: CSV/Parquet Tabular Parser

**Created:** 2026-03-01
**Base commit:** 9ff77ed
**Branch:** main
**Mode:** Standard
**Cursor Model:** Auto/Composer
**Cursor Mode:** Agent

## Objective

Implement the third and final Tier 1 parser: CSV and Parquet file parsing. This completes the "three fundamentally different input types producing the same SemanticSnapshot" protocol story (DDL = schema definition, SQLite = live database, CSV/Parquet = raw data files). CSV uses zero external dependencies (stdlib `csv` module). Parquet uses `pyarrow` as an optional dependency.

## Current Baseline

- **102 tests passing** (`python -m pytest datashark-protocol/tests/ -v`)
- **5 parsers registered:** dbt_manifest, dbt_project, lookml, sqlite, ddl
- Parser plugin interface: `SnapshotParser` protocol in `parsers/base.py`
- `build_snapshot()` helper in `parsers/base.py` handles SHA-256 snapshot_id computation
- `ParserRegistry` in `parsers/registry.py` with lazy singleton `get_default_registry()`

## Files to Touch

- `datashark-protocol/datashark_protocol/parsers/tabular.py` — **NEW** — CSV and Parquet parsers
- `datashark-protocol/datashark_protocol/parsers/registry.py` — Register `CSVParser` and `ParquetParser`
- `datashark-protocol/datashark_protocol/parsers/__init__.py` — Export new symbols
- `datashark-protocol/pyproject.toml` — Add `[parquet]` optional dependency
- `datashark-protocol/tests/test_parsers.py` — Add ~25 new tests

## Approach

One file (`tabular.py`) with two parser classes following the established pattern:

1. **`CSVParser`** — stdlib only, zero new dependencies
   - Reads header row for column names
   - Samples up to 100 data rows for type inference
   - Produces one entity per CSV file (entity name = filename stem)

2. **`ParquetParser`** — requires `pyarrow` (optional dependency)
   - Reads Parquet metadata for column names and explicit types
   - No type inference needed (Parquet stores types natively)
   - Graceful `ImportError` handling — parser not registered if pyarrow absent

## Implementation Details

### `parsers/tabular.py`

```python
"""
CSV and Parquet tabular parsers.

CSV: stdlib csv module, type inference from sample rows. Zero new dependencies.
Parquet: pyarrow for metadata reading. Optional dependency.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from datashark_protocol.types import (
    Entity,
    FieldDef,
    FieldType,
    SemanticSnapshot,
)
from .base import build_snapshot
```

#### CSV Type Inference Logic

For each column, sample up to 100 non-empty values and try types in this order (most specific first):

1. **BOOLEAN** — all values in `{"true", "false", "yes", "no", "1", "0", "t", "f"}` (case-insensitive)
2. **INTEGER** — all values match `^-?\d+$`
3. **DECIMAL** — all values match `^-?\d+\.\d+$` (contains decimal point)
4. **DATE** — all values match `^\d{4}-\d{2}-\d{2}$`
5. **TIMESTAMP** — all values match `^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}` (date + time)
6. **VARCHAR** — fallback for everything else

Implement as a function:
```python
def _infer_column_type(values: List[str]) -> str:
    """Infer SQL type from a list of string values."""
```

Return the **normalized type string** (same format as DDL parser: `"INTEGER"`, `"DECIMAL"`, `"TIMESTAMP"`, `"DATE"`, `"BOOLEAN"`, `"VARCHAR"`).

#### `parse_csv_file(file_path: Path) -> SemanticSnapshot`

```python
def parse_csv_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a CSV file into a SemanticSnapshot.

    One entity per file. Column names from header row.
    Types inferred from up to 100 sample rows.
    """
    file_path = Path(file_path)
    entity_name = file_path.stem  # "raw_customers.csv" → "raw_customers"
    entity_id = f"entity:{entity_name}"

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Sample up to 100 rows for type inference
        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 100:
                break
            sample_rows.append(row)

    # Build column samples (transpose rows → columns)
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

        # FieldType inference (same heuristics as DDL/SQLite parsers)
        name_lower = col_name.lower()
        is_id = name_lower == "id" or name_lower.endswith("_id")

        if is_id and i == 0:
            field_type = FieldType.ID
        elif is_id:
            field_type = FieldType.FOREIGN_KEY
        elif inferred_type in ("TIMESTAMP", "DATE"):
            field_type = FieldType.TIMESTAMP
        elif inferred_type in ("DECIMAL", "INTEGER") and any(
            kw in name_lower for kw in ("amount", "price", "total", "revenue", "cost", "tax", "discount")
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
            nullable=True,  # CSV has no NOT NULL constraint
            primary_key=(is_id and i == 0),
        )
        entity_fields.append(field_id)

    # Grain: first column if it's an ID, else "rownum"
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
        joins=[],  # CSV files have no FK relationships
        metadata={
            "source_file": str(file_path),
            "table_count": 1,
            "sample_rows": len(sample_rows),
        },
    )
```

#### `CSVParser` class

```python
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
```

#### Parquet Parser

```python
try:
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    _PYARROW_AVAILABLE = False
```

Type mapping from PyArrow types to normalized SQL types:
```python
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
    return "VARCHAR"  # fallback
```

```python
def parse_parquet_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a Parquet file into a SemanticSnapshot.

    Reads schema metadata only — does NOT load row data into memory.
    Requires pyarrow.
    """
    if not _PYARROW_AVAILABLE:
        raise ImportError("pyarrow is required to parse Parquet files: pip install pyarrow")

    file_path = Path(file_path)
    pf = pq.ParquetFile(file_path)
    schema = pf.schema_arrow
    num_rows = pf.metadata.num_rows

    entity_name = file_path.stem
    entity_id = f"entity:{entity_name}"

    # ... build entities/fields using schema column names and _arrow_type_to_sql()
    # Same FieldType heuristics as CSV parser
    # grain: first column if it looks like an ID, else "rownum"

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
```

```python
class ParquetParser:
    """SnapshotParser implementation for Parquet files."""

    def detect(self, path: Path) -> float:
        if not _PYARROW_AVAILABLE:
            return 0.0
        path = Path(path)
        if path.suffix.lower() == ".parquet":
            return 0.95
        # Check magic bytes: PAR1
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
```

### `parsers/registry.py` Changes

In `get_default_registry()`, add after the DDLParser registration:

```python
from .tabular import CSVParser
_default_registry.register(CSVParser())
try:
    from .tabular import ParquetParser, _PYARROW_AVAILABLE
    if _PYARROW_AVAILABLE:
        _default_registry.register(ParquetParser())
except Exception:
    pass  # pyarrow not installed — Parquet parser simply not available
```

### `parsers/__init__.py` Changes

Add imports and exports:
```python
from .tabular import parse_csv_file, CSVParser
try:
    from .tabular import parse_parquet_file, ParquetParser
except ImportError:
    pass
```

Add to `__all__`:
```python
"CSVParser",
"parse_csv_file",
"ParquetParser",      # only available if pyarrow installed
"parse_parquet_file",  # only available if pyarrow installed
```

### `pyproject.toml` Changes

Add optional dependency:
```toml
[project.optional-dependencies]
postgres = ["asyncpg>=0.29.0"]
parquet = ["pyarrow>=14.0.0"]
```

### Test Fixtures

Use existing jaffle_shop seed CSVs — no new fixtures needed:
- `test_warehouses/jaffle_shop/seeds/raw_customers.csv` — 100 rows, 3 columns (id, first_name, last_name)
- `test_warehouses/jaffle_shop/seeds/raw_orders.csv` — 99 rows, 4 columns (id, user_id, order_date, status)
- `test_warehouses/jaffle_shop/seeds/raw_payments.csv` — 113 rows, 4 columns (id, order_id, payment_method, amount)

For Parquet tests: create a temporary Parquet file programmatically in the test using pyarrow (skip if pyarrow not installed).

### Tests to Add (~25 new tests)

Add to `datashark-protocol/tests/test_parsers.py`:

```python
# Top of file — add imports:
from datashark_protocol.parsers import parse_csv_file, CSVParser

JAFFLE_CUSTOMERS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds" / "raw_customers.csv"
JAFFLE_ORDERS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds" / "raw_orders.csv"
JAFFLE_PAYMENTS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds" / "raw_payments.csv"
```

**CSV Parser Tests — `TestCSVCustomers` class:**
1. `test_returns_semantic_snapshot` — isinstance check
2. `test_one_entity` — single entity per file
3. `test_entity_name_from_filename` — entity name = "raw_customers"
4. `test_field_count` — 3 fields (id, first_name, last_name)
5. `test_id_field_is_pk` — field:raw_customers:id has primary_key=True, field_type=ID
6. `test_id_type_inferred_as_integer` — data_type = "INTEGER" (all values are ints)
7. `test_string_fields` — first_name and last_name are VARCHAR
8. `test_grain_is_id` — grain = "id"
9. `test_deterministic_id` — parse twice, same snapshot_id
10. `test_source_system` — source_system = "csv"
11. `test_no_joins` — CSV files produce zero joins

**CSV Parser Tests — `TestCSVOrders` class:**
12. `test_date_type_inferred` — order_date column → DATE type
13. `test_user_id_is_foreign_key` — user_id field has field_type=FOREIGN_KEY
14. `test_status_is_dimension` — status field has field_type=DIMENSION

**CSV Parser Tests — `TestCSVPayments` class:**
15. `test_amount_is_measure` — amount column → MEASURE field_type (name heuristic + integer type)
16. `test_payment_method_is_dimension` — payment_method → DIMENSION

**Plugin interface tests:**
17. `test_csv_parser_implements_protocol` — isinstance(CSVParser(), SnapshotParser)
18. `test_csv_parser_detect_csv` — CSVParser().detect(Path("data.csv")) > 0.0
19. `test_csv_parser_detect_non_csv` — CSVParser().detect(Path("README.md")) == 0.0
20. `test_registry_includes_csv` — "csv" in get_default_registry().registered_types
21. `test_detect_source_type_csv` — detect_source_type(file_path=JAFFLE_CUSTOMERS) == "csv"

**Parquet tests (all skipif pyarrow not installed):**
22. `test_parquet_parser_implements_protocol` — isinstance check
23. `test_parquet_parse_roundtrip` — create temp Parquet from CSV data, parse it, verify entity/fields
24. `test_parquet_types_preserved` — int/float/string types from Parquet metadata map correctly
25. `test_parquet_detect` — ParquetParser().detect(Path("data.parquet")) > 0.0

## Verification

After implementation, run:

1. `python -m pytest datashark-protocol/tests/test_parsers.py -v` — expect ~127 tests (102 existing + ~25 new), all passing
2. `python datashark-protocol/tests/verify_eyes.py` — still 15 passing (no regressions)
3. Verify CSV fixtures parse without error:
   ```python
   from datashark_protocol.parsers import parse_csv_file
   from pathlib import Path
   snap = parse_csv_file(Path("test_warehouses/jaffle_shop/seeds/raw_customers.csv"))
   print(f"Entities: {len(snap.entities)}, Fields: {len(snap.fields)}")
   # Should print: Entities: 1, Fields: 3
   ```

## Escalation

If any verification check fails after TWO fix attempts:
1. STOP. Do not keep iterating.
2. Write `.claude/handoffs/RETURN.md` with:
   - Which spec item you were executing
   - What you tried (both attempts)
   - Exact error output / test failures
   - Your assessment of why it failed
3. Commit your partial work to a branch so nothing is lost.

## Scope Boundaries — Do NOT

- Do not modify any existing parser files (dbt.py, lookml.py, sqlite.py, ddl.py)
- Do not modify server.py (parse_from_path already delegates to registry — no changes needed)
- Do not modify detect.py (already delegates to registry)
- Do not add pandas as a dependency (use stdlib csv for CSV, pyarrow for Parquet)
- Do not attempt to infer joins between multiple CSV files (each file is a standalone entity)
- Do not load full Parquet data into memory — read schema metadata only
