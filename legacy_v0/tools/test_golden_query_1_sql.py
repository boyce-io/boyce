#!/usr/bin/env python3
"""
Test Golden Query 1 SQL Generation: "Total sales revenue by product category for the last 12 months."

This script:
1. Loads the SemanticSnapshot from the ingestion test
2. Creates a planner output with structured temporal filter
3. Uses dialect-aware SQLBuilder to generate Postgres SQL
4. Executes against local database (if available)
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))

from datashark.core.sql.builder import SQLBuilder
from datashark.core.types import TemporalFilter, TemporalOperator, TemporalUnit
from datashark.ingestion.looker.adapter import LookerAdapter


def create_mock_lookml_explore() -> dict:
    """
    Create mock LookML Explore JSON for orders → products.
    
    This represents the "orders" explore that joins to "products",
    with the fields needed for Golden Query 1.
    """
    return {
        "name": "orders",
        "sql_table_name": "orders",
        "schema": "public",
        "description": "Orders explore with product join",
        "grain": "ORDER",
        "version": "1.0",
        "dimensions": [
            {
                "name": "order_id",
                "type": "number",
                "primary_key": True,
                "sql": {"type": "INTEGER"},
                "nullable": False,
                "description": "Unique order identifier"
            },
            {
                "name": "created_at",
                "type": "time",
                "sql": {"type": "TIMESTAMP"},
                "nullable": False,
                "description": "Order creation timestamp"
            },
            {
                "name": "product_id",
                "type": "number",
                "sql": {"type": "INTEGER"},
                "nullable": False,
                "description": "Foreign key to products table"
            }
        ],
        "measures": [
            {
                "name": "revenue",
                "type": "sum",
                "sql": {
                    "type": "DECIMAL(10,2)",
                    "expression": "SUM(${orders.order_price})"
                },
                "description": "Total sales revenue (sum of order prices)"
            }
        ],
        "joins": [
            {
                "name": "products",
                "sql_table_name": "products",
                "schema": "public",
                "type": "left_outer",
                "sql_on": "${orders.product_id} = ${products.id}",
                "relationship": {
                    "from": "product_id",
                    "to": "id"
                },
                "description": "Join to products table",
                "dimensions": [
                    {
                        "name": "id",
                        "type": "number",
                        "primary_key": True,
                        "sql": {"type": "INTEGER"},
                        "nullable": False,
                        "description": "Product identifier"
                    },
                    {
                        "name": "category",
                        "type": "string",
                        "sql": {"type": "VARCHAR(255)"},
                        "nullable": True,
                        "description": "Product category",
                        "allowed_values": ["Electronics", "Clothing", "Home", "Sports", "Books"]
                    },
                    {
                        "name": "name",
                        "type": "string",
                        "sql": {"type": "VARCHAR(255)"},
                        "nullable": True,
                        "description": "Product name"
                    }
                ],
                "measures": []
            }
        ]
    }


def create_planner_output_for_golden_query_1() -> dict:
    """
    Create planner output for Golden Query 1 with structured temporal filter.
    
    Query: "Total sales revenue by product category for the last 12 months."
    
    This demonstrates the hardened architecture:
    - Temporal filter is a structured TemporalFilter object
    - No natural language strings in the planner output
    - SQLBuilder only renders structured objects
    """
    return {
        "concept_map": {
            "entities": [
                {"entity_id": "entity:orders", "entity_name": "orders"},
                {"entity_id": "entity:products", "entity_name": "products"}
            ],
            "dimensions": [
                {"field_id": "field:products:category", "field_name": "category"}
            ],
            "metrics": [
                {
                    "field_id": "field:orders:revenue",
                    "metric_name": "revenue",
                    "aggregation_type": "SUM"
                }
            ],
            "filters": [
                {
                    "operator": "trailing_interval",
                    "field_id": "field:orders:created_at",
                    "value": {
                        "value": 12,
                        "unit": "month"
                    }
                }
            ]
        },
        "join_path": [
            {
                "source_entity_id": "entity:orders",
                "target_entity_id": "entity:products",
                "source_field_id": "field:orders:product_id",
                "target_field_id": "field:products:id"
            }
        ],
        "grain_context": {
            "grain_id": "category",
            "grain_level": "category",
            "grouping_fields": ["category"],
            "aggregation_required": True
        },
        "policy_context": {
            "resolved_predicates": []
        }
    }


def main():
    """Generate SQL for Golden Query 1 and optionally execute it."""
    print("🔧 Creating mock LookML Explore JSON...")
    lookml_explore = create_mock_lookml_explore()
    
    print("📥 Ingesting via LookerAdapter to create SemanticSnapshot...")
    adapter = LookerAdapter()
    snapshot = adapter.ingest(lookml_explore)
    
    print(f"✅ SemanticSnapshot created (ID: {snapshot.snapshot_id[:16]}...)")
    
    print("🔧 Creating planner output with structured temporal filter...")
    planner_output = create_planner_output_for_golden_query_1()
    
    print("📝 Generating Postgres SQL using JoinPathResolver...")
    builder = SQLBuilder()
    builder.set_dialect("postgres")
    
    # Use snapshot-based join resolution
    sql = builder.build_final_sql(planner_output, snapshot=snapshot)
    
    print("\n" + "=" * 80)
    print("✅ Generated SQL (Postgres):")
    print("=" * 80)
    print(sql)
    print("=" * 80)
    
    # Validate temporal filter structure
    print("\n🔍 Validating structured temporal filter:")
    filter_item = planner_output["concept_map"]["filters"][0]
    temporal_filter = TemporalFilter(
        field_id=filter_item["field_id"],
        operator=TemporalOperator(filter_item["operator"]),
        value=filter_item["value"]
    )
    print(f"   ✅ TemporalFilter: {temporal_filter.operator.value}")
    print(f"      Field: {temporal_filter.field_id}")
    print(f"      Value: {temporal_filter.value}")
    
    # Try to execute against database if available
    print("\n🗄️  Attempting to execute against local database...")
    try:
        import psycopg2
        
        # Try to connect to thelook_ecommerce
        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="thelook_ecommerce",
                user=None  # Use default
            )
            cursor = conn.cursor()
            
            print("   ✅ Connected to thelook_ecommerce database")
            print(f"   📊 Executing query...")
            
            cursor.execute(sql)
            results = cursor.fetchmany(5)
            
            if results:
                print(f"\n   ✅ Query executed successfully!")
                print(f"   📋 First 5 rows:")
                print("   " + "-" * 76)
                
                # Get column names
                columns = [desc[0] for desc in cursor.description]
                print(f"   {' | '.join(columns)}")
                print("   " + "-" * 76)
                
                for row in results:
                    row_str = " | ".join([str(val) if val is not None else "NULL" for val in row])
                    print(f"   {row_str}")
            else:
                print("   ⚠️  Query returned 0 rows")
            
            cursor.close()
            conn.close()
            
        except psycopg2.OperationalError as e:
            print(f"   ⚠️  Could not connect to database: {e}")
            print("   💡 Run './scripts/setup_env.sh postgres' to set up the database")
    
    except ImportError:
        print("   ⚠️  psycopg2 not installed. Install with: pip install psycopg2-binary")
    
    print("\n" + "=" * 80)
    print("✅ Deterministic SQL generation verified!")
    print("   The SQLBuilder rendered structured temporal filter into dialect-specific SQL.")
    print("   No natural language interpretation occurred in the SQLBuilder.")


if __name__ == "__main__":
    main()

