# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

---

## Role

CTO / Architect. Follows the four-phase protocol defined in `~/.claude/CLAUDE.md`: Assess & Plan → Build → Verify → Ship.

### Session Protocol
1. Read `_strategy/MASTER.md` for current priorities
2. Check for active plans in `_strategy/plans/`
3. If session is getting long (>30 messages): *"Run `/compact` to preserve context."*

### Model Tiering
Follows the Mandatory Model Gate defined in `~/.claude/CLAUDE.md`.

---

## Master Planning Document

`_strategy/MASTER.md` is the single source of truth for product direction, execution plan, and architectural decisions. Read it at the start of any non-trivial session. Do not create new strategy documents — update MASTER.md directly.

---

## Tech Stack
- Language: Python 3.10+ (repo `.venv` is 3.12 — system `python3` is 3.9, do not use it)
- Database: Amazon Redshift 1.0.121035 (PostgreSQL 8.0.2 base)
- Primary package: `boyce/` — headless FastMCP server
- Legacy code: `legacy_v0/` — quarantined v1.0.0 package, do not import from it in new code

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
👁️  Eyes          PostgresAdapter     — live schema introspection, read-only queries,
                                         EXPLAIN pre-flight validation

🧠  Brain          QueryPlanner        — NL → StructuredFilter via LiteLLM
                   SemanticGraph       — Dijkstra join-path resolution (NetworkX)
                   kernel.process_request() → deterministic SQL  ← ZERO LLM HERE

🛡️  Nervous System safety.py          — Redshift 1.0 lint + NULLIF cast rewrites
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
    ▼  JSON response  {sql, validation, compat_risks, snapshot_id,
                       entities_resolved, null_trap_warnings}
```

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

### MCP Tools (6)

| Tool | Purpose |
|---|---|
| `ingest_source` | Parse + ingest a SemanticSnapshot from any supported format |
| `ingest_definition` | Store a certified business definition (injected into planner context at query time) |
| `solve_path` | Find optimal semantic join path between two entities via Dijkstra |
| `ask_boyce` | Full NL → SQL pipeline with NULL trap detection and EXPLAIN pre-flight |
| `query_database` | Execute read-only SELECT against live database (two-level write rejection) |
| `profile_data` | Profile a column: null count/pct, distinct count, min/max |

### Key Tests / Scripts

| Script | What it covers |
|---|---|
| `tests/verify_eyes.py` | 15 offline unit tests — no DB, no LLM (~4s) |
| `tests/test_audit.py` | AuditLog: file creation, JSON validity, appending, tail() |
| `tests/test_definitions.py` | DefinitionStore: upsert, overwrite, isolation, context string |
| `tests/test_parsers.py` | All 10 parsers: detect, parse, protocol compliance, registry |
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

## Known Gaps (check before working in these areas)
- `pytest` is not in `pyproject.toml` deps — CI installs it separately
- `SemanticGraph` is in-memory only; snapshots persist as files in `_local_context/` but the graph is rebuilt from scratch on each server start
- `process_request()` takes a single snapshot — multi-snapshot merge not yet implemented
- `PostgresAdapter` only supports asyncpg (Postgres/Redshift) — no BigQuery or DuckDB live adapter yet
- CI/CD workflows (`.github/workflows/`) reference stale paths — must be updated before enabling CI
- `legacy_v0/src/datashark/` v1.0.0 package — do not import from it in new code

## Workflow Rules
- Always verify `python boyce/tests/verify_eyes.py` passes before and after changes
- Commit granularly with descriptive messages
- When writing SQL migrations, include both UP and DOWN
- Use `git diff` to verify changes before committing

## Context Window Discipline
- During any multi-step analysis or investigation, write findings to a file in `_management_documents/` before moving to the next step. Do not hold conclusions only in context.
- When a task produces a significant output (audit, comparison, dependency map, etc.), always write it to disk unprompted. Never assume the conversation will persist.
- If a session is clearly getting long, proactively tell the user to run `/compact` before continuing.

## Code Standards
- Type hints on all Python functions
- Docstrings on public interfaces
- No bare `except:` clauses
- F-strings for formatting (no `.format()` or `%`)
