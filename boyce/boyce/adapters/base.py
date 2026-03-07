"""
DatabaseAdapter — Abstract Base Class

Defines the standard interface all concrete database adapters must implement.
All methods are async to support connection pooling and non-blocking I/O.

Concrete implementations:
    PostgresAdapter  — asyncpg-based (boyce.adapters.postgres)

Usage::

    adapter = PostgresAdapter(dsn="postgresql://user:pass@host/db")
    await adapter.connect()

    rows = await adapter.execute_query("SELECT id, name FROM orders LIMIT 10")
    schema = await adapter.get_schema_summary()
    profile = await adapter.profile_column("orders", "status")

    await adapter.disconnect()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class DatabaseAdapter(ABC):
    """
    Abstract interface for read-only database access.

    All implementations must guarantee:
      - No write operations (INSERT / UPDATE / DELETE / DDL) can be executed
        via execute_query(). Enforcement mechanism is adapter-specific.
      - Connections must be cleaned up on disconnect().
      - All return types are JSON-serialisable dicts / lists.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """
        Open a database connection (or acquire from pool).

        Must be called before any query methods.

        Raises:
            ConnectionError: If the database is unreachable or credentials
                are invalid.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close the database connection (or release back to pool).

        Safe to call even if connect() was never called or already disconnected.
        """

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a READ-ONLY SQL query and return rows as a list of dicts.

        Implementations MUST reject or raise on any DML / DDL statement
        (INSERT, UPDATE, DELETE, TRUNCATE, DROP, CREATE, ALTER, …).

        Args:
            sql: A SELECT statement (or equivalent read query).

        Returns:
            List of row dicts, e.g.::

                [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

            Column values are coerced to JSON-safe Python types:
            datetime → ISO string, Decimal → float, UUID → str, etc.

        Raises:
            ValueError: If the SQL statement is detected as a write operation.
            RuntimeError: If called before connect().
        """

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_schema_summary(self) -> List[Dict[str, Any]]:
        """
        Return a summary of all user-accessible tables and their columns.

        Returns:
            List of table dicts, e.g.::

                [
                    {
                        "schema": "public",
                        "table": "orders",
                        "type": "BASE TABLE",
                        "approx_row_count": 84231,
                        "columns": [
                            {
                                "name": "id",
                                "data_type": "integer",
                                "nullable": False,
                                "primary_key": True,
                            },
                            ...
                        ],
                    },
                    ...
                ]
        """

    # ------------------------------------------------------------------
    # Data profiling
    # ------------------------------------------------------------------

    @abstractmethod
    async def profile_column(self, table: str, column: str) -> Dict[str, Any]:
        """
        Return basic statistics for a single column.

        Runs a single SQL query against the live table. On large tables this
        may be slow — callers should rely on statement_timeout for safety.

        Args:
            table: Fully-qualified or bare table name (e.g. "orders" or
                "public.orders").
            column: Column name.

        Returns:
            Dict of profile statistics, e.g.::

                {
                    "table":          "orders",
                    "column":         "status",
                    "row_count":      84231,
                    "null_count":     0,
                    "null_pct":       0.0,
                    "distinct_count": 5,
                    "min_value":      "active",
                    "max_value":      "voided",
                }

            min_value / max_value are cast to text; ordering is lexicographic
            for non-numeric types.

        Raises:
            ValueError: If table or column contains unsafe characters.
            RuntimeError: If called before connect().
        """
