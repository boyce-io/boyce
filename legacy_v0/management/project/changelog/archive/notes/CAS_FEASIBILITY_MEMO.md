# CAS Feasibility Analysis: SemanticSnapshot Content-Addressable Storage
## Evidence-Only Assessment

**Generated:** 2025-12-31  
**Commit:** 280c40e (main)

---

## 1) SNAPSHOT_DIR Configuration

### File Paths
- **Config Module:** `datashark-mcp/src/datashark/core/config.py:58`
- **Constant:** `SNAPSHOT_DIR = get_snapshot_dir()` (line 78)

### How Config is Loaded/Used
```python
def get_snapshot_dir() -> Path:
    """
    Get the snapshot directory path.
    
    Resolution order:
    1. Environment variable DATASHARK_SNAPSHOT_DIR (highest priority)
    2. Default: PROJECT_ROOT / "tests" / "fixtures" / "semantic"
    
    Returns:
        Path to the snapshot directory
    """
    env_snapshot_dir = os.environ.get("DATASHARK_SNAPSHOT_DIR")
    if env_snapshot_dir:
        return Path(env_snapshot_dir).resolve()
    
    # Default: tests/fixtures/semantic in the project root
    default = PROJECT_ROOT / "tests" / "fixtures" / "semantic"
    return default.resolve()

SNAPSHOT_DIR = get_snapshot_dir()
```

**Status:** ✅ **NOW USED** by Safety Kernel code paths (CAS implemented).

**Evidence:**
- `SNAPSHOT_DIR` imported in `datashark-mcp/src/datashark_mcp/kernel/snapshot_store.py:16`
- `SnapshotStore` uses `SNAPSHOT_DIR` for CAS storage (line 35)
- `DataSharkEngine.load_snapshot_by_id()` uses `SnapshotStore` (line 91)
- CAS is fully implemented and operational

### Existing Filesystem Helpers
- **Atomic writes:** `datashark-mcp/src/datashark_mcp/_legacy/context/store/json_store.py:141` (`save_atomic` method)
  - Pattern: Write to temp file → `os.replace()` for atomic rename
  - Code: Lines 142, 156-158, 251-253
- **Path validation:** `datashark-mcp/src/datashark/core/config.py:81` (`validate_source` function)
  - Validates source names for filesystem safety (invalid chars, path separators)

---

## 2) JSONStore Analysis

### File Path
- **Primary:** `datashark-mcp/src/datashark_mcp/_legacy/context/store/json_store.py:19`

### What It Stores and How Keys Are Defined
**Storage Format:**
- **Nodes:** `nodes.jsonl` or `nodes.json` (JSONL preferred)
- **Edges:** `edges.jsonl` or `edges.json` (JSONL preferred)
- **Manifest:** `manifest.json` (single JSON file)

**Keys:**
- **NOT content-addressable** — Files are named by directory, not by hash
- **Directory-based:** `JSONStore(snapshot_dir: Path)` — entire directory is the "key"
- **No hash-based retrieval:** `load()` method reads entire directory, not by hash

**Methods:**
- `save_atomic(nodes: List[Node], edges: List[Edge], manifest: Dict[str, Any])` — Writes all data atomically
- `load() -> Tuple[List[Dict], List[Dict], Dict]` — Loads entire directory contents

### Read/Write by Key Support
**Status:** NO — JSONStore does not support hash-based keys

**Evidence:**
- `save_atomic()` takes Node/Edge lists, not a hash key
- `load()` returns all nodes/edges, not filtered by hash
- No `get_by_hash(hash: str)` or `save_with_hash(data, hash: str)` methods

### Usage in Current (Non-Legacy) Code Paths
**Status:** NOT USED in Safety Kernel paths

**Evidence:**
- **Legacy usage only:**
  - `datashark-mcp/src/datashark/core/server.py:686` — Legacy `_run_query` path
  - `datashark-mcp/src/datashark_mcp/orchestration/instance_hub.py:59` — InstanceHub (legacy)
  - `datashark-mcp/src/datashark_mcp/_legacy/tools/concurrent_query_test.py:50` — Legacy test
- **Safety Kernel paths:** No imports of JSONStore in `datashark-mcp/src/datashark_mcp/kernel/`

**Conclusion:** JSONStore is legacy infrastructure, not used by current SemanticSnapshot/Safety Kernel architecture. **UPDATE (2026-01-02):** CAS is now fully implemented via `SnapshotStore` class, which provides content-addressable storage for SemanticSnapshot objects.

---

## 3) Minimal Integration Points for CAS

