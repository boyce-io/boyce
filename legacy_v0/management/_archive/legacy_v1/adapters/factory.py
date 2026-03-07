"""
Adapter factory for selecting the right database adapter.
"""

from typing import Dict, Any, Optional
from .base import DatabaseAdapter
from .redshift import RedshiftAdapter
from .postgres import PostgresAdapter


class AdapterFactory:
    """Factory for creating database adapters."""
    
    # Registry of available adapters
    _adapters = {
        'redshift': RedshiftAdapter,
        'postgres': PostgresAdapter,
        'postgresql': PostgresAdapter,  # Alias
    }
    
    @classmethod
    def create(cls, adapter_type: str, connection_params: Optional[Dict[str, Any]] = None) -> DatabaseAdapter:
        """
        Create a database adapter instance.
        
        Args:
            adapter_type: Type of adapter ('redshift', 'postgres', etc.)
            connection_params: Optional connection parameters
        
        Returns:
            DatabaseAdapter instance
        
        Raises:
            ValueError: If adapter_type is not supported
        """
        adapter_type = adapter_type.lower()
        
        if adapter_type not in cls._adapters:
            available = ', '.join(cls._adapters.keys())
            raise ValueError(
                f"Unsupported adapter type: '{adapter_type}'. "
                f"Available adapters: {available}"
            )
        
        adapter_class = cls._adapters[adapter_type]
        return adapter_class(connection_params)
    
    @classmethod
    def register_adapter(cls, name: str, adapter_class: type):
        """
        Register a custom adapter.
        
        Args:
            name: Adapter name
            adapter_class: Adapter class (must inherit from DatabaseAdapter)
        """
        if not issubclass(adapter_class, DatabaseAdapter):
            raise TypeError("Adapter class must inherit from DatabaseAdapter")
        
        cls._adapters[name.lower()] = adapter_class
    
    @classmethod
    def list_adapters(cls) -> list:
        """Get list of available adapter names."""
        return list(cls._adapters.keys())


def get_adapter(adapter_type: Optional[str] = None, connection_params: Optional[Dict[str, Any]] = None) -> DatabaseAdapter:
    """
    Convenience function to get an adapter.
    
    Args:
        adapter_type: Type of adapter. If None, auto-detects from environment.
        connection_params: Optional connection parameters
    
    Returns:
        DatabaseAdapter instance
    """
    if adapter_type is None:
        # Auto-detect from environment variables
        import os
        if os.getenv('REDSHIFT_HOST'):
            adapter_type = 'redshift'
        elif os.getenv('POSTGRES_HOST') or os.getenv('DB_HOST'):
            adapter_type = 'postgres'
        else:
            # Default to Redshift for backward compatibility
            adapter_type = 'redshift'
    
    return AdapterFactory.create(adapter_type, connection_params)

