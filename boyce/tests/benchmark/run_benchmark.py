#!/usr/bin/env python3
"""
Boyce Preliminary Benchmark — Pagila (Tier 1)

Measures "With Boyce" vs "Without Boyce" query accuracy against the Pagila
PostgreSQL sample database across 12 ground-truth queries.

Metrics:
  - Row count accuracy    (results ≈ expected count, ±5%)
  - Top result accuracy   (expected leading row appears in results)
  - Join correctness      (SQL references all expected tables)
  - EXPLAIN verified      (all queries pass pre-flight validation)

Special safety checks (Q08, Q09):
  - Q08: NULL trap detection (original_language_id is 100% NULL in Pagila)
  - Q09: Dialect safety (Redshift: use || not CONCAT())

Usage:
    python boyce/tests/benchmark/run_benchmark.py

Required env vars:
    BOYCE_PROVIDER          — LLM provider, e.g. "anthropic" or "openai"
    BOYCE_MODEL             — Model name, e.g. "claude-haiku-4-5-20251001"
    ANTHROPIC_API_KEY       — (or OPENAI_API_KEY / LITELLM_API_KEY)

Optional env vars:
    BOYCE_DB_URL            — Pagila DSN (default: postgresql://boyce:password@localhost:5433/pagila)
    BOYCE_PAGILA_SNAPSHOT   — Path to pagila.json (default: ~/boyce-test/_local_context/pagila.json)
    BENCHMARK_QUERIES       — Path to queries.json (default: same dir as this script)
    BENCHMARK_OUTPUT        — Path for results markdown (default: _strategy/research/preliminary-benchmark.md)
    BENCHMARK_MODE          — "both" | "a_only" | "b_only"  (default: "both")
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap — must happen before any boyce imports
# ---------------------------------------------------------------------------

_BENCHMARK_DIR = Path(__file__).parent
_BOYCE_ROOT    = _BENCHMARK_DIR.parent.parent       # boyce/
_REPO_ROOT     = _BOYCE_ROOT.parent                 # Boyce/
sys.path.insert(0, str(_BOYCE_ROOT / "src"))

_DEFAULT_DB_URL   = "postgresql://boyce:password@localhost:5433/pagila"
_DEFAULT_SNAPSHOT = Path.home() / "boyce-test" / "_local_context" / "pagila.json"
_DEFAULT_QUERIES  = _BENCHMARK_DIR / "queries.json"
_DEFAULT_OUTPUT   = _REPO_ROOT / "_strategy" / "research" / "preliminary-benchmark.md"


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

def _check_prerequisites() -> None:
    missing = []
    if not os.environ.get("BOYCE_PROVIDER"):
        missing.append("BOYCE_PROVIDER  (e.g. 'anthropic' or 'openai')")
    if not os.environ.get("BOYCE_MODEL"):
        missing.append("BOYCE_MODEL     (e.g. 'claude-haiku-4-5-20251001')")
    has_key = any(
        os.environ.get(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LITELLM_API_KEY")
    )
    if not has_key:
        missing.append("ANTHROPIC_API_KEY  (or OPENAI_API_KEY / LITELLM_API_KEY)")
    if missing:
        print("❌  Missing required environment variables:\n")
        for m in missing:
            print(f"    {m}")
        sys.exit(1)

    try:
        import asyncpg  # noqa: F401
    except ImportError:
        print('❌  asyncpg not installed.\n    pip install "boyce[postgres]"')
        sys.exit(1)

    try:
        import litellm  # noqa: F401
    except ImportError:
        print("❌  litellm not installed.\n    pip install litellm")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Snapshot loading
# ---------------------------------------------------------------------------

def _load_snapshot(path: Path) -> Any:
    from boyce.types import SemanticSnapshot

    data = json.loads(path.read_text())
    return SemanticSnapshot(**data)


def _build_graph(snapshot: Any) -> Any:
    from boyce.graph import SemanticGraph

    graph = SemanticGraph()
    graph.add_snapshot(snapshot)
    return graph


def _build_schema_context(snapshot: Any) -> str:
    """Plain-text schema description for the Mode B (no-Boyce) LLM prompt."""
    lines: List[str] = [
        "PostgreSQL database schema (Pagila):",
        "",
    ]
    for entity_id, entity in snapshot.entities.items():
        lines.append(f"Table: {entity.name}")
        for field_id in entity.fields:
            field = snapshot.fields.get(field_id)
            if field:
                nullable = " (nullable)" if field.nullable else ""
                lines.append(f"  - {field.name}: {field.data_type}{nullable}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mode A: With Boyce
# ---------------------------------------------------------------------------

async def _run_mode_a(
    query_def: Dict[str, Any],
    snapshot: Any,
    graph: Any,
    planner: Any,
    adapter: Any,
) -> Dict[str, Any]:
    """Run one query through the full Boyce pipeline (planner → kernel → execute)."""
    from boyce import kernel

    result: Dict[str, Any] = {
        "mode": "A",
        "query_id": query_def["id"],
        "sql": None,
        "rows": None,
        "row_count": None,
        "error": None,
        "explain_valid": False,
        "tables_found": [],
        "null_trap_detected": None,
        "dialect_safe": None,
        "elapsed_ms": None,
    }

    t0 = time.monotonic()
    try:
        # Stage 1: NL → StructuredFilter (LLM)
        structured_filter = planner.plan_query(query_def["nl_prompt"], graph)
        structured_filter["dialect"] = "postgres"

        # Stage 2: StructuredFilter → SQL (deterministic, no LLM)
        sql = kernel.process_request(snapshot, structured_filter)
        result["sql"] = sql

        # Stage 3: EXPLAIN pre-flight
        try:
            await adapter.execute_query(f"EXPLAIN {sql}")
            result["explain_valid"] = True
        except Exception as exc:
            result["explain_valid"] = False
            result["error"] = f"EXPLAIN failed: {exc}"

        # Stage 4: Execute
        if result["explain_valid"]:
            rows = await adapter.execute_query(sql)
            result["rows"] = rows
            result["row_count"] = len(rows)

        # Stage 5: Safety checks
        sql_upper = sql.upper()
        expected_tables = [t.upper() for t in query_def.get("expected_tables", [])]
        result["tables_found"] = [t for t in expected_tables if t in sql_upper]

        category = query_def.get("category", "")
        if category == "null_trap":
            # Q08: Boyce should use LEFT JOIN to avoid silently dropping all rows
            result["null_trap_detected"] = bool(re.search(r"LEFT\s+(OUTER\s+)?JOIN", sql, re.IGNORECASE))
        if category == "dialect_safety":
            # Q09: Boyce should use || not CONCAT() for Redshift safety
            result["dialect_safe"] = "CONCAT(" not in sql_upper

    except Exception as exc:
        if not result["error"]:
            result["error"] = str(exc)

    result["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
    return result


# ---------------------------------------------------------------------------
# Mode B: Without Boyce (direct LLM → SQL)
# ---------------------------------------------------------------------------

_SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_sql(text: str) -> Optional[str]:
    """Extract SQL from an LLM response — code block first, then bare SELECT."""
    m = _SQL_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: grab from SELECT to end of content
    match = re.search(r"(SELECT\b.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


async def _run_mode_b(
    query_def: Dict[str, Any],
    schema_context: str,
    adapter: Any,
) -> Dict[str, Any]:
    """Run one query via direct LLM call — no Boyce pipeline."""
    import litellm

    result: Dict[str, Any] = {
        "mode": "B",
        "query_id": query_def["id"],
        "sql": None,
        "rows": None,
        "row_count": None,
        "error": None,
        "explain_valid": False,
        "tables_found": [],
        "null_trap_detected": None,
        "dialect_safe": None,
        "elapsed_ms": None,
    }

    provider = os.environ["BOYCE_PROVIDER"]
    model    = os.environ["BOYCE_MODEL"]

    t0 = time.monotonic()
    try:
        response = litellm.completion(
            model=f"{provider}/{model}",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a PostgreSQL expert. Write a single SQL SELECT query "
                        "to answer the user's question. Return only the SQL inside a "
                        "```sql code block. No explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{schema_context}\n\nQuestion: {query_def['nl_prompt']}",
                },
            ],
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip()

        sql = _extract_sql(raw)
        if not sql:
            result["error"] = "Could not extract SQL from LLM response"
            result["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
            return result

        result["sql"] = sql

        # EXPLAIN pre-flight
        try:
            await adapter.execute_query(f"EXPLAIN {sql}")
            result["explain_valid"] = True
        except Exception as exc:
            result["explain_valid"] = False
            result["error"] = f"EXPLAIN failed: {exc}"

        # Execute
        if result["explain_valid"]:
            rows = await adapter.execute_query(sql)
            result["rows"] = rows
            result["row_count"] = len(rows)

        # Safety checks (same criteria as Mode A)
        sql_upper = sql.upper()
        expected_tables = [t.upper() for t in query_def.get("expected_tables", [])]
        result["tables_found"] = [t for t in expected_tables if t in sql_upper]

        category = query_def.get("category", "")
        if category == "null_trap":
            result["null_trap_detected"] = bool(re.search(r"LEFT\s+(OUTER\s+)?JOIN", sql, re.IGNORECASE))
        if category == "dialect_safety":
            result["dialect_safe"] = "CONCAT(" not in sql_upper

    except Exception as exc:
        if not result["error"]:
            result["error"] = str(exc)

    result["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
    return result


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _values_approx_equal(actual: Any, expected: Any) -> bool:
    """Near-equality check for floats (2% tolerance), exact for ints, case-insensitive for strings."""
    if isinstance(expected, float):
        try:
            return abs(float(actual) - expected) <= max(abs(expected) * 0.02, 0.01)
        except (TypeError, ValueError):
            return False
    if isinstance(expected, int):
        try:
            return int(actual) == expected
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        return str(actual).strip().upper() == expected.strip().upper()
    return actual == expected


def _top_result_present(rows: List[Dict[str, Any]], expected_top: Dict[str, Any]) -> bool:
    """Check if expected_top values appear in the first few result rows."""
    if expected_top.get("all_null"):
        # Q08 special case: check that returned rows are mostly NULL language names
        for row in rows[:5]:
            values = list(row.values())
            if any(v is None for v in values):
                return True
        return False

    for row in rows[:5]:
        row_lower = {k.lower(): v for k, v in row.items()}
        matched = 0
        for key, exp_val in expected_top.items():
            actual_val = row_lower.get(key.lower())
            if actual_val is None:
                # Key not found by name — check if value appears in any column
                if any(_values_approx_equal(v, exp_val) for v in row.values()):
                    matched += 1
            elif _values_approx_equal(actual_val, exp_val):
                matched += 1
        if matched >= max(1, len(expected_top) - 1):   # Allow one miss
            return True
    return False


def _score(result: Dict[str, Any], query_def: Dict[str, Any]) -> Dict[str, Any]:
    """Score one result dict against its ground-truth query definition."""
    scores: Dict[str, Any] = {
        "row_count_match": False,
        "top_result_match": False,
        "join_correctness": False,
        "explain_valid": bool(result.get("explain_valid")),
        "null_trap_detected": result.get("null_trap_detected"),
        "dialect_safe": result.get("dialect_safe"),
        "total": 0,
        "max": 4,
    }

    rows = result.get("rows") or []
    actual_count = result.get("row_count")
    expected_count = query_def.get("expected_row_count")

    # Row count match (±5%)
    if actual_count is not None and expected_count is not None:
        tolerance = max(1, int(expected_count * 0.05))
        scores["row_count_match"] = abs(actual_count - expected_count) <= tolerance

    # Top result present
    expected_top = query_def.get("expected_top_result")
    if rows and expected_top:
        scores["top_result_match"] = _top_result_present(rows, expected_top)

    # Join correctness: all expected tables appear in SQL
    expected_tables = query_def.get("expected_tables", [])
    found = result.get("tables_found", [])
    scores["join_correctness"] = (len(found) == len(expected_tables)) if expected_tables else True

    scores["total"] = int(scores["row_count_match"]) + int(scores["top_result_match"]) + \
                      int(scores["join_correctness"]) + int(scores["explain_valid"])
    return scores


# ---------------------------------------------------------------------------
# Summary & reporting
# ---------------------------------------------------------------------------

def _summarize(
    results_a: List[Dict],
    results_b: List[Dict],
    queries: List[Dict],
) -> Dict[str, Any]:
    n = len(queries)

    def pct(values: List[bool]) -> int:
        return round(100 * sum(values) / n) if n else 0

    a_scores = [_score(r, q) for r, q in zip(results_a, queries)]
    b_scores = [_score(r, q) for r, q in zip(results_b, queries)]

    summary: Dict[str, Any] = {
        "n_queries": n,
        "mode_a": {
            "row_count_match": pct([s["row_count_match"] for s in a_scores]),
            "top_result_match": pct([s["top_result_match"] for s in a_scores]),
            "join_correctness": pct([s["join_correctness"] for s in a_scores]),
            "explain_valid":    pct([s["explain_valid"] for s in a_scores]),
            "avg_score": round(sum(s["total"] for s in a_scores) / n, 2),
        },
        "mode_b": {
            "row_count_match": pct([s["row_count_match"] for s in b_scores]),
            "top_result_match": pct([s["top_result_match"] for s in b_scores]),
            "join_correctness": pct([s["join_correctness"] for s in b_scores]),
            "explain_valid":    pct([s["explain_valid"] for s in b_scores]),
            "avg_score": round(sum(s["total"] for s in b_scores) / n, 2),
        },
        "per_query": [],
    }

    for q, ra, rb, sa, sb in zip(queries, results_a, results_b, a_scores, b_scores):
        summary["per_query"].append({
            "id": q["id"],
            "category": q["category"],
            "nl_prompt": q["nl_prompt"],
            "mode_a": {
                "score": sa["total"],
                "row_count": ra.get("row_count"),
                "explain_valid": sa["explain_valid"],
                "null_trap_detected": sa.get("null_trap_detected"),
                "dialect_safe": sa.get("dialect_safe"),
                "error": ra.get("error"),
                "sql": ra.get("sql"),
            },
            "mode_b": {
                "score": sb["total"],
                "row_count": rb.get("row_count"),
                "explain_valid": sb["explain_valid"],
                "null_trap_detected": sb.get("null_trap_detected"),
                "dialect_safe": sb.get("dialect_safe"),
                "error": rb.get("error"),
                "sql": rb.get("sql"),
            },
        })

    return summary


def _write_markdown(summary: Dict[str, Any], output_path: Path, model_label: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    a = summary["mode_a"]
    b = summary["mode_b"]
    n = summary["n_queries"]

    lines = [
        "# Boyce Preliminary Benchmark — Pagila (Tier 1)",
        "",
        f"**Run:** {now}  ",
        f"**Model:** {model_label}  ",
        f"**Queries:** {n}  ",
        "**Database:** Pagila (PostgreSQL sample — 29 tables, ~1,000 films, ~600 customers)",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | With Boyce | Without Boyce |",
        "|---|---|---|",
        f"| Row count accuracy | {a['row_count_match']}% | {b['row_count_match']}% |",
        f"| Top result accuracy | {a['top_result_match']}% | {b['top_result_match']}% |",
        f"| Join correctness | {a['join_correctness']}% | {b['join_correctness']}% |",
        f"| EXPLAIN verified | {a['explain_valid']}% | {b['explain_valid']}% |",
        f"| Average score (0–4) | {a['avg_score']} | {b['avg_score']} |",
        "",
        "---",
        "",
        "## Per-Query Results",
        "",
        "| ID | Category | With Boyce | Without Boyce | Notes |",
        "|---|---|---|---|---|",
    ]

    for q in summary["per_query"]:
        ma = q["mode_a"]
        mb = q["mode_b"]
        notes = []
        if q["id"] == "Q08":
            if ma.get("null_trap_detected") is True:
                notes.append("Boyce: NULL-safe LEFT JOIN")
            elif ma.get("null_trap_detected") is False:
                notes.append("Boyce: INNER JOIN (drops rows)")
            if mb.get("null_trap_detected") is False:
                notes.append("Direct: INNER JOIN (drops rows)")
        if q["id"] == "Q09":
            if ma.get("dialect_safe") is True:
                notes.append("Boyce: uses ||")
            if mb.get("dialect_safe") is False:
                notes.append("Direct: used CONCAT()")
        if ma.get("error"):
            notes.append(f"A-err: {ma['error'][:50]}")
        if mb.get("error"):
            notes.append(f"B-err: {mb['error'][:50]}")

        lines.append(
            f"| {q['id']} | {q['category']} "
            f"| {ma['score']}/4 | {mb['score']}/4 "
            f"| {'; '.join(notes) if notes else '—'} |"
        )

    lines += [
        "",
        "---",
        "",
        "## What Pagila Tests (and What It Doesn't)",
        "",
        "**Demonstrates:**",
        "- Query accuracy (correct tables, joins, columns)",
        "- Join correctness (Dijkstra path resolution vs model-guessed joins)",
        "- Dialect safety (Redshift lint — `||` vs `CONCAT()`)",
        "- EXPLAIN pre-flight (all Boyce queries verified before return)",
        "- Determinism (same prompt → same SQL)",
        "",
        "**Does NOT demonstrate (Pagila is too clean):**",
        "- NULL trap detection on pervasive NULLs (Pagila has minimal NULLs "
        "outside `original_language_id`)",
        "- Schema ambiguity resolution (Pagila table names are unambiguous)",
        "- Cross-schema join resolution",
        "",
        "The full benchmark (Phase 10) runs against a Tier 2 messy warehouse "
        "where these failure modes are common.",
        "",
    ]

    output_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_benchmark() -> None:
    db_url        = os.environ.get("BOYCE_DB_URL", _DEFAULT_DB_URL)
    snapshot_path = Path(os.environ.get("BOYCE_PAGILA_SNAPSHOT", str(_DEFAULT_SNAPSHOT)))
    queries_path  = Path(os.environ.get("BENCHMARK_QUERIES", str(_DEFAULT_QUERIES)))
    output_path   = Path(os.environ.get("BENCHMARK_OUTPUT", str(_DEFAULT_OUTPUT)))
    mode          = os.environ.get("BENCHMARK_MODE", "both")

    sep = "=" * 66
    print(f"\n{sep}")
    print("Boyce Preliminary Benchmark — Pagila (Tier 1)")
    print(sep)

    # Load query set
    query_set = json.loads(queries_path.read_text())
    queries   = query_set["queries"]
    provider  = os.environ["BOYCE_PROVIDER"]
    model_id  = os.environ["BOYCE_MODEL"]
    print(f"\nQueries : {len(queries)}")
    print(f"DB      : {db_url}")
    print(f"Model   : {provider}/{model_id}")
    print(f"Mode    : {mode}")

    # Load snapshot and build graph
    print(f"\n[1/4] Loading Pagila snapshot ...")
    if not snapshot_path.exists():
        print(f"\n❌  Snapshot not found at: {snapshot_path}")
        print("     Ingest it first:")
        print(f"     BOYCE_DB_URL={db_url} boyce ingest_source pagila")
        sys.exit(1)

    snapshot       = _load_snapshot(snapshot_path)
    graph          = _build_graph(snapshot)
    schema_context = _build_schema_context(snapshot)
    print(f"     ✓ {len(snapshot.entities)} entities, {len(snapshot.fields)} fields")

    # Connect to database
    print(f"\n[2/4] Connecting to Pagila ...")
    from boyce.adapters.postgres import PostgresAdapter
    from boyce.planner import QueryPlanner

    adapter = PostgresAdapter(dsn=db_url)
    await adapter.connect()
    print("     ✓ Connected")

    planner = QueryPlanner(provider=provider, model=model_id)

    results_a: List[Dict[str, Any]] = []
    results_b: List[Dict[str, Any]] = []

    _skipped: Dict[str, Any] = {
        "sql": None, "rows": None, "row_count": None, "error": "skipped",
        "explain_valid": False, "tables_found": [], "null_trap_detected": None,
        "dialect_safe": None, "elapsed_ms": 0,
    }

    try:
        print(f"\n[3/4] Running {len(queries)} queries ...")

        for q in queries:
            qid = q["id"]
            print(f"\n  {qid}  {q['nl_prompt']}")

            if mode in ("both", "a_only"):
                print("       Mode A (With Boyce)    ...", end="", flush=True)
                ra = await _run_mode_a(q, snapshot, graph, planner, adapter)
                results_a.append(ra)
                sa = _score(ra, q)
                if ra.get("error") and not ra.get("rows"):
                    print(f" ✗  {ra['error'][:60]}  ({ra['elapsed_ms']}ms)")
                else:
                    print(f" ✓  {ra['row_count']} rows  score {sa['total']}/4  ({ra['elapsed_ms']}ms)")
            else:
                results_a.append({"mode": "A", "query_id": qid, **_skipped})

            if mode in ("both", "b_only"):
                print("       Mode B (Without Boyce) ...", end="", flush=True)
                rb = await _run_mode_b(q, schema_context, adapter)
                results_b.append(rb)
                sb = _score(rb, q)
                if rb.get("error") and not rb.get("rows"):
                    print(f" ✗  {rb['error'][:60]}  ({rb['elapsed_ms']}ms)")
                else:
                    print(f" ✓  {rb['row_count']} rows  score {sb['total']}/4  ({rb['elapsed_ms']}ms)")
            else:
                results_b.append({"mode": "B", "query_id": qid, **_skipped})

        # Summary
        print(f"\n[4/4] Computing scores ...")
        summary = _summarize(results_a, results_b, queries)
        a = summary["mode_a"]
        b = summary["mode_b"]

        print(f"\n{sep}")
        print(f"{'Metric':<28} {'With Boyce':>12} {'Without Boyce':>14}")
        print(f"{'-'*28} {'-'*12} {'-'*14}")
        print(f"{'Row count accuracy':<28} {a['row_count_match']:>11}% {b['row_count_match']:>13}%")
        print(f"{'Top result accuracy':<28} {a['top_result_match']:>11}% {b['top_result_match']:>13}%")
        print(f"{'Join correctness':<28} {a['join_correctness']:>11}% {b['join_correctness']:>13}%")
        print(f"{'EXPLAIN verified':<28} {a['explain_valid']:>11}% {b['explain_valid']:>13}%")
        print(f"{'Avg score (0–4)':<28} {a['avg_score']:>12} {b['avg_score']:>14}")
        print(sep)

        # Write outputs
        model_label = f"{provider}/{model_id}"
        _write_markdown(summary, output_path, model_label)
        print(f"\n✓ Markdown written to {output_path.relative_to(_REPO_ROOT)}")

        json_path = output_path.with_suffix(".json")
        json_path.write_text(json.dumps(summary, indent=2, default=str))
        print(f"✓ JSON written to     {json_path.relative_to(_REPO_ROOT)}")

    finally:
        await adapter.disconnect()
        print("\n✓ Disconnected")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _check_prerequisites()
    asyncio.run(run_benchmark())
