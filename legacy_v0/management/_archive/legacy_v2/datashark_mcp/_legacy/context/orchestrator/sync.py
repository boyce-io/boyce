"""
Multi-Repo Sync

Orchestrates multiple extractors and generates consolidated manifest.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timezone
from datashark_mcp.context.orchestrator.repo_manager import RepoManager
from datashark_mcp.context.manifest import Manifest
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.merge import merge_nodes_and_edges
from datashark_mcp.context.models import Node, Edge


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        sha256.update(f.read())
    return sha256.hexdigest()


def sync_extractors(
    extractor_configs: List[Dict[str, Any]],
    output_dir: Path,
    repo_manager: RepoManager = None
) -> Dict[str, Any]:
    """
    Sync multiple extractors and merge results.
    
    Args:
        extractor_configs: List of extractor configs with 'name', 'input_path', 'system', 'repo_id'
        output_dir: Output directory for consolidated artifacts
        repo_manager: Optional RepoManager instance
        
    Returns:
        Consolidated manifest dict
    """
    if repo_manager is None:
        repo_manager = RepoManager()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    all_nodes: List[Node] = []
    all_edges: List[Edge] = []
    all_manifests: List[Dict[str, Any]] = []
    
    # Run each extractor
    for config in extractor_configs:
        extractor_name = config["name"]
        system = config["system"]
        repo_id = config.get("repo_id", f"{system}_default")
        
        # Register repo if needed
        if not repo_manager.get_repo(repo_id):
            repo_manager.register_repo(repo_id, system)
        
        # Import extractor dynamically
        if extractor_name == "database_catalog":
            from datashark_mcp.context.extractors.database_catalog import DatabaseCatalogExtractor
            extractor = DatabaseCatalogExtractor()
        elif extractor_name == "bi_tool":
            from datashark_mcp.context.extractors.bi_tool import BIToolExtractor
            extractor = BIToolExtractor()
        else:
            raise ValueError(f"Unknown extractor: {extractor_name}")
        
        # Run extractor
        extractor_out = output_dir / f"extractor_{repo_id}"
        extractor_out.mkdir(parents=True, exist_ok=True)
        
        extractor.run(
            out_dir=str(extractor_out),
            input_path=config.get("input_path")
        )
        
        # Load artifacts
        nodes_path = extractor_out / "nodes.jsonl"
        edges_path = extractor_out / "edges.jsonl"
        manifest_path = extractor_out / "manifest.json"
        
        # Load nodes
        with open(nodes_path, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    node = Node.from_dict(data)
                    all_nodes.append(node)
        
        # Load edges
        with open(edges_path, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    edge = Edge.from_dict(data)
                    all_edges.append(edge)
        
        # Load manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
            all_manifests.append(manifest)
            
            # Update repo state
            manifest_hash = manifest.get("hash_summaries", {}).get("nodes_sha256", "")
            repo_manager.update_repo(repo_id, manifest_hash)
    
    # Merge into unified store
    store = GraphStore()
    merge_result = merge_nodes_and_edges(all_nodes, all_edges, store, handle_deletions=False)
    
    # Write consolidated artifacts
    from datashark_mcp.context.extractors.base import write_jsonl
    
    nodes_data = [node.to_dict() for node in all_nodes]
    write_jsonl(output_dir / "nodes.jsonl", nodes_data)
    
    edges_data = [edge.to_dict() for edge in all_edges]
    write_jsonl(output_dir / "edges.jsonl", edges_data)
    
    # Create consolidated manifest
    consolidated = {
        "run_id": all_manifests[0]["run_id"] if all_manifests else str(datetime.now(timezone.utc)),
        "systems": [m["system"] for m in all_manifests],
        "start_time": min(m["start_time"] for m in all_manifests) if all_manifests else datetime.now(timezone.utc).isoformat(),
        "end_time": max(m["end_time"] for m in all_manifests) if all_manifests else datetime.now(timezone.utc).isoformat(),
        "counts": {
            "nodes": merge_result.new_nodes + merge_result.changed_nodes,
            "edges": merge_result.new_edges + merge_result.changed_edges,
            "tombstones": merge_result.deleted_nodes + merge_result.deleted_edges
        },
        "hash_summaries": {
            "nodes_sha256": compute_file_hash(output_dir / "nodes.jsonl"),
            "edges_sha256": compute_file_hash(output_dir / "edges.jsonl")
        },
        "status": "success" if all(m.get("status") == "success" for m in all_manifests) else "warning"
    }
    
    with open(output_dir / "manifest.json", "w") as f:
        json.dump(consolidated, f, indent=2, sort_keys=True)
    
    # Generate consolidated telemetry
    telemetry = {
        "run_id": consolidated["run_id"],
        "phase": "orchestration",
        "duration_ms": 0,  # Would be measured
        "node_count": consolidated["counts"]["nodes"],
        "edge_count": consolidated["counts"]["edges"],
        "extractors": [c["name"] for c in extractor_configs],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    with open(output_dir / "telemetry.jsonl", "w") as f:
        json.dump(telemetry, f)
        f.write("\n")
    
    return consolidated

