"""
dbt Ingestion Parsers

Two ingestion paths for dbt projects:
  - parse_dbt_manifest: Gold Standard — reads compiled manifest.json
  - parse_dbt_project_source: Silver Standard — reads raw YAML without dbt compile

Both return a SemanticSnapshot ready for ingest_source.
"""

from __future__ import annotations

import json
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from .base import build_snapshot

_build_snapshot = build_snapshot


def parse_dbt_manifest(manifest_path: Path) -> SemanticSnapshot:
    """
    Parse a dbt manifest.json and return a SemanticSnapshot.

    Reads nodes + sources, maps models/sources → Entity, columns → FieldDef,
    and relationship tests → JoinDef.

    Args:
        manifest_path: Path to dbt manifest.json (typically target/manifest.json)

    Returns:
        SemanticSnapshot with entities, fields, and joins.
    """
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    nodes = manifest_data.get("nodes", {})
    sources = manifest_data.get("sources", {})
    all_nodes = {**nodes, **sources}

    for node_id, node_data in all_nodes.items():
        resource_type = node_data.get("resource_type")
        if resource_type not in ("model", "source"):
            continue

        model_name = node_data.get("name", "")
        schema_name = node_data.get("schema", "public")
        description = node_data.get("description", "")
        columns = node_data.get("columns", {})

        # Infer grain from primary key meta or _id suffix
        grain: Optional[str] = None
        primary_keys: List[str] = []
        for col_name, col_data in columns.items():
            meta = col_data.get("meta", {})
            if meta.get("primary_key") or col_name.endswith("_id"):
                primary_keys.append(col_name)

        if primary_keys:
            grain = "_".join(primary_keys) if len(primary_keys) > 1 else primary_keys[0]
        else:
            for col_name in columns:
                if col_name.endswith("_id"):
                    grain = col_name
                    break
            if not grain:
                grain = "<unknown_grain>"

        entity_id = f"entity:{model_name}"
        entity_fields: List[str] = []

        for col_name, col_data in columns.items():
            field_id = f"field:{model_name}:{col_name}"
            col_type = col_data.get("data_type", "VARCHAR") or "VARCHAR"
            meta = col_data.get("meta", {})

            field_type = FieldType.DIMENSION
            if meta.get("primary_key"):
                field_type = FieldType.ID
            elif col_name in ("created_at", "updated_at", "timestamp", "date"):
                field_type = FieldType.TIMESTAMP
            elif any(kw in col_name.lower() for kw in ("amount", "revenue", "count", "sum", "total")):
                field_type = FieldType.MEASURE
            elif col_name.endswith("_id") and not meta.get("primary_key"):
                field_type = FieldType.FOREIGN_KEY

            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=col_name,
                field_type=field_type,
                data_type=col_type.upper(),
                nullable=True,
                primary_key=bool(meta.get("primary_key", False)),
                description=col_data.get("description", "") or None,
            )
            entity_fields.append(field_id)

        entities[entity_id] = Entity(
            id=entity_id,
            name=model_name,
            schema_name=schema_name,
            description=description or None,
            fields=entity_fields,
            grain=grain,
        )

    # Extract joins from relationship tests on model nodes
    for node_id, node_data in nodes.items():
        if node_data.get("resource_type") != "model":
            continue

        source_model = node_data.get("name", "")
        source_entity_id = f"entity:{source_model}"
        if source_entity_id not in entities:
            continue

        for test in node_data.get("tests", []):
            kwargs = test.get("test_metadata", {}).get("kwargs", {})
            if test.get("test_metadata", {}).get("name") != "relationships":
                continue

            to_model = kwargs.get("to")
            from_field = kwargs.get("from")
            to_field = kwargs.get("field")

            if not (to_model and from_field and to_field):
                continue

            target_entity_id = f"entity:{to_model}"
            if target_entity_id not in entities:
                continue

            source_field_id = f"field:{source_model}:{from_field}"
            target_field_id = f"field:{to_model}:{to_field}"

            if source_field_id in fields and target_field_id in fields:
                joins.append(JoinDef(
                    id=f"join:{source_model}:{to_model}",
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    join_type=JoinType.LEFT,
                    source_field_id=source_field_id,
                    target_field_id=target_field_id,
                    description=f"dbt relationship: {source_model}.{from_field} -> {to_model}.{to_field}",
                ))

    return _build_snapshot(
        source_system="dbt",
        source_version=manifest_data.get("metadata", {}).get("dbt_schema_version", "1.0"),
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "manifest_path": str(manifest_path),
            "dbt_version": manifest_data.get("metadata", {}).get("dbt_version", "unknown"),
            "source_type": "manifest",
        },
    )


