# Handoff: Version Lifecycle — Full Implementation & Validation

**From:** Opus strategic session (2026-03-23)
**To:** Claude Code — implement all 12 items, validate exhaustively, batch HITL at end

---

## Executive Context

Will identified a critical experience bug during Cursor cross-platform testing: there is no mechanism for users or agents to discover, apply, or complete Boyce upgrades. This handoff covers 12 items that together create a complete version lifecycle — from discovery through upgrade through server reload. All 12 ship together. Do not defer any.

This plan was validated against industry best practices from pip (`self_outdated_check.py`), npm (`update-notifier`, 5.2M weekly downloads), Terraform (`Checkpoint` service), rustup (`self update` / `auto-self-update`), GitHub CLI (24h extension update checks), and the MCP protocol spec (server-initiated shutdown). Everything here is battle-tested in production by tools with millions of users.

---

## Files to Create

| File | Purpose |
|------|---------|
| `boyce/src/boyce/version_check.py` | New module — all version lifecycle logic |
| `boyce/tests/test_version_check.py` | New — unit tests for version_check |

## Files to Modify

| File | Changes |
|------|---------|
| `boyce/src/boyce/cli.py` | Add `update` subcommand, enhance `--version` output |
| `boyce/src/boyce/server.py` | Wire version check into `_check_environment_suggestions` and `check_health` |
| `boyce/src/boyce/doctor.py` | Add `check_version()` as 6th check function |
| `boyce/src/boyce/__init__.py` | No changes needed (already exports `__version__`) |
| `boyce/tests/test_cli_smoke.py` | Add `boyce update` smoke tests |
| `boyce/tests/test_doctor.py` | Add `check_version` tests |

---

## Item 1: PyPI Version Check — Core Function

**File:** `version_check.py`

**Implementation:**

```python
def fetch_latest_version(timeout: float = 2.0) -> Optional[str]:
    """
    Hit PyPI JSON API, return latest version string.
    Returns None on any failure (network, timeout, parse).
    
    Uses stdlib only — no requests, no aiohttp, no new dependencies.
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
            return data["info"]["version"]
    except Exception:
        return None
```

**Key constraints:**
- stdlib only (`urllib.request`), zero new dependencies
- Hard 2-second timeout default
- Returns `None` on ANY failure — never raises, never blocks
- Respects `BOYCE_DISABLE_UPDATE_CHECK` env var (Item 3)

---

## Item 2: 24-Hour Disk Cache

**File:** `version_check.py`

**Implementation:**

The disk cache lives at `_local_context/version_check.json`. Structure:

```json
{
    "last_check": "2026-03-23T04:30:00+00:00",
    "latest_version": "0.2.0",
    "current_version_at_check": "0.1.0"
}
```

```python
_CACHE_FILE = "version_check.json"
_CACHE_MAX_AGE_HOURS = 24

def get_version_info(context_dir: Path) -> Dict[str, Any]:
    """
    Return version info dict, using disk cache if fresh.
    
    Returns:
        {
            "current": "0.1.0",
            "latest": "0.2.0" | None,
            "update_available": bool,
            "update_type": "major" | "minor" | "patch" | None,
            "restart_required": bool,  # running != installed
            "cache_age_hours": float | None,
        }
    """
```

Logic:
1. Read `_local_context/version_check.json`
2. If cache exists and `last_check` is < 24h old → use cached `latest_version`
3. If cache is stale or missing → call `fetch_latest_version()`
4. Write result back to cache file
5. Compare versions using `packaging.version.Version`
6. Also check running-vs-installed (Item 7)
7. Return structured dict

**Cache write must be non-fatal** — wrap in try/except, never block on file I/O failure. Same pattern as `run_doctor`'s `environment.json` write.

---

## Item 3: Opt-Out Env Var

**File:** `version_check.py`

**Implementation:** Single guard at the top of `fetch_latest_version()`:

```python
if os.environ.get("BOYCE_DISABLE_UPDATE_CHECK"):
    return None
```

