# Cursor MCP config for DataShark (mcp_app)

Use this once Phase 1 is live so Cursor talks to the **official-SDK** MCP server (`datashark.mcp_app`) instead of the legacy hand-rolled loop.

## Where to put it

- **Cursor app config (recommended):**  
  **macOS:** `~/.cursor/config/mcp.json`  
  **Linux:** `~/.cursor/config/mcp.json`  
  **Windows:** `%USERPROFILE%\.cursor\config\mcp.json`

- If you use a project-specific MCP config, add the `datashark` entry under `mcpServers` in that file.

## Snippet to add

Add a `datashark` entry to the `mcpServers` object. Example `mcp.json`:

```json
{
  "mcpServers": {
    "datashark": {
      "command": "python3",
      "args": ["-m", "datashark.mcp_app"],
      "env": {
        "PYTHONPATH": "<REPO_ROOT>/src"
      }
    }
  }
}
```

Replace `<REPO_ROOT>` with the absolute path to the DataShark repo (e.g. `/Users/you/ConvergentMethods/Products/DataShark`), or use a path relative to the config’s working directory if your setup supports it.

### Using the project directory as cwd

If Cursor runs the server with the project as current working directory and the package is installed (`pip install -e .`), you can use:

```json
{
  "mcpServers": {
    "datashark": {
      "command": "python3",
      "args": ["-m", "datashark.mcp_app"]
    }
  }
}
```

No `PYTHONPATH` is needed when the app is run from the repo root and the package is installed.

### If you run from a fixed path

Example with an absolute path and optional env:

```json
{
  "mcpServers": {
    "datashark": {
      "command": "/Users/willwright/ConvergentMethods/Products/DataShark/.venv/bin/python",
      "args": ["-m", "datashark.mcp_app"],
      "cwd": "/Users/willwright/ConvergentMethods/Products/DataShark",
      "env": {
        "PYTHONPATH": "/Users/willwright/ConvergentMethods/Products/DataShark/src"
      }
    }
  }
}
```

## .cursorrules (optional)

You do **not** need to put MCP config inside `.cursorrules`. MCP servers are configured in `mcp.json` (or your project’s MCP config file). If you want a short pointer in `.cursorrules` for humans:

```
Use the DataShark MCP server via ~/.cursor/config/mcp.json — entrypoint: python -m datashark.mcp_app.
```

## Verifying

1. Install deps: `pip install -e .` (or install from repo root so `mcp` is available).
2. Run once by hand: `python -m datashark.mcp_app` (should block on stdin; Ctrl+C to stop).
3. Point Cursor at `datashark` in `mcp.json` as above, then restart Cursor or reload MCP and confirm DataShark tools appear.
