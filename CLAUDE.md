# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

---

## Role

CTO / Architect. Follows the four-phase protocol defined in `~/.claude/CLAUDE.md`: Assess & Plan → Build → Verify → Ship.

## Session Protocol
1. Read `_strategy/MASTER.md` for current priorities
2. Check for active plans in `_strategy/plans/`
3. If session is getting long (>30 messages): *"Run `/compact` to preserve context."*

### Model Tiering
Follows the Mandatory Model Gate defined in `~/.claude/CLAUDE.md`.

---

## Master Planning Document

`_strategy/MASTER.md` is the single source of truth for product direction, execution plan, and architectural decisions. Read it at the start of any non-trivial session. Do not create new strategy documents — update MASTER.md directly.

---

## Ops Layer

This project uses the Convergent Methods ops layer protocol. The canonical protocol definition lives in the CM root CLAUDE.md (`/Users/willwright/ConvergentMethods/CLAUDE.md`). Follow all ops layer behaviors defined there: session boot sequence, session end protocol, amendment protocol, session log rotation, status bar, and directory scope rules.

On session boot, read `ROADMAP.md` and `SESSION_LOG.md` at the repo root before doing any work. These files govern phase sequencing and session continuity.

**Upward propagation paths:** When a propagation event occurs (phase
completion, external publish, blocking status change, HITL gate
reached/cleared — see CM root CLAUDE.md for full list), update these
CEO-level docs before the session ends:
- `/Users/willwright/ConvergentMethods/MASTER.md` — this project's workstream entry
- `/Users/willwright/ConvergentMethods/OPUS_BRIEF.md` — this project's portfolio brief entry

**Status bar:** Every response footer must include, alongside existing lines (docs updated, persistence receipts, timestamp):
```
Project: Boyce | Phase: [current phase from ROADMAP.md]
```

---

## Repo Folder Visibility Convention

Every top-level folder signals its audience by its prefix:

| Prefix | Audience | Examples |
|---|---|---|
| `_name/` | **Internal only** — planning, strategy, management scratch. Never referenced in public docs. | `_strategy/` |
| `name/` (no prefix) | **Public / contributor-visible** — source, tests, docs, demo. What a user or contributor sees on GitHub. | `boyce/`, `docs/`, `demo/`, `extension/`, `test_warehouses/` |
| `.name/` | **Runtime / tooling** — config files, generated data, IDE/tool artifacts. Usually gitignored or system-managed. | `.boyce/`, `.claude/`, `.venv/` |

`_local_context/` is a runtime snapshot store (underscore = internal; contents are gitignored). `.claude/handoffs/` is where CEO→CTO architectural handoff documents live between sessions.

## Tech Stack
- Language: Python 3.10+ (repo `.venv` is 3.12 — system `python3` is 3.9, do not use it)
- Database: Amazon Redshift 1.0.121035 (PostgreSQL 8.0.2 base)
- Primary package: `boyce/` — headless FastMCP server
- Legacy code: `legacy_v0/` deleted (2026-03-11) — preserved in git history only

## Commands

```bash
# Dev setup (detects uv or python, writes .env template, installs, runs verify_eyes)
./quickstart.sh
./quickstart.sh --postgres    # also installs asyncpg

# Install
pip install -e boyce/                         # installs boyce (from boyce/pyproject.toml)
pip install -e "boyce/[postgres]"  # add asyncpg for live DB adapter

# Run the MCP server
python -m boyce.server           # FastMCP on stdio
boyce                            # same, via installed script

# Tests — offline (no DB, no LLM, ~4 seconds)
python boyce/tests/verify_eyes.py
python -m pytest boyce/tests/ -v

# Single test by name
python -m pytest boyce/tests/verify_eyes.py -v -k "test_preflight"

# Full integration test (requires Docker + LLM API key)
BOYCE_PROVIDER=anthropic BOYCE_MODEL=claude-haiku-4-5-20251001 \
ANTHROPIC_API_KEY=sk-ant-... \
python boyce/tests/live_fire/run_mission.py

# Demo smoke test — The Null Trap (requires Docker)
python demo/magic_moment/verify_demo.py
SKIP_DOCKER=1 BOYCE_DB_URL=postgresql://... python demo/magic_moment/verify_demo.py
```

