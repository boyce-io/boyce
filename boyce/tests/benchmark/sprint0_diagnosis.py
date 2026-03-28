#!/usr/bin/env python3
"""
Sprint 0 Diagnostic — Haiku Regression Root Cause

Runs the 12 benchmark queries through a STRIPPED StructuredFilter prompt
(entities + fields + filters only — no metrics, dimensions, expressions,
order_by, or limit) to determine whether the Haiku regression is caused by:

  Branch A: Prompt complexity / validation issues (stripped scores ≈ full)
  Branch B: StructuredFilter cognitive tax (stripped scores > full, ≈ vanilla)

Loads existing Mode A (full Boyce) and Mode B (vanilla) results from the
preliminary-benchmark-haiku.json for comparison.

Usage:
    ANTHROPIC_API_KEY=... python boyce/tests/benchmark/sprint0_diagnosis.py

Optional env vars:
    BOYCE_DB_URL            — Pagila DSN (default: postgresql://boyce:password@localhost:5433/pagila)
    BOYCE_PAGILA_SNAPSHOT   — Path to pagila.json
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
# Path bootstrap
# ---------------------------------------------------------------------------

_BENCHMARK_DIR = Path(__file__).parent
_BOYCE_ROOT    = _BENCHMARK_DIR.parent.parent
_REPO_ROOT     = _BOYCE_ROOT.parent
sys.path.insert(0, str(_BOYCE_ROOT / "src"))

_DEFAULT_DB_URL   = "postgresql://boyce:password@localhost:5433/pagila"
_DEFAULT_SNAPSHOT = Path.home() / "boyce-test" / "_local_context" / "pagila.json"
_DEFAULT_QUERIES  = _BENCHMARK_DIR / "queries.json"
_HAIKU_RESULTS    = _REPO_ROOT / "_strategy" / "research" / "preliminary-benchmark-haiku.json"
_OUTPUT_DIR       = _REPO_ROOT / "_strategy" / "research"


# ---------------------------------------------------------------------------
# Stripped planner — entities + fields + filters only
# ---------------------------------------------------------------------------

_STRIPPED_SYSTEM_PROMPT = """You are a Data Engineer. Given a user query and a database schema, return a JSON object with:

{
  "entities": ["table1", "table2"],
  "fields": ["column1", "column2"],
  "filters": [{"field": "status", "operator": "=", "value": "active", "entity": "orders"}]
}

