# Test Warehouses

Curated collection of real-world database projects for validating parsers, testing join
resolution, benchmarking the planner, and exercising the full pipeline.

## Quick Start

Small fixtures are committed directly — no setup needed. For large fixtures:

```bash
cd test_warehouses/
./setup.sh
```

## Fixture Inventory

### Committed (always available)

| Fixture | Source | Size | Tables | Parser Coverage | Best For |
|---------|--------|------|--------|----------------|----------|
| **jaffle_shop/** | [dbt-labs/jaffle_shop](https://github.com/dbt-labs/jaffle_shop) | 140 KB | 3 raw + 2 models | dbt project parser, CSV/Parquet parser (seeds) | Multi-table join resolution, dbt YAML parsing |
| **jaffle_shop_duckdb/** | [dbt-labs/jaffle_shop_duckdb](https://github.com/dbt-labs/jaffle_shop_duckdb) | 584 KB | 3 | dbt project parser | DuckDB dialect testing |
| **thelook_lookml/** | [looker-open-source/thelook](https://github.com/looker-open-source/thelook) | 36 KB | 5 entities, 6 joins | LookML parser | Join graph complexity, LookML explore parsing |
| **northwind_ddl/** | [microsoft/sql-server-samples](https://github.com/microsoft/sql-server-samples) | 1.0 MB | 14 | DDL parser (T-SQL dialect) | Classic retail schema, FK relationships |
| **wide_world_importers_ddl/** | [microsoft/sql-server-samples](https://github.com/microsoft/sql-server-samples) | 136 KB | 17 (fact + dimension) | DDL parser (T-SQL dialect) | Star schema, data warehouse patterns |
| **airflow_analytics/** | Synthetic | 8 KB | 8 (3 dim + 3 fact + 2 bridge) | DDL parser (multi-file) | Airflow-style analytics warehouse, FK chains |
| **django_models/** | Synthetic | 4 KB | 5 models | Django models parser | ORM-to-schema extraction |
| **sqlalchemy_models/** | Synthetic | 4 KB | 5 models | SQLAlchemy parser | SQLAlchemy 2.0 mapped_column syntax |
| **prisma_schema/** | Synthetic | 4 KB | 5 models | Prisma parser | Prisma schema parsing |
| **postgres_ddl/** | Synthetic | 4 KB | 5 | DDL parser (PostgreSQL) | PostgreSQL-specific DDL syntax |
| **sample_sqlite/** | Synthetic | 28 KB | 5 + seed data | SQLite parser | SQLite introspection, live profiling |

### Cloned by setup.sh (git-ignored)

| Fixture | Source | Size | Parser Coverage | Best For |
|---------|--------|------|----------------|----------|
| **mattermost/** | [mattermost/mattermost-data-warehouse](https://github.com/mattermost/mattermost-data-warehouse) | ~8 MB | dbt project parser, Airflow DAG parser | Enterprise-scale dbt, Airflow DAG SQL extraction |
| **dagster_platform/** | [dagster-io/dagster-open-platform](https://github.com/dagster-io/dagster-open-platform) | ~5 MB | dbt project parser | Real production SaaS analytics, governance patterns |

### Also available (elsewhere in repo)

| Fixture | Location | Parser Coverage | Best For |
|---------|----------|----------------|----------|
| **Null Trap demo** | `demo/magic_moment/` | dbt manifest parser | Safety layer demo, NULL distribution validation |
| **Live Fire** | `boyce/tests/live_fire/` | Raw JSON snapshot | Pipeline integration smoke test (Docker) |

## Parser Validation Matrix

Which fixture tests which parser:

| Parser | jaffle_shop | thelook_lookml | northwind_ddl | wwi_ddl | airflow_analytics | django_models | sqlalchemy_models | prisma_schema | postgres_ddl | sample_sqlite |
|--------|:-----------:|:--------------:|:-------------:|:-------:|:-----------------:|:-------------:|:-----------------:|:-------------:|:------------:|:-------------:|
| dbt project YAML | X | | | | | | | | | |
| LookML | | X | | | | | | | | |
| Raw DDL | | | X | X | X | | | | X | |
| CSV/Parquet | X (seeds) | | | | | | | | | |
| Django models | | | | | | X | | | | |
| SQLAlchemy | | | | | | | X | | | |
| Prisma | | | | | | | | X | | |
| SQLite | | | | | | | | | | X |

**Coverage:** All 8 active parsers (dbt, lookml, ddl, django, sqlalchemy, prisma, sqlite, csv) have at least one committed fixture.

## Auto-Discovery Coverage

The `boyce init` wizard's data source discovery (`discovery.py`) is tested against these
fixtures in `boyce/tests/test_discovery.py`. The test suite verifies:
- Detection: each fixture is correctly identified by parser type
- Path resolution: directory→file mapping for Django/SQLAlchemy/Prisma
- Ingestion: full detect→parse→save pipeline produces valid snapshots
- Walk behavior: deduplication, confidence sorting, empty/nonexistent roots

## Data Characteristics

### jaffle_shop (best general-purpose fixture)
- `raw_customers`: 100 rows, clean
- `raw_orders`: 99 rows, includes `amount = 0.00` on cancelled order (row 74)
- `raw_payments`: 113 rows, multiple payments per order possible
- FK: `orders.customer_id -> customers.id`
- Status values: `placed`, `shipped`, `completed`, `return_pending`, `returned`
- dbt model derivations: `customers.number_of_orders`, `customers.total_order_amount`

### thelook_lookml (most join-rich)
- 5 entities: `users`, `orders`, `order_items`, `inventory_items`, `products`
- 6 join relationships defined in `.model.lkml`
- Derived dimensions using correlated subqueries
- `returned_at` nullable (sparse returns — potential NULL trap test)
- No seed data (LookML structure only)

### airflow_analytics (multi-file DDL, FK chains)
- 8 tables: 3 dimensions (customers, products, dates) + 1 bridge (channels) + 3 fact (orders, order_items, payments) + 1 session fact
- FK chains: fact_orders → dim_customers, dim_dates; fact_order_items → fact_orders, dim_products
- Redshift-compatible DDL (GETDATE(), DECIMAL, BOOLEAN)
- Numbered files simulate Airflow DAG task ordering

### sample_sqlite (live profiling)
- 5 tables: customers, products, orders, order_items, reviews
- Seed data included (3 customers, 3 products, 3 orders, 4 line items, 2 reviews)
- NULL values present (Carol White has NULL email, one review has NULL comment)
- Supports live profiling and NULL trap detection testing

### northwind_ddl (classic retail, T-SQL)
- 14 tables: Categories, Customers, Employees, Orders, OrderDetails, Products, Shippers, Suppliers, etc.
- Rich FK web: Orders -> Customers, Orders -> Employees, OrderDetails -> Orders, OrderDetails -> Products, etc.
- Includes INSERT statements for seed data
- T-SQL dialect — DDL parser must handle T-SQL CREATE TABLE syntax

### wide_world_importers_ddl (star schema)
- Fact tables: Sale, Order, Purchase, Movement, Transaction, StockHolding
- Dimension tables: Customer, City, Date, Employee, PaymentMethod, StockItem, Supplier, TransactionType
- Classic star schema pattern for data warehouse testing
- T-SQL dialect with schema-qualified names (Fact., Dimension., Integration.)

## Updating Fixtures

Committed fixtures are pinned to specific versions. To update:
1. Check the upstream repo for breaking changes
2. Copy new version, verify parsers still produce valid snapshots
3. Update this README with any schema changes

Cloned fixtures update via `./setup.sh` (pulls latest).

## Adding New Fixtures

When adding a new test warehouse:
1. Determine if it should be committed (<1 MB) or cloned (>1 MB)
2. If committed: copy contents (excluding `.git/`) into a named directory
3. If cloned: add to `setup.sh` and `.gitignore`
4. Update the fixture inventory table above
5. Update the parser validation matrix
6. Document data characteristics if non-trivial
