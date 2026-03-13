# Troubleshooting

Common issues and fixes. If you're still stuck after trying these, open a
[Setup Help issue](https://github.com/boyce-io/boyce/issues/new?template=setup_help.yml)
or email [will@convergentmethods.com](mailto:will@convergentmethods.com).

---

## Installation

### `boyce` command not found after `pip install boyce`

Your PATH doesn't include pip's script directory.

```bash
# Find where pip installed the script
python -m site --user-base   # e.g. /Users/you/Library/Python/3.12

# Add to your shell config (~/.zshrc or ~/.bashrc)
export PATH="$HOME/Library/Python/3.12/bin:$PATH"
```

Or install into a virtual environment:

```bash
python -m venv .venv && source .venv/bin/activate
pip install boyce
boyce  # now works
```

### Python version error

Boyce requires Python 3.10+. Check your version:

```bash
python --version
```

If you're on 3.9 or older, use `pyenv` or `uv` to install a newer version:

```bash
uv python install 3.12
uv pip install boyce
```

---

## boyce-init

### `boyce-init` can't find my MCP host config

The wizard looks for config files at standard paths. If it doesn't detect your host automatically,
configure manually using the snippets in the [README](../README.md#configure-your-mcp-host).

Common config locations:

| Host | Config file |
|------|-------------|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cursor | `.cursor/mcp.json` in your project root |
| Claude Code | `.claude/settings.json` in your project root |
| Cline / Continue.dev | VSCode settings or `.vscode/mcp.json` |

### `boyce-init` wrote a config but the MCP host still doesn't connect

1. **Restart the host completely** — most MCP hosts only read config on startup.
2. **Check the path** — verify the config file is in the right location for your OS.
3. **Validate JSON** — a syntax error in the config file will silently break everything.
   Run `python -m json.tool /path/to/config.json` to check.
4. **Check for `boyce` in PATH** — the MCP host spawns `boyce` as a subprocess. If your
   shell PATH isn't inherited by the host, it won't find the command. Use an absolute path:
   ```json
   { "command": "/Users/you/.local/bin/boyce" }
   ```

---

## Schema / Snapshots

### `get_schema` returns no tables

Your snapshot hasn't been ingested yet. Run `ingest_source` with the path to your
dbt manifest, DDL file, SQLite database, or other source:

```
ingest_source(path="/path/to/your/target/manifest.json")
```

Or use the scan CLI to auto-detect sources in a project directory:

```bash
boyce-scan ./my-project/ --save
```

### Snapshots disappear after restarting the server

Snapshots persist to `_local_context/` in the directory where Boyce runs. If Boyce starts
in a different working directory each time, it won't find the previous snapshots.

Fix: always start Boyce from the same directory, or configure `BOYCE_SNAPSHOT_DIR` to an
absolute path (planned feature — track [#issue](https://github.com/boyce-io/boyce/issues)).

### `ingest_source` returns a parse error

Check which parser is being used:

```bash
boyce-scan /path/to/file -v   # shows detected format
```

If the format is wrong, specify it explicitly in `ingest_source`:

```
ingest_source(path="/path/to/schema.sql", source_type="ddl")
```

Supported source types: `dbt_manifest`, `dbt_project`, `lookml`, `sqlite`, `ddl`, `csv`,
`parquet`, `django`, `sqlalchemy`, `prisma`.

---

## NL→SQL (ask_boyce)

### "No LLM provider configured" error

`ask_boyce` requires `BOYCE_PROVIDER` and `BOYCE_MODEL`. These are only needed for the
NL→SQL planner — if you're using an MCP host (Claude Desktop, Cursor, Claude Code), the
host's own LLM handles the routing and you can use `get_schema` + `build_sql` instead.

For direct NL→SQL via `ask_boyce`, set:

```bash
export BOYCE_PROVIDER=anthropic        # or openai, ollama, etc.
export BOYCE_MODEL=claude-haiku-4-5-20251001  # or gpt-4o-mini, etc.
export ANTHROPIC_API_KEY=sk-ant-...    # matching provider key
```

### NL→SQL produces wrong SQL or resolves the wrong table

1. **Check your snapshot** — use `get_schema` to see what entities are registered.
   If the table isn't there, re-run `ingest_source`.
2. **Improve descriptions** — the planner uses entity and field descriptions to resolve
   intent. Richer descriptions in your dbt YAML or as `ingest_definition` entries produce
   better results.
3. **Explicit entity name** — if you have ambiguous entity names, be explicit:
   _"Show me orders from the `public.orders` table"_.

### SQL generation works but EXPLAIN returns "invalid"

The generated SQL has a syntax error or references a table/column that doesn't exist in
your live database. This often means:

- Your snapshot is out of sync with the actual schema — re-run `ingest_source`
- You're using a dialect mismatch — set `BOYCE_DIALECT` to match your database
  (`redshift`, `postgres`, `duckdb`, `bigquery`)

---

## Database Connection

### `validation.status` is always "unchecked"

EXPLAIN pre-flight requires a live database connection. Set `BOYCE_DB_URL`:

```bash
export BOYCE_DB_URL=postgresql://user:pass@host:5432/dbname
```

Without it, Boyce runs in schema-only mode — SQL generation still works, but no
live validation.

### "Could not connect to database" error

1. Check that `BOYCE_DB_URL` is a valid asyncpg DSN (PostgreSQL format).
2. Check that the `boyce[postgres]` extra is installed: `pip install "boyce[postgres]"`.
3. Check network access — firewall rules, VPN, or security group settings may block
   the connection from your local machine.
4. Boyce opens **read-only** connections — ensure the database user has SELECT privileges.

---

## HTTP API (`boyce serve --http`)

### Bearer token authentication failing

The HTTP API requires a token set via `BOYCE_HTTP_TOKEN` (env var) or in `.boyce/config.json`:

```json
{ "token": "your-secret-token" }
```

Requests must include `Authorization: Bearer your-secret-token`.

### VS Code extension can't reach the server

1. Check that `boyce serve --http` is running (`GET http://localhost:8741/health` should return `{"status":"ok"}`).
2. Check the port — default is 8741. The extension's `boyce.serverUrl` setting must match.
3. Check firewall settings — some corporate environments block localhost ports.

---

## Still stuck?

- Open a [Setup Help issue](https://github.com/boyce-io/boyce/issues/new?template=setup_help.yml)
- Email [will@convergentmethods.com](mailto:will@convergentmethods.com) for issues involving credentials or sensitive config