Also check in `get_version_info()` — if disabled, return early with `latest: None, update_available: False`.

**Document in:**
- `cli.py` module docstring (add to Environment variables section)
- `boyce doctor` output (show "version check: disabled" when set)

---

## Item 4: Version Info in `boyce --version`

**File:** `cli.py`

**Current code (in `main()`):**
```python
if subcmd == "version":
    from importlib.metadata import version as _version, PackageNotFoundError
    try:
        print(_version("boyce"))
    except PackageNotFoundError:
        print("boyce (development install)")
    return
```

**New code:**
```python
if subcmd == "version":
    from importlib.metadata import version as _version, PackageNotFoundError
    try:
        ver = _version("boyce")
    except PackageNotFoundError:
        ver = "dev"
    
    # Attempt to show latest version from cache (don't fetch — too slow for --version)
    suffix = ""
    try:
        from .version_check import get_cached_version_info
        info = get_cached_version_info(Path("_local_context"))
        if info and info.get("update_available"):
            suffix = f" (latest: {info['latest']} — run `boyce update`)"
    except Exception:
        pass
    
    print(f"boyce {ver}{suffix}")
    return
```

**Important:** `--version` must be instant. Use `get_cached_version_info()` which ONLY reads the disk cache, never makes a network call. If no cache exists, just print the version with no suffix.

Add a separate function:

```python
def get_cached_version_info(context_dir: Path) -> Optional[Dict[str, Any]]:
    """Read version cache from disk only. No network calls. Returns None if no cache."""
```

---

## Item 5: `boyce update` Subcommand

**File:** `cli.py` (dispatch) + `version_check.py` (logic)

### cli.py changes

Add to `_parse_args()`:
```python
if subcmd == "update":
    yes = "--yes" in argv or "-y" in argv
    return ("update", {"yes": yes})
```

Add to `main()`:
```python
if subcmd == "update":
    from .version_check import run_update
    code = run_update(yes=kwargs["yes"])
    sys.exit(code)
```

Add to module docstring:
```
    boyce update [--yes]                   Check for and apply Boyce updates
```

Add to unknown-command error message in `_parse_args()`:
```python
return ("error", {"msg": f"Unknown command: '{subcmd}'\nUsage: boyce [ask|chat|doctor|init|scan|serve|update] ...\nRun 'boyce --help' for full usage."})
```

### version_check.py — `run_update()`

```python
def run_update(yes: bool = False) -> int:
    """
    Check for updates and apply if available.
    
    Exit codes:
        0 — successfully upgraded
        1 — already on latest version
        2 — error during upgrade
    """
```

Logic:
1. Call `fetch_latest_version()` (always fresh, not cached)
2. Compare against current version
3. If current >= latest → print "Boyce {version} is already up to date." → return 1
4. Print "Boyce {current} → {latest} available."
5. Detect install method (Item 6)
6. Print the exact command that will be run
7. If not `--yes` → prompt for confirmation (or if stdin is not a TTY, require `--yes`)
8. Execute the upgrade subprocess
9. Verify the upgrade worked (Item 5 verification below)
10. Print editor restart instructions (Item 8)
11. Return 0 on success, 2 on error

### Post-upgrade verification

After the pip/uv/pipx subprocess exits 0, verify by running `boyce --version` as a **separate subprocess** (you cannot re-import in-process — Python module cache gives stale `__version__`):

```python
result = subprocess.run(
    [sys.executable, "-m", "boyce", "--version"],
    capture_output=True, text=True, timeout=5,
)
new_version = result.stdout.strip()
```

Compare `new_version` against `latest`. If they match → success. If not → warn but don't fail.

---

## Item 6: Install Method Detection

**File:** `version_check.py`

```python
def _detect_install_method() -> Tuple[str, List[str]]:
    """
    Detect how Boyce was installed and return (method_name, upgrade_command).
    
    Try in order, stop at first match:
    1. pipx — if `pipx list` output contains 'boyce'
    2. uv — if `uv` is on PATH
    3. pip — fallback using sys.executable
    """
```

