# Handoff: Tier 2 Parsers — Django, SQLAlchemy, Prisma

**Created:** 2026-03-01
**Base commit:** 9ff77ed
**Branch:** main
**Mode:** Multi-step
**Cursor Model:** Sonnet 4.6 Thinking
**Cursor Mode:** Agent

## Objective

Implement the three Tier 2 ORM/schema parsers. Django and SQLAlchemy use Python AST traversal (no Django/SQLAlchemy import required at runtime). Prisma uses regex-based parsing of the Prisma Schema Language. All three follow the established `SnapshotParser` protocol pattern. Zero new external dependencies.

## Current Baseline

- **127 tests** (123 passed, 4 skipped — Parquet tests skip when pyarrow absent)
- **7 parsers registered:** dbt_manifest, dbt_project, lookml, sqlite, ddl, csv, parquet
- Established patterns to follow: `parsers/ddl.py` (regex-based), `parsers/sqlite.py` (introspection), `parsers/tabular.py` (simple)
- `build_snapshot()` in `parsers/base.py` handles SHA-256 computation
- `FieldType` enum: `ID`, `FOREIGN_KEY`, `TIMESTAMP`, `MEASURE`, `DIMENSION`
- `JoinType` enum: `INNER`, `LEFT`, `RIGHT`, `FULL`

## Steps

Each step is independent. Complete each step and its verification before proceeding to the next. Escalation rules apply per-step.

---

## Step 1: Django Models Parser

### Files to Touch
- `datashark-protocol/datashark_protocol/parsers/django.py` — **NEW**
- `test_warehouses/django_models/models.py` — **NEW** — synthetic fixture
- `datashark-protocol/tests/test_parsers.py` — add tests

### Synthetic Fixture: `test_warehouses/django_models/models.py`

Create this file exactly (it tests all the edge cases the parser must handle):

```python
"""Synthetic Django models for parser testing."""
from django.db import models


class TimestampMixin(models.Model):
    """Abstract mixin — should NOT become an entity."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Customer(TimestampMixin):
    """Concrete model inheriting from abstract mixin."""
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "customers"


class Product(TimestampMixin):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_count = models.IntegerField(default=0)

    class Meta:
        db_table = "products"


class Order(TimestampMixin):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    order_date = models.DateTimeField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default="pending")

    class Meta:
        db_table = "orders"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "order_items"
        unique_together = [("order", "product")]


class Review(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rating = models.IntegerField()
    review_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviews"
```

### Parser Implementation: `parsers/django.py`

**Approach:** Use Python `ast` module to parse the file. Walk `ast.ClassDef` nodes. For each class:

1. **Skip abstract models.** Look for a nested `Meta` class with `abstract = True`. Skip these classes as entities but remember their fields (for inheritance).

2. **Detect Django models.** A class is a Django model if any base class name contains `Model` (handles `models.Model`, `MyModel`, `TimestampMixin` inheritance). Use a conservative check: if the class has any `models.XxxField()` assignments, it's a model.

3. **Extract table name.** Check for `Meta.db_table` string value. If absent, default to class name lowercased.

4. **Extract fields.** Look for `ast.Assign` or `ast.AnnAssign` nodes where the value is an `ast.Call` whose function name (or attribute name) ends with `Field`. Map Django field types to SQL types:

