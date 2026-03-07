# Handoff: Raw DDL Parser + Interface Cleanup
**Created:** 2026-02-28
**Base commit:** 9ff77ed
**Branch:** main
**Mode:** Standard
**Cursor Model:** Sonnet 4.6 Thinking
**Cursor Mode:** Agent

## Objective
Implement a DDL parser that extracts SemanticSnapshot from raw `CREATE TABLE` SQL files. This is the first Tier 1 parser — universal format, zero new dependencies (`sqlparse` is already installed). While building it, clean up two minor interface issues from the previous handoff: remove the dead `snapshot_name` parameter from the parse path, and refactor `detect_source_type()` to delegate to the registry for file-path detection.

## Files to Touch
- `parsers/ddl.py` — **NEW** — DDL parser + `DDLParser` class
- `parsers/registry.py` — register `DDLParser`, remove dead `snapshot_name` param from `parse()`, add `reset_default_registry()`
- `parsers/detect.py` — refactor `detect_source_type()` to delegate to registry for file paths; remove `snapshot_name` from `parse_from_path()`
- `parsers/__init__.py` — export `DDLParser`, `parse_ddl_file`, `reset_default_registry`
- `server.py` — update `parse_from_path()` call on line 289 (remove `snapshot_name` arg)
- `tests/test_parsers.py` — DDL parser tests + cleanup validation
- `test_warehouses/postgres_ddl/ecommerce.sql` — **NEW** — synthetic Postgres DDL fixture

All file paths are relative to `datashark-protocol/datashark_protocol/` unless noted otherwise (test_warehouses is at repo root).

## Approach

### Why sqlparse
`sqlparse` is already in `pyproject.toml` and used by `safety.py`. It handles statement splitting and tokenization. We use it for splitting multi-statement files and identifying `CREATE TABLE` statements, then use targeted regex to extract column definitions and constraints from within each statement body. No new dependencies.

### Why clean up now
The DDL parser is the first parser built from scratch on the plugin interface. Cleaning the dead parameter and duplicated detection logic now means every subsequent parser (SQLite, Django, SQLAlchemy, Prisma, etc.) builds on a tight foundation.

## Implementation Details

### 1. DDL Parser (`parsers/ddl.py`)

Core function: `parse_ddl_file(file_path: Path) -> SemanticSnapshot`

**Statement splitting:**
- Read the file, strip T-SQL `GO` batch separators (replace `\nGO\n` and `\ngo\n` with `\n;\n`)
- Use `sqlparse.split()` to split into individual statements
- Filter to statements starting with `CREATE TABLE` (case-insensitive, after stripping comments/whitespace)
- Skip everything else (`CREATE VIEW`, `CREATE INDEX`, `INSERT INTO`, `ALTER TABLE`, `SET`, `IF EXISTS`, stored procedures, etc.)

**Table name extraction from each CREATE TABLE statement:**
- Pattern: `CREATE TABLE [IF NOT EXISTS] <name> (`
- Handle bracket notation: `[Fact].[Order]` → schema=`Fact`, name=`Order`
- Handle double-quote notation: `"dbo"."Employees"` → schema=`dbo`, name=`Employees`
- Handle dot notation: `public.users` → schema=`public`, name=`users`
- Handle unqualified: `users` → schema=`public` (default), name=`users`
- Strip all quotes/brackets from final names
- Suggested regex: `CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(.+?)\s*\(`

**Column extraction (from the parenthesized body of CREATE TABLE):**
- Extract everything between the first `(` after the table name and the matching `)` — must respect nested parens
- Split by top-level commas (respect paren nesting for things like `DECIMAL(10,2)`)
- For each element, classify as either a column definition or a constraint:
  - **Constraint line**: starts with `CONSTRAINT`, `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK`, `INDEX` (case-insensitive, after stripping whitespace)
  - **Column line**: everything else — extract `column_name data_type [modifiers]`
