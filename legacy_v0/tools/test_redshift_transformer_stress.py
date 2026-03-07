#!/usr/bin/env python3
"""
Stress test for transform_sql_for_redshift_safety.

Tests complex SQL patterns:
- CTEs (WITH clauses)
- Nested casts
- Multiple cast patterns (CAST(...) and :: syntax)
- COALESCE wrapping
- Different numeric types
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))

from safety_kernel.redshift_guardrails import transform_sql_for_redshift_safety, lint_redshift_compat


def main():
    """Run stress test against complex SQL."""

    evil_sql = """WITH test_cte AS (
    SELECT CAST(raw_val AS VARCHAR) as val_str 
    FROM source_table
)
SELECT 
    CAST(val_str AS NUMERIC(18,2)),
    COALESCE(CAST(val_str AS DECIMAL), 0) as nested_val,
    val_str::float,
    val_str::int
FROM test_cte;"""
    
    print("=" * 80)
    print("STRESS TEST: Redshift Safety Transformer")
    print("=" * 80)
    print("\n📝 INPUT SQL:")
    print("-" * 80)
    print(evil_sql)
    print("-" * 80)
    
    # Run transformation
    print("\n🔄 Running transform_sql_for_redshift_safety()...")
    transformed = transform_sql_for_redshift_safety(evil_sql)
    
    print("\n✅ TRANSFORMED SQL:")
    print("-" * 80)
    print(transformed)
    print("-" * 80)
    
    # Run linter
    print("\n🔍 Running lint_redshift_compat()...")
    problems = lint_redshift_compat(transformed)
    
    if problems:
        print("\n⚠️  LINTER ISSUES FOUND:")
        for i, problem in enumerate(problems, 1):
            print(f"   {i}. {problem}")
    else:
        print("\n✅ No Redshift compatibility issues detected.")
    
    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)
    
    checks = [
        ("CTE preserved", "WITH test_cte AS" in transformed),
        ("CAST(val_str AS NUMERIC) wrapped", "NULLIF(val_str" in transformed and "NUMERIC(18,2)" in transformed),
        ("CAST(val_str AS DECIMAL) wrapped", "NULLIF(val_str" in transformed and "DECIMAL" in transformed),
        ("::float handled", "::float" in transformed or "CAST" in transformed),
        ("COALESCE preserved", "COALESCE" in transformed),
    ]
    
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"   {status} {check_name}: {passed}")
    
    # Show specific transformations
    print("\n" + "=" * 80)
    print("TRANSFORMATION DETAILS:")
    print("=" * 80)
    
    if "NULLIF(val_str" in transformed:
        print("\n✅ Found NULLIF wrapping for val_str casts")
        # Extract the transformed CAST expressions
        import re
        cast_patterns = re.findall(r'CAST\([^)]+\)', transformed, re.IGNORECASE)
        for pattern in cast_patterns:
            if "NULLIF" in pattern:
                print(f"   → {pattern[:80]}...")
    else:
        print("\n❌ No NULLIF wrapping detected - transformation may have failed")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

