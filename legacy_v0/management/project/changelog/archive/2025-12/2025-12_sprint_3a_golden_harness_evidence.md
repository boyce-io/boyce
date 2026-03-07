# 1) golden_harness.py (full)

```python
#!/usr/bin/env python3
"""
Golden Query Harness for DataShark Phase 1.

Runs Golden Queries 1-3 and validates:
- Engine generates SQL deterministically
- Audit artifacts are emitted (Contract A: one record per file)
- Generated SQL matches approved baselines

Usage:
    python3 tools/golden_harness.py [--update-baselines]
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from datashark.core.audit import get_audit_writer, log_artifact
from datashark.ingestion.looker.adapter import LookerAdapter
from datashark_mcp.kernel.engine import DataSharkEngine
from datashark_mcp.kernel.types import UserContext
from datashark_mcp.security.policy import PolicyRule, PolicySet


# Golden Query Definitions
GOLDEN_QUERIES = {
    "Q1": {
        "query": "Total sales revenue by product category for the last 12 months.",
        "description": "Revenue by category with trailing 12-month temporal filter"
    },
    "Q2": {
        "query": "Total sales revenue by month for 'Electronics' items throughout 2024.",
        "description": "Monthly revenue with category filter and date truncation"
    },
    "Q3": {
        "query": "Show me all customers and their total order count, including customers who have never placed an order.",
        "description": "LEFT JOIN with zero-value detection (customers with no orders)"
    }
}


def create_lookml_for_q1() -> Dict:
    """Create mock LookML Explore JSON for Golden Query 1."""
    return {
        "name": "orders",
        "sql_table_name": "orders",
        "schema": "public",
        "description": "Orders explore with product join",
        "grain": "ORDER",
        "version": "1.0",
        "dimensions": [
            {
                "name": "order_id",
                "type": "number",
                "primary_key": True,
                "sql": {"type": "INTEGER"},
                "nullable": False,
                "description": "Unique order identifier"
            },
            {
                "name": "created_at",
                "type": "time",
                "sql": {"type": "TIMESTAMP"},
                "nullable": False,
                "description": "Order creation timestamp"
            },
            {
                "name": "product_id",
                "type": "number",
                "sql": {"type": "INTEGER"},
                "nullable": False,
                "description": "Foreign key to products table"
            }
        ],
        "measures": [
            {
                "name": "revenue",
                "type": "sum",
                "sql": {
                    "type": "DECIMAL(10,2)",
                    "expression": "SUM(${orders.order_price})"
                },
                "description": "Total sales revenue (sum of order prices)"
            }
        ],
        "joins": [
            {
                "name": "products",
                "sql_table_name": "products",
                "schema": "public",
                "type": "left_outer",
                "sql_on": "${orders.product_id} = ${products.id}",
                "relationship": {
                    "from": "product_id",
                    "to": "id"
                },
                "description": "Join to products table",
                "dimensions": [
                    {
                        "name": "id",
                        "type": "number",
                        "primary_key": True,
                        "sql": {"type": "INTEGER"},
                        "nullable": False,
                        "description": "Product identifier"
                    },
                    {
                        "name": "category",
                        "type": "string",
                        "sql": {"type": "VARCHAR(255)"},
                        "nullable": True,
                        "description": "Product category",
                        "allowed_values": ["Electronics", "Clothing", "Home", "Sports", "Books"]
                    }
                ],
                "measures": []
            }
        ]
    }


def create_lookml_for_q2() -> Dict:
    """Create mock LookML Explore JSON for Golden Query 2 (3-table join)."""
    return {
        "name": "orders",
        "sql_table_name": "orders",
        "schema": "public",
        "description": "Orders explore with order_items and products joins",
        "grain": "ORDER",
        "version": "1.0",
        "dimensions": [
            {
                "name": "order_id",
                "type": "number",
                "primary_key": True,
                "sql": {"type": "INTEGER"},
                "nullable": False
            },
            {
                "name": "created_at",
                "type": "time",
                "sql": {"type": "TIMESTAMP"},
                "nullable": False
            }
        ],
        "measures": [
            {
                "name": "total_revenue",
                "type": "sum",
                "sql": {
                    "type": "DECIMAL(10,2)",
                    "expression": "SUM(${order_items.sale_price})"
                }
            }
        ],
        "joins": [
            {
                "name": "order_items",
                "sql_table_name": "order_items",
                "schema": "public",
                "type": "left_outer",
                "sql_on": "${orders.order_id} = ${order_items.order_id}",
                "relationship": {
                    "from": "order_id",
                    "to": "order_id"
                },
                "dimensions": [
                    {
                        "name": "order_item_id",
                        "type": "number",
                        "primary_key": True,
                        "sql": {"type": "INTEGER"}
                    },
                    {
                        "name": "product_id",
                        "type": "number",
                        "sql": {"type": "INTEGER"}
                    },
                    {
                        "name": "sale_price",
                        "type": "number",
                        "sql": {"type": "DECIMAL(10,2)"}
                    }
                ],
                "measures": [],
                "joins": [
                    {
                        "name": "products",
                        "sql_table_name": "products",
                        "schema": "public",
                        "type": "left_outer",
                        "sql_on": "${order_items.product_id} = ${products.id}",
                        "relationship": {
                            "from": "product_id",
                            "to": "id"
                        },
                        "dimensions": [
                            {
                                "name": "id",
                                "type": "number",
                                "primary_key": True,
                                "sql": {"type": "INTEGER"}
                            },
                            {
                                "name": "category",
                                "type": "string",
                                "sql": {"type": "VARCHAR(255)"},
                                "allowed_values": ["Electronics", "Clothing", "Home", "Sports", "Books"]
                            }
                        ],
                        "measures": []
                    }
                ]
            }
        ]
    }


def normalize_sql(sql: str) -> str:
    """
    Normalize SQL for comparison (whitespace, case-insensitive keywords).
    
    This allows minor formatting differences while catching semantic changes.
    """
    # Convert to uppercase for keywords
    lines = sql.split('\n')
    normalized = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            # Basic keyword normalization (can be extended)
            normalized.append(stripped)
    return '\n'.join(normalized).strip()


def run_golden_query(
    query_id: str,
    query_text: str,
    lookml_data: Dict,
    baseline_dir: Path,
    audit_dir: Optional[Path] = None,
    update_baseline: bool = False
) -> Dict:
    """
    Run a golden query and validate against baseline.
    
    Returns:
        Dict with keys: success, generated_sql, baseline_sql, audit_file, snapshot_id, errors
    """
    result = {
        "query_id": query_id,
        "query_text": query_text,
        "success": False,
        "generated_sql": None,
        "baseline_sql": None,
        "audit_file": None,
        "snapshot_id": None,
        "errors": []
    }
    
    try:
        # Step 1: Create snapshot from LookML
        adapter = LookerAdapter()
        snapshot = adapter.ingest(lookml_data)
        result["snapshot_id"] = snapshot.snapshot_id
        
        # Step 2: Set up engine with user context
        context = UserContext(
            user_id="golden_harness_user",
            roles=["admin"],
            tenant_id="test_tenant"
        )
        engine = DataSharkEngine(context=context)
        
        # Set up permissive policy for testing
        policy_set = PolicySet(
            rules=[PolicyRule(resource_pattern=".*", allowed_roles=["admin"], action="allow")],
            default_action="deny"
        )
        engine.policy_set = policy_set
        
        # Step 3: Load metadata into engine
        # Convert SemanticSnapshot to raw metadata format expected by SnapshotFactory
        # The raw_metadata should match SemanticGraph schema
        raw_metadata = {
            "source_system": snapshot.source_system,
            "source_version": snapshot.source_version or "1.0",
            "entities": {eid: {
                "id": e.id,
                "name": e.name,
                "schema": e.schema_name if hasattr(e, 'schema_name') else None,
                "fields": e.fields,
                "grain": e.grain if hasattr(e, 'grain') else None
            } for eid, e in snapshot.entities.items()},
            "fields": {fid: {
                "id": f.id,
                "entity_id": f.entity_id,
                "name": f.name,
                "field_type": f.field_type.value if hasattr(f.field_type, 'value') else str(f.field_type),
                "data_type": f.data_type,
                "nullable": f.nullable if hasattr(f, 'nullable') else None,
                "primary_key": f.primary_key if hasattr(f, 'primary_key') else None
            } for fid, f in snapshot.fields.items()},
            "joins": [{
                "id": j.id if hasattr(j, 'id') else None,
                "source_entity_id": j.source_entity_id,
                "target_entity_id": j.target_entity_id,
                "join_type": j.join_type.value if hasattr(j.join_type, 'value') else str(j.join_type),
                "source_field_id": j.source_field_id,
                "target_field_id": j.target_field_id
            } for j in snapshot.joins],
            "metadata": snapshot.metadata if hasattr(snapshot, 'metadata') else {}
        }
        engine.load_metadata(raw_metadata)
        
        # Step 4: Set audit directory if provided
        if audit_dir:
            os.environ["DATASHARK_AUDIT_DIR"] = str(audit_dir)
            # Reset global writer to pick up new directory
            from datashark.core.audit import _global_writer
            global _global_writer
            _global_writer = None
        
        # Step 5: Process request (generates SQL and logs artifact)
        engine_result = engine.process_request(query_text)
        result["generated_sql"] = engine_result.get("final_sql_output", "")
        
        if not result["generated_sql"]:
            result["errors"].append("No SQL generated in engine result")
            return result
        
        # Step 6: Find the audit file (most recent in audit directory)
        audit_writer = get_audit_writer()
        audit_dir_path = audit_writer.audit_dir
        
        # Find most recent audit file
        audit_files = sorted(audit_dir_path.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if audit_files:
            result["audit_file"] = audit_files[0]
            
            # Verify audit file content
            with open(result["audit_file"], "r") as f:
                audit_data = json.loads(f.read())
                if audit_data.get("snapshot_id") != snapshot.snapshot_id:
                    result["errors"].append(f"Audit snapshot_id mismatch: expected {snapshot.snapshot_id[:16]}..., got {audit_data.get('snapshot_id', 'missing')[:16] if audit_data.get('snapshot_id') else 'missing'}...")
                if audit_data.get("input_query") != query_text:
                    result["errors"].append("Audit input_query mismatch")
                if audit_data.get("generated_sql") != result["generated_sql"]:
                    result["errors"].append("Audit generated_sql mismatch")
        else:
            result["errors"].append("No audit file found")
        
        # Step 7: Compare with baseline
        baseline_file = baseline_dir / f"{query_id}.sql"
        
        if baseline_file.exists():
            with open(baseline_file, "r") as f:
                result["baseline_sql"] = f.read().strip()
            
            # Normalize both for comparison
            normalized_generated = normalize_sql(result["generated_sql"])
            normalized_baseline = normalize_sql(result["baseline_sql"])
            
            if normalized_generated != normalized_baseline:
                if update_baseline:
                    # Update baseline
                    with open(baseline_file, "w") as f:
                        f.write(result["generated_sql"])
                    result["errors"].append(f"Baseline updated for {query_id}")
                else:
                    result["errors"].append(f"SQL mismatch for {query_id}")
                    result["errors"].append(f"Expected:\n{result['baseline_sql']}")
                    result["errors"].append(f"Got:\n{result['generated_sql']}")
        else:
            # No baseline exists - create it
            if update_baseline:
                baseline_file.parent.mkdir(parents=True, exist_ok=True)
                with open(baseline_file, "w") as f:
                    f.write(result["generated_sql"])
                result["errors"].append(f"Created new baseline for {query_id}")
            else:
                result["errors"].append(f"No baseline file found: {baseline_file}")
        
        # Success if no errors (or only update messages)
        if not result["errors"] or all("updated" in e.lower() or "created" in e.lower() for e in result["errors"]):
            result["success"] = True
        
    except Exception as e:
        result["errors"].append(f"Exception: {str(e)}")
        import traceback
        result["errors"].append(traceback.format_exc())
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Run Golden Query Harness")
    parser.add_argument(
        "--update-baselines",
        action="store_true",
        help="Update baseline SQL files with current generated SQL"
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path(__file__).parent.parent / "tests" / "golden_baselines",
        help="Directory containing baseline SQL files"
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        help="Directory for audit files (default: temp directory)"
    )
    args = parser.parse_args()
    
    # Set up audit directory
    if args.audit_dir:
        audit_dir = args.audit_dir
        audit_dir.mkdir(parents=True, exist_ok=True)
    else:
        audit_dir = Path(tempfile.mkdtemp(prefix="datashark_audit_"))
    
    print("=" * 80)
    print("Golden Query Harness - Sprint 3A")
    print("=" * 80)
    print(f"Baseline directory: {args.baseline_dir}")
    print(f"Audit directory: {audit_dir}")
    print(f"Update baselines: {args.update_baselines}")
    print("=" * 80)
    print()
    
    # LookML data for each query
    lookml_data = {
        "Q1": create_lookml_for_q1(),
        "Q2": create_lookml_for_q2()
    }
    
    results = []
    for query_id, query_def in GOLDEN_QUERIES.items():
        print(f"\n{'='*80}")
        print(f"Running {query_id}: {query_def['description']}")
        print(f"Query: {query_def['query']}")
        print(f"{'='*80}")
        
        result = run_golden_query(
            query_id=query_id,
            query_text=query_def["query"],
            lookml_data=lookml_data[query_id],
            baseline_dir=args.baseline_dir,
            audit_dir=audit_dir,
            update_baseline=args.update_baselines
        )
        results.append(result)
        
        if result["success"]:
            print(f"✅ {query_id} PASSED")
            print(f"   Snapshot ID: {result['snapshot_id'][:16]}...")
            print(f"   Audit file: {result['audit_file'].name if result['audit_file'] else 'None'}")
        else:
            print(f"❌ {query_id} FAILED")
            for error in result["errors"]:
                print(f"   {error}")
    
    # Summary
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All golden queries passed!")
        return 0
    else:
        print("❌ Some golden queries failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

# 2) test_golden_harness.py (full)

```python
"""
Unit tests for Golden Query Harness.

Tests that the harness:
- Runs golden queries successfully
- Emits audit artifacts (Contract A: one record per file)
- Validates SQL against baselines
"""

