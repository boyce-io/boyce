"""
Tests for boyce.parsers — dbt manifest + auto-detect.

Uses fixture manifest files already in legacy_v0/tests/ — no network required.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from boyce.parsers import (
    detect_source_type,
    parse_dbt_manifest,
    parse_from_path,
    parse_sqlite_file,
    parse_ddl_file,
    parse_csv_file,
    SQLiteParser,
    DDLParser,
    CSVParser,
)
from boyce.types import FieldType, SemanticSnapshot

REPO_ROOT = Path(__file__).parent.parent.parent
DEMO_MANIFEST = REPO_ROOT / "demo" / "magic_moment" / "manifest.json"
SMALL_RETAIL_MANIFEST = (
    REPO_ROOT / "legacy_v0" / "tests" / "universes" / "small_retail" / "dbt_project" / "target" / "manifest.json"
)
POSTGRES_DDL = REPO_ROOT / "test_warehouses" / "postgres_ddl" / "ecommerce.sql"
NORTHWIND_DDL = REPO_ROOT / "test_warehouses" / "northwind_ddl" / "northwind.sql"
JAFFLE_CUSTOMERS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds" / "raw_customers.csv"
JAFFLE_ORDERS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds" / "raw_orders.csv"
JAFFLE_PAYMENTS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds" / "raw_payments.csv"


# ---------------------------------------------------------------------------
# detect_source_type
# ---------------------------------------------------------------------------


def test_detect_manifest_by_filename():
    assert detect_source_type(file_path=Path("target/manifest.json")) == "dbt_manifest"


def test_detect_lookml_by_extension():
    assert detect_source_type(file_path=Path("views/orders.lkml")) == "lookml"


def test_detect_dbt_project_by_yml():
    assert detect_source_type(file_path=Path("dbt_project.yml")) == "dbt_project"


def test_detect_unknown():
    assert detect_source_type(file_path=Path("README.md")) == "unknown"


# ---------------------------------------------------------------------------
# parse_dbt_manifest — demo manifest (single model)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DEMO_MANIFEST.exists(), reason="Demo manifest not present")
class TestDemoManifest:
    def setup_method(self):
        self.snap = parse_dbt_manifest(DEMO_MANIFEST)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_snapshot_id_is_sha256(self):
        assert len(self.snap.snapshot_id) == 64
        assert all(c in "0123456789abcdef" for c in self.snap.snapshot_id)

    def test_source_system(self):
        assert self.snap.source_system == "dbt"

    def test_entities_non_empty(self):
        assert len(self.snap.entities) >= 1

    def test_fields_non_empty(self):
        assert len(self.snap.fields) >= 1

    def test_subscriptions_entity_present(self):
        assert "entity:subscriptions" in self.snap.entities

    def test_entity_fields_resolve(self):
        entity = self.snap.entities["entity:subscriptions"]
        for field_id in entity.fields:
            assert field_id in self.snap.fields, f"Field {field_id} missing from snapshot"

    def test_field_types_are_valid(self):
        for field in self.snap.fields.values():
            assert field.field_type in FieldType.__members__.values()

    def test_metadata_source_type(self):
        assert self.snap.metadata.get("source_type") == "manifest"

    def test_deterministic_id(self):
        snap2 = parse_dbt_manifest(DEMO_MANIFEST)
        assert snap2.snapshot_id == self.snap.snapshot_id


# ---------------------------------------------------------------------------
# parse_dbt_manifest — small_retail fixture (multi-model)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not SMALL_RETAIL_MANIFEST.exists(), reason="small_retail fixture not present")
class TestSmallRetailManifest:
    def setup_method(self):
        self.snap = parse_dbt_manifest(SMALL_RETAIL_MANIFEST)

    def test_multiple_entities(self):
        assert len(self.snap.entities) >= 2

    def test_all_fields_have_valid_entity(self):
        for field_id, field in self.snap.fields.items():
            assert field.entity_id in self.snap.entities, (
                f"Field {field_id} references missing entity {field.entity_id}"
            )


# ---------------------------------------------------------------------------
# parse_from_path — auto-detect
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DEMO_MANIFEST.exists(), reason="Demo manifest not present")
def test_parse_from_path_manifest():
    snap = parse_from_path(DEMO_MANIFEST)
    assert isinstance(snap, SemanticSnapshot)
    assert snap.source_system == "dbt"


def test_parse_from_path_unsupported_raises():
    with pytest.raises(ValueError, match="No parser can handle"):
        parse_from_path(Path("/tmp/something.xyz"))


# ---------------------------------------------------------------------------
# Plugin Interface Tests
# ---------------------------------------------------------------------------


def test_snapshot_parser_protocol_exists():
    from boyce.parsers import SnapshotParser

    assert hasattr(SnapshotParser, "detect")
    assert hasattr(SnapshotParser, "parse")
    assert hasattr(SnapshotParser, "source_type")


def test_dbt_manifest_parser_implements_protocol():
    from boyce.parsers import DbtManifestParser, SnapshotParser

    parser = DbtManifestParser()
    assert isinstance(parser, SnapshotParser)


def test_dbt_project_parser_implements_protocol():
    from boyce.parsers import DbtProjectParser, SnapshotParser

    parser = DbtProjectParser()
    assert isinstance(parser, SnapshotParser)


def test_lookml_parser_implements_protocol():
    from boyce.parsers import LookMLParser, SnapshotParser

    parser = LookMLParser()
    assert isinstance(parser, SnapshotParser)


def test_registry_detects_manifest():
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    candidates = registry.detect(Path("target/manifest.json"))
    assert len(candidates) >= 1
    assert candidates[0][0].source_type() == "dbt_manifest"


def test_registry_detects_lookml():
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    candidates = registry.detect(Path("views/orders.lkml"))
    assert len(candidates) >= 1
    assert candidates[0][0].source_type() == "lookml"


def test_registry_no_match_for_unknown():
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    candidates = registry.detect(Path("README.md"))
    assert len(candidates) == 0


def test_registry_registered_types():
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    types = registry.registered_types
    assert "dbt_manifest" in types
    assert "dbt_project" in types
    assert "lookml" in types


@pytest.mark.skipif(not DEMO_MANIFEST.exists(), reason="Demo manifest not present")
def test_registry_parse_manifest():
    """Registry-based parse produces identical result to direct function call."""
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    snap_registry = registry.parse(DEMO_MANIFEST)
    snap_direct = parse_dbt_manifest(DEMO_MANIFEST)
    assert snap_registry.snapshot_id == snap_direct.snapshot_id


def test_build_snapshot_accessible():
    """build_snapshot is importable from parsers package."""
    from boyce.parsers import build_snapshot

    assert callable(build_snapshot)


# ---------------------------------------------------------------------------
# SQLite Parser Tests
# ---------------------------------------------------------------------------


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

    def test_sqlite_parser_detect_real_file(self):
        """detect() returns 0.95 for a real SQLite file (magic bytes verified)."""
        parser = SQLiteParser()
        assert parser.detect(self._db_path) == 0.95


def test_sqlite_parser_implements_protocol():
    from boyce.parsers import SQLiteParser, SnapshotParser

    parser = SQLiteParser()
    assert isinstance(parser, SnapshotParser)


def test_sqlite_parser_detect_sqlite_extension():
    parser = SQLiteParser()
    assert parser.detect(Path("data.sqlite")) > 0.0
    assert parser.detect(Path("data.db")) > 0.0
    assert parser.detect(Path("data.sqlite3")) > 0.0


def test_sqlite_parser_detect_non_sqlite():
    parser = SQLiteParser()
    assert parser.detect(Path("schema.sql")) == 0.0
    assert parser.detect(Path("README.md")) == 0.0


def test_registry_includes_sqlite():
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    assert "sqlite" in registry.registered_types


# ---------------------------------------------------------------------------
# DDL Parser Tests
# ---------------------------------------------------------------------------


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

    def test_source_system(self):
        assert self.snap.source_system == "ddl"

    def test_metadata_table_count(self):
        assert self.snap.metadata["table_count"] == 5


@pytest.mark.skipif(not NORTHWIND_DDL.exists(), reason="Northwind fixture not present")
class TestNorthwindDDL:
    """DDL parser against T-SQL Northwind fixture."""

    def setup_method(self):
        self.snap = parse_ddl_file(NORTHWIND_DDL)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_table_count(self):
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
        int_fields = [f for f in self.snap.fields.values()
                      if f.data_type == "INTEGER"]
        assert len(int_fields) > 0, "Quoted int not normalized to INTEGER"


# Plugin interface tests
def test_ddl_parser_implements_protocol():
    from boyce.parsers import DDLParser, SnapshotParser

    parser = DDLParser()
    assert isinstance(parser, SnapshotParser)


def test_ddl_parser_detect_sql():
    parser = DDLParser()
    assert parser.detect(Path("schema.sql")) > 0.0


def test_ddl_parser_detect_non_sql():
    parser = DDLParser()
    assert parser.detect(Path("README.md")) == 0.0


def test_registry_includes_ddl():
    from boyce.parsers import get_default_registry

    registry = get_default_registry()
    assert "ddl" in registry.registered_types


def test_detect_source_type_sql_via_registry():
    """detect_source_type delegates to registry for .sql files."""
    assert detect_source_type(file_path=POSTGRES_DDL) == "ddl"


# Interface cleanup tests
def test_parse_from_path_signature_clean():
    """parse_from_path no longer accepts snapshot_name."""
    import inspect
    sig = inspect.signature(parse_from_path)
    params = list(sig.parameters.keys())
    assert "source_path" in params
    assert "snapshot_name" not in params


def test_reset_default_registry():
    from boyce.parsers import get_default_registry, reset_default_registry

    reg1 = get_default_registry()
    reset_default_registry()
    reg2 = get_default_registry()
    assert reg1 is not reg2
    assert "ddl" in reg2.registered_types


# ---------------------------------------------------------------------------
# CSV Parser Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not JAFFLE_CUSTOMERS.exists(), reason="Jaffle customers CSV not present")
class TestCSVCustomers:
    """CSV parser against jaffle_shop raw_customers.csv."""

    def setup_method(self):
        self.snap = parse_csv_file(JAFFLE_CUSTOMERS)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_one_entity(self):
        assert len(self.snap.entities) == 1

    def test_entity_name_from_filename(self):
        assert "entity:raw_customers" in self.snap.entities
        assert self.snap.entities["entity:raw_customers"].name == "raw_customers"

    def test_field_count(self):
        assert len(self.snap.fields) == 3
        names = {self.snap.fields[fid].name for fid in self.snap.entities["entity:raw_customers"].fields}
        assert names == {"id", "first_name", "last_name"}

    def test_id_field_is_pk(self):
        pk_field = self.snap.fields["field:raw_customers:id"]
        assert pk_field.primary_key is True
        assert pk_field.field_type == FieldType.ID

    def test_id_type_inferred_as_integer(self):
        pk_field = self.snap.fields["field:raw_customers:id"]
        assert pk_field.data_type == "INTEGER"

    def test_string_fields(self):
        assert self.snap.fields["field:raw_customers:first_name"].data_type == "VARCHAR"
        assert self.snap.fields["field:raw_customers:last_name"].data_type == "VARCHAR"

    def test_grain_is_id(self):
        assert self.snap.entities["entity:raw_customers"].grain == "id"

    def test_deterministic_id(self):
        snap2 = parse_csv_file(JAFFLE_CUSTOMERS)
        assert snap2.snapshot_id == self.snap.snapshot_id

    def test_source_system(self):
        assert self.snap.source_system == "csv"

    def test_no_joins(self):
        assert len(self.snap.joins) == 0


@pytest.mark.skipif(not JAFFLE_ORDERS.exists(), reason="Jaffle orders CSV not present")
class TestCSVOrders:
    """CSV parser against jaffle_shop raw_orders.csv."""

    def setup_method(self):
        self.snap = parse_csv_file(JAFFLE_ORDERS)

    def test_date_type_inferred(self):
        order_date_field = self.snap.fields["field:raw_orders:order_date"]
        assert order_date_field.data_type == "DATE"

    def test_user_id_is_foreign_key(self):
        user_id_field = self.snap.fields["field:raw_orders:user_id"]
        assert user_id_field.field_type == FieldType.FOREIGN_KEY

    def test_status_is_dimension(self):
        status_field = self.snap.fields["field:raw_orders:status"]
        assert status_field.field_type == FieldType.DIMENSION


@pytest.mark.skipif(not JAFFLE_PAYMENTS.exists(), reason="Jaffle payments CSV not present")
class TestCSVPayments:
    """CSV parser against jaffle_shop raw_payments.csv."""

    def setup_method(self):
        self.snap = parse_csv_file(JAFFLE_PAYMENTS)

    def test_amount_is_measure(self):
        amount_field = self.snap.fields["field:raw_payments:amount"]
        assert amount_field.field_type == FieldType.MEASURE

    def test_payment_method_is_dimension(self):
        pm_field = self.snap.fields["field:raw_payments:payment_method"]
        assert pm_field.field_type == FieldType.DIMENSION


def test_csv_parser_implements_protocol():
    from boyce.parsers import SnapshotParser
    parser = CSVParser()
    assert isinstance(parser, SnapshotParser)


def test_csv_parser_detect_csv():
    assert CSVParser().detect(Path("data.csv")) > 0.0


def test_csv_parser_detect_non_csv():
    assert CSVParser().detect(Path("README.md")) == 0.0


def test_registry_includes_csv():
    from boyce.parsers import get_default_registry
    assert "csv" in get_default_registry().registered_types


@pytest.mark.skipif(not JAFFLE_CUSTOMERS.exists(), reason="Jaffle customers CSV not present")
def test_detect_source_type_csv():
    """detect_source_type delegates to registry for .csv files."""
    assert detect_source_type(file_path=JAFFLE_CUSTOMERS) == "csv"


# ---------------------------------------------------------------------------
# Parquet Parser Tests (optional pyarrow)
# ---------------------------------------------------------------------------


def test_parquet_parser_implements_protocol():
    pytest.importorskip("pyarrow")
    from boyce.parsers import ParquetParser, SnapshotParser
    assert isinstance(ParquetParser(), SnapshotParser)


def test_parquet_parse_roundtrip():
    """Create temp Parquet from CSV-like data, parse it, verify entity/fields."""
    pyarrow = pytest.importorskip("pyarrow")
    import tempfile
    pa = pyarrow
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        path = Path(f.name)
    try:
        table = pa.table({
            "id": pa.array([1, 2, 3]),
            "name": pa.array(["a", "b", "c"]),
            "amount": pa.array([10.5, 20.0, 30.0]),
        })
        pa.parquet.write_table(table, path)
        from boyce.parsers import parse_parquet_file
        snap = parse_parquet_file(path)
        assert len(snap.entities) == 1
        assert len(snap.fields) == 3
        assert snap.source_system == "parquet"
        names = {snap.fields[fid].name for fid in list(snap.entities.values())[0].fields}
        assert names == {"id", "name", "amount"}
    finally:
        path.unlink(missing_ok=True)


def test_parquet_types_preserved():
    pytest.importorskip("pyarrow")
    from boyce.parsers import parse_parquet_file
    import tempfile
    import pyarrow as pa
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        path = Path(f.name)
    try:
        table = pa.table({
            "id": pa.array([1, 2], type=pa.int64()),
            "label": pa.array(["x", "y"]),
            "value": pa.array([1.5, 2.5], type=pa.float64()),
        })
        pa.parquet.write_table(table, path)
        snap = parse_parquet_file(path)
        entity_id = list(snap.entities.keys())[0]
        entity_name = snap.entities[entity_id].name
        assert snap.fields[f"field:{entity_name}:id"].data_type == "INTEGER"
        assert snap.fields[f"field:{entity_name}:label"].data_type == "VARCHAR"
        assert snap.fields[f"field:{entity_name}:value"].data_type == "DOUBLE PRECISION"
    finally:
        path.unlink(missing_ok=True)


def test_parquet_detect():
    pytest.importorskip("pyarrow")
    from boyce.parsers import ParquetParser
    assert ParquetParser().detect(Path("data.parquet")) > 0.0


# ---------------------------------------------------------------------------
# Django Parser Tests
# ---------------------------------------------------------------------------

DJANGO_MODELS = REPO_ROOT / "test_warehouses" / "django_models" / "models.py"


@pytest.mark.skipif(not DJANGO_MODELS.exists(), reason="Django fixture not found")
class TestDjangoModels:
    def setup_method(self):
        from boyce.parsers import parse_django_models
        self.snap = parse_django_models(DJANGO_MODELS)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_entity_count(self):
        assert len(self.snap.entities) == 5

    def test_entity_names(self):
        names = {e.name for e in self.snap.entities.values()}
        assert names == {"customers", "products", "orders", "order_items", "reviews"}

    def test_abstract_model_excluded(self):
        names = {e.name.lower() for e in self.snap.entities.values()}
        assert not any("timestamp" in n or "mixin" in n for n in names)

    def test_customer_fields(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        field_names = {self.snap.fields[fid].name for fid in entity.fields}
        assert "name" in field_names
        assert "email" in field_names
        assert "is_active" in field_names
        assert "id" in field_names

    def test_inherited_fields_present(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        field_names = {self.snap.fields[fid].name for fid in entity.fields}
        assert "created_at" in field_names
        assert "updated_at" in field_names

    def test_fk_field_naming(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "orders")
        field_names = {self.snap.fields[fid].name for fid in entity.fields}
        assert "customer_id" in field_names
        assert "customer" not in field_names

    def test_fk_joins_extracted(self):
        assert len(self.snap.joins) >= 4

    def test_implicit_pk(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        id_field = next(
            self.snap.fields[fid] for fid in entity.fields
            if self.snap.fields[fid].name == "id"
        )
        assert id_field.field_type == FieldType.ID
        assert id_field.primary_key is True

    def test_decimal_is_measure(self):
        products = next(e for e in self.snap.entities.values() if e.name == "products")
        price_field = next(
            self.snap.fields[fid] for fid in products.fields
            if self.snap.fields[fid].name == "price"
        )
        assert price_field.field_type == FieldType.MEASURE

    def test_datetime_is_timestamp(self):
        customers = next(e for e in self.snap.entities.values() if e.name == "customers")
        created = next(
            self.snap.fields[fid] for fid in customers.fields
            if self.snap.fields[fid].name == "created_at"
        )
        assert created.field_type == FieldType.TIMESTAMP

    def test_nullable_detection(self):
        products = next(e for e in self.snap.entities.values() if e.name == "products")
        by_name = {self.snap.fields[fid].name: self.snap.fields[fid] for fid in products.fields}
        assert by_name["category"].nullable is True
        assert by_name["name"].nullable is False

    def test_deterministic_id(self):
        from boyce.parsers import parse_django_models
        snap2 = parse_django_models(DJANGO_MODELS)
        assert self.snap.snapshot_id == snap2.snapshot_id

    def test_source_system(self):
        assert self.snap.source_system == "django"


def test_django_parser_implements_protocol():
    from boyce.parsers import DjangoParser, SnapshotParser
    assert isinstance(DjangoParser(), SnapshotParser)


def test_django_parser_detect_models_py():
    from boyce.parsers import DjangoParser
    assert DjangoParser().detect(DJANGO_MODELS) > 0.0


def test_django_parser_detect_non_models():
    from boyce.parsers import DjangoParser
    assert DjangoParser().detect(Path("README.md")) == 0.0


def test_registry_includes_django():
    from boyce.parsers import get_default_registry, reset_default_registry
    reset_default_registry()
    reg = get_default_registry()
    assert "django" in reg.registered_types


# ---------------------------------------------------------------------------
# SQLAlchemy Parser Tests
# ---------------------------------------------------------------------------

SQLALCHEMY_MODELS = REPO_ROOT / "test_warehouses" / "sqlalchemy_models" / "models.py"


@pytest.mark.skipif(not SQLALCHEMY_MODELS.exists(), reason="SQLAlchemy fixture not found")
class TestSQLAlchemyModels:
    def setup_method(self):
        from boyce.parsers import parse_sqlalchemy_models
        self.snap = parse_sqlalchemy_models(SQLALCHEMY_MODELS)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_entity_count(self):
        assert len(self.snap.entities) == 5

    def test_entity_names(self):
        names = {e.name for e in self.snap.entities.values()}
        assert names == {"customers", "products", "orders", "order_items", "reviews"}

    def test_base_class_excluded(self):
        names = {e.name.lower() for e in self.snap.entities.values()}
        assert "base" not in names

    def test_customer_fields(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        field_names = {self.snap.fields[fid].name for fid in entity.fields}
        assert {"id", "name", "email", "is_active", "created_at"}.issubset(field_names)

    def test_pk_detected(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        id_field = next(
            self.snap.fields[fid] for fid in entity.fields
            if self.snap.fields[fid].name == "id"
        )
        assert id_field.primary_key is True
        assert id_field.field_type == FieldType.ID

    def test_composite_pk(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "order_items")
        grain = entity.grain
        assert "order_id" in grain and "product_id" in grain

    def test_fk_joins_extracted(self):
        assert len(self.snap.joins) >= 4

    def test_fk_field_type(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "orders")
        cid = next(
            self.snap.fields[fid] for fid in entity.fields
            if self.snap.fields[fid].name == "customer_id"
        )
        assert cid.field_type == FieldType.FOREIGN_KEY

    def test_numeric_is_measure(self):
        products = next(e for e in self.snap.entities.values() if e.name == "products")
        price_field = next(
            self.snap.fields[fid] for fid in products.fields
            if self.snap.fields[fid].name == "price"
        )
        assert price_field.field_type == FieldType.MEASURE

    def test_datetime_is_timestamp(self):
        customers = next(e for e in self.snap.entities.values() if e.name == "customers")
        created = next(
            self.snap.fields[fid] for fid in customers.fields
            if self.snap.fields[fid].name == "created_at"
        )
        assert created.field_type == FieldType.TIMESTAMP

    def test_nullable_detection(self):
        products = next(e for e in self.snap.entities.values() if e.name == "products")
        by_name = {self.snap.fields[fid].name: self.snap.fields[fid] for fid in products.fields}
        assert by_name["category"].nullable is True
        assert by_name["name"].nullable is False

    def test_relationship_excluded(self):
        orders = next(e for e in self.snap.entities.values() if e.name == "orders")
        field_names = {self.snap.fields[fid].name for fid in orders.fields}
        assert "orders" not in field_names
        assert "customer" not in field_names
        assert "items" not in field_names

    def test_deterministic_id(self):
        from boyce.parsers import parse_sqlalchemy_models
        snap2 = parse_sqlalchemy_models(SQLALCHEMY_MODELS)
        assert self.snap.snapshot_id == snap2.snapshot_id

    def test_source_system(self):
        assert self.snap.source_system == "sqlalchemy"


def test_sqlalchemy_parser_implements_protocol():
    from boyce.parsers import SQLAlchemyParser, SnapshotParser
    assert isinstance(SQLAlchemyParser(), SnapshotParser)


def test_sqlalchemy_parser_detect():
    from boyce.parsers import SQLAlchemyParser
    assert SQLAlchemyParser().detect(SQLALCHEMY_MODELS) > 0.0


def test_registry_includes_sqlalchemy():
    from boyce.parsers import get_default_registry, reset_default_registry
    reset_default_registry()
    reg = get_default_registry()
    assert "sqlalchemy" in reg.registered_types


# ---------------------------------------------------------------------------
# Prisma Parser Tests
# ---------------------------------------------------------------------------

PRISMA_SCHEMA = REPO_ROOT / "test_warehouses" / "prisma_schema" / "schema.prisma"


@pytest.mark.skipif(not PRISMA_SCHEMA.exists(), reason="Prisma fixture not found")
class TestPrismaSchema:
    def setup_method(self):
        from boyce.parsers import parse_prisma_schema
        self.snap = parse_prisma_schema(PRISMA_SCHEMA)

    def test_returns_semantic_snapshot(self):
        assert isinstance(self.snap, SemanticSnapshot)

    def test_entity_count(self):
        assert len(self.snap.entities) == 5

    def test_entity_names(self):
        names = {e.name for e in self.snap.entities.values()}
        assert names == {"customers", "products", "orders", "order_items", "reviews"}

    def test_customer_fields(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        field_names = {self.snap.fields[fid].name for fid in entity.fields}
        assert {"id", "name", "email", "isActive", "createdAt", "updatedAt"}.issubset(field_names)
        # Relation-only navigation fields excluded
        assert "orders" not in field_names
        assert "reviews" not in field_names

    def test_pk_detected(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "customers")
        id_field = next(
            self.snap.fields[fid] for fid in entity.fields
            if self.snap.fields[fid].name == "id"
        )
        assert id_field.primary_key is True
        assert id_field.field_type == FieldType.ID

    def test_composite_pk(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "order_items")
        grain = entity.grain
        assert "orderId" in grain and "productId" in grain

    def test_fk_joins_extracted(self):
        assert len(self.snap.joins) >= 4

    def test_fk_field_type(self):
        entity = next(e for e in self.snap.entities.values() if e.name == "orders")
        cid = next(
            self.snap.fields[fid] for fid in entity.fields
            if self.snap.fields[fid].name == "customerId"
        )
        assert cid.field_type == FieldType.FOREIGN_KEY

    def test_nullable_detection(self):
        products = next(e for e in self.snap.entities.values() if e.name == "products")
        by_name = {self.snap.fields[fid].name: self.snap.fields[fid] for fid in products.fields}
        assert by_name["category"].nullable is True
        assert by_name["name"].nullable is False

    def test_decimal_is_measure(self):
        products = next(e for e in self.snap.entities.values() if e.name == "products")
        price = next(
            self.snap.fields[fid] for fid in products.fields
            if self.snap.fields[fid].name == "price"
        )
        assert price.field_type == FieldType.MEASURE

    def test_datetime_is_timestamp(self):
        customers = next(e for e in self.snap.entities.values() if e.name == "customers")
        created = next(
            self.snap.fields[fid] for fid in customers.fields
            if self.snap.fields[fid].name == "createdAt"
        )
        assert created.field_type == FieldType.TIMESTAMP

    def test_relation_fields_excluded(self):
        orders = next(e for e in self.snap.entities.values() if e.name == "orders")
        field_names = {self.snap.fields[fid].name for fid in orders.fields}
        # These are relation navigation fields, not columns
        assert "items" not in field_names
        assert "customer" not in field_names

    def test_deterministic_id(self):
        from boyce.parsers import parse_prisma_schema
        snap2 = parse_prisma_schema(PRISMA_SCHEMA)
        assert self.snap.snapshot_id == snap2.snapshot_id

    def test_source_system(self):
        assert self.snap.source_system == "prisma"


def test_prisma_parser_implements_protocol():
    from boyce.parsers import PrismaParser, SnapshotParser
    assert isinstance(PrismaParser(), SnapshotParser)


def test_prisma_parser_detect():
    from boyce.parsers import PrismaParser
    assert PrismaParser().detect(PRISMA_SCHEMA) > 0.0


def test_prisma_parser_detect_non_prisma():
    from boyce.parsers import PrismaParser
    assert PrismaParser().detect(Path("README.md")) == 0.0


def test_registry_includes_prisma():
    from boyce.parsers import get_default_registry, reset_default_registry
    reset_default_registry()
    reg = get_default_registry()
    assert "prisma" in reg.registered_types