- For column lines:
  - First token = column name (strip quotes/brackets)
  - Second token(s) = data type (may include size like `VARCHAR(100)` or `DECIMAL(10,2)`)
  - Scan remainder for: `NOT NULL`, `NULL`, `PRIMARY KEY` (inline), `REFERENCES` (inline FK), `DEFAULT`, `IDENTITY`, `SERIAL`/`BIGSERIAL`
  - Handle T-SQL quoted types: `"int"`, `"datetime"`, `"money"`, `"bit"`, `"image"`, `"ntext"` — strip quotes

**Data type normalization:**

| Input | Output |
|-------|--------|
| `nvarchar(N)`, `varchar(N)`, `character varying(N)` | `VARCHAR(N)` |
| `"int"`, `integer`, `int4`, `int` | `INTEGER` |
| `"smallint"`, `int2` | `SMALLINT` |
| `"bigint"`, `int8` | `BIGINT` |
| `serial` | `INTEGER` (also infer PK) |
| `bigserial` | `BIGINT` (also infer PK) |
| `"datetime"`, `timestamp`, `datetime2(N)`, `timestamp without time zone` | `TIMESTAMP` |
| `date` | `DATE` |
| `"money"` | `DECIMAL(19,4)` |
| `decimal(N,M)`, `numeric(N,M)` | `DECIMAL(N,M)` |
| `"bit"`, `boolean`, `bool` | `BOOLEAN` |
| `"ntext"`, `text` | `TEXT` |
| `"image"`, `bytea` | `BYTEA` |
| `nchar(N)`, `char(N)`, `character(N)` | `CHAR(N)` |
| `real`, `float4` | `REAL` |
| `double precision`, `float8` | `DOUBLE PRECISION` |
| Unknown | keep as-is, uppercase |

**Primary key extraction:**
- Inline: `column_name type PRIMARY KEY` → mark column `primary_key=True`
- `SERIAL` / `BIGSERIAL` type → infer `primary_key=True`
- Named constraint: `CONSTRAINT "PK_xxx" PRIMARY KEY [CLUSTERED|NONCLUSTERED] (col1 [ASC|DESC], col2 [ASC|DESC])` → mark those columns, ignore CLUSTERED/NONCLUSTERED and ASC/DESC
- Also handle un-named: `PRIMARY KEY (col1, col2)`
- For PK partition specs like `ON [PS_Date] ([Date Key])` — ignore the ON clause
- Composite PKs: grain = `col1_col2`

**Foreign key extraction → JoinDef:**
- Named constraint: `CONSTRAINT "FK_xxx" FOREIGN KEY (col) REFERENCES [schema]."table" (col)`
- Inline on column: `col_name type REFERENCES table(col)` or `REFERENCES table (col)`
- For each FK, create a `JoinDef`:
  - `id`: `join:<source_table>:<target_table>` — but if multiple FKs point to the same target (e.g., `Picker Key` and `Salesperson Key` both → `Employee`), disambiguate: `join:<source>:<target>:<source_col>`
  - `source_entity_id`: `entity:<source_table>`
  - `target_entity_id`: `entity:<target_table>`
  - `join_type`: `JoinType.LEFT`
  - `source_field_id`: `field:<source_table>:<source_col>`
  - `target_field_id`: `field:<target_table>:<target_col>`
  - `description`: `FK: <source_table>.<source_col> -> <target_table>.<target_col>`
- Strip schema prefixes from target table name (e.g., `"dbo"."Customers"` → `Customers`, `[Dimension].[Customer]` → `Customer`)

**Field type inference:**
- PK column → `FieldType.ID`
- Column participating in a FK (as source) → `FieldType.FOREIGN_KEY`
- TIMESTAMP/DATETIME/DATE type → `FieldType.TIMESTAMP`
- DECIMAL/MONEY type AND name contains amount/price/total/revenue/cost/freight/tax/discount/unit_price → `FieldType.MEASURE`
- Everything else → `FieldType.DIMENSION`

**Build snapshot:**
```python
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
```

