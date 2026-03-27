# Implementation Details — `validate_sql` + Schema Freshness

**Parent:** `handoff-architecture-revision.md` Changes 5 and 9

---

## Part A: `validate_sql` Tool

### Location: `boyce/src/boyce/server.py`

### Full signature:
```python
@mcp.tool()
async def validate_sql(
    sql: str,
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
    """
    Validate a SQL query through Boyce's safety layer without executing it.

    Use this when you've written SQL directly (without a StructuredFilter) and
    want to check it before running. Returns pre-flight validation, Redshift
    compatibility warnings, and NULL risk analysis.

    This tool does NOT execute the query. Use `query_database` to run it after
    validation confirms it is safe.

    Args:
        sql: A SELECT statement to validate.
        snapshot_name: Name of a previously ingested snapshot (used for NULL risk
            analysis — matching WHERE clause columns against snapshot field metadata).
            Defaults to "default".
        dialect: Target SQL dialect for compatibility linting. Defaults to "redshift".
            Supported: "redshift", "postgres", "duckdb", "bigquery".

    Returns:
        JSON string with keys:

            sql               — the SQL as provided (echoed back)
            validation        — pre-flight EXPLAIN result:
                status        — "verified" | "invalid" | "unchecked"
                error         — Postgres error message if invalid, else null
                cost_estimate — planner cost if verified, else null
            compat_risks      — list of Redshift compatibility warnings (if any)
            null_risk_columns — list of columns in WHERE equality filters that are
                                nullable in the snapshot (potential NULL trap risk)
            snapshot_name     — snapshot used for NULL risk analysis
    """
```

### Implementation:
```python
    if not sql or not sql.strip():
        return json.dumps({
            "error": {"code": -32602, "message": "sql is required"}
        })

    logger.info("validate_sql called | sql=%r", sql[:200])

    # Stage 1: Redshift compat lint
    compat_risks = lint_redshift_compat(sql) if dialect == "redshift" else []

    # Stage 2: EXPLAIN pre-flight
    validation = await _preflight_check(sql)

    # Stage 3: Lightweight NULL risk scan
    null_risk_columns = _scan_null_risk(sql, snapshot_name)

    payload = {
        "sql": sql,
        "validation": validation,
        "snapshot_name": snapshot_name,
    }
    if compat_risks:
        payload["compat_risks"] = compat_risks
    if null_risk_columns:
        payload["null_risk_columns"] = null_risk_columns

    # Audit
    _audit.log_query(
        query="[validate_sql]",
        snapshot_name=snapshot_name,
        snapshot_id="",
        sql=sql,
        entities_resolved=[],
        validation_status=validation["status"],
    )

    return json.dumps(payload)
```

### `_scan_null_risk()` helper:
```python
import re

_EQUALITY_FILTER_RE = re.compile(
    r"""(\w+)\.(\w+)\s*=\s*'[^']*'"""    # table.column = 'value'
    r"""|(\w+)\s*=\s*'[^']*'""",           # column = 'value'
    re.IGNORECASE
)

def _scan_null_risk(sql: str, snapshot_name: str) -> List[Dict[str, Any]]:
    """
    Parse WHERE clause for equality filters and check if those columns
    are nullable in the snapshot.

    This is a lightweight heuristic — not a full SQL parser. It catches
    common patterns like `status = 'active'` and `orders.status = 'active'`.

    Returns list of dicts with keys: table, column, nullable, risk.
    """
    try:
        snapshot = _store.load(snapshot_name)
    except (FileNotFoundError, ValueError):
        return []

    risks = []
    for match in _EQUALITY_FILTER_RE.finditer(sql):
        if match.group(1) and match.group(2):
            # table.column pattern
            table_name = match.group(1)
            column_name = match.group(2)
        elif match.group(3):
            # bare column pattern
            table_name = None
            column_name = match.group(3)
        else:
            continue

        # Look up in snapshot
        for field_id, field in snapshot.fields.items():
            if field.name != column_name:
                continue
            if table_name:
                entity = snapshot.entities.get(field.entity_id)
                if entity and entity.name != table_name:
                    continue
            if field.nullable:
                entity = snapshot.entities.get(field.entity_id)
                entity_name = entity.name if entity else "unknown"
                risks.append({
                    "table": entity_name,
                    "column": column_name,
                    "nullable": True,
                    "risk": (
                        f"Column '{column_name}' is nullable. "
                        f"Equality filter (= 'value') silently excludes NULL rows."
                    ),
                })
            break  # found the column, move on

    return risks
```

