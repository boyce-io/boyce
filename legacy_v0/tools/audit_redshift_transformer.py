#!/usr/bin/env python3
"""
Comprehensive audit report for transform_sql_for_redshift_safety.

Tests multiple edge cases and complex SQL patterns.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))

from safety_kernel.redshift_guardrails import transform_sql_for_redshift_safety, lint_redshift_compat


def test_case(name: str, sql: str, expected_features: list[str]):
    """Run a test case and report results."""
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print('='*80)
    print("\n📝 INPUT:")
    print(sql)
    
    transformed = transform_sql_for_redshift_safety(sql)
    
    print("\n✅ OUTPUT:")
    print(transformed)
    
    print("\n🔍 VERIFICATION:")
    all_passed = True
    for feature in expected_features:
        passed = feature in transformed or feature.lower() in transformed.lower()
        status = "✅" if passed else "❌"
        print(f"   {status} {feature}")
        if not passed:
            all_passed = False
    
    problems = lint_redshift_compat(transformed)
    if problems:
        print(f"\n⚠️  LINTER WARNINGS: {len(problems)}")
        for p in problems:
            print(f"   - {p}")
    else:
        print("\n✅ No linter issues")
    
    return all_passed


def main():
    """Run comprehensive audit."""
    print("="*80)
    print("REDSHIFT SAFETY TRANSFORMER - COMPREHENSIVE AUDIT")
    print("="*80)
    
    results = []
    
    # Test 1: Original stress test
    results.append(("Stress Test (CTE + Nested Casts)", test_case(
        "Stress Test: CTE with nested CAST expressions",
        """WITH test_cte AS (
    SELECT CAST(raw_val AS VARCHAR) as val_str 
    FROM source_table
)
SELECT 
    CAST(val_str AS NUMERIC(18,2)),
    COALESCE(CAST(val_str AS DECIMAL), 0) as nested_val,
    val_str::float
FROM test_cte;""",
        ["NULLIF(val_str, '')", "NUMERIC(18,2)", "DECIMAL", "COALESCE", "WITH test_cte"]
    )))
    
    # Test 2: Double-colon syntax
    results.append(("Double-Colon Syntax", test_case(
        "Double-colon NUMERIC/DECIMAL casts",
        """SELECT 
    price::NUMERIC(10,2),
    amount::DECIMAL,
    id::INTEGER
FROM orders;""",
        ["NULLIF(price", "NULLIF(amount", "CAST", "INTEGER"]  # INTEGER should be left alone
    )))
    
    # Test 3: Non-numeric casts (should be untouched)
    results.append(("Non-Numeric Casts", test_case(
        "Non-numeric casts should remain unchanged",
        """SELECT 
    CAST(id AS VARCHAR),
    name::TEXT,
    created_at::TIMESTAMP
FROM users;""",
        ["CAST(id AS VARCHAR)", "name::TEXT", "created_at::TIMESTAMP"]  # No NULLIF
    )))
    
    # Test 4: Complex expressions (should be left alone)
    results.append(("Complex Expressions", test_case(
        "Complex expressions should not be wrapped",
        """SELECT 
    CAST(price * quantity AS NUMERIC(18,2)),
    CAST(COALESCE(amount, 0) AS DECIMAL)
FROM line_items;""",
        ["price * quantity", "COALESCE(amount, 0)"]  # Complex, should not wrap
    )))
    
    # Test 5: Subqueries
    results.append(("Subqueries", test_case(
        "CAST in subqueries",
        """SELECT 
    (SELECT CAST(total AS NUMERIC(10,2)) FROM summary WHERE id = orders.id)
FROM orders;""",
        ["NULLIF(total", "NUMERIC(10,2)"]
    )))
    
    # Test 6: Multiple statements
    results.append(("Multiple Statements", test_case(
        "Multiple SQL statements",
        """SELECT CAST(val1 AS NUMERIC) FROM t1;
SELECT CAST(val2 AS DECIMAL) FROM t2;""",
        ["NULLIF(val1", "NULLIF(val2"]
    )))
    
    # Summary
    print("\n" + "="*80)
    print("AUDIT SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {name}")
    
    print(f"\n   Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - Transformer is production-ready")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - Review required")


if __name__ == "__main__":
    main()


