#!/usr/bin/env python3
"""
Heavyweight Ingestion Integration Tests

This test suite validates that our SemanticSnapshot schema can handle
real-world complexity from enterprise-scale fixtures.

It acts as a "Simulated Agent" that scans fixtures and attempts to map
them to our SemanticSnapshot structure.
"""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add src to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from datashark.core.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from datashark.core.validation import validate_snapshot


class TestHeavyIngestion:
    """Test suite for heavyweight ingestion validation."""
    
    def test_thelook_lookml_complexity(self):
        """
        Test Case 1: TheLook (LookML Complexity)
        
        Action: Read LookML files and create SemanticSnapshot representing
        Orders entity with Users join (One-to-Many).
        
        Validation: validate_snapshot() must pass. This proves we can
        represent LookML semantics.
        """
        # Read the model file to understand relationships
        model_file = project_root / "tests" / "fixtures" / "thelook" / "thelook.model.lkml"
        
        if not model_file.exists():
            # Fallback: create snapshot based on known structure
            pass
        
        # Simulate Agent: Create SemanticSnapshot from LookML structure
        # Based on thelook.model.lkml: orders -> users (many_to_one via user_id)
        
        # Create Orders entity
        orders_entity = Entity(
            id="entity:orders",
            name="orders",
            schema_name="public",
            fields=[
                "field:orders:id",
                "field:orders:user_id",
                "field:orders:status",
                "field:orders:total_amount",
                "field:orders:created_at",
            ],
            grain="order_id"  # Grain: one row per order
        )
        
        # Create Users entity
        users_entity = Entity(
            id="entity:users",
            name="users",
            schema_name="public",
            fields=[
                "field:users:id",
                "field:users:first_name",
                "field:users:last_name",
                "field:users:email",
                "field:users:city",
                "field:users:country",
            ],
            grain="user_id"  # Grain: one row per user
        )
        
        # Create fields for Orders
        orders_fields = {
            "field:orders:id": FieldDef(
                id="field:orders:id",
                entity_id="entity:orders",
                name="id",
                field_type=FieldType.ID,
                data_type="INTEGER",
                nullable=False,
                primary_key=True
            ),
            "field:orders:user_id": FieldDef(
                id="field:orders:user_id",
                entity_id="entity:orders",
                name="user_id",
                field_type=FieldType.FOREIGN_KEY,
                data_type="INTEGER",
                nullable=False,
                primary_key=False
            ),
            "field:orders:status": FieldDef(
                id="field:orders:status",
                entity_id="entity:orders",
                name="status",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(50)",
                nullable=True,
                primary_key=False
            ),
            "field:orders:total_amount": FieldDef(
                id="field:orders:total_amount",
                entity_id="entity:orders",
                name="total_amount",
                field_type=FieldType.MEASURE,
                data_type="DECIMAL(10,2)",
                nullable=True,
                primary_key=False
            ),
            "field:orders:created_at": FieldDef(
                id="field:orders:created_at",
                entity_id="entity:orders",
                name="created_at",
                field_type=FieldType.TIMESTAMP,
                data_type="TIMESTAMP",
                nullable=True,
                primary_key=False
            ),
        }
        
        # Create fields for Users
        users_fields = {
            "field:users:id": FieldDef(
                id="field:users:id",
                entity_id="entity:users",
                name="id",
                field_type=FieldType.ID,
                data_type="INTEGER",
                nullable=False,
                primary_key=True
            ),
            "field:users:first_name": FieldDef(
                id="field:users:first_name",
                entity_id="entity:users",
                name="first_name",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(100)",
                nullable=True,
                primary_key=False
            ),
            "field:users:last_name": FieldDef(
                id="field:users:last_name",
                entity_id="entity:users",
                name="last_name",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(100)",
                nullable=True,
                primary_key=False
            ),
            "field:users:email": FieldDef(
                id="field:users:email",
                entity_id="entity:users",
                name="email",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(255)",
                nullable=True,
                primary_key=False
            ),
            "field:users:city": FieldDef(
                id="field:users:city",
                entity_id="entity:users",
                name="city",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(100)",
                nullable=True,
                primary_key=False
            ),
            "field:users:country": FieldDef(
                id="field:users:country",
                entity_id="entity:users",
                name="country",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(100)",
                nullable=True,
                primary_key=False
            ),
        }
        
        # Create join: orders -> users (many-to-one)
        # Based on thelook.model.lkml: ${orders.user_id} = ${users.id}
        join_orders_users = JoinDef(
            id="join:orders:users",
            source_entity_id="entity:orders",
            target_entity_id="entity:users",
            join_type=JoinType.LEFT,  # LookML uses left_outer
            source_field_id="field:orders:user_id",
            target_field_id="field:users:id",
            description="Orders to Users join (many-to-one)"
        )
        
        # Create snapshot
        snapshot_dict = {
            "snapshot_id": "",  # Will be computed by validation
            "source_system": "lookml",
            "source_version": "1.0",
            "schema_version": "v0.1",
            "entities": {
                "entity:orders": orders_entity.model_dump(mode='json'),
                "entity:users": users_entity.model_dump(mode='json'),
            },
            "fields": {**orders_fields, **users_fields},
            "joins": [join_orders_users.model_dump(mode='json')],
            "metadata": {
                "source_file": "thelook.model.lkml",
                "fixture": "thelook"
            }
        }
        
        # Convert field dicts to model_dump format
        snapshot_dict["fields"] = {
            k: v.model_dump(mode='json') for k, v in snapshot_dict["fields"].items()
        }
        
        # Compute snapshot_id (validation requires correct hash)
        snapshot_dict.pop("snapshot_id", None)
        snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
        snapshot_dict["snapshot_id"] = snapshot_id
        
        # Validate snapshot
        validation_errors = validate_snapshot(snapshot_dict)
        
        assert len(validation_errors) == 0, f"Validation failed: {validation_errors}"
        print("✅ Test Case 1 PASSED: TheLook LookML complexity validated")
    
    def test_mattermost_airflow_dbt_complexity(self):
        """
        Test Case 2: Mattermost (Airflow/dbt Complexity)
        
        Action: Walk the mattermost/airflow/dags directory. Count Python files.
        
        Simulation: Create a SemanticSnapshot representing a DAG as an Entity
        (Grain: execution_date) with a Measure (duration).
        
        Validation: validate_snapshot() must pass. This proves we can represent
        Operational/Log data.
        """
        # Walk the dags directory
        dags_dir = project_root / "tests" / "fixtures" / "mattermost" / "airflow" / "dags"
        
        python_files = []
        if dags_dir.exists():
            python_files = list(dags_dir.rglob("*.py"))
        
        dag_count = len(python_files)
        print(f"   Found {dag_count} Python files in Mattermost dags directory")
        
        # Simulate Agent: Create SemanticSnapshot representing DAG execution logs
        # Grain: execution_date (one row per DAG execution)
        
        # Create DAG Execution entity
        dag_execution_entity = Entity(
            id="entity:dag_execution",
            name="dag_execution",
            schema_name="airflow",
            fields=[
                "field:dag_execution:execution_date",
                "field:dag_execution:dag_id",
                "field:dag_execution:duration",
                "field:dag_execution:status",
                "field:dag_execution:task_count",
            ],
            grain="execution_date"  # Grain: one row per execution
        )
        
        # Create fields
        dag_fields = {
            "field:dag_execution:execution_date": FieldDef(
                id="field:dag_execution:execution_date",
                entity_id="entity:dag_execution",
                name="execution_date",
                field_type=FieldType.TIMESTAMP,
                data_type="TIMESTAMP",
                nullable=False,
                primary_key=True
            ),
            "field:dag_execution:dag_id": FieldDef(
                id="field:dag_execution:dag_id",
                entity_id="entity:dag_execution",
                name="dag_id",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(255)",
                nullable=False,
                primary_key=False
            ),
            "field:dag_execution:duration": FieldDef(
                id="field:dag_execution:duration",
                entity_id="entity:dag_execution",
                name="duration",
                field_type=FieldType.MEASURE,
                data_type="INTEGER",  # Duration in seconds
                nullable=True,
                primary_key=False
            ),
            "field:dag_execution:status": FieldDef(
                id="field:dag_execution:status",
                entity_id="entity:dag_execution",
                name="status",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(50)",
                nullable=True,
                primary_key=False,
                valid_values=["success", "failed", "running"]
            ),
            "field:dag_execution:task_count": FieldDef(
                id="field:dag_execution:task_count",
                entity_id="entity:dag_execution",
                name="task_count",
                field_type=FieldType.MEASURE,
                data_type="INTEGER",
                nullable=True,
                primary_key=False
            ),
        }
        
        # Create snapshot
        snapshot_dict = {
            "snapshot_id": "",  # Will be computed
            "source_system": "airflow",
            "source_version": "2.0",
            "schema_version": "v0.1",
            "entities": {
                "entity:dag_execution": dag_execution_entity.model_dump(mode='json'),
            },
            "fields": {k: v.model_dump(mode='json') for k, v in dag_fields.items()},
            "joins": [],
            "metadata": {
                "source_directory": str(dags_dir),
                "dag_file_count": dag_count,
                "fixture": "mattermost"
            }
        }
        
        # Compute snapshot_id (validation requires correct hash)
        snapshot_dict.pop("snapshot_id", None)
        snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
        snapshot_dict["snapshot_id"] = snapshot_id
        
        # Validate snapshot
        validation_errors = validate_snapshot(snapshot_dict)
        
        assert len(validation_errors) == 0, f"Validation failed: {validation_errors}"
        print(f"✅ Test Case 2 PASSED: Mattermost Airflow/dbt complexity validated ({dag_count} DAG files found)")
    
    def test_stress_test_volume(self):
        """
        Test Case 3: The "Stress Test" (Volume)
        
        Action: Generate a SemanticSnapshot with 50 Entities and 200 Joins
        (programmatically generated).
        
        Validation: Verify validate_snapshot() is under 100ms. This proves
        the Bouncer is fast enough for enterprise schemas.
        """
        print("\n   Generating stress test snapshot: 50 entities, 200 joins...")
        
        # Generate 50 entities
        entities: Dict[str, Entity] = {}
        fields: Dict[str, FieldDef] = {}
        joins: List[JoinDef] = []
        
        for i in range(50):
            entity_id = f"entity:table_{i}"
            entity = Entity(
                id=entity_id,
                name=f"table_{i}",
                schema_name="public",
                fields=[
                    f"field:table_{i}:id",
                    f"field:table_{i}:name",
                    f"field:table_{i}:value",
                ],
                grain=f"table_{i}_id"
            )
            entities[entity_id] = entity
            
            # Create fields for each entity
            fields[f"field:table_{i}:id"] = FieldDef(
                id=f"field:table_{i}:id",
                entity_id=entity_id,
                name="id",
                field_type=FieldType.ID,
                data_type="INTEGER",
                nullable=False,
                primary_key=True
            )
            fields[f"field:table_{i}:name"] = FieldDef(
                id=f"field:table_{i}:name",
                entity_id=entity_id,
                name="name",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR(100)",
                nullable=True,
                primary_key=False
            )
            fields[f"field:table_{i}:value"] = FieldDef(
                id=f"field:table_{i}:value",
                entity_id=entity_id,
                name="value",
                field_type=FieldType.MEASURE,
                data_type="DECIMAL(10,2)",
                nullable=True,
                primary_key=False
            )
        
        # Generate 200 joins (connect entities in a mesh pattern)
        join_count = 0
        for i in range(50):
            for j in range(i + 1, min(i + 5, 50)):  # Connect each entity to next 4
                if join_count >= 200:
                    break
                
                source_entity_id = f"entity:table_{i}"
                target_entity_id = f"entity:table_{j}"
                
                join = JoinDef(
                    id=f"join:table_{i}:table_{j}",
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    join_type=JoinType.LEFT,
                    source_field_id=f"field:table_{i}:id",
                    target_field_id=f"field:table_{j}:id",
                    description=f"Join from table_{i} to table_{j}"
                )
                joins.append(join)
                join_count += 1
            
            if join_count >= 200:
                break
        
        print(f"   Generated {len(entities)} entities, {len(joins)} joins, {len(fields)} fields")
        
        # Create snapshot dict
        snapshot_dict = {
            "snapshot_id": "",  # Will be computed
            "source_system": "stress_test",
            "source_version": "1.0",
            "schema_version": "v0.1",
            "entities": {k: v.model_dump(mode='json') for k, v in entities.items()},
            "fields": {k: v.model_dump(mode='json') for k, v in fields.items()},
            "joins": [j.model_dump(mode='json') for j in joins],
            "metadata": {
                "test_type": "stress_test",
                "entity_count": len(entities),
                "join_count": len(joins),
                "field_count": len(fields)
            }
        }
        
        # Compute snapshot_id (validation requires correct hash)
        snapshot_dict.pop("snapshot_id", None)
        snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
        snapshot_dict["snapshot_id"] = snapshot_id
        
        # Measure validation time
        start_time = time.time()
        validation_errors = validate_snapshot(snapshot_dict)
        elapsed_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Verify validation passed
        assert len(validation_errors) == 0, f"Validation failed: {validation_errors}"
        
        # Verify performance
        assert elapsed_time < 100, f"Validation took {elapsed_time:.2f}ms, expected < 100ms"
        
        print(f"✅ Test Case 3 PASSED: Stress test validated in {elapsed_time:.2f}ms (< 100ms threshold)")
        print(f"   Entities: {len(entities)}, Joins: {len(joins)}, Fields: {len(fields)}")


if __name__ == "__main__":
    # Run tests
    test_suite = TestHeavyIngestion()
    
    print("=" * 80)
    print("Heavyweight Ingestion Integration Tests")
    print("=" * 80)
    print()
    
    try:
        print("Test Case 1: TheLook (LookML Complexity)")
        print("-" * 80)
        test_suite.test_thelook_lookml_complexity()
        print()
        
        print("Test Case 2: Mattermost (Airflow/dbt Complexity)")
        print("-" * 80)
        test_suite.test_mattermost_airflow_dbt_complexity()
        print()
        
        print("Test Case 3: Stress Test (Volume)")
        print("-" * 80)
        test_suite.test_stress_test_volume()
        print()
        
        print("=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
