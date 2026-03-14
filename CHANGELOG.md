# Changelog

All notable changes to Boyce are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.1.0] — 2026-03-14

First functional release. `0.0.1` was a PyPI namespace placeholder only.

### Added

- **7 MCP tools** via FastMCP stdio server:
  - `ingest_source` — parse SemanticSnapshot from dbt manifest, dbt project, LookML, DDL, SQLite, Django, SQLAlchemy, Prisma, CSV, Parquet (10 parsers, auto-detected)
  - `ingest_definition` — store certified business definitions, auto-injected at query time
  - `get_schema` — return full schema context + StructuredFilter documentation for host-LLM reasoning
  - `ask_boyce` — tri-modal NL→SQL pipeline (Mode A: StructuredFilter, Mode B: NL+credentials, Mode C: NL fallback)
  - `validate_sql` — EXPLAIN pre-flight + Redshift lint + NULL risk analysis without executing
  - `query_database` — read-only SELECT execution against live database (write rejection at two layers)
  - `profile_data` — column profiling: null %, distinct count, min/max
- **`boyce-init` setup wizard** — auto-detects and configures 6 MCP host platforms: Claude Desktop, Cursor, Claude Code, VS Code, JetBrains/DataGrip, Windsurf
- **`boyce-scan` CLI** — walks directories, auto-detects all parseable sources, produces JSON report
- **`boyce ask "..."` CLI** — NL→SQL, output to stdout (requires `BOYCE_PROVIDER` + `BOYCE_MODEL`)
- **`boyce chat "..."` CLI** — conversational mode routing through `ask_boyce`
- **`boyce serve --http` HTTP API** — Starlette REST API with Bearer auth
- **Deterministic SQL kernel** — same inputs produce byte-for-byte identical SQL, zero LLM calls
- **SemanticGraph** — in-memory NetworkX MultiDiGraph with Dijkstra join-path resolution
- **ask_boyce tri-modal routing** — Mode A (host LLM + StructuredFilter, zero credentials), Mode B (NL + BOYCE_PROVIDER), Mode C (NL fallback, returns schema guidance)
- **NULL trap detection** — profiles equality-filtered columns for NULL distributions before returning SQL
- **EXPLAIN pre-flight** — validates every generated query at planning time via PostgresAdapter
- **Redshift safety layer** — lint + NULLIF cast rewrites for Redshift 1.0 (PG 8.0.2 base): LATERAL, JSONB, REGEXP_COUNT, CONCAT, STRING_AGG, FILTER(WHERE), RECURSIVE CTE
- **10 source parsers** — dbt_manifest, dbt_project, lookml, ddl, sqlite, django, sqlalchemy, prisma, csv, parquet
- **Snapshot persistence** — JSON files in `_local_context/`, survives server restarts
- **Schema freshness** — Tier 2 (mtime + auto re-ingest), Tier 3 (live DB drift detection via information_schema)
- **Audit log** — append-only JSONL of all queries
- **LiteLLM integration** — `BOYCE_PROVIDER` + `BOYCE_MODEL` env vars; supports Anthropic, OpenAI, Ollama, vLLM, Azure, Bedrock, Vertex, Mistral, 100+ providers
- **PostgresAdapter** — read-only asyncpg adapter for Postgres/Redshift
- **Business definitions** — `ingest_definition` + `DefinitionStore`, context auto-injected at query time
- **Multi-dialect SQL** — redshift, postgres, duckdb, bigquery
- **Public API exports** — `from boyce import process_request, SemanticSnapshot, lint_redshift_compat, SemanticGraph`
- **`pip install "boyce[postgres]"`** — optional asyncpg extra for live DB adapter
- **`pip install "boyce[parquet]"`** — optional pyarrow extra for Parquet parser

### Fixed (testing sprint — 13 bugs resolved, March 13)

- `boyce-init` wrote `.claude/settings.json` for Claude Code — corrected to `.mcp.json`
- `ingest_source` tool description listed only 3 formats — now lists all 10 parsers
- Snapshot hash mismatch on re-ingest — `source_path` injection broke hash determinism; recomputed after mutation
- `COUNT("metric_name")` — builder used alias string instead of resolving field_id to column name
- `GROUP BY "field:Entity:col"` — builder leaked raw field_id instead of resolved column name
- ORDER BY/LIMIT not generated — added explicit guidance in `ask_boyce` docstring for host LLM
- `temporal_filters` at StructuredFilter top level silently dropped — never passed to WHERE builder
- `ask_boyce` docstring missing `date_trunc_field` / `date_trunc_unit` guidance
- LookML parser: directory ingest failed — `detect()` matched files only, not directories
- LookML parser: model file produced 0 entities — `include` directives not followed; fixed by parsing all `.lkml` files in directory and merging
- LookML join builder: used explore `base_view` instead of `sql_on` source view for `source_entity` / field — caused validation failures
- `ingest_source` (source_path path) did not validate snapshot before saving — silent invalid snapshots possible
- `safety.py` missing 4 Redshift lint rules: CONCAT, STRING_AGG, FILTER(WHERE), RECURSIVE CTE
- `concept_map.fields` ignored in SELECT — builder fell back to `SELECT *` for raw field queries; fixed to use fields list for projection
- Filter operator aliases rejected — `NOT_IN`, `IS_NULL`, `IS_NOT_NULL` not normalized; fixed at both validator and builder
- Django parser FK target resolution used `class_name.lower()` — diverged from `db_table` override (e.g. `"Customer"` → `"customer"` vs entity registered as `"customers"`)

### Architecture

- `src` layout (`boyce/src/boyce/`) — eliminates CWD namespace conflict
- `build_sql` and `solve_path` internalized — not MCP tools; host LLM constructs StructuredFilter and calls `ask_boyce` Mode A
- `validate_sql` added as new MCP tool (EXPLAIN pre-flight + lint + NULL risk without executing)
- Intent classifier removed — CLI and HTTP API route directly through `ask_boyce`

---

## [0.0.1] — 2026-03-04

PyPI namespace placeholder. No functional code.
