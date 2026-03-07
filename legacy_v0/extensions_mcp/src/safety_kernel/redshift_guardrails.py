"""
Redshift 1.0.127211 guardrails and SQL transformation utilities.

Goals (Phase 1, Step 2 - Deterministic Core):
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
       - Designed for deterministically-generated SQL from DataShark
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
from sqlparse.sql import Token, TokenList
from sqlparse import tokens as T


# Redshift 1.0 numeric type family that is unsafe for '' casts.
# Note: DOUBLE PRECISION is two tokens at the SQL level, handled via regex.
NUMERIC_TYPE_PATTERN = r"(NUMERIC|DECIMAL|INT|INTEGER|BIGINT|FLOAT|DOUBLE\\s+PRECISION)"
# Compiled regex for matching type_part in _transform_double_colon (e.g. "NUMERIC(10,2)" or "DECIMAL")
NUMERIC_TYPE_RE = re.compile(r"^(NUMERIC|DECIMAL|INT|INTEGER|BIGINT|FLOAT|DOUBLE\s+PRECISION)(?:\([^)]+\))?", re.IGNORECASE)


def _wrap_cast_argument(arg_sql: str) -> str:
    """
    Wrap a cast argument with NULLIF(..., '') if it is a simple column reference.

    This is intentionally conservative: it only rewrites simple identifiers
    (optionally qualified with a single dot). Complex expressions are left
    untouched to avoid semantic changes.
    """
    # Allow multi-part identifiers: col, table.col, schema.table.col
    simple_ident = re.compile(
        r"^[a-zA-Z_][a-zA-Z0-9_]*"
        r"(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$"
    )
    stripped = arg_sql.strip()
    if simple_ident.match(stripped):
        return f"NULLIF({stripped}, '')"
    return arg_sql


def _transform_cast_function(token: Token) -> str | None:
    """
    Attempt to rewrite a CAST(...) token if it targets NUMERIC/DECIMAL.

    Returns the rewritten SQL string if a transformation was applied,
    otherwise None.
    """
    # We operate on the raw value because CAST tends to be straightforward
    text = str(token)
    # Cheap pre-check
    if "CAST" not in text.upper():
        return None

    # Pattern: CAST(expr AS NUMERIC...) or CAST(expr AS DECIMAL...)
    # We keep parsing manually with regex since sqlparse AST for functions
    # can vary with whitespace.
    cast_re = re.compile(
        r"""^CAST\s*\(\s*(?P<expr>.+?)\s+AS\s+(?P<type>NUMERIC|DECIMAL)\b""",
        re.IGNORECASE | re.DOTALL,
    )
    m = cast_re.match(text.strip())
    if not m:
        return None

    expr = m.group("expr")
    type_part = text[text.upper().find("AS") + 2 :].strip()  # "NUMERIC(10,2))..."

    wrapped_expr = _wrap_cast_argument(expr)
    # Reconstruct CAST, preserving the type tail verbatim
    # Example:
    #   original: CAST(price AS NUMERIC(10,2))
    #   rewritten: CAST(NULLIF(price, '') AS NUMERIC(10,2))
    before_type = text[: text.upper().find("AS")]
    rewritten = f"{before_type}AS {type_part}"
    # Replace only the first occurrence of expr inside the parentheses
    rewritten = rewritten.replace(expr, wrapped_expr, 1)
    return rewritten


def _transform_double_colon(token: Token) -> str | None:
    """
    Rewrite 'expr::NUMERIC/DECIMAL' into 'CAST(NULLIF(expr, '') AS NUMERIC/DECIMAL)'.

    We again only wrap simple identifiers to avoid changing complex expressions.
    """
    text = str(token)
    if "::" not in text:
        return None

    # Very targeted pattern for deterministic SQL we expect:
    #   identifier[::schema].TYPE or identifier::TYPE(...)
    m = re.match(
        r"^(?P<expr>[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)::(?P<type>.+)$",
        text.strip(),
    )
    if not m:
        return None

    expr = m.group("expr")
    type_part = m.group("type")

    if not NUMERIC_TYPE_RE.match(type_part.strip()):
        return None

    wrapped_expr = _wrap_cast_argument(expr)
    return f"CAST({wrapped_expr} AS {type_part})"


def _find_and_transform_casts_in_tokenlist(token_list: TokenList) -> str:
    """
    Recursively walk a TokenList to find and transform CAST expressions.
    
    Returns the transformed string representation of the token list.
    """
    result_parts = []
    
    i = 0
    while i < len(token_list.tokens):
        tok = token_list.tokens[i]
        
        # Check if this is a CAST function call
        if isinstance(tok, TokenList) and len(tok.tokens) > 0:
            # Check if first token is CAST
            first_token = tok.tokens[0]
            if isinstance(first_token, (TokenList, Token)) and str(first_token).strip().upper() == "CAST":
                # This looks like a CAST expression - try to extract and transform
                cast_str = str(tok)
                transformed = _transform_cast_function(tok)
                if transformed:
                    result_parts.append(transformed)
                    i += 1
                    continue
            
            # Recursively process nested TokenLists
            result_parts.append(_find_and_transform_casts_in_tokenlist(tok))
            i += 1
            continue
        
        # Check for double-colon casts in simple tokens
        if isinstance(tok, Token) and "::" in str(tok):
            transformed = _transform_double_colon(tok)
            if transformed:
                result_parts.append(transformed)
                i += 1
                continue
        
        # Regular token - keep as-is
        result_parts.append(str(tok))
        i += 1
    
    return "".join(result_parts)


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
    # Use regex-based approach for reliability with complex SQL
    import re
    
    # Pattern 1: CAST(expr AS <NUMERIC TYPE>(...))
    # Match: CAST( followed by expression, then AS NUMERIC/DECIMAL
    def replace_cast_function(match):
        full_match = match.group(0)
        # Extract the expression part (between CAST( and AS)
        cast_match = re.search(
            rf"CAST\s*\(\s*(.+?)\s+AS\s+{NUMERIC_TYPE_PATTERN}",
            full_match,
            re.IGNORECASE | re.DOTALL,
        )
        if not cast_match:
            return full_match
        
        expr = cast_match.group(1).strip()
        type_part = full_match[full_match.upper().find("AS"):]
        
        # Only wrap simple identifiers (column references)
        simple_ident = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?$')
        if simple_ident.match(expr):
            wrapped_expr = f"NULLIF({expr}, '')"
            return full_match.replace(expr, wrapped_expr, 1)
        
        return full_match
    
    # Pattern 2: expr::NUMERIC / expr::DECIMAL / expr::INT / expr::FLOAT / expr::DOUBLE PRECISION
    def replace_double_colon(match):
        full_match = match.group(0)
        # Extract identifier and full type (including precision/scale)
        # Pattern: identifier::NUMERIC(...) or identifier::DECIMAL
        # We need to capture the full type including parentheses and parameters
        dc_match = re.match(
            rf"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)::({NUMERIC_TYPE_PATTERN}(?:\([^)]+\))?)",
            full_match,
            re.IGNORECASE
        )
        if not dc_match:
            return full_match
        
        expr = dc_match.group(1)
        full_type = dc_match.group(2)  # e.g., "NUMERIC(10,2)" or "DECIMAL"
        
        wrapped_expr = f"NULLIF({expr}, '')"
        return f"CAST({wrapped_expr} AS {full_type})"
    
    # Apply transformations
    transformed = sql
    
    # Find all CAST(... AS <NUMERIC TYPE>) patterns
    cast_pattern = re.compile(
        rf"CAST\s*\(\s*[^)]+\s+AS\s+{NUMERIC_TYPE_PATTERN}(?:\([^)]+\))?\)",
        re.IGNORECASE
    )
    transformed = cast_pattern.sub(replace_cast_function, transformed)
    
    # Find all expr::<NUMERIC TYPE> patterns
    # Match: identifier::TYPE or identifier::TYPE(...) where TYPE is one of NUMERIC/DECIMAL/INT/...
    dc_pattern = re.compile(
        rf"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?::{NUMERIC_TYPE_PATTERN}(?:\([^)]+\))?(?=[,\s\)]|$)",
        re.IGNORECASE
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

    # 4) Lookahead / lookbehind in regex patterns.
    #    We approximate by scanning string literals only.
    parsed = sqlparse.parse(sql)
    for stmt in parsed:
        for tok in stmt.flatten():
            if tok.ttype in (T.Literal.String.Single, T.Literal.String.Symbol, T.Literal.String.Double):
                val = tok.value
                # Strip quotes for inspection
                inner = val[1:-1] if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"') else val
                if re.search(r"\(\?=|\(\?<=|\(\?!|\(\?<!", inner):
                    problems.append(
                        "Redshift 1.0 regex engine does not support lookahead/lookbehind; "
                        f"problematic pattern found in literal: {val!r}"
                    )

    return problems



