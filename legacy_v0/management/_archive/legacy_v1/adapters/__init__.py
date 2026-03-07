"""
Database adapters for DataShark.

Provides a plugin architecture for supporting multiple database types.
"""

from .base import DatabaseAdapter
from .redshift import RedshiftAdapter
from .postgres import PostgresAdapter
from .factory import AdapterFactory, get_adapter

__all__ = ['DatabaseAdapter', 'RedshiftAdapter', 'PostgresAdapter', 'AdapterFactory', 'get_adapter']