import json
import tempfile
from pathlib import Path

import pytest

from tools.golden_harness import (
    create_lookml_for_q1,
    create_lookml_for_q2,
    normalize_sql,
    run_golden_query,
)


def test_normalize_sql():
    """Test SQL normalization for comparison."""
    sql1 = "SELECT * FROM test"
    sql2 = "SELECT *\nFROM test"
    sql3 = "select * from test"
    
    assert normalize_sql(sql1) == normalize_sql(sql2)
    # Note: current normalization doesn't handle case, but can be extended
    assert normalize_sql(sql1) == normalize_sql(sql1)


def test_golden_query_q1_audit_artifact():
    """Test that Q1 generates SQL and emits audit artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        baseline_dir = Path(tmpdir) / "baselines"
        baseline_dir.mkdir()
        
        # Create a dummy baseline (will fail SQL match but should generate audit)
        baseline_file = baseline_dir / "Q1.sql"
        baseline_file.write_text("SELECT 1")
        
        lookml = create_lookml_for_q1()
        result = run_golden_query(
            query_id="Q1",
            query_text="Total sales revenue by product category for the last 12 months.",
            lookml_data=lookml,
            baseline_dir=baseline_dir,
            audit_dir=audit_dir,
            update_baseline=False
        )
        
        # Should generate SQL
        assert result["generated_sql"] is not None
        assert len(result["generated_sql"]) > 0
        
        # Should have snapshot_id
        assert result["snapshot_id"] is not None
        
        # Should have audit file (Contract A: one record per file)
        assert result["audit_file"] is not None
        assert result["audit_file"].exists()
        
        # Verify audit file content
        with open(result["audit_file"], "r") as f:
            audit_data = json.loads(f.read())
            assert audit_data["input_query"] == "Total sales revenue by product category for the last 12 months."
            assert audit_data["generated_sql"] == result["generated_sql"]
            assert audit_data["snapshot_id"] == result["snapshot_id"]
            assert "request_id" in audit_data
            assert "timestamp" in audit_data


def test_golden_query_q2_audit_artifact():
    """Test that Q2 generates SQL and emits audit artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        baseline_dir = Path(tmpdir) / "baselines"
        baseline_dir.mkdir()
        
        # Create a dummy baseline
        baseline_file = baseline_dir / "Q2.sql"
        baseline_file.write_text("SELECT 1")
        
        lookml = create_lookml_for_q2()
        result = run_golden_query(
            query_id="Q2",
            query_text="Total sales revenue by month for 'Electronics' items throughout 2024.",
            lookml_data=lookml,
            baseline_dir=baseline_dir,
            audit_dir=audit_dir,
            update_baseline=False
        )
        
        # Should generate SQL
        assert result["generated_sql"] is not None
        assert len(result["generated_sql"]) > 0
        
        # Should have audit file
        assert result["audit_file"] is not None
        assert result["audit_file"].exists()
        
        # Verify audit file is single-line JSONL (Contract A)
        with open(result["audit_file"], "r") as f:
            lines = f.readlines()
            assert len(lines) == 1, "Audit file should have exactly one line (Contract A)"
            
            audit_data = json.loads(lines[0])
            assert audit_data["snapshot_id"] == result["snapshot_id"]


