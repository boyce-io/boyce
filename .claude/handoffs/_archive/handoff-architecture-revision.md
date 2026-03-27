# Architecture Revision — CEO Directive (2026-03-13)

**Priority:** CRITICAL — blocks Phase B completion and PyPI publish
**Source:** CEO planning session with Opus. All decisions are final unless noted as OPEN.
**Scope:** MCP tool surface, credential architecture, platform targeting, extension strategy

---

## Executive Summary

The current architecture requires two LLM credentials in MCP host contexts: the host's own LLM (user's subscription) and Boyce's internal planner (separate API key via BOYCE_PROVIDER). This is a bounce-off risk for every MCP host user. The fix: Boyce never reasons in MCP context. The host LLM does all reasoning. Boyce is a deterministic compiler and safety layer.

Additionally: the custom VS Code extension (`extension/`) is deprioritized. VS Code has native GA MCP support. Boyce works in VS Code through standard MCP configuration, no custom extension needed. JetBrains/DataGrip is added as a high-priority target platform.

---

## Architectural Principle

**Boyce is invisible infrastructure.** The user talks to their LLM. Their LLM uses Boyce. The user never configures Boyce's LLM, never authenticates with Boyce's LLM, never learns Boyce's vocabulary. They just get better, safer SQL than they would have gotten without it.

The QueryPlanner and LiteLLM exist exclusively for non-MCP delivery surfaces (CLI, HTTP API) where no host LLM is present. MCP host users need zero Boyce-specific LLM configuration.

---

## Change 1: Consolidate MCP Tools from 8 to 7

### Remove as exposed MCP tools (keep as internal functions):
- **`build_sql`** — functionality absorbed into `ask_boyce` via optional `structured_filter` parameter
- **`solve_path`** — diagnostic utility; kernel resolves joins internally

### Add:
- **`validate_sql`** (new) — accepts raw SQL, runs EXPLAIN pre-flight + Redshift lint + lightweight NULL-risk scan

### Final MCP tool surface (7 tools):

| # | Tool | Intent | Credentials needed |
|---|------|--------|--------------------|
| 1 | `ingest_source` | Parse + load schema | None |
| 2 | `ingest_definition` | Store business definitions | None |
| 3 | `get_schema` | Understand the database | None |
| 4 | `ask_boyce` | Get SQL (NL or StructuredFilter) | None for StructuredFilter path; BOYCE_PROVIDER for NL path |
| 5 | `validate_sql` | Check my SQL | None (BOYCE_DB_URL for EXPLAIN) |
| 6 | `query_database` | Execute read-only SQL | BOYCE_DB_URL |
| 7 | `profile_data` | Profile a column | BOYCE_DB_URL |

Each tool maps to exactly one user intent. No overlap.

### Implementation notes:
- `build_sql` becomes `_build_sql()` internal function in `server.py`. The HTTP API (`/build-sql`) can still call it internally.
- `solve_path` becomes `_solve_path()` internal function. The HTTP API (`/solve-path` if needed) and CLI can still call it.
- Both functions remain importable from `boyce.server` for programmatic use.

---

## Change 2: `ask_boyce` Becomes Tri-Modal

The unified query entrypoint accepts three input modes:

### Mode A: StructuredFilter provided (zero credentials)
```
ask_boyce(structured_filter={...}, snapshot_name="default", dialect="redshift")
```
- Skip planner entirely
- Run deterministic pipeline: kernel → NULL trap → EXPLAIN → lint
- This is the primary MCP host path
- `natural_language_query` parameter is optional/ignored when filter is provided

### Mode B: NL query + credentials configured
```
ask_boyce(natural_language_query="revenue by product last 12 months", snapshot_name="default")
```
- Run QueryPlanner → StructuredFilter → pipeline
- This is the standalone CLI / HTTP API path
- Same as current behavior

### Mode C: NL query + no credentials + no filter
```
ask_boyce(natural_language_query="revenue by product last 12 months", snapshot_name="default")
# BOYCE_PROVIDER not set, no structured_filter provided
```
- Return relevant schema context inline (entity names, fields, types scoped to query via keyword-overlap scoring)
- Include StructuredFilter documentation
- Include business definitions from DefinitionStore
- Return structured guidance message for the host LLM to construct a filter and call back
- Two calls total, zero config

### Parameter changes to `ask_boyce`:
```python
@mcp.tool()
async def ask_boyce(
    natural_language_query: str = "",        # existing, now optional
    structured_filter: Optional[dict] = None, # NEW — StructuredFilter dict
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
```

