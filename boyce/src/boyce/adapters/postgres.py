"""
PostgresAdapter — asyncpg-based implementation of DatabaseAdapter.

Read-only enforcement is layered:
  1. Regex pre-check: rejects obvious DML/DDL before touching the wire.
  2. asyncpg readonly transaction: database refuses any write at the protocol
     level, even if the pre-check is bypassed by a clever statement.

Configuration (environment variables):
    BOYCE_DB_URL         — asyncpg DSN, e.g.
                               postgresql://user:pass@localhost:5432/mydb
    BOYCE_STATEMENT_TIMEOUT_MS   — per-statement timeout in ms (default 30000)

Install the extra dependency:
    pip install "boyce[postgres]"
    # or directly:
    pip install asyncpg>=0.29.0
"""

from __future__ import annotations

import datetime
import decimal
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

from .base import DatabaseAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Read-only guard (belt-and-suspenders over the readonly transaction)
# ---------------------------------------------------------------------------

_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE|DROP|CREATE|ALTER|REPLACE|MERGE|UPSERT"
    r"|COPY|GRANT|REVOKE|CALL|DO|VACUUM|ANALYZE|REINDEX|CLUSTER|COMMENT ON)\b",
    re.IGNORECASE,
)

# Identifier safety: schema.table or table, column names
_SAFE_IDENT_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")


def _assert_readonly(sql: str) -> None:
    """Raise ValueError if sql appears to be a write operation."""
    if _WRITE_PATTERN.match(sql.strip()):
        keyword = sql.strip().split()[0].upper()
        raise ValueError(
            f"execute_query() is read-only. Rejected statement starting with: {keyword}"
        )