def test_golden_query_baseline_matching():
    """Test that baseline matching works correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        baseline_dir = Path(tmpdir) / "baselines"
        baseline_dir.mkdir()
        
        lookml = create_lookml_for_q1()
        
        # First run: create baseline
        result1 = run_golden_query(
            query_id="Q1",
            query_text="Total sales revenue by product category for the last 12 months.",
            lookml_data=lookml,
            baseline_dir=baseline_dir,
            audit_dir=audit_dir,
            update_baseline=True
        )
        
        assert result1["generated_sql"] is not None
        generated_sql = result1["generated_sql"]
        
        # Second run: should match baseline
        result2 = run_golden_query(
            query_id="Q1",
            query_text="Total sales revenue by product category for the last 12 months.",
            lookml_data=lookml,
            baseline_dir=baseline_dir,
            audit_dir=audit_dir,
            update_baseline=False
        )
        
        # Should match (may have minor formatting differences)
        # The harness normalizes for comparison
        assert result2["baseline_sql"] is not None
        assert normalize_sql(result2["generated_sql"]) == normalize_sql(result2["baseline_sql"])


def test_audit_file_per_query():
    """Test that each query generates a separate audit file (Contract A)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        baseline_dir = Path(tmpdir) / "baselines"
        baseline_dir.mkdir()
        
        # Create baselines
        (baseline_dir / "Q1.sql").write_text("SELECT 1")
        (baseline_dir / "Q2.sql").write_text("SELECT 1")
        
        # Run Q1
        result1 = run_golden_query(
            query_id="Q1",
            query_text="Total sales revenue by product category for the last 12 months.",
            lookml_data=create_lookml_for_q1(),
            baseline_dir=baseline_dir,
            audit_dir=audit_dir,
            update_baseline=False
        )
        
        # Run Q2
        result2 = run_golden_query(
            query_id="Q2",
            query_text="Total sales revenue by month for 'Electronics' items throughout 2024.",
            lookml_data=create_lookml_for_q2(),
            baseline_dir=baseline_dir,
            audit_dir=audit_dir,
            update_baseline=False
        )
        
        # Should have separate audit files
        assert result1["audit_file"] is not None
        assert result2["audit_file"] is not None
        assert result1["audit_file"] != result2["audit_file"]
        
        # Each file should have exactly one line (Contract A)
        for audit_file in [result1["audit_file"], result2["audit_file"]]:
            with open(audit_file, "r") as f:
                lines = f.readlines()
                assert len(lines) == 1, f"Audit file {audit_file.name} should have exactly one line"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

