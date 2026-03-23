"""
boyce doctor — environment health checks and diagnostics.

Five check functions, each returning a structured dict with status,
items, and actionable fix suggestions.  The top-level ``run_doctor()``
orchestrates all checks and returns an exit code (0/1/2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Check: editors
# ---------------------------------------------------------------------------

def check_editors() -> Dict[str, Any]:
    """
    Detect MCP host editors and whether each has Boyce configured.

    Returns:
        {
            "status": "ok" | "warning",
            "items": [{"name": str, "detected": bool, "configured": bool,
                       "config_path": str, "fix": str | None}]
        }
    """
    from .init_wizard import detect_hosts

    hosts = detect_hosts()
    items: List[Dict[str, Any]] = []
    has_warning = False

    for h in hosts:
        item: Dict[str, Any] = {
            "name": h.name,
            "detected": h.exists,
            "configured": h.has_boyce,
            "config_path": str(h.config_path),
        }
        if h.exists and not h.has_boyce:
            item["fix"] = "boyce init"
            has_warning = True
        else:
            item["fix"] = None
        items.append(item)

    return {
        "status": "warning" if has_warning else "ok",
        "items": items,
    }


# ---------------------------------------------------------------------------
# Check: database
# ---------------------------------------------------------------------------

async def check_database(context_dir: Path) -> Dict[str, Any]:
    """
    Test connectivity for all stored database connections.

    Returns:
        {
            "status": "ok" | "warning" | "error",
            "items": [{"snapshot_name": str, "dsn_redacted": str,
                       "connected": bool, "message": str, "fix": str | None}]
        }
    """
    from .connections import ConnectionStore

    store = ConnectionStore(context_dir)
    entries = store.list_all()

    if not entries:
        return {
            "status": "ok",
            "items": [],
            "message": "No stored database connections.",
        }

    items: List[Dict[str, Any]] = []
    any_fail = False
    all_fail = True

    for name, entry in entries.items():
        dsn = store.load(name)
        item: Dict[str, Any] = {
            "snapshot_name": name,
            "dsn_redacted": entry["dsn_redacted"],
        }

        if not dsn:
            item["connected"] = False
            item["message"] = "No DSN stored"
            item["fix"] = f'ingest_source with a live PostgreSQL DSN for "{name}"'
            any_fail = True
            items.append(item)
            continue

        # Try connecting
        try:
            import asyncpg  # type: ignore[import-untyped]
            conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5.0)
            await conn.execute("SELECT 1")
            await conn.close()
            item["connected"] = True
            item["message"] = "Connected successfully"
            item["fix"] = None
            all_fail = False
        except ImportError:
            item["connected"] = False
            item["message"] = 'asyncpg not installed — pip install "boyce[postgres]"'
            item["fix"] = 'pip install "boyce[postgres]"'
            any_fail = True
        except Exception as exc:
            item["connected"] = False
            item["message"] = str(exc)
            item["fix"] = f'Check DSN or call ingest_source with a new DSN for "{name}"'
            any_fail = True

        if item["connected"]:
            all_fail = False
        items.append(item)

    if all_fail and items:
        status = "error"
    elif any_fail:
        status = "warning"
    else:
        status = "ok"

    return {"status": status, "items": items}


# ---------------------------------------------------------------------------
# Check: snapshots
# ---------------------------------------------------------------------------

def check_snapshots(context_dir: Path) -> Dict[str, Any]:
    """
    List all snapshots and report their age and size.

    Returns:
        {
            "status": "ok" | "warning",
            "items": [{"name": str, "entities": int, "fields": int,
                       "joins": int, "age_hours": float, "fix": str | None}]
        }
    """
    items: List[Dict[str, Any]] = []
    has_warning = False

    if not context_dir.exists():
        return {"status": "ok", "items": [], "message": "No snapshots found."}

    for path in sorted(context_dir.glob("*.json")):
        # Skip non-snapshot files
        if path.name in ("connections.json", "environment.json") or \
                path.name.endswith(".definitions.json"):
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        name = path.stem
        entities = data.get("entities", {})
        # entities is a dict keyed by entity_id; iterate values
        if isinstance(entities, dict):
            entity_list = list(entities.values())
        else:
            entity_list = entities
        fields_count = sum(len(e.get("fields", [])) for e in entity_list)
        joins_count = len(data.get("joins", []))

        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600

        item: Dict[str, Any] = {
            "name": name,
            "entities": len(entity_list),
            "fields": fields_count,
            "joins": joins_count,
            "age_hours": round(age_hours, 1),
        }

        if age_hours > 168:  # 7 days
            item["fix"] = f'ingest_source(snapshot_name="{name}") to refresh'
            has_warning = True
        else:
            item["fix"] = None

        items.append(item)

    return {
        "status": "warning" if has_warning else "ok",
        "items": items,
    }


# ---------------------------------------------------------------------------
# Check: sources
# ---------------------------------------------------------------------------

def check_sources() -> Dict[str, Any]:
    """
    Run lightweight source discovery and report un-ingested sources.

    Returns:
        {
            "status": "info" | "ok",
            "items": [{"path": str, "parser_type": str, "fix": str | None}]
        }
    """
    try:
        from .discovery import discover_sources
        discovered = discover_sources(max_depth=2)
    except Exception:
        return {"status": "ok", "items": [], "message": "Discovery scan skipped."}

    items: List[Dict[str, Any]] = []
    for src in discovered:
        items.append({
            "path": str(src.path),
            "parser_type": src.parser_type,
            "confidence": src.confidence,
            "fix": "boyce scan",
        })

    return {
        "status": "info" if items else "ok",
        "items": items,
    }


# ---------------------------------------------------------------------------
# Check: server
# ---------------------------------------------------------------------------

def check_server(context_dir: Path) -> Dict[str, Any]:
    """
    Check Boyce server component availability.

    Returns:
        {
            "status": "ok" | "error",
            "version": str,
            "asyncpg_installed": bool,
            "context_dir_exists": bool,
            "snapshot_count": int,
            "boyce_command": str | None,
        }
    """
    from . import __version__

    # asyncpg check
    asyncpg_installed = False
    try:
        import asyncpg  # type: ignore[import-untyped]  # noqa: F811
        asyncpg_installed = True
    except ImportError:
        pass

    # context dir
    context_exists = context_dir.exists()
    snapshot_count = 0
    if context_exists:
        snapshot_count = len([
            p for p in context_dir.glob("*.json")
            if p.name not in ("connections.json", "environment.json")
            and not p.name.endswith(".definitions.json")
        ])

    # boyce command
    boyce_cmd = shutil.which("boyce")

    status = "ok"
    if not asyncpg_installed:
        status = "warning"
    if not boyce_cmd:
        status = "error"

    return {
        "status": status,
        "version": __version__,
        "asyncpg_installed": asyncpg_installed,
        "context_dir_exists": context_exists,
        "snapshot_count": snapshot_count,
        "boyce_command": boyce_cmd,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_doctor(
    context_dir: Optional[Path] = None,
    json_output: bool = False,
) -> int:
    """
    Run all checks, print results, return exit code.

    Exit codes:
        0 — all ok
        1 — warnings present
        2 — errors present
    """
    if context_dir is None:
        context_dir = Path("_local_context")

    results: Dict[str, Any] = {
        "checks": {
            "editors": check_editors(),
            "database": await check_database(context_dir),
            "snapshots": check_snapshots(context_dir),
            "sources": check_sources(),
            "server": check_server(context_dir),
        },
        "suggestions": [],
    }

    # Aggregate suggestions from all checks
    for check_name, check_result in results["checks"].items():
        for item in check_result.get("items", []):
            fix = item.get("fix")
            if fix:
                results["suggestions"].append(fix)

    # Determine overall status
    statuses = [c.get("status", "ok") for c in results["checks"].values()]
    if "error" in statuses:
        results["status"] = "errors"
        exit_code = 2
    elif "warning" in statuses:
        results["status"] = "warnings"
        exit_code = 1
    else:
        results["status"] = "ok"
        exit_code = 0

    # Write environment.json for environment_suggestions to read
    try:
        context_dir.mkdir(parents=True, exist_ok=True)
        env_path = context_dir / "environment.json"
        env_data = {
            "last_doctor": datetime.now(timezone.utc).isoformat(),
            "status": results["status"],
            "suggestion_count": len(results["suggestions"]),
        }
        with open(env_path, "w", encoding="utf-8") as f:
            json.dump(env_data, f, indent=2)
    except OSError:
        pass  # Non-fatal — don't block doctor output on file write failure

    if json_output:
        print(json.dumps(results, indent=2, default=str))
    else:
        _print_human_readable(results)

    return exit_code


def _print_human_readable(results: Dict[str, Any]) -> None:
    """Format doctor results for terminal output."""
    from . import __version__

    server = results["checks"].get("server", {})
    print(f"\n  Boyce Doctor v{server.get('version', __version__)}")
    print(f"  {'=' * 40}")

    for check_name, check_result in results["checks"].items():
        status = check_result.get("status", "ok")
        icon = {"ok": "✓", "warning": "⚠", "error": "✗", "info": "ℹ"}.get(status, "?")
        print(f"\n  {icon} {check_name}: {status}")

        for item in check_result.get("items", []):
            name = item.get("name") or item.get("snapshot_name") or item.get("path", "")
            fix = item.get("fix")
            if fix:
                print(f"    → {name}: {fix}")

    suggestions = results.get("suggestions", [])
    if suggestions:
        print(f"\n  Suggestions ({len(suggestions)}):")
        for s in suggestions[:5]:  # Cap at 5 for readability
            print(f"    • {s}")

    overall = results.get("status", "ok")
    print(f"\n  Overall: {overall}\n")