## Architecture

Boyce is a privacy-first SQL compiler exposed as an MCP server. The LLM is only involved in translating natural language to a `StructuredFilter` dict; all SQL generation is deterministic.

### The Three Layers

```
Database Inspector  PostgresAdapter     — live schema introspection, read-only queries,
                                          EXPLAIN pre-flight validation

SQL Compiler        QueryPlanner        — NL → StructuredFilter via LiteLLM
                    SemanticGraph       — Dijkstra join-path resolution (NetworkX)
                    kernel.process_request() → deterministic SQL  ← ZERO LLM HERE

Query Verification  safety.py           — Redshift 1.0 lint + NULLIF cast rewrites
                    _null_trap_check()  — profiles equality-filtered columns for NULL hazards
                    EXPLAIN pre-flight  — catches invalid SQL before it reaches the DB
```

### Request Flow (`ask_boyce`)

```
NL query
    │
    ▼  Stage 1: QueryPlanner.plan_query(nl, graph)   [LiteLLM — only LLM in the pipeline]
StructuredFilter dict
    │
    ▼  Stage 2: kernel.process_request(snapshot, filter)  [deterministic, no LLM]
    │  └─ SQLBuilder.build_final_sql()
    │     └─ JoinResolver → dialect renderer
SQL string
    │
    ▼  Stage 2.5: _null_trap_check()                 [profiles equality-filtered columns]
    │                                                  warning code: "NULL_TRAP"
    │
    ▼  Stage 3: _preflight_check(sql)                [EXPLAIN via PostgresAdapter]
    │                                                  status: "verified" | "invalid" | "unchecked"
    │
    ▼  Stage 4: lint_redshift_compat(sql)            [compat_risks list]
    │
    ▼  Stage 5: _build_response_guidance()            [response guidance]
    │            next_step, present_to_user, data_reality
    │
    ▼  JSON response  {next_step, present_to_user?, data_reality?,
                       sql, validation, compat_risks, snapshot_id,
                       entities_resolved, null_trap_warnings}
```

### Response Guidance Layer

Every successful tool response includes guidance fields ABOVE the data payload
via `_build_response_guidance()`. See `../../MASTER.md` for the design framework.
This section covers Boyce-specific implementation.

**Response schema (guidance fields precede primary payload):**

```python
{
    "next_step": str,              # Always present. Directive language.
    "present_to_user": str | None, # Loss-aversion finding. Only when material.
    "data_reality": dict | None,   # Snapshot-based column insights for touched columns.
    "environment_suggestions": list | None,  # First-call-per-session only. Max 3 items.
    # ... primary payload (sql, rows, validation, etc.) ...
}
```

**Per-tool `next_step` patterns:**

| Tool | Condition | next_step |
|------|-----------|-----------|
| `ingest_source` | success | "Snapshot '{name}' is ready. Use get_schema to explore tables, or ask_boyce..." |
| `ingest_definition` | success | "Definition stored. ask_boyce will apply it automatically..." |
| `get_schema` | success | "Use this schema to construct a StructuredFilter for ask_boyce..." |
| `ask_boyce` | SQL compiled successfully | "Pass the SQL above to query_database to execute it." |
| `ask_boyce` | No StructuredFilter + no credentials | "Call ask_boyce(structured_filter=ready_filter) now..." |
| `validate_sql` | clean | "SQL passed all checks. Pass to query_database to execute." |
| `validate_sql` | issues found | "Issues detected. Resubmit through ask_boyce for automatic remediation..." |
| `query_database` | clean | "Query complete. Use profile_data on any column..." |
| `query_database` | NULL risk | "Results may be incomplete. Resubmit through ask_boyce for NULL-safe compilation." |
| `profile_data` | success | "Use these distributions to inform your next ask_boyce query..." |