**DDLParser class:**
```python
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
            return 0.3  # .sql file — might have CREATE TABLE later
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_ddl_file(Path(path))

    def source_type(self) -> str:
        return "ddl"
```

### 2. Registry Cleanup (`parsers/registry.py`)

**Remove dead `snapshot_name` parameter:**
```python
# BEFORE (line 37):
def parse(self, path: Path, snapshot_name: str = "default") -> SemanticSnapshot:

# AFTER:
def parse(self, path: Path) -> SemanticSnapshot:
```

**Register DDLParser in `get_default_registry()`:**
```python
def get_default_registry() -> ParserRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ParserRegistry()
        from .dbt import DbtManifestParser, DbtProjectParser
        from .lookml import LookMLParser
        from .ddl import DDLParser
        _default_registry.register(DbtManifestParser())
        _default_registry.register(DbtProjectParser())
        _default_registry.register(LookMLParser())
        _default_registry.register(DDLParser())
    return _default_registry
```

**Add `reset_default_registry()` for test isolation:**
```python
def reset_default_registry() -> None:
    """Reset the default registry. Useful for testing."""
    global _default_registry
    _default_registry = None
```

### 3. detect_source_type Refactor (`parsers/detect.py`)

**Remove `snapshot_name` from `parse_from_path`:**
```python
# BEFORE:
def parse_from_path(source_path: str | Path, snapshot_name: str = "default") -> SemanticSnapshot:
    from .registry import get_default_registry
    path = Path(source_path)
    return get_default_registry().parse(path, snapshot_name)

# AFTER:
def parse_from_path(source_path: str | Path) -> SemanticSnapshot:
    from .registry import get_default_registry
    path = Path(source_path)
    return get_default_registry().parse(path)
```

**Refactor `detect_source_type` to delegate to registry for file paths:**
```python
def detect_source_type(
    file_path: Optional[Path] = None,
    source_text: Optional[str] = None,
) -> str:
    """
    Detect ingestion source type from path or content.
    Returns one of: "dbt_manifest", "dbt_project", "lookml", "ddl", "unknown".
    """
    if file_path:
        from .registry import get_default_registry
        path = Path(file_path)
        candidates = get_default_registry().detect(path)
        if candidates:
            return candidates[0][0].source_type()
        return "unknown"

    # Text-based detection — no registry support, inline logic
    if source_text:
        if '"nodes"' in source_text and '"sources"' in source_text:
            return "dbt_manifest"
        if "view:" in source_text or "explore:" in source_text:
            return "lookml"
        if "CREATE TABLE" in source_text.upper() or "CREATE VIEW" in source_text.upper():
            return "ddl"
        if "name:" in source_text and "models:" in source_text:
            return "dbt_project"

    return "unknown"
```

### 4. server.py Update

Line 289 only — remove `snapshot_name` from `parse_from_path` call:
```python
# BEFORE:
snapshot = parse_from_path(source_path, snapshot_name)

# AFTER:
snapshot = parse_from_path(source_path)
```

`snapshot_name` is still in scope and correctly used on line 296: `_store.save(snapshot, snapshot_name)`. Only the parse call changes.

### 5. `parsers/__init__.py` Update

Add imports:
```python
from .ddl import parse_ddl_file, DDLParser
from .registry import ParserRegistry, get_default_registry, reset_default_registry
```

Add to `__all__`:
```python
"parse_ddl_file",
"DDLParser",
"reset_default_registry",
```

### 6. Synthetic Postgres DDL Fixture

Create file `test_warehouses/postgres_ddl/ecommerce.sql`:

