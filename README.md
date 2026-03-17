# Boyce: Semantic Protocol & Safety Layer for Agentic Database Workflows

> **Don't let your agents guess. Give them Eyes.**
> Boyce connects LLMs to live database context with built-in safety rails.

Named for [Raymond F. Boyce](https://en.wikipedia.org/wiki/Raymond_F._Boyce), co-inventor of SQL (1974) and co-author of Boyce-Codd Normal Form (BCNF).

AI agents querying databases without proper context generate unreliable SQL — working from incomplete schemas, inferring column names, guessing join paths. Boyce gives agents the structured database intelligence they need to generate correct, safe SQL every time — through three interconnected systems:

| Layer | What it does |
|---|---|
| 🧠 **The Brain** | `ask_boyce` — NL → StructuredFilter → deterministic SQL. Zero LLM in the SQL builder. Same inputs, same SQL, byte-for-byte, every time. |
| 👁️ **The Eyes** | `query_database` / `profile_data` — Live Postgres/Redshift adapters let your agent see real schema and real data distributions before writing a single filter. |
| 🛡️ **The Nervous System** | Pre-flight `EXPLAIN` loops on every generated query. Bad SQL is caught at planning time, not at 2am in your on-call rotation. |

**Why does this matter?** → [The Null Trap: Your AI Agent's SQL Is Correct. The Answer Is Still Wrong.](https://convergentmethods.com/boyce/null-trap/)

---

## Install

**Requires Python 3.10+**

```bash
pip install boyce

# With live Postgres/Redshift adapter (enables EXPLAIN pre-flight + column profiling)
pip install "boyce[postgres]"
```

```bash
# uv (recommended)
uv pip install boyce
uv pip install "boyce[postgres]"
```

**From source:**
```bash
git clone https://github.com/boyce-io/boyce
uv pip install -e "boyce/"
```

---

## Quickstart

After installing, run `boyce init` to configure your MCP host automatically:

```bash
boyce init
```

The wizard detects Claude Desktop, Cursor, Claude Code, and JetBrains (DataGrip, IntelliJ, etc.), and writes the correct config block for each.

**Developing from source?** The repo includes a setup script:

```bash
./quickstart.sh   # detects uv or python, installs package, writes .env template
```

---

## Configure Your MCP Host

The fastest path is `boyce init` — it detects your MCP host and writes the config automatically:

```bash
boyce init
```

Or configure manually. **There are two setup paths depending on your host:**

---

### Path 1 — MCP Hosts (No LLM key required)

If you're using **Claude Desktop, Cursor, Claude Code, Codex, Cline, Windsurf, JetBrains (DataGrip,
IntelliJ), or any MCP-compatible host**, you do not need to configure an LLM provider for Boyce.
The host's own model handles reasoning — Boyce supplies the schema context and deterministic SQL
compiler via `get_schema` and `ask_boyce`. Only `BOYCE_DB_URL` is needed (and even that is optional).

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "env": {
        "BOYCE_DB_URL": "postgresql://user:pass@host:5432/db"
      }
    }
  }
}
```

**Cursor** (`.cursor/mcp.json` in project root):

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "env": {
        "BOYCE_DB_URL": "postgresql://user:pass@host:5432/db"
      }
    }
  }
}
```

---

### Path 2 — With Boyce's Built-in NL→SQL

If you're using the CLI (`boyce ask`), HTTP API, or a non-MCP client (e.g., the VS Code
extension), configure Boyce's internal query planner with your LLM provider:

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "env": {
        "BOYCE_PROVIDER": "anthropic",
        "BOYCE_MODEL": "claude-sonnet-4-6",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "BOYCE_DB_URL": "postgresql://user:pass@host:5432/db"
      }
    }
  }
}
```

Boyce supports any LLM provider available through [LiteLLM](https://docs.litellm.ai/docs/providers):
Anthropic, OpenAI, Ollama (local), vLLM (local), Azure, Bedrock, Vertex, Mistral, and more.

---

`BOYCE_DB_URL` is optional on both paths. Without it, Boyce runs in schema-only mode — SQL
generation still works; EXPLAIN pre-flight and live query tools return `"status": "unchecked"`.

---

## Environment Variables

| Variable | When needed | Example | Purpose |
|---|---|---|---|
| `BOYCE_PROVIDER` | Path 2 only (CLI/HTTP/non-MCP) | `anthropic` | LiteLLM provider name |
| `BOYCE_MODEL` | Path 2 only (CLI/HTTP/non-MCP) | `claude-sonnet-4-6` | Model ID passed to LiteLLM |
| `ANTHROPIC_API_KEY` | When using Anthropic | `sk-ant-...` | Anthropic credentials |
| `OPENAI_API_KEY` | When using OpenAI | `sk-...` | OpenAI credentials |
| `BOYCE_DB_URL` | Optional (either path) | `postgresql://user:pass@host:5432/db` | asyncpg DSN — enables EXPLAIN pre-flight + live query tools |
| `BOYCE_HTTP_TOKEN` | Path 2 HTTP API only | `my-secret-token` | Bearer token for `boyce serve --http` |
| `BOYCE_STATEMENT_TIMEOUT_MS` | Optional | `30000` | Per-statement timeout in ms (default: 30s) |

---

## MCP Tools

