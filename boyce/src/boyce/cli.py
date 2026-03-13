"""
boyce CLI — unified command dispatcher.

Usage:
    boyce                                  Start MCP server on stdio
    boyce ask "query" [OPTIONS]            Direct NL → SQL (uses ask_boyce pipeline)
    boyce chat "message" [OPTIONS]         Conversational mode (intent routing)
    boyce serve --http [--port N]          Start HTTP API server

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
# Intent routing for `boyce chat`
# ---------------------------------------------------------------------------

_SCHEMA_KEYWORDS = frozenset({
    "table", "tables", "schema", "field", "fields", "column", "columns",
    "entity", "entities", "available", "what data", "what tables",
})
_PATH_KEYWORDS = frozenset({
    "connect", "connection", "join", "joins", "relate", "related",
    "path", "link", "relationship", "between",
})
_PROFILE_KEYWORDS = frozenset({
    "null", "nulls", "profile", "distribution", "how many", "count",
    "distinct", "min", "max", "stats", "statistics",
})


def _classify_intent(message: str) -> str:
    """
    Classify a chat message into one of: schema | path | profile | sql.

    Uses keyword heuristics — no LLM call needed for routing.
    """
    lower = message.lower()
    words = set(lower.split())

    schema_hits = len(words & _SCHEMA_KEYWORDS) + (1 if any(kw in lower for kw in _SCHEMA_KEYWORDS) else 0)
    path_hits = len(words & _PATH_KEYWORDS) + (1 if any(kw in lower for kw in _PATH_KEYWORDS) else 0)
    profile_hits = len(words & _PROFILE_KEYWORDS) + (1 if any(kw in lower for kw in _PROFILE_KEYWORDS) else 0)

    if schema_hits >= 1 and schema_hits >= path_hits and schema_hits >= profile_hits:
        return "schema"
    if path_hits >= 1 and path_hits >= schema_hits:
        return "path"
    if profile_hits >= 1:
        return "profile"
    return "sql"


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
# `boyce chat` — conversational with intent routing
# ---------------------------------------------------------------------------


async def _cmd_chat(
    message: str,
    snapshot_name: str,
    dialect: str,
) -> int:
    """
    Route a natural language message to the appropriate tool and print
    a conversational text response.
    """
    from .server import ask_boyce, get_schema, solve_path  # noqa: PLC0415

    intent = _classify_intent(message)

    if intent == "schema":
        raw = get_schema(snapshot_name)
        result = json.loads(raw)
        if "error" in result:
            print(f"Error: {result['error']['message']}", file=sys.stderr)
            return 1
        entities = result["entities"]
        lines = [f"Available entities in snapshot '{snapshot_name}':\n"]
        for ent in entities:
            field_names = [f["name"] for f in ent["fields"]]
            lines.append(f"  {ent['name']}  ({len(ent['fields'])} fields)")
            if field_names:
                preview = ", ".join(field_names[:6])
                if len(field_names) > 6:
                    preview += f", … +{len(field_names) - 6} more"
                lines.append(f"    Fields: {preview}")
        print("\n".join(lines))
        return 0

    if intent == "path":
        # Try to extract two entity names from the message
        raw_schema = get_schema(snapshot_name)
        schema = json.loads(raw_schema)
        if "error" in schema:
            print(f"Error: {schema['error']['message']}", file=sys.stderr)
            return 1
        entity_names = [e["name"] for e in schema["entities"]]
        mentioned = [n for n in entity_names if n.lower() in message.lower()]
        if len(mentioned) >= 2:
            raw = solve_path(mentioned[0], mentioned[1], snapshot_name)
            result = json.loads(raw)
            if "error" in result:
                print(f"No join path found between '{mentioned[0]}' and '{mentioned[1]}'.", file=sys.stderr)
                return 1
            print(f"Join path from {mentioned[0]} to {mentioned[1]}:")
            print(f"  {result['path_length']} hop(s), semantic cost {result['semantic_cost']:.2f}")
            print(f"\n{result['sql']}")
            return 0
        # Fall through to SQL if we can't identify entities
        print("Tip: name two entities to explore their join path (e.g. 'how do orders connect to customers?')")

    if intent == "profile":
        print("Profile queries require a live database (BOYCE_DB_URL) and a specific table/column.")
        print("Try: boyce ask 'how many nulls in orders.status'")
        print("Or use the profile_data MCP tool from your host.")
        return 0

    # Default: SQL generation via ask_boyce
    raw = await ask_boyce(
        natural_language_query=message,
        snapshot_name=snapshot_name,
        dialect=dialect,
    )
    result = json.loads(raw)
    if "error" in result:
        print(f"Error: {result['error']['message']}", file=sys.stderr)
        return 1

    entities = ", ".join(result.get("entities_resolved", []))
    validation = result["validation"]["status"]

    print(f"Here's the SQL for '{message}':\n")
    print(result["sql"])
    print(f"\n-- Entities: {entities} | Validation: {validation}")

    if "warning" in result:
        w = result["warning"]
        print(f"\n⚠  {w['code']}: {w['message']}", file=sys.stderr)

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

    # Unknown subcommand — print error rather than silently starting MCP server
    return ("error", {"msg": f"Unknown command: '{subcmd}'\nUsage: boyce [ask|chat|serve] ...\nRun 'boyce --help' for full usage."})


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


if __name__ == "__main__":
    main()
