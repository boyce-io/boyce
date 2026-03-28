"""
Snapshot Validation Module - The "Bouncer"

This module provides strict validation for SemanticSnapshot objects.
It does not parse; it only checks if the snapshot is valid according
to the schema and invariants.

The validation function returns a list of error strings. If empty, the snapshot is valid.
"""

from __future__ import annotations

import hashlib
import json
from typing import List

from .types import SemanticSnapshot


def validate_snapshot(snapshot_data: dict) -> List[str]:
    """
    Validate that a snapshot dictionary conforms to the SemanticSnapshot schema
    and satisfies all architectural invariants.

    This is the "Bouncer" - it does not parse or create snapshots, only validates.

    Args:
        snapshot_data: Dictionary representation of a SemanticSnapshot

    Returns:
        List of error strings. Empty list means the snapshot is valid.

    Validation Checks:
        1. Schema compliance (required fields present, correct types)
        2. Grain existence (every entity declares a grain)
        3. ID consistency (joins reference valid entity IDs, fields reference valid entities)
        4. Determinism (snapshot_id matches SHA-256 hash of content)
    """
    errors: List[str] = []

    # Check 1: Schema Compliance
    try:
        snapshot = SemanticSnapshot(**snapshot_data)
    except Exception as e:
        errors.append(f"Schema validation failed: {str(e)}")
        return errors

    # Check 2: Grain Existence
    for entity_id, entity in snapshot.entities.items():
        if entity.grain is None or entity.grain.strip() == "":
            errors.append(
                f"Entity '{entity_id}' (name: '{entity.name}') must declare a grain. "
                f"Use '<unknown_grain>' if grain cannot be determined."
            )

    # Check 3: ID Consistency
    # 3a: Verify all field entity_ids reference valid entities
    for field_id, field in snapshot.fields.items():
        if field.entity_id not in snapshot.entities:
            errors.append(
                f"Field '{field_id}' references entity_id '{field.entity_id}' "
                f"which does not exist in snapshot.entities"
            )

    # 3b: Verify all entity.fields lists reference valid field IDs
    for entity_id, entity in snapshot.entities.items():
        for field_id in entity.fields:
            if field_id not in snapshot.fields:
                errors.append(
                    f"Entity '{entity_id}' references field_id '{field_id}' "
                    f"which does not exist in snapshot.fields"
                )

    # 3c: Verify all joins reference valid entity IDs
    for join in snapshot.joins:
        if join.source_entity_id not in snapshot.entities:
            errors.append(
                f"Join '{join.id}' references source_entity_id '{join.source_entity_id}' "
                f"which does not exist in snapshot.entities"
            )
        if join.target_entity_id not in snapshot.entities:
            errors.append(
                f"Join '{join.id}' references target_entity_id '{join.target_entity_id}' "
                f"which does not exist in snapshot.entities"
            )

    # 3d: Verify all join field IDs reference valid fields
    for join in snapshot.joins:
        if join.source_field_id not in snapshot.fields:
            errors.append(
                f"Join '{join.id}' references source_field_id '{join.source_field_id}' "
                f"which does not exist in snapshot.fields"
            )
        if join.target_field_id not in snapshot.fields:
            errors.append(
                f"Join '{join.id}' references target_field_id '{join.target_field_id}' "
                f"which does not exist in snapshot.fields"
            )

    # 3e: Verify join field IDs belong to the correct entities
    for join in snapshot.joins:
        source_field = snapshot.fields.get(join.source_field_id)
        target_field = snapshot.fields.get(join.target_field_id)

        if source_field and source_field.entity_id != join.source_entity_id:
            errors.append(
                f"Join '{join.id}': source_field_id '{join.source_field_id}' belongs to "
                f"entity '{source_field.entity_id}', not '{join.source_entity_id}'"
            )

        if target_field and target_field.entity_id != join.target_entity_id:
            errors.append(
                f"Join '{join.id}': target_field_id '{join.target_field_id}' belongs to "
                f"entity '{target_field.entity_id}', not '{join.target_entity_id}'"
            )

    # Check 4: Determinism (snapshot_id matches SHA-256 hash)
    computed_hash = _compute_snapshot_hash(snapshot)
    if snapshot.snapshot_id != computed_hash:
        errors.append(
            f"Snapshot ID mismatch: provided '{snapshot.snapshot_id}' does not match "
            f"computed hash '{computed_hash}'. The snapshot_id must be the SHA-256 hash "
            f"of the canonical JSON serialization (excluding snapshot_id field itself)."
        )

    return errors


# Profiling fields are excluded from the snapshot_id hash.
# The hash represents structural identity (schema shape, joins, base field attributes).
# Profiling data is observational metadata that changes without altering schema identity.
_SNAPSHOT_PROFILING_FIELDS: frozenset = frozenset({"profiled_at"})
_ENTITY_PROFILING_FIELDS: frozenset = frozenset({"object_type", "row_count", "view_sql", "view_lineage"})
_FIELD_PROFILING_FIELDS: frozenset = frozenset({"null_rate", "distinct_count", "sample_values", "business_description", "business_rules"})
_JOIN_PROFILING_FIELDS: frozenset = frozenset({"join_confidence", "orphan_rate"})


def canonicalize_snapshot_for_hash(snapshot_dict: dict) -> dict:
    """
    Strip snapshot_id and all profiling fields from a snapshot dict, returning the
    canonical form used for SHA-256 hash computation.

    This is the single source of truth for what goes into the hash. Both
    build_snapshot() (at creation time) and _compute_snapshot_hash() (at validation
    time) must call this function to guarantee the hash is consistent.

    Args:
        snapshot_dict: Raw dict from SemanticSnapshot.model_dump(mode="json") or
                       a manually constructed dict with the same structure.

    Returns:
        New dict with snapshot_id and all profiling fields removed.
    """
    result = {
        k: v for k, v in snapshot_dict.items()
        if k != "snapshot_id" and k not in _SNAPSHOT_PROFILING_FIELDS
    }

    if "entities" in result:
        result["entities"] = {
            eid: {k: v for k, v in edata.items() if k not in _ENTITY_PROFILING_FIELDS}
            for eid, edata in result["entities"].items()
        }

    if "fields" in result:
        result["fields"] = {
            fid: {k: v for k, v in fdata.items() if k not in _FIELD_PROFILING_FIELDS}
            for fid, fdata in result["fields"].items()
        }

    if "joins" in result:
        result["joins"] = [
            {k: v for k, v in jdata.items() if k not in _JOIN_PROFILING_FIELDS}
            for jdata in result["joins"]
        ]

    return result


def _compute_snapshot_hash(snapshot: SemanticSnapshot) -> str:
    """
    Compute the SHA-256 hash of a SemanticSnapshot.

    Delegates canonicalization to canonicalize_snapshot_for_hash() so that
    build_snapshot() and validate_snapshot() always agree on what gets hashed.

    Args:
        snapshot: SemanticSnapshot instance

    Returns:
        64-character hexadecimal SHA-256 hash string
    """
    snapshot_dict = snapshot.model_dump(mode="json")
    canonical = canonicalize_snapshot_for_hash(snapshot_dict)

    snapshot_json = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    json_bytes = snapshot_json.encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()
