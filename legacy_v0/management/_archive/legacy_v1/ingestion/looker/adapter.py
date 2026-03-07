"""
LookerAdapter - Converts LookML Explore JSON to SemanticSnapshot.

This adapter implements the Source-Agnostic Ingestion Contract by mapping
LookML explores, dimensions, measures, and joins into the canonical
SemanticSnapshot format.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List

from datashark.core.types import (
    SemanticSnapshot,
    Entity,
    FieldDef,
    JoinDef,
    FieldType,
    JoinType,
)


class LookerAdapter:
    """
    Adapter for converting LookML Explore JSON to SemanticSnapshot.
    
    Implements the Source-Agnostic Ingestion Contract:
    - Maps LookML explores to Entity objects
    - Maps LookML dimensions/measures to FieldDef objects
    - Maps LookML joins to JoinDef objects
    - Computes deterministic snapshot_id via SHA-256
    """
    
    def __init__(self):
        """Initialize the Looker adapter."""
        pass
    
    def ingest(self, lookml_explore: Dict[str, Any]) -> SemanticSnapshot:
        """
        Ingest LookML Explore JSON and produce a SemanticSnapshot.
        
        Args:
            lookml_explore: Dictionary containing LookML explore structure:
                - name: Explore name (e.g., "orders")
                - sql_table_name: Base table name
                - dimensions: List of dimension definitions
                - measures: List of measure definitions
                - joins: List of join definitions
        
        Returns:
            SemanticSnapshot with deterministic snapshot_id
        """
        explore_name = lookml_explore.get("name", "unknown")
        base_table = lookml_explore.get("sql_table_name", explore_name)
        
        # Build fields and entity field lists first (entities are frozen)
        fields: Dict[str, FieldDef] = {}
        entity_field_lists: Dict[str, List[str]] = {}  # entity_id -> list of field_ids
        joins: List[JoinDef] = []
        
        # Initialize base entity field list
        base_entity_id = f"entity:{explore_name}"
        entity_field_lists[base_entity_id] = []
        
        # Process base entity dimensions
        for dim in lookml_explore.get("dimensions", []):
            dim_name = dim.get("name", "")
            field_id = f"field:{explore_name}:{dim_name}"
            
            # Determine field type
            field_type = FieldType.DIMENSION
            if dim.get("type") == "time":
                field_type = FieldType.TIMESTAMP
            elif dim.get("primary_key") or dim_name.endswith("_id"):
                field_type = FieldType.ID
            
            field_def = FieldDef(
                id=field_id,
                entity_id=base_entity_id,
                name=dim_name,
                field_type=field_type,
                data_type=dim.get("sql", {}).get("type", "VARCHAR"),
                nullable=dim.get("nullable", True),
                primary_key=dim.get("primary_key", False),
                description=dim.get("description"),
                valid_values=dim.get("allowed_values")
            )
            fields[field_id] = field_def
            entity_field_lists[base_entity_id].append(field_id)
        
        # Process base entity measures
        for measure in lookml_explore.get("measures", []):
            measure_name = measure.get("name", "")
            field_id = f"field:{explore_name}:{measure_name}"
            
            field_def = FieldDef(
                id=field_id,
                entity_id=base_entity_id,
                name=measure_name,
                field_type=FieldType.MEASURE,
                data_type=measure.get("sql", {}).get("type", "DECIMAL(10,2)"),
                nullable=True,
                primary_key=False,
                description=measure.get("description")
            )
            fields[field_id] = field_def
            entity_field_lists[base_entity_id].append(field_id)
        
        # Process joins (including nested joins)
        def process_join(join_def: Dict[str, Any], source_entity_id: str) -> None:
            """Recursively process a join definition and its nested joins."""
            join_name = join_def.get("name", "")
            join_table = join_def.get("sql_table_name", join_name)
            
            # Initialize joined entity field list if not exists
            joined_entity_id = f"entity:{join_name}"
            if joined_entity_id not in entity_field_lists:
                entity_field_lists[joined_entity_id] = []
                
                # Add dimensions/measures from joined explore
                for dim in join_def.get("dimensions", []):
                    dim_name = dim.get("name", "")
                    field_id = f"field:{join_name}:{dim_name}"
                    
                    field_type = FieldType.DIMENSION
                    if dim.get("type") == "time":
                        field_type = FieldType.TIMESTAMP
                    elif dim.get("primary_key") or dim_name.endswith("_id"):
                        field_type = FieldType.ID
                    
                    field_def = FieldDef(
                        id=field_id,
                        entity_id=joined_entity_id,
                        name=dim_name,
                        field_type=field_type,
                        data_type=dim.get("sql", {}).get("type", "VARCHAR"),
                        nullable=dim.get("nullable", True),
                        primary_key=dim.get("primary_key", False),
                        description=dim.get("description"),
                        valid_values=dim.get("allowed_values")
                    )
                    fields[field_id] = field_def
                    entity_field_lists[joined_entity_id].append(field_id)
                
                for measure in join_def.get("measures", []):
                    measure_name = measure.get("name", "")
                    field_id = f"field:{join_name}:{measure_name}"
                    
                    field_def = FieldDef(
                        id=field_id,
                        entity_id=joined_entity_id,
                        name=measure_name,
                        field_type=FieldType.MEASURE,
                        data_type=measure.get("sql", {}).get("type", "DECIMAL(10,2)"),
                        nullable=True,
                        primary_key=False,
                        description=measure.get("description")
                    )
                    fields[field_id] = field_def
                    entity_field_lists[joined_entity_id].append(field_id)
            
            # Create join relationship
            sql_on = join_def.get("sql_on", "")
            source_field = None
            target_field = None
            
            # Try to extract fields from sql_on (e.g., "${orders.product_id} = ${products.id}")
            if "=" in sql_on:
                parts = sql_on.split("=")
                if len(parts) == 2:
                    # Extract field names from ${entity.field} syntax
                    source_match = re.search(r'\$\{([^}]+)\.([^}]+)\}', parts[0])
                    target_match = re.search(r'\$\{([^}]+)\.([^}]+)\}', parts[1])
                    
                    if source_match and target_match:
                        source_entity_name, source_field_name = source_match.groups()
                        target_entity_name, target_field_name = target_match.groups()
                        
                        source_field = f"field:{source_entity_name}:{source_field_name}"
                        target_field = f"field:{target_entity_name}:{target_field_name}"
            
            # Fallback: use relationship fields if provided
            if not source_field:
                relationship = join_def.get("relationship", {})
                source_entity_name = source_entity_id.replace("entity:", "")
                source_field = f"field:{source_entity_name}:{relationship.get('from', 'id')}"
                target_field = f"field:{join_name}:{relationship.get('to', 'id')}"
            
            # Determine join type
            join_type_str = join_def.get("type", "left_outer").upper()
            if "INNER" in join_type_str:
                join_type = JoinType.INNER
            elif "RIGHT" in join_type_str:
                join_type = JoinType.RIGHT
            elif "FULL" in join_type_str:
                join_type = JoinType.FULL
            else:
                join_type = JoinType.LEFT  # Default to LEFT
            
            join_id = f"join:{source_entity_id.replace('entity:', '')}:{join_name}"
            join = JoinDef(
                id=join_id,
                source_entity_id=source_entity_id,
                target_entity_id=joined_entity_id,
                join_type=join_type,
                source_field_id=source_field or f"field:{source_entity_id.replace('entity:', '')}:id",
                target_field_id=target_field or f"field:{join_name}:id",
                description=join_def.get("description")
            )
            joins.append(join)
            
            # Process nested joins recursively
            for nested_join_def in join_def.get("joins", []):
                process_join(nested_join_def, joined_entity_id)
        
        # Process all top-level joins
        for join_def in lookml_explore.get("joins", []):
            process_join(join_def, base_entity_id)
        
        # Build entities with complete field lists (entities are frozen, so build once)
        # Process all entities (including nested joins)
        def build_entity_from_join_def(join_def: Dict[str, Any], source_entity_id: str) -> None:
            """Recursively build entities from join definitions."""
            join_name = join_def.get("name", "")
            joined_entity_id = f"entity:{join_name}"
            
            if joined_entity_id not in final_entities:
                final_entities[joined_entity_id] = Entity(
                    id=joined_entity_id,
                    name=join_name,
                    schema_name=join_def.get("schema", None),
                    description=join_def.get("description"),
                    fields=entity_field_lists.get(joined_entity_id, []),
                    grain=join_def.get("grain")
                )
            
            # Process nested joins
            for nested_join_def in join_def.get("joins", []):
                build_entity_from_join_def(nested_join_def, joined_entity_id)
        
        final_entities: Dict[str, Entity] = {}
        
        # Base entity
        final_entities[base_entity_id] = Entity(
            id=base_entity_id,
            name=explore_name,
            schema_name=lookml_explore.get("schema", None),
            description=lookml_explore.get("description"),
            fields=entity_field_lists[base_entity_id],
            grain=lookml_explore.get("grain")
        )
        
        # Joined entities (including nested)
        for join_def in lookml_explore.get("joins", []):
            build_entity_from_join_def(join_def, base_entity_id)
        
        # Compute deterministic snapshot_id
        snapshot_dict = {
            "source_system": "looker",
            "source_version": lookml_explore.get("version", "1.0"),
            "entities": {eid: {
                "id": e.id,
                "name": e.name,
                "schema": e.schema_name,
                "fields": e.fields,
                "grain": e.grain
            } for eid, e in final_entities.items()},
            "fields": {fid: {
                "id": f.id,
                "entity_id": f.entity_id,
                "name": f.name,
                "field_type": f.field_type.value,
                "data_type": f.data_type,
                "nullable": f.nullable,
                "primary_key": f.primary_key
            } for fid, f in fields.items()},
            "joins": [{
                "id": j.id,
                "source_entity_id": j.source_entity_id,
                "target_entity_id": j.target_entity_id,
                "join_type": j.join_type.value,
                "source_field_id": j.source_field_id,
                "target_field_id": j.target_field_id
            } for j in joins]
        }
        
        # Deterministic serialization
        snapshot_json = json.dumps(snapshot_dict, sort_keys=True, ensure_ascii=False)
        snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
        
        # Create SemanticSnapshot
        snapshot = SemanticSnapshot(
            snapshot_id=snapshot_id,
            source_system="looker",
            source_version=lookml_explore.get("version", "1.0"),
            entities=final_entities,
            fields=fields,
            joins=joins,
            metadata={"lookml_explore": explore_name}
        )
        
        return snapshot

