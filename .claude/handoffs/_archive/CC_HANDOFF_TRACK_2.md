# CC Handoff — Track 2: Init Redesign + Agent-Guided Setup Docs
**Priority:** BLOCKING — must complete before publish  
**Model:** Sonnet · high effort (this is mostly refactoring, not architecture)  
**Estimated time:** ~60-90 min  
**File ownership:** `init_wizard.py`, `test_init.py`, `test_cli_smoke.py`, `cli.py` (init subcommand flags only)  
**Does NOT touch:** `server.py`, `doctor.py`, `connections.py` (those belong to Track 1)

---

## Context

The `boyce init` wizard works for interactive human use. But agents can't run it — it requires a TTY and has no structured output. This track makes init agent-invokable with `--non-interactive` and `--json` flags, ensures re-runs are idempotent, and creates the "agent-guided setup" documentation pattern for the website.

Read these before starting:
- `CLAUDE.md` — architecture, CLI change rule
- `boyce/src/boyce/init_wizard.py` — the existing wizard
- `boyce/tests/test_init.py` — existing init tests
- This handoff

---

## Block 1: Non-Interactive Mode

### New CLI flags for `boyce init`

Add to the argument parser in `cli.py` (or wherever init's entry point is wired):

```
boyce init [OPTIONS]

  --non-interactive     Skip all prompts. Requires explicit flags for configuration.
                        Fails fast with exit code 1 on missing required params.
  --json                Output structured JSON summary instead of human-readable text.
  --editors EDITORS     Comma-separated list of editors to configure.
                        Valid names: claude_code, cursor, vscode, jetbrains, windsurf, claude_desktop
                        If omitted in non-interactive mode: auto-detect and configure all found.
  --db-url DSN          PostgreSQL connection string to configure as BOYCE_DB_URL.
  --skip-db             Skip the database connection step entirely.
  --skip-sources        Skip the data source discovery step entirely.
  --skip-existing       Skip editors that already have Boyce configured.
```

### Implementation approach

The wizard's `_run_wizard_interactive()` function currently drives the 3-step flow. Create a parallel path:

```python
def _run_wizard_noninteractive(
    editors: Optional[List[str]],
    db_url: Optional[str],
    skip_db: bool,
    skip_sources: bool,
    skip_existing: bool,
    json_output: bool,
) -> int:
    """Non-interactive wizard path. No prompts, no questionary."""
    
    result = {"status": "ok", "editors_configured": [], "database": None, "sources_ingested": []}
    
    # Step 1: Editors
    hosts = detect_hosts()
    if editors:
        # Map CLI names to MCPHost objects
        name_map = {_cli_name(h): h for h in hosts}
        selected = [name_map[e] for e in editors if e in name_map]
        unknown = [e for e in editors if e not in name_map]
        if unknown:
            # Fail fast: unknown editor names
            ...
    else:
        # Auto-detect: configure all detected editors
        selected = [h for h in hosts if h.exists]
    
    if skip_existing:
        selected = [h for h in selected if not h.has_boyce]
    
    # Step 2: Database
    if not skip_db and db_url:
        ok, msg = _test_db_connection(db_url)
        result["database"] = {"dsn_redacted": _redact(db_url), "connected": ok, "message": msg}
        if not ok:
            result["status"] = "error"
            if json_output:
                print(json.dumps(result))
            return 1
    
    # Step 3: Sources
    if not skip_sources:
        # Run auto-discovery silently, ingest all pre-selected sources
        ...
    
    # Write configs
    configured = _build_and_write_configs(selected, [(db_name, db_url)] if db_url else [])
    result["editors_configured"] = [h.name for h in configured]
    result["config_paths"] = [str(h.config_path) for h in configured]
    
    if json_output:
        print(json.dumps(result))
    else:
        _print_summary(configured, ...)
    
    return 0 if configured else 1
```

### CLI name mapping

Create a mapping from CLI-friendly names to the wizard's host detection:

```python
_CLI_EDITOR_NAMES = {
    "claude_code": "Claude Code",
    "cursor": "Cursor", 
    "vscode": "VS Code",
    "jetbrains": "JetBrains / DataGrip",
    "windsurf": "Windsurf",
    "claude_desktop": "Claude Desktop",
}
```

### Entry point routing

In `run_wizard()` or the CLI entry point:

```python
if non_interactive:
    return _run_wizard_noninteractive(editors, db_url, skip_db, skip_sources, skip_existing, json_output)
else:
    if json_output:
        print("Warning: --json without --non-interactive; interactive mode ignores --json", file=sys.stderr)
    return _run_wizard_interactive()
```

### Error handling in non-interactive mode

- Unknown editor name → print error JSON, exit 1
- DB connection fails → print error JSON with message, exit 1  
- No editors detected and none specified → print error JSON, exit 1
- Zero editors configured (e.g., all skipped) → exit 0 with empty list (not an error)

---

## Block 2: Idempotent Re-Runs

### Interactive mode changes

In `_step_editors()`, modify the display logic:

```python
for h in ordered:
    if h.exists and h.has_boyce:
        label = f"{h.name}  (configured ✓)"
        # Pre-check OFF — don't re-configure by default
        pre_checked_value = False
    elif h.exists:
        label = f"{h.name}  (detected)"
        pre_checked_value = True  # New editor, suggest configuring
    else:
        label = h.name
        pre_checked_value = False
```

This way, re-running `boyce init` shows already-configured editors as checked-off and skipped, while newly detected editors are pre-selected.

### Non-interactive mode

`--skip-existing` flag filters out already-configured editors. Without the flag, non-interactive mode updates existing entries (merge_config already does dict merge, so this is safe — it preserves existing env vars and adds/updates the boyce entry).

### Database re-configuration

If the wizard detects an existing `BOYCE_DB_URL` in the MCP config, interactive mode should show:
```
  Database already configured: postgresql://...@localhost:5433/pagila
  Keep this? [Y/n]:
```

Non-interactive mode with `--db-url`: always overwrites. Non-interactive without `--db-url`: keeps existing.

---

## Block 3: `--json` Output Schema

```json
{
  "status": "ok",
  "editors_configured": ["Claude Code", "Cursor"],
  "editors_skipped": ["VS Code"],
  "database": {
    "name": "pagila",
    "dsn_redacted": "postgresql://boyce:***@localhost:5433/pagila",
    "connected": true,
    "table_count": 31
  },
  "sources_ingested": [
    {"name": "jaffle_shop", "path": "~/analytics/dbt_project.yml", "parser_type": "dbt"}
  ],
  "config_paths": [".mcp.json", ".cursor/mcp.json"],
  "suggestions": [
    "VS Code detected but skipped (already configured). Use --editors vscode to reconfigure."
  ]
}
```

On error:
```json
{
  "status": "error",
  "error": "Database connection failed: Authentication failed — check your username and password",
  "editors_configured": [],
  "database": {
    "dsn_redacted": "postgresql://boyce:***@localhost:5433/pagila",
    "connected": false,
    "message": "Authentication failed — check your username and password"
  }
}
```

---

## Block 4: Agent-Guided Setup Documentation

Create a markdown section (for the website/README) that shows platform-specific agent-guided setup. This is documentation, not code — but it depends on the `--non-interactive --json` flags existing.

### The pattern

Right after the install block on the website, add:

```markdown
## Quick Start

### Install
```
pip install boyce
```

### Set up (choose your editor)

**Claude Code** — paste this into your terminal:
```
claude "Install Boyce for this project. My database is at postgresql://user:pass@host:5432/mydb"
```

**Cursor** — open Composer (Cmd+I) and type:
```
Set up the Boyce MCP server for my project. Connect it to my PostgreSQL 
database at postgresql://user:pass@host:5432/mydb
```

**VS Code Copilot** — open Copilot Chat and type:
```
Run `boyce init --non-interactive --editors vscode --db-url "postgresql://user:pass@host:5432/mydb" --json` 
and tell me if it worked
```

**Manual setup** — if you prefer:
```
boyce init
```
The wizard walks you through editor detection, database connection, and data source discovery.

### Verify
```
boyce doctor
```
```

**Key insight:** For Claude Code and Cursor, the prompt is natural language — the agent figures out it needs to run `boyce init --non-interactive`. For VS Code Copilot (which is less agentic), we give it the explicit command. This matches real-world capability differences.

### Where this lives

- `sites/boyce_io/` — the boyce.io product site (post-publish, but write the content now)
- `README.md` in the Boyce repo — the PyPI page people see first
- `convergentmethods.com/boyce/` — update the existing product page

For now, write it as a standalone markdown file at `docs/QUICK_START.md` that can be dropped into any of those surfaces.

---

## Block 5: Test Updates

### `test_init.py` additions

- Test `--non-interactive` with `--editors claude_code --db-url <dsn>` → verify config written
- Test `--non-interactive` without required params → verify exit code 1
- Test `--non-interactive --skip-existing` → verify already-configured editors skipped
- Test `--json` output is valid parseable JSON
- Test idempotent re-run: run init twice, verify second run doesn't clobber first
- Test unknown editor name → error exit

### `test_cli_smoke.py` additions (per CLI change rule in CLAUDE.md)

- `boyce init --help` includes `--non-interactive`, `--json`, `--editors`, `--db-url`, `--skip-db`, `--skip-sources`, `--skip-existing`
- `boyce init --non-interactive --skip-db --skip-sources --json` exits 0 with valid JSON (smoke test, no DB needed)

---

## Verification Checklist

Before marking this track complete:

- [ ] `python boyce/tests/verify_eyes.py` passes
- [ ] `python -m pytest boyce/tests/test_init.py -v` passes (including new tests)
- [ ] `boyce init --non-interactive --skip-db --skip-sources --json` produces valid JSON, exit 0
- [ ] `boyce init --non-interactive --editors nonexistent_editor --json` exits 1 with error JSON
- [ ] Running `boyce init` twice interactively shows "configured ✓" for already-done editors
- [ ] `test_cli_smoke.py` updated and passing
- [ ] `docs/QUICK_START.md` written with platform-specific agent-guided setup blocks
- [ ] No changes to `server.py` (that's Track 1's file)
