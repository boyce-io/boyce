"""
Snapshot Validation Module - The "Bouncer"

This module provides strict validation for SemanticSnapshot objects created by
the Ingestion Agent. It does not parse; it only checks if the Agent's output
is valid according to the schema and invariants.

The validation function returns a list of error strings. If empty, the snapshot is valid.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from datashark.core.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)


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
        # Attempt to create SemanticSnapshot from dict (Pydantic will validate schema)
        snapshot = SemanticSnapshot(**snapshot_data)
    except Exception as e:
        errors.append(f"Schema validation failed: {str(e)}")
        # If schema validation fails, we can't proceed with other checks
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


def _compute_snapshot_hash(snapshot: SemanticSnapshot) -> str:
    """
    Compute the SHA-256 hash of a SemanticSnapshot.
    
    This matches the hash computation logic used in SnapshotStore._compute_snapshot_id().
    The hash is computed over the canonical JSON serialization, excluding
    the snapshot_id field itself.
    
    Args:
        snapshot: SemanticSnapshot instance
        
    Returns:
        64-character hexadecimal SHA-256 hash string
    """
    # Use model_dump to get dict representation (matches SnapshotStore._canonical_serialize)
    snapshot_dict = snapshot.model_dump(mode='json')
    
    # Exclude snapshot_id from hash computation (it's derived from the hash)
    if 'snapshot_id' in snapshot_dict:
        snapshot_dict = {k: v for k, v in snapshot_dict.items() if k != 'snapshot_id'}
    
    # Serialize with deterministic options (matches SnapshotStore exactly):
    # - sort_keys=True
    # - ensure_ascii=False
    # - separators=(',', ':') for compact format
    snapshot_json = json.dumps(
        snapshot_dict,
        sort_keys=True,
        ensure_ascii=False,
        separators=(',', ':')  # Compact format (no extra whitespace)
    )
    
    # Compute SHA-256 hash
    json_bytes = snapshot_json.encode('utf-8')
    hash_obj = hashlib.sha256(json_bytes)
    return hash_obj.hexdigest()
