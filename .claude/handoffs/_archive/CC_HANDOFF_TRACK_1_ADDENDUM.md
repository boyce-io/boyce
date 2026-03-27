# CC Handoff — Track 1 Addendum: Arrogant Archetype Safety Fixes
**Append this to CC_HANDOFF_TRACK_1.md as Block 5**  
**Execute AFTER Blocks 1-4 pass tests**  
**All changes in server.py (already owned by Track 1)**

---

## Context

Cross-platform testing revealed that non-Claude models (GPT-5.4/Codex, Cursor/Auto) bypass ask_boyce entirely and send raw SQL straight to query_database. The behavioral advertising layer fires correctly on the bypass path but does not change their behavior. The safety pipeline (live NULL trap detection, join validation) only runs through ask_boyce, meaning the bypass path is unsafe.

These fixes make the bypass path safe. We are NOT trying to force arrogant models into ask_boyce. We are making query_database provide equivalent safety regardless of how the model got there.

---

## Fix A: Live NULL Trap Detection in query_database

**Problem:** `query_database` currently runs `_scan_null_risk()` which is regex + schema metadata. It reports "column is nullable" — a boolean fact that arrogant models ignore. The live `_null_trap_check()` that profiles columns against the actual DB and reports "WHERE status = 'active' silently excludes 3,000 NULL rows (30%)" only runs through the ask_boyce pipeline.

**Fix:** Call `_null_trap_check()` (or a lightweight adapted version) inside `query_database` before execution, for queries that contain equality filters on nullable columns.

**Implementation:**

In `query_database()`, after the existing `_scan_null_risk()` call but before query execution:

```python
# Existing lightweight check (keep this — it's fast)
null_risk_columns = _scan_null_risk(sql, snapshot_name)

# NEW: Live NULL trap profiling for equality-filtered columns
# Only runs when _scan_null_risk found nullable columns in WHERE equality filters
live_null_warnings = []
if null_risk_columns:
    try:
        snapshot = _store.load(snapshot_name)
        # Build a minimal structured_filter-like dict from the regex matches
        # so we can reuse _null_trap_check's profiling logic
        live_null_warnings = await _query_database_null_check(
            sql, snapshot, snapshot_name, max_columns=3
        )
    except Exception:
        pass  # Non-fatal — never block query execution on a failed profile
```

**New helper function:**

```python
async def _query_database_null_check(
    sql: str,
    snapshot: "SemanticSnapshot", 
    snapshot_name: str,
    max_columns: int = 3,
) -> List[Dict[str, Any]]:
    """
    Profile equality-filtered columns in raw SQL against the live DB.
    
    This is the query_database equivalent of _null_trap_check() — adapted
    to work with raw SQL (no StructuredFilter) by parsing WHERE clauses.
    
    Caps at max_columns to bound latency on complex queries.
    Returns list of warning dicts (same shape as _null_trap_check output).
    """
    try:
        adapter = await _get_adapter()
    except RuntimeError:
        return []
    
    warnings = []
    checked = 0
    
    # Use existing _EQUALITY_FILTER_RE to find table.col = 'value' patterns
    from_tables = _extract_from_tables(sql)
    real_table_names = set(from_tables.values())
    
    for match in _EQUALITY_FILTER_RE.finditer(sql):
        if checked >= max_columns:
            break
            
        if match.group(1) and match.group(2):
            table_name = from_tables.get(match.group(1), match.group(1))
            column_name = match.group(2)
        elif match.group(3):
            # Bare column — resolve against FROM tables
            column_name = match.group(3)
            table_name = None
            for field in snapshot.fields.values():
                if field.name == column_name:
                    entity = snapshot.entities.get(field.entity_id)
                    if entity and entity.name in real_table_names:
                        table_name = entity.name
                        break
            if not table_name:
                continue
        else:
            continue
        
        # Only profile if snapshot says nullable
        is_nullable = False
        for field in snapshot.fields.values():
            if field.name == column_name:
                entity = snapshot.entities.get(field.entity_id)
                if entity and entity.name == table_name and field.nullable:
                    is_nullable = True
                    break
        
        if not is_nullable:
            continue
        
        checked += 1
        try:
            profile = await adapter.profile_column(table_name, column_name)
            null_pct = profile.get("null_pct", 0.0)
            if null_pct > 5.0:  # Same threshold as _null_trap_check
                warnings.append({
                    "table": table_name,
                    "column": column_name,
                    "null_pct": null_pct,
                    "null_count": profile.get("null_count", "?"),
                    "row_count": profile.get("row_count", "?"),
                    "risk": (
                        f"WHERE {column_name} = '...' silently excludes "
                        f"{profile.get('null_count', '?')} NULL rows "
                        f"({null_pct:.1f}% of {table_name}). "
                        f"Those rows vanish without warning."
                    ),
                })
        except Exception:
            continue
    
    return warnings
```

**Update query_database response to include live warnings:**

