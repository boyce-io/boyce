#!/usr/bin/env python3
"""
verify_demo.py — Operation Trap Reveal
Boyce Magic Moment Demo: Safety & Grounding

Proves that the seeded subscriptions table contains the exact "trap" distribution
used in the demo, and that Boyce's Eyes (profile_data) surface it.

Pipeline exercised:
    Postgres DB (Docker) → PostgresAdapter.profile_column()
    → NULL distribution on subscriptions.status
    → Recent last_login on cancelled users

Usage:
    # Full run (spins up Docker, seeds, profiles, tears down):
    python verify_demo.py

    # Skip Docker if DB is already running:
    SKIP_DOCKER=1 python verify_demo.py

    # Point at a different DB (skip Docker implied):
    BOYCE_DB_URL=postgresql://... python verify_demo.py

Requires:
    pip install "boyce[postgres]"
    docker (or SKIP_DOCKER=1 with a running Postgres)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

_DEMO_DIR = Path(__file__).parent
_REPO_ROOT = _DEMO_DIR.parent.parent              # Boyce/
_PROTO_ROOT = _REPO_ROOT / "boyce"  # boyce/
sys.path.insert(0, str(_PROTO_ROOT))

_COMPOSE_FILE = _DEMO_DIR / "docker-compose.yml"
_SEED_SQL     = _DEMO_DIR / "seed.sql"
_SNAPSHOT_JSON = _DEMO_DIR / "snapshot.json"

_DB_URL        = os.environ.get(
    "BOYCE_DB_URL",
    "postgresql://boyce:password@localhost:5433/demo_db",
)
_SNAPSHOT_NAME = "magic_moment"

# Expected distribution (exact — seed.sql uses generate_series, not random counts)
_EXPECTED_ROWS        = 1_000
_EXPECTED_NULL_COUNT  = 300
_EXPECTED_NULL_PCT    = 30.0
_EXPECTED_DISTINCT    = 2      # 'active', 'cancelled' — NULL is not a distinct value
_EXPECTED_CANCELLED   = 200
_EXPECTED_ACTIVE      = 500
_MAX_CANCELLED_LOGIN_DAYS = 30  # All cancelled rows logged in within this window


# ---------------------------------------------------------------------------
# Terminal colours
# ---------------------------------------------------------------------------

RED    = "\033[0;31m"
GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

SEP = "=" * 62


def _ok(msg: str)   -> None: print(f"{GREEN}  ✓{RESET}  {msg}")
def _warn(msg: str) -> None: print(f"{YELLOW}  ⚠{RESET}  {msg}")
def _info(msg: str) -> None: print(f"{CYAN}  →{RESET}  {msg}")
def _fail(msg: str) -> None: print(f"{RED}  ✗{RESET}  {msg}", file=sys.stderr)
def _die(msg: str)  -> None: _fail(msg); sys.exit(1)


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

def _check_prerequisites() -> None:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        _die(
            "asyncpg is not installed.\n"
            '    pip install "boyce[postgres]"'
        )

    try:
        from boyce_protocol.adapters.postgres import PostgresAdapter  # noqa: F401
    except ImportError as exc:
        _die(f"boyce not importable: {exc}\n    pip install -e boyce/")


# ---------------------------------------------------------------------------
# Docker helpers  (identical pattern to live_fire/run_mission.py)
# ---------------------------------------------------------------------------

def _docker_cmd() -> list:
    """Return the docker-compose command list, or raise with a clear install hint."""
    try:
        probe = subprocess.run(["docker", "compose", "version"], capture_output=True)
        if probe.returncode == 0:
            return ["docker", "compose"]
    except FileNotFoundError:
        pass
    try:
        subprocess.run(["docker-compose", "version"], capture_output=True, check=True)
        return ["docker-compose"]
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    _die(
        "Docker not found. Install Docker Desktop or run with:\n"
        "    SKIP_DOCKER=1 BOYCE_DB_URL=postgresql://... python verify_demo.py"
    )


def _docker_up() -> None:
    cmd = _docker_cmd() + ["-f", str(_COMPOSE_FILE), "up", "-d", "--wait"]
    subprocess.run(cmd, check=True, capture_output=True)


def _docker_down() -> None:
    cmd = _docker_cmd() + [
        "-f", str(_COMPOSE_FILE), "down",
        "--volumes", "--remove-orphans",
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def _wait_for_db(dsn: str, max_seconds: int = 90) -> None:
    import asyncpg
    deadline = time.monotonic() + max_seconds
    last_exc: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return
        except Exception as exc:
            last_exc = exc
            await asyncio.sleep(2.0)
    raise RuntimeError(
        f"Database did not become ready within {max_seconds}s.\nLast error: {last_exc}"
    )


async def _seed_db(dsn: str) -> None:
    import asyncpg
    sql = _SEED_SQL.read_text()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _build_snapshot() -> tuple:
    """
    Load snapshot.json, compute the canonical SHA-256 snapshot_id,
    return (snapshot_data_dict, SemanticSnapshot_object).
    """
    from boyce_protocol.types import SemanticSnapshot
    from boyce_protocol.validation import _compute_snapshot_hash

    data = json.loads(_SNAPSHOT_JSON.read_text())
    data.pop("_comment", None)

    data["snapshot_id"] = "placeholder"
    snap_tmp = SemanticSnapshot(**data)
    data["snapshot_id"] = _compute_snapshot_hash(snap_tmp)

    return data, SemanticSnapshot(**data)


# ---------------------------------------------------------------------------
# Demo report formatting
# ---------------------------------------------------------------------------

def _box(lines: list[str], width: int = 56) -> None:
    """Print a box around a list of lines."""
    border = "─" * width
    print(f"  ┌{border}┐")
    for line in lines:
        padding = width - len(line)
        print(f"  │ {line}{' ' * max(padding - 1, 0)}│")
    print(f"  └{border}┘")


def _print_status_profile(profile: Dict[str, Any]) -> None:
    null_pct   = profile["null_pct"]
    null_count = profile["null_count"]
    row_count  = profile["row_count"]
    distinct   = profile["distinct_count"]
    min_v      = profile["min_value"]
    max_v      = profile["max_value"]

    trap_flag = f"  ← {YELLOW}THE NULL TRAP{RESET}" if null_pct >= 25 else ""
    _box([
        f"  table        :  {profile['table']}",
        f"  column       :  {profile['column']}",
        f"  row_count    :  {row_count:,}",
        f"  null_count   :  {null_count:,}  ({null_pct:.1f}%)",
        f"  distinct     :  {distinct}  ('{min_v}', '{max_v}')",
        f"  null_pct     :  {null_pct:.1f}%",
    ])
    print()
    _warn(f"null_pct = {null_pct:.1f}% — 300 rows are INVISIBLE to:{trap_flag}")
    print()
    print("       DELETE FROM subscriptions WHERE status = 'cancelled'")
    print()
    _warn("These rows will be silently skipped. Is that intentional?")


def _print_cancelled_login_profile(profile: Dict[str, Any], max_days: int) -> None:
    row_count = profile["row_count"]
    min_v     = profile["min_value"]    # oldest last_login (as text)
    max_v     = profile["max_value"]    # most recent last_login (as text)

    _box([
        f"  table        :  {profile['table']} WHERE status='cancelled'",
        f"  column       :  {profile['column']}",
        f"  row_count    :  {row_count:,}  (the 'cancelled' segment)",
        f"  oldest login :  {min_v}",
        f"  newest login :  {max_v}",
        f"  window       :  all within {max_days} days",
    ])
    print()
    _warn(
        f"All {row_count} 'cancelled' users logged in within the past {max_days} days."
    )
    _warn("Deleting them now would destroy actively-engaged users.")


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------

async def _assert_status_profile(adapter: Any) -> None:
    from boyce_protocol.adapters.postgres import PostgresAdapter
    assert isinstance(adapter, PostgresAdapter)

    profile = await adapter.profile_column("subscriptions", "status")

    # Hard assertions
    actual_rows = profile["row_count"]
    assert actual_rows == _EXPECTED_ROWS, (
        f"Expected {_EXPECTED_ROWS} rows, got {actual_rows}. "
        "Did the seed run correctly?"
    )

    actual_null = profile["null_count"]
    assert actual_null == _EXPECTED_NULL_COUNT, (
        f"Expected {_EXPECTED_NULL_COUNT} NULL status rows, got {actual_null}."
    )

    actual_pct = profile["null_pct"]
    assert abs(actual_pct - _EXPECTED_NULL_PCT) < 1.0, (
        f"Expected null_pct ≈ {_EXPECTED_NULL_PCT}%, got {actual_pct}%."
    )

    actual_distinct = profile["distinct_count"]
    assert actual_distinct == _EXPECTED_DISTINCT, (
        f"Expected {_EXPECTED_DISTINCT} distinct status values "
        f"(active, cancelled), got {actual_distinct}. "
        "NULL is not counted as a distinct value — this is the trap."
    )

    return profile


async def _assert_cancelled_login_profile(adapter: Any) -> tuple:
    """
    Profile last_login for cancelled-only rows via a direct query.
    Returns (profile_dict, max_days_ago_float).
    """
    import asyncpg  # noqa: F401

    conn = adapter._conn
    rows = await conn.fetch("""
        WITH cancelled_profile AS (
            SELECT
                COUNT(*)                              AS row_count,
                COUNT(last_login)                     AS non_null_logins,
                MIN(last_login::TEXT)                 AS min_last_login,
                MAX(last_login::TEXT)                 AS max_last_login,
                EXTRACT(EPOCH FROM (NOW() - MIN(last_login))) / 86400
                                                      AS oldest_days_ago,
                EXTRACT(EPOCH FROM (NOW() - MAX(last_login))) / 86400
                                                      AS newest_days_ago
            FROM subscriptions
            WHERE status = 'cancelled'
        )
        SELECT * FROM cancelled_profile
    """)

    row = rows[0]
    cancelled_count = int(row["row_count"])
    oldest_days     = float(row["oldest_days_ago"])

    assert cancelled_count == _EXPECTED_CANCELLED, (
        f"Expected {_EXPECTED_CANCELLED} cancelled rows, got {cancelled_count}."
    )
    assert oldest_days <= _MAX_CANCELLED_LOGIN_DAYS + 1, (
        f"Expected all cancelled logins within {_MAX_CANCELLED_LOGIN_DAYS} days, "
        f"but oldest was {oldest_days:.1f} days ago."
    )

    profile = {
        "table": "subscriptions",
        "column": "last_login",
        "row_count": cancelled_count,
        "null_count": int(cancelled_count) - int(row["non_null_logins"]),
        "min_value": row["min_last_login"],
        "max_value": row["max_last_login"],
    }
    return profile, oldest_days


# ---------------------------------------------------------------------------
# Ingest snapshot (optional — for MCP demo readiness)
# ---------------------------------------------------------------------------

def _ingest_snapshot_to_local_context() -> str:
    """
    Persist the computed snapshot to _local_context/ so the MCP server
    can serve it when Claude Desktop calls ingest_source.
    Returns the snapshot_id.
    """
    from boyce_protocol.store import SnapshotStore
    from boyce_protocol.validation import validate_snapshot

    local_context = _PROTO_ROOT / "_local_context"
    store = SnapshotStore(local_context)

    snap_data, snapshot = _build_snapshot()
    errors = validate_snapshot(snap_data)
    if errors:
        raise RuntimeError(f"Snapshot validation failed:\n" + "\n".join(errors))

    store.save(snapshot, _SNAPSHOT_NAME)
    return snapshot.snapshot_id


# ---------------------------------------------------------------------------
# Main mission
# ---------------------------------------------------------------------------

async def run_trap_reveal() -> None:
    skip_docker = os.environ.get("SKIP_DOCKER") == "1" or os.environ.get("BOYCE_DB_URL")

    print(f"\n{SEP}")
    print(f"{BOLD}OPERATION TRAP REVEAL — Boyce Magic Moment Demo{RESET}")
    print(SEP)
    print()
    print("  Scenario: Product manager asks — 'Delete all cancelled")
    print("  subscriptions from the database.'")
    print()
    print("  The Trap: The table contains two hidden dangers the PM")
    print("  doesn't know about. Boyce's Eyes reveal them both.")
    print(SEP)

    # ------------------------------------------------------------------
    # Step 1 — Docker
    # ------------------------------------------------------------------
    print(f"\n{BOLD}[1/5] Spinning up Postgres container{RESET}")
    if not skip_docker:
        _info("Running docker-compose up ...")
        _docker_up()
        _ok("Container up  (postgres:15 on port 5433)")
    else:
        _info("SKIP_DOCKER=1 — using existing database")

    teardown_docker = not skip_docker

    from boyce_protocol.adapters.postgres import PostgresAdapter

    adapter = PostgresAdapter(_DB_URL)

    try:
        # ------------------------------------------------------------------
        # Step 2 — Wait
        # ------------------------------------------------------------------
        print(f"\n{BOLD}[2/5] Waiting for database{RESET}")
        _info(f"Connecting to {_DB_URL.split('@')[-1]} ...")
        await _wait_for_db(_DB_URL)
        _ok("Database ready")

        # ------------------------------------------------------------------
        # Step 3 — Seed
        # ------------------------------------------------------------------
        print(f"\n{BOLD}[3/5] Seeding subscriptions table{RESET}")
        _info("Executing seed.sql ...")
        await _seed_db(_DB_URL)
        _ok(
            f"Seeded: {_EXPECTED_ACTIVE} 'active'  "
            f"+ {_EXPECTED_CANCELLED} 'cancelled'  "
            f"+ {_EXPECTED_NULL_COUNT} NULL status"
        )
        print(f"       Total: {_EXPECTED_ROWS:,} rows")

        await adapter.connect()

        # ------------------------------------------------------------------
        # Step 4 — Eye #1: Profile the status column
        # ------------------------------------------------------------------
        print(f"\n{BOLD}[4/5] Boyce Eyes — profile_data(subscriptions, status){RESET}")
        print()
        print(f"  {CYAN}Naive query the PM requested:{RESET}")
        print()
        print(f"      DELETE FROM subscriptions WHERE status = 'cancelled'")
        print()
        print(f"  {CYAN}What Boyce sees before letting that run:{RESET}")
        print()

        status_profile = await _assert_status_profile(adapter)
        _print_status_profile(status_profile)

        _ok(f"null_count  = {status_profile['null_count']}  ({status_profile['null_pct']:.1f}%)")
        _ok(f"distinct    = {status_profile['distinct_count']}  (NULL is not a distinct value)")

        # ------------------------------------------------------------------
        # Step 5 — Eye #2: Profile cancelled users' last_login
        # ------------------------------------------------------------------
        print(f"\n{BOLD}[5/5] Boyce Eyes — profile last_login WHERE status='cancelled'{RESET}")
        print()
        print(f"  {CYAN}Before deleting, Boyce profiles the target rows:{RESET}")
        print()

        cancelled_profile, oldest_days = await _assert_cancelled_login_profile(adapter)
        _print_cancelled_login_profile(cancelled_profile, _MAX_CANCELLED_LOGIN_DAYS)

        _ok(f"cancelled_count = {cancelled_profile['row_count']}")
        _ok(f"oldest login    = {oldest_days:.1f} days ago  (within {_MAX_CANCELLED_LOGIN_DAYS}-day window)")

        # ------------------------------------------------------------------
        # Ingest snapshot to _local_context/ for MCP demo
        # ------------------------------------------------------------------
        print(f"\n{BOLD}[+] Saving snapshot to _local_context/ for MCP demo{RESET}")
        try:
            snap_id = _ingest_snapshot_to_local_context()
            _ok(f"Snapshot saved  (id={snap_id[:16]}...)")
            _info(f"Name: '{_SNAPSHOT_NAME}'  — ready for ask_boyce tool")
        except Exception as exc:
            _warn(f"Snapshot ingest failed (non-fatal for demo): {exc}")

        # ------------------------------------------------------------------
        # Final verdict
        # ------------------------------------------------------------------
        print()
        print(SEP)
        print(f"{GREEN}{BOLD}  TRAP CONFIRMED.  Boyce's Eyes caught both dangers.{RESET}")
        print(SEP)
        print()
        print(f"  {BOLD}Danger 1 — The NULL Trap:{RESET}")
        print(f"    {status_profile['null_count']} rows ({status_profile['null_pct']:.1f}%) have NULL status.")
        print(f"    They are invisible to WHERE status = 'cancelled'.")
        print(f"    A bulk delete would silently leave them orphaned — or")
        print(f"    a future job using WHERE status != 'active' would nuke them.")
        print()
        print(f"  {BOLD}Danger 2 — The Active Trap:{RESET}")
        print(f"    All {cancelled_profile['row_count']} 'cancelled' users logged in")
        print(f"    within the last {_MAX_CANCELLED_LOGIN_DAYS} days.")
        print(f"    Deleting them destroys actively-engaged users.")
        print()
        print(f"  {BOLD}Safe query Boyce would suggest instead:{RESET}")
        print()
        print(f"    -- Only delete users cancelled AND inactive for 90+ days")
        print(f"    DELETE FROM subscriptions")
        print(f"    WHERE  status = 'cancelled'")
        print(f"    AND    last_login < NOW() - INTERVAL '90 days'")
        print(f"    AND    status IS NOT NULL;   -- belt-and-suspenders guard")
        print()
        print(SEP)
        print(f"{GREEN}✅  All assertions passed.  The demo is ready to record.{RESET}")
        print(SEP)
        print()

    finally:
        await adapter.disconnect()
        if teardown_docker:
            print(f"\n{BOLD}[Teardown] Stopping Docker container{RESET}")
            _docker_down()
            _ok("Container stopped and volumes removed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _check_prerequisites()
    asyncio.run(run_trap_reveal())
