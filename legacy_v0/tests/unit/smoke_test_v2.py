#!/usr/bin/env python3
"""
Phase 1 Smoke Test - Agentic Sandwich Validation

This test proves the "Agentic Sandwich" works without an LLM:
1. Manual "Agent" output: Hardcoded valid SemanticSnapshot JSON
2. Manual "Chat" output: Hardcoded StructuredFilter
3. Kernel processes: Calls api.process_request()
4. Validates: Returns valid SQL
5. Error handling: Broken snapshot raises ValidationError

This test validates the minimal kernel entrypoint without requiring
any agentic components (no LLM, no parsers, no planners).
"""

import sys
from pathlib import Path

# Add src to path
# smoke_test_v2.py is at: tests/unit/smoke_test_v2.py
# So we need to go up 2 levels to reach repo root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from datashark.core.api import process_request
from datashark.core.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from datashark.core.validation import validate_snapshot
import hashlib
import json


def create_valid_snapshot() -> SemanticSnapshot:
    """
    Create a valid SemanticSnapshot (simulating Agent output).
    
    This represents what the Agent would produce after reading DDL/LookML.
    """
    # Entity: orders table
    orders_entity = Entity(
        id="entity:orders",
        name="orders",
        schema_name="public",
        fields=["field:orders:order_id", "field:orders:amount", "field:orders:order_date"],
        grain="order_id"  # REQUIRED: Every entity must have a grain
    )
    
    # Entity: products table
    products_entity = Entity(
        id="entity:products",
        name="products",
        schema_name="public",
        fields=["field:products:product_id", "field:products:category", "field:products:name"],
        grain="product_id"  # REQUIRED: Every entity must have a grain
    )
    
    # Fields for orders
    order_id_field = FieldDef(
        id="field:orders:order_id",
        entity_id="entity:orders",
        name="order_id",
        field_type=FieldType.ID,
        data_type="INTEGER",
        nullable=False,
        primary_key=True
    )
    
    amount_field = FieldDef(
        id="field:orders:amount",
        entity_id="entity:orders",
        name="amount",
        field_type=FieldType.MEASURE,
        data_type="DECIMAL(10,2)",
        nullable=False,
        primary_key=False
    )
    
    order_date_field = FieldDef(
        id="field:orders:order_date",
        entity_id="entity:orders",
        name="order_date",
        field_type=FieldType.TIMESTAMP,
        data_type="DATE",
        nullable=False,
        primary_key=False
    )
    
    # Fields for products
    product_id_field = FieldDef(
        id="field:products:product_id",
        entity_id="entity:products",
        name="product_id",
        field_type=FieldType.ID,
        data_type="INTEGER",
        nullable=False,
        primary_key=True
    )
    
    category_field = FieldDef(
        id="field:products:category",
        entity_id="entity:products",
        name="category",
        field_type=FieldType.DIMENSION,
        data_type="VARCHAR(100)",
        nullable=True,
        primary_key=False
    )
    
    name_field = FieldDef(
        id="field:products:name",
        entity_id="entity:products",
        name="name",
        field_type=FieldType.DIMENSION,
        data_type="VARCHAR(255)",
        nullable=False,
        primary_key=False
    )
    
    # Join: orders -> products (via product_id)
    orders_products_join = JoinDef(
        id="join:orders:products",
        source_entity_id="entity:orders",
        target_entity_id="entity:products",
        join_type=JoinType.INNER,
        source_field_id="field:orders:product_id",  # Note: We'd need this field, but for simplicity using product_id
        target_field_id="field:products:product_id"
    )
    
    # Add product_id field to orders for the join
    product_id_fk_field = FieldDef(
        id="field:orders:product_id",
        entity_id="entity:orders",
        name="product_id",
        field_type=FieldType.FOREIGN_KEY,
        data_type="INTEGER",
        nullable=True,
        primary_key=False
    )
    
    # Update orders entity to include product_id field
    orders_entity = Entity(
        id="entity:orders",
        name="orders",
        schema_name="public",
        fields=["field:orders:order_id", "field:orders:product_id", "field:orders:amount", "field:orders:order_date"],
        grain="order_id"
    )
    
    # Create snapshot with join
    snapshot = SemanticSnapshot(
        snapshot_id="",  # Will be computed by validation
        source_system="smoke_test",
        source_version="1.0",
        schema_version="v0.1",
        entities={
            "entity:orders": orders_entity,
            "entity:products": products_entity,
        },
        fields={
            "field:orders:order_id": order_id_field,
            "field:orders:product_id": product_id_fk_field,
            "field:orders:amount": amount_field,
            "field:orders:order_date": order_date_field,
            "field:products:product_id": product_id_field,
            "field:products:category": category_field,
            "field:products:name": name_field,
        },
        joins=[orders_products_join],
        metadata={}
    )
    
    # Compute snapshot_id (matching validation logic)
    snapshot_dict = snapshot.model_dump(mode='json')
    snapshot_dict.pop("snapshot_id", None)
    snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
    
    # Create snapshot with computed ID
    snapshot_with_id = SemanticSnapshot(**{**snapshot.model_dump(), "snapshot_id": snapshot_id})
    
    return snapshot_with_id