### Routing logic (pseudocode):
```python
if structured_filter:
    # Mode A: deterministic, no LLM
    validate filter against snapshot
    run _run_sql_pipeline(snapshot, structured_filter, ...)
    return SQL + safety results

if not natural_language_query:
    return error("Provide natural_language_query or structured_filter")

try:
    planner = _get_planner()  # checks BOYCE_PROVIDER, BOYCE_MODEL, API key
    structured_filter = planner.plan_query(query, graph, definitions_context)
    # Mode B: NL with credentials
    run _run_sql_pipeline(...)
    return SQL + safety results
except ValueError:
    # Mode C: no credentials — return schema context for host LLM
    return _build_schema_guidance(query, snapshot, snapshot_name)
```

### `_build_schema_guidance()` implementation:
- Reuse the keyword-overlap entity scoring from `planner.py` lines 120-128
- Return top-50 entities with full field details (same format as `get_schema`)
- Include StructuredFilter docs (`_STRUCTURED_FILTER_DOCS`)
- Include business definitions from `_definitions.as_context_string(snapshot_name)`
- Return as JSON with a clear `"mode": "schema_guidance"` key so callers can distinguish from SQL results

---

## Change 3: Rewrite All MCP Tool Descriptions

Tool descriptions are the UX layer for MCP hosts. The host LLM reads these to decide which tools to call and in what order. Current descriptions are implementation-focused. New descriptions must program host LLM behavior.

### `get_schema` description (revised):
```
Return the full schema context for a snapshot — entities, fields, joins, 
business definitions, and StructuredFilter documentation.

**Call this first** when you need to understand a database before generating SQL.
Read the schema to learn what entities (tables), fields (columns), joins, and 
business definitions are available. Use the StructuredFilter documentation to 
construct a filter for `ask_boyce`.

If you are an MCP host with your own LLM: read this schema, reason about the 
user's question, construct a StructuredFilter, and pass it to `ask_boyce`. 
No additional credentials or API keys are needed.
```

### `ask_boyce` description (revised):
```
Generate safe, deterministic SQL from either a natural language question or a 
StructuredFilter.

**For MCP hosts (Claude, Cursor, Copilot, etc.):** Call `get_schema` first to 
understand the database. Construct a StructuredFilter from the schema and pass 
it here via the `structured_filter` parameter. No additional credentials needed.
Boyce compiles deterministic SQL and runs safety checks (NULL trap detection, 
EXPLAIN pre-flight, Redshift compatibility lint).

**For standalone use (CLI, HTTP API):** Pass a `natural_language_query` and 
configure BOYCE_PROVIDER + BOYCE_MODEL environment variables.

If called with only a natural language query and no LLM credentials are configured,
returns relevant schema context so you can construct the filter.
```

### `validate_sql` description (new tool):
```
Validate a SQL query through Boyce's safety layer without executing it.

Use this when you've written SQL directly (without using a StructuredFilter) and 
want to check it before running. Returns:
- EXPLAIN pre-flight result (verified/invalid/unchecked)
- Redshift compatibility warnings
- NULL risk analysis for equality-filtered columns (when parseable from WHERE clause)

Does NOT execute the query. Use `query_database` to run it after validation.
```

### Other tool descriptions:
- `ingest_source`: keep current description, it's already good
- `ingest_definition`: keep current description, it's already good  
- `query_database`: keep current description, it's already good
- `profile_data`: keep current description, it's already good

---

## Change 4: StructuredFilter Documentation Enhancement

The StructuredFilter docs returned by `get_schema` (currently `_STRUCTURED_FILTER_DOCS` in `server.py`) need 3-5 concrete query/filter example pairs. The host LLM learns by example.

### Add to `_STRUCTURED_FILTER_DOCS`:

```
### Examples

**Example 1: Simple aggregation**
User question: "Total revenue by product status"
StructuredFilter:
{
  "concept_map": {
    "entities": [{"entity_id": "entity:orders", "entity_name": "orders"}],
    "fields": [],
    "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue", 
                  "aggregation_type": "SUM"}],
    "dimensions": [{"field_id": "field:orders:status", "field_name": "status",
                     "entity_id": "entity:orders"}],
    "filters": []
  },
  "join_path": ["entity:orders"],
  "grain_context": {"aggregation_required": true, "grouping_fields": ["status"]}
}

**Example 2: Filtered query with temporal range**
User question: "Active customers in the last 6 months"
StructuredFilter:
{
  "concept_map": {
    "entities": [{"entity_id": "entity:customers", "entity_name": "customers"}],
    "fields": [{"field_id": "field:customers:customer_id", "field_name": "customer_id",
                 "entity_id": "entity:customers"}],
    "metrics": [{"metric_name": "customer_id", "field_id": "field:customers:customer_id",
                  "aggregation_type": "COUNT_DISTINCT"}],
    "dimensions": [],
    "filters": [{"field_id": "field:customers:status", "operator": "=", 
                  "value": "active", "entity_id": "entity:customers"}]
  },
  "temporal_filters": [{"field_id": "field:customers:last_login",
                          "operator": "trailing_interval",
                          "value": {"value": 6, "unit": "month"}}],
  "grain_context": {"aggregation_required": true, "grouping_fields": []}
}

**Example 3: Multi-table join**
User question: "Revenue by customer name"
StructuredFilter:
{
  "concept_map": {
    "entities": [{"entity_id": "entity:orders", "entity_name": "orders"},
                 {"entity_id": "entity:customers", "entity_name": "customers"}],
    "fields": [],
    "metrics": [{"metric_name": "revenue", "field_id": "field:orders:revenue",
                  "aggregation_type": "SUM"}],
    "dimensions": [{"field_id": "field:customers:name", "field_name": "name",
                     "entity_id": "entity:customers"}],
    "filters": []
  },
  "join_path": ["entity:orders", "entity:customers"],
  "grain_context": {"aggregation_required": true, "grouping_fields": ["name"]}
}
```

