"""
Django Models Parser

Parses Django models.py files into a SemanticSnapshot using Python AST.
No Django import required — pure static analysis.

Handles:
- Concrete and abstract models
- Inheritance from abstract models (field merging)
- ForeignKey / OneToOneField → JoinDef + _id suffix column
- ManyToManyField → skipped (intermediate table, not a column)
- db_table Meta override
- Implicit id AutoField when no explicit PK declared
- null=True keyword for nullable detection
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
# Django field → SQL type mapping
# ---------------------------------------------------------------------------

DJANGO_TYPE_MAP: Dict[str, Tuple[str, FieldType]] = {
    "AutoField": ("INTEGER", FieldType.ID),
    "BigAutoField": ("BIGINT", FieldType.ID),
    "SmallAutoField": ("SMALLINT", FieldType.ID),
    "CharField": ("VARCHAR", FieldType.DIMENSION),
    "TextField": ("TEXT", FieldType.DIMENSION),
    "EmailField": ("VARCHAR", FieldType.DIMENSION),
    "SlugField": ("VARCHAR", FieldType.DIMENSION),
    "URLField": ("VARCHAR", FieldType.DIMENSION),
    "UUIDField": ("UUID", FieldType.DIMENSION),
    "IntegerField": ("INTEGER", FieldType.DIMENSION),
    "BigIntegerField": ("BIGINT", FieldType.DIMENSION),
    "SmallIntegerField": ("SMALLINT", FieldType.DIMENSION),
    "PositiveIntegerField": ("INTEGER", FieldType.DIMENSION),
    "PositiveBigIntegerField": ("BIGINT", FieldType.DIMENSION),
    "PositiveSmallIntegerField": ("SMALLINT", FieldType.DIMENSION),
    "FloatField": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "DecimalField": ("DECIMAL", FieldType.MEASURE),
    "BooleanField": ("BOOLEAN", FieldType.DIMENSION),
    "NullBooleanField": ("BOOLEAN", FieldType.DIMENSION),
    "DateField": ("DATE", FieldType.TIMESTAMP),
    "DateTimeField": ("TIMESTAMP", FieldType.TIMESTAMP),
    "TimeField": ("TIME", FieldType.TIMESTAMP),
    "DurationField": ("INTERVAL", FieldType.DIMENSION),
    "BinaryField": ("BYTEA", FieldType.DIMENSION),
    "FileField": ("VARCHAR", FieldType.DIMENSION),
    "ImageField": ("VARCHAR", FieldType.DIMENSION),
    "JSONField": ("JSONB", FieldType.DIMENSION),
    "ForeignKey": ("INTEGER", FieldType.FOREIGN_KEY),
    "OneToOneField": ("INTEGER", FieldType.FOREIGN_KEY),
    # ManyToManyField is intentionally absent — handled separately (skip)
}

_RELATION_FIELDS = {"ForeignKey", "OneToOneField", "ManyToManyField"}
_SKIP_FIELDS = {"ManyToManyField"}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _get_call_func_name(node: ast.Call) -> str:
    """Extract the function/method name from a Call node."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _get_kwarg_bool(node: ast.Call, key: str) -> Optional[bool]:
    """Return True/False if keyword `key` is a bool constant in `node.keywords`."""
    for kw in node.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant):
            return bool(kw.value.value)
    return None


def _get_first_arg_name(node: ast.Call) -> Optional[str]:
    """Return the string or Name of the first positional arg (FK target)."""
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    return None


# ---------------------------------------------------------------------------
# Per-class field extraction
# ---------------------------------------------------------------------------