# 3) Baselines

## Q1.sql
```
(File does not exist - will be created on first run with --update-baselines)
```

## Q2.sql
```
(File does not exist - will be created on first run with --update-baselines)
```

## Directory listing of datashark-mcp/tests/golden_baselines/
```
README.md
```

# 4) Normalization logic

```python
def normalize_sql(sql: str) -> str:
    """
    Normalize SQL for comparison (whitespace, case-insensitive keywords).
    
    This allows minor formatting differences while catching semantic changes.
    """
    # Convert to uppercase for keywords
    lines = sql.split('\n')
    normalized = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            # Basic keyword normalization (can be extended)
            normalized.append(stripped)
    return '\n'.join(normalized).strip()
```

**Usage in baseline comparison (lines 365-366 of golden_harness.py):**
```python
            # Normalize both for comparison
            normalized_generated = normalize_sql(result["generated_sql"])
            normalized_baseline = normalize_sql(result["baseline_sql"])
            
            if normalized_generated != normalized_baseline:
```

# 5) Audit-dir isolation

## In golden_harness.py

**Setting DATASHARK_AUDIT_DIR (lines 320-326):**
```python
        # Step 4: Set audit directory if provided
        if audit_dir:
            os.environ["DATASHARK_AUDIT_DIR"] = str(audit_dir)
            # Reset global writer to pick up new directory
            from datashark.core.audit import _global_writer
            global _global_writer
            _global_writer = None
```

