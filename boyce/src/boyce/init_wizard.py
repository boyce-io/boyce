"""
boyce init — Interactive setup wizard.

Detects editors with MCP support, configures the boyce server entry, tests
database connections, and auto-discovers data sources.

Usage:
    boyce-init
    python -m boyce.init_wizard

Optional dependency:
    pip install boyce[wizard]   # adds questionary for interactive arrow-key UI
    pip install questionary     # or directly

No required third-party dependencies — falls back to numbered-list prompts.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# questionary — optional interactive UI
# ---------------------------------------------------------------------------

_q = None  # Set to questionary module if available


def _ensure_questionary() -> bool:
    """
    Check if questionary is available. If not, offer to install it.
    Sets the module-level _q variable. Returns True if available.
    """
    global _q

    try:
        import questionary as _questionary  # noqa: PLC0415
        _q = _questionary
        return True
    except ImportError:
        pass

    print("\n  For the best experience, Boyce uses interactive prompts.")
    raw = input("  Install now? [Y/n]: ").strip().lower()
    if raw in ("n", "no"):
        print("  Continuing with basic prompts.\n")
        return False

    print("  Installing...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "questionary", "--quiet"],
            capture_output=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        result = None  # type: ignore[assignment]

    if result and result.returncode == 0:
        import importlib
        importlib.invalidate_caches()
        try:
            import questionary as _questionary  # noqa: PLC0415
            _q = _questionary
            print("✓ Ready\n")
            return True
        except ImportError:
            pass

    print("failed — continuing with basic prompts.\n")
    return False


# ---------------------------------------------------------------------------
# Host detection
# ---------------------------------------------------------------------------


@dataclass
class MCPHost:
    """A detected MCP host and its config file state."""

    name: str
    config_path: Path
    project_level: bool
    exists: bool
    has_boyce: bool
    servers_key: str = "mcpServers"
    post_config_note: Optional[str] = None


def _claude_desktop_path() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    if system == "Linux":
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def _windsurf_path() -> Path:
    if platform.system() == "Windows":
        return Path.home() / "AppData" / "Roaming" / ".codeium" / "windsurf" / "mcp_config.json"
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


def _is_cursor_installed() -> bool:
    """Check if Cursor editor is installed."""
    if platform.system() == "Darwin":
        if (Path("/Applications/Cursor.app")).exists():
            return True
    if (Path.home() / ".cursor").exists():
        return True
    if shutil.which("cursor"):
        return True
    return False


def _is_vscode_installed() -> bool:
    """Check if VS Code is installed."""
    if platform.system() == "Darwin":
        if (Path("/Applications/Visual Studio Code.app")).exists():
            return True
    if (Path.home() / ".vscode").exists():
        return True
    if shutil.which("code"):
        return True
    return False


def _is_windsurf_installed() -> bool:
    """Check if Windsurf is installed."""
    p = _windsurf_path()
    if p.parent.exists():
        return True
    if platform.system() == "Darwin" and Path("/Applications/Windsurf.app").exists():
        return True
    return False


def _host_specs() -> List[Dict]:
    return [
        {
            "name": "Claude Desktop",
            "path": _claude_desktop_path(),
            "project_level": False,
            "servers_key": "mcpServers",
            "installed_check": lambda: _claude_desktop_path().exists(),
        },
        {
            "name": "Cursor",
            "path": Path.cwd() / ".cursor" / "mcp.json",
            "project_level": True,
            "servers_key": "mcpServers",
            "installed_check": _is_cursor_installed,
        },
        {
            "name": "Claude Code",
            "path": Path.cwd() / ".mcp.json",
            "project_level": True,
            "servers_key": "mcpServers",
            "installed_check": lambda: (Path.cwd() / ".claude").is_dir() or bool(shutil.which("claude")),
        },
        {
            "name": "VS Code",
            "path": Path.cwd() / ".vscode" / "mcp.json",
            "project_level": True,
            "servers_key": "servers",
            "installed_check": _is_vscode_installed,
        },
        {
            "name": "JetBrains / DataGrip",
            "path": Path.cwd() / ".jb-mcp.json",
            "project_level": True,
            "servers_key": "mcpServers",
            "installed_check": lambda: (Path.cwd() / ".idea").is_dir(),
            "post_config_note": (
                "  Tip: Also configure in IDE:\n"
                "       Settings → Tools → AI Assistant → Model Context Protocol → Add"
            ),
        },
        {
            "name": "Windsurf",
            "path": _windsurf_path(),
            "project_level": False,
            "servers_key": "mcpServers",
            "installed_check": _is_windsurf_installed,
        },
    ]


def detect_hosts(specs: Optional[List[Dict]] = None) -> List[MCPHost]:
    if specs is None:
        specs = _host_specs()

    hosts: List[MCPHost] = []
    for spec in specs:
        path: Path = spec["path"]
        servers_key: str = spec.get("servers_key", "mcpServers")
        installed_check = spec.get("installed_check")
        detection_hint: Optional[Path] = spec.get("detection_hint")

        exists = (
            path.exists()
            or (installed_check is not None and bool(installed_check()))
            or (detection_hint is not None and detection_hint.is_dir())
        )
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
    Return the full path to the boyce executable.

    Preference order:
    1. Full path from PATH lookup (clean install, pipx, homebrew)
    2. Full path in the current Python env's bin/
    3. Bare 'boyce' as last resort
    """
    found = shutil.which("boyce")
    if found:
        return found  # Return full resolved path, not bare "boyce"

    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "boyce"
    if candidate.exists():
        return str(candidate)

    return "boyce"


