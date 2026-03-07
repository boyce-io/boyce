"""
SQLAlchemy Models Parser

Parses SQLAlchemy models.py files into a SemanticSnapshot using Python AST.
No SQLAlchemy import required — pure static analysis.

Supports:
- Classic style (1.x): name = Column(String(100), ...)
- Mapped style (2.0): name: Mapped[str] = mapped_column(String(100), ...)
- ForeignKey("table.column") detection → JoinDef
- Composite primary keys
- relationship() assignments are skipped (ORM navigation, not schema columns)
- Base / DeclarativeBase subclasses are skipped (not models)
"""
from __future__ import annotations

import ast
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
# SQLAlchemy type → SQL type mapping
# ---------------------------------------------------------------------------

SQLALCHEMY_TYPE_MAP: Dict[str, Tuple[str, FieldType]] = {
    "Integer": ("INTEGER", FieldType.DIMENSION),
    "BigInteger": ("BIGINT", FieldType.DIMENSION),
    "SmallInteger": ("SMALLINT", FieldType.DIMENSION),
    "String": ("VARCHAR", FieldType.DIMENSION),
    "Text": ("TEXT", FieldType.DIMENSION),
    "Boolean": ("BOOLEAN", FieldType.DIMENSION),
    "DateTime": ("TIMESTAMP", FieldType.TIMESTAMP),
    "Date": ("DATE", FieldType.TIMESTAMP),
    "Time": ("TIME", FieldType.TIMESTAMP),
    "Numeric": ("DECIMAL", FieldType.MEASURE),
    "Float": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "LargeBinary": ("BYTEA", FieldType.DIMENSION),
    "JSON": ("JSONB", FieldType.DIMENSION),
    "Uuid": ("UUID", FieldType.DIMENSION),
    "UUID": ("UUID", FieldType.DIMENSION),
}

# Mapped[X] annotation → SQL type (fallback when no explicit type arg)
_MAPPED_PYTHON_TYPE_MAP: Dict[str, Tuple[str, FieldType]] = {
    "int": ("INTEGER", FieldType.DIMENSION),
    "str": ("VARCHAR", FieldType.DIMENSION),
    "bool": ("BOOLEAN", FieldType.DIMENSION),
    "float": ("DOUBLE PRECISION", FieldType.DIMENSION),
    "datetime": ("TIMESTAMP", FieldType.TIMESTAMP),
    "date": ("DATE", FieldType.TIMESTAMP),
    "Decimal": ("DECIMAL", FieldType.MEASURE),
    "bytes": ("BYTEA", FieldType.DIMENSION),
}

_SKIP_FUNCS = {"relationship", "backref"}
# Actual SQLAlchemy framework base class names (not user-defined names like "Base").
# User code typically does: class Base(DeclarativeBase): pass
# We detect THAT "Base" class dynamically in the first pass.
_SQLALCHEMY_FRAMEWORK_BASES = {"DeclarativeBase", "DeclarativeMeta", "AbstractConcreteBase"}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _get_call_func_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _get_first_type_name(node: ast.Call) -> Optional[str]:
    """Extract the SQLAlchemy type name from the first positional arg of Column/mapped_column."""
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    if isinstance(arg, ast.Call):
        # e.g. String(100), Numeric(10, 2)
        if isinstance(arg.func, ast.Name):
            return arg.func.id
        if isinstance(arg.func, ast.Attribute):
            return arg.func.attr
    return None


def _extract_fk_target(node: ast.Call) -> Optional[str]:
    """
    Look for ForeignKey("table.column") in positional or keyword args.
    Returns the target table name (before the dot).
    """
    for arg in node.args:
        if isinstance(arg, ast.Call) and _get_call_func_name(arg) == "ForeignKey":
            if arg.args and isinstance(arg.args[0], ast.Constant):
                ref = str(arg.args[0].value)
                return ref.split(".")[0]
    for kw in node.keywords:
        if isinstance(kw.value, ast.Call) and _get_call_func_name(kw.value) == "ForeignKey":
            if kw.value.args and isinstance(kw.value.args[0], ast.Constant):
                ref = str(kw.value.args[0].value)
                return ref.split(".")[0]
    return None


def _get_kwarg_bool(node: ast.Call, key: str) -> Optional[bool]:
    for kw in node.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant):
            return bool(kw.value.value)
    return None