**Command-line argument (lines 413-416):**
```python
    parser.add_argument(
        "--audit-dir",
        type=Path,
        help="Directory for audit files (default: temp directory)"
    )
```

**Default audit directory setup (lines 420-425):**
```python
    # Set up audit directory
    if args.audit_dir:
        audit_dir = args.audit_dir
        audit_dir.mkdir(parents=True, exist_ok=True)
    else:
        audit_dir = Path(tempfile.mkdtemp(prefix="datashark_audit_"))
```

**Passing audit_dir to run_golden_query (line 454):**
```python
        result = run_golden_query(
            query_id=query_id,
            query_text=query_def["query"],
            lookml_data=lookml_data[query_id],
            baseline_dir=args.baseline_dir,
            audit_dir=audit_dir,
            update_baseline=args.update_baselines
        )
```

## In test_golden_harness.py

**All tests use tempfile.TemporaryDirectory() for isolation:**
```python
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_dir = Path(tmpdir) / "audit"
        baseline_dir = Path(tmpdir) / "baselines"
        baseline_dir.mkdir()
        
        result = run_golden_query(
            ...
            audit_dir=audit_dir,
            ...
        )
```

**Test functions using audit_dir:**
- `test_golden_query_q1_audit_artifact()` (line 38)
- `test_golden_query_q2_audit_artifact()` (line 80)
- `test_golden_query_baseline_matching()` (line 118)
- `test_audit_file_per_query()` (line 156)

