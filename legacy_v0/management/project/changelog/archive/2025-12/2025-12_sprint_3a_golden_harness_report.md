# Sprint 3A Implementation Report: Golden Query Harness

## Summary

Implemented Golden Query Harness (Sprint 3A) for validating deterministic SQL generation against approved baselines.

## Files Created

### 1. `datashark-mcp/tools/golden_harness.py`
**Purpose:** Main harness script that runs golden queries Q1-Q2 and validates SQL against baselines.

**Key Features:**
- Runs queries through `engine.process_request()` (exercises artifact logger)
- Validates audit artifacts are emitted (Contract A: one record per file)
- Compares generated SQL to approved baselines
- Supports `--update-baselines` flag for intentional baseline updates
- Normalizes SQL for comparison (whitespace handling)

**Golden Queries:**
- **Q1:** "Total sales revenue by product category for the last 12 months."
- **Q2:** "Total sales revenue by month for 'Electronics' items throughout 2024."
- **Q3:** "Show me all customers and their total order count, including customers who have never placed an order." (Added in Sprint 3B)

### 2. `datashark-mcp/tests/golden_baselines/`
**Purpose:** Directory for approved baseline SQL files.

**Files:**
- `README.md` - Documentation on baseline format and update process
- `Q1.sql` - Approved SQL for Q1
- `Q2.sql` - Approved SQL for Q2
- `Q3.sql` - Approved SQL for Q3 (added in Sprint 3B)

### 3. `datashark-mcp/tests/test_golden_harness.py`
**Purpose:** Unit tests for harness functionality.

**Test Coverage:**
- `test_normalize_sql()` - SQL normalization for comparison
- `test_golden_query_q1_audit_artifact()` - Q1 generates SQL and audit artifact
- `test_golden_query_q2_audit_artifact()` - Q2 generates SQL and audit artifact
- `test_golden_query_baseline_matching()` - Baseline matching logic
- `test_audit_file_per_query()` - Contract A validation (one file per query)

### 4. `datashark-mcp/tools/README_GOLDEN_HARNESS.md`
**Purpose:** User documentation for running and extending the harness.

## How to Run

### Basic Validation Run
```bash
cd datashark-mcp
PYTHONPATH=src python3 tools/golden_harness.py
```

### Update Baselines (After Intentional SQL Changes)
```bash
cd datashark-mcp
PYTHONPATH=src python3 tools/golden_harness.py --update-baselines
```

**Process:**
1. Review the generated SQL output
2. If correct, the baselines will be updated automatically
3. Commit the updated baseline files to version control

### Run Tests
```bash
cd datashark-mcp
PYTHONPATH=src python3 -m pytest tests/test_golden_harness.py -v
```

## Validation Checks

The harness validates:

1. **SQL Generation:** Engine successfully generates SQL for each query
2. **Audit Artifacts:** 
   - Exactly one audit file per query (Contract A)
   - Audit file contains: input_query, generated_sql, snapshot_id, timestamp, request_id
   - Audit file is valid JSONL (single line)
3. **Baseline Matching:**
   - Generated SQL matches approved baseline (with normalization)
   - Or creates baseline if missing (with --update-baselines)

## Contract: SQL Comparison

**Current:** Exact match with whitespace normalization.

The harness normalizes SQL by:
- Stripping leading/trailing whitespace
- Normalizing line breaks
- Preserving semantic structure

**Future (Phase 2):** Can extend to canonicalized SQL comparison or result hashing.

## Extending to Q3-Q5

To add more golden queries:

1. Add query to `GOLDEN_QUERIES` dict in `golden_harness.py`
2. Create `create_lookml_for_q3()` function
3. Add to `lookml_data` dict in `main()`
4. Create baseline file `tests/golden_baselines/Q3.sql`
5. Run harness to validate

## Known Limitations

1. **Metadata Conversion:** The harness converts `SemanticSnapshot` (from LookerAdapter) to `raw_metadata` format for the engine. This conversion may need refinement as the engine's metadata format evolves.

2. **SQL Normalization:** Current normalization is basic (whitespace only). More sophisticated canonicalization may be needed for complex SQL.

3. **No Execution:** Harness validates SQL generation, not SQL correctness. Phase 2 can add execution + result hashing.

4. **Single Process:** Assumes single-process execution. Multi-process concurrency not tested.

## Status: READY

Sprint 3A (Golden Query Harness) is implemented and ready for use. Baselines will be created on first run with `--update-baselines`.

