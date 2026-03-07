"""
Polyglot Ingestion Parsers

Lightweight parsers for extracting SemanticSnapshot structures from:
- dbt manifest.json files
- dbt raw YAML source files (Phase 5: Silver Standard)
- LookML .lkml files
- SQL DDL files (future)

These parsers extract the "Grain" (Entities/Measures) from standard benchmarks.
"""

from __future__ import annotations

import hashlib
import json
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from datashark.core.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)


def parse_dbt_manifest(manifest_path: Path) -> SemanticSnapshot:
    """
    Parse a dbt manifest.json file and extract SemanticSnapshot structure.
    
    Args:
        manifest_path: Path to dbt manifest.json file
        
    Returns:
        SemanticSnapshot with entities, fields, and joins extracted from dbt models
        
    Logic:
        1. Read manifest.json
        2. Extract nodes (model resource types)
        3. Map dbt models → Entities
        4. Map dbt columns → Fields
        5. Extract relationships → Joins
    """
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
    
    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []
    
    nodes = manifest_data.get("nodes", {})
    sources = manifest_data.get("sources", {})
    
    # Merge nodes and sources for processing
    all_nodes = {**nodes, **sources}
    
    # Extract models and sources (entities)
    for node_id, node_data in all_nodes.items():
        resource_type = node_data.get("resource_type")
        if resource_type not in ["model", "source"]:
            continue  # Skip seeds, tests, etc.
        
        # Extract model/source metadata
        model_name = node_data.get("name", "")
        if resource_type == "source":
            # For sources, entity name might collide with models if not careful
            # But typically models are "fct_orders" and sources are "orders" (in "raw")
            # We will use the table name.
            source_name = node_data.get("source_name", "")
            # To distinguish, we might want to qualify, but for now lets keep it simple:
            # If source name is "raw" and table is "orders", model_name is "orders".
            pass
            
        schema_name = node_data.get("schema", "public")
        database = node_data.get("database", "")
        description = node_data.get("description", "")
        
        # Infer grain from primary key or unique columns
        grain = None
        columns = node_data.get("columns", {})
        primary_keys = []
        
        for col_name, col_data in columns.items():
            meta = col_data.get("meta", {})
            if meta.get("primary_key") or col_name.endswith("_id"):
                primary_keys.append(col_name)
        
        if primary_keys:
            grain = "_".join(primary_keys) if len(primary_keys) > 1 else primary_keys[0]
        else:
            # Try to infer from name patterns
            if model_name.endswith("_fact") or "fact" in model_name.lower():
                grain = "<unknown_grain>"  # Facts need explicit grain
            else:
                # Look for _id columns
                for col_name in columns.keys():
                    if col_name.endswith("_id"):
                        grain = col_name
                        break
                if not grain:
                    grain = "<unknown_grain>"
        
        # Create entity
        entity_id = f"entity:{model_name}"
        entity = Entity(
            id=entity_id,
            name=model_name,
            schema_name=schema_name,
            description=description,
            fields=[],
            grain=grain
        )
        entities[entity_id] = entity
        
        # Extract columns as fields
        for col_name, col_data in columns.items():
            field_id = f"field:{model_name}:{col_name}"
            
            # Determine field type from dbt meta or column name
            col_type = col_data.get("data_type", "VARCHAR")
            meta = col_data.get("meta", {})
            
            # Infer field type
            field_type = FieldType.DIMENSION
            if meta.get("primary_key") or col_name.endswith("_id"):
                field_type = FieldType.ID
            elif col_name in ["created_at", "updated_at", "timestamp", "date"]:
                field_type = FieldType.TIMESTAMP
            elif any(keyword in col_name.lower() for keyword in ["amount", "revenue", "count", "sum", "total"]):
                field_type = FieldType.MEASURE
            elif col_name.endswith("_id") and not meta.get("primary_key"):
                field_type = FieldType.FOREIGN_KEY
            
            field = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=col_name,
                field_type=field_type,
                data_type=col_type.upper(),
                nullable=col_data.get("quote", True),  # Default to nullable
                primary_key=meta.get("primary_key", False),
                description=col_data.get("description", "")
            )
            fields[field_id] = field
            entity.fields.append(field_id)
        
        # Update entity with field list
        entities[entity_id] = Entity(
            id=entity_id,
            name=model_name,
            schema_name=schema_name,
            description=description,
            fields=entity.fields,
            grain=grain
        )
    
    # Extract relationships (from dbt meta or tests)
    # dbt relationships are often in tests or meta
    for node_id, node_data in nodes.items():
        if node_data.get("resource_type") != "model":
            continue
        
        source_model = node_data.get("name", "")
        source_entity_id = f"entity:{source_model}"
        
        if source_entity_id not in entities:
            continue
        
        # Look for relationship tests or meta
        tests = node_data.get("tests", [])
        for test in tests:
            if test.get("test_metadata", {}).get("name") == "relationships":
                # Extract relationship info
                to_model = test.get("test_metadata", {}).get("kwargs", {}).get("to")
                from_field = test.get("test_metadata", {}).get("kwargs", {}).get("from")
                to_field = test.get("test_metadata", {}).get("kwargs", {}).get("field")
                
                if to_model and from_field and to_field:
                    target_entity_id = f"entity:{to_model}"
                    if target_entity_id in entities:
                        source_field_id = f"field:{source_model}:{from_field}"
                        target_field_id = f"field:{to_model}:{to_field}"
                        
                        if source_field_id in fields and target_field_id in fields:
                            join = JoinDef(
                                id=f"join:{source_model}:{to_model}",
                                source_entity_id=source_entity_id,
                                target_entity_id=target_entity_id,
                                join_type=JoinType.LEFT,  # Default to LEFT
                                source_field_id=source_field_id,
                                target_field_id=target_field_id,
                                description=f"dbt relationship: {source_model}.{from_field} -> {to_model}.{to_field}"
                            )
                            joins.append(join)
    
    # Compute snapshot_id
    snapshot_dict = {
        "source_system": "dbt",
        "source_version": manifest_data.get("metadata", {}).get("dbt_schema_version", "1.0"),
        "schema_version": "v0.1",
        "entities": {k: v.model_dump(mode='json') for k, v in entities.items()},
        "fields": {k: v.model_dump(mode='json') for k, v in fields.items()},
        "joins": [j.model_dump(mode='json') for j in joins],
        "metadata": {
            "manifest_path": str(manifest_path),
            "dbt_version": manifest_data.get("metadata", {}).get("dbt_version", "unknown"),
            "source_type": "manifest"  # Mark as Gold Standard
        }
    }
    
    snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
    
    snapshot_dict["snapshot_id"] = snapshot_id
    
    return SemanticSnapshot(**snapshot_dict)