These examples teach the host LLM the pattern. Adjust field/entity IDs to match common snapshot structures.

---

## Change 5: Three-Tier Schema Freshness

### Tier 1 — Event-driven invalidation (instant)
- Already works: `ingest_source` rebuilds snapshot and graph
- **Add:** on re-ingestion, compare new snapshot hash to previous. If changed, log what changed (entities added/removed, fields changed). Store previous hash in snapshot metadata.

### Tier 2 — Session-start re-validation (lightweight)
- On first `get_schema` or `ask_boyce` call in a session, check `_local_context/` files against their source paths (stored in `snapshot.metadata["source_path"]`)
- If source file mtime > snapshot creation time, auto re-ingest and log a notice
- If source file is missing, log a warning but don't fail
- **Implementation:** add `_check_snapshot_freshness(snapshot_name)` helper in `server.py`, called at top of `get_schema` and `ask_boyce`

### Tier 3 — Live DB drift detection (when DB connected)
- On first `get_schema` call when `BOYCE_DB_URL` is set, run lightweight introspection:
  ```sql
  SELECT table_name, column_name 
  FROM information_schema.columns 
  WHERE table_schema = 'public'
  ORDER BY table_name, ordinal_position
  ```
- Compare against snapshot entity/field list
- If new tables or columns exist not in snapshot, include warning in response:
  ```json
  {"drift_warning": "3 columns in 'orders' not in snapshot. Run ingest_source to refresh."}
  ```
