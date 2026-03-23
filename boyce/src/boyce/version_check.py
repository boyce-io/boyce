"""
boyce version_check — version lifecycle management.

Handles PyPI version checking, disk caching, install method detection,
stale-process detection, and self-update.  All network calls fail silently.
All file writes are non-fatal.

Environment variables:
    BOYCE_DISABLE_UPDATE_CHECK     Set to any value to disable PyPI checks.
    BOYCE_AUTO_RESTART_ON_UPDATE   Set to "1" to enable graceful server
                                   self-termination after an upgrade is
                                   detected.  Default: off.  Caveat: if the
                                   MCP host does not auto-respawn stdio
                                   servers, the user will lose Boyce until
                                   they manually restart their editor.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE_FILE = "version_check.json"
_CACHE_MAX_AGE_HOURS = 24
_COOLDOWN_HOURS = 48


# ---------------------------------------------------------------------------
# PyPI fetch
# ---------------------------------------------------------------------------

def _fetch_pypi_info(timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """
    Fetch version info from PyPI JSON API.

    Returns dict with ``version`` and ``upload_time`` keys, or None on any
    failure (network, timeout, parse, opt-out).
    """
    if os.environ.get("BOYCE_DISABLE_UPDATE_CHECK"):
        return None
    try:
        import urllib.request

        req = urllib.request.Request(
            "https://pypi.org/pypi/boyce/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

        latest = data["info"]["version"]

        # Get upload time of latest release
        release_files = data.get("releases", {}).get(latest, [])
        upload_time: Optional[str] = None
        if release_files:
            upload_time = release_files[0].get("upload_time_iso_8601")

        return {"version": latest, "upload_time": upload_time}
    except Exception:
        return None


def fetch_latest_version(timeout: float = 2.0) -> Optional[str]:
    """
    Hit PyPI JSON API, return latest version string.

    Returns None on any failure (network, timeout, parse, opt-out).
    """
    info = _fetch_pypi_info(timeout=timeout)
    return info["version"] if info else None


# ---------------------------------------------------------------------------
# Version classification
# ---------------------------------------------------------------------------

def _classify_update(current: str, latest: str) -> Optional[str]:
    """Classify the update type.  Returns 'major', 'minor', 'patch', or None."""
    try:
        from packaging.version import Version

        c = Version(current)
        l = Version(latest)  # noqa: E741
        if l <= c:
            return None
        if l.major > c.major:
            return "major"
        if l.minor > c.minor:
            return "minor"
        return "patch"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stale-process detection
# ---------------------------------------------------------------------------

def check_running_vs_installed() -> Dict[str, Any]:
    """
    Compare the version loaded in memory vs what's installed on disk.

    Returns dict with ``running``, ``installed``, and ``restart_required`` keys.
    """
    from . import __version__ as running

    try:
        from importlib.metadata import version as meta_version

        installed = meta_version("boyce")
    except Exception:
        installed = running  # Can't determine — assume match

    return {
        "running": running,
        "installed": installed,
        "restart_required": running != installed,
    }


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

def _read_cache(context_dir: Path) -> Optional[Dict[str, Any]]:
    """Read version cache from disk.  Returns None if missing or corrupt."""
    cache_path = context_dir / _CACHE_FILE
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(context_dir: Path, data: Dict[str, Any]) -> None:
    """Write version cache to disk.  Non-fatal on failure."""
    try:
        context_dir.mkdir(parents=True, exist_ok=True)
        cache_path = context_dir / _CACHE_FILE
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # Non-fatal


def _cache_is_fresh(cache: Dict[str, Any]) -> bool:
    """Return True if the cache is less than _CACHE_MAX_AGE_HOURS old."""
    try:
        last_check = cache.get("last_check", "")
        if not last_check:
            return False
        dt = datetime.fromisoformat(last_check)
        age = datetime.now(timezone.utc) - dt
        return age < timedelta(hours=_CACHE_MAX_AGE_HOURS)
    except Exception:
        return False


def get_cached_version_info(context_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Read version cache from disk only.  No network calls.

    Returns None if no cache exists.  Used by ``--version`` for instant output.
    """
    cache = _read_cache(context_dir)
    if not cache:
        return None

    from . import __version__ as current

    latest = cache.get("latest_version")
    if not latest:
        return None

    update_type = _classify_update(current, latest)
    rv = check_running_vs_installed()

    return {
        "current": current,
        "latest": latest,
        "update_available": update_type is not None,
        "update_type": update_type,
        "restart_required": rv["restart_required"],
        "running": rv["running"],
        "installed": rv["installed"],
    }


