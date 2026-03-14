# MCP Directory Submissions — Boyce

Pre-drafted content for all four MCP/AI tool registries. Copy-paste on publish day.
Reference: `ConvergentMethods/ASSETS.md` → Publish Surfaces → MCP directories.

**Prerequisite:** PyPI publish complete and package is live at https://pypi.org/project/boyce/

---

## Canonical Content (source of truth for all submissions)

### Name
```
Boyce
```

### Tagline (≤ 80 chars)
```
Semantic protocol and safety layer for agentic database workflows
```

### Short description (≤ 160 chars — PyPI/Twitter style)
```
Give AI agents structured database intelligence. Deterministic SQL, NULL trap detection, EXPLAIN pre-flight. MIT licensed.
```

### Long description (Markdown, ~300 words)

```markdown
Boyce is an MCP server that gives AI agents structured database intelligence to generate
correct, safe SQL — deterministically.

**The problem:** AI agents querying databases without context produce unreliable SQL. They
guess join paths, miss NULL distributions, and silently return wrong results. A naive equality
filter on a column with 30% NULLs silently drops those rows — and the agent never knows.

**What Boyce does:**

- 🧠 **The Brain** — NL → StructuredFilter → deterministic SQL. Same inputs, same SQL,
  byte-for-byte, every time. Zero LLM in the SQL compiler.
- 👁 **The Eyes** — Live Postgres/Redshift adapter. Real schema, real NULL distributions
  before writing a single filter.
- 🛡 **The Nervous System** — EXPLAIN pre-flight on every query. Bad SQL caught at planning
  time, not at 2am.

**For MCP hosts (Claude Desktop, Cursor, Claude Code, etc.):** No API key needed. The host
LLM reads the schema via `get_schema`, constructs a query, and Boyce compiles deterministic
SQL. Zero configuration beyond `pip install boyce`.

**7 MCP tools:** `ingest_source`, `ingest_definition`, `get_schema`, `ask_boyce`, `validate_sql`, `query_database`, `profile_data`

**10 source parsers:** dbt manifest, dbt project, LookML, raw DDL, SQLite, Django, SQLAlchemy,
Prisma, CSV, Parquet — auto-detected via `boyce-scan`

**Dialect support:** Redshift, Postgres, DuckDB, BigQuery

Named for [Raymond F. Boyce](https://en.wikipedia.org/wiki/Raymond_F._Boyce), co-inventor
of SQL (1974). MIT licensed.
```

### Install command
```
pip install boyce
```

### GitHub URL
```
https://github.com/boyce-io/boyce
```

### PyPI URL
```
https://pypi.org/project/boyce/
```

### Product page
```
https://convergentmethods.com/boyce/
```

### Agent docs (for registries that support it)
```
https://convergentmethods.com/boyce/llms.txt
```

### Category / Tags
```
Categories: Database, SQL, Data Engineering, Developer Tools, Safety
Tags: mcp, sql, database, postgresql, redshift, duckdb, bigquery, dbt, semantic-layer, agents, llm
```

### Tool count
```
7
```

### Language / Runtime
```
Python 3.10+
```

### License
```
MIT
```

---

## Registry-Specific Submission Notes

### Smithery — https://smithery.ai

- Submit at: https://smithery.ai/submit (or search for "submit server")
- Smithery indexes from GitHub — they may auto-discover via the repo or require a PR to their registry
- Verify the `boyce` package appears correctly after PyPI publish
- Use the long description above; Smithery renders Markdown

### PulseMCP — https://pulsemcp.com

- Submit at: https://pulsemcp.com/submit
- Typically requires: name, description, GitHub URL, category
- Check if they have a JSON manifest requirement (some registries want a `mcp.json` in the repo root)

### mcp.so

- Submit at: https://mcp.so (look for "Add Server" or similar)
- Newer registry, submission process may vary
- Use short description + tags above

### Glama — https://glama.ai

- Submit at: https://glama.ai/mcp/servers (look for submission link)
- Glama indexes MCP servers; may pull from GitHub automatically
- Use canonical content above; adjust to their character limits

---

## Pre-Submission Checklist

- [ ] PyPI publish complete — `pip install boyce` works in a clean env
- [ ] GitHub repo is public (boyce-io/boyce)
- [ ] README is publish-ready (reviewed, correct version, no stale content)
- [ ] Product page live at convergentmethods.com/boyce/
- [ ] llms.txt live at convergentmethods.com/boyce/llms.txt
- [ ] Version number consistent across: PyPI, README badge, llms-full.txt, MASTER.md

---

## Post-Submission

After submitting to each registry:
- Note submission date in this file
- Check indexing within 24-48h (some are manual review, some are auto)
- If a registry requires changes (description format, metadata, etc.), update canonical content above and re-submit
- Add registry URLs to ASSETS.md once listed

---

*Draft prepared 2026-03-13. Submit on PyPI publish day.*