def parse_dbt_project_source(project_root: Path) -> SemanticSnapshot:
    """
    Parse raw dbt YAML source files and extract SemanticSnapshot structure.
    
    This is the "Silver Standard" parser - it parses raw YAML files without
    requiring `dbt compile` to generate manifest.json.
    
    Args:
        project_root: Path to dbt project root (contains dbt_project.yml)
        
    Returns:
        SemanticSnapshot with entities, fields, and joins extracted from raw YAML
        
    Logic:
        1. Read dbt_project.yml to confirm it's a dbt project
        2. Recursively scan for *.yml files in models/ directory
        3. Parse YAML looking for models: list
        4. Extract name (Entity) and columns (Fields)
        5. Look for tests: (e.g., relationships, foreign_key) to extract Joins
    """
    # Step 1: Verify dbt_project.yml exists
    dbt_project_file = project_root / "dbt_project.yml"
    if not dbt_project_file.exists():
        raise ValueError(f"Not a dbt project: dbt_project.yml not found in {project_root}")
    
    # Read dbt_project.yml to get project name
    with open(dbt_project_file, "r") as f:
        dbt_project_data = yaml.safe_load(f)
    
    project_name = dbt_project_data.get("name", "dbt_project")
    models_path = project_root / "models"
    
    if not models_path.exists():
        raise ValueError(f"models/ directory not found in {project_root}")
    
    # Step 2: Recursively scan for *.yml files in models/
    yml_files = list(models_path.rglob("*.yml"))
    
    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []
    
    # Step 3: Parse each YAML file
    for yml_file in yml_files:
        try:
            with open(yml_file, "r") as f:
                yml_data = yaml.safe_load(f)
            
            if not yml_data or "models" not in yml_data:
                continue  # Skip files without models section
            
            models_list = yml_data.get("models", [])
            if not isinstance(models_list, list):
                continue
            
            # Step 4: Extract models and columns
            for model_def in models_list:
                if not isinstance(model_def, dict):
                    continue
                
                model_name = model_def.get("name")
                if not model_name:
                    continue
                
                # Infer grain from primary key columns or _id columns
                grain = None
                columns = model_def.get("columns", [])
                primary_keys = []
                
                for col_def in columns:
                    if not isinstance(col_def, dict):
                        continue
                    col_name = col_def.get("name", "")
                    # Check for primary key in tests
                    tests = col_def.get("tests", [])
                    for test in tests:
                        if isinstance(test, str) and "primary_key" in test.lower():
                            primary_keys.append(col_name)
                        elif isinstance(test, dict) and "primary_key" in str(test).lower():
                            primary_keys.append(col_name)
                
                if primary_keys:
                    grain = "_".join(primary_keys) if len(primary_keys) > 1 else primary_keys[0]
                else:
                    # Look for _id columns
                    for col_def in columns:
                        if isinstance(col_def, dict):
                            col_name = col_def.get("name", "")
                            if col_name.endswith("_id"):
                                grain = col_name
                                break
                    if not grain:
                        grain = "<unknown_grain>"
                
                # Create entity
                entity_id = f"entity:{model_name}"
                entity = Entity(
                    id=entity_id,
                    name=model_name,
                    schema_name="public",  # Default schema
                    description=model_def.get("description"),
                    fields=[],
                    grain=grain
                )
                entities[entity_id] = entity
                
                # Extract columns as fields
                for col_def in columns:
                    if not isinstance(col_def, dict):
                        continue
                    
                    col_name = col_def.get("name", "")
                    if not col_name:
                        continue
                    
                    field_id = f"field:{model_name}:{col_name}"
                    
                    # Infer field type
                    field_type = FieldType.DIMENSION
                    is_primary_key = False
                    
                    # Check tests for primary key
                    tests = col_def.get("tests", [])
                    for test in tests:
                        if isinstance(test, str) and "primary_key" in test.lower():
                            field_type = FieldType.ID
                            is_primary_key = True
                        elif isinstance(test, dict) and "primary_key" in str(test).lower():
                            field_type = FieldType.ID
                            is_primary_key = True
                    
                    if not is_primary_key:
                        if col_name.endswith("_id"):
                            field_type = FieldType.ID if col_name == grain else FieldType.FOREIGN_KEY
                        elif col_name in ["created_at", "updated_at", "timestamp", "date", "received_at"]:
                            field_type = FieldType.TIMESTAMP
                        elif any(keyword in col_name.lower() for keyword in ["amount", "revenue", "count", "sum", "total"]):
                            field_type = FieldType.MEASURE
                    
                    field = FieldDef(
                        id=field_id,
                        entity_id=entity_id,
                        name=col_name,
                        field_type=field_type,
                        data_type="VARCHAR(255)",  # Default, YAML doesn't always specify
                        nullable=True,
                        primary_key=is_primary_key,
                        description=col_def.get("description")
                    )
                    fields[field_id] = field
                    entity.fields.append(field_id)
                    
                    # Step 5: Extract joins from relationship tests
                    for test in tests:
                        if isinstance(test, dict):
                            # Handle relationships test
                            if "relationships" in test:
                                rel_test = test["relationships"]
                                if isinstance(rel_test, dict):
                                    to_model = rel_test.get("to")
                                    to_field = rel_test.get("field")
                                    
                                    # Handle ref() syntax: ref('model_name') -> model_name
                                    if to_model and isinstance(to_model, str):
                                        # Extract model name from ref('model_name') or just 'model_name'
                                        to_model_match = re.search(r"ref\(['\"]?(\w+)['\"]?\)|['\"]?(\w+)['\"]?", to_model)
                                        if to_model_match:
                                            to_model = to_model_match.group(1) or to_model_match.group(2)
                                    
                                    if to_model and to_field:
                                        target_entity_id = f"entity:{to_model}"
                                        target_field_id = f"field:{to_model}:{to_field}"
                                        
                                        # Create join (entities may not exist yet, but will be merged)
                                        join = JoinDef(
                                            id=f"join:{model_name}:{to_model}",
                                            source_entity_id=entity_id,
                                            target_entity_id=target_entity_id,
                                            join_type=JoinType.LEFT,  # Default to LEFT
                                            source_field_id=field_id,
                                            target_field_id=target_field_id,
                                            description=f"dbt relationship (source YAML): {model_name}.{col_name} -> {to_model}.{to_field}"
                                        )
                                        joins.append(join)
        
        except Exception as e:
            # Log but continue processing other files
            print(f"Warning: Failed to parse {yml_file}: {str(e)}")
            continue
    
    # Update entities with field lists
    for entity_id, entity in entities.items():
        entities[entity_id] = Entity(
            id=entity.id,
            name=entity.name,
            schema_name=entity.schema_name,
            description=entity.description,
            fields=entity.fields,
            grain=entity.grain
        )
    
    # Compute snapshot_id
    snapshot_dict = {
        "source_system": "dbt",
        "source_version": "1.0",
        "schema_version": "v0.1",
        "entities": {k: v.model_dump(mode='json') for k, v in entities.items()},
        "fields": {k: v.model_dump(mode='json') for k, v in fields.items()},
        "joins": [j.model_dump(mode='json') for j in joins],
        "metadata": {
            "project_root": str(project_root),
            "project_name": project_name,
            "source_type": "source_yaml"  # Mark as Silver Standard
        }
    }
    
    snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
    
    snapshot_dict["snapshot_id"] = snapshot_id
    
    return SemanticSnapshot(**snapshot_dict)


