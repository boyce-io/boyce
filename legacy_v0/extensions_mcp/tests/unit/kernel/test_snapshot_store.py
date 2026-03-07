"""Unit tests for SnapshotStore CAS implementation."""

import json
import tempfile
from pathlib import Path

import pytest

from datashark.core.types import SemanticSnapshot, Entity, FieldDef, FieldType, JoinDef, JoinType
from datashark_mcp.kernel.exceptions import SnapshotIntegrityError, SnapshotNotFoundError
from datashark_mcp.kernel.snapshot_store import SnapshotStore


@pytest.fixture
def temp_snapshot_dir():
    """Create a temporary directory for snapshot storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_snapshot():
    """Create a sample SemanticSnapshot for testing."""
    entities = {
        "entity_1": Entity(
            id="entity_1",
            name="users",
            schema_name="public",
            fields=["field_1", "field_2"],
            grain="user_id"
        )
    }
    fields = {
        "field_1": FieldDef(
            id="field_1",
            entity_id="entity_1",
            name="user_id",
            field_type=FieldType.DIMENSION,
            data_type="integer",
            nullable=False,
            primary_key=True
        ),
        "field_2": FieldDef(
            id="field_2",
            entity_id="entity_1",
            name="email",
            field_type=FieldType.DIMENSION,
            data_type="varchar",
            nullable=True,
            primary_key=False
        )
    }
    joins = []
    
    return SemanticSnapshot(
        snapshot_id="",  # Will be computed by store
        source_system="test",
        source_version="1.0",
        schema_version="v0.1",
        entities=entities,
        fields=fields,
        joins=joins,
        metadata={"test_key": "test_value"}
    )


def test_save_then_load_returns_identical(sample_snapshot, temp_snapshot_dir):
    """Test that save() then load() returns identical snapshot."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Save snapshot
    snapshot_id = store.save(sample_snapshot)
    
    # Load snapshot
    loaded = store.load(snapshot_id)
    
    # Verify model_dump() is identical
    original_dict = sample_snapshot.model_dump()
    loaded_dict = loaded.model_dump()
    
    # Update original with computed snapshot_id for comparison
    original_dict['snapshot_id'] = snapshot_id
    
    assert original_dict == loaded_dict, "Loaded snapshot should match original"


def test_two_saves_of_same_snapshot_produce_same_id(sample_snapshot, temp_snapshot_dir):
    """Test that two saves of the same semantic snapshot produce the same snapshot_id."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Save first time
    snapshot_id_1 = store.save(sample_snapshot)
    
    # Save second time (should be idempotent)
    snapshot_id_2 = store.save(sample_snapshot)
    
    assert snapshot_id_1 == snapshot_id_2, "Same snapshot should produce same snapshot_id"
    assert len(snapshot_id_1) == 64, "snapshot_id should be 64 hex characters"


def test_atomic_write_creates_exactly_one_file(sample_snapshot, temp_snapshot_dir):
    """Test that atomic write creates exactly one file."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Save snapshot
    snapshot_id = store.save(sample_snapshot)
    
    # Check that exactly one file exists
    snapshot_files = list(temp_snapshot_dir.glob("*.json"))
    assert len(snapshot_files) == 1, f"Expected 1 snapshot file, found {len(snapshot_files)}"
    
    # Verify file name matches snapshot_id
    expected_file = temp_snapshot_dir / f"{snapshot_id}.json"
    assert expected_file.exists(), f"Snapshot file {expected_file} should exist"
    
    # Verify no temp files remain
    temp_files = list(temp_snapshot_dir.glob("*.tmp"))
    assert len(temp_files) == 0, f"Temp files should be cleaned up, found {temp_files}"


def test_exists_returns_true_after_save(sample_snapshot, temp_snapshot_dir):
    """Test that exists() returns True after save."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    snapshot_id = store.save(sample_snapshot)
    
    assert store.exists(snapshot_id), "exists() should return True for saved snapshot"


def test_exists_returns_false_for_nonexistent(temp_snapshot_dir):
    """Test that exists() returns False for nonexistent snapshot."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    fake_id = "a" * 64  # Valid format but doesn't exist
    
    assert not store.exists(fake_id), "exists() should return False for nonexistent snapshot"


def test_load_nonexistent_raises_not_found(temp_snapshot_dir):
    """Test that loading nonexistent snapshot raises SnapshotNotFoundError."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    fake_id = "a" * 64
    
    with pytest.raises(SnapshotNotFoundError):
        store.load(fake_id)


def test_secret_validation_rejects_password_key(sample_snapshot, temp_snapshot_dir):
    """Test that save() rejects snapshots with password-like keys in metadata."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Create snapshot with password in metadata
    bad_metadata = sample_snapshot.model_dump()
    bad_metadata['metadata'] = {"password": "secret123"}
    bad_snapshot = SemanticSnapshot(**bad_metadata)
    
    with pytest.raises(SnapshotIntegrityError) as exc_info:
        store.save(bad_snapshot)
    
    assert "secret" in str(exc_info.value).lower() or "password" in str(exc_info.value).lower()


def test_secret_validation_rejects_token_key(sample_snapshot, temp_snapshot_dir):
    """Test that save() rejects snapshots with token-like keys in metadata."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Create snapshot with token in metadata
    bad_metadata = sample_snapshot.model_dump()
    bad_metadata['metadata'] = {"api_token": "abc123"}
    bad_snapshot = SemanticSnapshot(**bad_metadata)
    
    with pytest.raises(SnapshotIntegrityError):
        store.save(bad_snapshot)


def test_determinism_same_input_same_hash(sample_snapshot, temp_snapshot_dir):
    """Test that same input always produces same hash (determinism)."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Save same snapshot twice
    id1 = store.save(sample_snapshot)
    
    # Create identical snapshot (new instance)
    snapshot_copy = SemanticSnapshot(**sample_snapshot.model_dump())
    id2 = store.save(snapshot_copy)
    
    assert id1 == id2, "Identical snapshots must produce identical hashes"


def test_snapshot_id_computed_from_canonical_serialization(sample_snapshot, temp_snapshot_dir):
    """Test that snapshot_id is computed from canonical serialization, not raw_metadata."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Save with empty snapshot_id
    snapshot_with_empty_id = SemanticSnapshot(**{**sample_snapshot.model_dump(), "snapshot_id": ""})
    snapshot_id = store.save(snapshot_with_empty_id)
    
    # Verify snapshot_id is set correctly
    assert len(snapshot_id) == 64, "snapshot_id should be 64 hex characters"
    
    # Load and verify
    loaded = store.load(snapshot_id)
    assert loaded.snapshot_id == snapshot_id, "Loaded snapshot should have correct snapshot_id"


def test_schema_version_preserved(sample_snapshot, temp_snapshot_dir):
    """Test that schema_version field is preserved in save/load."""
    store = SnapshotStore(snapshot_dir=temp_snapshot_dir)
    
    # Ensure schema_version is set
    snapshot_with_version = SemanticSnapshot(**{**sample_snapshot.model_dump(), "schema_version": "v0.1"})
    snapshot_id = store.save(snapshot_with_version)
    
    loaded = store.load(snapshot_id)
    assert loaded.schema_version == "v0.1", "schema_version should be preserved"
