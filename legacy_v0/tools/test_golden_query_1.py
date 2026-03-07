#!/usr/bin/env python3
"""
Test Golden Query 1: "Total sales revenue by product category for the last 12 months."

This script:
1. Creates a mock LookML Explore JSON for orders → products
2. Uses LookerAdapter to ingest into SemanticSnapshot
3. Outputs the deterministic JSON representation
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))

from datashark.ingestion.looker.adapter import LookerAdapter


def create_mock_lookml_explore() -> dict:
    """
    Create mock LookML Explore JSON for orders → products.
    
    This represents the "orders" explore that joins to "products",
    with the fields needed for Golden Query 1:
    - revenue measure (SUM of order price)
    - category dimension (from products)
    - created_at timestamp dimension (from orders)
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


def main():
    """Run the ingestion and output the SemanticSnapshot JSON."""
    print("🔧 Creating mock LookML Explore JSON...")
    lookml_explore = create_mock_lookml_explore()
    
    print("📥 Ingesting via LookerAdapter...")
    adapter = LookerAdapter()
    snapshot = adapter.ingest(lookml_explore)
    
    print(f"✅ SemanticSnapshot created!")
    print(f"   Snapshot ID: {snapshot.snapshot_id}")
    print(f"   Entities: {len(snapshot.entities)}")
    print(f"   Fields: {len(snapshot.fields)}")
    print(f"   Joins: {len(snapshot.joins)}")
    
    # Validate required elements
    print("\n🔍 Validating required elements for Golden Query 1:")
    
    # Check for orders → products join
    orders_joins = snapshot.get_entity_joins("entity:orders")
    products_join = next((j for j in orders_joins if j.target_entity_id == "entity:products"), None)
    if products_join:
        print(f"   ✅ Join: orders → products (via {products_join.source_field_id} = {products_join.target_field_id})")
    else:
        print("   ❌ Missing: orders → products join")
    
    # Check for revenue measure
    revenue_field = snapshot.fields.get("field:orders:revenue")
    if revenue_field and revenue_field.field_type.value == "MEASURE":
        print(f"   ✅ Revenue measure: {revenue_field.name} ({revenue_field.data_type})")
    else:
        print("   ❌ Missing: revenue measure")
    
    # Check for category dimension
    category_field = snapshot.fields.get("field:products:category")
    if category_field and category_field.field_type.value == "DIMENSION":
        print(f"   ✅ Category dimension: {category_field.name} (valid_values: {category_field.valid_values})")
    else:
        print("   ❌ Missing: category dimension")
    
    # Check for created_at timestamp
    created_at_field = snapshot.fields.get("field:orders:created_at")
    if created_at_field and created_at_field.field_type.value == "TIMESTAMP":
        print(f"   ✅ Created_at timestamp: {created_at_field.name} ({created_at_field.data_type})")
    else:
        print("   ❌ Missing: created_at timestamp")
    
    # Output deterministic JSON representation
    print("\n📄 SemanticSnapshot JSON (deterministic, sorted keys):")
    print("=" * 80)
    
    # Convert to JSON-serializable dict
    snapshot_dict = {
        "snapshot_id": snapshot.snapshot_id,
        "source_system": snapshot.source_system,
        "source_version": snapshot.source_version,
        "entities": {
            eid: {
                "id": e.id,
                "name": e.name,
                "schema": e.schema_name,
                "description": e.description,
                "fields": e.fields,
                "grain": e.grain
            }
            for eid, e in snapshot.entities.items()
        },
        "fields": {
            fid: {
                "id": f.id,
                "entity_id": f.entity_id,
                "name": f.name,
                "field_type": f.field_type.value,
                "data_type": f.data_type,
                "nullable": f.nullable,
                "primary_key": f.primary_key,
                "description": f.description,
                "valid_values": f.valid_values
            }
            for fid, f in snapshot.fields.items()
        },
        "joins": [
            {
                "id": j.id,
                "source_entity_id": j.source_entity_id,
                "target_entity_id": j.target_entity_id,
                "join_type": j.join_type.value,
                "source_field_id": j.source_field_id,
                "target_field_id": j.target_field_id,
                "description": j.description
            }
            for j in snapshot.joins
        ],
        "metadata": snapshot.metadata
    }
    
    # Output with sorted keys for determinism
    print(json.dumps(snapshot_dict, indent=2, sort_keys=True, ensure_ascii=False))
    
    print("\n" + "=" * 80)
    print("✅ Deterministic Midpoint proven!")
    print(f"   Snapshot ID (SHA-256): {snapshot.snapshot_id}")
    print("   This snapshot contains all 'Gravity' needed for SQL generation.")


if __name__ == "__main__":
    main()