**`data_reality` fires when:** SQL references a nullable column in WHERE, GROUP BY,
or JOIN ON clauses. Uses snapshot metadata only (no live DB queries). Resolves both
qualified (`films.rating`) and bare (`rating`) column references against the snapshot
via FROM clause extraction.

**`present_to_user` fires when:** NULL risk detected, EXPLAIN failure, or Redshift
compat issues. Suppressed on clean queries to prevent noise fatigue.

### StructuredFilter Shape

The contract between `QueryPlanner` (output) and `kernel.process_request` (input):

```python
{
    "concept_map": {
        "entities":   [{"entity_id": "entity:orders", "entity_name": "orders"}],
        "fields":     [{"field_id": "field:orders:revenue", "field_name": "revenue", "entity_id": "..."}],
        "metrics":    [{"metric_name": "revenue", "field_id": "...", "aggregation_type": "SUM"}],
        "dimensions": [{"field_id": "...", "field_name": "status", "entity_id": "..."}],
        "filters":    [{"field_id": "...", "operator": "=", "value": "active", "entity_id": "..."}],
    },
    "join_path":        ["entity:orders", "entity:customers"],  # Dijkstra output
    "grain_context":    {"aggregation_required": True, "grouping_fields": [...]},
    "policy_context":   {"resolved_predicates": []},            # RLS hooks (future)
    "temporal_filters": [{"field_id": "...", "operator": "trailing_interval",
                          "value": {"value": 12, "unit": "month"}}],
    "dialect":          "redshift",   # stamped by server.py before kernel call
}
```

### Snapshot Lifecycle

1. `ingest_source` — parses source via `parse_from_path()` → validates → `SnapshotStore.save()` → `_local_context/<name>.json`
2. `_compute_snapshot_hash()` — deterministic SHA-256 of canonical content
3. `SemanticGraph.add_snapshot()` — loads snapshot into in-memory NetworkX graph
4. `_local_context/` — survives server restarts; snapshots reload on next use

### Join Weight Hierarchy (in `graph.py`)
- `0.1` — Explicit dbt/LookML joins (preferred)
- `0.5` — dbt source YAML joins
- `1.0` — Foreign key joins
- `2.0` — Inferred edges (name-match heuristic)
- `100.0` — Many-to-many (avoid)

### Key Files — `boyce/src/boyce/`

| Concern | File |
|---|---|
| **MCP entry point** (8 tools) | `server.py` |
| **Response guidance layer** | `server.py` — `_build_response_guidance()` (next_step, present_to_user, data_reality, environment_suggestions) |
| **DSN persistence** | `connections.py` — `ConnectionStore` (`_local_context/connections.json`) |
| **Environment diagnostics** | `doctor.py` — `run_doctor()`, 6 check functions (incl. version), `boyce doctor` CLI |
| **Version lifecycle** | `version_check.py` — PyPI check, 24h disk cache, install detection, `boyce update`, stale-process detection |
| **Deterministic kernel** | `kernel.py` — `process_request(snapshot, filter)` |
| **Semantic graph** | `graph.py` — `SemanticGraph` (NetworkX MultiDiGraph) |
| **Protocol contract** | `types.py` — `SemanticSnapshot`, `Entity`, `FieldDef`, `JoinDef` |
| NL → StructuredFilter | `planner/planner.py` — `QueryPlanner` (LiteLLM) |
| SQL generation | `sql/builder.py` — `SQLBuilder.build_final_sql()` |
| Join resolution | `sql/join_resolver.py` |
| Dialect rendering | `sql/dialects.py` — redshift / postgres / duckdb / bigquery |
| Source parsers (10) | `parsers/` — dbt, lookml, sqlite, ddl, csv, parquet, django, sqlalchemy, prisma |
| Live DB adapter | `adapters/postgres.py` — `PostgresAdapter` (read-only, asyncpg) |
| Redshift safety | `safety.py` — `lint_redshift_compat()`, `transform_sql_for_redshift_safety()` |
| Snapshot persistence | `store.py` — `SnapshotStore` (`_local_context/` JSON files) |
| Business definitions | `store.py` — `DefinitionStore` (`_local_context/` JSON files) |
| Validation + hashing | `validation.py` — `validate_snapshot()`, `_compute_snapshot_hash()` |
| Audit log | `audit.py` — `AuditLog` (append-only JSONL) |

