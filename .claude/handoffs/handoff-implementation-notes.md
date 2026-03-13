# Implementation Notes — CTO Addendum (2026-03-13)

**Context:** Opus review produced three handoff docs. Before Sonnet executes them
sequentially, this addendum resolves every ambiguity found during code review of
`server.py`, `planner.py`, `http_api.py`, and `detect.py`.

**Rule:** Sonnet should read this file BEFORE starting any change. Each note maps
to a specific change number from `handoff-architecture-revision.md`.

---

## Note 1: `_run_sql_pipeline()` already exists — no ambiguity

**Affects:** Change 2 (ask_boyce tri-modal)

The handoff pseudocode references `_run_sql_pipeline(...)`. This function already
exists at `server.py:399`. It takes `(snapshot, structured_filter, snapshot_name,
dialect, *, query_label)` and runs Stages 2-4 (kernel → NULL trap → EXPLAIN → lint).

Both `build_sql` (line 821) and `ask_boyce` (line 1034) already call it. When
implementing Mode A of `ask_boyce`, call `_run_sql_pipeline()` directly — same
pattern as the existing `build_sql` tool body.

---

## Note 2: Exception routing for Mode C — verified correct

**Affects:** Change 2 (ask_boyce tri-modal, Mode C fallback)

The handoff pseudocode catches `ValueError` to trigger Mode C. This is correct.
`plan_query()` in `planner.py` raises `ValueError` in exactly three cases:

- Line 107-110: `litellm` not installed
- Line 112-116: `BOYCE_PROVIDER` or `BOYCE_MODEL` not set
- Line 118-122: No API key found (OPENAI/ANTHROPIC/LITELLM_API_KEY)

These are the "no credentials" cases that should trigger Mode C.

`litellm.AuthenticationError` (invalid key, not missing key) is a **different**
case — it means the user configured credentials but they're wrong. This should
NOT trigger Mode C; it should return the error so the user can fix their key.
The existing `except Exception` handler at line 1023 already catches this.

**Implementation pattern:**
```python
try:
    planner = _get_planner()
    structured_filter = planner.plan_query(
        natural_language_query, _graph,
        definitions_context=definitions_context,
    )
except ValueError:
    # Mode C: credentials not configured → return schema guidance
    return _build_schema_guidance(
        natural_language_query, snapshot, snapshot_name,
    )
except Exception as e:
    # Actual LLM error (bad key, network, parse failure)
    logger.exception("Unexpected error in plan_query")
    _audit.log_query(...)
    return json.dumps({"error": {"code": -32603, "message": f"Planner error: {e}"}})
```

---

## Note 3: `get_schema` already returns StructuredFilter docs — no change needed

**Affects:** Change 3 (tool descriptions)

The handoff says `get_schema` should return StructuredFilter documentation. It
already does — see `server.py:749`:

```python
"structured_filter_docs": _STRUCTURED_FILTER_DOCS,
```

The revised tool description in the handoff matches the current behavior. When
rewriting the description (Change 3), no payload changes are needed for `get_schema`.
Only the docstring/description text changes.

---

## Note 4: `_validate_structured_filter()` already exists — Mode A uses it

**Affects:** Change 2 (ask_boyce Mode A)

The filter validator is at `server.py:104-176`. It checks entity IDs, field IDs,
metrics, dimensions, filters, temporal filters, and dialect against the snapshot.
Returns a list of error strings (empty = valid).

Mode A should validate the filter the same way `build_sql` does (see line 809):

```python
validation_errors = _validate_structured_filter(structured_filter, snapshot)
if validation_errors:
    return json.dumps({
        "error": {
            "code": -32602,
            "message": "StructuredFilter validation failed",
            "data": validation_errors,
        }
    })
```

---

## Note 5: Entity scoring code line numbers are off

**Affects:** Change 2 (Mode C `_build_schema_guidance`)

The handoff says "Reuse the keyword-overlap entity scoring from `planner.py`
lines 120-128." The actual location is **lines 131-138**:

```python
# planner.py:131-138
query_words = set(re.findall(r"\b\w+\b", query.lower()))
entity_scores: List[tuple[int, str]] = []
for entity_name in entity_names:
    score = sum(1 for w in query_words if w in entity_name.lower())
    if score > 0 or len(entity_names) <= 50:
        entity_scores.append((score, entity_name))
entity_scores.sort(reverse=True, key=lambda x: x[0])
top_entities = [name for _, name in entity_scores[:50]]
```

For `_build_schema_guidance()`, extract this into a helper or duplicate the
pattern. The function needs access to the graph's entity list, which means
importing `_graph` (already module-level in `server.py`).

---

## Note 6: HTTP API impact — explicit changes needed

**Affects:** Change 1 (internalization), Change 6 (kill intent classifier)

### After Change 1 (build_sql/solve_path internalized):

`http_api.py` imports these as:
```python
from .server import build_sql   # line 156
from .server import solve_path  # line 230 (via route_chat)
```

When `@mcp.tool()` decorators are removed, the functions remain importable.
**No http_api.py changes needed for Change 1.** The HTTP routes call the
functions directly, not through MCP — the `@mcp.tool()` decorator is irrelevant
to the import.

However: rename the functions to `_build_sql` and `_solve_path` (with underscore
prefix for consistency), and update `http_api.py` imports accordingly. This makes
the internal-vs-exposed distinction clear.

### After Change 6 (kill intent classifier):

`http_api.py:190` imports `_classify_intent` from `cli.py`:
```python
from .cli import _classify_intent  # noqa: PLC0415
```