def _assert_safe_ident(value: str, label: str) -> None:
    """Raise ValueError if value contains characters unsafe for identifier quoting."""
    if not _SAFE_IDENT_PATTERN.match(value):
        raise ValueError(
            f"Unsafe {label} name: {value!r}. "
            "Only alphanumeric characters, underscores, and dots are allowed."
        )


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _coerce(value: Any) -> Any:
    """Convert asyncpg row values to JSON-safe Python types."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, memoryview):
        return bytes(value).hex()
    return value


def _record_to_dict(record: Any) -> Dict[str, Any]:
    """Convert an asyncpg Record to a JSON-safe dict."""
    return {key: _coerce(value) for key, value in record.items()}


# ---------------------------------------------------------------------------
# PostgresAdapter
# ---------------------------------------------------------------------------

class PostgresAdapter(DatabaseAdapter):
    """
    Async, read-only PostgreSQL adapter backed by asyncpg.

    Args:
        dsn: asyncpg-compatible DSN string.
            e.g. "postgresql://user:pass@localhost:5432/mydb"
            Falls back to the BOYCE_DB_URL environment variable if omitted.
        statement_timeout_ms: Maximum time (ms) any single statement may run.
            Defaults to 30 000 (30 s). Passed as a session-level GUC on connect.

    Example::

        adapter = PostgresAdapter("postgresql://user:pass@localhost/mydb")
        await adapter.connect()

        rows = await adapter.execute_query("SELECT * FROM orders LIMIT 5")
        schema = await adapter.get_schema_summary()
        profile = await adapter.profile_column("orders", "status")

        await adapter.disconnect()
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        statement_timeout_ms: int = 30_000,
    ) -> None:
        import os
        self._dsn = dsn or os.environ.get("BOYCE_DB_URL") or ""
        self._statement_timeout_ms = statement_timeout_ms
        self._conn: Optional[Any] = None  # asyncpg.Connection at runtime

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open a single asyncpg connection with a read-only statement timeout."""
        if asyncpg is None:
            raise RuntimeError(
                "asyncpg is not installed. "
                'Install it with: pip install "boyce[postgres]"'
            )
        if not self._dsn:
            raise ConnectionError(
                "No DSN provided. Pass dsn= to PostgresAdapter() or set "
                "the BOYCE_DB_URL environment variable."
            )
        logger.info("PostgresAdapter: connecting to %s", _redact_dsn(self._dsn))
        self._conn = await asyncpg.connect(
            self._dsn,
            server_settings={
                "statement_timeout": str(self._statement_timeout_ms),
            },
        )
        logger.info("PostgresAdapter: connected (server version %s)", self._conn.get_server_version())

    async def disconnect(self) -> None:
        """Close the asyncpg connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("PostgresAdapter: disconnected")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connection(self) -> Any:
        if self._conn is None:
            raise RuntimeError(
                "PostgresAdapter is not connected. Call await adapter.connect() first."
            )
        return self._conn

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a read-only SELECT and return rows as a list of dicts.

        Read-only is enforced at two levels:
          - Pre-check: obvious DML/DDL is rejected immediately (clear error).
          - Transaction: asyncpg runs the statement inside a readonly transaction;
            the database rejects any write that slipped past the pre-check.

        Args:
            sql: A SELECT statement.

        Returns:
            List of row dicts with JSON-safe values.

        Raises:
            ValueError: If sql is detected as a write operation.
            RuntimeError: If not connected.
            asyncpg.PostgresError: For server-side errors (syntax, timeout, etc.).
        """
        _assert_readonly(sql)
        conn = self._require_connection()

        async with conn.transaction(readonly=True):
            rows = await conn.fetch(sql)

        return [_record_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    async def get_schema_summary(self) -> List[Dict[str, Any]]:
        """
        Return all user-accessible tables with columns and approximate row counts.

        Uses information_schema (portable) for structure and pg_class for
        fast approximate row counts (no table scan required).
        """
        conn = self._require_connection()

        # Fetch tables + approx row count in one shot
        table_rows = await conn.fetch("""
            SELECT
                t.table_schema,
                t.table_name,
                t.table_type,
                COALESCE(c.reltuples::BIGINT, -1) AS approx_row_count
            FROM information_schema.tables t
            LEFT JOIN pg_class c
                ON c.relname = t.table_name
            LEFT JOIN pg_namespace n
                ON n.nspname = t.table_schema AND n.oid = c.relnamespace
            WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema',
                                          'pg_toast', 'pg_temp_1')
            ORDER BY t.table_schema, t.table_name
        """)

        # Fetch all columns at once (one round-trip)
        column_rows = await conn.fetch("""
            SELECT
                c.table_schema,
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.ordinal_position,
                COALESCE(
                    (SELECT true FROM information_schema.table_constraints tc
                     JOIN information_schema.key_column_usage kcu
                         ON kcu.constraint_name = tc.constraint_name
                         AND kcu.table_schema  = tc.table_schema
                     WHERE tc.constraint_type = 'PRIMARY KEY'
                       AND tc.table_schema     = c.table_schema
                       AND tc.table_name       = c.table_name
                       AND kcu.column_name     = c.column_name
                     LIMIT 1),
                    false
                ) AS primary_key
            FROM information_schema.columns c
            WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema',
                                          'pg_toast', 'pg_temp_1')
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """)

        # Index columns by (schema, table)
        col_index: Dict[tuple, List[Dict[str, Any]]] = {}
        for row in column_rows:
            key = (row["table_schema"], row["table_name"])
            col_index.setdefault(key, []).append({
                "name": row["column_name"],
                "data_type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "primary_key": bool(row["primary_key"]),
            })

        return [
            {
                "schema": row["table_schema"],
                "table": row["table_name"],
                "type": row["table_type"],
                "approx_row_count": int(row["approx_row_count"]),
                "columns": col_index.get((row["table_schema"], row["table_name"]), []),
            }
            for row in table_rows
        ]

    async def get_foreign_keys(self) -> List[Dict[str, Any]]:
        """
        Return all FK constraints in the database as a list of dicts.

        Each dict has keys: src_schema, src_table, src_column,
        tgt_schema, tgt_table, tgt_column.

        Uses information_schema for portability (works on Postgres and Redshift).
        """
        conn = self._require_connection()
        rows = await conn.fetch("""
            SELECT
                kcu.table_schema  AS src_schema,
                kcu.table_name    AS src_table,
                kcu.column_name   AS src_column,
                ccu.table_schema  AS tgt_schema,
                ccu.table_name    AS tgt_table,
                ccu.column_name   AS tgt_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema   = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema   = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY src_schema, src_table, src_column
        """)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Data profiling
    # ------------------------------------------------------------------

    async def profile_column(self, table: str, column: str) -> Dict[str, Any]:
        """
        Return null count, distinct count, and min/max for a column.

        The entire profile is computed in a single SQL round-trip using a CTE.
        MIN/MAX values are cast to text; ordering is lexicographic for
        non-numeric types.

        Args:
            table: Table name (e.g. "orders" or "public.orders").
            column: Column name.

        Returns:
            Profile dict — see base class docstring for shape.
        """
        _assert_safe_ident(table, "table")
        _assert_safe_ident(column, "column")

        conn = self._require_connection()

        # Quote identifiers to handle reserved words and mixed case
        quoted_table = ".".join(f'"{part}"' for part in table.split("."))
        quoted_col = f'"{column}"'

        # Single-query profile using a CTE
        sql = f"""
            WITH profile AS (
                SELECT
                    COUNT(*)                        AS row_count,
                    COUNT({quoted_col})             AS non_null_count,
                    COUNT(*) - COUNT({quoted_col})  AS null_count,
                    COUNT(DISTINCT {quoted_col})    AS distinct_count,
                    MIN({quoted_col}::TEXT)         AS min_value,
                    MAX({quoted_col}::TEXT)         AS max_value
                FROM {quoted_table}
            )
            SELECT * FROM profile
        """

        rows = await conn.fetch(sql)
        if not rows:
            return {"table": table, "column": column, "error": "no rows returned"}

        row = rows[0]
        row_count = int(row["row_count"])
        null_count = int(row["null_count"])
        null_pct = round(null_count / row_count * 100, 2) if row_count > 0 else 0.0

        return {
            "table": table,
            "column": column,
            "row_count": row_count,
            "null_count": null_count,
            "null_pct": null_pct,
            "distinct_count": int(row["distinct_count"]),
            "min_value": row["min_value"],
            "max_value": row["max_value"],
        }

    # ------------------------------------------------------------------
    # Context manager support (optional convenience)
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PostgresAdapter":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_dsn(dsn: str) -> str:
    """Replace password in DSN with *** for safe logging."""
    return re.sub(r"(:)[^:@]+(@)", r"\1***\2", dsn)
