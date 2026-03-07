# Midpoint Artifact Contract Sheet
## SemanticSnapshot Implementation Spec (Evidence-Only)

**Generated:** 2025-12-31  
**Commit:** 280c40e (main)

---

## 1) SemanticSnapshot Definition

### File Path
`datashark-mcp/src/datashark/core/types.py:114`

### Class Definition
```python
class SemanticSnapshot(BaseModel):
    """
    Source-agnostic canonical representation of database metadata.
    
    This is the deterministic, immutable snapshot that can be populated from
    any ingestion adapter (Looker, Tableau, dbt, etc.) and used by the Planner
    and SQLBuilder without knowledge of the source origin.
    
    Attributes:
        snapshot_id: Deterministic SHA-256 hash identifier
        source_system: Origin system (e.g., "looker", "tableau", "dbt")
        source_version: Version of the source system or extractor
        entities: Dictionary mapping entity_id -> Entity
        fields: Dictionary mapping field_id -> FieldDef
        joins: List of join relationships
        metadata: Optional additional metadata (source-specific, but opaque to engine)
    """
    
    model_config = {"frozen": True}
    
    snapshot_id: str  # SHA-256 hash
    source_system: str
    source_version: Optional[str] = None
    entities: Dict[str, Entity] = Field(default_factory=dict)
    fields: Dict[str, FieldDef] = Field(default_factory=dict)
    joins: List[JoinDef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### Key Fields (Names + Types)
- `snapshot_id: str` — SHA-256 hash (64 hex chars)
- `source_system: str` — Origin system identifier
- `source_version: Optional[str]` — Source/extractor version
- `entities: Dict[str, Entity]` — Entity ID → Entity mapping
- `fields: Dict[str, FieldDef]` — Field ID → FieldDef mapping
- `joins: List[JoinDef]` — Join relationship list
- `metadata: Dict[str, Any]` — Opaque source-specific metadata

### Immutability Settings
- **`model_config = {"frozen": True}`** — Pydantic frozen model (immutable after creation)
- **Nested models also frozen:**
  - `Entity.model_config = {"frozen": True}` (line 48)
  - `FieldDef.model_config = {"frozen": True}` (line 76)
  - `JoinDef.model_config = {"frozen": True}` (line 103)

---

## 2) SnapshotID / Hash Computation

### Exact Function
**File:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:38`

```python
@staticmethod
def create_snapshot(raw_metadata: Dict) -> Tuple[SemanticGraph, SnapshotID]:
    """Create a semantic snapshot from raw metadata."""
    try:
        # Step A: Instantiate SemanticGraph using the raw_metadata
        graph = SemanticGraph.model_construct(raw_data=raw_metadata)
        
        # Step B: Deterministic serialization of the graph metadata
        # Use json.dumps with sort_keys=True to ensure deterministic ordering
        # This ensures the same metadata always produces the same hash
        serialized_metadata = json.dumps(
            raw_metadata,
            sort_keys=True,
            ensure_ascii=False  # Preserve unicode characters
        )
        
        # Step C: Generate SHA-256 hash of the serialized string
        # Encode the string to bytes before hashing
        hash_bytes = hashlib.sha256(serialized_metadata.encode('utf-8')).digest()
        hash_hex = hash_bytes.hex()
        
        # Step D: Instantiate SnapshotID with the hash
        # The SnapshotID model will validate that the hash is 64 hex characters
        snapshot_id = SnapshotID(id=hash_hex)
        
        # Step E: Return the tuple (graph, snapshot_id)
        return (graph, snapshot_id)
```

### What Data is Hashed
- **Full `raw_metadata` dictionary** (entire input)
- **NOT** the SemanticGraph object (hashed before graph instantiation)
- **NOT** the SemanticSnapshot object (hash computed separately in LookerAdapter)

### Canonicalization Steps
1. **JSON serialization with sorted keys:**
   ```python
   json.dumps(raw_metadata, sort_keys=True, ensure_ascii=False)
   ```
   - `sort_keys=True` — Ensures deterministic key ordering
   - `ensure_ascii=False` — Preserves unicode characters

