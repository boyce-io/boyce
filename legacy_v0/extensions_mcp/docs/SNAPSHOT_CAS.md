# SemanticSnapshot Content-Addressable Storage (CAS)

## Overview

The `SnapshotStore` provides content-addressable storage for `SemanticSnapshot` objects, keyed by their deterministic SHA-256 hash (`snapshot_id`). This enables:

- **Deterministic snapshots**: Same metadata always produces the same `snapshot_id`
- **Audit trail**: `snapshot_id` serves as an authoritative pointer to persisted canonical snapshot bytes
- **Reproducibility**: Load any snapshot by its hash for testing, debugging, or replay

## Configuration

The snapshot directory is configured via the `DATASHARK_SNAPSHOT_DIR` environment variable:

```bash
export DATASHARK_SNAPSHOT_DIR=/path/to/snapshots
```

If not set, defaults to: `<project_root>/tests/fixtures/semantic`

## File Format

Snapshots are stored as JSON files:

```
<SNAPSHOT_DIR>/<snapshot_id>.json
```

Where `snapshot_id` is a 64-character hexadecimal SHA-256 hash string.

### Example

```
tests/fixtures/semantic/565f1f160d9b4b54fd2317248d3d6218f222dafe6f64f596348bdeb6b45f5e77.json
```

## Usage

### Saving a Snapshot

```python
from datashark.core.types import SemanticSnapshot
from datashark_mcp.kernel.snapshot_store import SnapshotStore
from datashark_mcp.kernel.snapshot_factory import SnapshotFactory

# Create or load a SemanticSnapshot
snapshot = ...  # Your SemanticSnapshot instance

# Save to CAS
store = SnapshotStore()
snapshot_id = SnapshotFactory.save_snapshot(snapshot)

# snapshot_id is now the authoritative hash
print(f"Snapshot ID: {snapshot_id}")
```

### Loading a Snapshot

```python
from datashark_mcp.kernel.snapshot_store import SnapshotStore
from datashark_mcp.kernel.exceptions import SnapshotNotFoundError

store = SnapshotStore()

try:
    snapshot = store.load("565f1f160d9b4b54fd2317248d3d6218f222dafe6f64f596348bdeb6b45f5e77")
    # Use snapshot...
except SnapshotNotFoundError:
    print("Snapshot not found in CAS")
```

### Checking Existence

```python
if store.exists(snapshot_id):
    snapshot = store.load(snapshot_id)
```

## Hash Computation

The `snapshot_id` is computed as:

1. Serialize `SemanticSnapshot` to canonical JSON (excluding `snapshot_id` field itself)
2. Use deterministic options: `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`
3. Compute SHA-256 hash of the serialized bytes
4. Use the 64-character hex string as `snapshot_id`

This ensures:
- **Determinism**: Same snapshot content → same hash
- **Canonicalization**: Field ordering and formatting are stable
- **Integrity**: Hash mismatch on load indicates corruption

## Security

### Secret Validation

Before saving, the store validates that `snapshot.metadata` does not contain obvious secret keys:

- `password`, `secret`, `token`, `apikey`, `api_key`
- `authorization`, `auth`, `credential`
- `private.*key` (regex pattern)

If detected, `save()` raises `SnapshotIntegrityError`.

**Important**: Secrets must be redacted before snapshot creation.

## Atomic Writes

Snapshots are written atomically using a temp file + rename pattern:

1. Write to `<snapshot_id>.json.<timestamp>.tmp`
2. Atomic rename to `<snapshot_id>.json` using `os.replace()`

This prevents corruption from partial writes.

## Integration Points

### SnapshotFactory

```python
from datashark_mcp.kernel.snapshot_factory import SnapshotFactory

# Save a snapshot after creation
snapshot_id = SnapshotFactory.save_snapshot(snapshot)
```

### DataSharkEngine

```python
from datashark_mcp.kernel.engine import DataSharkEngine

engine = DataSharkEngine(context)

# Load snapshot by ID
engine.load_snapshot_by_id("565f1f160d9b4b54fd2317248d3d6218f222dafe6f64f596348bdeb6b45f5e77")

# Process request (snapshot is now available)
result = engine.process_request("show me users")
```

## Schema Versioning

`SemanticSnapshot` includes a `schema_version` field (default: `"v0.1"`) for future schema evolution. The hash computation includes this field, so schema changes will produce different hashes.

## Backwards Compatibility

The CAS implementation preserves backwards compatibility:

- Existing code using `load_metadata()` continues to work
- `load_snapshot_by_id()` is optional; in-memory graphs still supported
- If a snapshot is not found in CAS, the engine falls back to in-memory operation (with a warning)