```python
DJANGO_TYPE_MAP = {
    "AutoField": ("INTEGER", FieldType.ID),
    "BigAutoField": ("BIGINT", FieldType.ID),
    "SmallAutoField": ("SMALLINT", FieldType.ID),
    "CharField": ("VARCHAR", FieldType.DIMENSION),
    "TextField": ("TEXT", FieldType.DIMENSION),
    "EmailField": ("VARCHAR", FieldType.DIMENSION),
    "SlugField": ("VARCHAR", FieldType.DIMENSION),
    "URLField": ("VARCHAR", FieldType.DIMENSION),
    "UUIDField": ("UUID", FieldType.DIMENSION),
    "IntegerField": ("INTEGER", FieldType.DIMENSION),
    "BigIntegerField": ("BIGINT", FieldType.DIMENSION),
    "SmallIntegerField": ("SMALLINT", FieldType.DIMENSION),
    "PositiveIntegerField": ("INTEGER", FieldType.DIMENSION),
    "FloatField": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "DecimalField": ("DECIMAL", FieldType.MEASURE),
    "BooleanField": ("BOOLEAN", FieldType.DIMENSION),
    "NullBooleanField": ("BOOLEAN", FieldType.DIMENSION),
    "DateField": ("DATE", FieldType.TIMESTAMP),
    "DateTimeField": ("TIMESTAMP", FieldType.TIMESTAMP),
    "TimeField": ("TIME", FieldType.TIMESTAMP),
    "DurationField": ("INTERVAL", FieldType.DIMENSION),
    "BinaryField": ("BYTEA", FieldType.DIMENSION),
    "FileField": ("VARCHAR", FieldType.DIMENSION),
    "ImageField": ("VARCHAR", FieldType.DIMENSION),
    "JSONField": ("JSONB", FieldType.DIMENSION),
    "ForeignKey": ("INTEGER", FieldType.FOREIGN_KEY),
    "OneToOneField": ("INTEGER", FieldType.FOREIGN_KEY),
}
```

5. **Handle ForeignKey/OneToOneField.** The first positional argument is the target model name (string or bare name). Append `_id` to the field name (Django convention). Create a `JoinDef` linking to the target entity.

6. **Handle ManyToManyField.** Skip — these create intermediate tables, not columns. (Document why in a comment.)

7. **Nullable.** Check for `null=True` in keyword arguments. Default False.

8. **Inheritance.** When a model's base classes include a known abstract model, merge that model's fields into this one. Track abstract models and their fields in a first pass.

9. **Grain.** If an explicit `AutoField`/`BigAutoField` is found, that's the grain. Otherwise use `"id"` (Django's implicit auto PK).

10. **The implicit `id` field.** Django adds an implicit `id = AutoField(primary_key=True)` to every model unless a field has `primary_key=True`. If no explicit PK field is found, add an implicit `id` field.

```python
def parse_django_models(file_path: Path) -> SemanticSnapshot:
    """
    Parse a Django models.py file into a SemanticSnapshot using AST.

    No Django import required — pure AST analysis.
    """
```

```python
class DjangoParser:
    """SnapshotParser implementation for Django models.py files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.name == "models.py":
            try:
                with open(path) as f:
                    content = f.read(2000)
                if "from django" in content or "import django" in content or "models.Model" in content:
                    return 0.9
                if "models.CharField" in content or "models.ForeignKey" in content:
                    return 0.7
            except Exception:
                pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_django_models(Path(path))

    def source_type(self) -> str:
        return "django"
```

### Step 1 Tests (~15 new)

Add to `test_parsers.py`:

```python
DJANGO_MODELS = REPO_ROOT / "test_warehouses" / "django_models" / "models.py"
```

**TestDjangoModels class:**
1. `test_returns_semantic_snapshot` — isinstance check
2. `test_entity_count` — 5 entities (Customer, Product, Order, OrderItem, Review). TimestampMixin is abstract — must NOT appear.
3. `test_entity_names` — names should be table names from `db_table`: "customers", "products", "orders", "order_items", "reviews"
4. `test_abstract_model_excluded` — no entity containing "timestamp" or "mixin" in the name
5. `test_customer_fields` — name, email, is_active, created_at, updated_at, id (implicit PK + inherited fields)
6. `test_inherited_fields_present` — created_at and updated_at from TimestampMixin present on Customer
7. `test_fk_field_naming` — Order entity should have a field named "customer_id" (not "customer")
8. `test_fk_joins_extracted` — at least 4 joins (Order→Customer, OrderItem→Order, OrderItem→Product, Review→Customer, Review→Product)
9. `test_implicit_pk` — Customer entity has an "id" field with field_type=ID, primary_key=True
10. `test_decimal_is_measure` — price and total_amount fields have field_type=MEASURE
11. `test_datetime_is_timestamp` — created_at has field_type=TIMESTAMP
12. `test_nullable_detection` — category is nullable (null=True in fixture), name is not
13. `test_deterministic_id` — parse twice, same snapshot_id
14. `test_source_system` — source_system = "django"