2. **UTF-8 encoding:**
   ```python
   serialized_metadata.encode('utf-8')
   ```

3. **SHA-256 hashing:**
   ```python
   hashlib.sha256(serialized_metadata.encode('utf-8')).digest()
   hash_hex = hash_bytes.hex()  # 64-character hex string
   ```

4. **SnapshotID normalization:**
   ```python
   # datashark-mcp/src/datashark_mcp/kernel/types.py:67
   return v.lower()  # Normalize to lowercase for consistency
   ```

### Timestamps/UUIDs Handling
- **NO normalization** — Timestamps and UUIDs in `raw_metadata` are hashed as-is
- **Evidence:** No timestamp/UUID normalization code found in `snapshot_factory.py`
- **Gap:** If `raw_metadata` contains `extracted_at` timestamps or `run_id` UUIDs, hash will differ across runs

### Alternative Hash Computation (LookerAdapter)
**File:** `datashark-mcp/src/datashark/ingestion/looker/adapter.py:290-292`

```python
# Deterministic serialization
snapshot_json = json.dumps(snapshot_dict, sort_keys=True, ensure_ascii=False)
snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
```

**Note:** LookerAdapter computes hash from `snapshot_dict` (subset of metadata), not full `raw_metadata`. This is a separate code path from `SnapshotFactory.create_snapshot()`.

---

## 3) Creation and Consumption Call Sites

### Creation Call Site #1: SnapshotFactory (Kernel Entry Point)
**File:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:38`  
**Function:** `SnapshotFactory.create_snapshot(raw_metadata: Dict) -> Tuple[SemanticGraph, SnapshotID]`  
**Line Range:** 38-92

**Called from:**
- `datashark-mcp/src/datashark_mcp/kernel/engine.py:62` — `DataSharkEngine.load_metadata()`

### Creation Call Site #2: LookerAdapter (Direct SemanticSnapshot Creation)
**File:** `datashark-mcp/src/datashark/ingestion/looker/adapter.py:41`  
**Function:** `LookerAdapter.ingest(lookml_explore: Dict[str, Any]) -> SemanticSnapshot`  
**Line Range:** 41-305

**Hash Computation:** Lines 290-292 (separate from SnapshotFactory)

### Consumption Call Site #1: Planner (via active_snapshot_id string)
**File:** `datashark-mcp/src/datashark_mcp/planner/planner.py:54`  
**Function:** `Planner.plan_and_build_sql(query_input: str, user_context: dict, active_snapshot_id: str)`  
**Line Range:** 54-189

**Usage:**
```python
# Line 98
reasoning_steps.append(f"Context Setup: Starting planning for snapshot {active_snapshot_id}")

# Line 156
result = planner.plan_and_build_sql(
    query_input=intent,
    user_context=user_context_dict,
    active_snapshot_id=snapshot_id_str  # SHA-256 hash string
)
```

**Note:** Planner receives `active_snapshot_id` as string, not SemanticSnapshot object. Planner accesses graph via `AirGapAPI` (read-only interface to ProjectedGraph).

### Consumption Call Site #2: SQLBuilder (SemanticSnapshot object)
**File:** `datashark-mcp/src/datashark/core/sql/builder.py:65`  
**Function:** `SQLBuilder.build_final_sql(planner_output: Dict[str, Any], snapshot: SemanticSnapshot, input_query: Optional[str] = None) -> str`  
**Line Range:** 65-129

**Usage:**
```python
# Line 95
if not snapshot:
    raise ValueError("SemanticSnapshot is required. The snapshot is the sole source of truth for JOIN definitions.")

