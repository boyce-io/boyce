#!/usr/bin/env python3
"""
Test Join-Path Resolver for Sprint 1 validation.

This script tests that the JoinPathResolver correctly consumes JoinDef objects
from SemanticSnapshot and produces deterministic SQL JOIN clauses.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))

from datashark.core.sql.builder import SQLBuilder
from datashark.core.sql.join_resolver import JoinPathResolver
from datashark.core.types import (
    SemanticSnapshot,
    Entity,
    FieldDef,
    JoinDef,
    FieldType,
    JoinType,
)
from datashark.ingestion.looker.adapter import LookerAdapter


def create_test_snapshot() -> SemanticSnapshot:
    """Create a test snapshot with orders → products join."""
    # Create entities
    orders_entity = Entity(
        id="entity:orders",
        name="orders",
        schema_name="public",
        description="Orders table",
        fields=["field:orders:order_id", "field:orders:product_id", "field:orders:revenue"],
        grain="ORDER"
    )
    
    products_entity = Entity(
        id="entity:products",
        name="products",
        schema_name="public",
        description="Products table",
        fields=["field:products:id", "field:products:category"],
        grain=None
    )
    
    # Create fields
    fields = {
        "field:orders:order_id": FieldDef(
            id="field:orders:order_id",
            entity_id="entity:orders",
            name="order_id",
            field_type=FieldType.ID,
            data_type="INTEGER",
            nullable=False,
            primary_key=True
        ),
        "field:orders:product_id": FieldDef(
            id="field:orders:product_id",
            entity_id="entity:orders",
            name="product_id",
            field_type=FieldType.FOREIGN_KEY,
            data_type="INTEGER",
            nullable=False
        ),
        "field:orders:revenue": FieldDef(
            id="field:orders:revenue",
            entity_id="entity:orders",
            name="revenue",
            field_type=FieldType.MEASURE,
            data_type="DECIMAL(10,2)",
            nullable=True
        ),
        "field:products:id": FieldDef(
            id="field:products:id",
            entity_id="entity:products",
            name="id",
            field_type=FieldType.ID,
            data_type="INTEGER",
            nullable=False,
            primary_key=True
        ),
        "field:products:category": FieldDef(
            id="field:products:category",
            entity_id="entity:products",
            name="category",
            field_type=FieldType.DIMENSION,
            data_type="VARCHAR(255)",
            nullable=True
        ),
    }
    
    # Create join
    join = JoinDef(
        id="join:orders:products",
        source_entity_id="entity:orders",
        target_entity_id="entity:products",
        join_type=JoinType.LEFT,  # Test LEFT OUTER JOIN
        source_field_id="field:orders:product_id",
        target_field_id="field:products:id",
        description="Orders to products join"
    )
    
    # Create snapshot
    snapshot = SemanticSnapshot(
        snapshot_id="test_snapshot_123",
        source_system="test",
        source_version="1.0",
        entities={
            "entity:orders": orders_entity,
            "entity:products": products_entity,
        },
        fields=fields,
        joins=[join],
        metadata={}
    )
    
    return snapshot


def test_join_path_resolver():
    """Test JoinPathResolver with test snapshot."""
    print("🧪 Testing JoinPathResolver...")
    
    snapshot = create_test_snapshot()
    
    from datashark.core.sql.dialects import PostgresDialect
    dialect = PostgresDialect()
    resolver = JoinPathResolver(snapshot, dialect)
    
    # Test resolving join path
    from_clause, join_clauses = resolver.resolve_join_path(
        "entity:orders",
        ["entity:products"]
    )
    
    print(f"✅ FROM clause: {from_clause}")
    print(f"✅ JOIN clauses ({len(join_clauses)}):")
    for i, clause in enumerate(join_clauses, 1):
        print(f"   {i}. {clause}")
    
    # Verify determinism: run twice and compare
    from_clause2, join_clauses2 = resolver.resolve_join_path(
        "entity:orders",
        ["entity:products"]
    )
    
    assert from_clause == from_clause2, "FROM clause not deterministic"
    assert join_clauses == join_clauses2, "JOIN clauses not deterministic"
    assert len(join_clauses) == 1, "Should have exactly 1 join"
    assert "LEFT OUTER JOIN" in join_clauses[0], "Should default to LEFT OUTER JOIN"
    assert "orders" in from_clause, "FROM should reference orders table"
    assert "products" in join_clauses[0], "JOIN should reference products table"
    
    print("✅ Determinism verified: identical inputs produce identical outputs")
    print("✅ Join type verified: defaults to LEFT OUTER JOIN")
    
    return True


def test_sql_builder_with_snapshot():
    """Test SQLBuilder using SemanticSnapshot."""
    print("\n🧪 Testing SQLBuilder with SemanticSnapshot...")
    
    snapshot = create_test_snapshot()
    builder = SQLBuilder()
    builder.set_dialect("postgres")
    
    # Create planner output
    planner_output = {
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
            "filters": []
        },
        "grain_context": {
            "aggregation_required": True,
            "grouping_fields": ["category"]
        },
        "policy_context": {
            "resolved_predicates": []
        }
    }
    
    # Build SQL with snapshot (now required parameter)
    sql = builder.build_final_sql(planner_output, snapshot)
    
    print(f"✅ Generated SQL:")
    print(f"   {sql}")
    
    # Verify SQL contains correct join
    assert "LEFT OUTER JOIN" in sql or "LEFT JOIN" in sql, "SQL should contain LEFT JOIN"
    assert '"orders"' in sql or "orders" in sql, "SQL should reference orders table"
    assert '"products"' in sql or "products" in sql, "SQL should reference products table"
    assert "product_id" in sql, "SQL should reference join key"
    
    # Test determinism: run twice
    sql2 = builder.build_final_sql(planner_output, snapshot=snapshot)
    assert sql == sql2, "SQL generation not deterministic"
    
    print("✅ SQLBuilder with snapshot verified")
    print("✅ Determinism verified: same inputs → same SQL")
    
    return sql


def test_inner_join():
    """Test that INNER join is respected when specified."""
    print("\n🧪 Testing INNER JOIN support...")
    
    snapshot = create_test_snapshot()
    
    # Modify join to be INNER
    inner_join = JoinDef(
        id="join:orders:products",
        source_entity_id="entity:orders",
        target_entity_id="entity:products",
        join_type=JoinType.INNER,  # Explicitly INNER
        source_field_id="field:orders:product_id",
        target_field_id="field:products:id",
        description="Orders to products join (INNER)"
    )
    
    # Create new snapshot with INNER join
    snapshot_inner = SemanticSnapshot(
        snapshot_id="test_snapshot_inner",
        source_system="test",
        entities=snapshot.entities,
        fields=snapshot.fields,
        joins=[inner_join],
        metadata={}
    )
    
    from datashark.core.sql.dialects import PostgresDialect
    dialect = PostgresDialect()
    resolver = JoinPathResolver(snapshot_inner, dialect)
    
    from_clause, join_clauses = resolver.resolve_join_path(
        "entity:orders",
        ["entity:products"]
    )
    
    assert "INNER JOIN" in join_clauses[0], "Should use INNER JOIN when specified"
    assert "LEFT OUTER JOIN" not in join_clauses[0], "Should not default to LEFT when INNER specified"
    
    print("✅ INNER JOIN correctly respected")
    
    return True


def main():
    """Run all tests."""
    print("=" * 80)
    print("Sprint 1: Join-Path Resolver Validation")
    print("=" * 80)
    
    try:
        test_join_path_resolver()
        sql = test_sql_builder_with_snapshot()
        test_inner_join()
        
        print("\n" + "=" * 80)
        print("✅ All tests passed!")
        print("=" * 80)
        print(f"\n📋 Final SQL output:")
        print(f"   {sql}")
        print("\n✅ Sprint 1: Join-Path Resolver - VALIDATED")
        
        return 0
    
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

