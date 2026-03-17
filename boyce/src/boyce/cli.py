"""
boyce CLI — unified command dispatcher.

Usage:
    boyce                                  Start MCP server on stdio
    boyce ask "query" [OPTIONS]            Direct NL → SQL (uses ask_boyce pipeline)
    boyce chat "message" [OPTIONS]         Conversational mode
    boyce serve --http [--port N]          Start HTTP API server
    boyce init                             Setup wizard — configure editors, DB, data sources
    boyce scan <path> [-o FILE]            Scan a file or directory for data schemas

Options for ask / chat:
    --snapshot NAME    Snapshot name (default: "default")
    --dialect DIALECT  SQL dialect (default: "redshift")

Options for serve:
    --http             Start HTTP REST server instead of MCP stdio
    --port N           Port for HTTP server (default: 8741)

Environment variables:
    BOYCE_PROVIDER   LLM provider for ask_boyce (e.g. "anthropic")
    BOYCE_MODEL      LLM model name
    BOYCE_DB_URL     asyncpg DSN for live DB
    BOYCE_HTTP_TOKEN Bearer token for HTTP server auth
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# `boyce ask` — direct NL → SQL
# ---------------------------------------------------------------------------


async def _cmd_ask(
    query: str,
    snapshot_name: str,
    dialect: str,
) -> int:
    """
    Run the full ask_boyce pipeline and print SQL to stdout.

    Warnings go to stderr so callers can pipe SQL cleanly:
        boyce ask "revenue by customer" | pbcopy
    """
    # Import here to keep startup fast and avoid circular imports
    from .server import ask_boyce  # noqa: PLC0415

    raw = await ask_boyce(
        natural_language_query=query,
        snapshot_name=snapshot_name,
        dialect=dialect,
    )
    result = json.loads(raw)

    if "error" in result:
        msg = result["error"].get("message", str(result["error"]))
        print(f"Error: {msg}", file=sys.stderr)
        return 1

    # Warnings to stderr
    if "warning" in result:
        w = result["warning"]
        print(f"[{w['severity']}] {w['code']}: {w['message']}", file=sys.stderr)

    if "compat_risks" in result:
        for risk in result["compat_risks"]:
            print(f"[COMPAT] {risk}", file=sys.stderr)

    print(f"-- Snapshot: {result.get('snapshot_name')} | Validation: {result['validation']['status']}")
    print(result["sql"])
    return 0


# ---------------------------------------------------------------------------
# `boyce chat` — conversational via ask_boyce
# ---------------------------------------------------------------------------


async def _cmd_chat(
    message: str,
    snapshot_name: str,
    dialect: str,
) -> int:
    """
    Route a natural language message through ask_boyce and print
    a conversational text response.
    """
    from .server import ask_boyce  # noqa: PLC0415

    raw = await ask_boyce(
        natural_language_query=message,
        snapshot_name=snapshot_name,
        dialect=dialect,
    )
    result = json.loads(raw)

    if "error" in result:
        print(f"Error: {result['error']['message']}", file=sys.stderr)
        return 1

    # Mode C: schema guidance — no credentials configured
    if result.get("mode") == "schema_guidance":
        print(f"Here's what I found in the database for '{message}':\n")
        entities = result.get("relevant_entities", [])
        for ent in entities:
            field_names = [f["name"] for f in ent.get("fields", [])]
            print(f"  {ent['name']}  ({len(field_names)} fields)")
            if field_names:
                preview = ", ".join(field_names[:6])
                if len(field_names) > 6:
                    preview += f", … +{len(field_names) - 6} more"
                print(f"    Fields: {preview}")
        print(
            "\nTo generate SQL, configure Boyce's LLM credentials:\n"
            "  Run `boyce init` to configure your editor, or set:\n"
            "  BOYCE_PROVIDER=anthropic BOYCE_MODEL=claude-haiku-4-5-20251001"
        )
        return 0

    # Mode A/B: SQL result
    entities = ", ".join(result.get("entities_resolved", []))
    validation = result["validation"]["status"]

    print(f"Here's the SQL for '{message}':\n")
    print(result["sql"])
    print(f"\n-- Entities: {entities} | Validation: {validation}")

    if "warning" in result:
        w = result["warning"]
        print(f"\n⚠  {w['code']}: {w['message']}", file=sys.stderr)

    if "compat_risks" in result:
        for risk in result["compat_risks"]:
            print(f"[COMPAT] {risk}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# `boyce serve --http` — start HTTP API
# ---------------------------------------------------------------------------


def _cmd_serve_http(port: int) -> int:
    """Launch the HTTP API server via uvicorn."""
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        print("uvicorn is required for HTTP mode. Install it: pip install uvicorn", file=sys.stderr)
        return 1

    from .http_api import build_app  # noqa: PLC0415

    app = build_app()
    print(f"Boyce HTTP API listening on http://0.0.0.0:{port}", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=port)
    return 0


# ---------------------------------------------------------------------------
# Argument parsing (stdlib argparse)
# ---------------------------------------------------------------------------


def _parse_args(argv: list) -> tuple:
    """
    Parse sys.argv into (subcommand, kwargs).

    Returns:
        ("mcp", {})          — no subcommand → MCP stdio mode
        ("ask", {...})       — ask subcommand
        ("chat", {...})      — chat subcommand
        ("serve", {...})     — serve subcommand
        ("error", {"msg": "..."}) — parse error
    """
    if not argv:
        return ("mcp", {})

    subcmd = argv[0]

    if subcmd in ("-h", "--help"):
        return ("help", {})

    if subcmd in ("-V", "--version"):
        return ("version", {})

    if subcmd in ("ask", "chat"):
        if len(argv) < 2:
            return ("error", {"msg": f"Usage: boyce {subcmd} \"<query>\" [--snapshot NAME] [--dialect DIALECT]"})
        query = argv[1]
        snapshot = "default"
        dialect = "redshift"
        i = 2
        while i < len(argv):
            if argv[i] == "--snapshot" and i + 1 < len(argv):
                snapshot = argv[i + 1]
                i += 2
            elif argv[i] == "--dialect" and i + 1 < len(argv):
                dialect = argv[i + 1]
                i += 2
            else:
                i += 1
        return (subcmd, {"query": query, "snapshot": snapshot, "dialect": dialect})

    if subcmd == "serve":
        http = "--http" in argv
        port = 8741
        if "--port" in argv:
            idx = argv.index("--port")
            if idx + 1 < len(argv):
                try:
                    port = int(argv[idx + 1])
                except ValueError:
                    return ("error", {"msg": f"Invalid port: {argv[idx + 1]}"})
        if not http:
            return ("error", {"msg": "Usage: boyce serve --http [--port N]"})
        return ("serve", {"port": port})

    if subcmd == "init":
        return ("init", {})

    if subcmd == "scan":
        # Pass remaining args through to scan's own argparse
        return ("scan", {"argv": argv[1:]})

    # Unknown subcommand — print error rather than silently starting MCP server
    return ("error", {"msg": f"Unknown command: '{subcmd}'\nUsage: boyce [ask|chat|init|scan|serve] ...\nRun 'boyce --help' for full usage."})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    argv = sys.argv[1:]
    subcmd, kwargs = _parse_args(argv)

    if subcmd == "error":
        print(kwargs["msg"], file=sys.stderr)
        sys.exit(1)

    if subcmd == "help":
        print(__doc__)
        return

    if subcmd == "version":
        from importlib.metadata import version as _version, PackageNotFoundError
        try:
            print(_version("boyce"))
        except PackageNotFoundError:
            print("boyce (development install)")
        return

    if subcmd == "mcp":
        # Default: run MCP server on stdio
        from .server import main as mcp_main  # noqa: PLC0415
        mcp_main()
        return

    if subcmd == "ask":
        code = asyncio.run(_cmd_ask(kwargs["query"], kwargs["snapshot"], kwargs["dialect"]))
        sys.exit(code)

    if subcmd == "chat":
        code = asyncio.run(_cmd_chat(kwargs["query"], kwargs["snapshot"], kwargs["dialect"]))
        sys.exit(code)

    if subcmd == "serve":
        code = _cmd_serve_http(kwargs["port"])
        sys.exit(code)

    if subcmd == "init":
        from .init_wizard import run_wizard  # noqa: PLC0415
        sys.exit(run_wizard())

    if subcmd == "scan":
        from .scan import main as scan_main  # noqa: PLC0415
        # Patch sys.argv so scan's argparse sees the right args
        sys.argv = ["boyce scan"] + kwargs["argv"]
        scan_main()
        return


if __name__ == "__main__":
    main()