In the success path of `query_database()`, merge live warnings into the advertising layer:

```python
ad = _build_advertising_layer(
    sql=sql, snapshot_name=snapshot_name, tool_name="query_database",
    validation=validation,
    null_risk=null_risk_columns or None,
    null_trap_warnings=live_null_warnings or None,  # NEW: pass live warnings
)
```

Note: `_build_advertising_layer` already handles `null_trap_warnings` — it builds the loss-aversion `present_to_user` messages from them. The same code path that makes ask_boyce warnings visceral now makes query_database warnings visceral.

**Test:** Write a test that calls query_database with raw SQL containing a WHERE equality filter on a nullable column, and verify that the response includes null_trap_warnings with actual percentages (not just the boolean nullable flag).

---

## Fix B: Schema Guidance Returns Ready-to-Use Filter

**Problem:** Mode C (ask_boyce without credentials) returns a suggested_filter and a message saying "you may adjust it first or pass it directly." The arrogant archetype reads "adjust" as "I should just write SQL myself."

**Fix:** Change the framing from suggestion to gift. The filter is ready to use.

**In `_build_schema_guidance()`**, change the message:

```python
# BEFORE:
"message": (
    "Here is a suggested StructuredFilter for your query.  "
    "Call ask_boyce again with structured_filter set to the "
    "suggested_filter below.  You may adjust it first or pass "
    "it directly — no additional credentials are needed."
),

# AFTER:
"message": (
    "Ready-to-use filter constructed from your query.  "
    "Call ask_boyce(structured_filter=ready_filter) to compile "
    "validated SQL with NULL trap detection and EXPLAIN pre-flight.  "
    "No modification needed, no credentials required.  One call."
),
```

**Rename the key** in the response dict:

```python
# BEFORE:
if suggested:
    result["suggested_filter"] = suggested

# AFTER:
if suggested:
    result["ready_filter"] = suggested
    # Keep backward compat for any existing consumers
    result["suggested_filter"] = suggested
```

**Update the Mode C next_step** in `_build_advertising_layer`:

```python
# BEFORE:
"ask_boyce_mode_c": (
    "Call ask_boyce again with the suggested_filter above as the "
    "structured_filter parameter."
),

# AFTER:
"ask_boyce_mode_c": (
    "Call ask_boyce(structured_filter=ready_filter) now. "
    "The filter is complete — pass it directly, no changes needed."
),
```

**Test:** Verify Mode C response contains `ready_filter` key and the message says "No modification needed."

---

## Fix C: get_schema Authority Claim + information_schema Detection

**Problem:** Codex called get_schema AND ran two additional raw SQL queries against information_schema to independently verify the snapshot. The verification instinct wastes round-trips for data already in the snapshot.

### Fix C1: Authority claim in get_schema response

In the `get_schema` function, add an `authority` field to the response:

```python
result: Dict[str, Any] = {
    **ad,
    "snapshot_id": snapshot.snapshot_id,
    "snapshot_name": snapshot_name,
    "authority": (
        f"Complete schema: {len(entities_out)} entities, "
        f"{sum(len(e['fields']) for e in entities_out)} fields, "
        f"{len(joins_out)} joins with confidence weights. "
        f"Reflects full live database as of ingest — no additional "
        f"metadata queries (information_schema, pg_catalog) needed."
    ),
    "entities": entities_out,
    ...
}
```

### Fix C2: Detect information_schema/pg_catalog queries in query_database

In `query_database()`, after the SQL is received but before execution, check if it queries metadata tables:

```python
# Detect metadata table queries — model is duplicating get_schema work
_metadata_tables = {"information_schema", "pg_catalog"}
sql_lower = sql.lower()
is_metadata_query = any(t in sql_lower for t in _metadata_tables)

# ... after execution, in the advertising layer call:
if is_metadata_query:
    # Add to the messages list that feeds present_to_user
    # (This requires passing a flag to _build_advertising_layer or
    #  adding the message after the ad dict is built)
    ad.setdefault("present_to_user", "")
    metadata_note = (
        "get_schema already provides this metadata enriched with "
        "join confidence weights, NULL risk flags, and certified "
        "business definitions that information_schema does not contain."
    )
    if ad.get("present_to_user"):
        ad["present_to_user"] += " " + metadata_note
    else:
        ad["present_to_user"] = metadata_note
```

**Test:** Call query_database with `SELECT * FROM information_schema.tables LIMIT 5` and verify present_to_user includes the metadata note.

---

## Updated Verification Checklist (append to Track 1 checklist)

- [ ] query_database with equality filter on nullable column returns null_trap_warnings with live percentages
- [ ] Mode C response contains `ready_filter` key with complete StructuredFilter
- [ ] Mode C message says "No modification needed"
- [ ] get_schema response contains `authority` field with entity/field/join counts
- [ ] query_database on information_schema query includes metadata note in present_to_user
- [ ] No performance regression: query_database on non-equality queries (no WHERE = 'value') skips null profiling entirely