Rules:
- "entities": list every table needed to answer the query
- "fields": list every column needed (for SELECT, grouping, counting, etc.)
- "filters": list WHERE conditions. operator: "=", "!=", ">", ">=", "<", "<=", "IN", "NOT IN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL"
- Only use table and column names that exist in the provided schema
- Return ONLY valid JSON, no markdown, no explanation"""


def _build_schema_text(entity_context: List[Dict[str, Any]]) -> str:
    lines = ["Available tables and columns:\n"]
    for ent in entity_context:
        lines.append(f"Table: {ent['name']}")
        for field in ent["fields"]:
            lines.append(f"  - {field['name']} ({field['type']}, {field['data_type']})")
        lines.append("")
    return "\n".join(lines)


def _build_entity_context(graph: Any, query: str) -> List[Dict[str, Any]]:
    """Build entity context the same way the real planner does."""
    all_entity_ids = graph.list_entities()
    entity_names = [eid.replace("entity:", "") for eid in all_entity_ids]

    query_words = set(re.findall(r"\b\w+\b", query.lower()))
    entity_scores: List[tuple] = []
    for name in entity_names:
        score = sum(1 for w in query_words if w in name.lower())
        if score > 0 or len(entity_names) <= 50:
            entity_scores.append((score, name))
    entity_scores.sort(reverse=True, key=lambda x: x[0])
    top_entities = [name for _, name in entity_scores[:50]]

    context: List[Dict[str, Any]] = []
    for name in top_entities:
        eid = f"entity:{name}"
        if eid not in graph.graph:
            continue
        node_data = graph.graph.nodes[eid]
        entity = node_data.get("entity")
        if not entity:
            continue
        fields = []
        for fid in entity.fields:
            if fid in graph.field_cache:
                f = graph.field_cache[fid]
                fields.append({"name": f.name, "type": f.field_type.value, "data_type": f.data_type})
        context.append({"name": name, "fields": fields[:20]})
    return context


def _call_stripped_planner(
    query: str,
    schema_text: str,
    provider: str,
    model: str,
    api_key: str,
) -> Dict[str, Any]:
    """Call LLM with the stripped prompt. Returns raw JSON response."""
    import litellm

    os.environ["LITELLM_API_KEY"] = api_key
    if provider == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = api_key

    response = litellm.completion(
        model=f"{provider}/{model}",
        messages=[
            {"role": "system", "content": _STRIPPED_SYSTEM_PROMPT},
            {"role": "user", "content": f"User query: {query}\n\n{schema_text}"},
        ],
        temperature=0.1,
    )
    text = response.choices[0].message.content.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def _validate_and_assemble(
    raw: Dict[str, Any],
    graph: Any,
) -> Dict[str, Any]:
    """Validate raw LLM output against graph and assemble a minimal StructuredFilter.

    Same validation logic as the real planner (entity grounding, field keyword scoring,
    entity reachability) but assembles with empty metrics/dimensions.
    """
    import networkx as nx

    # --- Entity validation ---
    validated_entities: List[Dict[str, Any]] = []
    for name in raw.get("entities", []):
        eid = f"entity:{name}"
        if eid in graph.graph:
            validated_entities.append({"entity_id": eid, "entity_name": name})

    # Reachability check (BUG-C logic)
    if len(validated_entities) > 1:
        undirected = graph.graph.to_undirected()
        first = validated_entities[0]
        rest = sorted(validated_entities[1:], key=lambda e: e["entity_id"])
        reachable = [first]
        for ent in rest:
            tid = ent["entity_id"]
            can_reach = any(
                tid in undirected
                and r["entity_id"] in undirected
                and nx.has_path(undirected, r["entity_id"], tid)
                for r in reachable
            )
            if can_reach:
                reachable.append(ent)
        validated_entities = reachable

    # --- Field validation with keyword scoring ---
    validated_fields: List[Dict[str, Any]] = []
    for field_name in raw.get("fields", []):
        best_match: Optional[Dict[str, Any]] = None
        best_score = -1
        for ent in validated_entities:
            entity = graph.graph.nodes[ent["entity_id"]].get("entity")
            if not entity:
                continue
            for fid in entity.fields:
                if fid not in graph.field_cache:
                    continue
                cname = graph.field_cache[fid].name
                if cname == field_name:
                    best_match = {"field_id": fid, "field_name": field_name, "entity_id": ent["entity_id"]}
                    best_score = 999
                    break
                # Keyword scoring
                qw = set(w for w in re.split(r"[_\s]+", field_name.lower()) if w)
                cw = set(w for w in re.split(r"[_\s]+", cname.lower()) if w)
                score = len(qw & cw)
                if score > best_score:
                    best_score = score
                    best_match = {"field_id": fid, "field_name": field_name, "entity_id": ent["entity_id"]}
            if best_score == 999:
                break
        if best_match and best_score > 0:
            validated_fields.append(best_match)

    # --- Filter validation ---
    validated_filters: List[Dict[str, Any]] = []
    for filt in raw.get("filters", []):
        field_name = filt.get("field", "")
        entity_name = filt.get("entity", "")
        entity_id = f"entity:{entity_name}" if entity_name else None

        search_entities = (
            [e for e in validated_entities if e["entity_id"] == entity_id]
            if entity_id and entity_id in graph.graph
            else []
        ) or validated_entities

        flt_best: Optional[Dict[str, Any]] = None
        flt_score = -1
        for ent in search_entities:
            entity = graph.graph.nodes[ent["entity_id"]].get("entity")
            if not entity:
                continue
            for fid in entity.fields:
                if fid not in graph.field_cache:
                    continue
                cname = graph.field_cache[fid].name
                if cname == field_name:
                    flt_best = {"field_id": fid, "entity_id": ent["entity_id"]}
                    flt_score = 999
                    break
                qw = set(w for w in re.split(r"[_\s]+", field_name.lower()) if w)
                cw = set(w for w in re.split(r"[_\s]+", cname.lower()) if w)
                score = len(qw & cw)
                if score > flt_score:
                    flt_score = score
                    flt_best = {"field_id": fid, "entity_id": ent["entity_id"]}
            if flt_score == 999:
                break

        if flt_best and flt_score > 0:
            validated_filters.append({
                "field_id": flt_best["field_id"],
                "operator": filt.get("operator", "="),
                "value": filt.get("value"),
                "entity_id": flt_best["entity_id"],
            })

    # Assemble minimal StructuredFilter — NO metrics, dimensions, order_by, limit
    return {
        "concept_map": {
            "entities": validated_entities,
            "fields": validated_fields,
            "metrics": [],
            "dimensions": [],
            "filters": validated_filters,
        },
        "join_path": [e["entity_id"] for e in validated_entities],
        "grain_context": {
            "aggregation_required": False,
            "grouping_fields": [],
        },
        "policy_context": {"resolved_predicates": []},
        "dialect": "postgres",
    }


# ---------------------------------------------------------------------------
# Execution and scoring (reuses run_benchmark.py logic)
# ---------------------------------------------------------------------------

async def _run_stripped(
    query_def: Dict[str, Any],
    snapshot: Any,
    graph: Any,
    adapter: Any,
    provider: str,
    model: str,
    api_key: str,
) -> Dict[str, Any]:
    """Run one query through the stripped pipeline."""
    from boyce import kernel

    result: Dict[str, Any] = {
        "mode": "C",
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
        "raw_llm_output": None,
        "entities_selected": [],
        "fields_selected": [],
    }

    entity_context = _build_entity_context(graph, query_def["nl_prompt"])
    schema_text = _build_schema_text(entity_context)

    t0 = time.monotonic()
    try:
        # Stage 1: Stripped LLM call
        raw = _call_stripped_planner(
            query_def["nl_prompt"], schema_text, provider, model, api_key
        )
        result["raw_llm_output"] = raw
        result["entities_selected"] = raw.get("entities", [])
        result["fields_selected"] = raw.get("fields", [])

        # Stage 2: Validate and assemble minimal StructuredFilter
        sf = _validate_and_assemble(raw, graph)

        # Stage 3: Kernel → SQL
        sql = kernel.process_request(snapshot, sf)
        result["sql"] = sql

        # Stage 4: EXPLAIN
        try:
            await adapter.execute_query(f"EXPLAIN {sql}")
            result["explain_valid"] = True
        except Exception as exc:
            result["explain_valid"] = False
            result["error"] = f"EXPLAIN failed: {exc}"

        # Stage 5: Execute
        if result["explain_valid"]:
            rows = await adapter.execute_query(sql)
            result["rows"] = rows
            result["row_count"] = len(rows)

        # Stage 6: Safety checks
        sql_upper = sql.upper()
        expected_tables = [t.upper() for t in query_def.get("expected_tables", [])]
        result["tables_found"] = [t for t in expected_tables if t in sql_upper]

        category = query_def.get("category", "")
        if category == "null_trap":
            result["null_trap_detected"] = bool(
                re.search(r"LEFT\s+(OUTER\s+)?JOIN", sql, re.IGNORECASE)
            )
        if category == "dialect_safety":
            result["dialect_safe"] = "CONCAT(" not in sql_upper

    except Exception as exc:
        if not result["error"]:
            result["error"] = str(exc)

    result["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
    return result


def _score(result: Dict[str, Any], query_def: Dict[str, Any]) -> Dict[str, Any]:
    """Score one result — identical logic to run_benchmark.py."""
    scores: Dict[str, Any] = {
        "row_count_match": False,
        "top_result_match": False,
        "join_correctness": False,
        "explain_valid": bool(result.get("explain_valid")),
        "total": 0,
        "max": 4,
    }

    actual_count = result.get("row_count")
    expected_count = query_def.get("expected_row_count")
    if actual_count is not None and expected_count is not None:
        tolerance = max(1, int(expected_count * 0.05))
        scores["row_count_match"] = abs(actual_count - expected_count) <= tolerance

    rows = result.get("rows") or []
    expected_top = query_def.get("expected_top_result")
    if rows and expected_top:
        if expected_top.get("all_null"):
            for row in rows[:5]:
                if any(v is None for v in row.values()):
                    scores["top_result_match"] = True
                    break
        else:
            for row in rows[:5]:
                row_lower = {k.lower(): v for k, v in row.items()}
                matched = 0
                for key, exp_val in expected_top.items():
                    actual = row_lower.get(key.lower())
                    if actual is None:
                        if any(_approx(v, exp_val) for v in row.values()):
                            matched += 1
                    elif _approx(actual, exp_val):
                        matched += 1
                if matched >= max(1, len(expected_top) - 1):
                    scores["top_result_match"] = True
                    break

    expected_tables = query_def.get("expected_tables", [])
    found = result.get("tables_found", [])
    scores["join_correctness"] = (len(found) == len(expected_tables)) if expected_tables else True

    scores["total"] = (
        int(scores["row_count_match"])
        + int(scores["top_result_match"])
        + int(scores["join_correctness"])
        + int(scores["explain_valid"])
    )
    return scores


def _approx(actual: Any, expected: Any) -> bool:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    db_url = os.environ.get("BOYCE_DB_URL", _DEFAULT_DB_URL)
    snapshot_path = Path(os.environ.get("BOYCE_PAGILA_SNAPSHOT", str(_DEFAULT_SNAPSHOT)))
    queries_path = _DEFAULT_QUERIES

    provider = "anthropic"
    model = "claude-haiku-4-5-20251001"

    api_key = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY_RESEARCH")
    )
    if not api_key:
        print("❌  Set ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_RESEARCH")
        sys.exit(1)

    sep = "=" * 70
    print(f"\n{sep}")
    print("Sprint 0 Diagnostic — Haiku Regression Root Cause")
    print(f"Stripped StructuredFilter (entities + fields + filters only)")
    print(sep)

    # Load queries
    queries = json.loads(queries_path.read_text())["queries"]
    print(f"\nQueries : {len(queries)}")
    print(f"DB      : {db_url}")
    print(f"Model   : {provider}/{model}")

    # Load snapshot + graph
    print("\n[1/5] Loading Pagila snapshot ...")
    from boyce.types import SemanticSnapshot
    from boyce.graph import SemanticGraph

    snapshot = SemanticSnapshot(**json.loads(snapshot_path.read_text()))
    graph = SemanticGraph()
    graph.add_snapshot(snapshot)
    print(f"     ✓ {len(snapshot.entities)} entities, {len(snapshot.fields)} fields")

    # Connect
    print("\n[2/5] Connecting to Pagila ...")
    from boyce.adapters.postgres import PostgresAdapter
    adapter = PostgresAdapter(dsn=db_url)
    await adapter.connect()
    print("     ✓ Connected")

    # Load existing Mode A/B results
    print("\n[3/5] Loading existing Haiku benchmark results ...")
    if not _HAIKU_RESULTS.exists():
        print(f"❌  Not found: {_HAIKU_RESULTS}")
        print("     Run the full benchmark first with Haiku.")
        sys.exit(1)
    existing = json.loads(_HAIKU_RESULTS.read_text())
    print(f"     ✓ Loaded {len(existing['per_query'])} query results")

    # Run stripped benchmark
    print(f"\n[4/5] Running stripped StructuredFilter benchmark ...")
    results_c: List[Dict[str, Any]] = []

    try:
        for q in queries:
            qid = q["id"]
            print(f"\n  {qid}  {q['nl_prompt']}")
            print("       Mode C (Stripped)      ...", end="", flush=True)

            rc = await _run_stripped(q, snapshot, graph, adapter, provider, model, api_key)
            results_c.append(rc)
            sc = _score(rc, q)

            if rc.get("error") and not rc.get("rows"):
                print(f" ✗  {rc['error'][:60]}  ({rc['elapsed_ms']}ms)")
            else:
                print(f" ✓  {rc['row_count']} rows  score {sc['total']}/4  ({rc['elapsed_ms']}ms)")

            # Show entity/field selection
            print(f"       Entities: {rc['entities_selected']}")
            print(f"       Fields:   {rc['fields_selected'][:8]}{'...' if len(rc['fields_selected']) > 8 else ''}")

        # Scoring
        print(f"\n[5/5] Computing comparison ...")
        c_scores = [_score(r, q) for r, q in zip(results_c, queries)]

        c_avg = round(sum(s["total"] for s in c_scores) / len(queries), 2)
        c_row = round(100 * sum(s["row_count_match"] for s in c_scores) / len(queries))
        c_top = round(100 * sum(s["top_result_match"] for s in c_scores) / len(queries))
        c_join = round(100 * sum(s["join_correctness"] for s in c_scores) / len(queries))
        c_expl = round(100 * sum(s["explain_valid"] for s in c_scores) / len(queries))

        a = existing["mode_a"]
        b = existing["mode_b"]

        print(f"\n{sep}")
        print(f"{'Metric':<28} {'Full (A)':>10} {'Stripped (C)':>14} {'Vanilla (B)':>14}")
        print(f"{'-'*28} {'-'*10} {'-'*14} {'-'*14}")
        print(f"{'Row count accuracy':<28} {a['row_count_match']:>9}% {c_row:>13}% {b['row_count_match']:>13}%")
        print(f"{'Top result accuracy':<28} {a['top_result_match']:>9}% {c_top:>13}% {b['top_result_match']:>13}%")
        print(f"{'Join correctness':<28} {a['join_correctness']:>9}% {c_join:>13}% {b['join_correctness']:>13}%")
        print(f"{'EXPLAIN verified':<28} {a['explain_valid']:>9}% {c_expl:>13}% {b['explain_valid']:>13}%")
        print(f"{'Avg score (0–4)':<28} {a['avg_score']:>10} {c_avg:>14} {b['avg_score']:>14}")
        print(sep)

        # Write JSON output
        output = {
            "run": datetime.now(timezone.utc).isoformat(),
            "model": f"{provider}/{model}",
            "prompt": "stripped (entities + fields + filters only)",
            "summary": {
                "mode_c": {
                    "row_count_match": c_row,
                    "top_result_match": c_top,
                    "join_correctness": c_join,
                    "explain_valid": c_expl,
                    "avg_score": c_avg,
                },
                "mode_a_existing": a,
                "mode_b_existing": b,
            },
            "per_query": [],
        }
        for q, rc, sc, existing_q in zip(queries, results_c, c_scores, existing["per_query"]):
            output["per_query"].append({
                "id": q["id"],
                "category": q["category"],
                "nl_prompt": q["nl_prompt"],
                "mode_c": {
                    "score": sc["total"],
                    "row_count": rc.get("row_count"),
                    "explain_valid": sc["explain_valid"],
                    "join_correctness": sc["join_correctness"],
                    "row_count_match": sc["row_count_match"],
                    "top_result_match": sc["top_result_match"],
                    "error": rc.get("error"),
                    "sql": rc.get("sql"),
                    "entities_selected": rc.get("entities_selected"),
                    "fields_selected": rc.get("fields_selected"),
                    "raw_llm_output": rc.get("raw_llm_output"),
                },
                "mode_a_existing": existing_q.get("mode_a", {}),
                "mode_b_existing": existing_q.get("mode_b", {}),
            })

        json_path = _OUTPUT_DIR / "sprint0-diagnosis.json"
        json_path.write_text(json.dumps(output, indent=2, default=str))
        print(f"\n✓ JSON written to {json_path.relative_to(_REPO_ROOT)}")

    finally:
        await adapter.disconnect()
        print("✓ Disconnected")


if __name__ == "__main__":
    try:
        import asyncpg  # noqa: F401
        import litellm  # noqa: F401
    except ImportError as e:
        print(f"❌  Missing dependency: {e}")
        sys.exit(1)

    asyncio.run(main())
