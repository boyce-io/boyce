"""
Redshift 1.0 guardrails and SQL transformation utilities.

Goals:
    - Harden generated SQL for legacy Redshift (PostgreSQL 8.0.2 compatible)
    - Prevent hard crashes on empty-string → NUMERIC/DECIMAL casts
    - Flag use of PostgreSQL features not supported by Redshift 1.0

Key behaviours:
    1) transform_sql_for_redshift_safety(sql: str) -> str
       - Uses sqlparse to scan the query and rewrite numeric casts into a
         NULLIF(column, '') wrapper so that Redshift does not error on ''.
       - Supports both:
            CAST(expr AS NUMERIC/DECIMAL(...))
            expr::NUMERIC / expr::DECIMAL
       - Designed for deterministically-generated SQL from Boyce
         (simple, predictable patterns), not arbitrary hand-written SQL.

    2) lint_redshift_compat(sql: str) -> list[str]
       - Returns a list of human-readable problems if the SQL uses:
            * LATERAL joins
            * JSONB types or advanced JSON functions
            * REGEXP_COUNT
            * Lookahead / lookbehind constructs in regex patterns
              (identified via '(?=' style sequences)
"""

from __future__ import annotations

import re
from typing import List

import sqlparse
from sqlparse import tokens as T


# Redshift 1.0 numeric type family that is unsafe for '' casts.
NUMERIC_TYPE_PATTERN = r"(NUMERIC|DECIMAL|INT|INTEGER|BIGINT|FLOAT|DOUBLE\\s+PRECISION)"
# Compiled regex for matching type_part in _transform_double_colon
NUMERIC_TYPE_RE = re.compile(
    r"^(NUMERIC|DECIMAL|INT|INTEGER|BIGINT|FLOAT|DOUBLE\s+PRECISION)(?:\([^)]+\))?",
    re.IGNORECASE,
)


def transform_sql_for_redshift_safety(sql: str) -> str:
    """
    Transform a SQL string to be safer on legacy Redshift.

    - Wraps numeric/decimal casts in NULLIF(..., '') to avoid errors on ''.
    - Leaves non-numeric casts untouched.

    The transformation is idempotent for already-safe SQL produced by
    this function (we avoid double-wrapping).

    Strategy:
        - Uses regex-based pattern matching on the full SQL string
        - More reliable than token-level manipulation for complex nested structures
        - Handles CTEs, subqueries, and nested expressions
    """

    def replace_cast_function(match: re.Match) -> str:
        full_match = match.group(0)
        cast_match = re.search(
            rf"CAST\s*\(\s*(.+?)\s+AS\s+{NUMERIC_TYPE_PATTERN}",
            full_match,
            re.IGNORECASE | re.DOTALL,
        )
        if not cast_match:
            return full_match

        expr = cast_match.group(1).strip()
        type_part = full_match[full_match.upper().find("AS"):]

        simple_ident = re.compile(
            r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?$"
        )
        if simple_ident.match(expr):
            wrapped_expr = f"NULLIF({expr}, '')"
            return full_match.replace(expr, wrapped_expr, 1)

        return full_match

    def replace_double_colon(match: re.Match) -> str:
        full_match = match.group(0)
        dc_match = re.match(
            rf"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)::({NUMERIC_TYPE_PATTERN}(?:\([^)]+\))?)",
            full_match,
            re.IGNORECASE,
        )
        if not dc_match:
            return full_match

        expr = dc_match.group(1)
        full_type = dc_match.group(2)

        wrapped_expr = f"NULLIF({expr}, '')"
        return f"CAST({wrapped_expr} AS {full_type})"

    transformed = sql

    cast_pattern = re.compile(
        rf"CAST\s*\(\s*[^)]+\s+AS\s+{NUMERIC_TYPE_PATTERN}(?:\([^)]+\))?\)",
        re.IGNORECASE,
    )
    transformed = cast_pattern.sub(replace_cast_function, transformed)

    dc_pattern = re.compile(
        rf"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?::{NUMERIC_TYPE_PATTERN}(?:\([^)]+\))?(?=[,\s\)]|$)",
        re.IGNORECASE,
    )
    transformed = dc_pattern.sub(replace_double_colon, transformed)

    return transformed


def lint_redshift_compat(sql: str) -> List[str]:
    """
    Lint SQL for features that are not supported by Redshift 1.0 (PG 8.0.2).

    Returns:
        List of human-readable error strings. Empty list => no problems found.

    Checks:
        - LATERAL joins
        - JSONB types / operators (jsonb, ->>, #>> etc.)
        - REGEXP_COUNT function
        - Lookahead/lookbehind constructs in regex ( '(?=' , '(?<=' , '(?!' , '(?<!' )
    """
    problems: List[str] = []
    sql_upper = sql.upper()

    # 1) LATERAL joins
    if " LATERAL " in f" {sql_upper} ":
        problems.append("Redshift 1.0 does not support LATERAL joins.")

    # 2) JSONB / advanced JSON
    if re.search(r"\bJSONB\b", sql_upper):
        problems.append("Redshift 1.0 does not support JSONB; use JSON or VARCHAR instead.")
    if re.search(r"->>|#>>", sql):
        problems.append("Redshift 1.0 does not support JSONB path operators (->>, #>>).")

    # 3) REGEXP_COUNT
    if "REGEXP_COUNT" in sql_upper:
        problems.append("Redshift 1.0 does not support REGEXP_COUNT.")

    # 4) Lookahead / lookbehind in regex patterns (scan string literals only)
    parsed = sqlparse.parse(sql)
    for stmt in parsed:
        for tok in stmt.flatten():
            if tok.ttype in (
                T.Literal.String.Single,
                T.Literal.String.Symbol,
                T.Literal.String.Double,
            ):
                val = tok.value
                inner = (
                    val[1:-1]
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"')
                    else val
                )
                if re.search(r"\(\?=|\(\?<=|\(\?!|\(\?<!", inner):
                    problems.append(
                        "Redshift 1.0 regex engine does not support lookahead/lookbehind; "
                        f"problematic pattern found in literal: {val!r}"
                    )

    return problems