Logic:
1. `shutil.which("pipx")` → if found, run `pipx list --short`, check if "boyce" appears → return `("pipx", ["pipx", "upgrade", "boyce"])`
2. `shutil.which("uv")` → if found → return `("uv", ["uv", "pip", "install", "--upgrade", "boyce"])`
3. Fallback → return `("pip", [sys.executable, "-m", "pip", "install", "--upgrade", "boyce"])`

**Critical:** Use `sys.executable` for the pip fallback, never bare `pip`. Bare `pip` may resolve to a different Python installation.

Run the detected command via `subprocess.run()` with stdout/stderr passed through to the terminal.

---

## Item 7: Stale-Process Detection

**File:** `version_check.py`

```python
def check_running_vs_installed() -> Dict[str, Any]:
    """
    Compare the version loaded in memory vs what's installed on disk.
    
    Returns:
        {
            "running": "0.1.0",
            "installed": "0.2.0",
            "restart_required": True,
        }
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
```

**Wire into `get_version_info()`** — the returned dict should include `restart_required` from this check. This is the highest-priority signal — it means an upgrade happened but the MCP server is still running old code.

**Wire into `_check_environment_suggestions()` in server.py** — if `restart_required` is True, this should be the FIRST suggestion, before snapshot staleness or doctor age:

```python
"Boyce was upgraded to {installed} but the running server is still {running}. Restart your editor to load the new version."
```

**Wire into `check_health()` in server.py** — add a `version` key to the response:

```json
{
    "version": {
        "running": "0.1.0",
        "installed": "0.2.0",
        "latest": "0.3.0",
        "restart_required": true,
        "update_available": true
    }
}
```

---

## Item 8: Editor-Specific Restart Instructions

**File:** `version_check.py`

```python
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
    
    lines = ["Restart your editor to load the new version:"]
    
    # Map editor names to restart instructions
    instructions = {
        "Cursor": "  Cursor: Settings → Tools & MCP → toggle Boyce off/on, or restart Cursor",
        "VS Code": "  VS Code: Cmd+Shift+P → 'MCP: Restart Server'",
        "Claude Code": "  Claude Code: exit and relaunch",
        "Windsurf": "  Windsurf: Cmd+Shift+P → 'MCP: Restart Server'",
    }
    
    if detected:
        for h in detected:
            for name, instruction in instructions.items():
                if name.lower() in h.name.lower():
                    lines.append(instruction)
                    break
    else:
        # No editors detected — show all
        lines.extend(instructions.values())
    
    return "\n".join(lines)
```

**Call this at the end of `run_update()`** after a successful upgrade.

**Also include in `check_health` and `environment_suggestions`** when `restart_required` is True — but use a shorter form: "Restart your editor to load Boyce {installed}."

---

## Item 9: Graceful Self-Termination (Gated)

**File:** `version_check.py` + `server.py`

**Implementation:** When stale-process is detected AND `BOYCE_AUTO_RESTART_ON_UPDATE=1` is set, the MCP server cleanly exits after the current tool call completes. The MCP host will respawn it with the new binary.

In `server.py`, add a post-tool-call hook. The cleanest place is at the end of `_build_advertising_layer()` since every tool response flows through it:

```python
# At the end of _build_advertising_layer(), after assembling the result dict:
if os.environ.get("BOYCE_AUTO_RESTART_ON_UPDATE"):
    from .version_check import check_running_vs_installed
    rv = check_running_vs_installed()
    if rv["restart_required"]:
        import threading
        # Exit after a short delay to allow the current response to flush
        def _delayed_exit():
            import time
            time.sleep(0.5)
            import sys
            sys.exit(0)
        threading.Thread(target=_delayed_exit, daemon=True).start()
```

**Default: OFF.** The env var must be explicitly set. This is aggressive behavior and we want to observe it working before making it default.

**Caveat:** If the MCP host does not auto-respawn stdio servers after exit, the user will lose Boyce until they manually restart their editor. Claude Code and Cursor DO respawn. Other hosts may not. Document this in the env var's docstring.