def parse_dbt_project_source(project_root: Path) -> SemanticSnapshot:
    """
    Parse raw dbt YAML source files without requiring dbt compile.

    Reads models/ directory recursively, extracts models + columns from YAML,
    and resolves relationship tests into JoinDefs.

    Args:
        project_root: Path to dbt project root (must contain dbt_project.yml)

    Returns:
        SemanticSnapshot from raw YAML (Silver Standard — no column data types).
    """
    dbt_project_file = project_root / "dbt_project.yml"
    if not dbt_project_file.exists():
        raise ValueError(f"Not a dbt project: dbt_project.yml not found in {project_root}")

    with open(dbt_project_file, "r") as f:
        dbt_project_data = yaml.safe_load(f)

    project_name = dbt_project_data.get("name", "dbt_project")
    models_path = project_root / "models"
    if not models_path.exists():
        raise ValueError(f"models/ directory not found in {project_root}")

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    for yml_file in models_path.rglob("*.yml"):
        try:
            with open(yml_file, "r") as f:
                yml_data = yaml.safe_load(f)

            if not yml_data or "models" not in yml_data:
                continue

            for model_def in yml_data.get("models", []):
                if not isinstance(model_def, dict):
                    continue

                model_name = model_def.get("name")
                if not model_name:
                    continue

                columns = model_def.get("columns", [])
                entity_id = f"entity:{model_name}"
                entity_fields: List[str] = []

                # Determine grain
                grain: Optional[str] = None
                primary_keys: List[str] = []
                for col_def in columns:
                    if not isinstance(col_def, dict):
                        continue
                    col_name = col_def.get("name", "")
                    for test in col_def.get("tests", []):
                        if (isinstance(test, str) and "primary_key" in test.lower()) or \
                           (isinstance(test, dict) and "primary_key" in str(test).lower()):
                            primary_keys.append(col_name)

                if primary_keys:
                    grain = "_".join(primary_keys) if len(primary_keys) > 1 else primary_keys[0]
                else:
                    for col_def in columns:
                        if isinstance(col_def, dict):
                            col_name = col_def.get("name", "")
                            if col_name.endswith("_id"):
                                grain = col_name
                                break
                    if not grain:
                        grain = "<unknown_grain>"

                for col_def in columns:
                    if not isinstance(col_def, dict):
                        continue
                    col_name = col_def.get("name", "")
                    if not col_name:
                        continue

                    field_id = f"field:{model_name}:{col_name}"
                    tests = col_def.get("tests", [])

                    field_type = FieldType.DIMENSION
                    is_primary_key = False
                    for test in tests:
                        if (isinstance(test, str) and "primary_key" in test.lower()) or \
                           (isinstance(test, dict) and "primary_key" in str(test).lower()):
                            field_type = FieldType.ID
                            is_primary_key = True

                    if not is_primary_key:
                        if col_name.endswith("_id"):
                            field_type = FieldType.ID if col_name == grain else FieldType.FOREIGN_KEY
                        elif col_name in ("created_at", "updated_at", "timestamp", "date", "received_at"):
                            field_type = FieldType.TIMESTAMP
                        elif any(kw in col_name.lower() for kw in ("amount", "revenue", "count", "sum", "total")):
                            field_type = FieldType.MEASURE

                    fields[field_id] = FieldDef(
                        id=field_id,
                        entity_id=entity_id,
                        name=col_name,
                        field_type=field_type,
                        data_type="VARCHAR(255)",
                        nullable=True,
                        primary_key=is_primary_key,
                        description=col_def.get("description") or None,
                    )
                    entity_fields.append(field_id)

                    # Extract relationship joins from column tests
                    for test in tests:
                        if not isinstance(test, dict) or "relationships" not in test:
                            continue
                        rel_test = test["relationships"]
                        if not isinstance(rel_test, dict):
                            continue
                        to_model_raw = rel_test.get("to")
                        to_field = rel_test.get("field")
                        if not (to_model_raw and to_field):
                            continue

                        # Handle ref('model_name') syntax
                        m = re.search(r"ref\(['\"]?(\w+)['\"]?\)|(\w+)", str(to_model_raw))
                        to_model = (m.group(1) or m.group(2)) if m else None
                        if not to_model:
                            continue

                        target_entity_id = f"entity:{to_model}"
                        joins.append(JoinDef(
                            id=f"join:{model_name}:{to_model}",
                            source_entity_id=entity_id,
                            target_entity_id=target_entity_id,
                            join_type=JoinType.LEFT,
                            source_field_id=field_id,
                            target_field_id=f"field:{to_model}:{to_field}",
                            description=f"dbt relationship (YAML): {model_name}.{col_name} -> {to_model}.{to_field}",
                        ))

                entities[entity_id] = Entity(
                    id=entity_id,
                    name=model_name,
                    schema_name="public",
                    description=model_def.get("description") or None,
                    fields=entity_fields,
                    grain=grain,
                )

        except Exception as e:
            print(f"Warning: Failed to parse {yml_file}: {e}")
            continue

    return _build_snapshot(
        source_system="dbt",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "project_root": str(project_root),
            "project_name": project_name,
            "source_type": "source_yaml",
        },
    )


class DbtManifestParser:
    """SnapshotParser implementation for dbt manifest.json files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.name == "manifest.json":
            return 0.9
        if path.suffix == ".json":
            try:
                with open(path) as f:
                    data = json.load(f)
                if "nodes" in data and "sources" in data:
                    return 0.8
            except Exception:
                pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_dbt_manifest(Path(path))

    def source_type(self) -> str:
        return "dbt_manifest"


class DbtProjectParser:
    """SnapshotParser implementation for dbt project directories."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.name == "dbt_project.yml":
            return 0.95
        if path.is_dir() and (path / "dbt_project.yml").exists():
            return 0.95
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        path = Path(path)
        return parse_dbt_project_source(path if path.is_dir() else path.parent)

    def source_type(self) -> str:
        return "dbt_project"
