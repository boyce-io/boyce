"""
Schema Extractor for Redshift
Introspects database schema and exports it for AI context.
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import pandas as pd
from core.connection_manager import RedshiftConnectionManager


@dataclass
class Column:
    """Represents a database column."""
    name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int
    column_default: Optional[str] = None


@dataclass
class Table:
    """Represents a database table."""
    schema: str
    name: str
    columns: List[Column]
    row_count: Optional[int] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.name}"


class SchemaExtractor:
    """
    Extracts schema metadata from Redshift.
    Optimized for AI context - generates both structured (JSON) and 
    semantic (Markdown) representations.
    """
    
    def __init__(self, connection_manager: RedshiftConnectionManager):
        self.conn_manager = connection_manager
    
    def extract_full_schema(self, schemas: Optional[List[str]] = None) -> List[Table]:
        """
        Extract complete schema information for specified schemas.
        Uses pg_catalog for Redshift compatibility.
        
        Args:
            schemas: List of schema names to include. If None, excludes system schemas.
        
        Returns:
            List of Table objects with full column metadata
        """
        # Query to get all columns with metadata using pg_catalog
        query = """
        SELECT 
            n.nspname as table_schema,
            c.relname as table_name,
            a.attname as column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
            CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END as is_nullable,
            a.attnum as ordinal_position,
            pg_catalog.pg_get_expr(d.adbin, d.adrelid) as column_default
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_catalog.pg_attrdef d ON (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
        WHERE c.relkind = 'r'
        AND a.attnum > 0
        AND NOT a.attisdropped
        AND n.nspname NOT LIKE 'pg_%'
        AND n.nspname != 'information_schema'
        """
        
        if schemas:
            schema_list = "', '".join(schemas)
            query += f" AND n.nspname IN ('{schema_list}')"
        
        query += " ORDER BY n.nspname, c.relname, a.attnum;"
        
        # Execute query and get results as DataFrame
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn)
        
        # Group by table and build Table objects
        tables = []
        for (schema, table_name), group in df.groupby(['table_schema', 'table_name']):
            columns = [
                Column(
                    name=row['column_name'],
                    data_type=row['data_type'],
                    is_nullable=(row['is_nullable'] == 'YES'),
                    ordinal_position=row['ordinal_position'],
                    column_default=row['column_default'],
                )
                for _, row in group.iterrows()
            ]
            
            tables.append(Table(
                schema=schema,
                name=table_name,
                columns=columns,
            ))
        
        return tables
    
    def get_table_row_counts(self, tables: List[Table]) -> Dict[str, int]:
        """
        Get approximate row counts for tables.
        Uses system tables for speed - exact counts are slow on Redshift.
        
        Args:
            tables: List of Table objects
        
        Returns:
            Dict mapping full table names to row counts
        """
        counts = {}
        
        with self.conn_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for table in tables:
                    try:
                        # Use COUNT(*) for smaller tables, system tables for larger
                        query = f"""
                        SELECT COUNT(*) FROM {table.full_name}
                        """
                        cur.execute(query)
                        count = cur.fetchone()[0]
                        counts[table.full_name] = count
                    except Exception:
                        # If count fails, skip it
                        counts[table.full_name] = None
        
        return counts
    
    def list_schemas(self) -> List[str]:
        """
        Get list of non-system schemas in the database.
        Uses pg_namespace for Redshift compatibility.
        
        Returns:
            List of schema names
        """
        query = """
        SELECT nspname as schema_name
        FROM pg_namespace
        WHERE nspname NOT LIKE 'pg_%'
        AND nspname != 'information_schema'
        ORDER BY nspname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn)
        
        return df['schema_name'].tolist()
    
    def export_to_json(self, tables: List[Table], output_path: str):
        """
        Export schema to JSON for structured parsing.
        Optimized for programmatic access.
        
        Args:
            tables: List of Table objects
            output_path: Path to save JSON file
        """
        schema_dict = {
            "tables": [
                {
                    "schema": table.schema,
                    "name": table.name,
                    "full_name": table.full_name,
                    "columns": [asdict(col) for col in table.columns],
                    "row_count": table.row_count,
                }
                for table in tables
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(schema_dict, f, indent=2)
    
    def export_to_markdown(self, tables: List[Table], output_path: str):
        """
        Export schema to Markdown for LLM context.
        Optimized for semantic understanding by AI models.
        
        Args:
            tables: List of Table objects
            output_path: Path to save Markdown file
        """
        lines = [
            "# Database Schema",
            "",
            "This document contains the complete schema of the Redshift database.",
            "Use this as reference when writing SQL queries.",
            "",
        ]
        
        # Group tables by schema
        from itertools import groupby
        tables_sorted = sorted(tables, key=lambda t: t.schema)
        
        for schema, schema_tables in groupby(tables_sorted, key=lambda t: t.schema):
            lines.append(f"## Schema: `{schema}`")
            lines.append("")
            
            for table in schema_tables:
                lines.append(f"### Table: `{table.full_name}`")
                if table.row_count is not None:
                    lines.append(f"*~{table.row_count:,} rows*")
                lines.append("")
                
                lines.append("| Column | Type | Nullable |")
                lines.append("|--------|------|----------|")
                
                for col in table.columns:
                    nullable = "✓" if col.is_nullable else "✗"
                    lines.append(f"| `{col.name}` | {col.data_type} | {nullable} |")
                
                lines.append("")
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))

