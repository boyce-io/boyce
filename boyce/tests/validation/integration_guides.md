# Boyce Integration Guides
**For testing week of March 9 — one guide per MCP host.**

All MCP hosts use **Path 1** (no Boyce LLM key needed). The host's own LLM drives
the interaction using `get_schema` + `ask_boyce`. `BOYCE_PROVIDER` is only required
for CLI (`boyce ask`) and HTTP API (`boyce serve --http`).

---

## Prerequisites

Install Boyce and verify it starts:

```bash
pip install boyce
boyce --help         # should print usage
boyce-init           # auto-detects and configures your MCP hosts
```

Or from this repo (editable install):

```bash
pip install -e /Users/willwright/ConvergentMethods/Products/Boyce/boyce/
```

Find the full path to the `boyce` executable (needed for manual config):

```bash
which boyce          # e.g. /Users/willwright/.local/bin/boyce
# or if using venv:
# /Users/willwright/ConvergentMethods/Products/Boyce/.venv/bin/boyce
```

---

## Claude Desktop

**Config file:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": []
    }
  }
}
```

**Steps:**
1. Edit the config file above (create if it doesn't exist)
2. Restart Claude Desktop
3. Look for the tools icon (hammer) in the chat input — Boyce tools should appear
4. Test: ask Claude "Use boyce to show me what tables are available" or run `get_schema`

**What to verify:**
- MCP tools appear (7 tools: `ingest_source`, `ingest_definition`, `get_schema`, `ask_boyce`, `validate_sql`, `query_database`, `profile_data`)
- `get_schema` returns the Pagila schema after ingesting a snapshot
- A plain-English query produces SQL

---

## Cursor

**Config file:** `.cursor/mcp.json` in your project root (or `~/.cursor/mcp.json` for global)

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": []
    }
  }
}
```

**Steps:**
1. Create `.cursor/mcp.json` in your project
2. Restart Cursor (or reload window: Cmd+Shift+P → "Developer: Reload Window")
3. Open Cursor chat (Cmd+L or Cmd+I for Composer)
4. Test: "Use boyce get_schema to list available entities"

**What to verify:**
- Boyce tools available in Cursor chat
- `get_schema` works
- `ask_boyce` with a `StructuredFilter` produces deterministic SQL

---

## Claude Code

**Config file:** `.claude/settings.json` in your project root

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "type": "stdio"
    }
  }
}
```

Or add globally at `~/.claude/settings.json` under the same `"mcpServers"` key.

**Steps:**
1. Add the config above to `.claude/settings.json`
2. Start a new Claude Code session in the project
3. Test: "Call the boyce get_schema tool and show me what's available"

**What to verify:**
- Boyce MCP tools available in Claude Code session
- Claude Code can call `get_schema`, `ask_boyce`, `validate_sql` directly
- End-to-end: Claude Code ingests a snapshot and generates a SQL query

---

## Cline (VS Code Extension)

Cline is MCP-native. Path 1 — no Boyce LLM key needed.

**Steps:**
1. Install Cline from VS Code Marketplace
2. Open Cline settings → MCP Servers → Add Server
3. Fill in:
   - **Name:** `boyce`
   - **Command:** `boyce` (or full path from `which boyce`)
   - **Args:** (leave empty)
   - **Transport:** `stdio`
4. Save and reload
5. Test in Cline chat: "Use boyce to get the schema"

**Or via `cline_mcp_settings.json`** (usually at `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

**What to verify:**
- Boyce server shows as connected in Cline's MCP panel
- Tools available in Cline chat
- `get_schema` returns Pagila entities

---

## Continue.dev (VS Code Extension)

Continue supports MCP servers via its config file.

**Config file:** `~/.continue/config.yaml` (or `config.json` depending on version)

For `config.yaml`:
```yaml
mcpServers:
  - name: boyce
    command: boyce
    args: []
```

For `config.json`:
```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "boyce",
          "args": []
        }
      }
    ]
  }
}
```

**Steps:**
1. Edit the config file above
2. Reload Continue (VS Code command palette: "Continue: Reload")
3. Test in Continue chat: "@boyce get the schema"

**What to verify:**
- Boyce tools accessible in Continue chat
- Schema retrieval works
- SQL generation works

---

## Local LLM via Ollama (Path 2 — internal planner)

This uses Boyce's internal `ask_boyce` planner, not a host LLM.
Required for `boyce ask "..."` CLI and `boyce serve --http`.

**Steps:**
1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama3.1` (or `mistral`, `qwen2.5-coder`, etc.)
3. Set env vars:

```bash
export BOYCE_PROVIDER=ollama
export BOYCE_MODEL=ollama/llama3.1     # match whatever you pulled
# No API key needed for Ollama
```

4. Test:
```bash
boyce ask "show me all customers"
# or
boyce serve --http   # then POST to /chat
```

**What to verify:**
- `boyce ask` returns SQL without an Anthropic/OpenAI key
- Response quality: does llama3.1 produce usable StructuredFilters?
- Latency vs. hosted models

---

## Ingest Pagila for Testing

After connecting any host, ingest the Pagila snapshot so the host can see the schema.
First make sure the Pagila Docker container is running:

```bash
cd boyce/tests/validation && ./setup.sh
```

Then in any MCP host, call `ingest_source` with the live connection:

```
Tool: ingest_source
Args:
  source_type: "postgres"
  connection_string: "postgresql://boyce:password@localhost:5433/pagila"
  snapshot_name: "pagila"
```

Or ingest a DDL snapshot if you prefer not to use a live connection — a Pagila DDL file
can be generated with `pg_dump --schema-only` and passed to `ingest_source` with `source_type: "ddl"`.

---

## Quick Verification Checklist

After connecting each host, run these in order:

1. `get_schema` — returns entities? Shows `film`, `rental`, `customer`, `payment`?
2. `ask_boyce` with a StructuredFilter — produces deterministic SQL?
3. `ask_boyce` "how many rentals were there last month?" (CLI/HTTP path or schema guidance fallback) — full pipeline works?
4. `validate_sql` with a hand-written query — EXPLAIN pre-flight and lint run?
5. `ask_boyce` with equality filter on nullable column — NULL trap warning fires?
