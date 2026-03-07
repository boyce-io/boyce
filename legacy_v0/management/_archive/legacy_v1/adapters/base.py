"""
Base database adapter interface.

All database adapters must implement this interface to work with DataShark.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""
    
    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize adapter with connection parameters.
        
        Args:
            connection_params: Dictionary containing connection details
                (host, port, database, user, password, etc.)
        """
        self.connection_params = connection_params
        self.connection = None
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the database.
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test if connection is alive and working.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        pass
    
    @abstractmethod
    def execute_query(self, sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Execute a SQL query and return results as DataFrame.
        
        Args:
            sql: SQL query string
            params: Optional query parameters for safe substitution
        
        Returns:
            pandas DataFrame with query results
        
        Raises:
            Exception: If query execution fails
        """
        pass
    
    @abstractmethod
    def list_schemas(self) -> List[str]:
        """
        Get list of all schemas in the database.
        
        Returns:
            List of schema names
        """
        pass
    
    @abstractmethod
    def list_tables(self, schema: str) -> List[str]:
        """
        Get list of tables in a schema.
        
        Args:
            schema: Schema name
        
        Returns:
            List of table names
        """
        pass
    
    @abstractmethod
    def get_table_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """
        Get column metadata for a table.
        
        Args:
            schema: Schema name
            table: Table name
        
        Returns:
            List of column dictionaries with keys:
                - name: Column name
                - type: Data type
                - nullable: Boolean
                - default: Default value (if any)
        """
        pass
    
    @abstractmethod
    def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """
        Get primary key columns for a table.
        
        Args:
            schema: Schema name
            table: Table name
        
        Returns:
            List of primary key column names
        """
        pass
    
    @abstractmethod
    def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, str]]:
        """
        Get foreign key relationships for a table.
        
        Args:
            schema: Schema name
            table: Table name
        
        Returns:
            List of foreign key dictionaries with keys:
                - column: Column name
                - referenced_schema: Referenced schema
                - referenced_table: Referenced table
                - referenced_column: Referenced column
        """
        pass
    
    @abstractmethod
    def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """
        Get indexes for a table.
        
        Args:
            schema: Schema name
            table: Table name
        
        Returns:
            List of index dictionaries with keys:
                - name: Index name
                - columns: List of column names
                - unique: Boolean
        """
        pass
    
    @abstractmethod
    def get_table_count(self, schema: str) -> int:
        """
        Get count of tables in a schema.
        
        Args:
            schema: Schema name
        
        Returns:
            Number of tables in schema
        """
        pass
    
    @abstractmethod
    def batch_extract_columns(self, schema: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract columns for all tables in a schema (optimized batch query).
        
        Args:
            schema: Schema name
        
        Returns:
            Dictionary mapping table names to column metadata lists
        """
        pass
    
    @abstractmethod
    def batch_extract_primary_keys(self, schema: str) -> Dict[str, List[str]]:
        """
        Extract primary keys for all tables in a schema (optimized batch query).
        
        Args:
            schema: Schema name
        
        Returns:
            Dictionary mapping table names to primary key column lists
        """
        pass
    
    @abstractmethod
    def batch_extract_foreign_keys(self, schema: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract foreign keys for all tables in a schema (optimized batch query).
        
        Args:
            schema: Schema name
        
        Returns:
            Dictionary mapping table names to foreign key lists
        """
        pass
    
    @abstractmethod
    def batch_extract_indexes(self, schema: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract indexes for all tables in a schema (optimized batch query).
        
        Args:
            schema: Schema name
        
        Returns:
            Dictionary mapping table names to index lists
        """
        pass
    
    @abstractmethod
    def extract_relationships(self, schema: str) -> List[Dict[str, str]]:
        """
        Extract all foreign key relationships in a schema.
        
        Args:
            schema: Schema name
        
        Returns:
            List of relationship dictionaries
        """
        pass
    
    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """
        Get the name of this adapter (e.g., 'redshift', 'postgres').
        
        Returns:
            Adapter name string
        """
        pass
    
    @property
    @abstractmethod
    def supports_batch_extraction(self) -> bool:
        """
        Whether this adapter supports optimized batch extraction.
        
        Returns:
            True if batch extraction is supported
        """
        pass
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    # Transaction management methods
    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begin a new database transaction.
        
        Disables auto-commit mode and starts a transaction block.
        Must be followed by commit() or rollback().
        """
        pass
    
    @abstractmethod
    def commit(self) -> None:
        """
        Commit the current transaction.
        
        Makes all changes since begin_transaction() permanent.
        """
        pass
    
    @abstractmethod
    def rollback(self) -> None:
        """
        Rollback the current transaction.
        
        Discards all changes since begin_transaction().
        """
        pass
    
    @abstractmethod
    def set_auto_commit(self, enabled: bool) -> None:
        """
        Enable or disable auto-commit mode.
        
        Args:
            enabled: True to enable auto-commit, False to disable
        """
        pass
    
    @property
    @abstractmethod
    def in_transaction(self) -> bool:
        """
        Check if currently in a transaction.
        
        Returns:
            True if a transaction is active, False otherwise
        """
        pass
    
    def transaction(self):
        """
        Context manager for transactions.
        
        Usage:
            with adapter.transaction():
                adapter.execute_query("INSERT...")
                adapter.execute_query("UPDATE...")
            # Automatically commits on success, rollbacks on exception
        """
        return TransactionContext(self)


    # Query cancellation methods
    @abstractmethod
    def cancel_query(self) -> bool:
        """
        Cancel the currently executing query.
        
        Returns:
            True if cancellation was successful, False otherwise
        """
        pass
    
    def execute_query_cancellable(
        self, 
        sql: str, 
        params: Optional[tuple] = None,
        timeout: Optional[int] = None
    ):
        """
        Execute query with cancellation support.
        
        This is a default implementation that subclasses can override
        for more sophisticated cancellation.
        
        Args:
            sql: SQL query to execute
            params: Query parameters
            timeout: Timeout in seconds
        
        Returns:
            DataFrame with results
        """
        import threading
        
        result = None
        error = None
        
        def _execute():
            nonlocal result, error
            try:
                result = self.execute_query(sql, params)
            except Exception as e:
                error = e
        
        thread = threading.Thread(target=_execute, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            # Query still running after timeout
            self.cancel_query()
            thread.join(timeout=5)  # Give it 5 seconds to cancel
            raise TimeoutError(f"Query exceeded timeout of {timeout}s")
        
        if error:
            raise error
        
        return result


class TransactionContext:
    """Context manager for database transactions."""
    
    def __init__(self, adapter: 'DatabaseAdapter'):
        self.adapter = adapter
        self._transaction_started = False
    
    def __enter__(self):
        self.adapter.begin_transaction()
        self._transaction_started = True
        return self.adapter
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._transaction_started:
            return False
        
        if exc_type is None:
            # No exception, commit
            self.adapter.commit()
        else:
            # Exception occurred, rollback
            self.adapter.rollback()
        
        return False  # Don't suppress exceptions

