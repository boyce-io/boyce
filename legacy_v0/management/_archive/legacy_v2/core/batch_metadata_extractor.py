"""
Batch Metadata Extractor - DataGrip Performance Parity
Extracts ALL tables' metadata in a schema with minimal queries.

Instead of: 808 tables × 5 queries = 4,040 queries
We do: 5 queries total → distribute to tables

10-100x faster than per-table extraction.
"""

from typing import Dict, List, Tuple
import pandas as pd
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, date, timezone
from decimal import Decimal

from core.connection_manager import RedshiftConnectionManager
from core.metadata_extractor import (
    PrimaryKey, ForeignKey, Index, TableConstraint, TableMetadata
)


class BatchMetadataExtractor:
    """
    Extracts complete schema metadata in batched queries.
    Commercial tool performance - designed for 100+ schemas.
    """
    
    def __init__(self, connection_manager: RedshiftConnectionManager):
        self.conn_manager = connection_manager
    
    def extract_schema_batch(self, schema: str, include_stats: bool = True) -> Dict[str, TableMetadata]:
        """
        Extract ALL tables in a schema with batched queries.
        Returns dict mapping table_name -> TableMetadata.
        
        This is 10-100x faster than per-table extraction.
        
        Args:
            schema: Schema name
            include_stats: If True, extract row counts, sizes, and last modified times
        """
        # Get all tables first
        tables = self._get_tables_list(schema)
        
        if not tables:
            return {}
        
        # Batch extract all metadata types
        all_columns = self._batch_extract_columns(schema)
        all_pks = self._batch_extract_primary_keys(schema)
        all_fks = self._batch_extract_foreign_keys(schema)
        all_indexes = self._batch_extract_indexes(schema)
        all_constraints = self._batch_extract_constraints(schema)
        
        # Extract operational stats if requested
        all_stats = {}
        if include_stats:
            all_stats = self.batch_extract_table_stats(schema, tables)
        
        # Assemble into TableMetadata objects
        result = {}
        for table_name in tables:
            stats = all_stats.get(table_name, {})
            result[table_name] = TableMetadata(
                schema=schema,
                table=table_name,
                columns=all_columns.get(table_name, []),
                primary_key=all_pks.get(table_name),
                foreign_keys=all_fks.get(table_name, []),
                indexes=all_indexes.get(table_name, []),
                constraints=all_constraints.get(table_name, []),
                row_count=stats.get('row_count'),
                size_bytes=stats.get('size_bytes'),
                last_modified=stats.get('last_modified'),
            )
        
        return result
    
    def _get_tables_list(self, schema: str) -> List[str]:
        """Get list of all tables in schema."""
        query = """
        SELECT c.relname as table_name
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
        AND n.nspname = %s
        ORDER BY c.relname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        return df['table_name'].tolist()
    
    def _batch_extract_columns(self, schema: str) -> Dict[str, List[Dict]]:
        """
        Extract ALL columns for ALL tables in one query.
        Returns: {table_name: [column_dicts]}
        """
        query = """
        SELECT 
            c.relname as table_name,
            a.attname as column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
            a.attnotnull as not_null,
            a.attnum as ordinal_position,
            pg_catalog.pg_get_expr(d.adbin, d.adrelid) as column_default,
            col_description(a.attrelid, a.attnum) as comment
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
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        # Group by table
        result = defaultdict(list)
        for _, row in df.iterrows():
            result[row['table_name']].append({
                'column_name': row['column_name'],
                'data_type': row['data_type'],
                'not_null': row['not_null'],
                'ordinal_position': row['ordinal_position'],
                'column_default': row['column_default'],
                'comment': row['comment'],
            })
        
        return dict(result)
    
    def _batch_extract_primary_keys(self, schema: str) -> Dict[str, PrimaryKey]:
        """
        Extract ALL primary keys in one query.
        Redshift 8.0 compatible - uses constraint definition parsing.
        Returns: {table_name: PrimaryKey}
        """
        query = """
        SELECT 
            c.relname as table_name,
            con.conname as constraint_name,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s
        AND con.contype = 'p';
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        result = {}
        for _, row in df.iterrows():
            # Parse "PRIMARY KEY (col1, col2, col3)"
            constraint_def = row['constraint_def']
            try:
                cols = constraint_def.split('PRIMARY KEY (')[1].split(')')[0]
                columns = [col.strip() for col in cols.split(',')]
                
                result[row['table_name']] = PrimaryKey(
                    constraint_name=row['constraint_name'],
                    columns=columns
                )
            except:
                # Skip malformed constraints
                continue
        
        return result
    
    def _batch_extract_foreign_keys(self, schema: str) -> Dict[str, List[ForeignKey]]:
        """
        Extract ALL foreign keys in one query.
        Returns: {table_name: [ForeignKey]}
        """
        query = """
        SELECT 
            c.relname as table_name,
            con.conname as constraint_name,
            nf.nspname as referenced_schema,
            cf.relname as referenced_table,
            con.confdeltype as on_delete,
            con.confupdtype as on_update,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_class cf ON con.confrelid = cf.oid
        JOIN pg_catalog.pg_namespace nf ON cf.relnamespace = nf.oid
        WHERE n.nspname = %s
        AND con.contype = 'f';
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        result = defaultdict(list)
        for _, row in df.iterrows():
            # Parse constraint definition to extract columns
            constraint_def = row['constraint_def']
            
            try:
                # Extract source columns
                from_cols = constraint_def.split('FOREIGN KEY (')[1].split(')')[0]
                from_columns = [col.strip() for col in from_cols.split(',')]
                
                # Extract target columns
                to_cols = constraint_def.split('REFERENCES')[1].split('(')[1].split(')')[0]
                to_columns = [col.strip() for col in to_cols.split(',')]
                
                result[row['table_name']].append(ForeignKey(
                    constraint_name=row['constraint_name'],
                    columns=from_columns,
                    referenced_schema=row['referenced_schema'],
                    referenced_table=row['referenced_table'],
                    referenced_columns=to_columns,
                    on_delete=row['on_delete'],
                    on_update=row['on_update'],
                ))
            except:
                # Skip malformed constraints
                continue
        
        return dict(result)
    
    def _batch_extract_indexes(self, schema: str) -> Dict[str, List[Index]]:
        """
        Extract ALL indexes in one query.
        Redshift 8.0 compatible.
        Returns: {table_name: [Index]}
        """
        query = """
        SELECT 
            c.relname as table_name,
            i.relname as index_name,
            ix.indisunique as is_unique,
            am.amname as index_type,
            pg_catalog.pg_get_indexdef(ix.indexrelid) as index_def
        FROM pg_catalog.pg_index ix
        JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
        JOIN pg_catalog.pg_class c ON c.oid = ix.indrelid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_am am ON i.relam = am.oid
        WHERE n.nspname = %s
        AND NOT ix.indisprimary;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        result = defaultdict(list)
        for _, row in df.iterrows():
            # Parse index definition to get columns
            try:
                index_def = row['index_def']
                # Extract column names from index definition
                if ' USING ' in index_def and '(' in index_def:
                    cols_part = index_def.split('(')[1].split(')')[0]
                    columns = [col.strip().split()[0] for col in cols_part.split(',')]
                else:
                    columns = []
                
                result[row['table_name']].append(Index(
                    index_name=row['index_name'],
                    columns=columns,
                    is_unique=row['is_unique'],
                    index_type=row['index_type'],
                ))
            except:
                # Skip malformed indexes
                continue
        
        return dict(result)
    
    def _batch_extract_constraints(self, schema: str) -> Dict[str, List[TableConstraint]]:
        """
        Extract ALL check/unique constraints in one query.
        Returns: {table_name: [TableConstraint]}
        """
        query = """
        SELECT 
            c.relname as table_name,
            con.conname as constraint_name,
            CASE con.contype
                WHEN 'c' THEN 'CHECK'
                WHEN 'u' THEN 'UNIQUE'
            END as constraint_type,
            pg_catalog.pg_get_constraintdef(con.oid, true) as definition
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s
        AND con.contype IN ('c', 'u');
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        result = defaultdict(list)
        for _, row in df.iterrows():
            result[row['table_name']].append(TableConstraint(
                constraint_name=row['constraint_name'],
                constraint_type=row['constraint_type'],
                definition=row['definition'],
                columns=None,  # Could parse from definition if needed
            ))
        
        return dict(result)
    
    def batch_extract_table_stats(self, schema_name: str, table_names: List[str]) -> Dict[str, Dict]:
        """
        Extract operational statistics for multiple tables in a schema.
        
        Args:
            schema_name: Schema name
            table_names: List of table names
        
        Returns:
            Dict mapping table_name to:
                - row_count: int
                - size_bytes: int
                - size_mb: float
                - last_modified: datetime (from svv_table_info)
                - freshness_hours: float
        """
        if not table_names:
            return {}
        
        stats = {}
        
        try:
            with self.conn_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Query 1: Row counts (batch query using UNION ALL)
                # Note: This can be slow for large tables, so we limit to first 100 tables
                if len(table_names) <= 100:
                    row_count_sql = " UNION ALL ".join([
                        f"SELECT '{table}' as table_name, COUNT(*) as row_count FROM {schema_name}.{table}"
                        for table in table_names[:100]
                    ])
                    
                    try:
                        cursor.execute(row_count_sql)
                        for row in cursor.fetchall():
                            table_name, row_count = row
                            stats[table_name] = {"row_count": int(row_count) if row_count is not None else 0}
                    except Exception as e:
                        print(f"  Warning: Could not get row counts: {e}")
                        # Initialize with zeros
                        for table in table_names:
                            stats[table] = {"row_count": None}
                else:
                    # Too many tables, skip row counts
                    for table in table_names:
                        stats[table] = {"row_count": None}
                
                # Query 2: Table sizes (Redshift-specific)
                size_sql = """
                SELECT 
                    tablename as table_name,
                    pg_total_relation_size(schemaname || '.' || tablename) as size_bytes
                FROM pg_tables
                WHERE schemaname = %s AND tablename = ANY(%s)
                """
                
                try:
                    cursor.execute(size_sql, (schema_name, table_names))
                    for row in cursor.fetchall():
                        table_name, size_bytes = row
                        if table_name not in stats:
                            stats[table_name] = {}
                        stats[table_name]["size_bytes"] = int(size_bytes) if size_bytes is not None else 0
                        stats[table_name]["size_mb"] = round(size_bytes / (1024 * 1024), 2) if size_bytes else 0
                except Exception as e:
                    print(f"  Warning: Could not get table sizes: {e}")
                
                # Query 3: Last modified (from svv_table_info)
                modified_sql = """
                SELECT 
                    "table" as table_name,
                    MAX(last_altered) as last_modified
                FROM svv_table_info
                WHERE schema = %s AND "table" = ANY(%s)
                GROUP BY "table"
                """
                
                try:
                    cursor.execute(modified_sql, (schema_name, table_names))
                    for row in cursor.fetchall():
                        table_name, last_modified = row
                        if table_name not in stats:
                            stats[table_name] = {}
                        
                        if last_modified:
                            stats[table_name]["last_modified"] = last_modified.isoformat() if isinstance(last_modified, datetime) else str(last_modified)
                            
                            # Calculate freshness in hours
                            try:
                                if isinstance(last_modified, datetime):
                                    now = datetime.now(timezone.utc)
                                    # Make last_modified timezone-aware if it isn't
                                    if last_modified.tzinfo is None:
                                        last_modified = last_modified.replace(tzinfo=timezone.utc)
                                    delta = now - last_modified
                                    stats[table_name]["freshness_hours"] = round(delta.total_seconds() / 3600, 1)
                            except:
                                stats[table_name]["freshness_hours"] = None
                        else:
                            stats[table_name]["last_modified"] = None
                            stats[table_name]["freshness_hours"] = None
                except Exception as e:
                    print(f"  Warning: Could not get last modified times: {e}")
        
        except Exception as e:
            print(f"Error extracting stats for {schema_name}: {e}")
        
        return stats
    
    def extract_sample_data(self, schema_name: str, table_name: str, limit: int = 5) -> List[Dict]:
        """
        Extract sample rows from a table.
        
        Args:
            schema_name: Schema name
            table_name: Table name
            limit: Number of sample rows (default 5)
        
        Returns:
            List of dicts representing sample rows
        """
        try:
            sql = f"SELECT * FROM {schema_name}.{table_name} LIMIT {limit}"
            
            with self.conn_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                
                # Get column names
                columns = [desc[0] for desc in cursor.description]
                
                # Fetch rows and convert to dicts
                rows = []
                for row in cursor.fetchall():
                    row_dict = {}
                    for i, col_name in enumerate(columns):
                        value = row[i]
                        # Convert to JSON-serializable types
                        if isinstance(value, (datetime, date)):
                            value = value.isoformat()
                        elif isinstance(value, Decimal):
                            value = float(value)
                        elif value is None:
                            value = None
                        else:
                            # Convert to string if not a basic JSON type
                            if not isinstance(value, (str, int, float, bool)):
                                value = str(value)
                        row_dict[col_name] = value
                    rows.append(row_dict)
                
                return rows
        
        except Exception as e:
            print(f"  Warning: Could not extract sample data from {schema_name}.{table_name}: {e}")
            return []

