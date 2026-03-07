#!/usr/bin/env python3
"""Debug script to see what sqlparse produces for the test SQL."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))

import sqlparse
from sqlparse.sql import Token, TokenList
from sqlparse import tokens as T

evil_sql = """WITH test_cte AS (
    SELECT CAST(raw_val AS VARCHAR) as val_str 
    FROM source_table
)
SELECT 
    CAST(val_str AS NUMERIC(18,2)),
    COALESCE(CAST(val_str AS DECIMAL), 0) as nested_val,
    val_str::float
FROM test_cte;"""

print("=" * 80)
print("SQLPARSE TOKEN ANALYSIS")
print("=" * 80)
print("\nOriginal SQL:")
print(evil_sql)
print("\n" + "=" * 80)

parsed = sqlparse.parse(evil_sql)
for i, stmt in enumerate(parsed):
    print(f"\nStatement {i+1}:")
    print("-" * 80)
    
    def print_tokens(tokens, indent=0):
        for token in tokens:
            prefix = "  " * indent
            if isinstance(token, TokenList):
                print(f"{prefix}TokenList: {token.ttype} | {token.value[:60]}")
                print_tokens(token.tokens, indent + 1)
            else:
                ttype_str = str(token.ttype) if token.ttype else "None"
                value_preview = repr(token.value[:60]) if len(token.value) > 60 else repr(token.value)
                print(f"{prefix}Token: {ttype_str:30} | {value_preview}")
    
    print_tokens(stmt.tokens)
    
    print("\nFlattened tokens:")
    print("-" * 80)
    for tok in stmt.flatten():
        ttype_str = str(tok.ttype) if tok.ttype else "None"
        value_preview = repr(tok.value[:80])
        print(f"  {ttype_str:30} | {value_preview}")


