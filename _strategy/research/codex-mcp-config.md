# Research: OpenAI Codex MCP Configuration
**Date:** 2026-03-17
**Purpose:** Determine how to add Codex support to `boyce init` wizard

## Codex MCP Config Format

### Config File Location

Codex uses TOML (not JSON like every other MCP host Boyce supports):

- **Global:** `~/.codex/config.toml`
- **Project-scoped:** `.codex/config.toml` (trusted projects only)

This is the first non-JSON config target for the init wizard.

### TOML Structure for Stdio Servers

Each MCP server is a `[mcp_servers.<name>]` table:

```toml
[mcp_servers.boyce]
command = "/path/to/boyce"
args = []
startup_timeout_sec = 10
tool_timeout_sec = 60
enabled = true

[mcp_servers.boyce.env]
BOYCE_DB_URL = "postgresql://user:pass@host:5432/dbname"
```

### Supported Fields (stdio transport)

| Field | Required | Type | Default | Notes |
|---|---|---|---|---|
| `command` | Yes | string | -- | Launcher command for the MCP stdio server |
| `args` | No | array of strings | `[]` | Arguments passed to the command |
| `env` | No | map of strings | `{}` | Static env vars forwarded to the server process |
| `env_vars` | No | array of strings | `[]` | Whitelist of env var *names* to propagate from parent shell |
| `cwd` | No | string | -- | Working directory for the server process |
| `startup_timeout_sec` | No | float | 10.0 | Startup timeout |
| `tool_timeout_sec` | No | float | 60.0 | Per-tool execution timeout |
| `enabled` | No | bool | true | Disable without deleting |
| `required` | No | bool | false | Fail Codex startup if server can't initialize |
| `enabled_tools` | No | array of strings | -- | Allow list of tool names |
| `disabled_tools` | No | array of strings | -- | Deny list applied after enabled_tools |
| `scopes` | No | array of strings | -- | OAuth scopes (not relevant for Boyce) |

### Environment Variables

Two mechanisms:

1. **`env`** (inline map) -- sets explicit key=value pairs in the server's environment:
   ```toml
   [mcp_servers.boyce.env]
   BOYCE_DB_URL = "postgresql://user:pass@host:5432/db"
   ```

2. **`env_vars`** (whitelist array) -- forwards named vars from the parent shell:
   ```toml
   [mcp_servers.boyce]
   env_vars = ["BOYCE_DB_URL", "ANTHROPIC_API_KEY"]
   ```

Both are supported and can be combined. For `boyce init`, the `env` map is the right choice (matches behavior of JSON configs for other hosts where the DSN is written directly).

### CLI Management

```bash
# Add a stdio server
codex mcp add boyce -- /path/to/boyce

# Add with env vars
codex mcp add boyce --env BOYCE_DB_URL=postgresql://... -- /path/to/boyce

# List/manage servers
codex mcp --help
```

### Transport

Codex supports stdio transport (subprocess communication via stdin/stdout), which is exactly what Boyce uses. No transport adapter changes needed.

### Installation Detection

- Binary: `codex` (installable via `npm i -g @openai/codex`, `brew install --cask codex`, or GitHub release binary)
- Config directory: `~/.codex/`
- Version check: `codex --version` (e.g., "codex-cli 0.2.0")

## Current Init Wizard Status

File: `boyce/src/boyce/init_wizard.py`

### Supported hosts (6 total)

1. Claude Desktop -- global JSON (`~/Library/Application Support/Claude/claude_desktop_config.json`)
2. Cursor -- project JSON (`.cursor/mcp.json`)
3. Claude Code -- project JSON (`.mcp.json`)
4. VS Code -- project JSON (`.vscode/mcp.json`, uses `servers` key instead of `mcpServers`)
5. JetBrains / DataGrip -- project JSON (`.jb-mcp.json`)
6. Windsurf -- global JSON (`~/.codeium/windsurf/mcp_config.json`)

### What exists

- `_host_specs()` returns a list of dicts, each with `name`, `path`, `project_level`, `servers_key`, `installed_check`
- `detect_hosts()` probes each spec for existence and whether Boyce is already configured
- `generate_server_entry()` builds a JSON dict: `{"command": "...", "args": [], "env": {...}}`
- `merge_config()` reads/writes JSON files, merging the boyce entry under the `servers_key`

### What does NOT exist for Codex

- No Codex entry in `_host_specs()`
- No Codex detection logic (checking for `~/.codex/` dir or `codex` binary)
- No TOML writer -- `merge_config()` is JSON-only
- No Codex config path function