### MCP Tools (8)

| Tool | Purpose |
|---|---|
| `ingest_source` | Parse + ingest a SemanticSnapshot from any supported format |
| `ingest_definition` | Store a certified business definition (injected into planner context at query time) |
| `get_schema` | Return full schema (entities, fields, joins) + authority claim + StructuredFilter docs |
| `ask_boyce` | NL→SQL: MCP host path (StructuredFilter, zero credentials), CLI/HTTP path (NL+LLM), schema guidance fallback (returns ready_filter) |
| `validate_sql` | Validate hand-written SQL — EXPLAIN pre-flight, Redshift lint, NULL risk — without executing |
| `query_database` | Execute read-only SELECT with live NULL trap profiling, EXPLAIN pre-flight, metadata query detection |
| `profile_data` | Profile a column: null count/pct, distinct count, min/max |
| `check_health` | Operational health check — DB connectivity, snapshot freshness, version info, actionable fix commands |

Note: `build_sql` and `solve_path` are internal functions (not MCP tools). Host LLM uses `get_schema` + `ask_boyce` directly.

### Key Tests / Scripts

| Script | What it covers |
|---|---|
| `tests/verify_eyes.py` | 15 offline unit tests — no DB, no LLM (~4s) |
| `tests/test_audit.py` | AuditLog: file creation, JSON validity, appending, tail() |
| `tests/test_definitions.py` | DefinitionStore: upsert, overwrite, isolation, context string |
| `tests/test_parsers.py` | All 10 parsers: detect, parse, protocol compliance, registry |
| `tests/test_discovery.py` | Auto-discovery: detect, resolve, ingest for all parser types (27 tests) |
| `tests/test_init.py` | Init wizard: detect_hosts, generate_server_entry, merge_config, _merge_toml_config (Codex/TOML) — 56 tests |
| `tests/test_response_guidance.py` | Response guidance layer: column extraction, bare column resolution, next_step/present_to_user/data_reality/environment_suggestions, integration (34 tests) |
| `tests/test_connections.py` | ConnectionStore: save/load/touch/remove/list_all, DSN persistence, edge cases (16 tests) |
| `tests/test_doctor.py` | Doctor checks: version, editors, database, snapshots, sources, server, orchestrator, JSON output (20 tests) |
| `tests/test_version_check.py` | Version lifecycle: PyPI fetch, disk cache, classify update, stale-process, install detection, cooldown, nudge filtering, run_update (37 tests) |
| `tests/live_fire/run_mission.py` | Full pipeline: Docker Postgres + LLM + EXPLAIN |
| `demo/magic_moment/verify_demo.py` | Demo smoke test — NULL Trap distribution check |
| `quickstart.sh` | Dev setup: install, `.env` template, verify_eyes |

### Demo Kit (`demo/magic_moment/`)

Self-contained "Null Trap" scenario for recording the magic-moment demo:
- `seed.sql` — 1,000 rows: 500 active + 200 cancelled (recent last_login) + 300 NULL status
- `snapshot.json` — SemanticSnapshot describing the table
- `verify_demo.py` — profiles the data and asserts the trap distribution
- `DEMO_SCRIPT.md` — operator script for a 30-second recording

