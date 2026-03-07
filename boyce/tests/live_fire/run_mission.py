#!/usr/bin/env python3
"""
run_mission.py — Operation Live Fire
End-to-end integration test for the Boyce protocol.

Pipeline under test:
  Postgres DB (Docker) → SemanticSnapshot (ingested) →
  QueryPlanner (LLM) → kernel.process_request (deterministic SQL) →
  EXPLAIN pre-flight (PostgresAdapter) → validation.status == "verified"

Usage (from the boyce/ directory):
    python tests/live_fire/run_mission.py

Required env vars:
    BOYCE_PROVIDER   — LLM provider, e.g. "openai" or "anthropic"
    BOYCE_MODEL      — Model name, e.g. "gpt-4o-mini" or "claude-haiku-4-5-20251001"
    OPENAI_API_KEY       — (or ANTHROPIC_API_KEY / LITELLM_API_KEY)

Optional env vars:
    SKIP_DOCKER=1        — Skip docker-compose lifecycle; assumes DB is already running.
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
# Path bootstrap — must happen before any boyce imports
# ---------------------------------------------------------------------------

_MISSION_DIR = Path(__file__).parent
_PROTO_ROOT = _MISSION_DIR.parent.parent           # boyce/
sys.path.insert(0, str(_PROTO_ROOT / "src"))

_COMPOSE_FILE = _MISSION_DIR / "docker-compose.yml"
_SEED_SQL = _MISSION_DIR / "seed.sql"
_MOCK_SNAPSHOT = _MISSION_DIR / "mock_snapshot.json"
_LOCAL_CONTEXT = _PROTO_ROOT / "_local_context"    # mirrors server.py's _LOCAL_CONTEXT

_DB_URL = "postgresql://boyce:password@localhost:5432/live_fire_db"
_SNAPSHOT_NAME = "live_fire"
_NL_QUERY = "List all active agents with their kill counts"


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def _check_prerequisites() -> None:
    """Fail fast with clear error messages before we touch Docker or the LLM."""
    missing = []

    # LLM credentials
    if not os.environ.get("BOYCE_PROVIDER"):
        missing.append("BOYCE_PROVIDER  (e.g. 'openai' or 'anthropic')")
    if not os.environ.get("BOYCE_MODEL"):
        missing.append("BOYCE_MODEL     (e.g. 'gpt-4o-mini')")

    has_key = any(
        os.environ.get(k)
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LITELLM_API_KEY")
    )
    if not has_key:
        missing.append("OPENAI_API_KEY  (or ANTHROPIC_API_KEY / LITELLM_API_KEY)")

    if missing:
        print("❌  Missing required environment variables:\n")
        for m in missing:
            print(f"    {m}")
        print()
        sys.exit(1)

    # asyncpg
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        print(
            "❌  asyncpg is not installed.\n"
            '    pip install "boyce[postgres]"'
        )
        sys.exit(1)

    # litellm
    try:
        import litellm  # noqa: F401
    except ImportError:
        print("❌  litellm is not installed.\n    pip install litellm")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _docker_cmd() -> list:
    """Prefer 'docker compose' plugin; fall back to legacy 'docker-compose'."""
    probe = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
    )
    return ["docker", "compose"] if probe.returncode == 0 else ["docker-compose"]


def _docker_up() -> None:
    cmd = _docker_cmd() + ["-f", str(_COMPOSE_FILE), "up", "-d", "--wait"]
    subprocess.run(cmd, check=True)


def _docker_down() -> None:
    cmd = _docker_cmd() + [
        "-f", str(_COMPOSE_FILE), "down",
        "--volumes", "--remove-orphans",
    ]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def _wait_for_db(dsn: str, max_seconds: int = 90) -> None:
    """Poll until asyncpg can connect, or raise after max_seconds."""
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
        f"Database did not become ready within {max_seconds}s.\n"
        f"Last error: {last_exc}"
    )


async def _seed_db(dsn: str) -> None:
    """Execute seed.sql against the live database."""
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

def _load_snapshot() -> Dict[str, Any]:
    """
    Read mock_snapshot.json, compute the canonical SHA-256 snapshot_id,
    and return a dict that will pass validate_snapshot() cleanly.

    The JSON file stores "COMPUTED" as the snapshot_id placeholder.
    We materialise the real hash here using the same algorithm as
    boyce.validation._compute_snapshot_hash.
    """
    from boyce.types import SemanticSnapshot
    from boyce.validation import _compute_snapshot_hash

    data = json.loads(_MOCK_SNAPSHOT.read_text())
    data.pop("_comment", None)          # strip doc comment — not a Pydantic field

    # Two-pass: create object with placeholder → compute hash → stamp real id
    data["snapshot_id"] = "placeholder"
    snap_tmp = SemanticSnapshot(**data)
    data["snapshot_id"] = _compute_snapshot_hash(snap_tmp)

    return data


# ---------------------------------------------------------------------------
# EXPLAIN cost parser (inlined to avoid importing server.py / FastMCP)
# ---------------------------------------------------------------------------

import re as _re

_EXPLAIN_COST_RE = _re.compile(r"\(cost=[\d.]+\.\.([\d.]+)")


def _parse_explain_cost(rows: list) -> Optional[float]:
    if not rows:
        return None
    plan_text = rows[0].get("QUERY PLAN", "")
    m = _EXPLAIN_COST_RE.search(plan_text)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------

async def run_mission() -> None:
    skip_docker = os.environ.get("SKIP_DOCKER") == "1"

    _sep = "=" * 60
    print(f"\n{_sep}")
    print("OPERATION LIVE FIRE — Boyce End-to-End Integration Test")
    print(_sep)

    # ------------------------------------------------------------------
    # Step 1: Docker
    # ------------------------------------------------------------------
    if not skip_docker:
        print("\n[1/6] Launching Postgres 15 container ...")
        _docker_up()
        print("      ✓ Container up")
    else:
        print("\n[1/6] SKIP_DOCKER=1 — using pre-existing database")

    teardown_docker = not skip_docker

    try:
        # ------------------------------------------------------------------
        # Step 2: Wait for DB
        # ------------------------------------------------------------------
        print(f"\n[2/6] Waiting for database at {_DB_URL} ...")
        await _wait_for_db(_DB_URL)
        print("      ✓ Database ready")

        # ------------------------------------------------------------------
        # Step 3: Seed
        # ------------------------------------------------------------------
        print("\n[3/6] Seeding `agents` table ...")
        await _seed_db(_DB_URL)
        print("      ✓ Seeded: 3 rows (007 / Vesper / Nomi)")

        # ------------------------------------------------------------------
        # Step 4: Ingest snapshot into SemanticGraph
        # ------------------------------------------------------------------
        print("\n[4/6] Ingesting SemanticSnapshot ...")

        from boyce.graph import SemanticGraph
        from boyce.store import SnapshotStore
        from boyce.types import SemanticSnapshot
        from boyce.validation import validate_snapshot

        snapshot_data = _load_snapshot()
        errors = validate_snapshot(snapshot_data)
        if errors:
            raise RuntimeError(
                f"SemanticSnapshot validation failed:\n" + "\n".join(errors)
            )

        snapshot = SemanticSnapshot(**snapshot_data)
        store = SnapshotStore(_LOCAL_CONTEXT)
        store.save(snapshot, _SNAPSHOT_NAME)

        graph = SemanticGraph()
        graph.add_snapshot(snapshot)

        entities = graph.list_entities()
        print(f"      ✓ Snapshot valid  (id={snapshot.snapshot_id[:16]}...)")
        print(f"        Entities in graph : {entities}")
        print(f"        Fields in cache   : {len(graph.field_cache)}")

        # ------------------------------------------------------------------
        # Step 5: Plan → SQL (Brain + Kernel)
        # ------------------------------------------------------------------
        print(f"\n[5/6] Running pipeline for: {_NL_QUERY!r}")
        print("      Stage 1 — QueryPlanner (LLM) ...")

        from boyce.planner import QueryPlanner
        from boyce import kernel

        planner = QueryPlanner(
            provider=os.environ["BOYCE_PROVIDER"],
            model=os.environ["BOYCE_MODEL"],
        )
        structured_filter = planner.plan_query(_NL_QUERY, graph)
        structured_filter["dialect"] = "postgres"

        entities_resolved = [
            e.get("entity_name", e.get("entity_id", ""))
            for e in structured_filter.get("concept_map", {}).get("entities", [])
        ]
        print(f"      ✓ Planner resolved entities: {entities_resolved}")
        print(f"        structured_filter keys: {list(structured_filter.keys())}")

        print("      Stage 2 — kernel.process_request (deterministic SQL) ...")
        sql = kernel.process_request(snapshot, structured_filter)
        print(f"      ✓ SQL generated ({len(sql)} chars)")

        # ------------------------------------------------------------------
        # Stage 3: EXPLAIN pre-flight (Eyes)
        # ------------------------------------------------------------------
        print("      Stage 3 — EXPLAIN pre-flight (PostgresAdapter) ...")

        from boyce.adapters.postgres import PostgresAdapter

        adapter = PostgresAdapter(dsn=_DB_URL)
        await adapter.connect()
        try:
            explain_rows = await adapter.execute_query(f"EXPLAIN {sql}")
            cost = _parse_explain_cost(explain_rows)
            validation: Dict[str, Any] = {
                "status": "verified",
                "error": None,
                "cost_estimate": cost,
            }
        except Exception as exc:
            validation = {
                "status": "invalid",
                "error": str(exc),
                "cost_estimate": None,
            }
        finally:
            await adapter.disconnect()

        # ------------------------------------------------------------------
        # Step 6: Verify
        # ------------------------------------------------------------------
        print("\n[6/6] Verifying results ...")

        result = {
            "sql": sql,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_name": _SNAPSHOT_NAME,
            "entities_resolved": entities_resolved,
            "validation": validation,
            "structured_filter": structured_filter,
        }

        print("\n--- Full pipeline result ---")
        print(json.dumps(result, indent=2, default=str))
        print("--- End result ---\n")

        # Assertion 1: no error from planning or SQL building
        assert "error" not in result, f"Pipeline returned an error: {result.get('error')}"

        # Assertion 2: EXPLAIN passed
        status = validation["status"]
        if status == "unchecked":
            raise AssertionError(
                "validation.status is 'unchecked' — "
                "PostgresAdapter was not reached. Check BOYCE_DB_URL handling."
            )
        if status == "invalid":
            raise AssertionError(
                f"validation.status is 'invalid' — EXPLAIN failed.\n"
                f"  error : {validation['error']}\n"
                f"  sql   : {sql}"
            )
        assert status == "verified", f"Unexpected validation.status: {status!r}"
        print(f"      ✓ EXPLAIN verified  (cost_estimate={validation['cost_estimate']})")

        # Assertion 3: SQL references the agents table
        assert "agents" in sql.lower(), (
            f"Expected 'agents' in generated SQL, got:\n{sql}"
        )
        print("      ✓ SQL references 'agents' table")

        print(f"\n      Generated SQL:\n")
        for line in sql.splitlines():
            print(f"        {line}")

        print(f"\n{_sep}")
        print("✅  MISSION COMPLETE — All checks passed.")
        print(_sep)

    finally:
        # Always clean up, even on assertion failure
        if teardown_docker:
            print("\n[Teardown] Stopping Docker container ...")
            _docker_down()
            print("           ✓ Container stopped and volumes removed")

        # Remove snapshot file created during this test run
        live_fire_json = _LOCAL_CONTEXT / f"{_SNAPSHOT_NAME}.json"
        if live_fire_json.exists():
            live_fire_json.unlink()
            print(f"           ✓ Removed {live_fire_json.relative_to(_PROTO_ROOT)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _check_prerequisites()
    asyncio.run(run_mission())