```sql
-- Synthetic e-commerce schema (Postgres dialect)
-- 5 tables, 5 FK relationships, 1 composite PK
-- Tests: SERIAL, VARCHAR, TIMESTAMP, DECIMAL, TEXT, BOOLEAN
-- Tests: inline REFERENCES, composite PRIMARY KEY, NOT NULL, DEFAULT, CHECK

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10,2) NOT NULL,
    stock_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TIMESTAMP NOT NULL DEFAULT NOW(),
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 7. Tests (`tests/test_parsers.py`)

Add imports at top:
```python
from datashark_protocol.parsers import parse_ddl_file, DDLParser
```

Add fixture paths:
```python
POSTGRES_DDL = REPO_ROOT / "test_warehouses" / "postgres_ddl" / "ecommerce.sql"
NORTHWIND_DDL = REPO_ROOT / "test_warehouses" / "northwind_ddl" / "northwind.sql"
```

**Postgres DDL tests (always available — committed fixture):**

```python
class TestPostgresDDL:
    """DDL parser against synthetic Postgres fixture."""

    def setup_method(self):
        self.snap = parse_ddl_file(POSTGRES_DDL)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_five_entities(self):
        assert len(self.snap.entities) == 5

    def test_entity_names(self):
        names = {e.name for e in self.snap.entities.values()}
        assert names == {"customers", "products", "orders", "order_items", "reviews"}

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
        """order_items has composite PK (order_id, product_id)."""
        entity = self.snap.entities["entity:order_items"]
        assert "order_id" in entity.grain
        assert "product_id" in entity.grain

    def test_foreign_keys_extracted(self):
        """Should find FK joins for all REFERENCES."""
        join_targets = {j.target_entity_id for j in self.snap.joins}
        assert "entity:customers" in join_targets
        assert "entity:products" in join_targets
        assert "entity:orders" in join_targets

    def test_fk_count(self):
        """5 REFERENCES = 5 JoinDefs."""
        assert len(self.snap.joins) == 5

    def test_nullable_detection(self):
        email = self.snap.fields["field:customers:email"]
        assert email.nullable is False
        category = self.snap.fields["field:products:category"]
        assert category.nullable is True

    def test_timestamp_field_type(self):
        created = self.snap.fields["field:customers:created_at"]
        assert created.field_type == FieldType.TIMESTAMP

    def test_measure_field_type(self):
        total = self.snap.fields["field:orders:total_amount"]
        assert total.field_type == FieldType.MEASURE

    def test_deterministic_id(self):
        snap2 = parse_ddl_file(POSTGRES_DDL)
        assert snap2.snapshot_id == self.snap.snapshot_id

    def test_serial_normalized_to_integer(self):
        pk_field = self.snap.fields["field:customers:id"]
        assert pk_field.data_type == "INTEGER"

    def test_boolean_type(self):
        is_active = self.snap.fields["field:customers:is_active"]
        assert is_active.data_type == "BOOLEAN"
```

**Northwind T-SQL DDL tests (skipif fixture not present):**

```python
@pytest.mark.skipif(not NORTHWIND_DDL.exists(), reason="Northwind fixture not present")
class TestNorthwindDDL:
    """DDL parser against T-SQL Northwind fixture."""

    def setup_method(self):
        self.snap = parse_ddl_file(NORTHWIND_DDL)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_table_count(self):
        """Northwind has at least 8 main tables."""
        assert len(self.snap.entities) >= 8

    def test_key_tables_present(self):
        names = {e.name for e in self.snap.entities.values()}
        for expected in ["Employees", "Customers", "Orders", "Products", "Categories"]:
            assert expected in names, f"Missing table: {expected}"

    def test_orders_fk_to_customers(self):
        fk_joins = [j for j in self.snap.joins
                     if j.source_entity_id == "entity:Orders"
                     and j.target_entity_id == "entity:Customers"]
        assert len(fk_joins) >= 1

    def test_quoted_identifiers_stripped(self):
        for entity in self.snap.entities.values():
            assert '"' not in entity.name
            assert '[' not in entity.name

    def test_nvarchar_normalized(self):
        varchar_fields = [f for f in self.snap.fields.values()
                          if "VARCHAR" in f.data_type.upper()]
        assert len(varchar_fields) > 0, "nvarchar not normalized to VARCHAR"

    def test_tsql_int_normalized(self):
        """T-SQL quoted "int" should normalize to INTEGER."""
        int_fields = [f for f in self.snap.fields.values()
                      if f.data_type == "INTEGER"]
        assert len(int_fields) > 0, "Quoted int not normalized to INTEGER"