- Never block — just warn
- Cache the drift check result for the session (don't re-run on every call)

---

## Change 6: Kill Keyword Intent Classifier

Remove `_classify_intent()` from `cli.py`. 

### `boyce chat` new behavior:
- Route everything through `ask_boyce` 
- Wrap the response in conversational formatting (entity list, SQL with comments, warnings)
- If `ask_boyce` returns Mode C (schema guidance), format as: "Here's what I found in the database. To generate SQL, I need LLM credentials configured. Run `boyce-init` or set BOYCE_PROVIDER."

### `boyce ask` behavior:
- Unchanged — goes straight to `ask_boyce`, SQL to stdout, warnings to stderr

### HTTP `/chat` endpoint:
- Remove intent classification 
- Route through `ask_boyce`
- Format response conversationally (same as CLI chat)

### What to delete:
- `_SCHEMA_KEYWORDS`, `_PATH_KEYWORDS`, `_PROFILE_KEYWORDS` constants
- `_classify_intent()` function
- Intent routing logic in `_cmd_chat()` and `route_chat()`

---

## Change 7: VS Code Extension — Deprioritized

The `extension/` directory is NOT deleted but is explicitly deprioritized. VS Code has native GA MCP support. Boyce works in VS Code through `.vscode/mcp.json` configuration.

### Immediate actions:
- Do NOT work on the extension
- Do NOT include extension in PyPI publish
- Update MASTER.md Block 1b to reflect this decision: "VS Code extension deprioritized. VS Code MCP native integration is the primary path. Extension becomes Option 2 (UX sugar) when organic demand justifies it."
- Add VS Code MCP config to `boyce-init` auto-configuration (see Change 8)

### Future (post-launch):
- Option 2: Thin extension for UX sugar (schema tree, SQL panels, Run button)
- Option 3: MCP Apps interactive UI (when MCP Apps stabilizes)
- Decision deferred until post-launch adoption data exists

---

## Change 8: Platform Targeting — `boyce-init` Updates

Update `init_wizard.py` to auto-detect and configure these 6 platforms:

### Currently supported:
1. Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Cursor — `.cursor/mcp.json` (project-level)
3. Claude Code — `.claude/settings.json` (project-level)

### Add:
4. **VS Code** — `.vscode/mcp.json` (project-level)
5. **JetBrains / DataGrip** — detect via `.idea/` directory presence; config in `.jb-mcp.json` (project-level) OR guide user to Settings → Tools → MCP Server
6. **Windsurf** — `~/.codeium/windsurf/mcp_config.json` (global)

See `handoff-boyce-init-platforms.md` for detailed detection specs and config formats.

### Integration guides (Phase C):
Write and publish guides for all 6 platforms + mention Cline, Continue.dev, Zed as "also works with standard MCP config."

---

## Change 9: `validate_sql` — New Tool Implementation

### Signature:
```python
@mcp.tool()
async def validate_sql(
    sql: str,
    snapshot_name: str = "default",
    dialect: str = "redshift",
) -> str:
```

### Pipeline:
1. Run `lint_redshift_compat(sql)` → compat_risks
2. Run `_preflight_check(sql)` → EXPLAIN validation (if DB connected)
3. Lightweight NULL risk scan: parse WHERE clause for `column = 'value'` patterns, check those columns against snapshot field metadata for nullable flag
4. Return JSON:
```json
{
  "sql": "<echoed back>",
  "validation": {"status": "verified|invalid|unchecked", "error": null, "cost_estimate": 123.4},
  "compat_risks": [...],
  "null_risk_columns": [{"column": "status", "table": "orders", "nullable": true}],
  "snapshot_name": "default"
}
```

### Implementation notes:
- Reuse existing `_preflight_check()` and `lint_redshift_compat()` from `server.py`
- For NULL risk: use a simple regex to extract `WHERE column = value` patterns, look up columns in snapshot
- This does NOT require the full StructuredFilter machinery — it works on raw SQL
- Audit log the validation call

---

## Change 10: Keep CLI/HTTP as Secondary Surfaces

### What stays:
- `cli.py` — `boyce ask`, `boyce chat`, `boyce serve --http`
- `http_api.py` — all endpoints
- `planner.py` — QueryPlanner + LiteLLM
- All BOYCE_PROVIDER / BOYCE_MODEL / API key env var support

### What changes:
- These are documented as "standalone mode" — for use outside MCP hosts
- `boyce-init` wizard already distinguishes: "MCP hosts do NOT need LLM config"
- HTTP API keeps `/build-sql` and `/solve-path` endpoints (even though MCP tools are consolidated) — HTTP API serves different consumers

### Positioning:
- MCP path = primary product, zero config
- Standalone path = secondary, explicit setup expected
- HTTP API = embedding surface for custom integrations

---

## Changes to MASTER.md

Update the following sections:

### "Two LLM Roles" section:
Replace current table with updated architecture reflecting that MCP hosts use zero Boyce LLM config.

### Block 1b (VS Code Extension):
Mark as deprioritized. Add note: "VS Code native MCP support is the primary VS Code delivery path. Custom extension deferred to post-launch."

### Platform targeting:
Update delivery surface table to include VS Code (MCP native), JetBrains/DataGrip, Windsurf.

### Current Technical State:
Update MCP tools count from 8 to 7. Add `validate_sql`. Note `build_sql` and `solve_path` internalized.

---

## Implementation Order

1. **`ask_boyce` tri-modal** — highest leverage change. Unblocks zero-config MCP path.
2. **Tool descriptions** — rewrite all 7 descriptions for host-LLM consumption.
3. **`validate_sql`** — new tool, uses existing functions.
4. **`build_sql` / `solve_path` internalization** — remove `@mcp.tool()` decorators, keep functions.
5. **StructuredFilter examples** — add to `_STRUCTURED_FILTER_DOCS`.
6. **Kill intent classifier** — simplify `cli.py` and `http_api.py`.
7. **`boyce-init` platform updates** — add VS Code, JetBrains, Windsurf.
8. **Schema freshness (Tier 2)** — mtime check on session start.
9. **Schema freshness (Tier 3)** — live DB drift warning.
10. **MASTER.md updates** — reflect all changes.

### Verification:
- `python boyce/tests/verify_eyes.py` must pass before and after every change
- All existing tests must continue to pass (build_sql/solve_path tests may need adjustment since tools become internal functions, but the functions themselves don't change)
- New tests required for: `validate_sql` tool, `ask_boyce` Mode A (structured_filter), `ask_boyce` Mode C (schema guidance fallback), `_check_snapshot_freshness()`

---

## What This Is NOT

- NOT a rewrite. The kernel, builder, graph, parsers, types, safety — all unchanged.
- NOT removing any functionality. `build_sql` and `solve_path` still exist as functions.
- NOT changing the StructuredFilter contract. Same shape, same fields.
- NOT changing the deterministic pipeline. Same stages, same order.
- The planner, LiteLLM, and credential system stay for standalone surfaces.