## Implementation Gap

### 1. Detection (small)

Add to `_host_specs()`:

```python
{
    "name": "Codex",
    "path": Path.home() / ".codex" / "config.toml",
    "project_level": False,
    "servers_key": "mcp_servers",  # TOML table name, not JSON key
    "installed_check": lambda: (Path.home() / ".codex").is_dir() or bool(shutil.which("codex")),
}
```

Detection hints: `~/.codex/` directory exists, or `codex` binary is on PATH.

### 2. Config Generation (small adaptation)

`generate_server_entry()` already produces the right shape:
```python
{"command": "/path/to/boyce", "args": [], "env": {"BOYCE_DB_URL": "..."}}
```

This maps directly to TOML fields. No change needed to the entry generator itself.

### 3. Config Writing (new code path -- the main gap)

`merge_config()` currently does JSON read/write only. Codex needs TOML. Two options:

**Option A: Use Python's `tomllib` (read) + manual TOML write**
- `tomllib` is stdlib in Python 3.11+ (available in our 3.12 env)
- For writing, there's no stdlib TOML writer. Could use `tomli_w` (small dep) or hand-roll a simple TOML emitter for this narrow use case.

**Option B: Use `tomlkit` (preserves comments, formatting)**
- `tomlkit` is a single dependency that reads and writes TOML while preserving style.
- Better for merge semantics (user's existing config.toml won't lose comments).
- Would need to be an optional dependency (like questionary).

**Option C: Shell out to `codex mcp add`**
- If `codex` binary is available, run:
  ```
  codex mcp add boyce --env BOYCE_DB_URL=... -- /path/to/boyce
  ```
- Avoids TOML dependency entirely.
- Downside: less control, can't merge cleanly, depends on Codex CLI being installed and functional.

**Recommendation:** Option C as primary path (simplest, no new deps), Option A as fallback for cases where the user has `~/.codex/config.toml` but `codex` isn't on PATH (unlikely but possible).

### 4. Merge Logic Refactor (moderate)

`merge_config()` needs to branch on file format. Cleanest approach:

```python
def merge_config(config_path, server_entry, servers_key="mcpServers"):
    if config_path.suffix == ".toml":
        _merge_toml_config(config_path, server_entry, servers_key)
    else:
        _merge_json_config(config_path, server_entry, servers_key)
```

### 5. has_boyce Detection for TOML (small)

In `detect_hosts()`, the existing JSON-based `has_boyce` check needs a TOML branch:

```python
if path.suffix == ".toml":
    import tomllib
    data = tomllib.loads(path.read_text())
    has_boyce = "boyce" in data.get("mcp_servers", {})
```

### 6. Test Coverage

`boyce/tests/test_init.py` has tests for `detect_hosts`, `generate_server_entry`, and `merge_config`. A Codex test case would need:
- Detection when `~/.codex/` exists
- TOML merge (new config, existing config with other servers)
- Round-trip: generate entry, write TOML, read back, verify structure

### Summary of Changes

| Component | Effort | Notes |
|---|---|---|
| `_host_specs()` entry | Trivial | One dict addition |
| Detection function | Trivial | Check `~/.codex/` or `which codex` |
| TOML write path | Small-Medium | Either shell out to `codex mcp add` or add `tomli_w`/hand-roll |
| `merge_config()` branch | Small | Format dispatch on `.toml` suffix |
| `detect_hosts()` TOML read | Small | `tomllib` stdlib read |
| Tests | Small | Mirror existing JSON tests for TOML |

Total estimated effort: ~1-2 hours of focused implementation.

## What a Boyce-for-Codex Config Looks Like

The final output in `~/.codex/config.toml`:

```toml
[mcp_servers.boyce]
command = "/Users/willwright/ConvergentMethods/products/Boyce/.venv/bin/boyce"
args = []

[mcp_servers.boyce.env]
BOYCE_DB_URL = "postgresql://user:pass@host:5432/dbname"
```

Or without database:

```toml
[mcp_servers.boyce]
command = "/Users/willwright/ConvergentMethods/products/Boyce/.venv/bin/boyce"
args = []
```

## Sources

- [Codex MCP Documentation](https://developers.openai.com/codex/mcp)
- [Codex Configuration Reference](https://developers.openai.com/codex/config-reference)
- [Codex Sample Configuration](https://developers.openai.com/codex/config-sample)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)
- [Codex GitHub Repository](https://github.com/openai/codex)
- [Codex Config Basics](https://developers.openai.com/codex/config-basic/)
- [Codex npm package](https://www.npmjs.com/package/@openai/codex)
