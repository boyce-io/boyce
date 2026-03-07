#!/usr/bin/env python3
"""
Database Inspector Utility

Inspects local database schema to provide ground truth for mapping logic.
Supports PostgreSQL and DuckDB for Phase 1 validation.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))
sys.path.insert(0, str(project_root / "core"))


def inspect_postgres(database: str, host: str = "localhost", port: int = 5432, user: Optional[str] = None) -> Dict:
    """Inspect PostgreSQL database schema."""
    try:
        import psycopg2
    except ImportError:
        print("❌ Error: psycopg2 not installed. Install with: pip install psycopg2-binary")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user
        )
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("""
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        tables = cursor.fetchall()
        
        schema_info = {
            "database": database,
            "type": "postgresql",
            "tables": []
        }
        
        for schema, table, table_type in tables:
            # Get columns for this table
            cursor.execute("""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table))
            columns = cursor.fetchall()
            
            # Get primary keys
            cursor.execute("""
                SELECT column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = %s
                    AND tc.table_name = %s
                    AND tc.constraint_type = 'PRIMARY KEY'
            """, (schema, table))
            pk_columns = [row[0] for row in cursor.fetchall()]
            
            # Get foreign keys
            cursor.execute("""
                SELECT
                    kcu.column_name,
                    ccu.table_schema AS foreign_table_schema,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = %s
                    AND tc.table_name = %s
            """, (schema, table))
            fks = cursor.fetchall()
            
            table_info = {
                "schema": schema,
                "name": table,
                "type": table_type,
                "columns": [],
                "primary_keys": pk_columns,
                "foreign_keys": []
            }
            
            for col_name, data_type, max_length, is_nullable, default in columns:
                col_info = {
                    "name": col_name,
                    "data_type": data_type,
                    "max_length": max_length,
                    "nullable": is_nullable == "YES",
                    "default": default
                }
                table_info["columns"].append(col_info)
            
            for fk_col, fk_schema, fk_table, fk_col_name in fks:
                table_info["foreign_keys"].append({
                    "column": fk_col,
                    "references": {
                        "schema": fk_schema,
                        "table": fk_table,
                        "column": fk_col_name
                    }
                })
            
            schema_info["tables"].append(table_info)
        
        cursor.close()
        conn.close()
        
        return schema_info
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL error: {e}")
        sys.exit(1)


def inspect_duckdb(db_path: str) -> Dict:
    """Inspect DuckDB database schema."""
    try:
        import duckdb
    except ImportError:
        print("❌ Error: duckdb not installed. Install with: pip install duckdb")
        sys.exit(1)
    
    try:
        conn = duckdb.connect(db_path)
        
        # Get all tables
        tables_result = conn.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        """).fetchall()
        
        schema_info = {
            "database": db_path,
            "type": "duckdb",
            "tables": []
        }
        
        for schema, table in tables_result:
            # Get columns
            columns_result = conn.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position
            """).fetchall()
            
            table_info = {
                "schema": schema,
                "name": table,
                "type": "BASE TABLE",
                "columns": [],
                "primary_keys": [],
                "foreign_keys": []
            }
            
            for col_name, data_type, is_nullable in columns_result:
                table_info["columns"].append({
                    "name": col_name,
                    "data_type": data_type,
                    "nullable": is_nullable == "YES",
                    "max_length": None,
                    "default": None
                })
            
            schema_info["tables"].append(table_info)
        
        conn.close()
        
        return schema_info
        
    except Exception as e:
        print(f"❌ DuckDB error: {e}")
        sys.exit(1)


def print_schema_summary(schema_info: Dict):
    """Print human-readable schema summary."""
    print(f"\n📊 Database Schema: {schema_info['database']} ({schema_info['type']})")
    print("=" * 80)
    
    for table in schema_info["tables"]:
        print(f"\n📋 Table: {table['schema']}.{table['name']}")
        print(f"   Type: {table['type']}")
        
        if table["primary_keys"]:
            print(f"   Primary Keys: {', '.join(table['primary_keys'])}")
        
        print(f"   Columns ({len(table['columns'])}):")
        for col in table["columns"]:
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            pk_marker = " [PK]" if col["name"] in table["primary_keys"] else ""
            print(f"     - {col['name']}: {col['data_type']} {nullable}{pk_marker}")
        
        if table["foreign_keys"]:
            print(f"   Foreign Keys:")
            for fk in table["foreign_keys"]:
                ref = fk["references"]
                print(f"     - {fk['column']} -> {ref['schema']}.{ref['table']}.{ref['column']}")


def export_json(schema_info: Dict, output_path: str):
    """Export schema info to JSON file."""
    import json
    with open(output_path, 'w') as f:
        json.dump(schema_info, f, indent=2)
    print(f"\n💾 Schema exported to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect local database schema for Phase 1 validation"
    )
    parser.add_argument(
        "--type",
        choices=["postgres", "duckdb"],
        default="postgres",
        help="Database type (default: postgres)"
    )
    parser.add_argument(
        "--database",
        default="thelook_ecommerce",
        help="Database name (Postgres) or file path (DuckDB)"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="PostgreSQL host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)"
    )
    parser.add_argument(
        "--user",
        help="PostgreSQL user (default: current system user)"
    )
    parser.add_argument(
        "--export",
        help="Export schema to JSON file"
    )
    
    args = parser.parse_args()
    
    if args.type == "postgres":
        schema_info = inspect_postgres(
            database=args.database,
            host=args.host,
            port=args.port,
            user=args.user
        )
    else:
        schema_info = inspect_duckdb(db_path=args.database)
    
    print_schema_summary(schema_info)
    
    if args.export:
        export_json(schema_info, args.export)


if __name__ == "__main__":
    main()


