# CC Handoff — Track 1: Foundation + Doctor + Health Tool + Advertising
**Priority:** BLOCKING — must complete before publish  
**Model:** Opus or Sonnet · max effort  
**Estimated time:** ~90-120 min  
**File ownership:** `connections.py` (new), `doctor.py` (new), `server.py`, `test_advertising.py`, `test_doctor.py` (new), `test_connections.py` (new)  
**Does NOT touch:** `init_wizard.py`, `test_init.py`, `test_cli_smoke.py` (those belong to Track 2)

---

## Context

Cross-platform testing exposed a lifecycle gap: Boyce has no persistent awareness of its environment. DSNs die with the process, schema drift is poorly surfaced, and there's no agent-invokable diagnostic. This track builds the infrastructure layer.

Read these before starting:
- `_strategy/MASTER.md` — current priorities
- `CLAUDE.md` — architecture, advertising layer schema
- This handoff

---

## Block 1: DSN Persistence (`connections.py`)

**New file:** `boyce/src/boyce/connections.py`

A thin read/write layer over `_local_context/connections.json`.

```python
class ConnectionStore:
    def __init__(self, context_dir: Path):
        self._path = context_dir / "connections.json"
    
    def save(self, snapshot_name: str, dsn: str, source: str = "ingest_source") -> None:
        """Write or update a DSN entry. Redact password in stored DSN."""
    
    def load(self, snapshot_name: str) -> Optional[str]:
        """Return raw DSN string for a snapshot, or None."""
    
    def touch(self, snapshot_name: str) -> None:
        """Update last_used timestamp."""
    
    def list_all(self) -> Dict[str, dict]:
        """Return all stored connections (DSN redacted for display)."""
    
    def remove(self, snapshot_name: str) -> bool:
        """Remove a connection entry. Returns True if existed."""
```

**Integration into `server.py`:**

1. Instantiate `_connections = ConnectionStore(_LOCAL_CONTEXT)` alongside `_store` and `_definitions`.
2. In `ingest_source`, when a live PostgreSQL DSN is accepted, call `_connections.save(snapshot_name, source_path)` after successful ingestion.
3. In `_get_adapter()`, add fallback chain:
   ```python
   db_url = os.environ.get("BOYCE_DB_URL", "") or _ingest_db_url
   if not db_url:
       db_url = _connections.load(snapshot_name) or ""  # persistent fallback
   if not db_url:
       raise RuntimeError(...)
   ```
   Note: `_get_adapter()` currently doesn't take `snapshot_name`. Either add it as a param with default `"default"`, or read the most-recently-used entry. Prefer adding the param — it threads through `query_database` and `profile_data` already.
4. On successful adapter connection, call `_connections.touch(snapshot_name)`.

**Tests:** `tests/test_connections.py` — save/load/touch/remove/list_all, file creation on first write, concurrent access safety (file locking not required but handle missing file gracefully).

---

## Block 2: `boyce doctor` CLI + Check Functions

**New file:** `boyce/src/boyce/doctor.py`

Five check functions, each returning a structured dict:

### `check_editors() -> dict`
- Reuse `detect_hosts()` from `init_wizard.py` (import it)
- For each host: detected (bool), configured (bool = has_boyce), config_path
- Status: "ok" if all detected editors are configured, "warning" if any detected but not configured
- Each warning item includes `"fix": "boyce init"`

### `check_database(connections: ConnectionStore) -> dict`
- Load all entries from `connections.json`
- For each: attempt a lightweight `SELECT 1` via asyncpg (or report "asyncpg not installed")
- Status: "ok" if all connected, "warning" if any unreachable, "error" if all fail
- Each failure includes `"fix": "boyce init --db-url <dsn>"` or `"ingest_source with current DSN"`

### `check_snapshots(store: SnapshotStore, connections: ConnectionStore) -> dict`
- List all snapshots in `_local_context/`
- For each: entity count, field count, join count, age
- If a connection exists for the snapshot, run drift detection (reuse `_check_db_drift` logic from server.py — extract into a shared function)
- Status: "warning" if drift detected, "ok" otherwise
- Drift items include `"fix": "ingest_source(snapshot_name='...')"`

### `check_sources() -> dict`
- Run lightweight discovery scan (reuse `discover_sources` from `discovery.py`)
- For each discovered source, check if a matching snapshot exists
- Status: "info" if un-ingested sources found (not a warning — they might be intentionally skipped)
- Each item includes `"fix": "boyce scan"`

### `check_server() -> dict`
- Boyce version (from package metadata)
- asyncpg installed (bool)
- `_local_context/` exists and snapshot count
- `boyce` command resolvable (reuse `_resolve_boyce_command` from init_wizard.py)
- Status: "ok" or "error" if critical components missing

### Top-level orchestrator

