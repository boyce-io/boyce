# Handoff: SQLite Direct Introspection Parser
**Created:** 2026-02-28
**Base commit:** (use HEAD when starting — DDL handoff should be complete first)
**Branch:** main
**Mode:** Standard
**Cursor Model:** Sonnet 4.6
**Cursor Mode:** Agent

## Objective
Implement a parser that introspects SQLite database files (`.sqlite`, `.db`) directly via the stdlib `sqlite3` module. No external dependencies. This is the second Tier 1 parser — it demonstrates the protocol working with a fundamentally different input type (live database file vs. text source code).

## Prerequisites
- DDL parser handoff complete (parsers/ddl.py exists, registry updated, detect_source_type delegates to registry, snapshot_name cleanup done)
- All tests passing

## Files to Touch
- `parsers/sqlite.py` — **NEW** — SQLite introspection parser + `SQLiteParser` class
- `parsers/registry.py` — register `SQLiteParser` in `get_default_registry()`
- `parsers/__init__.py` — export `parse_sqlite_file`, `SQLiteParser`
- `tests/test_parsers.py` — SQLite parser tests (fixture created in test setup via stdlib)

All file paths relative to `datashark-protocol/datashark_protocol/` unless noted.

## Approach

SQLite is unique among our parsers: instead of parsing source text, we open a live database file and introspect its schema using PRAGMAs. This is faster and more reliable than parsing DDL — we get the schema exactly as SQLite understands it. Zero external dependencies since `sqlite3` is part of the Python standard library.

## Implementation Details

### 1. SQLite Parser (`parsers/sqlite.py`)

```python
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

from datashark_protocol.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from .base import build_snapshot
```

**Core function: `parse_sqlite_file(file_path: Path) -> SemanticSnapshot`**

Step-by-step logic:

1. **Connect read-only:**
   ```python
   conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
   ```
   Use URI mode with `?mode=ro` to enforce read-only access. Wrap in try/finally to always close.

2. **Get table list from sqlite_master:**
   ```python
   cursor = conn.execute(
       "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
   )
   table_names = [row[0] for row in cursor.fetchall()]
   ```
   Filter out SQLite internal tables (`sqlite_sequence`, `sqlite_stat1`, etc.).

3. **For each table, get columns via PRAGMA:**
   ```python
   columns = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
   ```
   Each row returns: `(cid, name, type, notnull, dflt_value, pk)`
   - `cid`: column index
   - `name`: column name
   - `type`: declared type (may be empty — SQLite is dynamically typed)
   - `notnull`: 1 if NOT NULL, 0 otherwise
   - `dflt_value`: default value or None
   - `pk`: >0 if part of primary key (1-based index for composite PKs)

4. **For each table, get foreign keys via PRAGMA:**
   ```python
   fks = conn.execute(f"PRAGMA foreign_key_list('{table_name}')").fetchall()
   ```
   Each row returns: `(id, seq, table, from, to, on_update, on_delete, match)`
   - `id`: FK constraint id (groups multi-column FKs)
   - `seq`: column sequence within the FK
   - `table`: referenced table name
   - `from`: source column name
   - `to`: target column name

5. **Build entities, fields, joins:**

   For each table:
   - Create `Entity` with `id=f"entity:{table_name}"`, `schema_name="main"` (SQLite default schema)
   - Determine grain from PK columns (where `pk > 0`):
     - Single PK: `grain = pk_column_name`
     - Composite: `grain = "col1_col2"`
     - No PK: `grain = "rowid"` (SQLite always has an implicit rowid)

   For each column:
   - Create `FieldDef` with normalized data type
   - `nullable = not notnull` (invert the notnull flag)
   - `primary_key = pk > 0`

   **SQLite type normalization** (SQLite types are loose — normalize to standard SQL):

   | SQLite declared type | Output |
   |---------------------|--------|
   | `INTEGER`, `INT`, `BIGINT`, `SMALLINT`, `TINYINT`, `MEDIUMINT` | `INTEGER` |
   | `TEXT`, `CLOB`, `CHARACTER(N)`, `VARCHAR(N)`, `VARYING CHARACTER(N)`, `NCHAR(N)`, `NVARCHAR(N)`, `NATIVE CHARACTER(N)` | `TEXT` (or `VARCHAR(N)` if length specified) |
   | `REAL`, `DOUBLE`, `DOUBLE PRECISION`, `FLOAT` | `REAL` |
   | `BLOB`, (empty type) | `BLOB` |
   | `NUMERIC`, `DECIMAL(N,M)` | `DECIMAL(N,M)` or `NUMERIC` |
   | `BOOLEAN` | `BOOLEAN` |
   | `DATE` | `DATE` |
   | `DATETIME`, `TIMESTAMP` | `TIMESTAMP` |
   | (empty string) | `BLOB` (SQLite default affinity) |

   **Field type inference:**
   - `pk > 0` → `FieldType.ID`
   - Column participates in an FK (as source) → `FieldType.FOREIGN_KEY`
   - Type is `TIMESTAMP` / `DATETIME` / `DATE`, or name contains `_at`, `_date`, `timestamp` → `FieldType.TIMESTAMP`
   - Type is `DECIMAL` / `REAL` / `NUMERIC` AND name contains amount/price/total/revenue/cost → `FieldType.MEASURE`
   - Everything else → `FieldType.DIMENSION`

   For each FK:
   - Create `JoinDef`:
     - `id`: `join:{source_table}:{target_table}` — disambiguate with `:{source_col}` if multiple FKs to same target
     - `join_type`: `JoinType.LEFT`
     - `description`: `SQLite FK: {source_table}.{from_col} -> {target_table}.{to_col}`
   - Multi-column FKs (same `id`, multiple `seq` values): use the first column pair for the join (this is a simplification — multi-column FKs are rare in SQLite)

