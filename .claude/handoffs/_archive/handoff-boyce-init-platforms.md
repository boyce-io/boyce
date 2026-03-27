# `boyce-init` Platform Targeting — Implementation Spec

**Parent:** `handoff-architecture-revision.md` Change 8
**File to modify:** `boyce/src/boyce/init_wizard.py`

---

## Overview

Expand `boyce-init` from 3 detected platforms to 6. All new platforms follow the same pattern: detect config file location, check for existing `boyce` entry, generate server entry, merge into config.

---

## Platform Detection Table

| # | Platform | Config Path | Scope | Key Structure | Detection Signal |
|---|----------|------------|-------|---------------|-----------------|
| 1 | Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | Global | `mcpServers.boyce` | File exists |
| 2 | Cursor | `{CWD}/.cursor/mcp.json` | Project | `mcpServers.boyce` | `.cursor/` dir exists |
| 3 | Claude Code | `{CWD}/.claude/settings.json` | Project | `mcpServers.boyce` | `.claude/` dir exists |
| 4 | **VS Code** | `{CWD}/.vscode/mcp.json` | Project | `servers.boyce` | `.vscode/` dir exists |
| 5 | **JetBrains** | `{CWD}/.jb-mcp.json` | Project | `mcpServers.boyce` | `.idea/` dir exists |
| 6 | **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | Global | `mcpServers.boyce` | File or `~/.codeium/` dir exists |

### Notes:
- macOS paths shown. Linux/Windows paths differ for global configs — handle in implementation.
- VS Code uses `servers` key (not `mcpServers`) in `.vscode/mcp.json` per VS Code MCP docs.
- JetBrains can also be configured via IDE Settings → Tools → MCP Server GUI. The `.jb-mcp.json` is the file-based path. Print a note during wizard: "You can also configure in your JetBrains IDE: Settings → Tools → MCP Server → Add."

---

## Config Formats by Platform

### 1. Claude Desktop (existing — no change)
```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "env": {}
    }
  }
}
```

### 2. Cursor (existing — no change)
```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "env": {}
    }
  }
}
```

### 3. Claude Code (existing — no change)
```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "env": {}
    }
  }
}
```

### 4. VS Code (NEW)
VS Code uses a different key structure: `servers` not `mcpServers`.
```json
{
  "servers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "env": {}
    }
  }
}
```

**Detection:** Check for `{CWD}/.vscode/` directory.
**Config path:** `{CWD}/.vscode/mcp.json`
**Key to check:** `"boyce" in data.get("servers", {})`
**Merge target:** `data["servers"]["boyce"]`

### 5. JetBrains / DataGrip (NEW)
JetBrains AI Assistant reads MCP config from `.jb-mcp.json` in project root, OR from the IDE settings UI.
```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "env": {}
    }
  }
}
```

**Detection:** Check for `{CWD}/.idea/` directory (present in any JetBrains project).
**Config path:** `{CWD}/.jb-mcp.json`
**Key to check:** `"boyce" in data.get("mcpServers", {})`
**Merge target:** `data["mcpServers"]["boyce"]`
**Extra wizard output:** After configuration, print:
```
  Tip: You can also configure in your JetBrains IDE:
       Settings → Tools → AI Assistant → Model Context Protocol (MCP) → Add
```

### 6. Windsurf (NEW)
Windsurf uses a global config file.
```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "args": [],
      "env": {}
    }
  }
}
```

**Detection:** Check for `~/.codeium/windsurf/` directory OR `~/.codeium/` directory.
**Config path:** `~/.codeium/windsurf/mcp_config.json`
**Key to check:** `"boyce" in data.get("mcpServers", {})`
**Merge target:** `data["mcpServers"]["boyce"]`

---

## Changes to `init_wizard.py`

### Update `_host_specs()`:
```python
def _host_specs() -> List[Dict]:
    return [
        {
            "name": "Claude Desktop",
            "path": Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            "project_level": False,
            "servers_key": "mcpServers",
        },
        {
            "name": "Cursor",
            "path": Path.cwd() / ".cursor" / "mcp.json",
            "project_level": True,
            "servers_key": "mcpServers",
        },
        {
            "name": "Claude Code",
            "path": Path.cwd() / ".claude" / "settings.json",
            "project_level": True,
            "servers_key": "mcpServers",
        },
        {
            "name": "VS Code",
            "path": Path.cwd() / ".vscode" / "mcp.json",
            "project_level": True,
            "servers_key": "servers",  # VS Code uses "servers" not "mcpServers"
        },
        {
            "name": "JetBrains",
            "path": Path.cwd() / ".jb-mcp.json",
            "project_level": True,
            "servers_key": "mcpServers",
            "detection_hint": Path.cwd() / ".idea",  # detect by .idea/ dir
            "post_config_note": (
                "  Tip: You can also configure in your JetBrains IDE:\n"
                "       Settings → Tools → AI Assistant → Model Context Protocol (MCP) → Add"
            ),
        },
        {
            "name": "Windsurf",
            "path": Path.home() / ".codeium" / "windsurf" / "mcp_config.json",
            "project_level": False,
            "servers_key": "mcpServers",
        },
    ]
```

### Update `MCPHost` dataclass:
Add `servers_key: str` field (default `"mcpServers"`).
Add `post_config_note: Optional[str]` field (default `None`).

### Update `detect_hosts()`:
- Use `spec.get("servers_key", "mcpServers")` when checking for existing `boyce` entry
- For JetBrains: also check for `.idea/` directory as a detection signal (even if `.jb-mcp.json` doesn't exist yet, the project is a JetBrains project)

### Update `merge_config()`:
- Accept `servers_key` parameter to handle VS Code's `"servers"` vs others' `"mcpServers"`
- Create the correct top-level key if it doesn't exist

### Update `run_wizard()`:
- After each successful config, print `host.post_config_note` if set

---

## Cross-Platform Path Handling

### Windsurf:
- macOS: `~/.codeium/windsurf/mcp_config.json`
- Linux: `~/.codeium/windsurf/mcp_config.json`
- Windows: `%USERPROFILE%\.codeium\windsurf\mcp_config.json`

### Claude Desktop:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### Implementation:
Use `platform.system()` to detect OS and adjust paths. The current code is macOS-only for Claude Desktop — this should be addressed.

---

## Test Updates

Update `boyce/tests/test_init.py`:
- Add test cases for VS Code detection and config merging (note `"servers"` key)
- Add test cases for JetBrains detection via `.idea/` directory
- Add test cases for Windsurf global config path
- Add test case for `servers_key` parameter in `merge_config()`
- Verify `post_config_note` output for JetBrains

Update `boyce/tests/test_cli_smoke.py`:
- If `boyce-init` output format changes, update expected output patterns