# Line 106-108
from_clause, join_clauses = self._build_joins_from_snapshot(
    snapshot, concept_map, planner_output.get("join_path", [])
)
```

**Note:** SQLBuilder receives SemanticSnapshot object directly (not via hash). This is the legacy SQLBuilder path.

### Consumption Call Site #3: JoinPathResolver (SemanticSnapshot object)
**File:** `datashark-mcp/src/datashark/core/sql/join_resolver.py:27`  
**Function:** `JoinPathResolver.__init__(snapshot: SemanticSnapshot, dialect: SQLDialect)`  
**Line Range:** 27-32

**Usage:**
```python
# Line 214
target_entity = self.snapshot.entities.get(join_def.target_entity_id)

# Line 221
target_field = self.snapshot.fields.get(join_def.target_field_id)
```

### How Snapshot is Passed
- **In-memory only** — SemanticSnapshot objects are Python objects, not serialized
- **Via function parameters** — Passed as objects (not JSON/dict)
- **Via AirGapAPI** — Planner accesses filtered view (ProjectedGraph) via read-only API
- **SnapshotID as string** — Hash string passed separately (e.g., `active_snapshot_id: str`)

**Evidence:**
- ✅ `SnapshotStore.save(snapshot)` persists SemanticSnapshot to CAS
- ✅ `SnapshotStore.load(snapshot_id)` retrieves SemanticSnapshot by hash
- ✅ `SnapshotFactory.save_snapshot(snapshot)` convenience method exists
- ✅ `DataSharkEngine.load_snapshot_by_id(snapshot_id)` loads from CAS
- **UPDATE (2026-01-02):** CAS is fully implemented. Snapshots are now persisted and retrievable by hash.

---

## 4) Persistence Hooks

### Persistence: NOT IMPLEMENTED
**Status:** No content-addressable storage found

**Evidence:**
- No `save_snapshot(snapshot: SemanticSnapshot, path: Path)` function
- No `load_snapshot(snapshot_id: str) -> SemanticSnapshot` function
- No database/cache writes for SemanticSnapshot objects
- No retrieval-by-hash logic

### Placeholder: Snapshot Directory Config
**File:** `datashark-mcp/src/datashark/core/config.py:58`

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

**Status:** Directory path exists but no write/read functions use it for SemanticSnapshot

### Legacy Persistence (Separate System)
**File:** `datashark-mcp/src/datashark_mcp/_legacy/context/store/json_store.py:141`

```python
def save_atomic(self, nodes: List[Node], edges: List[Edge], manifest: Dict[str, Any]) -> None:
    """Save nodes, edges, and manifest atomically."""
    # Writes nodes.jsonl, edges.jsonl, manifest.json
```

**Status:** Legacy JSONStore persists Node/Edge/Manifest (separate from SemanticSnapshot). This is not used by current Safety Kernel architecture.

### Audit Log Persistence (SnapshotID Only)
**File:** `datashark-mcp/src/datashark/core/audit.py:197`

```python
def log_artifact(
    input_query: str,
    snapshot_id: str,  # SHA-256 hash string
    generated_sql: str,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Path]:
    """Log an artifact using the global writer."""
    record = AuditRecord(
        request_id=request_id or str(uuid.uuid4()),
        snapshot_id=snapshot_id,  # Hash stored, not snapshot object
        input_query=input_query,
        generated_sql=generated_sql,
        metadata=metadata or {}
    )
    writer = get_audit_writer()
    return writer.write_record(record)
```

**Status:** Only `snapshot_id` (hash string) is persisted in audit logs. Full SemanticSnapshot object is NOT persisted.

---

## Summary

**SemanticSnapshot Contract:**
- ✅ Immutable (frozen=True)
- ✅ Deterministic hash (SHA-256 with sorted keys)
- ❌ No persistence (in-memory only)
- ❌ No retrieval-by-hash
- ❌ No timestamp/UUID normalization before hashing
- ✅ Passed as Python objects (not serialized)
- ✅ SnapshotID (hash) passed separately as string

**Gap:** SemanticSnapshot is the midpoint artifact in structure, but lacks content-addressable storage, making it impossible to retrieve or verify snapshots by hash.