# ---------------------------------------------------------------------------
# Config generation and writing
# ---------------------------------------------------------------------------


def generate_server_entry(
    db_url: Optional[str] = None,
    want_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Build the mcpServers.boyce config entry.

    For MCP editors (Claude, Cursor, VS Code, JetBrains, Windsurf), LLM config
    is not needed — the host's own LLM calls get_schema + ask_boyce directly.
    LLM params are available for programmatic use (HTTP API, direct CLI).

    Args:
        db_url:   asyncpg DSN for live DB queries and EXPLAIN pre-flight.
        want_llm: Include BOYCE_PROVIDER / BOYCE_MODEL env vars.
        provider: LLM provider name (e.g. "anthropic", "openai").
        model:    Model identifier.
        api_key:  API key value. Leave None to rely on shell environment.
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


def merge_config(
    config_path: Path,
    server_entry: dict,
    servers_key: str = "mcpServers",
) -> None:
    """Merge boyce server entry into an MCP host config file."""
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
# Prompt helpers — questionary path + fallback
# ---------------------------------------------------------------------------


def _print_step(n: int, total: int, title: str) -> None:
    print(f"\nStep {n} of {total} — {title}\n")


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Y/n prompt. Returns True for yes."""
    hint = "[Y/n]" if default else "[y/N]"
    if _q:
        return _q.confirm(prompt, default=default).ask() or False
    raw = input(f"  {prompt} {hint}: ").strip().lower()
    if raw == "":
        return default
    return raw in ("y", "yes")


def _ask_text(prompt: str, default: str = "") -> str:
    """Text input with optional default. Enter accepts default."""
    if _q:
        result = _q.text(prompt, default=default).ask()
        return result or default
    if default:
        raw = input(f"  {prompt} [{default}]: ").strip()
        return raw or default
    raw = input(f"  {prompt}: ").strip()
    return raw


def _ask_password(prompt: str) -> str:
    """Masked password input."""
    if _q:
        result = _q.password(prompt).ask()
        return result or ""
    return getpass.getpass(f"  {prompt}: ")


def _ask_select(prompt: str, choices: List[str]) -> str:
    """Single-select list. Arrow keys with questionary, numbered list fallback."""
    if _q:
        result = _q.select(prompt, choices=choices).ask()
        return result or choices[0]
    print(f"  {prompt}")
    for i, c in enumerate(choices, 1):
        print(f"    [{i}] {c}")
    while True:
        raw = input("  > ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print(f"  Enter a number between 1 and {len(choices)}")


def _ask_checkbox(
    prompt: str,
    choices: List[str],
    pre_checked: Optional[List[bool]] = None,
) -> List[str]:
    """
    Multi-select checkbox. Space to toggle, Enter to confirm (questionary).
    Falls back to comma-separated number entry.
    """
    if _q:
        import questionary as _questionary  # noqa: PLC0415
        q_choices = [
            _questionary.Choice(c, checked=(pre_checked[i] if pre_checked else False))
            for i, c in enumerate(choices)
        ]
        result = _q.checkbox(
            prompt,
            choices=q_choices,
            instruction="(Space to toggle, Enter to confirm)",
        ).ask()
        return result or []

    # Fallback: show with indicators and accept comma-separated numbers
    print(f"  {prompt}")
    defaults: List[int] = []
    for i, c in enumerate(choices, 1):
        mark = "✓" if (pre_checked and pre_checked[i - 1]) else " "
        print(f"    [{i}] {mark} {c}")
        if pre_checked and pre_checked[i - 1]:
            defaults.append(i)

    default_str = ",".join(str(d) for d in defaults)
    hint = f"[{default_str}]" if defaults else ""
    raw = input(f"  Enter numbers (e.g. 1,2,3 / all / none) {hint}: ").strip().lower()

    if raw == "" and defaults:
        return [choices[d - 1] for d in defaults]
    if raw == "all":
        return choices[:]
    if raw in ("none", "0", ""):
        return []
    try:
        indices = [int(x.strip()) - 1 for x in raw.split(",")]
        return [choices[i] for i in indices if 0 <= i < len(choices)]
    except ValueError:
        return []


# ---------------------------------------------------------------------------
# Step 1 — Editor selection
# ---------------------------------------------------------------------------


_SOMETHING_ELSE = "Something else (manual config)"


def _step_editors(hosts: List[MCPHost]) -> List[MCPHost]:
    """
    Let the user select which editors to configure.
    Returns list of selected MCPHost objects.
    """
    _print_step(1, 3, "Select Your Editors")

    # Sort: detected first, then alphabetical
    detected = [h for h in hosts if h.exists]
    undetected = [h for h in hosts if not h.exists]
    ordered = detected + undetected

    # Build choice labels
    labels: List[str] = []
    for h in ordered:
        if h.exists:
            label = f"{h.name}  (detected)"
        else:
            label = h.name
        labels.append(label)
    labels.append(_SOMETHING_ELSE)

    # Pre-check all detected editors — if you're running the wizard,
    # you want every installed editor configured (especially for new DB URLs)
    pre_checked = [h.exists for h in ordered] + [False]

    selected_labels = _ask_checkbox(
        "Select your editors",
        labels,
        pre_checked=pre_checked,
    )

    if not selected_labels:
        return []

    if _SOMETHING_ELSE in selected_labels:
        _print_manual_config_instructions()
        selected_labels = [s for s in selected_labels if s != _SOMETHING_ELSE]

    # Map back to MCPHost objects
    label_to_host: Dict[str, MCPHost] = {}
    for i, h in enumerate(ordered):
        label_to_host[labels[i]] = h

    return [label_to_host[lbl] for lbl in selected_labels if lbl in label_to_host]


def _print_manual_config_instructions() -> None:
    cmd = _resolve_boyce_command()
    print(f"""
  ─── Manual Setup ───────────────────────────────────────
  Boyce uses the MCP (Model Context Protocol) standard.
  Add this to your editor's MCP server config file:

  {{
    "mcpServers": {{
      "boyce": {{
        "command": "{cmd}",
        "args": []
      }}
    }}
  }}

  Check your editor's documentation for the config file location.
  ────────────────────────────────────────────────────────
""")


# ---------------------------------------------------------------------------
# Step 2 — Database connection
# ---------------------------------------------------------------------------


def _test_db_connection(dsn: str) -> Tuple[bool, str]:
    """
    Test a database connection. Returns (success, human-readable message).
    Requires asyncpg; returns a safe skip message if not installed.
    """
    try:
        import asyncpg  # noqa: PLC0415
    except ImportError:
        return True, "Saved — install boyce[postgres] to verify connections"

    async def _connect() -> int:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5.0)
        count: int = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
        await conn.close()
        return count

    try:
        count = asyncio.run(_connect())
        return True, f"Connected ({count} tables)"
    except asyncio.TimeoutError:
        return False, "Could not reach host — is the database running?"
    except Exception as e:
        err = str(e).lower()
        if "password" in err or "authenticat" in err or "invalid x-api" in err:
            return False, "Authentication failed — check your username and password"
        if "database" in err and ("not exist" in err or "not found" in err):
            return False, "Database not found on this server"
        return False, f"Connection failed: {e}"


def _dsn_from_fields(host: str, port: str, db: str, user: str, password: str) -> str:
    from urllib.parse import quote  # noqa: PLC0415
    safe_user = quote(user, safe="")
    safe_pass = quote(password, safe="")
    return f"postgresql://{safe_user}:{safe_pass}@{host}:{port}/{db}"


def _collect_one_database() -> Optional[Tuple[str, str]]:
    """
    Collect one database connection from the user (field-by-field or paste URL).
    Returns (name, dsn) or None if skipped.
    """
    method = _ask_select(
        "How would you like to connect?",
        [
            "Enter connection details",
            "Paste a connection URL",
            "Skip for now",
        ],
    )

    if method == "Skip for now":
        return None

    if method == "Paste a connection URL":
        while True:
            url = _ask_text("Connection URL")
            if not url:
                return None
            print("  Connecting...", end=" ", flush=True)
            ok, msg = _test_db_connection(url)
            print(f"{'✓' if ok else '✗'} {msg}")
            if ok:
                try:
                    parsed = urlparse(url)
                    name = (parsed.path or "/unnamed").lstrip("/") or "database"
                except Exception:
                    name = "database"
                print(f"  Saved as \"{name}\"")
                return name, url
            if not _ask_yes_no("Try again?", default=True):
                return None

    # Field-by-field
    host = "localhost"
    port = "5432"
    db_name = ""
    username = ""
    password = ""

    while True:
        host = _ask_text("Host", default=host)
        # Auto-suggest Redshift default port
        default_port = "5439" if "redshift" in host.lower() else "5432"
        if port == "5432" and default_port != "5432":
            port = default_port
        port = _ask_text("Port", default=port)
        db_name = _ask_text("Database", default=db_name)
        username = _ask_text("Username", default=username)
        password = _ask_password("Password")

        dsn = _dsn_from_fields(host, port, db_name, username, password)
        print("  Connecting...", end=" ", flush=True)
        ok, msg = _test_db_connection(dsn)
        print(f"{'✓' if ok else '✗'} {msg}")

        if ok:
            print(f"  Saved as \"{db_name}\"")
            return db_name, dsn

        if not _ask_yes_no("Try again?", default=True):
            return None


def _step_databases() -> List[Tuple[str, str]]:
    """
    Let the user configure database connections.
    Returns list of (name, dsn) tuples.
    """
    _print_step(2, 3, "Connect Your Database")

    print("  Connect to your database for live queries and SQL validation.")
    print("  Press Enter to skip — you can always add this later.\n")

    results: List[Tuple[str, str]] = []

    while True:
        entry = _collect_one_database()
        if entry:
            results.append(entry)

        if not entry and not results:
            # First attempt skipped
            break

        if entry and not _ask_yes_no("\n  Add another database?", default=False):
            break

        if not entry:
            break

    return results


# ---------------------------------------------------------------------------
# Step 3 — Data sources
# ---------------------------------------------------------------------------


def _step_data_sources() -> List[Tuple[str, str]]:
    """
    Let the user discover and ingest data sources.
    Returns list of (snapshot_name, result_description) for successfully ingested sources.
    """
    _print_step(3, 3, "Add Your Data Sources")

    print("  Boyce can also learn your schema from files you already have:")
    print("    • dbt projects (models, sources, schema.yml)")
    print("    • LookML / Looker (views, explores, joins)")
    print("    • SQL files (CREATE TABLE, DDL, migrations)")
    print("    • ORM definitions (Django, SQLAlchemy, Prisma)")
    print("    • Data files (CSV, Parquet, SQLite)\n")

    ingested: List[Tuple[str, str]] = []

    if _ask_yes_no("Search your computer for data sources?", default=True):
        ingested.extend(_run_auto_discovery())

    # Always offer manual add after
    if _ask_yes_no("\n  Add paths manually?", default=False):
        ingested.extend(_run_manual_add())

    return ingested


def _run_auto_discovery() -> List[Tuple[str, str]]:
    """Run auto-discovery and let user select sources to ingest."""
    from .discovery import SEARCH_ROOTS, discover_sources  # noqa: PLC0415

    existing_roots = [r for r in SEARCH_ROOTS if r.exists()]
    if not existing_roots:
        print("  No standard code directories found.")
        return []

    root_display = "  ".join(str(r).replace(str(Path.home()), "~") for r in existing_roots)
    print(f"\n  Searching: {root_display}")
    print("  (Everything stays on your machine — nothing is sent anywhere.)\n")

    sources = discover_sources(existing_roots)

    if not sources:
        print("  Nothing found in common locations.")
        return []

    # Build display labels
    labels: List[str] = []
    for s in sources:
        path_display = str(s.path).replace(str(Path.home()), "~")
        labels.append(f"{path_display:<50}  {s.label}")

    pre_checked = [s.pre_selected for s in sources]

    print(f"  Found {len(sources)} data source{'s' if len(sources) != 1 else ''}:\n")
    selected_labels = _ask_checkbox(
        "Ingest which?  (Space to toggle, Enter to confirm)",
        labels,
        pre_checked=pre_checked,
    )

    if not selected_labels:
        return []

    label_to_source = dict(zip(labels, sources))
    selected_sources = [label_to_source[lbl] for lbl in selected_labels if lbl in label_to_source]

    return _ingest_sources(selected_sources)


def _run_manual_add() -> List[Tuple[str, str]]:
    """Loop asking for paths to ingest manually."""
    from .discovery import DiscoveredSource, ingest_source  # noqa: PLC0415

    results: List[Tuple[str, str]] = []

    while True:
        raw_path = _ask_text("  Path to scan (or Enter to finish)", default="")
        if not raw_path:
            break

        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            print(f"  Path not found: {path}")
            continue

        name = path.stem if path.is_file() else path.name
        print(f"  Scanning {name}...", end=" ", flush=True)

        try:
            from .discovery import _check_project_root  # noqa: PLC0415

            # Detect the parser type for accurate descriptions
            detected = _check_project_root(path) if path.is_dir() else None
            source = detected or DiscoveredSource(
                path=path,
                parser_type="unknown",
                label="",
                confidence=1.0,
                is_git_repo=False,
                pre_selected=True,
            )
            desc = ingest_source(source, name=name)
            print(f"✓ {desc}")
            print(f"  Saved as \"{name}\"")
            results.append((name, desc))
        except Exception as e:
            print(f"✗ Could not parse: {e}")

        if not _ask_yes_no("  Add another?", default=False):
            break

    return results


def _ingest_sources(sources: list) -> List[Tuple[str, str]]:
    """Ingest a list of DiscoveredSource objects. Returns (name, description) for successes."""
    from .discovery import ingest_source  # noqa: PLC0415

    results: List[Tuple[str, str]] = []
    print()

    for source in sources:
        name = source.path.stem if source.path.is_file() else source.path.name
        print(f"  Ingesting {name}...", end=" ", flush=True)
        try:
            desc = ingest_source(source, name=name)
            print(f"✓ {desc}")
            results.append((name, desc))
        except Exception as e:
            print(f"✗ {e}")

    return results


# ---------------------------------------------------------------------------
# Config generation and summary
# ---------------------------------------------------------------------------


def _build_and_write_configs(
    editors: List[MCPHost],
    db_entries: List[Tuple[str, str]],
) -> List[MCPHost]:
    """Generate and write server entry to each selected editor config."""
    first_dsn = db_entries[0][1] if db_entries else None
    server_entry = generate_server_entry(db_url=first_dsn)

    print()
    success: List[MCPHost] = []
    for host in editors:
        try:
            merge_config(host.config_path, server_entry, servers_key=host.servers_key)
            print(f"  ✓ {host.name}  →  {host.config_path}")
            if host.post_config_note:
                print(host.post_config_note)
            success.append(host)
        except Exception as exc:
            print(f"  ✗ {host.name}: {exc}")

    return success


def _print_summary(
    configured_editors: List[MCPHost],
    db_entries: List[Tuple[str, str]],
    source_entries: List[Tuple[str, str]],
) -> None:
    """Print the final summary screen."""
    print("\nDone! Boyce is ready.")
    print("═" * 38)

    if configured_editors:
        editor_names = "  ".join(h.name for h in configured_editors)
        print(f"\n  Editors:    {editor_names} ✓")

    if db_entries:
        db_display = "  ".join(name for name, _ in db_entries)
        print(f"  Databases:  {db_display} ✓")

    if source_entries:
        src_display = "  ".join(f"{name} ({desc})" for name, desc in source_entries)
        print(f"  Sources:    {src_display}")

    if configured_editors:
        print("\n  Open your editor and try:")
        print('    "Use boyce to show me the database schema"')
        print('    "What tables have revenue data?"')
    else:
        print("\n  Run boyce-init again to configure an editor.")

    print()


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------


def run_wizard() -> int:
    """
    Run the interactive setup wizard.
    Returns 0 on success, 1 on error or full skip.
    """
    # Require an interactive terminal — questionary and input() both need one
    if not sys.stdin.isatty():
        print("boyce-init requires an interactive terminal.")
        print("Run this command directly in your terminal, not as a subprocess.")
        return 1

    print("\nBoyce Setup Wizard")
    print("=" * 40)

    try:
        return _run_wizard_interactive()
    except (EOFError, KeyboardInterrupt):
        print("\n\nSetup cancelled.")
        return 0


def _run_wizard_interactive() -> int:
    """Inner wizard logic — separated so EOFError/KeyboardInterrupt bubble cleanly."""
    _ensure_questionary()

    hosts = detect_hosts()

    # Step 1 — Editor
    selected_editors = _step_editors(hosts)
    if not selected_editors:
        print("\n  No editors selected — nothing to configure.")
        print("  Run boyce-init again and select an editor to get started.\n")
        return 0

    # Step 2 — Database
    db_entries = _step_databases()

    # Step 3 — Data Sources
    source_entries = _step_data_sources()

    # Write configs
    configured = _build_and_write_configs(selected_editors, db_entries)

    # Summary
    _print_summary(configured, db_entries, source_entries)

    if configured:
        editor_names = ", ".join(h.name for h in configured)
        print(f"  Restart {editor_names} to pick up the new server.\n")

    return 0 if configured else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    sys.exit(run_wizard())


if __name__ == "__main__":
    main()
