"""
LookML Ingestion Parser

Parses .lkml files and extracts SemanticSnapshot structures.
Views → Entity, dimensions/measures → FieldDef, explore joins → JoinDef.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from .base import build_snapshot as _build_snapshot


def parse_lookml_file(file_path: Path) -> SemanticSnapshot:
    """
    Parse a LookML .lkml file and return a SemanticSnapshot.

    Args:
        file_path: Path to a .lkml or .lookml file.

    Returns:
        SemanticSnapshot with entities (views), fields (dimensions/measures),
        and joins (explore join blocks).
    """
    with open(file_path, "r") as f:
        content = f.read()

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    # --- Views → Entities ---
    for view_match in re.finditer(r"view:\s*(\w+)\s*\{", content):
        view_name = view_match.group(1)
        view_content = _extract_block(content, view_match.end())

        entity_id = f"entity:{view_name}"
        entity_fields: List[str] = []

        # Grain from primary_key dimension
        pk_dims = re.findall(r"dimension:\s*(\w+)\s*\{[^}]*primary_key:\s*yes", view_content)
        if pk_dims:
            grain = pk_dims[0]
        else:
            id_dims = re.findall(r"dimension:\s*(\w+_id)\s*\{", view_content)
            grain = id_dims[0] if id_dims else "<unknown_grain>"

        # Dimensions
        for dim_match in re.finditer(r"dimension(?:_group)?:\s*(\w+)\s*\{", view_content):
            dim_name = dim_match.group(1)
            dim_content = _extract_block(view_content, dim_match.end())

            is_pk = "primary_key: yes" in dim_content
            type_m = re.search(r"type:\s*(\w+)", dim_content)
            dim_type = type_m.group(1) if type_m else "string"

            sql_type = "VARCHAR(255)"
            if dim_type == "number":
                sql_type = "DECIMAL(10,2)"
            elif dim_type in ("time", "date"):
                sql_type = "TIMESTAMP"

            if is_pk:
                field_type = FieldType.ID
            elif dim_type in ("time", "date"):
                field_type = FieldType.TIMESTAMP
            elif dim_name.endswith("_id"):
                field_type = FieldType.FOREIGN_KEY
            else:
                field_type = FieldType.DIMENSION

            field_id = f"field:{view_name}:{dim_name}"
            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=dim_name,
                field_type=field_type,
                data_type=sql_type,
                nullable=True,
                primary_key=is_pk,
            )
            entity_fields.append(field_id)

        # Measures
        for meas_match in re.finditer(r"measure:\s*(\w+)\s*\{", view_content):
            meas_name = meas_match.group(1)
            meas_content = _extract_block(view_content, meas_match.end())
            type_m = re.search(r"type:\s*(\w+)", meas_content)
            meas_type = type_m.group(1) if type_m else "count"

            field_id = f"field:{view_name}:{meas_name}"
            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=meas_name,
                field_type=FieldType.MEASURE,
                data_type="INTEGER" if meas_type == "count" else "DECIMAL(10,2)",
                nullable=True,
                primary_key=False,
            )
            entity_fields.append(field_id)

        entities[entity_id] = Entity(
            id=entity_id,
            name=view_name,
            schema_name="public",
            fields=entity_fields,
            grain=grain,
        )

    # --- Explores → Joins ---
    for exp_match in re.finditer(r"explore:\s*(\w+)\s*\{", content):
        explore_name = exp_match.group(1)
        explore_content = _extract_block(content, exp_match.end())

        # Explore's base view (from: directive or explore name)
        from_m = re.search(r"from:\s*(\w+)", explore_content)
        base_view = from_m.group(1) if from_m else explore_name

        for join_match in re.finditer(r"join:\s*(\w+)\s*\{", explore_content):
            target_view = join_match.group(1)
            join_content = _extract_block(explore_content, join_match.end())

            type_m = re.search(r"type:\s*(\w+)", join_content)
            join_type_str = type_m.group(1) if type_m else "left_outer"
            join_type = JoinType.INNER if "inner" in join_type_str.lower() else JoinType.LEFT

            sql_on_m = re.search(
                r"sql_on:\s*\$\{(\w+)\.(\w+)\}\s*=\s*\$\{(\w+)\.(\w+)\}",
                join_content,
            )
            if sql_on_m:
                src_view, src_field, tgt_view, tgt_field = sql_on_m.groups()
                joins.append(JoinDef(
                    id=f"join:{base_view}:{tgt_view}",
                    source_entity_id=f"entity:{base_view}",
                    target_entity_id=f"entity:{tgt_view}",
                    join_type=join_type,
                    source_field_id=f"field:{base_view}:{src_field}",
                    target_field_id=f"field:{tgt_view}:{tgt_field}",
                    description=f"LookML join: {base_view}.{src_field} -> {tgt_view}.{tgt_field}",
                ))

    return _build_snapshot(
        source_system="lookml",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={"lookml_file": str(file_path), "view_count": len(entities)},
    )


class LookMLParser:
    """SnapshotParser implementation for LookML files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix in (".lkml", ".lookml"):
            return 0.95
        if path.suffix == ".txt" or path.suffix == "":
            try:
                with open(path) as f:
                    content = f.read(500)
                if "view:" in content or "explore:" in content:
                    return 0.6
            except Exception:
                pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_lookml_file(Path(path))

    def source_type(self) -> str:
        return "lookml"


def _extract_block(content: str, start: int) -> str:
    """Extract the content of a {} block starting at `start` (after the opening brace)."""
    depth = 1
    pos = start
    while depth > 0 and pos < len(content):
        if content[pos] == "{":
            depth += 1
        elif content[pos] == "}":
            depth -= 1
        pos += 1
    return content[start : pos - 1] if depth == 0 else ""
