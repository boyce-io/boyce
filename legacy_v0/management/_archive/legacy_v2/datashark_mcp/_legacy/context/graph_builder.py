from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple
from datashark_mcp.context.schema import (
    Node, Edge, NodeType, EdgeType, Provenance,
    stable_node_id, stable_edge_id, compute_node_hash, compute_edge_hash,
)
try:
    from datashark_mcp.context.store.json_store import JSONStore
except ImportError:
    # Fallback: JSONStore may not exist in all contexts
    JSONStore = None

logger = logging.getLogger(__name__)


class GraphBuilder:
    def __init__(self) -> None:
        pass

    @staticmethod
    def _ensure_provenance(p: Provenance) -> Provenance:
        """
        Ensure provenance has all required fields, including extracted_at.

        If extracted_at is missing, fill it with the current UTC timestamp.
        """
        extracted_at = p.extracted_at or datetime.now(timezone.utc).isoformat()
        return Provenance(
            system=p.system,
            source_path=p.source_path,
            source_line=p.source_line,
            source_commit=p.source_commit,
            extractor_version=p.extractor_version,
            extracted_at=extracted_at,
        )

    def build(self, raw_artifacts: Iterable[Dict[str, Any]]) -> Tuple[List[Node], List[Edge]]:
        nodes: List[Node] = []
        edges: List[Edge] = []
        for a in raw_artifacts:
            system = a["system"]
            atype = a["type"]
            name = a["name"]
            prov = self._ensure_provenance(
                Provenance(
                    system=system,
                    source_path=a.get("source_path"),
                    source_line=a.get("source_line"),
                    source_commit=a.get("source_commit"),
                    extractor_version=a.get("extractor_version"),
                    extracted_at=a.get("extracted_at"),
                )
            )
            if atype == "entity":
                node_id = stable_node_id(system, NodeType.ENTITY, name)
                n = Node(id=node_id, type=NodeType.ENTITY, system=system, name=name,
                         attributes=a.get("attributes", {}), provenance=prov)
                n.hash = compute_node_hash(n)
                nodes.append(n)
            elif atype == "metric":
                node_id = stable_node_id(system, NodeType.METRIC, name)
                n = Node(id=node_id, type=NodeType.METRIC, system=system, name=name,
                         attributes=a.get("attributes", {}), provenance=prov)
                n.grain = a.get("attributes", {}).get("grain")
                n.hash = compute_node_hash(n)
                nodes.append(n)
                # dependencies
                for dep in a.get("dependencies", []):
                    src = stable_node_id(system, NodeType.METRIC, name)
                    dst = stable_node_id(system, NodeType.FIELD, dep) if ":" in dep else stable_node_id(system, NodeType.ENTITY, dep)
                    e = Edge(id=stable_edge_id(src, dst, EdgeType.DEPENDS_ON), type=EdgeType.DEPENDS_ON, src=src, dst=dst,
                             attributes={}, provenance=prov)
                    e.hash = compute_edge_hash(e)
                    edges.append(e)
            elif atype == "field":
                node_id = stable_node_id(system, NodeType.FIELD, name)
                n = Node(id=node_id, type=NodeType.FIELD, system=system, name=name,
                         attributes=a.get("attributes", {}), provenance=prov)
                n.hash = compute_node_hash(n)
                nodes.append(n)
            elif atype == "relationship":
                # relationships are edges (joins_to)
                src = a["attributes"].get("left")
                dst = a["attributes"].get("right")
                if src and dst:
                    src_id = stable_node_id(system, NodeType.ENTITY, src)
                    dst_id = stable_node_id(system, NodeType.ENTITY, dst)
                    e = Edge(id=stable_edge_id(src_id, dst_id, EdgeType.JOINS_TO), type=EdgeType.JOINS_TO, src=src_id, dst=dst_id,
                             attributes={k: v for k, v in a.get("attributes", {}).items() if k not in ("left", "right")}, provenance=prov)
                    e.hash = compute_edge_hash(e)
                    edges.append(e)
            elif atype == "context_tag":
                node_id = stable_node_id(system, NodeType.CONTEXT_TAG, name)
                n = Node(id=node_id, type=NodeType.CONTEXT_TAG, system=system, name=name,
                         attributes=a.get("attributes", {}), provenance=prov)
                n.hash = compute_node_hash(n)
                nodes.append(n)
            # ignore others for now
        return nodes, edges

    def persist(self, store: JSONStore, nodes: List[Node], edges: List[Edge], manifest: Dict[str, Any]) -> None:
        start = time.time()
        store.save_atomic(nodes, edges, manifest)
        dur = time.time() - start
        summary = {
            "event": "persist_snapshot",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "runtime_seconds": round(dur, 3),
            "snapshot_dir": str(store.snapshot_dir),
        }
        logger.info(json.dumps(summary))


if __name__ == "__main__":
    import argparse, sys, json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Build semantic graph and manifest.")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        src_path = Path(args.source)
        if not src_path.exists():
            raise FileNotFoundError(f"Source not found: {src_path}")

        # Generic artifact loader - supports multiple adapters
        artifacts: list[dict[str, any]] = []
        adapter_name = args.adapter.lower()
        
        if adapter_name == "bi_tool":
            # Generic BI tool extractor - create entities from metadata files
            metadata_files = list(src_path.rglob("*.json")) + list(src_path.rglob("*.yaml")) + list(src_path.rglob("*.yml"))
            for f in metadata_files:
                name = f.stem
                artifacts.append({
                    "system": "bi_tool",
                    "type": "entity",
                    "name": name,
                    "source_path": str(f),
                })
        elif adapter_name == "database":
            # Database catalog extractor
            # This would be populated by database catalog extractor
            pass
        else:
            raise ValueError(f"Unsupported adapter: {args.adapter}. Supported: bi_tool, database")

        gb = GraphBuilder()
        nodes, edges = gb.build(artifacts)

        out_path = Path(args.output)
        snapshot_dir = out_path.parent
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        if JSONStore:
            store = JSONStore(snapshot_dir)
            store.save_atomic(nodes, edges, {"adapter": args.adapter})
        else:
            logger.warning("JSONStore not available, skipping persistence")

        # Also write a small summary to the specified output path for convenience
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "adapter": args.adapter,
                "source": str(src_path),
                "node_count": len(nodes),
                "edge_count": len(edges),
            }, f)

        print(f"✅ Graph built from {args.source} using {args.adapter}")
        print(f"Nodes: {len(nodes)}, Edges: {len(edges)}")
    except Exception as e:
        print(f"❌ Graph build failed: {e}")
        sys.exit(1)
