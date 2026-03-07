# Golden Query Harness

Sprint 3A implementation: Golden Query Harness for validating deterministic SQL generation.

## Overview

The Golden Query Harness runs canonical queries (Q1-Q3) and validates:
- Engine generates SQL deterministically
- Audit artifacts are emitted (Contract A: one record per file)
- Generated SQL matches approved baselines

## Running the Harness

### Basic Usage

```bash
cd datashark-mcp
PYTHONPATH=src python3 tools/golden_harness.py
```

### Update Baselines

When making intentional changes to SQL generation:

```bash
PYTHONPATH=src python3 tools/golden_harness.py --update-baselines
```

This will:
1. Run all golden queries
2. Generate SQL for each
3. Update baseline files in `tests/golden_baselines/` with the new SQL
4. You should review and commit the updated baselines

### Custom Directories

```bash
# Custom baseline directory
PYTHONPATH=src python3 tools/golden_harness.py --baseline-dir /path/to/baselines

# Custom audit directory
PYTHONPATH=src python3 tools/golden_harness.py --audit-dir /path/to/audit
```

## Golden Queries

### Q1: Revenue by Category (Trailing 12 Months)
**Query:** "Total sales revenue by product category for the last 12 months."

**Tests:**
- Temporal filter (trailing_interval: 12 months)
- Single join (orders → products)
- Aggregation by category

### Q2: Monthly Revenue with Filter
**Query:** "Total sales revenue by month for 'Electronics' items throughout 2024."

**Tests:**
- Temporal filter (BETWEEN dates)
- Category filter (= 'Electronics')
- DATE_TRUNC by month
- Multi-table join (orders → order_items → products)

### Q3: LEFT JOIN with Zero-Value Detection
**Query:** "Show me all customers and their total order count, including customers who have never placed an order."

**Tests:**
- LEFT JOIN semantics (customers → orders)
- Zero-value detection (customers with no orders)
- COUNT aggregation with GROUP BY

## Baseline Files

Baselines are stored in `tests/golden_baselines/`:
- `Q1.sql` - Approved SQL for Q1
- `Q2.sql` - Approved SQL for Q2
- `Q3.sql` - Approved SQL for Q3

Baselines are plain SQL files. The harness normalizes whitespace for comparison, but semantic changes will be detected.

## Audit Artifacts

The harness validates that:
- Each query generates exactly one audit file (Contract A: one record per file)
- Audit file contains: input_query, generated_sql, snapshot_id, timestamp, request_id
- Audit file is valid JSONL (single line)

## Running Tests

```bash
cd datashark-mcp
PYTHONPATH=src python3 -m pytest tests/test_golden_harness.py -v
```

Tests validate:
- SQL generation works
- Audit artifacts are emitted
- Baselines can be matched
- Each query creates a separate audit file

## Extending to More Queries

To add Q3-Q5:

1. Add query definition to `GOLDEN_QUERIES` dict in `tools/golden_harness.py`
2. Create `create_lookml_for_q3()` function with appropriate LookML structure
3. Add LookML data to `lookml_data` dict in `main()`
4. Create baseline file `tests/golden_baselines/Q3.sql`
5. Run harness to validate

## Future: Result Hashing (Phase 2)

The harness is designed to be extensible. Future work can add:
- SQL execution against test database
- Result set hashing
- Comparison of result hashes against baselines
- This is deferred to Phase 2 per Sprint 3A scope