def create_broken_snapshot() -> SemanticSnapshot:
    """
    Create a broken SemanticSnapshot (missing grain) to test validation.
    """
    # Entity WITHOUT grain (should fail validation)
    broken_entity = Entity(
        id="entity:orders",
        name="orders",
        schema_name="public",
        fields=["field:orders:order_id"],
        grain=None  # MISSING GRAIN - should fail validation
    )
    
    order_id_field = FieldDef(
        id="field:orders:order_id",
        entity_id="entity:orders",
        name="order_id",
        field_type=FieldType.ID,
        data_type="INTEGER",
        nullable=False,
        primary_key=True
    )
    
    snapshot = SemanticSnapshot(
        snapshot_id="test_hash",
        source_system="smoke_test",
        source_version="1.0",
        schema_version="v0.1",
        entities={"entity:orders": broken_entity},
        fields={"field:orders:order_id": order_id_field},
        joins=[],
        metadata={}
    )
    
    return snapshot


def create_structured_filter() -> dict:
    """
    Create a structured filter (simulating Chat Interface output).
    
    This represents what the Chat Interface would produce after
    translating natural language to structured filters.
    """
    return {
        "concept_map": {
            "entities": [
                {
                    "term": "orders",
                    "entity_id": "entity:orders",
                    "entity_name": "orders"
                }
            ],
            "metrics": [
                {
                    "term": "amount",
                    "field_id": "field:orders:amount",
                    "metric_name": "amount",  # SQLBuilder expects "metric_name" not "field_name"
                    "aggregation_type": "SUM"
                }
            ],
            "dimensions": [
                {
                    "term": "order_date",
                    "field_id": "field:orders:order_date",
                    "field_name": "order_date"
                }
            ]
        },
        "filters": [],
        "temporal_filters": [],
        "join_path": [],
        "grain_context": {
            "grain_id": "order_id",
            "grouping_fields": ["order_date"],
            "aggregation_required": True
        },
        "policy_context": {
            "resolved_predicates": []
        },
        "dialect": "postgres"
    }


def test_valid_snapshot_produces_sql():
    """Test Step 1-4: Valid snapshot + structured filter produces SQL."""
    print("=" * 80)
    print("Test 1: Valid Snapshot Produces SQL")
    print("=" * 80)
    
    # Step 1: Create valid snapshot (Agent output)
    snapshot = create_valid_snapshot()
    print(f"✅ Created valid snapshot with {len(snapshot.entities)} entities, {len(snapshot.fields)} fields")
    
    # Step 2: Create structured filter (Chat output)
    structured_filter = create_structured_filter()
    print(f"✅ Created structured filter")
    
    # Step 3: Call api.process_request()
    try:
        sql = process_request(snapshot, structured_filter)
        print(f"✅ Generated SQL:")
        print(f"   {sql}")
        
        # Step 4: Assert valid SQL is returned
        assert sql is not None, "SQL should not be None"
        assert isinstance(sql, str), "SQL should be a string"
        assert len(sql) > 0, "SQL should not be empty"
        assert "SELECT" in sql.upper(), "SQL should contain SELECT"
        print(f"✅ SQL validation passed")
        
        return True
    except Exception as e:
        print(f"❌ SQL generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_broken_snapshot_raises_validation_error():
    """Test Step 5: Broken snapshot (missing grain) raises ValidationError."""
    print("\n" + "=" * 80)
    print("Test 2: Broken Snapshot Raises Validation Error")
    print("=" * 80)
    
    # Create broken snapshot (missing grain)
    broken_snapshot = create_broken_snapshot()
    print(f"✅ Created broken snapshot (missing grain)")
    
    # Create structured filter
    structured_filter = create_structured_filter()
    
    # Attempt to process - should raise ValueError
    try:
        sql = process_request(broken_snapshot, structured_filter)
        print(f"❌ ERROR: Should have raised ValueError, but got SQL: {sql}")
        return False
    except ValueError as e:
        error_msg = str(e)
        print(f"✅ Correctly raised ValueError:")
        print(f"   {error_msg}")
        
        # Assert error mentions grain
        assert "grain" in error_msg.lower(), "Error should mention grain"
        print(f"✅ Validation error correctly identifies missing grain")
        return True
    except Exception as e:
        print(f"❌ ERROR: Raised {type(e).__name__} instead of ValueError: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all smoke tests."""
    print("\n" + "=" * 80)
    print("Phase 1 Smoke Test - Agentic Sandwich Validation")
    print("=" * 80)
    print("\nThis test validates the minimal kernel without requiring LLM/Agent components.")
    print("It simulates:")
    print("  - Layer 1 (Ingestion): Manual valid SemanticSnapshot (Agent output)")
    print("  - Layer 2 (Kernel): api.process_request() (Zero-Agency Determinism)")
    print("  - Layer 3 (Interface): Manual StructuredFilter (Chat output)")
    print()
    
    # Run tests
    test1_passed = test_valid_snapshot_produces_sql()
    test2_passed = test_broken_snapshot_raises_validation_error()
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Test 1 (Valid Snapshot → SQL): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Test 2 (Broken Snapshot → Error): {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n✅ All smoke tests passed! The Agentic Sandwich kernel is working.")
        return 0
    else:
        print("\n❌ Some smoke tests failed. Kernel needs fixes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