**MCP protocol justification:** The spec says "The server MAY initiate shutdown by closing its output stream to the client and exiting." This is compliant.

---

## Item 10: `check_version()` as 6th Doctor Check

**File:** `doctor.py`

```python
def check_version(context_dir: Path) -> Dict[str, Any]:
    """
    Check Boyce version against PyPI and detect stale processes.
    
    Returns:
        {
            "status": "ok" | "warning" | "info",
            "current": "0.1.0",
            "latest": "0.2.0" | None,
            "installed": "0.1.0",
            "update_available": bool,
            "restart_required": bool,
            "items": [{"fix": "boyce update"}],
        }
    """
    from .version_check import get_version_info
    
    info = get_version_info(context_dir)
    items = []
    
    if info.get("restart_required"):
        status = "warning"
        items.append({
            "name": "version",
            "fix": f"Restart editor (running {info['running']}, installed {info['installed']})",
        })
    elif info.get("update_available"):
        status = "info"
        items.append({
            "name": "version", 
            "fix": f"boyce update (current: {info['current']}, latest: {info['latest']})",
        })
    else:
        status = "ok"
    
    return {
        "status": status,
        "current": info.get("current"),
        "latest": info.get("latest"),
        "installed": info.get("installed"),
        "update_available": info.get("update_available", False),
        "restart_required": info.get("restart_required", False),
        "items": items,
    }
```

**Wire into `run_doctor()`:**

Add `check_version` as the FIRST check in the `results["checks"]` dict so it prints first:

```python
results: Dict[str, Any] = {
    "checks": {
        "version": check_version(context_dir),   # FIRST
        "editors": check_editors(),
        "database": await check_database(context_dir),
        "snapshots": check_snapshots(context_dir),
        "sources": check_sources(),
        "server": check_server(context_dir),
    },
    ...
}
```

**Update `_print_human_readable()`** — the version check should render distinctly:

```
  Boyce Doctor v0.1.0
  ========================================

  ⚠ version: 0.1.0 (0.2.0 available — run `boyce update`)
  ✓ editors: ok
  ...
```

When disabled via env var:
```
  ℹ version: 0.1.0 (update check disabled)
```

---

## Item 11: Supply Chain Cooldown (48h)

**File:** `version_check.py`

**Implementation:** When fetching from PyPI, also check the upload time of the latest release. If it was published less than 48 hours ago, treat the *previous* stable release as "latest" for notification purposes.

Modify `fetch_latest_version()` to return a richer result:

```python
def _fetch_pypi_info(timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """
    Fetch version info from PyPI. Returns dict with version and upload time,
    or None on failure.
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
        upload_time = None
        if release_files:
            upload_time = release_files[0].get("upload_time_iso_8601")
        
        return {"version": latest, "upload_time": upload_time}
    except Exception:
        return None
```

In `get_version_info()`, apply the cooldown:

```python
COOLDOWN_HOURS = 48

if pypi_info and pypi_info.get("upload_time"):
    upload_dt = datetime.fromisoformat(pypi_info["upload_time"])
    age_hours = (datetime.now(timezone.utc) - upload_dt).total_seconds() / 3600
    if age_hours < COOLDOWN_HOURS:
        # Too fresh — don't recommend this version in environment_suggestions
        # But DO show it in check_health and boyce doctor (with a note)
        result["cooldown_active"] = True
```