6. **Build and return snapshot:**
   ```python
   return build_snapshot(
       source_system="sqlite",
       source_version=sqlite3.sqlite_version,  # e.g. "3.39.0"
       entities=entities,
       fields=fields,
       joins=joins,
       metadata={
           "source_file": str(file_path),
           "table_count": len(entities),
           "sqlite_version": sqlite3.sqlite_version,
       },
   )
   ```

**SQLiteParser class:**
```python
class SQLiteParser:
    """SnapshotParser implementation for SQLite database files."""

    EXTENSIONS = {".sqlite", ".db", ".sqlite3", ".db3", ".s3db", ".sl3"}

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix.lower() in self.EXTENSIONS:
            # Verify it's actually a SQLite file by checking the magic bytes
            try:
                with open(path, "rb") as f:
                    header = f.read(16)
                if header[:16] == b"SQLite format 3\x00":
                    return 0.95
            except Exception:
                pass
            return 0.4  # Right extension but can't verify header
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_sqlite_file(Path(path))

    def source_type(self) -> str:
        return "sqlite"
```

Key design choice: `detect()` checks the SQLite file magic bytes (`SQLite format 3\0` — first 16 bytes of any valid SQLite file). This gives high confidence even for files with unusual extensions. Returns 0.95 for confirmed SQLite files, 0.4 for right extension but unverifiable, 0.0 for other extensions.

### 2. Registry Update (`parsers/registry.py`)

Add to `get_default_registry()`:
```python
from .sqlite import SQLiteParser
_default_registry.register(SQLiteParser())
```

### 3. `parsers/__init__.py` Update

Add imports:
```python
from .sqlite import parse_sqlite_file, SQLiteParser
```

Add to `__all__`:
```python
"parse_sqlite_file",
"SQLiteParser",
```

### 4. Tests (`tests/test_parsers.py`)

The test fixture is a SQLite database created in `setup_method` — no binary files committed to git. Use `tmp_path` pytest fixture or `tempfile`.

Add imports at top:
```python
import sqlite3
import tempfile
from datashark_protocol.parsers import parse_sqlite_file, SQLiteParser
```

**Helper to create test fixture:**
```python
def _create_test_sqlite(db_path: Path) -> Path:
    """Create a small SQLite database for testing."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            price DECIMAL(10,2) NOT NULL,
            stock_count INTEGER DEFAULT 0
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_amount DECIMAL(10,2) NOT NULL,
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE order_items (
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price DECIMAL(10,2) NOT NULL,
            PRIMARY KEY (order_id, product_id)
        );
    """)
    conn.close()
    return db_path
```

