"""
boyce init — Interactive MCP host setup wizard.

Detects installed MCP hosts (Claude Desktop, Cursor, Claude Code, VS Code,
JetBrains/DataGrip, Windsurf), generates the boyce server entry, and merges
it into each config file.

Usage:
    boyce-init
    python -m boyce.init_wizard

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MCPHost:
    """A detected MCP host and its config file state."""

    name: str
    config_path: Path
    project_level: bool        # True = path is CWD-relative (Cursor, Claude Code, VS Code, JetBrains)
    exists: bool               # config file exists on disk
    has_boyce: bool            # "boyce" key already present in the servers dict
    servers_key: str = "mcpServers"    # top-level JSON key; VS Code uses "servers"
    post_config_note: Optional[str] = None  # printed after successful config


# ---------------------------------------------------------------------------
# Host detection
# ---------------------------------------------------------------------------


def _claude_desktop_path() -> Path:
    """Return the Claude Desktop config path for the current OS."""
    system = platform.system()
    if system == "Windows":
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "Claude" / "claude_desktop_config.json"
    if system == "Linux":
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    # macOS default
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def _windsurf_path() -> Path:
    """Return the Windsurf global config path for the current OS."""
    if platform.system() == "Windows":
        return Path.home() / "AppData" / "Roaming" / ".codeium" / "windsurf" / "mcp_config.json"
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


# Resolved lazily so tests can patch Path.cwd()
def _host_specs() -> List[Dict]:
    return [
        {
            "name": "Claude Desktop",
            "path": _claude_desktop_path(),
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
            "detection_hint": Path.cwd() / ".idea",  # detect by .idea/ presence
            "post_config_note": (
                "  Tip: You can also configure in your JetBrains IDE:\n"
                "       Settings → Tools → AI Assistant → Model Context Protocol (MCP) → Add"
            ),
        },
        {
            "name": "Windsurf",
            "path": _windsurf_path(),
            "project_level": False,
            "servers_key": "mcpServers",
        },
    ]


def detect_hosts(specs: Optional[List[Dict]] = None) -> List[MCPHost]:
    """
    Detect which MCP hosts have config files and whether Boyce is already wired.

    Args:
        specs: Override the default host specs (used in tests).

    Returns:
        List of MCPHost — one per known host regardless of whether it exists.
    """
    if specs is None:
        specs = _host_specs()

    hosts: List[MCPHost] = []
    for spec in specs:
        path: Path = spec["path"]
        servers_key: str = spec.get("servers_key", "mcpServers")
        detection_hint: Optional[Path] = spec.get("detection_hint")

        # A host is "found" if:
        # - its config file exists, OR
        # - its detection_hint directory exists (e.g. .idea/ for JetBrains)
        exists = path.exists() or (detection_hint is not None and detection_hint.is_dir())
        has_boyce = False

        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                has_boyce = "boyce" in data.get(servers_key, {})
            except (json.JSONDecodeError, OSError):
                pass

        hosts.append(MCPHost(
            name=spec["name"],
            config_path=path,
            project_level=spec["project_level"],
            exists=exists,
            has_boyce=has_boyce,
            servers_key=servers_key,
            post_config_note=spec.get("post_config_note"),
        ))

    return hosts


# ---------------------------------------------------------------------------
# Command resolution
# ---------------------------------------------------------------------------


def _resolve_boyce_command() -> str:
    """
    Locate the boyce executable.

    Preference order:
    1. 'boyce' if it's on PATH (clean install, pipx, homebrew)
    2. Full path to the boyce script in the current Python env's bin/
    3. 'boyce' as a fallback (best effort)
    """
    if shutil.which("boyce"):
        return "boyce"

    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "boyce"
    if candidate.exists():
        return str(candidate)

    return "boyce"


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def generate_server_entry(
    db_url: Optional[str] = None,
    want_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Build the ``mcpServers.boyce`` config entry.

    For MCP hosts (Claude Desktop, Cursor, Claude Code): no LLM config
    is needed — the host's own LLM handles NL reasoning and calls
    ``get_schema`` + ``build_sql`` directly.

    LLM config is only needed if you want ``ask_boyce`` to work in
    self-contained mode (VS Code extension, HTTP API, Direct CLI).

    Args:
        db_url:   asyncpg DSN for live DB queries and EXPLAIN pre-flight.
        want_llm: Include BOYCE_PROVIDER / BOYCE_MODEL env vars.
        provider: LLM provider name (e.g. "anthropic", "openai").
        model:    Model identifier (e.g. "claude-haiku-4-5-20251001").
        api_key:  API key value. Leave None to rely on shell environment.

    Returns:
        Dict with "command", "args", and optionally "env".
    """
    entry: dict = {
        "command": _resolve_boyce_command(),
        "args": [],
    }

    env: Dict[str, str] = {}

    if db_url:
        env["BOYCE_DB_URL"] = db_url

    if want_llm:
        if provider:
            env["BOYCE_PROVIDER"] = provider
        if model:
            env["BOYCE_MODEL"] = model
        if api_key and provider:
            key_name = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
            }.get(provider.lower(), "LITELLM_API_KEY")
            env[key_name] = api_key

    if env:
        entry["env"] = env

    return entry


