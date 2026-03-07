"""
Boyce Database Adapters.

Provides a standard interface for connecting to live databases,
executing read-only queries, and profiling schema/data.
"""

from .base import DatabaseAdapter

__all__ = ["DatabaseAdapter"]

try:
    from .postgres import PostgresAdapter
    __all__.append("PostgresAdapter")
except ImportError:
    pass  # asyncpg not installed — postgres extra not available
