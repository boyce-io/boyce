# Plan: Phase 3 — Platform Expansion (Codex Support)
**Status:** COMPLETE
**Completed:** 2026-03-27
**Created:** 2026-03-27
**Model:** Sonnet · medium
**Estimated effort:** ~0.5 day

---

## Goal

Add OpenAI Codex as the 7th supported platform in `boyce init`. After this phase,
distribution copy can say "works with Claude Code, Cursor, VS Code, DataGrip,
Windsurf, Claude Desktop, and Codex."

---

## What Codex Needs

Codex uses TOML config at `~/.codex/config.toml` (global). Structure:

```toml
[mcp_servers.boyce]
command = "/path/to/boyce"
args = []
enabled = true

[mcp_servers.boyce.env]
BOYCE_DB_URL = "postgresql://user:pass@host:5432/dbname"
```

---

## Implementation Steps

### Step 1: Add Codex to `_host_specs()` in init_wizard.py

Add a new entry after Windsurf:

```python
{
    "name": "Codex",
    "path": Path.home() / ".codex" / "config.toml",
    "project_level": False,
    "servers_key": "mcp_servers",  # TOML key (not mcpServers)
    "installed_check": lambda: (Path.home() / ".codex").is_dir() or bool(shutil.which("codex")),
    "restart_instruction": "Restart Codex",
    "is_toml": True,  # NEW flag — signals TOML format
},
```

Add `"codex": "Codex"` to `_CLI_EDITOR_NAMES`.

### Step 2: Add `is_toml` field to MCPHost dataclass

```python
is_toml: bool = False
```

Wire it through `detect_hosts()` constructor.

### Step 3: TOML read support in `detect_hosts()`

For Codex detection (checking if boyce already configured), add TOML
parsing branch. Use `tomllib` (stdlib, Python 3.11+). Our minimum is
3.10, so guard with try/except and fall back to `tomli` if needed, or
just treat missing tomllib as "can't detect existing config" (safe default).

```python
if path.suffix == ".toml" and path.exists():
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        has_boyce = "boyce" in data.get("mcp_servers", {})
    except Exception:
        pass
```

Note: `tomllib` expects bytes in 3.11, use `path.read_bytes()` and
`tomllib.loads()` → `tomllib.load()` with file handle.

### Step 4: TOML write support in `_build_and_write_configs()` / `merge_config()`

**Do NOT add a TOML writing dependency.** The config structure is simple
and predictable. Write a helper `_write_codex_toml()` that:
1. Reads existing TOML (if any) via tomllib
2. Merges the boyce entry
3. Writes back as formatted TOML string (template-based)

Or simpler: add a `_merge_toml_config()` parallel to `merge_config()`.

The existing `merge_config()` is JSON-only. Branch on `host.is_toml`:
- If True: call `_merge_toml_config()`
- If False: call existing `merge_config()`

`_merge_toml_config()` implementation:
- Read existing TOML if file exists (tomllib)
- Add/update `mcp_servers.boyce` section
- Write back using a simple TOML serializer (string formatting — no dep)

### Step 5: Update `_build_and_write_configs()`

In the loop over editors, dispatch on `host.is_toml`:

```python
for host in editors:
    try:
        entry = {**server_entry, **(host.entry_extra or {})} if host.entry_extra else server_entry
        if host.is_toml:
            _merge_toml_config(host.config_path, entry)
        else:
            merge_config(host.config_path, entry, servers_key=host.servers_key)
        # ... rest unchanged
```

### Step 6: Tests

Add to `test_init.py`:
- `test_detect_hosts_codex_detected_via_dir` — create `~/.codex/` dir, verify detection
- `test_detect_hosts_codex_reads_toml` — create `config.toml` with boyce entry, verify `has_boyce=True`
- `test_merge_toml_config_creates_new` — write to empty path, verify valid TOML
- `test_merge_toml_config_preserves_existing` — existing servers survive merge
- `test_cli_editor_names_covers_codex` — existing test should auto-pass if _CLI_EDITOR_NAMES updated
- `test_noninteractive_codex` — `--editors codex` works

Add `"codex"` to CLI smoke test for `--editors` validation.

### Step 7: Verify

```bash
python -m pytest boyce/tests/test_init.py -v
python boyce/tests/test_cli_smoke.py
python -m pytest boyce/tests/ -q  # full suite
```

---

## Files to Modify

| File | Change |
|---|---|
| `boyce/src/boyce/init_wizard.py` | Add Codex spec, `is_toml` field, TOML read/write |
| `boyce/tests/test_init.py` | Add Codex detection + TOML merge tests |
| `boyce/tests/test_cli_smoke.py` | Verify `--editors codex` acceptance (may auto-pass) |

## Files NOT to Modify

- `server.py` — no changes
- `cli.py` — no changes (init routing already handles arbitrary editors)
- `README.md` — will update during distribution phase
- `CLAUDE.md` — will update after implementation

---

## Do NOT

- Add `tomli_w`, `tomlkit`, or any TOML writing dependency
- Modify the MCP server, kernel, or any tool logic
- Change existing platform behavior
- Touch the README or public docs (save for distribution phase)

---

## Read These Files

- `boyce/src/boyce/init_wizard.py` — full file, focus on `_host_specs()`, `MCPHost`, `detect_hosts()`, `merge_config()`, `_build_and_write_configs()`
- `boyce/tests/test_init.py` — test patterns for existing platforms
- `boyce/tests/test_cli_smoke.py` — CLI contract checks

---

## Acceptance Criteria

- [x] `boyce init --non-interactive --editors codex --skip-db --json` succeeds
- [x] Config written to `~/.codex/config.toml` with valid TOML
- [x] Existing TOML entries preserved on re-run
- [x] `detect_hosts()` finds Codex when `~/.codex/` exists
- [x] All existing tests still pass (448 passed, 6 skipped — was 438+)
- [x] CLI smoke checks pass (25 — was 24+)