### Tests for `validate_sql`:
Add to `boyce/tests/test_kernel_tools.py` or new `boyce/tests/test_validate_sql.py`:

1. `test_validate_sql_basic` — valid SQL, no DB → unchecked status, no errors
2. `test_validate_sql_empty` — empty SQL → error response
3. `test_validate_sql_compat_risks` — SQL with `CONCAT()` → compat risk returned
4. `test_validate_sql_null_risk` — SQL with `WHERE status = 'active'` against snapshot with nullable status → null_risk_columns populated
5. `test_validate_sql_no_snapshot` — invalid snapshot_name → empty null_risk_columns, no error

---

## Part B: Schema Freshness — Tier 2 (Session-Start Re-Validation)

### Location: `boyce/src/boyce/server.py`

### New helper function:
```python
import time

# Track which snapshots have been freshness-checked this session
_freshness_checked: set = set()


def _check_snapshot_freshness(snapshot_name: str) -> Optional[str]:
    """
    Check if a snapshot's source file has been modified since the snapshot was created.

    Returns a warning string if stale, None if fresh or unable to check.
    Only runs once per snapshot per server session.
    """
    if snapshot_name in _freshness_checked:
        return None
    _freshness_checked.add(snapshot_name)

    try:
        snapshot = _store.load(snapshot_name)
    except (FileNotFoundError, ValueError):
        return None

    source_path_str = snapshot.metadata.get("source_path")
    if not source_path_str:
        return None

    source_path = Path(source_path_str)
    if not source_path.exists():
        logger.warning(
            "Snapshot '%s' source file no longer exists: %s",
            snapshot_name, source_path,
        )
        return None  # Don't warn — file might have been moved intentionally

    # Compare source file mtime to snapshot file mtime
    snapshot_file = _LOCAL_CONTEXT / f"{snapshot_name}.json"
    if not snapshot_file.exists():
        return None

    source_mtime = source_path.stat().st_mtime
    snapshot_mtime = snapshot_file.stat().st_mtime

    if source_mtime > snapshot_mtime:
        age_seconds = source_mtime - snapshot_mtime
        age_human = (
            f"{int(age_seconds // 3600)}h {int((age_seconds % 3600) // 60)}m"
            if age_seconds > 3600
            else f"{int(age_seconds // 60)}m"
        )
        warning = (
            f"Source file '{source_path.name}' has been modified since snapshot "
            f"'{snapshot_name}' was created ({age_human} newer). "
            f"Run ingest_source to refresh."
        )
        logger.info("Snapshot freshness: %s", warning)

        # Auto re-ingest
        try:
            from .parsers import parse_from_path
            new_snapshot = parse_from_path(str(source_path))
            if new_snapshot.snapshot_id != snapshot.snapshot_id:
                _store.save(new_snapshot, snapshot_name)
                if new_snapshot.snapshot_id not in _graph.snapshots:
                    _graph.add_snapshot(new_snapshot)
                logger.info(
                    "Auto re-ingested '%s': snapshot_id changed %s → %s",
                    snapshot_name, snapshot.snapshot_id[:12], new_snapshot.snapshot_id[:12],
                )
                return (
                    f"Snapshot '{snapshot_name}' was auto-refreshed from "
                    f"'{source_path.name}' (source was modified)."
                )
            else:
                return None  # Source file changed but snapshot hash is the same
        except Exception as exc:
            logger.warning("Auto re-ingest failed for '%s': %s", snapshot_name, exc)
            return warning  # Return the stale warning since we couldn't auto-refresh

    return None
```

### Integration points:
Add at the top of `get_schema()` and `ask_boyce()`:
```python
freshness_warning = _check_snapshot_freshness(snapshot_name)
# Include in response if present
if freshness_warning:
    payload["freshness_warning"] = freshness_warning
```

### Prerequisite:
The parsers must store `source_path` in snapshot metadata. Check `parsers/detect.py` `parse_from_path()` — if it doesn't already store the path, add:
```python
snapshot.metadata["source_path"] = str(path)
```
This may require making the snapshot mutable during parse or passing metadata through. Check implementation.

### Tests:
1. `test_freshness_check_no_source_path` — snapshot without source_path → None
2. `test_freshness_check_fresh` — source mtime < snapshot mtime → None
3. `test_freshness_check_stale` — source mtime > snapshot mtime → warning string
4. `test_freshness_check_once_per_session` — second call returns None (cached)

---

## Part C: Schema Freshness — Tier 3 (Live DB Drift Detection)

### Location: `boyce/src/boyce/server.py`

