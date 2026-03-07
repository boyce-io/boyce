"""
Prisma Schema Parser

Parses Prisma Schema Language (.prisma) files into a SemanticSnapshot.
Uses regex-based line-by-line parsing — no Prisma runtime required.

Handles:
- model { ... } blocks
- @@map("table_name") → table name override
- @id → single-field primary key
- @@id([field1, field2]) → composite primary key
- String? → nullable detection
- @relation(fields: [...], references: [...]) → JoinDef creation
- Relation-only fields (Type[], single model refs with @relation) → skipped
- generator / datasource blocks → skipped
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from .base import build_snapshot


# ---------------------------------------------------------------------------
# Prisma scalar type → SQL type mapping
# ---------------------------------------------------------------------------

PRISMA_TYPE_MAP: Dict[str, Tuple[str, FieldType]] = {
    "String": ("VARCHAR", FieldType.DIMENSION),
    "Int": ("INTEGER", FieldType.DIMENSION),
    "BigInt": ("BIGINT", FieldType.DIMENSION),
    "Float": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "Decimal": ("DECIMAL", FieldType.MEASURE),
    "Boolean": ("BOOLEAN", FieldType.DIMENSION),
    "DateTime": ("TIMESTAMP", FieldType.TIMESTAMP),
    "Json": ("JSONB", FieldType.DIMENSION),
    "Bytes": ("BYTEA", FieldType.DIMENSION),
}

# All known Prisma scalars (for distinguishing relation fields from column fields)
_PRISMA_SCALARS = set(PRISMA_TYPE_MAP.keys())

# Regex patterns
_MODEL_START_RE = re.compile(r"^\s*model\s+(\w+)\s*\{")
_MAP_RE = re.compile(r'@@map\("([^"]+)"\)')
_COMPOSITE_ID_RE = re.compile(r"@@id\(\[([^\]]+)\]\)")
_RELATION_RE = re.compile(
    r"@relation\(fields:\s*\[([^\]]*)\]\s*,\s*references:\s*\[([^\]]*)\]\s*(?:,\s*[^)]*)?(?:name:\s*\"[^\"]*\"\s*)?\)"
)
_FIELD_RE = re.compile(r"^\s*(\w+)\s+(\w+)(\?)?\s*(.*)")


def _parse_id_list(raw: str) -> List[str]:
    """Parse 'field1, field2' → ['field1', 'field2']."""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _extract_model_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Extract (model_name, block_content) pairs from the schema text.
    Only extracts `model` blocks (skips generator, datasource, enum, type).
    """
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _MODEL_START_RE.match(lines[i])
        if m:
            model_name = m.group(1)
            depth = 1
            block_lines = []
            i += 1
            while i < len(lines) and depth > 0:
                line = lines[i]
                depth += line.count("{") - line.count("}")
                if depth > 0:
                    block_lines.append(line)
                i += 1
            blocks.append((model_name, "\n".join(block_lines)))
        else:
            i += 1
    return blocks