**Plugin interface tests:**
15. `test_django_parser_implements_protocol`
16. `test_django_parser_detect_models_py` — detect on the fixture returns > 0.0
17. `test_django_parser_detect_non_models` — detect on README.md returns 0.0
18. `test_registry_includes_django`

### Step 1 Verification

```bash
python -m pytest datashark-protocol/tests/test_parsers.py -v -k "django or Django"
# Expect: ~18 tests passing
python -m pytest datashark-protocol/tests/ -v
# Expect: ~145 tests (127 + ~18), all passing (4 skipped for pyarrow)
python datashark-protocol/tests/verify_eyes.py
# Expect: 15 passing (no regressions)
```

---

## Step 2: SQLAlchemy Models Parser

### Files to Touch
- `datashark-protocol/datashark_protocol/parsers/sqlalchemy_models.py` — **NEW**
- `test_warehouses/sqlalchemy_models/models.py` — **NEW** — synthetic fixture
- `datashark-protocol/tests/test_parsers.py` — add tests

### Synthetic Fixture: `test_warehouses/sqlalchemy_models/models.py`

Create this file (tests both classic 1.x and 2.0 `mapped_column` style):

```python
"""Synthetic SQLAlchemy models for parser testing."""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import datetime


# SQLAlchemy 2.0 style
class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)

    orders = relationship("Order", back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    stock_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    order_date: Mapped[datetime.datetime] = mapped_column(DateTime)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))

    order = relationship("Order", back_populates="items")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    rating: Mapped[int] = mapped_column(Integer)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)
```

### Parser Implementation: `parsers/sqlalchemy_models.py`

**Approach:** Use Python `ast` module. Similar to Django parser but different patterns:

1. **Detect SQLAlchemy models.** A class is a model if its base class name is `Base`, `DeclarativeBase`, or contains `Base` (e.g., `MyBase`). Also check for `__tablename__` assignment.

2. **Extract table name.** From `__tablename__` string assignment. If absent, fall back to class name lowercased.

3. **Extract fields — two styles to handle:**

   **Classic style (1.x):** `name = Column(String(100), nullable=False)`
   - Value is `ast.Call` where func resolves to `Column`
   - First positional arg is the type: `String`, `Integer`, `Numeric(10,2)`, etc.
   - Check keyword args for `primary_key=True`, `nullable`, `default`

   **Mapped style (2.0):** `name: Mapped[str] = mapped_column(String(100))`
   - Value is `ast.Call` where func resolves to `mapped_column`
   - First positional arg (if present) is the type. If absent, infer from `Mapped[X]` annotation.
   - Check keyword args same as classic

4. **Type mapping:**

```python
SQLALCHEMY_TYPE_MAP = {
    "Integer": ("INTEGER", FieldType.DIMENSION),
    "BigInteger": ("BIGINT", FieldType.DIMENSION),
    "SmallInteger": ("SMALLINT", FieldType.DIMENSION),
    "String": ("VARCHAR", FieldType.DIMENSION),
    "Text": ("TEXT", FieldType.DIMENSION),
    "Boolean": ("BOOLEAN", FieldType.DIMENSION),
    "DateTime": ("TIMESTAMP", FieldType.TIMESTAMP),
    "Date": ("DATE", FieldType.TIMESTAMP),
    "Time": ("TIME", FieldType.TIMESTAMP),
    "Numeric": ("DECIMAL", FieldType.MEASURE),
    "Float": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "LargeBinary": ("BYTEA", FieldType.DIMENSION),
    "JSON": ("JSONB", FieldType.DIMENSION),
    "Uuid": ("UUID", FieldType.DIMENSION),
}
```

   **Mapped type annotation fallback:** When `mapped_column()` has no positional type arg, infer from `Mapped[X]`:
   - `Mapped[int]` → INTEGER
   - `Mapped[str]` → VARCHAR
   - `Mapped[bool]` → BOOLEAN
   - `Mapped[float]` → DOUBLE PRECISION
   - `Mapped[datetime.datetime]` → TIMESTAMP
   - `Mapped[datetime.date]` → DATE