def _extract_class_fields(
    class_node: ast.ClassDef,
) -> Tuple[List[dict], bool, Optional[str], bool]:
    """
    Returns (raw_fields, is_abstract, db_table, has_explicit_pk).

    raw_fields is a list of dicts:
      {name, field_type_name, sql_type, field_type, nullable, is_fk, fk_target}
    """
    is_abstract = False
    db_table: Optional[str] = None
    raw_fields: List[dict] = []
    has_explicit_pk = False

    for node in ast.walk(class_node):
        # Detect abstract Meta and db_table
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "abstract" and isinstance(stmt.value, ast.Constant):
                                if stmt.value.value is True:
                                    is_abstract = True
                            if target.id == "db_table" and isinstance(stmt.value, ast.Constant):
                                db_table = str(stmt.value.value)
            continue

    for stmt in class_node.body:
        # Only direct assignments (not nested class statements)
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue

        # Get target name
        if isinstance(stmt, ast.Assign):
            if not stmt.targets or not isinstance(stmt.targets[0], ast.Name):
                continue
            field_name = stmt.targets[0].id
            value = stmt.value
        else:
            if not isinstance(stmt.target, ast.Name):
                continue
            field_name = stmt.target.id
            value = stmt.value

        if value is None or not isinstance(value, ast.Call):
            continue

        field_type_name = _get_call_func_name(value)
        # Accept both *Field names and relation descriptors (ForeignKey, OneToOneField, ManyToManyField)
        if not (field_type_name.endswith("Field") or field_type_name in _RELATION_FIELDS):
            continue

        # Skip ManyToManyField
        if field_type_name in _SKIP_FIELDS:
            continue

        # Nullable detection
        nullable = _get_kwarg_bool(value, "null") or False

        # primary_key detection
        is_pk = bool(_get_kwarg_bool(value, "primary_key"))

        # FK target
        fk_target: Optional[str] = None
        is_fk = field_type_name in _RELATION_FIELDS

        if is_fk:
            fk_target = _get_first_arg_name(value)
            # Strip quotes and module prefix (e.g. "Customer" or Customer)
            if fk_target and "." in fk_target:
                fk_target = fk_target.split(".")[-1]
            actual_field_name = field_name + "_id"
        else:
            actual_field_name = field_name

        sql_type, ft = DJANGO_TYPE_MAP.get(field_type_name, ("VARCHAR", FieldType.DIMENSION))

        # If explicit pk, override field type
        if is_pk:
            ft = FieldType.ID
            has_explicit_pk = True
        elif field_type_name in ("AutoField", "BigAutoField", "SmallAutoField"):
            has_explicit_pk = True

        raw_fields.append({
            "name": actual_field_name,
            "field_type_name": field_type_name,
            "sql_type": sql_type,
            "field_type": ft,
            "nullable": nullable,
            "is_fk": is_fk,
            "fk_target": fk_target,
            "is_pk": is_pk or field_type_name in ("AutoField", "BigAutoField", "SmallAutoField"),
        })

    return raw_fields, is_abstract, db_table, has_explicit_pk


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_django_models(file_path: Path) -> SemanticSnapshot:
    """
    Parse a Django models.py file into a SemanticSnapshot using AST.

    No Django import required — pure AST analysis.
    """
    file_path = Path(file_path)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    tree = ast.parse(source)

    # First pass: collect abstract models and their fields for inheritance.
    # Also collect all class names that look like abstract mixins (abstract = True in Meta).
    abstract_fields: Dict[str, List[dict]] = {}  # class_name → raw_fields
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        raw_fields, is_abstract, _, _ = _extract_class_fields(node)
        if is_abstract:
            abstract_fields[node.name] = raw_fields
        # Also track classes that inherit from known abstract models (to resolve inheritance chain)
        # N.B.: We only need to track the abstract flag here; inheritance is resolved in second pass.

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    # Second pass: build concrete models
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        raw_fields, is_abstract, db_table, has_explicit_pk = _extract_class_fields(node)
        if is_abstract:
            continue

        # Determine if this is a Django model at all (has at least one *Field/relation or inherits)
        has_field = any(
            f["field_type_name"].endswith("Field") or f["field_type_name"] in _RELATION_FIELDS
            for f in raw_fields
        )
        inherits_model = any(
            (isinstance(b, ast.Attribute) and "Model" in b.attr) or
            (isinstance(b, ast.Name) and ("Model" in b.id or b.id in abstract_fields))
            for b in node.bases
        )
        if not has_field and not inherits_model:
            continue

        class_name = node.name
        table_name = db_table or class_name.lower()
        entity_id = f"entity:{table_name}"

        # Merge in fields from abstract base classes
        inherited: List[dict] = []
        for base in node.bases:
            base_name = None
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name and base_name in abstract_fields:
                inherited.extend(abstract_fields[base_name])

        all_raw = raw_fields + inherited

        # Add implicit id if no explicit pk
        if not has_explicit_pk and not any(f["is_pk"] for f in all_raw):
            all_raw.insert(0, {
                "name": "id",
                "field_type_name": "AutoField",
                "sql_type": "INTEGER",
                "field_type": FieldType.ID,
                "nullable": False,
                "is_fk": False,
                "fk_target": None,
                "is_pk": True,
            })

        entity_fields: List[str] = []
        grain: Optional[str] = None
        join_target_counts: Dict[str, int] = {}

        for fdef in all_raw:
            fname = fdef["name"]
            field_id = f"field:{table_name}:{fname}"

            if fdef["is_pk"] and grain is None:
                grain = fname

            fields[field_id] = FieldDef(
                id=field_id,
                entity_id=entity_id,
                name=fname,
                field_type=fdef["field_type"],
                data_type=fdef["sql_type"],
                nullable=fdef["nullable"],
                primary_key=fdef["is_pk"],
            )
            entity_fields.append(field_id)

            # Build JoinDef for FK fields
            if fdef["is_fk"] and fdef["fk_target"]:
                raw_target = fdef["fk_target"]
                # Convert class name → table name heuristic (lowercase)
                # We'll use lowercase for now; may be overridden if we see db_table in later pass
                target_table = raw_target.lower()
                target_entity_id = f"entity:{target_table}"
                join_target_counts[target_table] = join_target_counts.get(target_table, 0) + 1
                count = join_target_counts[target_table]
                join_id = (
                    f"join:{table_name}:{target_table}"
                    if count == 1
                    else f"join:{table_name}:{target_table}:{fname}"
                )
                joins.append(JoinDef(
                    id=join_id,
                    source_entity_id=entity_id,
                    target_entity_id=target_entity_id,
                    join_type=JoinType.LEFT,
                    source_field_id=field_id,
                    target_field_id=f"field:{target_table}:id",
                    description=f"Django FK: {table_name}.{fname} -> {target_table}.id",
                ))

        entities[entity_id] = Entity(
            id=entity_id,
            name=table_name,
            schema_name="public",
            fields=entity_fields,
            grain=grain or "id",
        )

    return build_snapshot(
        source_system="django",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "source_file": str(file_path),
            "table_count": len(entities),
        },
    )


class DjangoParser:
    """SnapshotParser implementation for Django models.py files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        if path.name == "models.py":
            try:
                with open(path) as f:
                    content = f.read(2000)
                if "from django" in content or "import django" in content or "models.Model" in content:
                    return 0.9
                if "models.CharField" in content or "models.ForeignKey" in content:
                    return 0.7
            except Exception:
                pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_django_models(Path(path))

    def source_type(self) -> str:
        return "django"