### Integration Point #1: Snapshot Creation
**Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:38`

**Current Code:**
```python
@staticmethod
def create_snapshot(raw_metadata: Dict) -> Tuple[SemanticGraph, SnapshotID]:
    # ... hash computation ...
    graph = SemanticGraph.model_construct(raw_data=raw_metadata)
    snapshot_id = SnapshotID(id=hash_hex)
    return (graph, snapshot_id)
```

**Change Required:**
- After creating `SemanticGraph` and `SnapshotID`, call CAS `save()` method
- Pass `SemanticSnapshot` object (or convert `SemanticGraph` to `SemanticSnapshot`)
- Store at path: `SNAPSHOT_DIR / snapshot_id.id[:2] / snapshot_id.id[2:4] / snapshot_id.id[4:]`
- Return same tuple (no API change)

**Code Pointer:** Lines 71, 89, 92

---

### Integration Point #2: Snapshot ID Logging/Audit
**Location:** `datashark-mcp/src/datashark/core/audit.py:197`

**Current Code:**
```python
def log_artifact(
    input_query: str,
    snapshot_id: str,  # SHA-256 hash string
    generated_sql: str,
    ...
):
    record = AuditRecord(
        snapshot_id=snapshot_id,  # Hash stored, not snapshot object
        ...
    )
```

**Change Required:**
- No change needed (audit already stores hash)
- **Optional enhancement:** Verify snapshot exists in CAS before logging (defensive check)

**Code Pointer:** Line 222

---

### Integration Point #3: Active Snapshot ID Usage by Planner
**Location:** `datashark-mcp/src/datashark_mcp/planner/planner.py:54`

**Current Code:**
```python
def plan_and_build_sql(
    self,
    query_input: str,
    user_context: dict,
    active_snapshot_id: str  # SHA-256 hash string
) -> Dict[str, Any]:
    reasoning_steps.append(f"Context Setup: Starting planning for snapshot {active_snapshot_id}")
```

**Change Required:**
- **Option A (lazy load):** Planner receives `active_snapshot_id` string, CAS load happens in `DataSharkEngine.get_api_client()` if snapshot not already loaded
- **Option B (explicit load):** Add `load_snapshot(snapshot_id: str) -> SemanticSnapshot` call before planner instantiation
- Planner itself doesn't need changes (receives hash string, doesn't access snapshot directly)

**Code Pointer:** Lines 54, 98, 156

**Upstream Call Site:**
- `datashark-mcp/src/datashark_mcp/kernel/engine.py:153` — `planner.plan_and_build_sql(..., active_snapshot_id=snapshot_id_str)`
- **Change location:** `datashark-mcp/src/datashark_mcp/kernel/engine.py:140-144` (before planner instantiation)

---

## 4) Minimal CAS API (Interface Only)

### Proposed API
```python
class SnapshotStore:
    """Content-addressable storage for SemanticSnapshot objects."""
    
    def save(self, snapshot: SemanticSnapshot) -> str:
        """
        Save snapshot to CAS and return snapshot_id.
        
        Args:
            snapshot: SemanticSnapshot to save
            
        Returns:
            snapshot_id (SHA-256 hash string)
            
        Raises:
            SnapshotIntegrityError: If save fails
        """
        # Implementation: serialize snapshot, compute hash, write to filesystem
        pass
    
    def load(self, snapshot_id: str) -> SemanticSnapshot:
        """
        Load snapshot from CAS by hash.
        
        Args:
            snapshot_id: SHA-256 hash string (64 hex chars)
            
        Returns:
            SemanticSnapshot object
            
        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
            SnapshotIntegrityError: If loaded data doesn't match hash
        """
        # Implementation: read from filesystem, deserialize, validate hash
        pass
    
    def exists(self, snapshot_id: str) -> bool:
        """
        Check if snapshot exists in CAS.
        
        Args:
            snapshot_id: SHA-256 hash string
            
        Returns:
            True if snapshot exists, False otherwise
        """
        # Implementation: check filesystem path existence
        pass
```

### Where API Naturally Belongs
**Recommended Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_store.py`

**Rationale:**
- Co-located with `snapshot_factory.py` (same directory)
- Part of Safety Kernel (not legacy)
- Natural extension of `SnapshotFactory` (factory creates, store persists)
- Follows existing pattern: `kernel/` contains core Safety Kernel components

**Alternative Locations (less ideal):**
- `datashark-mcp/src/datashark/core/storage/` — Would require new directory
- `datashark-mcp/src/datashark_mcp/_legacy/context/store/` — Legacy location, not appropriate for Safety Kernel

---

## 5) Blockers & Concerns