5. **ForeignKey detection.** Look for `ForeignKey("table.column")` in the Column/mapped_column arguments. Parse the string to extract target table and column. Create a JoinDef.

6. **Skip `relationship()` assignments.** These define ORM navigation, not schema columns.

7. **Composite PK.** When multiple fields have `primary_key=True`, grain = joined names with `_`.

8. **Skip `Base` class.** `DeclarativeBase` subclass is not a model.

```python
def parse_sqlalchemy_models(file_path: Path) -> SemanticSnapshot:
class SQLAlchemyParser:
    def detect(self, path: Path) -> float:
        # Look for: "from sqlalchemy" or "Column(" or "mapped_column(" or "__tablename__"
    def source_type(self) -> str:
        return "sqlalchemy"
```

### Step 2 Tests (~15 new)

**TestSQLAlchemyModels class:**
1. `test_returns_semantic_snapshot`
2. `test_entity_count` — 5 entities
3. `test_entity_names` — "customers", "products", "orders", "order_items", "reviews"
4. `test_base_class_excluded` — no entity named "base" or "Base"
5. `test_customer_fields` — id, name, email, is_active, created_at
6. `test_pk_detected` — customers.id has primary_key=True, field_type=ID
7. `test_composite_pk` — order_items has grain containing both order_id and product_id
8. `test_fk_joins_extracted` — at least 4 joins
9. `test_fk_field_type` — customer_id field has field_type=FOREIGN_KEY
10. `test_numeric_is_measure` — price, total_amount, unit_price have field_type=MEASURE
11. `test_datetime_is_timestamp` — created_at has field_type=TIMESTAMP
12. `test_nullable_detection` — category nullable, name not nullable
13. `test_relationship_excluded` — no field named "orders" or "customer" (those are relationship() not columns)
14. `test_deterministic_id`
15. `test_source_system` — "sqlalchemy"

**Plugin interface tests:**
16. `test_sqlalchemy_parser_implements_protocol`
17. `test_sqlalchemy_parser_detect` — detect on fixture > 0.0
18. `test_registry_includes_sqlalchemy`

### Step 2 Verification

```bash
python -m pytest datashark-protocol/tests/test_parsers.py -v -k "sqlalchemy or SQLAlchemy"
# Expect: ~18 tests passing
python -m pytest datashark-protocol/tests/ -v
# Expect: ~163 tests (145 + ~18), all passing (4 skipped)
python datashark-protocol/tests/verify_eyes.py
# Expect: 15 passing
```

---

## Step 3: Prisma Schema Parser

### Files to Touch
- `datashark-protocol/datashark_protocol/parsers/prisma.py` — **NEW**
- `test_warehouses/prisma_schema/schema.prisma` — **NEW** — synthetic fixture
- `datashark-protocol/tests/test_parsers.py` — add tests

### Synthetic Fixture: `test_warehouses/prisma_schema/schema.prisma`

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model Customer {
  id        Int       @id @default(autoincrement())
  name      String
  email     String    @unique
  isActive  Boolean   @default(true)
  createdAt DateTime  @default(now())
  updatedAt DateTime  @updatedAt
  orders    Order[]
  reviews   Review[]

  @@map("customers")
}

