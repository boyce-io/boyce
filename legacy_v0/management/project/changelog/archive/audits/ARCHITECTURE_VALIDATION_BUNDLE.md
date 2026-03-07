# DataShark Architecture Validation Bundle
## Deterministic Midpoint Artifact Analysis

**Generated:** 2025-12-31  
**Commit:** 280c40e (main)  
**Purpose:** Validate whether current architecture implements a deterministic midpoint between agentic ingestion and agentic SQL generation

---

## SECTION 0 — Repo & Runtime Evidence

### Repository Context
```bash
$ pwd
/Users/willwright/ConvergentMethods/Products/DataShark

$ git rev-parse --show-toplevel
/Users/willwright/ConvergentMethods/Products/DataShark

$ git branch --show-current
main

$ git rev-parse --short HEAD
280c40e

$ git log -1 --oneline --decorate
280c40e (HEAD -> main) docs: add navigation + remove duplicate changelog artifacts
```

### Package Boundaries
- **datashark-mcp/** — Main MCP server package (Python)
  - **src/datashark_mcp/** — Core MCP server implementation
  - **src/datashark/** — Core semantic engine (types, SQL builder, ingestion)
  - **src/safety_kernel/** — Safety kernel models and guardrails
- **datashark-extension/** — VS Code extension (TypeScript)
- **core/** — Legacy adapters (Postgres, Redshift, Tableau, dbt, Airflow)
- **tools/** — Runner tools, golden harness, ingest scripts
- **tests/** — Test suites (unit, integration, golden baselines)

### Runtime Topology (10-Line Summary)
- **MCP Server** (`datashark-mcp/src/datashark/core/server.py`): Async MCP protocol server exposing database tools to AI agents
- **Safety Kernel Engine** (`datashark-mcp/src/datashark_mcp/kernel/engine.py`): Orchestrates SnapshotFactory → GraphProjector → AirGapAPI → Planner pipeline
- **Planner** (`datashark-mcp/src/datashark_mcp/planner/planner.py`): Deterministic planning pipeline (ConceptMapper → GrainResolver → JoinPlanner → SQLBuilder)
- **SQL Builder** (`datashark-mcp/src/datashark/core/sql/builder.py`): Renders structured planner output to dialect-specific SQL
- **Query Executor** (`core/query_executor.py`): Executes SQL via connection pool (psycopg2-binary)
- **Extension** (`datashark-extension/src/extension.ts`): VS Code UI for query execution and results
- **Runner Tools** (`tools/runner/`): Standalone execution harness for contract testing
- **Ingestion Adapters** (`datashark/ingestion/looker/`, `core/adapters/`): Convert source metadata → SemanticSnapshot
- **Audit Logger** (`datashark-mcp/src/datashark/core/audit.py`): Writes JSONL artifacts (input → snapshot_id → SQL)
- **Query Validator** (`datashark-mcp/src/datashark_mcp/safety/query_validator.py`): SQL parser-based safety checks (blocks DROP/DELETE/INSERT)

---

## SECTION 1 — Candidate "Midpoint Artifact" Identification

### Candidate #1: SemanticSnapshot (PRIMARY CANDIDATE)

**Artifact Name:** `SemanticSnapshot` (also referenced as `SemanticGraph` in kernel layer)

**Where it lives:**
- **Type Definition:** `datashark-mcp/src/datashark/core/types.py:114` (SemanticSnapshot)
- **Kernel Type:** `datashark-mcp/src/datashark_mcp/kernel/types.py:70` (SemanticGraph)
- **Factory:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:24` (SnapshotFactory.create_snapshot)

**Format:**
- Pydantic BaseModel with `frozen=True` (immutable)
- Python object in memory; can be serialized to JSON
- Schema: `datashark/core/types.py` defines Entity, FieldDef, JoinDef, TemporalFilter, FilterDef

**Inputs:**
- Raw metadata from ingestion adapters (Looker, Tableau, dbt, etc.)
- Entry point: `SnapshotFactory.create_snapshot(raw_metadata: Dict)`
- Adapters: `datashark/ingestion/looker/adapter.py:41` (LookerAdapter.ingest)

**Outputs:**
- Consumed by Planner via `AirGapAPI` (read-only interface)
- Consumed by SQLBuilder for join resolution (`datashark/core/sql/builder.py:65`)
- Referenced by SnapshotID (SHA-256 hash) throughout system

**Persistence:**
- ✅ **NOW PERSISTED** via `SnapshotStore` (CAS implementation complete)
- SnapshotID (hash) is persisted in audit logs
- `SnapshotStore.save()` writes SemanticSnapshot to `<SNAPSHOT_DIR>/<snapshot_id>.json`
- `SnapshotStore.load()` retrieves SemanticSnapshot by hash
- Legacy JSONStore persists nodes/edges/manifest (separate system, not used by Safety Kernel)

**Versioning:**
- **SnapshotID** (`datashark-mcp/src/datashark_mcp/kernel/types.py:32`): SHA-256 hash of serialized snapshot contents
- Hash computed in `SnapshotFactory.create_snapshot()`: `json.dumps(raw_metadata, sort_keys=True)` → SHA-256
- Same metadata → same hash (deterministic)

**Determinism:**
- **PASS (with caveats):**
  - Hash computation uses `sort_keys=True` for stable ordering
  - Immutable model (`frozen=True`)
  - Hash is deterministic
- **CAVEAT:** No evidence of timestamp normalization or randomness control in raw_metadata before hashing

**Auditability:**
- SnapshotID included in audit records (`datashark/core/audit.py:39`)
- Audit records include `snapshot_id`, `input_query`, `generated_sql`
- **GAP:** No explicit provenance metadata in SemanticSnapshot itself (source_system, source_version exist but no extraction timestamp/commit)

---

### Candidate #2: Planner Output Dictionary (INTERMEDIATE REPRESENTATION)

**Artifact Name:** Planner Output (conforms to PLANNER_IO_CONTRACT)

**Where it lives:**
- **Generated:** `datashark-mcp/src/datashark_mcp/planner/planner.py:54` (Planner.plan_and_build_sql)
- **Structure:** Dictionary with keys: `reasoning_steps`, `concept_map`, `join_path`, `grain_context`, `policy_context`, `sql_template`, `final_sql_output`

**Format:**
- Python dictionary (not a formal class/model)
- Conforms to PLANNER_IO_CONTRACT schema (referenced in docstrings, not validated)

**Inputs:**
- `query_input` (natural language string)
- `user_context` (dict with user_id, roles, tenant_id)
- `active_snapshot_id` (SHA-256 string)
- ProjectedGraph (via AirGapAPI)

**Outputs:**
- Consumed by SQLBuilder (`datashark/core/sql/builder.py:65`)
- Logged to audit artifacts (`datashark/core/audit.py`)

**Persistence:**
- **NOT persisted** as structured artifact
- Only `final_sql_output` is logged in audit records
- `sql_template` is generated but not separately persisted

**Versioning:**
- **NO explicit versioning**
- No hash/fingerprint computed for planner output

**Determinism:**
- **PARTIAL:**
  - Planner contract states "same inputs → same outputs"
  - No explicit randomness control (no seeds, no time-based fields in planner itself)
  - **GAP:** ConceptMapper uses regex/string matching (deterministic) but no explicit seed control
  - **GAP:** JoinPlanner uses Dijkstra (deterministic) but tie-breaking not specified

**Auditability:**
- `reasoning_steps` list provides trace
- `active_snapshot_id` links to snapshot
- **GAP:** No explicit provenance for planner decisions (which concepts matched, why join path chosen)

---

### Candidate #3: ProjectedGraph (SECURITY BOUNDARY ARTIFACT)

**Artifact Name:** `ProjectedGraph`

**Where it lives:**
- **Type Definition:** `datashark-mcp/src/datashark_mcp/kernel/types.py:100`
- **Creation:** `datashark-mcp/src/datashark_mcp/security/graph_projector.py:38` (GraphProjector.project_graph)

**Format:**
- Pydantic BaseModel with `frozen=True` (immutable)
- Contains filtered `raw_data` dict (deep copy of SemanticGraph)

**Inputs:**
- SemanticGraph (full graph)
- UserContext (user_id, roles, tenant_id)
- PolicySet (rules + default_action)

**Outputs:**
- Consumed by AirGapAPI (read-only interface for Planner)
- Planner never sees raw SemanticGraph, only ProjectedGraph

**Persistence:**
- **NOT persisted** (ephemeral, created per request)

**Versioning:**
- **NO versioning** (derived artifact, not versioned independently)

**Determinism:**
- **PASS:** Deep copy ensures no shared references
- **PASS:** Policy evaluation is deterministic (same user_context + policy → same projection)
- **GAP:** No hash/fingerprint for ProjectedGraph itself

**Auditability:**
- **GAP:** No explicit audit of what was filtered/removed
- Policy decisions not logged separately

---

### Candidate #4: Manifest (LEGACY INGESTION ARTIFACT)

**Artifact Name:** `Manifest` (IngestionManifest)

**Where it lives:**
- **Type Definition:** `datashark-mcp/src/datashark_mcp/_legacy/context/manifest.py:32`
- **Schema:** `datashark-mcp/src/datashark_mcp/schemas/manifest_schema.json`

**Format:**
- JSON schema-validated dictionary
- Contains: run_id, system, start_time, end_time, counts, versions, status, hash_summaries

**Inputs:**
- Generated during ingestion/extraction runs
- Written by JSONStore (`datashark-mcp/src/datashark_mcp/_legacy/context/store/json_store.py:141`)

**Outputs:**
- Referenced by ingestion tools
- **NOT consumed by Planner or SQLBuilder** (legacy artifact)

**Persistence:**
- **PERSISTED:** `manifest.json` in snapshot directories
- Atomic write via temp file + rename

**Versioning:**
- Contains `versions.schema_version` and `versions.extractor_version`
- Contains `hash_summaries.nodes_sha256` and `hash_summaries.edges_sha256`

**Determinism:**
- **PARTIAL:**
  - Hash summaries are deterministic (SHA-256 of nodes/edges)
  - **GAP:** `start_time` and `end_time` are timestamps (non-deterministic)
  - **GAP:** `run_id` may be UUID (non-deterministic)

**Auditability:**
- **PASS:** Contains provenance (system, source_path, extractor_version, extracted_at)
- Links to snapshot via hash summaries

---

### Candidate #5: SQL Template (STRUCTURED IR)

**Artifact Name:** `sql_template` (dictionary)

**Where it lives:**
- **Generated:** `datashark-mcp/src/datashark_mcp/planner/planner.py:245` (_build_sql_template)
- **Structure:** Dict with keys: `SELECT`, `FROM`, `JOIN`, `WHERE`, `GROUP_BY`

**Format:**
- Python dictionary (not a formal model)
- Structured representation before SQL string rendering

**Inputs:**
- `concept_map`, `join_path`, `grain_context`, `policy_context` from planner

**Outputs:**
- Consumed by SQLBuilder for final SQL rendering
- Included in planner output but not separately persisted

**Persistence:**
- **NOT persisted** (only in-memory, included in planner output dict)

**Versioning:**
- **NO versioning**

**Determinism:**
- **PASS:** Dictionary construction is deterministic (same inputs → same dict structure)
- **GAP:** No explicit ordering guarantees for JOIN list or WHERE predicates

**Auditability:**
- Included in planner output
- **GAP:** Not separately logged or diffable

---

## SECTION 2 — Determinism Checklist (Evidence-Based)

### Primary Candidate: SemanticSnapshot

#### Canonicalization
- **Status:** PASS (with evidence)
- **Evidence:**
  - Hash computation uses `json.dumps(raw_metadata, sort_keys=True, ensure_ascii=False)` (`datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:76`)
  - SnapshotID normalized to lowercase (`datashark-mcp/src/datashark_mcp/kernel/types.py:67`)
  - Entity/Field IDs computed deterministically (`datashark-mcp/src/datashark_mcp/_legacy/context/id_utils.py:44`)
- **Code Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:74-89`
- **GAP:** No explicit normalization of timestamps or UUIDs in raw_metadata before hashing

#### Hashing/Fingerprints
- **Status:** PASS
- **Evidence:**
  - SHA-256 hash computed: `hashlib.sha256(serialized_metadata.encode('utf-8')).hexdigest()` (`datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:84-85`)
  - Hash is 64-character hex string, validated by SnapshotID model (`datashark-mcp/src/datashark_mcp/kernel/types.py:47-67`)
- **Code Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:82-89`
- **GAP:** No content-addressable storage (snapshot not retrievable by hash alone)

#### Provenance
- **Status:** PARTIAL
- **Evidence:**
  - SemanticSnapshot contains `source_system` and `source_version` (`datashark/core/types.py:135-136`)
  - Legacy Manifest contains `provenance` with system, source_path, extractor_version, extracted_at (`datashark-mcp/src/datashark_mcp/schemas/graph_schema.json:5-16`)
- **Code Location:** `datashark/core/types.py:134-140`
- **GAP:** SemanticSnapshot has no extraction timestamp or source commit hash
- **GAP:** No link between SemanticSnapshot and Manifest in current architecture

#### Diffability
- **Status:** UNKNOWN
- **Evidence:**
  - No explicit diff tool or function found
  - Snapshots are immutable (frozen=True) but no comparison utilities
- **Code Location:** N/A (not implemented)
- **GAP:** Cannot meaningfully diff two SemanticSnapshot instances

#### Reproducibility
- **Status:** PASS (theoretical)
- **Evidence:**
  - Same raw_metadata → same hash (deterministic serialization)
  - Immutable model ensures no mutation
- **Code Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:74-89`
- **GAP:** No test evidence of reproducibility (no golden snapshot tests found)

#### Randomness Control
- **Status:** FAIL
- **Evidence:**
  - No explicit seed setting in SnapshotFactory
  - No timestamp normalization in raw_metadata before hashing
  - No UUID normalization
- **Code Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py`
- **GAP:** If raw_metadata contains timestamps or UUIDs, hash will differ across runs

---

### Secondary Candidate: Planner Output Dictionary

#### Canonicalization
- **Status:** PARTIAL
- **Evidence:**
  - `concept_map` uses lists (ordering not guaranteed)
  - `join_path` is list of tuples (ordering matters, but no explicit sort)
  - `sql_template` uses dict (Python 3.7+ preserves insertion order)
- **Code Location:** `datashark-mcp/src/datashark_mcp/planner/planner.py:159-189`
- **GAP:** No explicit ordering guarantees for concept_map lists

#### Hashing/Fingerprints
- **Status:** FAIL
- **Evidence:**
  - No hash computed for planner output
  - Only `final_sql_output` is logged, not intermediate planner state
- **Code Location:** N/A (not implemented)

#### Provenance
- **Status:** PARTIAL
- **Evidence:**
  - `reasoning_steps` provides trace
  - `active_snapshot_id` links to snapshot
- **Code Location:** `datashark-mcp/src/datashark_mcp/planner/planner.py:95-189`
- **GAP:** No explicit provenance for concept mapping decisions or join path selection

#### Diffability
- **Status:** UNKNOWN
- **Evidence:**
  - Dictionary structure is diffable (JSON serializable)
  - No explicit diff tool found
- **Code Location:** N/A (not implemented)

#### Reproducibility
- **Status:** UNKNOWN (contract claims determinism, no test evidence)
- **Evidence:**
  - Planner contract states "same inputs → same outputs" (`datashark-mcp/src/datashark_mcp/planner/planner.py:33,68`)
  - No explicit randomness control (no seeds)
- **Code Location:** `datashark-mcp/src/datashark_mcp/planner/planner.py:54-189`
- **GAP:** No test evidence of reproducibility

#### Randomness Control
- **Status:** PASS (no randomness found)
- **Evidence:**
  - ConceptMapper uses regex/string matching (deterministic)
  - JoinPlanner uses Dijkstra algorithm (deterministic)
  - No `random`, `uuid`, or `time.time()` calls in planner code
- **Code Location:** `datashark-mcp/src/datashark_mcp/planner/` (grep results show no randomness)

---

## SECTION 3 — Planner / IR Layer Validation

### Intermediate Representation (IR) Existence

**Status:** YES (informal dictionary structure, not formal IR class)

**Where defined:**
- **Planner Output Dictionary:** `datashark-mcp/src/datashark_mcp/planner/planner.py:179-189`
- **SQL Template Dictionary:** `datashark-mcp/src/datashark_mcp/planner/planner.py:245-338`
- **PlannerPlan Dataclass:** `datashark-mcp/src/datashark_mcp/planner/__init__.py:28` (defined but not actively used)

**IR Fields:**
1. **reasoning_steps** (list[str]): Sequence of planning decisions
2. **concept_map** (dict): Mapped entities, metrics, filters, dimensions
3. **join_path** (list[tuple]): Multi-hop join path [(source_entity, target_entity, join_key)]
4. **grain_context** (dict): Grain ID, grouping fields, aggregation flags
5. **policy_context** (dict): Resolved RLS/CLS predicates, policy IDs
6. **sql_template** (dict): Structured SQL representation (SELECT, FROM, JOIN, WHERE, GROUP_BY)
7. **final_sql_output** (str): Rendered SQL string

**First Point of Probabilistic Decisions:**
- **Location:** `datashark-mcp/src/datashark_mcp/planner/mapper/concept_mapper.py:45` (ConceptMapper.map_query_to_concepts)
- **Evidence:** Uses regex/string matching (deterministic), but no explicit seed control
- **GAP:** If multiple entities match a term, selection order not guaranteed (Python dict iteration order is stable but not explicitly controlled)

### End-to-End Flow

**Call Chain Diagram:**

```
User Query (NL string)
  ↓
DataSharkEngine.process_request(intent: str)
  ├─> DataSharkEngine.get_api_client()
  │   ├─> GraphProjector.project_graph(SemanticGraph, UserContext, PolicySet)
  │   │   └─> Returns ProjectedGraph (filtered view)
  │   └─> AirGapAPI(ProjectedGraph)
  │       └─> Returns read-only API interface
  ├─> Planner(AirGapAPI)
  └─> Planner.plan_and_build_sql(query_input, user_context, active_snapshot_id)
      ├─> ConceptMapper.map_query_to_concepts(query_input)
      │   └─> Returns concept_map: {entities, metrics, filters, dimensions}
      ├─> GrainResolver.resolve_final_grain(required_entity_ids)
      │   └─> Returns grain_context: {grain_id, grouping_fields, aggregation_required}
      ├─> JoinPlanner.infer_join_path(start_entity_id, target_entity_id)
      │   └─> Returns join_path: [(source, target, join_key), ...]
      ├─> Planner._resolve_policy_context(user_context)
      │   └─> Returns policy_context: {resolved_predicates, policy_ids}
      ├─> Planner._build_sql_template(final_plan)
      │   └─> Returns sql_template: {SELECT, FROM, JOIN, WHERE, GROUP_BY}
      └─> SQLBuilder.build_final_sql(planner_output)
          └─> Returns final_sql_output: "SELECT ... FROM ... WHERE ..."
```

**File:Function Mapping:**
- `datashark-mcp/src/datashark_mcp/kernel/engine.py:107` → `process_request()`
- `datashark-mcp/src/datashark_mcp/kernel/engine.py:70` → `get_api_client()`
- `datashark-mcp/src/datashark_mcp/security/graph_projector.py:38` → `project_graph()`
- `datashark-mcp/src/datashark_mcp/kernel/air_gap_api.py:28` → `__init__()`
- `datashark-mcp/src/datashark_mcp/planner/planner.py:39` → `__init__()`
- `datashark-mcp/src/datashark_mcp/planner/planner.py:54` → `plan_and_build_sql()`
- `datashark-mcp/src/datashark_mcp/planner/mapper/concept_mapper.py:45` → `map_query_to_concepts()`
- `datashark-mcp/src/datashark_mcp/planner/grain/grain_resolver.py:66` → `resolve_final_grain()`
- `datashark-mcp/src/datashark_mcp/planner/join/join_planner.py:39` → `infer_join_path()`
- `datashark-mcp/src/datashark_mcp/planner/planner.py:191` → `_resolve_policy_context()`
- `datashark-mcp/src/datashark_mcp/planner/planner.py:245` → `_build_sql_template()`
- `datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:30` → `build_final_sql()`

**Gap Analysis:**
- **IR is informal:** Dictionary structure, not a formal model/class
- **No IR validation:** No schema validation for planner output
- **No IR persistence:** IR exists only in-memory, not persisted separately
- **IR → SQL is deterministic:** SQLBuilder uses structured inputs, no randomness

---

## SECTION 4 — Governance & Safety Enforcement Layer

### Connection/Auth (IAM)

**Where implemented:**
- **Connection Pool:** `datashark-mcp/src/datashark_mcp/connection/pool.py:11` (ConnectionPool)
- **Session Manager:** `datashark-mcp/src/datashark_mcp/connection/session_manager.py:18` (Session)
- **Config Loading:** `core/connection_manager.py` (RedshiftConnectionManager)

**Enforcement Boundary:**
- **BEFORE plan:** Connection established at server initialization
- **BEFORE SQL execution:** Connection pool validates credentials
- **Evidence:** `datashark-mcp/src/datashark_mcp/connection/pool.py:108-126` (connection test on init)

**GAP:** No explicit IAM policy evaluation (no role-based connection restrictions)

---

### Secrets Handling (Redaction)

**Where implemented:**
- **Secret Detection:** `datashark-mcp/src/datashark_mcp/_legacy/context/security.py:55` (validate_no_secrets)
- **Redaction Patterns:** `datashark-mcp/src/datashark_mcp/_legacy/context/security.py:19-29` (SECRET_PATTERNS)

**Enforcement Boundary:**
- **UNKNOWN:** No explicit redaction in audit logs found
- **Evidence:** `datashark/core/audit.py:31-67` (AuditRecord) — no redaction logic
- **GAP:** Audit records may contain raw SQL with embedded values (no redaction)

**Code Location:**
- `datashark-mcp/src/datashark_mcp/_legacy/context/security.py:55-75`

---

### Policy Gates (RLS/CLS, Allow/Deny Fields, Masking)

**Where implemented:**
- **Policy Evaluation:** `datashark-mcp/src/datashark_mcp/planner/planner.py:191` (_resolve_policy_context)
- **Graph Projection:** `datashark-mcp/src/datashark_mcp/security/graph_projector.py:38` (project_graph)
- **Policy Rules:** `datashark-mcp/src/datashark_mcp/security/policy.py:12` (PolicyRule, PolicySet)

**Enforcement Boundary:**
- **BEFORE plan:** GraphProjector filters SemanticGraph → ProjectedGraph (air gap)
- **DURING plan:** Policy predicates resolved and included in planner output
- **BEFORE SQL:** Policy predicates injected into WHERE clause (`datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:261-264`)

**Evidence:**
- `datashark-mcp/src/datashark_mcp/security/graph_projector.py:38-132` (physical removal of denied resources)
- `datashark-mcp/src/datashark_mcp/planner/planner.py:191-243` (policy context resolution)
- `datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:261-277` (mandatory policy predicate injection)

**GAP:** Policy resolution is mock implementation (`_resolve_policy_context` returns hardcoded predicates)

---

### Query Parameterization / Injection Safety

**Where implemented:**
- **SQL Builder:** `datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:241-259` (builds SQL with string interpolation)
- **Query Validator:** `datashark-mcp/src/datashark_mcp/safety/query_validator.py:42` (validates SQL before execution)
- **Query Executor:** `datashark-mcp/src/datashark/core/server.py:516` (_execute_query_safe)

**Enforcement Boundary:**
- **BEFORE SQL execution:** QueryValidator blocks dangerous keywords (`datashark-mcp/src/datashark_mcp/safety/query_validator.py:82`)
- **DURING SQL execution:** `cursor.execute(sql)` — **NO PARAMETER BINDING** (`datashark-mcp/src/datashark/core/server.py:548`)

**Evidence:**
- SQLBuilder uses f-strings: `f"{column_ref} = '{value}'"` (`datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:251`)
- QueryValidator blocks DELETE/DROP/INSERT (`datashark-mcp/src/datashark_mcp/safety/query_validator.py:33-36`)
- **CRITICAL GAP:** No parameter binding in execution (`datashark-mcp/src/datashark/core/server.py:548` uses `cursor.execute(sql)` not `cursor.execute(sql, params)`)

**Code Locations:**
- `datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:241-259` (SQL construction)
- `datashark-mcp/src/datashark_mcp/safety/query_validator.py:42-90` (validation)
- `datashark-mcp/src/datashark/core/server.py:516-560` (execution)

---

### Audit Logging

**Where implemented:**
- **Audit Writer:** `datashark-mcp/src/datashark/core/audit.py:70` (AuditWriter)
- **Artifact Logger:** `datashark-mcp/src/datashark/core/audit.py:197` (log_artifact)
- **Engine Integration:** `datashark-mcp/src/datashark_mcp/kernel/engine.py:159` (logs after process_request)

**Enforcement Boundary:**
- **AFTER SQL generation:** Audit record written with input_query, snapshot_id, generated_sql
- **Fail-open:** Errors don't block SQL generation (`datashark/core/audit.py:230-232`)

**Evidence:**
- `datashark-mcp/src/datashark/core/audit.py:31-67` (AuditRecord schema)
- `datashark-mcp/src/datashark/core/audit.py:100-180` (AuditWriter.write_record)
- `datashark-mcp/src/datashark_mcp/kernel/engine.py:159-172` (engine-level logging)

**GAP:** No redaction of secrets in audit logs (SQL may contain embedded values)

---

## SECTION 5 — MVP "Proof of Midpoint" Definition (Architecture-Level)

### Minimal Artifact(s) That Must Exist

1. **SemanticSnapshot** (PRIMARY)
   - **Status:** EXISTS (`datashark/core/types.py:114`)
   - **Gap:** Not persisted/retrievable by hash
   - **Gap:** No explicit timestamp normalization

2. **SnapshotID** (Hash Identifier)
   - **Status:** EXISTS (`datashark-mcp/src/datashark_mcp/kernel/types.py:32`)
   - **Gap:** No content-addressable storage

3. **Planner Output Dictionary** (IR)
   - **Status:** EXISTS (informal structure)
   - **Gap:** Not a formal model, not persisted

### Minimal API Surfaces

**Required APIs:**
1. **build_snapshot** (Ingestion → SemanticSnapshot)
   - **Status:** EXISTS (`SnapshotFactory.create_snapshot`)
   - **Location:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:38`

2. **plan_query** (Query + Snapshot → Planner Output)
   - **Status:** EXISTS (`Planner.plan_and_build_sql`)
   - **Location:** `datashark-mcp/src/datashark_mcp/planner/planner.py:54`

3. **render_sql** (Planner Output → SQL String)
   - **Status:** EXISTS (`SQLBuilder.build_final_sql`)
   - **Location:** `datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:30`

4. **execute_with_audit** (SQL → Results + Audit Record)
   - **Status:** PARTIAL (execution exists, audit exists, not unified)
   - **Location:** `datashark-mcp/src/datashark/core/server.py:516` (execution) + `datashark/core/audit.py:197` (audit)

### Minimal Determinism Tests

**Required Tests:**
1. **Same input → identical snapshot hash**
   - **Status:** NOT FOUND (no test evidence)
   - **Gap:** No golden snapshot determinism test

2. **Identical plan** (same query + snapshot → same planner output)
   - **Status:** NOT FOUND (no test evidence)
   - **Gap:** No planner output determinism test

3. **SQL stable** (same planner output → same SQL string)
   - **Status:** NOT FOUND (no test evidence)
   - **Gap:** No SQL builder determinism test

**Existing Tests:**
- `tests/integration/test_golden_snapshot.py:22` (test_golden_snapshot_determinism) — tests ingestion determinism, not snapshot hash
- `datashark-mcp/tests/test_golden_harness.py` — tests SQL output against baselines, not determinism

### Minimal Audit Proof

**Required Audit Trail:**
1. **Plan includes trace + policy decision**
   - **Status:** PARTIAL
   - **Evidence:** `reasoning_steps` and `policy_context` exist in planner output
   - **Gap:** Not persisted separately, only in-memory

2. **Audit record links to snapshot_id**
   - **Status:** PASS
   - **Evidence:** `AuditRecord.snapshot_id` (`datashark/core/audit.py:39`)

3. **Audit record includes input_query and generated_sql**
   - **Status:** PASS
   - **Evidence:** `AuditRecord.input_query` and `AuditRecord.generated_sql` (`datashark/core/audit.py:40-41`)

**Gap:** No audit record of planner intermediate state (concept_map, join_path, etc.)

---

## SECTION 6 — Gaps & Risks (Ranked)

### Gap #1: No Content-Addressable Storage for Snapshots
- **Severity:** CRITICAL
- **Why it blocks:** Cannot retrieve snapshot by hash, cannot verify snapshot integrity, cannot share snapshots
- **Where in code:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py` creates snapshots but doesn't persist them
- **Type:** Missing abstraction

### Gap #2: No Parameter Binding in SQL Execution
- **Severity:** CRITICAL
- **Why it blocks:** SQL injection risk, values embedded in SQL strings
- **Where in code:** `datashark-mcp/src/datashark/core/server.py:548` uses `cursor.execute(sql)` not `cursor.execute(sql, params)`
- **Type:** Implementation bug

### Gap #3: No Timestamp/UUID Normalization in Snapshot Hashing
- **Severity:** HIGH
- **Why it blocks:** Same logical snapshot may produce different hashes if metadata contains timestamps
- **Where in code:** `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:74-89` (no normalization before hashing)
- **Type:** Implementation bug

### Gap #4: Planner Output Not Persisted or Versioned
- **Severity:** HIGH
- **Why it blocks:** Cannot audit planning decisions, cannot diff plans, cannot reproduce planning state
- **Where in code:** `datashark-mcp/src/datashark_mcp/planner/planner.py:179-189` (returns dict, not persisted)
- **Type:** Missing abstraction

### Gap #5: No Formal IR Model (Dictionary Only)
- **Severity:** MEDIUM
- **Why it blocks:** No schema validation, no type safety, no explicit versioning
- **Where in code:** `datashark-mcp/src/datashark_mcp/planner/planner.py:179` (returns Dict[str, Any])
- **Type:** Missing abstraction

### Gap #6: Policy Resolution is Mock
- **Severity:** MEDIUM
- **Why it blocks:** RLS/CLS predicates are hardcoded, not evaluated against real policy engine
- **Where in code:** `datashark-mcp/src/datashark_mcp/planner/planner.py:191-243` (_resolve_policy_context)
- **Type:** Implementation bug (stub not replaced)

### Gap #7: No Secrets Redaction in Audit Logs
- **Severity:** MEDIUM
- **Why it blocks:** Audit logs may contain sensitive data (SQL with embedded values)
- **Where in code:** `datashark-mcp/src/datashark/core/audit.py:31-67` (AuditRecord, no redaction)
- **Type:** Implementation bug

### Gap #8: No Explicit Ordering Guarantees for Concept Maps
- **Severity:** MEDIUM
- **Why it blocks:** Concept map lists may have non-deterministic ordering, affecting reproducibility
- **Where in code:** `datashark-mcp/src/datashark_mcp/planner/mapper/concept_mapper.py:45` (returns lists)
- **Type:** Implementation bug

### Gap #9: No Diff Tool for Snapshots or Plans
- **Severity:** LOW
- **Why it blocks:** Cannot meaningfully compare versions, debugging harder
- **Where in code:** N/A (not implemented)
- **Type:** Missing abstraction

### Gap #10: No Provenance Metadata in SemanticSnapshot
- **Severity:** LOW
- **Why it blocks:** Cannot trace snapshot origin (extraction time, source commit) for audit
- **Where in code:** `datashark/core/types.py:114` (SemanticSnapshot has source_system/version but no timestamp/commit)
- **Type:** Missing abstraction

---

## SECTION 7 — Appendix: Code Pointers

### Snapshot/Manifest/Schema
1. `datashark-mcp/src/datashark/core/types.py:114` — SemanticSnapshot definition
2. `datashark-mcp/src/datashark_mcp/kernel/types.py:32` — SnapshotID, SemanticGraph, ProjectedGraph
3. `datashark-mcp/src/datashark_mcp/kernel/snapshot_factory.py:24` — SnapshotFactory (ingestion entry point)
4. `datashark-mcp/src/datashark_mcp/schemas/graph_schema.json` — Graph schema (Node/Edge)
5. `datashark-mcp/src/datashark_mcp/schemas/manifest_schema.json` — Manifest schema
6. `datashark-mcp/src/datashark_mcp/_legacy/context/manifest.py:32` — Manifest class
7. `datashark-mcp/src/datashark_mcp/_legacy/context/store/json_store.py:19` — JSONStore (persistence)

### Planner/IR
8. `datashark-mcp/src/datashark_mcp/planner/planner.py:20` — Planner class (orchestration)
9. `datashark-mcp/src/datashark_mcp/planner/planner.py:245` — _build_sql_template (IR generation)
10. `datashark-mcp/src/datashark_mcp/planner/mapper/concept_mapper.py:17` — ConceptMapper
11. `datashark-mcp/src/datashark_mcp/planner/join/join_planner.py:17` — JoinPlanner
12. `datashark-mcp/src/datashark_mcp/planner/grain/grain_resolver.py:54` — GrainResolver
13. `datashark-mcp/src/datashark_mcp/planner/__init__.py:28` — PlannerPlan dataclass (unused)

### SQL Builder/Executor
14. `datashark-mcp/src/datashark_mcp/planner/sql/sql_builder.py:14` — SQLBuilder (planner output → SQL)
15. `datashark-mcp/src/datashark/core/sql/builder.py:29` — SQLBuilder (snapshot-aware, legacy)
16. `datashark-mcp/src/datashark/core/sql/dialects.py` — SQL dialect implementations
17. `datashark-mcp/src/datashark/core/server.py:516` — _execute_query_safe (execution)
18. `core/query_executor.py:13` — QueryExecutor (pandas interface)

### Policy/Auth/Audit
19. `datashark-mcp/src/datashark_mcp/security/policy.py:12` — PolicyRule, PolicySet
20. `datashark-mcp/src/datashark_mcp/security/graph_projector.py:20` — GraphProjector (air gap)
21. `datashark-mcp/src/datashark_mcp/kernel/air_gap_api.py:15` — AirGapAPI (read-only interface)
22. `datashark-mcp/src/datashark_mcp/safety/query_validator.py:17` — QueryValidator (SQL safety)
23. `datashark-mcp/src/datashark/core/audit.py:31` — AuditRecord, AuditWriter
24. `datashark-mcp/src/datashark_mcp/kernel/engine.py:23` — DataSharkEngine (orchestration)

### Determinism Utilities
25. `datashark-mcp/src/datashark_mcp/_legacy/context/id_utils.py:44` — compute_node_id, compute_edge_id
26. `datashark-mcp/src/datashark_mcp/_legacy/context/determinism.py` — Timestamp normalization, hash utilities

---

## EXECUTIVE SUMMARY

**Primary Midpoint Artifact:** `SemanticSnapshot` (with `SnapshotID` as hash identifier)

**Determinism Status:** PARTIALLY IMPLEMENTED
- ✅ Hash computation is deterministic (SHA-256 with sorted keys)
- ✅ Immutable model (frozen=True)
- ❌ No timestamp/UUID normalization before hashing
- ❌ No content-addressable storage
- ❌ No explicit reproducibility tests

**IR Layer Status:** INFORMAL
- ✅ Planner output dictionary exists with structured fields
- ❌ Not a formal model (no schema validation)
- ❌ Not persisted or versioned
- ✅ No randomness in planner code (deterministic algorithms)

**Governance Status:** PARTIALLY IMPLEMENTED
- ✅ Air gap enforced (ProjectedGraph)
- ✅ Policy predicates injected into SQL
- ❌ Policy resolution is mock
- ❌ No parameter binding (SQL injection risk)
- ❌ No secrets redaction in audit logs

**MVP Proof Status:** INCOMPLETE
- ✅ Core artifacts exist
- ❌ No explicit determinism tests (same input → same hash/SQL)
- ❌ No content-addressable snapshot storage
- ✅ Audit logging exists but incomplete (no planner state)

**Conclusion:** The architecture has the **structural foundation** for a deterministic midpoint (SemanticSnapshot + Planner IR), but **critical gaps** prevent it from being fully deterministic and auditable in practice.