**Test class:**
```python
class TestSQLiteParser:
    """SQLite introspection parser tests."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.sqlite"
        _create_test_sqlite(self._db_path)
        self.snap = parse_sqlite_file(self._db_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_four_entities(self):
        assert len(self.snap.entities) == 4

    def test_entity_names(self):
        names = {e.name for e in self.snap.entities.values()}
        assert names == {"customers", "products", "orders", "order_items"}

    def test_customer_fields(self):
        entity = self.snap.entities["entity:customers"]
        field_names = {self.snap.fields[fid].name for fid in entity.fields}
        assert "id" in field_names
        assert "name" in field_names
        assert "email" in field_names
        assert "created_at" in field_names

    def test_primary_key_detected(self):
        pk_field = self.snap.fields["field:customers:id"]
        assert pk_field.primary_key is True
        assert pk_field.field_type == FieldType.ID

    def test_composite_pk(self):
        entity = self.snap.entities["entity:order_items"]
        assert "order_id" in entity.grain
        assert "product_id" in entity.grain

    def test_foreign_keys_extracted(self):
        join_targets = {j.target_entity_id for j in self.snap.joins}
        assert "entity:customers" in join_targets
        assert "entity:products" in join_targets
        assert "entity:orders" in join_targets

    def test_fk_count(self):
        """3 FK relationships: orders→customers, order_items→orders, order_items→products."""
        assert len(self.snap.joins) == 3

    def test_nullable_detection(self):
        name_field = self.snap.fields["field:customers:name"]
        assert name_field.nullable is False
        category = self.snap.fields["field:products:category"]
        assert category.nullable is True

    def test_timestamp_field_type(self):
        created = self.snap.fields["field:customers:created_at"]
        assert created.field_type == FieldType.TIMESTAMP

    def test_measure_field_type(self):
        total = self.snap.fields["field:orders:total_amount"]
        assert total.field_type == FieldType.MEASURE

    def test_deterministic_id(self):
        snap2 = parse_sqlite_file(self._db_path)
        assert snap2.snapshot_id == self.snap.snapshot_id

    def test_source_system(self):
        assert self.snap.source_system == "sqlite"

    def test_metadata_has_table_count(self):
        assert self.snap.metadata["table_count"] == 4

    def test_read_only_access(self):
        """Parsing should not modify the database."""
        import os
        mtime_before = os.path.getmtime(self._db_path)
        parse_sqlite_file(self._db_path)
        mtime_after = os.path.getmtime(self._db_path)
        assert mtime_before == mtime_after
```

**Plugin interface tests:**
```python
def test_sqlite_parser_implements_protocol():
    from datashark_protocol.parsers import SQLiteParser, SnapshotParser
    parser = SQLiteParser()
    assert isinstance(parser, SnapshotParser)

def test_sqlite_parser_detect_sqlite_extension():
    parser = SQLiteParser()
    # Can't verify magic bytes on a non-existent file, but extension match gives 0.4
    assert parser.detect(Path("data.sqlite")) > 0.0
    assert parser.detect(Path("data.db")) > 0.0
    assert parser.detect(Path("data.sqlite3")) > 0.0

def test_sqlite_parser_detect_non_sqlite():
    parser = SQLiteParser()
    assert parser.detect(Path("schema.sql")) == 0.0
    assert parser.detect(Path("README.md")) == 0.0

def test_sqlite_parser_detect_real_file(self):
    """detect() returns 0.95 for a real SQLite file (magic bytes verified)."""
    # Uses the fixture from TestSQLiteParser setup
    parser = SQLiteParser()
    assert parser.detect(self._db_path) == 0.95

def test_registry_includes_sqlite():
    from datashark_protocol.parsers import get_default_registry
    registry = get_default_registry()
    assert "sqlite" in registry.registered_types
```

**IMPORTANT:** The `test_sqlite_parser_detect_real_file` test needs access to a real .sqlite file. Either make it a method on `TestSQLiteParser` class (so it has `self._db_path`), or create a standalone fixture. Choose whichever is cleaner — the key is that one test verifies the magic-byte detection path returns 0.95.

## Verification

1. `python datashark-protocol/tests/verify_eyes.py` — expected: 15 tests pass
2. `python -m pytest datashark-protocol/tests/test_parsers.py -v` — expected: all pass
3. `python -m pytest datashark-protocol/tests/ -v` — expected: full suite passes
4. Import check: `python -c "from datashark_protocol.parsers import SQLiteParser, parse_sqlite_file; print('OK')"`
5. Smoke test (creates a temp DB, parses it, verifies):
   ```bash
   python -c "
   import sqlite3, tempfile
   from pathlib import Path
   from datashark_protocol.parsers import parse_sqlite_file

   db = Path(tempfile.mktemp(suffix='.sqlite'))
   conn = sqlite3.connect(str(db))
   conn.executescript('''
       CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
       CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), title TEXT);
   ''')
   conn.close()

   snap = parse_sqlite_file(db)
   print(f'Entities: {len(snap.entities)}, Fields: {len(snap.fields)}, Joins: {len(snap.joins)}')
   assert len(snap.entities) == 2
   assert len(snap.joins) == 1
   db.unlink()
   print('PASS')
   "
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
- Touch `server.py`, `types.py`, `kernel.py`, `graph.py`, `safety.py`, or any SQL builder files
- Add any external dependencies — sqlite3 is stdlib only
- Implement any other parser (Django, SQLAlchemy, etc.)
- Modify existing parser logic (dbt, LookML, DDL)
- Add async support
- Change `build_snapshot()` hashing logic
- Touch `verify_eyes.py`
- Write data to the SQLite file being parsed — read-only access only