model Product {
  id         Int         @id @default(autoincrement())
  name       String
  category   String?
  price      Decimal
  stockCount Int         @default(0)
  createdAt  DateTime    @default(now())
  items      OrderItem[]
  reviews    Review[]

  @@map("products")
}

model Order {
  id          Int         @id @default(autoincrement())
  customer    Customer    @relation(fields: [customerId], references: [id])
  customerId  Int
  orderDate   DateTime
  totalAmount Decimal
  status      String      @default("pending")
  items       OrderItem[]

  @@map("orders")
}

model OrderItem {
  order     Order   @relation(fields: [orderId], references: [id])
  orderId   Int
  product   Product @relation(fields: [productId], references: [id])
  productId Int
  quantity  Int     @default(1)
  unitPrice Decimal

  @@id([orderId, productId])
  @@map("order_items")
}

model Review {
  id         Int      @id @default(autoincrement())
  customer   Customer @relation(fields: [customerId], references: [id])
  customerId Int
  product    Product  @relation(fields: [productId], references: [id])
  productId  Int
  rating     Int
  reviewText String?
  createdAt  DateTime @default(now())

  @@map("reviews")
}
```

### Parser Implementation: `parsers/prisma.py`

**Approach:** Regex-based line-by-line parsing. Prisma Schema Language is very regular — no nested structures beyond `model { ... }` blocks.

1. **Parse model blocks.** Find `model <Name> { ... }` blocks using regex. Track brace depth for nesting.

2. **Extract table name.** Look for `@@map("table_name")` inside the model block. If absent, use the model name lowercased.

3. **Parse fields.** Each line inside a model block that isn't a directive (`@@`) or relation-only field (type is another model name + `[]`) is a field. Format:
   ```
   fieldName  Type  @decorators
   ```

4. **Prisma type mapping:**

```python
PRISMA_TYPE_MAP = {
    "String": ("VARCHAR", FieldType.DIMENSION),
    "Int": ("INTEGER", FieldType.DIMENSION),
    "BigInt": ("BIGINT", FieldType.DIMENSION),
    "Float": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "Decimal": ("DECIMAL", FieldType.MEASURE),
    "Boolean": ("BOOLEAN", FieldType.DIMENSION),
    "DateTime": ("TIMESTAMP", FieldType.TIMESTAMP),
    "Json": ("JSONB", FieldType.DIMENSION),
    "Bytes": ("BYTEA", FieldType.DIMENSION),
}
```

5. **Detect PK.** Field with `@id` decorator. Composite PK via `@@id([field1, field2])`.

6. **Detect nullable.** A `?` suffix on the type means nullable: `String?` → nullable=True.

7. **Detect relations/FKs.** Lines with `@relation(fields: [fkField], references: [pkField])`. Parse the `fields` and `references` arrays. Create JoinDef from the FK field to the referenced model.

8. **Skip relation-only fields.** Lines where the type is a model name (not a Prisma scalar) followed by `[]` are relation navigation — not columns. E.g., `orders Order[]` → skip. Also skip singular relation fields like `customer Customer @relation(...)` — the actual FK column is the separate `customerId Int` field.

9. **Skip generator/datasource blocks.** Only parse `model` blocks.

```python
def parse_prisma_schema(file_path: Path) -> SemanticSnapshot:
class PrismaParser:
    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix == ".prisma":
            return 0.95
        if path.name == "schema.prisma":
            return 0.95
        # Check content for Prisma keywords
        if path.suffix in (".txt", ""):
            try:
                with open(path) as f:
                    content = f.read(2000)
                if "datasource" in content and "model " in content:
                    return 0.6
            except Exception:
                pass
        return 0.0

    def source_type(self) -> str:
        return "prisma"