```

**Plugin interface + cleanup tests:**

```python
def test_ddl_parser_implements_protocol():
    from datashark_protocol.parsers import DDLParser, SnapshotParser
    parser = DDLParser()
    assert isinstance(parser, SnapshotParser)

def test_ddl_parser_detect_sql():
    parser = DDLParser()
    assert parser.detect(Path("schema.sql")) > 0.0

def test_ddl_parser_detect_non_sql():
    parser = DDLParser()
    assert parser.detect(Path("README.md")) == 0.0

def test_registry_includes_ddl():
    from datashark_protocol.parsers import get_default_registry
    registry = get_default_registry()
    assert "ddl" in registry.registered_types

def test_detect_source_type_sql_via_registry():
    """detect_source_type delegates to registry for .sql files."""
    assert detect_source_type(file_path=POSTGRES_DDL) == "ddl"
```

Also update the existing `test_parse_from_path_unsupported_raises` — the error message changed in the previous handoff, verify it still works:
```python
def test_parse_from_path_unsupported_raises():
    with pytest.raises(ValueError, match="No parser can handle"):
        parse_from_path(Path("/tmp/something.xyz"))
```
Note: `.csv` files will get DDL parser confidence 0.0 so they'll still fail, but use `.xyz` to be safe.

## Verification

After completing all changes, run these checks in order:

1. `python datashark-protocol/tests/verify_eyes.py` — expected: 15 tests pass (unchanged)
2. `python -m pytest datashark-protocol/tests/test_parsers.py -v` — expected: all existing + all new tests pass
3. `python -m pytest datashark-protocol/tests/ -v` — expected: full suite passes
4. Import check: `python -c "from datashark_protocol.parsers import DDLParser, parse_ddl_file, reset_default_registry; print('OK')"`
5. Postgres DDL smoke test:
   ```bash
   python -c "
   from datashark_protocol.parsers import parse_ddl_file
   from pathlib import Path
   snap = parse_ddl_file(Path('test_warehouses/postgres_ddl/ecommerce.sql'))
   print(f'Entities: {len(snap.entities)}, Fields: {len(snap.fields)}, Joins: {len(snap.joins)}')
   assert len(snap.entities) == 5, f'Expected 5, got {len(snap.entities)}'
   assert len(snap.joins) == 5, f'Expected 5, got {len(snap.joins)}'
   print('PASS')
   "
   ```
6. Northwind T-SQL smoke test:
   ```bash
   python -c "
   from datashark_protocol.parsers import parse_ddl_file
   from pathlib import Path
   snap = parse_ddl_file(Path('test_warehouses/northwind_ddl/northwind.sql'))
   print(f'Entities: {len(snap.entities)}, Fields: {len(snap.fields)}, Joins: {len(snap.joins)}')
   assert len(snap.entities) >= 8, f'Expected >=8, got {len(snap.entities)}'
   print(f'Tables: {sorted(e.name for e in snap.entities.values())}')
   print('PASS')
   "
   ```
7. Backward compat check — server.py still works with updated `parse_from_path`:
   ```bash
   python -c "
   from datashark_protocol.parsers import parse_from_path
   import inspect
   sig = inspect.signature(parse_from_path)
   params = list(sig.parameters.keys())
   assert 'source_path' in params
   assert 'snapshot_name' not in params, 'snapshot_name should be removed'
   print('parse_from_path signature clean')
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
- Touch `types.py`, `kernel.py`, `graph.py`, `safety.py`, or any SQL builder files
- Add `sqlglot` as a dependency — use `sqlparse` only
- Implement other parsers (SQLite, Django, etc.) — those are separate handoffs
- Add async to any parser code
- Change the hashing logic in `build_snapshot()`
- Modify existing dbt or LookML parser logic (only imports and registration change)
- Touch `verify_eyes.py`
- Modify `server.py` beyond the single `parse_from_path` call on line 289
