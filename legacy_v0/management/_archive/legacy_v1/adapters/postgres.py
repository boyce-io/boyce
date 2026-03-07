"""
PostgreSQL database adapter for DataShark.

Implements the DatabaseAdapter interface for PostgreSQL.
95% code reuse with Redshift adapter (both use pg_catalog).
"""

import os
from typing import List, Dict, Any, Optional
import pandas as pd
import psycopg2
from collections import defaultdict

from .base import DatabaseAdapter


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL adapter using psycopg2."""
    
    def __init__(self, connection_params: Optional[Dict[str, Any]] = None):
        """
        Initialize PostgreSQL adapter.
        
        Args:
            connection_params: Optional dict with keys:
                - host: PostgreSQL server host
                - port: Port (default 5432)
                - database: Database name
                - user: Username
                - password: Password
                - sslmode: SSL mode (default 'prefer')
                
                Falls back to environment variables if not provided.
        """
        if connection_params is None:
            connection_params = {
                'host': os.getenv('POSTGRES_HOST', os.getenv('DB_HOST', 'localhost')),
                'port': int(os.getenv('POSTGRES_PORT', os.getenv('DB_PORT', '5432'))),
                'database': os.getenv('POSTGRES_DATABASE', os.getenv('DB_DATABASE', 'postgres')),
                'user': os.getenv('POSTGRES_USER', os.getenv('DB_USER', 'postgres')),
                'password': os.getenv('POSTGRES_PASSWORD', os.getenv('DB_PASSWORD', '')),
                'sslmode': os.getenv('POSTGRES_SSLMODE', 'prefer'),
            }
        
        super().__init__(connection_params)
        self._validate_params()
        self._in_transaction = False
    
    def _validate_params(self):
        """Ensure all required parameters are present."""
        required = ['host', 'database', 'user']
        missing = [k for k in required if not self.connection_params.get(k)]
        
        if missing:
            raise ValueError(
                f"Missing required connection parameters: {', '.join(missing)}. "
                "Set environment variables or pass in connection_params."
            )
    
    def connect(self) -> bool:
        """Establish connection to PostgreSQL."""
        try:
            self.connection = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params.get('port', 5432),
                database=self.connection_params['database'],
                user=self.connection_params['user'],
                password=self.connection_params.get('password', ''),
                sslmode=self.connection_params.get('sslmode', 'prefer'),
                connect_timeout=10,
            )
            return True
        except psycopg2.OperationalError as e:
            raise ConnectionError(f"Failed to connect to PostgreSQL: {str(e)}") from e
    
    def disconnect(self) -> None:
        """Close PostgreSQL connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def test_connection(self) -> bool:
        """Test if connection is alive."""
        try:
            if not self.connection:
                self.connect()
            
            with self.connection.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except:
            return False
    
    def execute_query(self, sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        if not self.connection:
            self.connect()
        
        try:
            df = pd.read_sql(sql, self.connection, params=params)
            return df
        except Exception as e:
            raise Exception(f"Query execution failed: {str(e)}") from e
    
    def list_schemas(self) -> List[str]:
        """Get list of all schemas."""
        query = """
        SELECT nspname as schema_name
        FROM pg_catalog.pg_namespace
        WHERE nspname NOT LIKE 'pg_%'
        AND nspname != 'information_schema'
        ORDER BY nspname;
        """
        df = self.execute_query(query)
        return df['schema_name'].tolist()
    
    def list_tables(self, schema: str) -> List[str]:
        """Get list of tables in schema."""
        query = """
        SELECT c.relname as table_name
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
        AND n.nspname = %s
        ORDER BY c.relname;
        """
        df = self.execute_query(query, params=(schema,))
        return df['table_name'].tolist()
    
    def get_table_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Get column metadata for table."""
        query = """
        SELECT 
            a.attname as name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as type,
            NOT a.attnotnull as nullable,
            pg_catalog.pg_get_expr(d.adbin, d.adrelid) as default
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_catalog.pg_attrdef d ON (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
        WHERE n.nspname = %s
        AND c.relname = %s
        AND c.relkind = 'r'
        AND a.attnum > 0
        AND NOT a.attisdropped
        ORDER BY a.attnum;
        """
        df = self.execute_query(query, params=(schema, table))
        return df.to_dict('records')
    
    def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """Get primary key columns for table."""
        query = """
        SELECT 
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s
        AND c.relname = %s
        AND con.contype = 'p';
        """
        df = self.execute_query(query, params=(schema, table))
        
        if df.empty:
            return []
        
        # Parse "PRIMARY KEY (col1, col2)"
        constraint_def = df.iloc[0]['constraint_def']
        try:
            cols = constraint_def.split('PRIMARY KEY (')[1].split(')')[0]
            return [col.strip() for col in cols.split(',')]
        except:
            return []
    
    def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, str]]:
        """Get foreign key relationships for table."""
        query = """
        SELECT 
            con.conname as name,
            nf.nspname as referenced_schema,
            cf.relname as referenced_table,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_class cf ON con.confrelid = cf.oid
        JOIN pg_catalog.pg_namespace nf ON cf.relnamespace = nf.oid
        WHERE n.nspname = %s
        AND c.relname = %s
        AND con.contype = 'f';
        """
        df = self.execute_query(query, params=(schema, table))
        
        results = []
        for _, row in df.iterrows():
            try:
                constraint_def = row['constraint_def']
                # Extract source column
                from_col = constraint_def.split('FOREIGN KEY (')[1].split(')')[0].strip()
                # Extract target column
                to_col = constraint_def.split('REFERENCES')[1].split('(')[1].split(')')[0].strip()
                
                results.append({
                    'column': from_col,
                    'referenced_schema': row['referenced_schema'],
                    'referenced_table': row['referenced_table'],
                    'referenced_column': to_col,
                })
            except:
                continue
        
        return results
    
    def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """Get indexes for table."""
        query = """
        SELECT 
            i.relname as name,
            ix.indisunique as unique,
            pg_catalog.pg_get_indexdef(ix.indexrelid) as index_def
        FROM pg_catalog.pg_index ix
        JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
        JOIN pg_catalog.pg_class c ON c.oid = ix.indrelid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s
        AND c.relname = %s
        AND NOT ix.indisprimary;
        """
        df = self.execute_query(query, params=(schema, table))
        
        results = []
        for _, row in df.iterrows():
            try:
                index_def = row['index_def']
                if ' USING ' in index_def and '(' in index_def:
                    cols_part = index_def.split('(')[1].split(')')[0]
                    columns = [col.strip().split()[0] for col in cols_part.split(',')]
                else:
                    columns = []
                
                results.append({
                    'name': row['name'],
                    'columns': columns,
                    'unique': row['unique'],
                })
            except:
                continue
        
        return results
    
    def get_table_count(self, schema: str) -> int:
        """Get count of tables in schema."""
        query = """
        SELECT COUNT(*) as count
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
        AND n.nspname = %s;
        """
        df = self.execute_query(query, params=(schema,))
        return int(df.iloc[0]['count'])
    
    def batch_extract_columns(self, schema: str) -> Dict[str, List[Dict[str, Any]]]:
        """Batch extract columns for all tables in schema."""
        query = """
        SELECT 
            c.relname as table_name,
            a.attname as name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as type,
            NOT a.attnotnull as nullable,
            pg_catalog.pg_get_expr(d.adbin, d.adrelid) as default
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_catalog.pg_attrdef d ON (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
        WHERE n.nspname = %s
        AND c.relkind = 'r'
        AND a.attnum > 0
        AND NOT a.attisdropped
        ORDER BY c.relname, a.attnum;
        """
        df = self.execute_query(query, params=(schema,))
        
        result = defaultdict(list)
        for _, row in df.iterrows():
            result[row['table_name']].append({
                'name': row['name'],
                'type': row['type'],
                'nullable': row['nullable'],
                'default': row['default'],
            })
        
        return dict(result)
    
    def batch_extract_primary_keys(self, schema: str) -> Dict[str, List[str]]:
        """Batch extract primary keys for all tables in schema."""
        query = """
        SELECT 
            c.relname as table_name,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s
        AND con.contype = 'p';
        """
        df = self.execute_query(query, params=(schema,))
        
        result = {}
        for _, row in df.iterrows():
            try:
                constraint_def = row['constraint_def']
                cols = constraint_def.split('PRIMARY KEY (')[1].split(')')[0]
                columns = [col.strip() for col in cols.split(',')]
                result[row['table_name']] = columns
            except:
                continue
        
        return result
    
    def batch_extract_foreign_keys(self, schema: str) -> Dict[str, List[Dict[str, str]]]:
        """Batch extract foreign keys for all tables in schema."""
        query = """
        SELECT 
            c.relname as table_name,
            con.conname as constraint_name,
            nf.nspname as referenced_schema,
            cf.relname as referenced_table,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_class cf ON con.confrelid = cf.oid
        JOIN pg_catalog.pg_namespace nf ON cf.relnamespace = nf.oid
        WHERE n.nspname = %s
        AND con.contype = 'f';
        """
        df = self.execute_query(query, params=(schema,))
        
        result = defaultdict(list)
        for _, row in df.iterrows():
            try:
                constraint_def = row['constraint_def']
                from_col = constraint_def.split('FOREIGN KEY (')[1].split(')')[0].strip()
                to_col = constraint_def.split('REFERENCES')[1].split('(')[1].split(')')[0].strip()
                
                result[row['table_name']].append({
                    'column': from_col,
                    'referenced_schema': row['referenced_schema'],
                    'referenced_table': row['referenced_table'],
                    'referenced_column': to_col,
                })
            except:
                continue
        
        return dict(result)
    
    def batch_extract_indexes(self, schema: str) -> Dict[str, List[Dict[str, Any]]]:
        """Batch extract indexes for all tables in schema."""
        query = """
        SELECT 
            c.relname as table_name,
            i.relname as name,
            ix.indisunique as unique,
            pg_catalog.pg_get_indexdef(ix.indexrelid) as index_def
        FROM pg_catalog.pg_index ix
        JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
        JOIN pg_catalog.pg_class c ON c.oid = ix.indrelid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s
        AND NOT ix.indisprimary;
        """
        df = self.execute_query(query, params=(schema,))
        
        result = defaultdict(list)
        for _, row in df.iterrows():
            try:
                index_def = row['index_def']
                if ' USING ' in index_def and '(' in index_def:
                    cols_part = index_def.split('(')[1].split(')')[0]
                    columns = [col.strip().split()[0] for col in cols_part.split(',')]
                else:
                    columns = []
                
                result[row['table_name']].append({
                    'name': row['name'],
                    'columns': columns,
                    'unique': row['unique'],
                })
            except:
                continue
        
        return dict(result)
    
    def extract_relationships(self, schema: str) -> List[Dict[str, str]]:
        """Extract all foreign key relationships in schema."""
        query = """
        SELECT 
            c.relname as table,
            nf.nspname as referenced_schema,
            cf.relname as referenced_table,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_class cf ON con.confrelid = cf.oid
        JOIN pg_catalog.pg_namespace nf ON cf.relnamespace = nf.oid
        WHERE n.nspname = %s
        AND con.contype = 'f';
        """
        df = self.execute_query(query, params=(schema,))
        
        results = []
        for _, row in df.iterrows():
            try:
                constraint_def = row['constraint_def']
                from_col = constraint_def.split('FOREIGN KEY (')[1].split(')')[0].strip()
                to_col = constraint_def.split('REFERENCES')[1].split('(')[1].split(')')[0].strip()
                
                results.append({
                    'table': row['table'],
                    'column': from_col,
                    'referenced_schema': row['referenced_schema'],
                    'referenced_table': row['referenced_table'],
                    'referenced_column': to_col,
                })
            except:
                continue
        
        return results
    
    @property
    def adapter_name(self) -> str:
        """Get adapter name."""
        return 'postgres'
    
    # Transaction management implementation
    def begin_transaction(self) -> None:
        """Begin a new transaction."""
        if not self.connection:
            self.connect()
        
        try:
            # Disable autocommit
            self.connection.autocommit = False
            
            # Execute BEGIN if not already in transaction
            if not self._in_transaction:
                with self.connection.cursor() as cur:
                    cur.execute("BEGIN")
                self._in_transaction = True
        except Exception as e:
            raise Exception(f"Failed to begin transaction: {str(e)}") from e
    
    def commit(self) -> None:
        """Commit the current transaction."""
        if not self.connection:
            raise ConnectionError("No active connection")
        
        if not self._in_transaction:
            # No-op if not in transaction
            return
        
        try:
            with self.connection.cursor() as cur:
                cur.execute("COMMIT")
            self._in_transaction = False
        except Exception as e:
            raise Exception(f"Failed to commit transaction: {str(e)}") from e
    
    def rollback(self) -> None:
        """Rollback the current transaction."""
        if not self.connection:
            raise ConnectionError("No active connection")
        
        if not self._in_transaction:
            # No-op if not in transaction
            return
        
        try:
            with self.connection.cursor() as cur:
                cur.execute("ROLLBACK")
            self._in_transaction = False
        except Exception as e:
            raise Exception(f"Failed to rollback transaction: {str(e)}") from e
    
    def set_auto_commit(self, enabled: bool) -> None:
        """Enable or disable auto-commit mode."""
        if not self.connection:
            self.connect()
        
        try:
            self.connection.autocommit = enabled
            
            # If enabling autocommit while in transaction, commit first
            if enabled and self._in_transaction:
                self.commit()
        except Exception as e:
            raise Exception(f"Failed to set auto-commit: {str(e)}") from e
    
    @property
    def in_transaction(self) -> bool:
        """Check if currently in a transaction."""
        return self._in_transaction
    
    # Query cancellation implementation
    def cancel_query(self) -> bool:
        """
        Cancel the currently executing query using pg_cancel_backend().
        
        Returns:
            True if cancellation was successful, False otherwise
        """
        if not self.connection:
            return False
        
        try:
            # Get backend PID of current connection
            pid = self.connection.get_backend_pid()
            
            # Create a new connection to issue the cancel command
            cancel_conn = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params.get('port', 5432),
                database=self.connection_params['database'],
                user=self.connection_params['user'],
                password=self.connection_params.get('password', ''),
                sslmode=self.connection_params.get('sslmode', 'prefer'),
                connect_timeout=5
            )
            
            try:
                with cancel_conn.cursor() as cur:
                    # Use pg_cancel_backend to cancel the query
                    cur.execute("SELECT pg_cancel_backend(%s)", (pid,))
                    result = cur.fetchone()
                    success = result[0] if result else False
                    
                    if success:
                        logger.info(f"✅ Successfully cancelled query on PID {pid}")
                    else:
                        logger.warning(f"⚠️ Failed to cancel query on PID {pid}")
                    
                    return success
            finally:
                cancel_conn.close()
        
        except Exception as e:
            logger.error(f"❌ Error cancelling query: {e}")
            return False
    
    @property
    def supports_batch_extraction(self) -> bool:
        """PostgreSQL supports batch extraction."""
        return True