# ---------------------------------------------------------------------------
# Config merging
# ---------------------------------------------------------------------------


def merge_config(
    config_path: Path,
    server_entry: dict,
    servers_key: str = "mcpServers",
) -> None:
    """
    Merge the boyce server entry into an MCP host config file.

    Behaviour:
    - Creates the file (and parent directories) if it doesn't exist.
    - Preserves all existing server entries.
    - Overwrites the existing ``boyce`` entry if present.

    Args:
        config_path:  Path to the host config JSON file.
        server_entry: Dict to set at ``servers_key["boyce"]``.
        servers_key:  Top-level JSON key for the servers dict.
                      Defaults to "mcpServers". VS Code uses "servers".
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    if servers_key not in existing:
        existing[servers_key] = {}

    existing[servers_key]["boyce"] = server_entry
    config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------


def run_wizard() -> int:
    """
    Run the interactive setup wizard.

    Prompts the user for which hosts to configure and optional DB/LLM config,
    then writes the boyce entry into each selected host's config file.

    Returns:
        0 on success, 1 on error or abort.
    """
    print("\nBoyce Setup Wizard")
    print("=" * 40)

    hosts = detect_hosts()

    print("\nDetected MCP hosts:")
    for i, host in enumerate(hosts):
        if host.has_boyce:
            status = "✓ boyce configured"
        elif host.exists:
            status = "config exists"
        else:
            status = "not found"
        print(f"  [{i + 1}] {host.name}  —  {status}")

    print("\nWhich hosts to configure?")
    print("  Enter comma-separated numbers (e.g. 1,3), 'all', or 'q' to quit.")
    raw = input("> ").strip().lower()

    if raw in ("q", "quit", ""):
        print("Aborted.")
        return 0

    if raw == "all":
        selected = hosts
    else:
        try:
            indices = [int(x.strip()) - 1 for x in raw.split(",")]
            selected = [hosts[i] for i in indices if 0 <= i < len(hosts)]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return 1

    if not selected:
        print("No hosts selected.")
        return 0

    # --- Optional: database URL ---
    print("\nDatabase URL (asyncpg DSN) — enables live queries and EXPLAIN pre-flight.")
    print("Leave blank to skip (set BOYCE_DB_URL env var later if needed).")
    db_url = input("DB URL: ").strip() or None

    # --- Optional: LLM config ---
    print("\nAdd LLM config for self-contained ask_boyce (NL mode)?")
    print("  MCP hosts (Claude, Cursor, VS Code, JetBrains, Windsurf) do NOT need this —")
    print("  the host's own LLM calls get_schema + ask_boyce directly.")
    raw_llm = input("Add LLM config? [y/N]: ").strip().lower()
    want_llm = raw_llm in ("y", "yes")

    provider = model = api_key = None
    if want_llm:
        provider = input("  Provider (e.g. anthropic, openai): ").strip() or None
        model = input("  Model (e.g. claude-haiku-4-5-20251001): ").strip() or None
        print("  API key (leave blank if already in your shell environment):")
        api_key = input("  API key: ").strip() or None

    # --- Generate and apply ---
    server_entry = generate_server_entry(
        db_url=db_url,
        want_llm=want_llm,
        provider=provider,
        model=model,
        api_key=api_key,
    )

    print()
    success_count = 0
    for host in selected:
        try:
            merge_config(host.config_path, server_entry, servers_key=host.servers_key)
            print(f"  ✓ {host.name}  →  {host.config_path}")
            if host.post_config_note:
                print(host.post_config_note)
            success_count += 1
        except Exception as exc:
            print(f"  ✗ {host.name}: {exc}")

    if success_count:
        print(f"\nDone — configured {success_count} host(s).")
        print("Restart your MCP host to pick up the new server.")
        print("Run 'boyce-scan <path>' to ingest a snapshot, then try 'get_schema'.")

    return 0 if success_count else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    sys.exit(run_wizard())


if __name__ == "__main__":
    main()