```

### Step 3 Tests (~15 new)

**TestPrismaSchema class:**
1. `test_returns_semantic_snapshot`
2. `test_entity_count` — 5 entities
3. `test_entity_names` — "customers", "products", "orders", "order_items", "reviews" (from @@map)
4. `test_customer_fields` — id, name, email, isActive, createdAt, updatedAt (relation-only `orders` and `reviews` excluded)
5. `test_pk_detected` — customers.id has primary_key=True, field_type=ID
6. `test_composite_pk` — order_items has composite grain from @@id([orderId, productId])
7. `test_fk_joins_extracted` — at least 4 joins
8. `test_fk_field_type` — customerId has field_type=FOREIGN_KEY
9. `test_nullable_detection` — category is nullable (String?), name is not
10. `test_decimal_is_measure` — price, totalAmount, unitPrice have field_type=MEASURE
11. `test_datetime_is_timestamp` — createdAt has field_type=TIMESTAMP
12. `test_relation_fields_excluded` — no field named "orders", "reviews", "items", "customer", "product" (relation navigation)
13. `test_deterministic_id`
14. `test_source_system` — "prisma"

**Plugin interface tests:**
15. `test_prisma_parser_implements_protocol`
16. `test_prisma_parser_detect` — detect on fixture > 0.0
17. `test_prisma_parser_detect_non_prisma` — detect on README.md returns 0.0
18. `test_registry_includes_prisma`

### Step 3 Verification

```bash
python -m pytest datashark-protocol/tests/test_parsers.py -v -k "prisma or Prisma"
# Expect: ~18 tests passing
python -m pytest datashark-protocol/tests/ -v
# Expect: ~181 tests total (163 + ~18), all passing (4 skipped)
python datashark-protocol/tests/verify_eyes.py
# Expect: 15 passing
```

---

## After All Three Steps: Registry + Exports Update

### `parsers/registry.py`

In `get_default_registry()`, add after the CSVParser/ParquetParser registration:

```python
from .django import DjangoParser
from .sqlalchemy_models import SQLAlchemyParser
from .prisma import PrismaParser
_default_registry.register(DjangoParser())
_default_registry.register(SQLAlchemyParser())
_default_registry.register(PrismaParser())
```

### `parsers/__init__.py`

Add imports:
```python
from .django import parse_django_models, DjangoParser
from .sqlalchemy_models import parse_sqlalchemy_models, SQLAlchemyParser
from .prisma import parse_prisma_schema, PrismaParser
```

Add to `__all__`:
```python
"DjangoParser",
"SQLAlchemyParser",
"PrismaParser",
"parse_django_models",
"parse_sqlalchemy_models",
"parse_prisma_schema",
```

### Final Verification

```bash
python -m pytest datashark-protocol/tests/ -v
# Expect: ~181 tests (127 + ~54 new), all passing (4 skipped)
python datashark-protocol/tests/verify_eyes.py
# Expect: 15 passing
```

Verify registry has 10 parsers:
```python
from datashark_protocol.parsers import get_default_registry
reg = get_default_registry()
print(reg.registered_types)
# ['dbt_manifest', 'dbt_project', 'lookml', 'sqlite', 'ddl', 'csv', 'parquet', 'django', 'sqlalchemy', 'prisma']
# (parquet only if pyarrow installed — 9 without it)
```

---

## Escalation

If any verification check fails after TWO fix attempts on a SINGLE step:
1. STOP that step. Do not keep iterating.
2. Write `.claude/handoffs/RETURN.md` with:
   - Which step (1/2/3) you were executing
   - What you tried (both attempts)
   - Exact error output / test failures
   - Your assessment of why it failed
3. Commit your partial work. Proceed to the next step if the failure is isolated.

## Scope Boundaries — Do NOT

- Do not modify any existing parser files (dbt.py, lookml.py, sqlite.py, ddl.py, tabular.py)
- Do not modify server.py or detect.py (registry delegation handles everything)
- Do not import Django, SQLAlchemy, or Prisma at runtime — all parsing is AST/regex-based
- Do not attempt to execute or evaluate the model files — pure static analysis
- Do not add any new dependencies to pyproject.toml (all three parsers use stdlib only)
- Do not create __init__.py files in the test_warehouses fixture directories
