#!/usr/bin/env python3
"""
DataShark MCP Server — Official SDK Entrypoint

Phase 1: Headless MCP. This module is the canonical MCP server for DataShark,
using the official `mcp` Python SDK (FastMCP). It exposes tools that call
existing logic in datashark.core.parsers, datashark.core.graph, and
datashark.core.api.

Run: python -m datashark.mcp_app
Cursor/MCP config: use command + args pointing at this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Safety Kernel: ensure extensions/mcp/src or datashark-mcp/src is on path for Redshift/Postgres
_mcp_root = Path(__file__).resolve().parent.parent.parent
for _kernel_src in [_mcp_root / "extensions" / "mcp" / "src", _mcp_root / "datashark-mcp" / "src"]:
    if _kernel_src.exists() and str(_kernel_src) not in sys.path:
        sys.path.insert(0, str(_kernel_src))
        break
try:
    from safety_kernel.redshift_guardrails import lint_redshift_compat
except ImportError:
    lint_redshift_compat = None

from mcp.server.fastmcp import FastMCP

from datashark.core.api import process_request
from datashark.core.graph import SemanticGraph
from datashark.core.parsers import detect_source_type, parse_dbt_manifest, parse_lookml_file
from datashark.core.types import SemanticSnapshot
from datashark.core.validation import validate_snapshot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MCP Server ---
mcp = FastMCP("DataShark", json_response=True)

# --- Local context and shared graph (existing logic surface) ---
# mcp_app.py lives at src/datashark/mcp_app.py -> parent.parent.parent = repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_CONTEXT_DIR = _REPO_ROOT / "_local_context"
_global_graph = SemanticGraph()


def _save_snapshot(snapshot: SemanticSnapshot, snapshot_name: str) -> Path:
    """Persist snapshot to _local_context/. Uses same contract as legacy mcp_server."""
    LOCAL_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_CONTEXT_DIR / f"{snapshot_name}.json"
    with open(path, "w") as f:
        json.dump(snapshot.model_dump(mode="json"), f, indent=2)
    logger.info("Saved snapshot to %s", path)
    return path


def _load_snapshot(snapshot_name: str) -> SemanticSnapshot:
    """Load snapshot from _local_context/. Uses parsers/validation."""
    path = LOCAL_CONTEXT_DIR / f"{snapshot_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Snapshot '{snapshot_name}' not found in _local_context/")
    with open(path, "r") as f:
        data = json.load(f)
    errs = validate_snapshot(data)
    if errs:
        raise ValueError(str(errs))
    return SemanticSnapshot(**data)


def _mock_agent_ingestion(source_text: str, source_type: str) -> Dict[str, Any]:
    """Placeholder for text-based ingestion (DDL/LookML). Uses same shape as legacy mcp_server."""
    return {
        "source_system": source_type,
        "source_version": "1.0",
        "schema_version": "v0.1",
        "entities": {},
        "fields": {},
        "joins": [],
        "metadata": {"source_text_length": len(source_text), "source_type": source_type},
    }


def _mock_chat_interface(natural_language_query: str) -> Dict[str, Any]:
    """Placeholder: natural language -> StructuredFilter. Same shape as legacy mcp_server."""
    return {
        "concept_map": {"entities": [], "metrics": [], "dimensions": []},
        "filters": [],
        "temporal_filters": [],
        "join_path": [],
        "grain_context": {"aggregation_required": False},
        "policy_context": {"resolved_predicates": []},
        "dialect": "postgres",
    }


# --- Tools (port from mcp_server; call parsers / graph / api only) ---


@mcp.tool()
def ingest_source(
    source_path: str | None = None,
    source_text: str = "",
    source_type: str | None = None,
    snapshot_name: str = "default",
) -> str:
    """
    Ingest a dbt manifest, LookML file, or raw text into a SemanticSnapshot and the graph.
    Prefer source_path (file); use source_text when no file is available.
    """
    snapshot = None

    if source_path:
        path = Path(source_path)
        if not path.exists():
            return json.dumps({"error": {"code": -32602, "message": f"Source file not found: {source_path}"}})
        detected = detect_source_type(file_path=path)
        if detected == "dbt":
            try:
                snapshot = parse_dbt_manifest(path)
            except Exception as e:
                return json.dumps({"error": {"code": -32603, "message": f"Failed to parse dbt manifest: {str(e)}"}})
        elif detected == "lookml":
            try:
                snapshot = parse_lookml_file(path)
            except Exception as e:
                return json.dumps({"error": {"code": -32603, "message": f"Failed to parse LookML file: {str(e)}"}})
        else:
            source_text = source_text or path.read_text()
            source_type = source_type or detect_source_type(source_text=source_text)

    if snapshot is None:
        if not source_text:
            return json.dumps({"error": {"code": -32602, "message": "Either source_path or source_text is required"}})
        st = source_type or detect_source_type(source_text=source_text) or "ddl"
        data = _mock_agent_ingestion(source_text, st)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        data["snapshot_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        errs = validate_snapshot(data)
        if errs:
            return json.dumps({"error": {"code": -32602, "message": "Snapshot failed validation", "data": errs}})
        snapshot = SemanticSnapshot(**data)

    errs = validate_snapshot(snapshot.model_dump(mode="json"))
    if errs:
        return json.dumps({"error": {"code": -32602, "message": "Parsed snapshot failed validation", "data": errs}})

    out_path = _save_snapshot(snapshot, snapshot_name)
    _global_graph.add_snapshot(snapshot)
    return json.dumps({
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_name": snapshot_name,
        "snapshot_path": str(out_path),
        "message": "Snapshot ingested and saved to _local_context/",
        "entities_count": len(snapshot.entities),
        "fields_count": len(snapshot.fields),
        "joins_count": len(snapshot.joins),
    })


@mcp.tool()
def solve_path(
    source: str,
    target: str,
    snapshot_name: str | None = None,
) -> str:
    """
    Find the optimal semantic path between two entities and return join SQL.
    source and target are entity IDs (e.g. 'orders' or 'entity:orders').
    """
    if not source or not target:
        return json.dumps({"error": {"code": -32602, "message": "Both 'source' and 'target' entity IDs are required"}})
    src = source if source.startswith("entity:") else f"entity:{source}"
    tgt = target if target.startswith("entity:") else f"entity:{target}"

    if snapshot_name:
        try:
            snap = _load_snapshot(snapshot_name)
            if snap.snapshot_id not in _global_graph.snapshots:
                _global_graph.add_snapshot(snap)
        except FileNotFoundError:
            return json.dumps({"error": {"code": -32602, "message": f"Snapshot '{snapshot_name}' not found in _local_context/"}})
        except ValueError as e:
            return json.dumps({"error": {"code": -32602, "message": str(e)}})

    try:
        path = _global_graph.find_path(src, tgt)
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except Exception as e:
        import networkx as nx
        if isinstance(e, nx.NetworkXNoPath):
            return json.dumps({"error": {"code": -32603, "message": f"No path found between {src} and {tgt}"}})
        raise

    if not path and src == tgt:
        try:
            sql = _global_graph.generate_join_sql([], src)
        except Exception as e:
            return json.dumps({"error": {"code": -32603, "message": str(e)}})
        return json.dumps({"source_entity": src, "target_entity": tgt, "path_length": 0, "semantic_cost": 0.0, "joins": [], "sql": sql})

    if not path:
        return json.dumps({"error": {"code": -32603, "message": f"No path found between {src} and {tgt}"}})

    try:
        join_sql = _global_graph.generate_join_sql(path, src)
    except Exception as e:
        return json.dumps({"error": {"code": -32603, "message": str(e)}})
    total_cost = sum(
        _global_graph.graph[path[i].source_entity_id][path[i].target_entity_id][path[i].id].get("weight", 1.0)
        for i in range(len(path))
    )
    joins = [
        {
            "id": j.id,
            "source": j.source_entity_id,
            "target": j.target_entity_id,
            "type": j.join_type.value,
            "weight": _global_graph.graph[j.source_entity_id][j.target_entity_id][j.id].get("weight", 1.0),
        }
        for j in path
    ]
    return json.dumps({"source_entity": src, "target_entity": tgt, "path_length": len(path), "semantic_cost": total_cost, "joins": joins, "sql": join_sql})


@mcp.tool()
def ask_datashark(
    natural_language_query: str,
    snapshot_name: str = "default",
) -> str:
    """
    Generate SQL from a natural language query using a saved snapshot.
    """
    if not natural_language_query:
        return json.dumps({"error": {"code": -32602, "message": "natural_language_query is required"}})
    try:
        snapshot = _load_snapshot(snapshot_name)
    except FileNotFoundError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})
    except ValueError as e:
        return json.dumps({"error": {"code": -32602, "message": str(e)}})

    structured_filter = _mock_chat_interface(natural_language_query)
    try:
        sql = process_request(snapshot, structured_filter)
    except ValueError as e:
        return json.dumps({"error": {"code": -32603, "message": str(e)}})

    # Redshift/Postgres: run safety kernel when available (SQL still comes only from process_request)
    payload = {"sql": sql, "snapshot_id": snapshot.snapshot_id, "snapshot_name": snapshot_name}
    if lint_redshift_compat:
        compat_errors = lint_redshift_compat(sql)
        if compat_errors:
            payload["compat_risks"] = compat_errors
    return json.dumps(payload)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