```python
async def run_doctor(json_output: bool = False) -> int:
    """Run all checks, print results, return exit code (0/1/2)."""
    results = {
        "version": get_version(),
        "checks": {
            "editors": check_editors(),
            "database": await check_database(...),
            "snapshots": await check_snapshots(...),
            "sources": check_sources(),
            "server": check_server(),
        },
        "suggestions": [],  # aggregated from all checks
    }
    # Aggregate suggestions from all check items with "fix" keys
    # Determine overall status and exit_code
    # Print human-readable or JSON based on flag
    return exit_code
```

### CLI integration

In `cli.py`, add `doctor` subcommand:
```
boyce doctor [--json]
```

Exit codes: 0 = all ok, 1 = warnings, 2 = errors.

**Tests:** `tests/test_doctor.py` — unit test each check function with mocked filesystem/DB. Test JSON output parsing. Test exit code semantics.

---

## Block 3: `check_health` MCP Tool

**In `server.py`, add a new MCP tool:**

```python
@mcp.tool()
async def check_health(snapshot_name: str = "default") -> str:
    """
    Check Boyce's operational health — database connectivity, snapshot
    freshness, and schema drift.

    Call this when a query fails unexpectedly, when you suspect stale
    data, or when Boyce suggests running a health check. Returns
    actionable diagnostics with specific fix commands.

    **Use this before debugging query failures yourself.** A failed
    EXPLAIN or missing table often means the snapshot is stale, not
    that your SQL is wrong.

    Args:
        snapshot_name: Snapshot to check health for. Defaults to "default".

    Returns:
        JSON string with keys:
            status      — "ok", "warnings", or "errors"
            database    — connection health check result
            snapshot    — freshness and drift check result  
            server      — component availability
            suggestions — list of actionable fix commands
    """
```

This wraps `check_database`, `check_snapshots`, and `check_server` from `doctor.py`. It does NOT include `check_editors` or `check_sources` (those are filesystem/CLI concerns the MCP server can't act on).

The tool description follows the behavioral framework:
- First sentence is an ad ("Check Boyce's operational health")
- Body is peer-to-peer ("Call this when a query fails unexpectedly")
- Last block is directive ("Use this before debugging query failures yourself")

**Advertising layer for check_health:**
- `next_step`: points to the suggested fix action (e.g., "Call ingest_source to refresh snapshot 'pagila'")
- `present_to_user`: surfaces the most critical finding
- `data_reality`: null (not SQL-related)

---

## Block 4: `environment_suggestions` in Advertising Layer

**In `server.py`, modify `_build_advertising_layer()`:**

Add `environment_suggestions` as an optional field, populated on first tool call per session.

```python
# Module-level flag
_environment_checked: bool = False

def _check_environment_suggestions(snapshot_name: str) -> List[str]:
    """
    Lightweight first-call-per-session environment check.
    Returns list of actionable suggestion strings (max 3).
    """
    global _environment_checked
    if _environment_checked:
        return []
    _environment_checked = True
    
    suggestions = []
    
    # 1. Snapshot drift (reuse existing drift check)
    # 2. Connection health (quick SELECT 1)
    # 3. Read environment.json for stale doctor check
    
    return suggestions[:3]  # noise fatigue protection
```

In `_build_advertising_layer()`, after existing logic:
```python
env_suggestions = _check_environment_suggestions(snapshot_name)
if env_suggestions:
    result["environment_suggestions"] = env_suggestions
```

**Update error messages in `_get_adapter()`:**

Current:
```python
raise RuntimeError("BOYCE_DB_URL environment variable is not set...")
```

New:
```python
raise RuntimeError(
    "No database connection available. "
    "Call check_health to diagnose, or call ingest_source "
    "with a PostgreSQL DSN to connect."
)
```

**`_local_context/environment.json`:**

Written by `boyce doctor` on completion (from Block 2). Read here for `last_doctor` timestamp. If >24h stale or missing, include "Run `boyce doctor` to check environment health" in suggestions.

**Documentation updates (this track owns):**
- `CLAUDE.md`: Add `check_health` to MCP Tools table, add `environment_suggestions` to advertising layer schema, add `connections.py` to Key Files table
- `test_advertising.py`: Add tests for `environment_suggestions` field — present when issues exist, absent on clean state, max 3 items, first-call-only behavior

---

## Verification Checklist

Before marking this track complete:

- [ ] `python boyce/tests/verify_eyes.py` passes
- [ ] `python -m pytest boyce/tests/ -v` passes (including new test files)
- [ ] `boyce doctor` runs clean on the dev environment
- [ ] `boyce doctor --json` returns valid parseable JSON
- [ ] `boyce doctor` exit code is 0 when healthy, 1 with warnings
- [ ] DSN persists: ingest a live DB, kill the server, restart, `query_database` still works
- [ ] `check_health` MCP tool is visible in tool list and returns valid JSON
- [ ] `environment_suggestions` appears on first tool call when drift exists, absent on second call
- [ ] CLAUDE.md updated with new tools, files, and schema