def parse_prisma_schema(file_path: Path) -> SemanticSnapshot:
    """
    Parse a Prisma schema file into a SemanticSnapshot.
    """
    file_path = Path(file_path)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    model_blocks = _extract_model_blocks(text)

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    # First pass: collect model_name → table_name mappings (needed for FKs)
    model_to_table: Dict[str, str] = {}
    for model_name, block_text in model_blocks:
        mm = _MAP_RE.search(block_text)
        table_name = mm.group(1) if mm else model_name.lower()
        model_to_table[model_name] = table_name

    # Second pass: parse fields
    for model_name, block_text in model_blocks:
        table_name = model_to_table[model_name]
        entity_id = f"entity:{table_name}"

        entity_fields: List[str] = []
        pk_fields: List[str] = []
        join_target_counts: Dict[str, int] = {}

        # Find composite PK directive
        composite_pk_m = _COMPOSITE_ID_RE.search(block_text)
        composite_pk_fields: List[str] = []
        if composite_pk_m:
            composite_pk_fields = _parse_id_list(composite_pk_m.group(1))

        # Find @relation directives with their FK fields
        # Maps: fk_field_name → target_model_name
        fk_field_to_target: Dict[str, str] = {}

        for line in block_text.splitlines():
            # Skip directive-only lines
            stripped = line.strip()
            if not stripped or stripped.startswith("@@") or stripped.startswith("//"):
                continue

            m = _FIELD_RE.match(line)
            if not m:
                continue

            field_name = m.group(1)
            type_name = m.group(2)
            nullable_marker = m.group(3)  # "?" or None
            rest = m.group(4)

            # Skip "id" used as a plain identifier in @@id lines (already handled above)
            if field_name == "@@id":
                continue

            # Check for @relation on this line
            relation_m = _RELATION_RE.search(rest or "")
            if relation_m:
                # This is a relation field: skip as a column
                # But record its FK fields → target model mapping
                fk_fields_raw = _parse_id_list(relation_m.group(1))
                for fk_f in fk_fields_raw:
                    fk_field_to_target[fk_f] = type_name
                continue

            # Skip relation-only fields: type is a known model (not a scalar) + optional []
            type_is_model = type_name.rstrip("?") not in _PRISMA_SCALARS
            type_is_list = rest.strip().startswith("[]") if rest else "[]" in type_name
            if type_is_model and not type_is_list and "@relation" not in (rest or ""):
                # Single model ref without @relation inline — still a relation navigation
                # field if the type is a known model name
                if type_name in model_to_table:
                    continue
            if type_is_model and type_is_list:
                continue

            # Normalize type (strip trailing [])
            clean_type = type_name.rstrip("?").replace("[]", "")

            # Nullability
            nullable = nullable_marker == "?"

            # PK detection
            is_pk = "@id" in (rest or "") or field_name in composite_pk_fields

            # Field type
            if clean_type in PRISMA_TYPE_MAP:
                sql_type, field_type = PRISMA_TYPE_MAP[clean_type]
            else:
                sql_type, field_type = "VARCHAR", FieldType.DIMENSION

            # Override field_type for PK
            if is_pk:
                field_type = FieldType.ID

            # Override field_type for FK columns
            if field_name in fk_field_to_target:
                field_type = FieldType.FOREIGN_KEY

            if is_pk:
                pk_fields.append(field_name)

            field_id = f"field:{table_name}:{field_name}"
            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=field_name,
                field_type=field_type,
                data_type=sql_type,
                nullable=nullable,
                primary_key=is_pk,
            )
            entity_fields.append(field_id)

        # Build JoinDefs from FK field → target model mappings
        for fk_field_name, target_model_name in fk_field_to_target.items():
            target_table = model_to_table.get(target_model_name, target_model_name.lower())
            target_entity_id = f"entity:{target_table}"
            join_target_counts[target_table] = join_target_counts.get(target_table, 0) + 1
            count = join_target_counts[target_table]
            join_id = (
                f"join:{table_name}:{target_table}"
                if count == 1
                else f"join:{table_name}:{target_table}:{fk_field_name}"
            )
            source_field_id = f"field:{table_name}:{fk_field_name}"
            joins.append(JoinDef(
                id=join_id,
                source_entity_id=entity_id,
                target_entity_id=target_entity_id,
                join_type=JoinType.LEFT,
                source_field_id=source_field_id,
                target_field_id=f"field:{target_table}:id",
                description=f"Prisma @relation: {table_name}.{fk_field_name} -> {target_table}",
            ))

        # Grain
        if len(pk_fields) == 1:
            grain = pk_fields[0]
        elif len(pk_fields) > 1:
            grain = "_".join(pk_fields)
        else:
            grain = "id"

        entities[entity_id] = Entity(
            id=entity_id,
            name=table_name,
            schema_name="public",
            fields=entity_fields,
            grain=grain,
        )

    return build_snapshot(
        source_system="prisma",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "source_file": str(file_path),
            "table_count": len(entities),
        },
    )


class PrismaParser:
    """SnapshotParser implementation for Prisma schema files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.suffix == ".prisma" or path.name == "schema.prisma":
            return 0.95
        # Check content for Prisma keywords
        if path.suffix in (".txt", ""):
            try:
                with open(path) as f:
                    content = f.read(2000)
                if "datasource" in content and "model " in content:
                    return 0.6
            except Exception:
                pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_prisma_schema(Path(path))

    def source_type(self) -> str:
        return "prisma"