**Behavior:**
- `environment_suggestions` — suppressed during cooldown (don't nudge for versions < 48h old)
- `check_health` — shown with note: "0.2.0 available (published {N}h ago, cooldown active)"
- `boyce doctor` — shown with note
- `boyce update` — always shows latest regardless of cooldown (user explicitly asked)

---

## Item 12: Version-Semantic Nudge Filtering

**File:** `version_check.py`

**Implementation:** Only nudge in `environment_suggestions` for minor or major version bumps. Patch-only bumps are silent in `environment_suggestions` but visible in `check_health` and `boyce doctor`.

```python
def _classify_update(current: str, latest: str) -> Optional[str]:
    """Classify the update type. Returns 'major', 'minor', 'patch', or None."""
    try:
        from packaging.version import Version
        c = Version(current)
        l = Version(latest)
        if l <= c:
            return None
        if l.major > c.major:
            return "major"
        if l.minor > c.minor:
            return "minor"
        return "patch"
    except Exception:
        return None
```

**Behavior:**
- `environment_suggestions` — only fires for `major` or `minor` (not `patch`)
- `check_health` — always shows any available update
- `boyce doctor` — always shows any available update
- `boyce update` — always shows any available update
- `boyce --version` — always shows any available update

---

## Wiring Summary for server.py

### `_check_environment_suggestions()` changes

Add version check BEFORE the existing snapshot staleness check. This is the highest-priority suggestion:

```python
def _check_environment_suggestions() -> List[str]:
    global _environment_checked
    if _environment_checked:
        return []
    _environment_checked = True

    suggestions: List[str] = []

    # 0. Version lifecycle checks (highest priority)
    try:
        from .version_check import get_version_info
        vi = get_version_info(_LOCAL_CONTEXT)
        
        # Stale process — highest priority
        if vi.get("restart_required"):
            suggestions.append(
                f"Boyce was upgraded to {vi['installed']} but the running "
                f"server is still {vi['running']}. Restart your editor."
            )
        # Update available (minor/major only, respect cooldown)
        elif (vi.get("update_available") 
              and vi.get("update_type") in ("major", "minor")
              and not vi.get("cooldown_active")):
            suggestions.append(
                f"Boyce {vi['latest']} available — run `boyce update` to upgrade."
            )
    except Exception:
        pass  # Non-fatal

    # 1. Existing: environment.json / doctor age check
    # ... (keep existing code)
    
    # 2. Existing: snapshot staleness check
    # ... (keep existing code)

    return suggestions[:3]
```

### `check_health()` changes

Add version info to the response. After the existing doctor checks:

```python
# Version info (always show full picture)
try:
    from .version_check import get_version_info
    version_info = get_version_info(_LOCAL_CONTEXT)
    result["version"] = {
        "current": version_info.get("current"),
        "latest": version_info.get("latest"),
        "installed": version_info.get("installed"),
        "update_available": version_info.get("update_available", False),
        "restart_required": version_info.get("restart_required", False),
    }
    if version_info.get("restart_required"):
        suggestions.insert(0, 
            f"Restart editor (running {version_info['running']}, "
            f"installed {version_info['installed']})"
        )
    elif version_info.get("update_available"):
        suggestions.append(
            f"Boyce {version_info['latest']} available — run `boyce update`"
        )
except Exception:
    pass
```

---

## Testing Strategy

### Unit Tests: `test_version_check.py` (new file)

CC can run all of these autonomously. Mock PyPI responses, mock filesystem, mock subprocesses.

```python
"""Tests for boyce.version_check — version lifecycle management."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
```

**Test cases to implement:**

1. **`test_fetch_latest_version_success`** — mock `urllib.request.urlopen` to return a valid PyPI JSON response. Assert returns the version string.

2. **`test_fetch_latest_version_timeout`** — mock urlopen to raise `socket.timeout`. Assert returns None.

3. **`test_fetch_latest_version_network_error`** — mock urlopen to raise `URLError`. Assert returns None.

4. **`test_fetch_latest_version_bad_json`** — mock urlopen to return invalid JSON. Assert returns None.

5. **`test_fetch_latest_version_disabled_by_env`** — set `BOYCE_DISABLE_UPDATE_CHECK=1`. Assert returns None without making any network call.

6. **`test_disk_cache_write_and_read`** — call `get_version_info()` with mocked PyPI. Assert cache file created. Call again. Assert PyPI NOT called second time (cache hit).

7. **`test_disk_cache_expired`** — write a cache file with `last_check` > 24h ago. Call `get_version_info()`. Assert PyPI IS called (cache miss).

8. **`test_disk_cache_fresh`** — write a cache file with `last_check` < 24h ago. Call `get_version_info()`. Assert PyPI NOT called.

9. **`test_disk_cache_write_failure_non_fatal`** — mock `open()` for the cache file to raise OSError. Assert `get_version_info()` still returns valid result (doesn't crash).

10. **`test_get_cached_version_info_no_file`** — no cache file exists. Assert returns None.

11. **`test_get_cached_version_info_reads_cache`** — cache file exists with data. Assert returns parsed data without network call.

12. **`test_classify_update_major`** — "0.1.0" vs "1.0.0" → "major"

13. **`test_classify_update_minor`** — "0.1.0" vs "0.2.0" → "minor"

14. **`test_classify_update_patch`** — "0.1.0" vs "0.1.1" → "patch"

15. **`test_classify_update_none`** — "0.2.0" vs "0.1.0" → None (downgrade)

16. **`test_classify_update_equal`** — "0.1.0" vs "0.1.0" → None

17. **`test_check_running_vs_installed_match`** — mock `__version__` and `importlib.metadata.version` to return same value. Assert `restart_required` is False.

18. **`test_check_running_vs_installed_mismatch`** — mock them to differ. Assert `restart_required` is True.

19. **`test_detect_install_method_pipx`** — mock `shutil.which("pipx")` to return a path, mock subprocess to show boyce in pipx list. Assert returns `("pipx", ["pipx", "upgrade", "boyce"])`.

20. **`test_detect_install_method_uv`** — mock `which("pipx")` to return None, `which("uv")` to return a path. Assert returns uv command.

21. **`test_detect_install_method_pip_fallback`** — mock both `which()` calls to return None. Assert returns pip command with `sys.executable`.

22. **`test_run_update_already_latest`** — mock `fetch_latest_version()` to return current version. Assert exit code 1.

23. **`test_run_update_success`** — mock fetch to return newer version, mock subprocess to succeed, mock verification. Assert exit code 0.

24. **`test_run_update_upgrade_failure`** — mock fetch to return newer version, mock subprocess to fail. Assert exit code 2.

25. **`test_cooldown_suppresses_fresh_release`** — mock PyPI response with upload_time < 48h ago. Assert `cooldown_active` is True in result.

26. **`test_cooldown_allows_old_release`** — mock PyPI response with upload_time > 48h ago. Assert `cooldown_active` is False.

27. **`test_nudge_filtering_patch_suppressed`** — patch-only update. Assert NOT included in environment_suggestions behavior.

28. **`test_nudge_filtering_minor_shown`** — minor update. Assert IS included.

29. **`test_restart_instructions_with_detected_editors`** — mock `detect_hosts()` to return Cursor. Assert instructions mention Cursor.

30. **`test_restart_instructions_no_editors`** — mock `detect_hosts()` to return empty. Assert all instructions shown.

### Doctor Tests: additions to `test_doctor.py`

31. **`test_check_version_returns_structure`** — assert has `status`, `current`, `items` keys.

32. **`test_check_version_update_available`** — mock PyPI to return newer version. Assert status is "info" and items has fix suggestion.

33. **`test_check_version_restart_required`** — mock running != installed. Assert status is "warning".

34. **`test_check_version_up_to_date`** — mock same version. Assert status is "ok" and items is empty.

35. **`test_run_doctor_includes_version_check`** — run full doctor with json_output. Assert "version" key in checks.

36. **`test_run_doctor_version_is_first_check`** — run full doctor. Assert "version" is first key in checks dict (Python 3.7+ dicts are ordered).

### CLI Smoke Tests: additions to `test_cli_smoke.py`

37. **`boyce update --help` or `boyce update` with no network** — should not hang, should exit cleanly. Expected exit: 1 or 2 (no network in test env).

38. **`boyce --version` enhanced output** — should exit 0, should contain version string.

### Integration-Level Validation (CC should run these after implementation)

39. **Full pytest suite** — `pytest boyce/tests/ -v` — all existing tests MUST still pass. Zero regressions.

40. **CLI smoke suite** — `python boyce/tests/test_cli_smoke.py` — all existing + new checks pass.

41. **Import check** — `python -c "from boyce.version_check import get_version_info, run_update, check_running_vs_installed"` — no import errors.

42. **Module structure check** — `python -c "import boyce; print(boyce.__version__)"` — still works.

---

## Execution Order

CC should implement in this order to minimize back-and-forth:

1. **Create `version_check.py`** with all functions (Items 1, 2, 3, 6, 7, 8, 11, 12)
2. **Create `test_version_check.py`** with all 30 test cases
3. **Run tests** — fix any failures
4. **Modify `cli.py`** (Items 4, 5) — add `update` subcommand and enhanced `--version`
5. **Modify `doctor.py`** (Item 10) — add `check_version()` as 6th check
6. **Modify `server.py`** (Items 7, 9) — wire into `_check_environment_suggestions` and `check_health`
7. **Update `test_doctor.py`** — add version check tests
8. **Update `test_cli_smoke.py`** — add `boyce update` smoke tests
9. **Run full test suite** — `pytest boyce/tests/ -v`
10. **Run CLI smoke tests** — `python boyce/tests/test_cli_smoke.py`
11. **Verify import chain** — no circular imports, no missing dependencies

---

## HITL Gates (Batched at End)

After CC completes all implementation and testing:

1. **Will reviews the diff** — `git diff` to review all changes
2. **Will runs `boyce doctor`** in the real dev environment to see the new version check output
3. **Will runs `boyce update`** to verify the UX feels right
4. **Will does a test publish cycle** (if ready) to verify the PyPI check works against a real package
5. **Will runs the Cursor cross-platform test** — this was the original gate

6. **CC updates CLAUDE.md** — new module (`version_check.py`), new env vars (`BOYCE_DISABLE_UPDATE_CHECK`, `BOYCE_AUTO_RESTART_ON_UPDATE`), new CLI command (`boyce update`), updated tool count references
7. **Will updates README/RELEASING** — public-facing copy is Will's voice. CC flags what needs updating but doesn't write it.

All seven of these can happen in one sitting after CC is done.

---

## Constraints & Reminders

- **One new explicit dependency:** Add `packaging` to `pyproject.toml` dependencies. It's load-bearing for version comparison logic. ~500KB, the standard library for version semantics in Python. Not optional, not extras — core dep.
- **Otherwise stdlib only:** `urllib.request`, `json`, `shutil`, `subprocess`, `importlib.metadata`.
- **All file paths use `_LOCAL_CONTEXT` pattern** — `Path("_local_context")` relative to cwd, consistent with existing code.
- **All network calls fail silently** — never block, never raise to the user.
- **All file writes are non-fatal** — wrap in try/except.
- **Use `sys.executable`** for pip subprocess, never bare `pip`.
- **Vim only** — all editing in vim, never nano.
- **Run tests with `pytest`** — the project uses pytest, not unittest runner.
- **Amazon Redshift 1.0.121035 (PostgreSQL 8.0.2 base)** — not relevant to this task but don't break any SQL-related tests.

---

## Read These Files Before Starting

Core (read in this order):
1. `boyce/src/boyce/__init__.py` — `__version__`, exports
2. `boyce/src/boyce/cli.py` — subcommand dispatch, `_parse_args()`, `main()`
3. `boyce/src/boyce/server.py` — `_check_environment_suggestions()`, `check_health()`, `_build_advertising_layer()`
4. `boyce/src/boyce/doctor.py` — check functions, `run_doctor()`, `_print_human_readable()`
5. `boyce/src/boyce/init_wizard.py` — `detect_hosts()`, `MCPHost` dataclass (for editor detection)
6. `boyce/src/boyce/connections.py` — `ConnectionStore` (for understanding `_local_context` pattern)

Tests (read before writing new tests):
7. `boyce/tests/test_cli_smoke.py` — CLI test patterns
8. `boyce/tests/test_doctor.py` — doctor test patterns

Strategy (for context):
9. `_strategy/MASTER.md` — advertising layer docs (offset 278+)
