"""
Complete Metadata Extractor for DataGrip Parity
Captures ALL database objects: tables, keys, constraints, indexes, relationships
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
from dataclasses import dataclass, asdict
from core.connection_manager import RedshiftConnectionManager


@dataclass
class PrimaryKey:
    """Primary key constraint."""
    constraint_name: str
    columns: List[str]


@dataclass
class ForeignKey:
    """Foreign key relationship."""
    constraint_name: str
    columns: List[str]
    referenced_schema: str
    referenced_table: str
    referenced_columns: List[str]
    on_delete: Optional[str] = None
    on_update: Optional[str] = None


@dataclass
class Index:
    """Table index."""
    index_name: str
    columns: List[str]
    is_unique: bool
    index_type: str


@dataclass
class TableConstraint:
    """Check or unique constraint."""
    constraint_name: str
    constraint_type: str  # CHECK, UNIQUE
    definition: Optional[str] = None
    columns: Optional[List[str]] = None


@dataclass
class TableMetadata:
    """Complete table metadata including all constraints and relationships."""
    schema: str
    table: str
    columns: List[Dict]
    primary_key: Optional[PrimaryKey] = None
    foreign_keys: List[ForeignKey] = None
    indexes: List[Index] = None
    constraints: List[TableConstraint] = None
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    last_modified: Optional[str] = None


class CompleteMetadataExtractor:
    """
    Extracts complete database metadata for DataGrip-like functionality.
    Captures keys, constraints, indexes, and relationships.
    """
    
    def __init__(self, connection_manager: RedshiftConnectionManager):
        self.conn_manager = connection_manager
    
    def extract_table_metadata(self, schema: str, table: str) -> TableMetadata:
        """
        Extract complete metadata for a single table.
        
        Args:
            schema: Schema name
            table: Table name
        
        Returns:
            TableMetadata object with all information
        """
        return TableMetadata(
            schema=schema,
            table=table,
            columns=self._get_columns(schema, table),
            primary_key=self._get_primary_key(schema, table),
            foreign_keys=self._get_foreign_keys(schema, table),
            indexes=self._get_indexes(schema, table),
            constraints=self._get_constraints(schema, table),
            row_count=self._get_row_count(schema, table),
            size_bytes=self._get_table_size(schema, table),
            last_modified=self._get_last_modified(schema, table),
        )
    
    def _get_columns(self, schema: str, table: str) -> List[Dict]:
        """Get column information."""
        query = """
        SELECT 
            a.attname as column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
            a.attnotnull as not_null,
            a.attnum as ordinal_position,
            pg_catalog.pg_get_expr(d.adbin, d.adrelid) as column_default,
            col_description(a.attrelid, a.attnum) as comment
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        LEFT JOIN pg_catalog.pg_attrdef d ON (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
        WHERE n.nspname = %s
        AND c.relname = %s
        AND a.attnum > 0
        AND NOT a.attisdropped
        ORDER BY a.attnum;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema, table))
        
        return df.to_dict('records')
    
    def _get_primary_key(self, schema: str, table: str) -> Optional[PrimaryKey]:
        """Get primary key constraint."""
        query = """
        SELECT 
            con.conname as constraint_name,
            array_agg(att.attname ORDER BY u.attposition) as columns
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS u(attnum, attposition) ON TRUE
        JOIN pg_catalog.pg_attribute att ON att.attrelid = c.oid AND att.attnum = u.attnum
        WHERE n.nspname = %s
        AND c.relname = %s
        AND con.contype = 'p'
        GROUP BY con.conname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema, table))
        
        if df.empty:
            return None
        
        row = df.iloc[0]
        return PrimaryKey(
            constraint_name=row['constraint_name'],
            columns=row['columns']
        )
    
    def _get_foreign_keys(self, schema: str, table: str) -> List[ForeignKey]:
        """Get foreign key constraints."""
        query = """
        SELECT 
            con.conname as constraint_name,
            array_agg(att.attname ORDER BY u.attposition) as columns,
            nf.nspname as referenced_schema,
            cf.relname as referenced_table,
            array_agg(attf.attname ORDER BY u.attposition) as referenced_columns,
            con.confdeltype as on_delete,
            con.confupdtype as on_update
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_class cf ON con.confrelid = cf.oid
        JOIN pg_catalog.pg_namespace nf ON cf.relnamespace = nf.oid
        JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS u(attnum, attposition) ON TRUE
        JOIN pg_catalog.pg_attribute att ON att.attrelid = c.oid AND att.attnum = u.attnum
        JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS uf(attnum, attposition) ON uf.attposition = u.attposition
        JOIN pg_catalog.pg_attribute attf ON attf.attrelid = cf.oid AND attf.attnum = uf.attnum
        WHERE n.nspname = %s
        AND c.relname = %s
        AND con.contype = 'f'
        GROUP BY con.conname, nf.nspname, cf.relname, con.confdeltype, con.confupdtype;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema, table))
        
        fkeys = []
        for _, row in df.iterrows():
            fkeys.append(ForeignKey(
                constraint_name=row['constraint_name'],
                columns=row['columns'],
                referenced_schema=row['referenced_schema'],
                referenced_table=row['referenced_table'],
                referenced_columns=row['referenced_columns'],
                on_delete=row['on_delete'],
                on_update=row['on_update'],
            ))
        
        return fkeys
    
    def _get_indexes(self, schema: str, table: str) -> List[Index]:
        """Get table indexes."""
        query = """
        SELECT 
            i.relname as index_name,
            array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) as columns,
            ix.indisunique as is_unique,
            am.amname as index_type
        FROM pg_catalog.pg_index ix
        JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
        JOIN pg_catalog.pg_class c ON c.oid = ix.indrelid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_am am ON i.relam = am.oid
        JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS u(attnum, attposition) ON TRUE
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = u.attnum
        WHERE n.nspname = %s
        AND c.relname = %s
        AND NOT ix.indisprimary
        GROUP BY i.relname, ix.indisunique, am.amname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema, table))
        
        indexes = []
        for _, row in df.iterrows():
            indexes.append(Index(
                index_name=row['index_name'],
                columns=row['columns'],
                is_unique=row['is_unique'],
                index_type=row['index_type'],
            ))
        
        return indexes
    
    def _get_constraints(self, schema: str, table: str) -> List[TableConstraint]:
        """Get check and unique constraints."""
        query = """
        SELECT 
            con.conname as constraint_name,
            CASE con.contype
                WHEN 'c' THEN 'CHECK'
                WHEN 'u' THEN 'UNIQUE'
            END as constraint_type,
            pg_catalog.pg_get_constraintdef(con.oid, true) as definition,
            array_agg(att.attname) as columns
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        LEFT JOIN LATERAL unnest(con.conkey) AS u(attnum) ON TRUE
        LEFT JOIN pg_catalog.pg_attribute att ON att.attrelid = c.oid AND att.attnum = u.attnum
        WHERE n.nspname = %s
        AND c.relname = %s
        AND con.contype IN ('c', 'u')
        GROUP BY con.conname, con.contype, con.oid;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema, table))
        
        constraints = []
        for _, row in df.iterrows():
            constraints.append(TableConstraint(
                constraint_name=row['constraint_name'],
                constraint_type=row['constraint_type'],
                definition=row['definition'],
                columns=row['columns'] if row['columns'] else None,
            ))
        
        return constraints
    
    def _get_row_count(self, schema: str, table: str) -> Optional[int]:
        """Get approximate row count."""
        try:
            query = f"SELECT COUNT(*) FROM {schema}.{table}"
            with self.conn_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    return cur.fetchone()[0]
        except:
            return None
    
    def _get_table_size(self, schema: str, table: str) -> Optional[int]:
        """Get table size in bytes."""
        query = """
        SELECT 
            SUM(size) as size_bytes
        FROM svv_table_info
        WHERE schema = %s
        AND "table" = %s;
        """
        
        try:
            with self.conn_manager.get_connection() as conn:
                df = pd.read_sql(query, conn, params=(schema, table))
            return int(df.iloc[0]['size_bytes']) if not df.empty else None
        except:
            return None
    
    def _get_last_modified(self, schema: str, table: str) -> Optional[str]:
        """Get last modified timestamp."""
        query = """
        SELECT 
            MAX(last_altered) as last_modified
        FROM svv_table_info
        WHERE schema = %s
        AND "table" = %s;
        """
        
        try:
            with self.conn_manager.get_connection() as conn:
                df = pd.read_sql(query, conn, params=(schema, table))
            return str(df.iloc[0]['last_modified']) if not df.empty else None
        except:
            return None
    
    def extract_schema_relationships(self, schema: str) -> Dict[str, List[Dict]]:
        """
        Extract all relationships within a schema for ER diagram generation.
        Redshift-compatible version without LATERAL UNNEST.
        
        Returns:
            Dict with relationship information suitable for diagram rendering
        """
        # Redshift 8.0 compatible query - no LATERAL UNNEST
        query = """
        SELECT 
            c.relname as from_table,
            con.conname as constraint_name,
            cf.relname as to_table,
            pg_catalog.pg_get_constraintdef(con.oid, true) as constraint_def
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON con.conrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_catalog.pg_class cf ON con.confrelid = cf.oid
        WHERE n.nspname = %s
        AND con.contype = 'f'
        ORDER BY c.relname, con.conname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        # Parse constraint definition to extract column names
        relationships = []
        for _, row in df.iterrows():
            # Parse "FOREIGN KEY (col1, col2) REFERENCES table(ref1, ref2)"
            constraint_def = row['constraint_def']
            
            # Extract source columns
            from_cols_match = constraint_def.split('FOREIGN KEY (')[1].split(')')[0]
            from_columns = [col.strip() for col in from_cols_match.split(',')]
            
            # Extract target columns
            to_cols_match = constraint_def.split('REFERENCES')[1].split('(')[1].split(')')[0]
            to_columns = [col.strip() for col in to_cols_match.split(',')]
            
            relationships.append({
                'from_table': row['from_table'],
                'constraint_name': row['constraint_name'],
                'from_columns': from_columns,
                'to_table': row['to_table'],
                'to_columns': to_columns,
            })
        
        return {
            'schema': schema,
            'relationships': relationships
        }