The entire `route_chat()` function (lines 177-263) uses intent classification
to route between get_schema, solve_path, profile, and ask_boyce.

**Replace `route_chat()` with:** Route everything through `ask_boyce`. Format
the response conversationally. If `ask_boyce` returns Mode C guidance, format
appropriately. Remove the `_classify_intent` import.

---

## Note 7: `ask_boyce` parameter change — MCP schema implications

**Affects:** Change 2 (ask_boyce tri-modal)

Current signature:
```python
async def ask_boyce(
    natural_language_query: str,  # REQUIRED
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
```

New signature:
```python
async def ask_boyce(
    natural_language_query: str = "",       # NOW OPTIONAL
    structured_filter: Optional[dict] = None,  # NEW
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
```

FastMCP auto-generates the JSON schema from the function signature. Making
`natural_language_query` default to `""` (empty string) instead of required
means the MCP tool schema will show it as optional. This is correct — Mode A
callers provide `structured_filter` only.

Ensure the routing logic handles the case where both are empty:
```python
if not structured_filter and not natural_language_query:
    return json.dumps({
        "error": {
            "code": -32602,
            "message": "Provide natural_language_query or structured_filter",
        }
    })
```

---

## Note 8: Source path tracking in `parse_from_path` — compose with today's edit

**Affects:** Change 5 (schema freshness Tier 2)

Today (2026-03-13) the SemanticSnapshot JSON passthrough was added to
`parse_from_path()` in `detect.py`. The freshness spec (Part D of
`handoff-validate-sql-and-freshness.md`) says to add `source_path` to
snapshot metadata in the same function.

The source_path tracking should be added to **both** code paths:
1. The new SemanticSnapshot JSON passthrough (line 72-91)
2. The registry parse path (line 93)

For path 1 (JSON passthrough):
```python
# After line 88 (before return snapshot):
updated_metadata = dict(snapshot.metadata)
updated_metadata["source_path"] = str(path.resolve())
snapshot = snapshot.model_copy(update={"metadata": updated_metadata})
return snapshot
```

For path 2 (registry parse):
```python
# After line 93:
snapshot = get_default_registry().parse(path)
updated_metadata = dict(snapshot.metadata)
updated_metadata["source_path"] = str(path.resolve())
snapshot = snapshot.model_copy(update={"metadata": updated_metadata})
return snapshot
```

`SemanticSnapshot` has `model_config = {"frozen": True}`, so `model_copy(update=...)`
(Pydantic v2) is required. This works correctly — verified in today's edit.

---

## Note 9: Mode A test spec (missing from handoffs)

**Affects:** Change 2 (ask_boyce tri-modal)

The handoff lists test requirements but doesn't specify Mode A test cases.
Add these to `boyce/tests/test_kernel_tools.py` or a new test file:

1. **`test_ask_boyce_mode_a_basic`** — call `ask_boyce` with a valid
   `structured_filter` and no `natural_language_query`. Verify: returns SQL,
   validation status, no planner error.

2. **`test_ask_boyce_mode_a_invalid_filter`** — call with a `structured_filter`
   that references non-existent entity IDs. Verify: returns validation error
   with specific field-level messages.

3. **`test_ask_boyce_mode_a_ignores_credentials`** — call with a valid
   `structured_filter` and no BOYCE_PROVIDER/BOYCE_MODEL set. Verify: succeeds
   (Mode A doesn't need credentials).

4. **`test_ask_boyce_mode_a_filter_takes_priority`** — call with BOTH
   `structured_filter` and `natural_language_query`. Verify: filter is used,
   NL query is ignored, no LLM call.

---

## Note 10: Change execution — what to test after each step

After each numbered change, run:
```bash
python boyce/tests/verify_eyes.py          # 15 offline tests
python -m pytest boyce/tests/ -v           # full suite (~260 tests)
python boyce/tests/test_cli_smoke.py       # 17 CLI checks
```

### Per-change test expectations:

| Change | Tests that need updating | New tests needed |
|--------|------------------------|------------------|
| 1 (internalize build_sql/solve_path) | `test_kernel_tools.py` — if any test calls `build_sql`/`solve_path` as MCP tools (unlikely, they're called as functions) | None |
| 2 (ask_boyce tri-modal) | None break | Mode A (4 tests above), Mode C (1-2 tests) |
| 3 (tool descriptions) | None | None (docstring-only changes) |
| 4 (StructuredFilter examples) | None | None (string constant update) |
| 5 (freshness) | None | 4 freshness tests (listed in validate-sql handoff) |
| 6 (kill intent classifier) | `test_cli_smoke.py` — if `boyce chat` exit codes change | None |
| 7 (boyce-init platforms) | `test_init.py` — add new platform tests | VS Code, JetBrains, Windsurf tests |
| 8-9 (freshness tiers) | None | Per tier (listed in validate-sql handoff) |
| 10 (MASTER.md) | None | None (doc update) |

---

## Summary: Gaps Resolved

| # | Issue identified in review | Resolution |
|---|--------------------------|------------|
| 1 | `_run_sql_pipeline()` doesn't exist | **It does.** Line 399. No issue. |
| 2 | `get_schema` silently gains new responsibilities | **Already implemented.** Line 749. No code change. |
| 3 | Missing test spec for Mode A | **Added above.** 4 test cases. |
| 4 | `_get_planner()` exception type assumed | **Verified correct.** `ValueError` catches all "no credentials" cases. |
| 5 | Source path tracking + today's edit interaction | **Documented.** Both code paths need the update. |
| 6 | HTTP API endpoints after internalization | **Documented.** Rename functions, update imports, rewrite `route_chat()`. |