| Tool | Description |
|---|---|
| `ingest_source` | Parse a `SemanticSnapshot` from dbt manifest, dbt project, LookML, DDL, SQLite, Django, SQLAlchemy, Prisma, CSV, or Parquet. |
| `ingest_definition` | Store a certified business definition — injected automatically at query time. |
| `get_schema` | Return full schema context + StructuredFilter format docs. Used by MCP hosts so the host LLM can construct queries without a Boyce API key. |
| `ask_boyce` | Full NL → SQL pipeline: query planner (LiteLLM) → deterministic kernel → NULL trap check → EXPLAIN pre-flight. |
| `validate_sql` | Validate hand-written SQL — EXPLAIN pre-flight, Redshift lint, NULL risk — without executing. |
| `query_database` | Execute a read-only `SELECT` against the live database. Write operations rejected at two independent layers. |
| `profile_data` | Null %, distinct count, min/max for any column — surface data quality issues before they affect query results. |

---

## Architecture

```
SemanticSnapshot (JSON)
        │
        ▼  ingest_source
 ┌─────────────────────────────────────────────┐
 │          SemanticGraph (NetworkX)            │  ← in-memory, loaded per session
 │  nodes = entities (tables/views/dbt models) │
 │  edges = joins  (weighted by confidence)    │
 └─────────────────────────────────────────────┘
        │                         │
        ▼  ask_boyce              ▼  (internal)
  QueryPlanner                 Dijkstra
  (LiteLLM)                    join resolver
  NL → StructuredFilter             │
        │                           │
        └──────────┬────────────────┘
                   ▼
           kernel.process_request()          ← ZERO LLM HERE
           SQLBuilder (dialect-aware)
                   │
                   ▼
           EXPLAIN pre-flight                ← 🛡️ Nervous System
           (PostgresAdapter)
                   │
                   ▼
            SQL + validation result
```

**Dialect support:** `redshift`, `postgres`, `duckdb`, `bigquery`

**Redshift safety rails** (`safety.py`): Automatic linting for `LATERAL`, `JSONB`, `REGEXP_COUNT`, lookahead regex patterns, and numeric cast rewrites for Redshift 1.0 (PG 8.0.2).

---

## Scan CLI

```bash
# Scan a single file
boyce scan demo/magic_moment/manifest.json

# Scan a directory (auto-detects all parseable sources)
boyce scan ./my-project/ -v

# Save snapshots for MCP server use
boyce scan ./my-project/ --save
```

10 parsers: dbt manifest, dbt project, LookML, SQLite, DDL, CSV, Parquet, Django, SQLAlchemy, Prisma.

---

## Verify the Install

```bash
# Unit tests — no DB required, runs in ~4 seconds
python boyce/tests/verify_eyes.py

# Expected output:
# Ran 15 tests in 3.5s
# OK
# ✅  All checks passed.
```

---

## SemanticSnapshot Format

The `ingest_source` tool accepts a `SemanticSnapshot` JSON dict. Minimal example:

```json
{
  "snapshot_id": "<sha256>",
  "source_system": "dbt",
  "entities": {
    "entity:orders": {
      "id": "entity:orders",
      "name": "orders",
      "schema": "public",
      "fields": ["field:orders:order_id", "field:orders:revenue"]
    }
  },
  "fields": {
    "field:orders:order_id": {
      "id": "field:orders:order_id",
      "entity_id": "entity:orders",
      "name": "order_id",
      "field_type": "ID",
      "data_type": "INTEGER"
    }
  },
  "joins": []
}
```

See `boyce/tests/live_fire/mock_snapshot.json` for a complete field/entity example.

---

## Project Layout

```
boyce/                          ← PRIMARY — headless FastMCP server + pip package
├── boyce/
│   ├── server.py               ← MCP entry point (7 tools)
│   ├── kernel.py               ← Deterministic SQL kernel
│   ├── graph.py                ← SemanticGraph (NetworkX)
│   ├── safety.py               ← Redshift compatibility rails
│   ├── types.py                ← Protocol contract (Pydantic)
│   ├── scan.py                 ← Scan CLI (boyce scan)
│   ├── sql/                    ← SQLBuilder, dialect layer, join resolver
│   ├── parsers/                ← 10 parsers (dbt, lookml, ddl, sqlite, csv, etc.)
│   ├── planner/                ← QueryPlanner (LiteLLM → StructuredFilter)
│   └── adapters/               ← PostgresAdapter (Eyes)
└── tests/
    ├── verify_eyes.py          ← 15-test suite, no DB required
    ├── test_parsers.py         ← Parser tests (all 10 parsers)
    ├── test_scan.py            ← Scan CLI tests
    └── live_fire/              ← Docker Compose integration tests
_management_documents/          ← Architecture docs and decision records
```

---

## Status

| Capability | Status |
|---|---|
| NL → SQL (deterministic kernel) | Operational |
| SemanticGraph (join resolution) | Operational |
| 10 source parsers | Operational |
| Scan CLI (`boyce scan`) | Operational |
| PostgresAdapter (read-only) | Operational |
| EXPLAIN pre-flight validation | Operational |
| NULL Trap detection | Operational |
| Redshift 1.0 safety linting | Operational |
| Snapshot persistence across restarts | Operational |
| Audit logging (append-only JSONL) | Operational |
| Business definitions (`ingest_definition`) | Operational |
| Multi-snapshot merge | Planned |

---

## Support

- **Troubleshooting guide:** [docs/troubleshooting.md](docs/troubleshooting.md)
- **Local LLM setup (Ollama/vLLM):** [docs/local-llm-setup.md](docs/local-llm-setup.md)
- **Bug reports:** [GitHub Issues](https://github.com/boyce-io/boyce/issues/new?template=bug_report.yml)
- **Setup help:** [GitHub Issues](https://github.com/boyce-io/boyce/issues/new?template=setup_help.yml)
- **Email:** [will@convergentmethods.com](mailto:will@convergentmethods.com) — for issues involving credentials or sensitive config

---

*Copyright 2026 Convergent Methods. MIT License.*