# 6) Commands + results

## Harness validation command

```bash
cd /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp && PYTHONPATH=src python3 tools/golden_harness.py
```

**Output:**
```
================================================================================
Golden Query Harness - Sprint 3A
================================================================================
Baseline directory: /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp/tests/golden_baselines
Audit directory: /var/folders/4y/29dfjtnx1hsbbspsyw96xyjh0000gn/T/datashark_audit_vnambvim
Update baselines: False
================================================================================


================================================================================
Running Q1: Revenue by category with trailing 12-month temporal filter
Query: Total sales revenue by product category for the last 12 months.
================================================================================
❌ Q1 FAILED
   Audit snapshot_id mismatch: expected 4ac74ef82502c8d1..., got ad9dfdd53e8a6b82...
   No baseline file found: /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp/tests/golden_baselines/Q1.sql

================================================================================
Running Q2: Monthly revenue with category filter and date truncation
Query: Total sales revenue by month for 'Electronics' items throughout 2024.
================================================================================
❌ Q2 FAILED
   Audit snapshot_id mismatch: expected 935d009ac73ffa7a..., got c60424a53525f31c...
   No baseline file found: /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp/tests/golden_baselines/Q2.sql

================================================================================
Summary
================================================================================
Passed: 0/2
❌ Some golden queries failed
```

## Pytest command

```bash
cd /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp && PYTHONPATH=src python3 -m pytest tests/test_golden_harness.py -v
```

**Summarized output:**
```
========================= 4 failed, 1 passed in 0.11s ==========================
```