### New helper function:
```python
_drift_checked: set = set()


async def _check_db_drift(snapshot_name: str) -> Optional[Dict[str, Any]]:
    """
    Compare snapshot entities/fields against live database information_schema.

    Returns a drift report dict if discrepancies found, None otherwise.
    Only runs once per snapshot per server session. Requires BOYCE_DB_URL.
    """
    if snapshot_name in _drift_checked:
        return None
    _drift_checked.add(snapshot_name)

    try:
        adapter = await _get_adapter()
    except RuntimeError:
        return None  # No DB configured

    try:
        snapshot = _store.load(snapshot_name)
    except (FileNotFoundError, ValueError):
        return None

    # Query information_schema for all columns in public schema
    try:
        rows = await adapter.execute_query(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "ORDER BY table_name, ordinal_position"
        )
    except Exception as exc:
        logger.debug("Drift check query failed: %s", exc)
        return None

    # Build set of (table, column) from live DB
    live_columns = set()
    for row in rows:
        live_columns.add((row["table_name"], row["column_name"]))

    # Build set of (table, column) from snapshot
    snapshot_columns = set()
    for entity_id, entity in snapshot.entities.items():
        for field_id in entity.fields:
            field = snapshot.fields.get(field_id)
            if field:
                snapshot_columns.add((entity.name, field.name))

    # Find columns in live DB not in snapshot
    new_in_db = live_columns - snapshot_columns
    # Find columns in snapshot not in live DB
    missing_from_db = snapshot_columns - live_columns

    if not new_in_db and not missing_from_db:
        return None

    # Group by table for readable output
    new_by_table: Dict[str, List[str]] = {}
    for table, column in sorted(new_in_db):
        new_by_table.setdefault(table, []).append(column)

    missing_by_table: Dict[str, List[str]] = {}
    for table, column in sorted(missing_from_db):
        missing_by_table.setdefault(table, []).append(column)

    report = {
        "new_in_db": new_by_table,
        "missing_from_db": missing_by_table,
        "message": (
            f"Snapshot '{snapshot_name}' may be stale: "
            f"{len(new_in_db)} column(s) in the live database are not in the snapshot"
            + (f", {len(missing_from_db)} column(s) in the snapshot are not in the database"
               if missing_from_db else "")
            + ". Run ingest_source to refresh."
        ),
    }

    logger.info("DB drift detected for '%s': %s", snapshot_name, report["message"])
    return report
```

### Integration point:
Add to `get_schema()` after loading snapshot:
```python
drift_report = await _check_db_drift(snapshot_name)
if drift_report:
    # Include in response alongside schema data
    result["drift_warning"] = drift_report
```

Note: `get_schema()` is currently sync. It will need to become async to call `_check_db_drift()`. This also means the HTTP route handler needs adjustment. Alternatively, run the drift check only in `ask_boyce()` which is already async.

**Recommendation:** Run drift check in `ask_boyce()` only (it's already async). `get_schema()` stays sync for simplicity. If the host LLM calls `get_schema` first (as recommended by tool descriptions), it won't see drift warnings — but the next `ask_boyce` call will. This is acceptable because drift warnings are informational, not blocking.

### Tests:
1. `test_drift_check_no_adapter` — no BOYCE_DB_URL → None
2. `test_drift_check_in_sync` — live DB matches snapshot → None
3. `test_drift_check_new_columns` — live DB has extra columns → report with new_in_db
4. `test_drift_check_once_per_session` — second call returns None (cached)

---

## Part D: Source Path Tracking in Parsers

### Check and update: `boyce/src/boyce/parsers/detect.py`

The `parse_from_path()` function should ensure that the resulting snapshot includes the source file path in metadata:

```python
def parse_from_path(path: str) -> SemanticSnapshot:
    """Auto-detect source type and parse into a SemanticSnapshot."""
    file_path = Path(path)
    # ... existing detection logic ...
    snapshot = parser.parse(file_path)
    
    # Ensure source_path is tracked for freshness checks
    if "source_path" not in snapshot.metadata:
        # SemanticSnapshot is frozen, so we need to handle this carefully
        # Option A: if metadata is a mutable dict reference, just set it
        # Option B: if frozen, reconstruct with updated metadata
        updated_metadata = dict(snapshot.metadata)
        updated_metadata["source_path"] = str(file_path.resolve())
        snapshot = snapshot.model_copy(update={"metadata": updated_metadata})
    
    return snapshot
```

**Note:** `SemanticSnapshot` has `model_config = {"frozen": True}`. Use `model_copy(update=...)` (Pydantic v2) to create a new instance with updated metadata. Verify this works with the frozen config.