## Critical Redshift/SQL Constraints
- Use `||` for string concatenation — NEVER `CONCAT()`
- Use `PERCENT_RANK()` instead of `NTILE()`
- No modern PostgreSQL functions: no `STRING_AGG`, no `FILTER`, no `LATERAL`
- No `GENERATED ALWAYS AS` columns
- `IDENTITY` columns use Redshift syntax
- `DISTKEY` and `SORTKEY` must be specified on all new tables
- Use `GETDATE()` not `NOW()` for current timestamp
- No `RECURSIVE` CTEs
- `VARCHAR` max is 65535

### VS Code Extension — `extension/`

Thin TypeScript GUI over `boyce serve --http`. All intelligence stays server-side.
The extension never touches LLMs or credentials directly.

```bash
# Dev setup
cd extension && npm install

# Compile
npm run compile          # tsc -p ./
npm run watch            # tsc -watch

# Package for marketplace
npm run package          # produces .vsix

# Lint
npm run lint
```

| File | Purpose |
|------|---------|
| `src/extension.ts` | Main entry — 5 commands, status bar, schema tree registration |
| `src/client.ts` | `BoyceClient` — typed HTTP client for 8 HTTP endpoints (7 of 8 MCP tools + `/health`; `check_health` not yet wired) |
| `src/process.ts` | `BoyceProcess` — auto-spawns `boyce serve --http`, health polling, graceful shutdown |
| `src/types.ts` | TypeScript interfaces mirroring `boyce.http_api` + `boyce.types` contracts |
| `src/panels/chatPanel.ts` | Webview chat panel — NL input → `/chat` → rendered SQL with "Run SQL" buttons |
| `src/providers/schemaTreeProvider.ts` | Sidebar tree: entities → fields, type-aware icons, FK annotations |
| `package.json` | VS Code manifest — commands, activity bar, keybindings, configuration |

**Status:** Scaffold complete (compiles clean, zero errors). Steps 1-4 of Block 1b plan built.
Remaining: SQL editor integration (CodeLens), setup wizard, marketplace publish.
See `_strategy/plans/block-1b-vscode-extension.md` for full plan.

## Known Gaps (check before working in these areas)
- `pytest` is not in `pyproject.toml` deps — CI installs it separately
- `SemanticGraph` is in-memory only; snapshots persist as files in `_local_context/` but the graph is rebuilt from scratch on each server start
- `process_request()` takes a single snapshot — multi-snapshot merge not yet implemented
- `PostgresAdapter` only supports asyncpg (Postgres/Redshift) — no BigQuery or DuckDB live adapter yet
- CI/CD workflows (`.github/workflows/`) reference stale paths — must be updated before enabling CI
- `legacy_v0/` has been deleted (2026-03-11) — historical code preserved in git history only

## Workflow Rules
- Always verify `python boyce/tests/verify_eyes.py` passes before and after changes
- **CLI change rule:** Any change to `cli.py`, `scan.py`, or `init_wizard.py` that adds, removes, or renames a subcommand/flag/exit-code contract MUST include a corresponding update to `boyce/tests/test_cli_smoke.py`. The smoke test is the contract registry for CLI behavior. No CLI PR merges without updating it.
- Commit granularly with descriptive messages
- When writing SQL migrations, include both UP and DOWN
- Use `git diff` to verify changes before committing

## Context Window Discipline
- During any multi-step analysis or investigation, write findings to a file before moving to the next step. Do not hold conclusions only in context.
- When a task produces a significant output (audit, comparison, dependency map, etc.), always write it to disk unprompted. Never assume the conversation will persist.
- If a session is clearly getting long, proactively tell the user to run `/compact` before continuing.

## Code Standards
- Type hints on all Python functions
- Docstrings on public interfaces
- No bare `except:` clauses
- F-strings for formatting (no `.format()` or `%`)