### Blocker #1: Pydantic Model Serialization
**Status:** SOLVABLE

**Evidence:**
- Pydantic v2 models support `.model_dump()` and `.model_dump_json()` methods
- Evidence: `datashark-mcp/src/datashark_mcp/kernel/engine.py:148` uses `self.context.model_dump()`
- SemanticSnapshot is Pydantic BaseModel, so serialization is straightforward

**Solution:**
```python
# Serialize SemanticSnapshot to JSON
snapshot_dict = snapshot.model_dump(mode='json')
snapshot_json = json.dumps(snapshot_dict, sort_keys=True, ensure_ascii=False)
```

**Concern:** Need to ensure serialization matches hash computation (same canonicalization)

---

### Blocker #2: Schema Evolution/Versioning
**Status:** GAP (not currently handled)

**Evidence:**
- SemanticSnapshot has no `schema_version` field
- No versioning metadata in current model
- Hash computation doesn't include schema version

**Required Fields:**
- Add `schema_version: str` to SemanticSnapshot (or metadata)
- Include schema_version in hash computation
- Handle version mismatches in `load()` (reject incompatible versions)

**Code Location:** `datashark-mcp/src/datashark/core/types.py:114` (SemanticSnapshot definition)

---

### Blocker #3: Concurrency/Locking for Filesystem Store
**Status:** PARTIALLY SOLVED (atomic writes exist)

**Evidence:**
- JSONStore uses atomic writes: `os.replace(tmp_file, final_file)` (`datashark-mcp/src/datashark_mcp/_legacy/context/store/json_store.py:251-253`)
- No file locking for concurrent reads (filesystem is read-safe)
- No locking for concurrent writes (race condition possible if two processes write same hash)

**Solution:**
- **Reads:** No locking needed (filesystem reads are safe)
- **Writes:** Use atomic write pattern (temp file + `os.replace`)
- **Race condition:** If two processes write same hash simultaneously, last write wins (acceptable for CAS — content is identical)

**Code Pattern to Reuse:**
```python
# From json_store.py:141-253
tmp_suffix = f".{int(time.time()*1000)}.tmp"
tmp_file = target_path.with_suffix(target_path.suffix + tmp_suffix)
# Write to tmp_file
os.replace(tmp_file, target_path)  # Atomic rename
```

---

### Blocker #4: Security (Secrets in Metadata)
**Status:** RISK (no redaction currently)

**Evidence:**
- SemanticSnapshot.metadata is `Dict[str, Any]` (opaque, source-specific)
- No redaction in `SnapshotFactory.create_snapshot()`
- No redaction in audit logs (`datashark/core/audit.py`)

**Risk:**
- If `raw_metadata` contains secrets (passwords, API keys), they will be:
  1. Hashed (in snapshot_id)
  2. Stored in CAS (if implemented)
  3. Logged in audit records

**Mitigation Options:**
- **Option A:** Redact secrets before hashing (normalize secrets to placeholder)
- **Option B:** Document that CAS stores raw metadata (user responsibility)
- **Option C:** Add `redact_secrets()` step in `SnapshotFactory.create_snapshot()`

**Code Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:38` (before serialization)

**Existing Secret Detection:**
- `datashark-mcp/src/datashark_mcp/_legacy/context/security.py:55` (`validate_no_secrets` function)
- Not currently used in Safety Kernel paths

---

## Summary

### Feasibility: HIGH

**Enablers:**
- ✅ SNAPSHOT_DIR config exists (unused but ready)
- ✅ Atomic write pattern exists (JSONStore.save_atomic)
- ✅ Pydantic serialization available (`.model_dump()`)
- ✅ Hash computation already deterministic
- ✅ Integration points are clear and minimal

**Blockers (All Solvable):**
- ⚠️ Schema versioning not in model (add field)
- ⚠️ No secrets redaction (add normalization step)
- ⚠️ No file locking (acceptable for CAS — atomic writes sufficient)

**Recommended Implementation:**
1. Create `datashark-mcp/src/datashark_mcp/kernel/snapshot_store.py` with `SnapshotStore` class
2. Add `save()` call in `SnapshotFactory.create_snapshot()` after hash computation
3. Add `load()` call in `DataSharkEngine.load_metadata()` if snapshot_id provided instead of raw_metadata
4. Use filesystem path: `SNAPSHOT_DIR / hash[:2] / hash[2:4] / hash[4:].json`
5. Use atomic write pattern (temp file + `os.replace`)

**Estimated Complexity:** LOW-MEDIUM (straightforward filesystem operations, Pydantic serialization is built-in)