def get_version_info(context_dir: Path) -> Dict[str, Any]:
    """
    Return version info dict, using disk cache if fresh.

    May make a network call to PyPI if the cache is stale or missing.
    """
    from . import __version__ as current

    rv = check_running_vs_installed()
    result: Dict[str, Any] = {
        "current": current,
        "latest": None,
        "update_available": False,
        "update_type": None,
        "restart_required": rv["restart_required"],
        "running": rv["running"],
        "installed": rv["installed"],
        "cooldown_active": False,
        "cache_age_hours": None,
    }

    if os.environ.get("BOYCE_DISABLE_UPDATE_CHECK"):
        return result

    # Try cache first
    cache = _read_cache(context_dir)
    if cache and _cache_is_fresh(cache):
        latest = cache.get("latest_version")
        if latest:
            result["latest"] = latest
            result["update_type"] = _classify_update(current, latest)
            result["update_available"] = result["update_type"] is not None
            result["cooldown_active"] = cache.get("cooldown_active", False)
            try:
                dt = datetime.fromisoformat(cache["last_check"])
                result["cache_age_hours"] = round(
                    (datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1,
                )
            except Exception:
                pass
            return result

    # Cache miss — fetch from PyPI
    pypi_info = _fetch_pypi_info()
    if not pypi_info:
        return result

    latest = pypi_info["version"]
    result["latest"] = latest
    result["update_type"] = _classify_update(current, latest)
    result["update_available"] = result["update_type"] is not None

    # Cooldown check
    cooldown_active = False
    if pypi_info.get("upload_time"):
        try:
            upload_dt = datetime.fromisoformat(pypi_info["upload_time"])
            age_hours = (datetime.now(timezone.utc) - upload_dt).total_seconds() / 3600
            if age_hours < _COOLDOWN_HOURS:
                cooldown_active = True
        except Exception:
            pass
    result["cooldown_active"] = cooldown_active

    # Write cache
    _write_cache(context_dir, {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "latest_version": latest,
        "current_version_at_check": current,
        "cooldown_active": cooldown_active,
    })

    return result


# ---------------------------------------------------------------------------
# Install method detection
# ---------------------------------------------------------------------------

def _detect_install_method() -> Tuple[str, List[str]]:
    """
    Detect how Boyce was installed and return (method_name, upgrade_command).

    Tries in order: pipx, uv, pip (fallback using sys.executable).
    """
    # 1. pipx
    pipx = shutil.which("pipx")
    if pipx:
        try:
            result = subprocess.run(
                [pipx, "list", "--short"],
                capture_output=True, text=True, timeout=5,
            )
            if "boyce" in result.stdout.lower():
                return ("pipx", [pipx, "upgrade", "boyce"])
        except Exception:
            pass

    # 2. uv
    uv = shutil.which("uv")
    if uv:
        return ("uv", [uv, "pip", "install", "--upgrade", "boyce"])

    # 3. pip fallback — use sys.executable, never bare pip
    return ("pip", [sys.executable, "-m", "pip", "install", "--upgrade", "boyce"])


# ---------------------------------------------------------------------------
# Restart instructions
# ---------------------------------------------------------------------------

def _get_restart_instructions() -> str:
    """
    Detect installed editors and return restart instructions.

    Reuses init_wizard.detect_hosts() for editor detection.
    """
    try:
        from .init_wizard import detect_hosts

        hosts = detect_hosts()
        detected = [h for h in hosts if h.exists]
    except Exception:
        detected = []

    instructions = {
        "Cursor": "  Cursor: Settings → Tools & MCP → toggle Boyce off/on, or restart Cursor",
        "VS Code": "  VS Code: Cmd+Shift+P → 'MCP: Restart Server'",
        "Claude Code": "  Claude Code: exit and relaunch",
        "Windsurf": "  Windsurf: Cmd+Shift+P → 'MCP: Restart Server'",
    }

    lines = ["Restart your editor to load the new version:"]

    if detected:
        for h in detected:
            for name, instruction in instructions.items():
                if name.lower() in h.name.lower():
                    lines.append(instruction)
                    break
    else:
        lines.extend(instructions.values())

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# boyce update
# ---------------------------------------------------------------------------

def run_update(yes: bool = False) -> int:
    """
    Check for updates and apply if available.

    Exit codes:
        0 — successfully upgraded
        1 — already on latest version
        2 — error during upgrade
    """
    from . import __version__ as current

    print(f"Boyce {current}")
    print("Checking for updates...")

    latest = fetch_latest_version()
    if latest is None:
        print("Could not reach PyPI. Check your internet connection.")
        return 2

    update_type = _classify_update(current, latest)
    if update_type is None:
        print(f"Boyce {current} is already up to date.")
        return 1

    print(f"Boyce {current} → {latest} available ({update_type} update).")

    method, cmd = _detect_install_method()
    print(f"Install method: {method}")
    print(f"Command: {' '.join(cmd)}")

    if not yes:
        if not sys.stdin.isatty():
            print("Non-interactive mode — pass --yes to confirm.")
            return 2
        try:
            answer = input("\nProceed? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Cancelled.")
                return 2
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 2

    print(f"\nRunning: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=120)
        if result.returncode != 0:
            print(f"Upgrade failed (exit code {result.returncode}).")
            return 2
    except subprocess.TimeoutExpired:
        print("Upgrade timed out after 120 seconds.")
        return 2
    except Exception as exc:
        print(f"Upgrade failed: {exc}")
        return 2

    # Verify the upgrade
    try:
        verify = subprocess.run(
            [sys.executable, "-m", "boyce", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        new_version = verify.stdout.strip()
        if latest in new_version:
            print(f"\nUpgraded to Boyce {latest}.")
        else:
            print(f"\nUpgrade command succeeded but version reports: {new_version}")
    except Exception:
        print("\nUpgrade command succeeded. Verify with: boyce --version")

    # Restart instructions
    print(f"\n{_get_restart_instructions()}")

    return 0