def parse_lookml_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a LookML .lkml file and extract SemanticSnapshot structure.
    
    Args:
        file_path: Path to LookML .lkml file
        
    Returns:
        SemanticSnapshot with entities, fields, and joins extracted from LookML views
        
    Logic:
        1. Read .lkml file
        2. Extract view: blocks → Entities
        3. Extract dimension: and measure: → Fields
        4. Extract explore: with join: → Joins
    """
    with open(file_path, "r") as f:
        content = f.read()
    
    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []
    
    # Extract views (LookML views are entities)
    # Look for view: name { ... } blocks (need to handle nested braces)
    view_pattern = r'view:\s*(\w+)\s*\{'
    view_matches = list(re.finditer(view_pattern, content))
    
    for i, view_match in enumerate(view_matches):
        view_name = view_match.group(1)
        start_pos = view_match.end()
        
        # Find matching closing brace (handle nested braces)
        brace_count = 1
        end_pos = start_pos
        while brace_count > 0 and end_pos < len(content):
            if content[end_pos] == '{':
                brace_count += 1
            elif content[end_pos] == '}':
                brace_count -= 1
            end_pos += 1
        
        view_content = content[start_pos:end_pos-1] if brace_count == 0 else ""
        
        # Infer grain from primary_key dimensions
        grain = None
        primary_key_dims = re.findall(r'dimension:\s*(\w+)\s*\{[^}]*primary_key:\s*yes', view_content)
        if primary_key_dims:
            grain = primary_key_dims[0]
        else:
            # Look for _id dimensions
            id_dims = re.findall(r'dimension:\s*(\w+_id)\s*\{', view_content)
            if id_dims:
                grain = id_dims[0]
            else:
                grain = "<unknown_grain>"
        
        # Create entity
        entity_id = f"entity:{view_name}"
        entity = Entity(
            id=entity_id,
            name=view_name,
            schema_name="public",  # LookML doesn't specify schema
            description=None,
            fields=[],
            grain=grain
        )
        entities[entity_id] = entity
        
        # Extract dimensions (handle nested braces)
        dim_pattern = r'dimension(?:_group)?:\s*(\w+)\s*\{'
        dim_matches = list(re.finditer(dim_pattern, view_content))
        
        for dim_match in dim_matches:
            dim_name = dim_match.group(1)
            dim_start = dim_match.end()
            
            # Find matching closing brace
            brace_count = 1
            dim_end = dim_start
            while brace_count > 0 and dim_end < len(view_content):
                if view_content[dim_end] == '{':
                    brace_count += 1
                elif view_content[dim_end] == '}':
                    brace_count -= 1
                dim_end += 1
            
            dim_content = view_content[dim_start:dim_end-1] if brace_count == 0 else ""
            
            # Check if primary_key
            is_primary_key = "primary_key: yes" in dim_content
            dim_type_match = re.search(r'type:\s*(\w+)', dim_content)
            dim_type = dim_type_match.group(1) if dim_type_match else "string"
            
            # Map LookML type to SQL data type
            sql_type = "VARCHAR(255)"
            if dim_type == "number":
                sql_type = "DECIMAL(10,2)"
            elif dim_type in ["time", "date"]:
                sql_type = "TIMESTAMP"
            
            # Determine field type
            field_type = FieldType.DIMENSION
            if is_primary_key:
                field_type = FieldType.ID
            elif dim_type in ["time", "date"]:
                field_type = FieldType.TIMESTAMP
            elif dim_name.endswith("_id") and not is_primary_key:
                field_type = FieldType.FOREIGN_KEY
            
            field_id = f"field:{view_name}:{dim_name}"
            field = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=dim_name,
                field_type=field_type,
                data_type=sql_type,
                nullable=True,
                primary_key=is_primary_key,
                description=None
            )
            fields[field_id] = field
            entity.fields.append(field_id)
        
        # Extract measures (handle nested braces)
        measure_pattern = r'measure:\s*(\w+)\s*\{'
        measure_matches = list(re.finditer(measure_pattern, view_content))
        
        for measure_match in measure_matches:
            measure_name = measure_match.group(1)
            measure_start = measure_match.end()
            
            # Find matching closing brace
            brace_count = 1
            measure_end = measure_start
            while brace_count > 0 and measure_end < len(view_content):
                if view_content[measure_end] == '{':
                    brace_count += 1
                elif view_content[measure_end] == '}':
                    brace_count -= 1
                measure_end += 1
            
            measure_content = view_content[measure_start:measure_end-1] if brace_count == 0 else ""
            
            measure_type_match = re.search(r'type:\s*(\w+)', measure_content)
            measure_type = measure_type_match.group(1) if measure_type_match else "count"
            
            field_id = f"field:{view_name}:{measure_name}"
            field = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=measure_name,
                field_type=FieldType.MEASURE,
                data_type="DECIMAL(10,2)" if measure_type != "count" else "INTEGER",
                nullable=True,
                primary_key=False,
                description=None
            )
            fields[field_id] = field
            entity.fields.append(field_id)
        
        # Update entity with field list
        entities[entity_id] = Entity(
            id=entity_id,
            name=view_name,
            schema_name="public",
            description=None,
            fields=entity.fields,
            grain=grain
        )
    
    # Extract explores and joins (from model file or explore blocks)
    # Handle nested braces properly (explores contain joins with nested braces)
    explore_pattern = r'explore:\s*(\w+)\s*\{'
    explore_matches = list(re.finditer(explore_pattern, content))
    
    for explore_match in explore_matches:
        explore_name = explore_match.group(1)
        start_pos = explore_match.end()
        
        # Find matching closing brace (handle nested braces)
        brace_count = 1
        end_pos = start_pos
        while brace_count > 0 and end_pos < len(content):
            if content[end_pos] == '{':
                brace_count += 1
            elif content[end_pos] == '}':
                brace_count -= 1
            end_pos += 1
        
        explore_content = content[start_pos:end_pos-1] if brace_count == 0 else ""
        
        # Identify the view_name associated with this explore
        # Look for "from:" directive, or use explore_name if it matches a view
        view_name = explore_name  # Default: explore name matches view name
        
        # Check for "from:" directive in explore content
        from_match = re.search(r'from:\s*(\w+)', explore_content)
        if from_match:
            view_name = from_match.group(1)
        else:
            # Check if explore_name matches an existing view/entity
            # If explore_name is in entities, use it; otherwise keep explore_name
            if f"entity:{explore_name}" not in entities:
                # Try to find a matching view name
                # In LookML, explores often reference views, so check if explore_name matches any view
                # For now, we'll use explore_name as-is, but this is the view we should use
                view_name = explore_name
        
        # Extract joins within explore (handle nested braces)
        join_pattern = r'join:\s*(\w+)\s*\{'
        join_matches = list(re.finditer(join_pattern, explore_content))
        
        for join_match in join_matches:
            target_view = join_match.group(1)
            join_start = join_match.end()
            
            # Find matching closing brace
            brace_count = 1
            join_end = join_start
            while brace_count > 0 and join_end < len(explore_content):
                if explore_content[join_end] == '{':
                    brace_count += 1
                elif explore_content[join_end] == '}':
                    brace_count -= 1
                join_end += 1
            
            join_content = explore_content[join_start:join_end-1] if brace_count == 0 else ""
            
            # Extract join type
            join_type_str = "left_outer"
            type_match = re.search(r'type:\s*(\w+)', join_content)
            if type_match:
                join_type_str = type_match.group(1)
            
            # Map LookML join type to JoinType
            join_type = JoinType.LEFT
            if "inner" in join_type_str.lower():
                join_type = JoinType.INNER
            
            # Extract SQL ON clause to infer fields
            sql_on_match = re.search(r'sql_on:\s*\$\{(\w+)\.(\w+)\}\s*=\s*\$\{(\w+)\.(\w+)\}', join_content)
            if sql_on_match:
                source_view_from_sql = sql_on_match.group(1)
                source_field_name = sql_on_match.group(2)
                target_view_from_sql = sql_on_match.group(3)
                target_field_name = sql_on_match.group(4)
                
                # Use view_name (from explore's "from:" or explore_name) as source entity
                # NOT explore_name directly - the source entity should be the view
                source_entity_id = f"entity:{view_name}"
                target_entity_id = f"entity:{target_view_from_sql}"
                
                # Use the view_name for source field, not the SQL-extracted source_view
                source_field_id = f"field:{view_name}:{source_field_name}"
                target_field_id = f"field:{target_view_from_sql}:{target_field_name}"
                
                # Create join even if entities/fields don't exist in this snapshot
                # (They may exist in other snapshots that will be added to the graph)
                # The graph will validate entity existence when adding the snapshot
                join = JoinDef(
                    id=f"join:{view_name}:{target_view_from_sql}",
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    join_type=join_type,
                    source_field_id=source_field_id,
                    target_field_id=target_field_id,
                    description=f"LookML join: {view_name}.{source_field_name} -> {target_view_from_sql}.{target_field_name}"
                )
                joins.append(join)
    
    # Compute snapshot_id
    snapshot_dict = {
        "source_system": "lookml",
        "source_version": "1.0",
        "schema_version": "v0.1",
        "entities": {k: v.model_dump(mode='json') for k, v in entities.items()},
        "fields": {k: v.model_dump(mode='json') for k, v in fields.items()},
        "joins": [j.model_dump(mode='json') for j in joins],
        "metadata": {
            "lookml_file": str(file_path),
            "view_count": len(entities)
        }
    }
    
    snapshot_json = json.dumps(snapshot_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
    
    snapshot_dict["snapshot_id"] = snapshot_id
    
    return SemanticSnapshot(**snapshot_dict)


def detect_source_type(file_path: Optional[Path] = None, source_text: Optional[str] = None) -> str:
    """
    Detect the source type from file path or content.
    
    Args:
        file_path: Path to source file (preferred)
        source_text: Source text content (fallback)
        
    Returns:
        Source type: "dbt", "lookml", "ddl", or "unknown"
    """
    if file_path:
        if file_path.name == "manifest.json" or str(file_path).endswith("manifest.json"):
            return "dbt"
        elif file_path.suffix in [".lkml", ".lookml"]:
            return "lookml"
        elif file_path.suffix == ".sql":
            return "ddl"
        elif file_path.name == "dbt_project.yml":
            return "dbt"
    
    if source_text:
        # Heuristic detection from content
        if '"nodes"' in source_text and '"sources"' in source_text:
            return "dbt"
        elif "view:" in source_text or "explore:" in source_text:
            return "lookml"
        elif "CREATE TABLE" in source_text.upper() or "CREATE VIEW" in source_text.upper():
            return "ddl"
        elif "name:" in source_text and "models:" in source_text:
            return "dbt"  # dbt YAML
    
    return "unknown"