def _get_mapped_inner_type(annotation: ast.expr) -> Optional[str]:
    """
    Extract the inner type name from Mapped[X] or Mapped[X | None].
    Returns "int", "str", "datetime", etc.
    """
    if not isinstance(annotation, ast.Subscript):
        return None
    # Mapped[X]
    slice_node = annotation.slice
    # Handle Mapped[X | None]  (BinOp in Python 3.10+)
    if isinstance(slice_node, ast.BinOp):
        # e.g. str | None — take the left side
        left = slice_node.left
        if isinstance(left, ast.Name):
            return left.id
        if isinstance(left, ast.Attribute):
            return left.attr
    if isinstance(slice_node, ast.Name):
        return slice_node.id
    if isinstance(slice_node, ast.Attribute):
        return slice_node.attr
    return None


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_sqlalchemy_models(file_path: Path) -> SemanticSnapshot:
    """
    Parse a SQLAlchemy models.py file into a SemanticSnapshot using AST.

    No SQLAlchemy import required — pure AST analysis.
    """
    file_path = Path(file_path)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    tree = ast.parse(source)

    # First pass: find user-defined declarative base classes.
    # These are classes that directly inherit from SQLAlchemy framework base names.
    # They should be skipped as entities; their names are used to detect model classes.
    declarative_bases: set = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            base_name = None
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name in _SQLALCHEMY_FRAMEWORK_BASES:
                declarative_bases.add(node.name)
                break

    entities: Dict[str, Entity] = {}
    fields: Dict[str, FieldDef] = {}
    joins: List[JoinDef] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        # Skip declarative base classes (e.g. class Base(DeclarativeBase): pass)
        if node.name in declarative_bases:
            continue

        # Must inherit from a user-defined declarative base class
        inherits_base = any(
            (isinstance(b, ast.Name) and b.id in declarative_bases) or
            (isinstance(b, ast.Attribute) and b.attr in declarative_bases)
            for b in node.bases
        )
        if not inherits_base:
            continue

        # Extract __tablename__
        table_name: Optional[str] = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "__tablename__":
                        if isinstance(stmt.value, ast.Constant):
                            table_name = str(stmt.value.value)

        if table_name is None:
            table_name = node.name.lower()

        entity_id = f"entity:{table_name}"
        entity_fields: List[str] = []
        grain_parts: List[str] = []
        join_target_counts: Dict[str, int] = {}

        for stmt in node.body:
            if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                continue

            # Target name
            if isinstance(stmt, ast.Assign):
                if not stmt.targets or not isinstance(stmt.targets[0], ast.Name):
                    continue
                field_name = stmt.targets[0].id
                value = stmt.value
                annotation = None
            else:
                if not isinstance(stmt.target, ast.Name):
                    continue
                field_name = stmt.target.id
                value = stmt.value
                annotation = stmt.annotation

            if value is None or not isinstance(value, ast.Call):
                continue

            func_name = _get_call_func_name(value)

            # Skip relationship() and similar ORM navigation
            if func_name in _SKIP_FUNCS:
                continue

            # Skip __tablename__ = ... (not an ast.Call, already handled above)
            if field_name == "__tablename__":
                continue

            # Only process Column() and mapped_column()
            if func_name not in ("Column", "mapped_column"):
                continue

            # Determine nullable
            nullable_kwarg = _get_kwarg_bool(value, "nullable")
            is_pk = bool(_get_kwarg_bool(value, "primary_key"))

            # Determine FK target
            fk_target = _extract_fk_target(value)

            # If FK, field_type is FOREIGN_KEY
            if fk_target:
                sql_type = "INTEGER"
                field_type = FieldType.FOREIGN_KEY
            else:
                # Try to get type from first positional arg
                type_name = _get_first_type_name(value)
                if type_name and type_name in SQLALCHEMY_TYPE_MAP:
                    sql_type, field_type = SQLALCHEMY_TYPE_MAP[type_name]
                elif annotation is not None:
                    # Mapped[X] fallback
                    inner = _get_mapped_inner_type(annotation)
                    if inner and inner in _MAPPED_PYTHON_TYPE_MAP:
                        sql_type, field_type = _MAPPED_PYTHON_TYPE_MAP[inner]
                    elif inner == "datetime":
                        sql_type, field_type = "TIMESTAMP", FieldType.TIMESTAMP
                    else:
                        sql_type, field_type = "VARCHAR", FieldType.DIMENSION
                else:
                    sql_type, field_type = "VARCHAR", FieldType.DIMENSION

            # PK overrides field_type
            if is_pk:
                field_type = FieldType.ID
                grain_parts.append(field_name)

            # nullable: if nullable kwarg is None (not specified), check Mapped[X | None]
            if nullable_kwarg is None:
                if annotation is not None and isinstance(annotation, ast.Subscript):
                    slice_node = annotation.slice
                    if isinstance(slice_node, ast.BinOp):
                        nullable = True
                    else:
                        nullable = False
                else:
                    nullable = False
            else:
                nullable = nullable_kwarg

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

            # Build JoinDef for FK fields
            if fk_target:
                join_target_counts[fk_target] = join_target_counts.get(fk_target, 0) + 1
                count = join_target_counts[fk_target]
                join_id = (
                    f"join:{table_name}:{fk_target}"
                    if count == 1
                    else f"join:{table_name}:{fk_target}:{field_name}"
                )
                target_entity_id = f"entity:{fk_target}"
                joins.append(JoinDef(
                    id=join_id,
                    source_entity_id=entity_id,
                    target_entity_id=target_entity_id,
                    join_type=JoinType.LEFT,
                    source_field_id=field_id,
                    target_field_id=f"field:{fk_target}:id",
                    description=f"SQLAlchemy FK: {table_name}.{field_name} -> {fk_target}.id",
                ))

        # Composite PK grain
        if len(grain_parts) == 1:
            grain = grain_parts[0]
        elif len(grain_parts) > 1:
            grain = "_".join(grain_parts)
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
        source_system="sqlalchemy",
        source_version="1.0",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={
            "source_file": str(file_path),
            "table_count": len(entities),
        },
    )


class SQLAlchemyParser:
    """SnapshotParser implementation for SQLAlchemy models.py files."""

    def detect(self, path: Path) -> float:
        path = Path(path)
        try:
            with open(path) as f:
                content = f.read(2000)
            has_sqlalchemy = (
                "from sqlalchemy" in content
                or "import sqlalchemy" in content
            )
            has_patterns = (
                "Column(" in content
                or "mapped_column(" in content
                or "__tablename__" in content
            )
            if has_sqlalchemy and has_patterns:
                return 0.9
            if has_patterns:
                return 0.5
        except Exception:
            pass
        return 0.0

    def parse(self, path: Path) -> SemanticSnapshot:
        return parse_sqlalchemy_models(Path(path))

    def source_type(self) -> str:
        return "sqlalchemy"
