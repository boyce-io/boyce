#!/usr/bin/env python3
"""
Ingestion CLI

End-to-end ingestion pipeline: extract → validate → merge → write manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.merge import merge_nodes_and_edges
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.extractors.database_catalog import DatabaseCatalogExtractor
from datashark_mcp.context.extractors.bi_tool import BIToolExtractor

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_jsonl(file_path: Path, model_class) -> List:
    """Load JSONL file and validate against schema."""
    items = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                item = model_class.from_dict(data)
                item.validate()  # Validate against schema
                items.append(item)
            except Exception as e:
                print(f"ERROR: Failed to parse {file_path}:{line_num}: {e}", file=sys.stderr)
                sys.exit(1)
    return items


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load and validate manifest."""
    with open(manifest_path, "r") as f:
        data = json.load(f)
    # Validate against schema (basic check)
    required_keys = ["run_id", "system", "start_time", "end_time", "counts", "versions", "status", "hash_summaries"]
    for key in required_keys:
        if key not in data:
            print(f"ERROR: Manifest missing required key: {key}", file=sys.stderr)
            sys.exit(1)
    return data


def run_extractor(extractor_name: str, extractor, input_path: str | None, since: str | None, temp_dir: Path) -> Path:
    """Run extractor and return output directory."""
    extractor_out = temp_dir / extractor_name
    extractor_out.mkdir(parents=True, exist_ok=True)
    
    extractor.run(out_dir=str(extractor_out), since=since, input_path=input_path)
    
    return extractor_out


def load_instance_config(instance_path: Path) -> Dict[str, Any]:
    """Load instance configuration."""
    config_file = instance_path / "config.yaml"
    config_json = instance_path / "config.json"
    
    if config_file.exists():
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except ImportError:
            raise ValueError("YAML library required for config.yaml")
    elif config_json.exists():
        import json
        with open(config_json, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        raise ValueError(f"Config file not found in instance: {instance_path}")
    
    return {}


def load_instance_credentials(instance_path: Path) -> Dict[str, str]:
    """Load instance credentials from .env file."""
    creds_file = instance_path / "credentials.env"
    credentials = {}
    
    if creds_file.exists():
        with open(creds_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    credentials[key.strip()] = value.strip()
    
    # Also check environment variables
    for key in ['REDSHIFT_HOST', 'REDSHIFT_USER', 'REDSHIFT_PASSWORD', 'REDSHIFT_DB']:
        if key not in credentials and key in os.environ:
            credentials[key] = os.environ[key]
    
    return credentials


def get_instance_path(instance_name: Optional[str] = None) -> Path:
    """Get instance path from name or active instance."""
    import sys
    from pathlib import Path
    
    # Add tools to path for import
    tools_path = Path(__file__).parent.parent.parent / "tools"
    if str(tools_path) not in sys.path:
        sys.path.insert(0, str(tools_path))
    
    from instance_manager.registry import InstanceRegistry
    
    registry = InstanceRegistry()
    
    if instance_name:
        instance_info = registry.get_instance(instance_name)
        if not instance_info:
            raise ValueError(f"Instance '{instance_name}' not found")
        return Path(instance_info["path"])
    else:
        # Use active instance
        active = registry.get_active_instance()
        if not active:
            raise ValueError("No active instance and no instance name provided. Use --instance <name> or 'datashark instance switch <name>'")
        return Path(active["path"])


def main():
    """Main CLI entry point."""
    import os
    
    parser = argparse.ArgumentParser(description="Enterprise Graph Ingestion CLI")
    parser.add_argument("--extractor", action="append", required=False, choices=["database_catalog", "bi_tool", "dbt_project", "airflow_dag", "datahub_catalog"],
                        help="Extractor to run (can be repeated)")
    parser.add_argument("--input", type=str, help="Input data path (optional, per extractor)")
    parser.add_argument("--out", type=str, help="Output directory for artifacts (default: instance/manifests)")
    parser.add_argument("--since", type=str, help="ISO timestamp for incremental extraction")
    parser.add_argument("--instance", type=str, help="Instance name (default: active instance)")
    parser.add_argument("--benchmark", type=str, choices=["extractors"], help="Benchmark mode")
    parser.add_argument("--repeat", type=int, default=1, help="Number of times to repeat (for benchmark mode)")
    
    args = parser.parse_args()
    
    if not args.extractor:
        print("ERROR: --extractor required (use --extractor <name> one or more times)", file=sys.stderr)
        sys.exit(1)
    
    # Benchmark mode: repeat extractors and collect timing stats
    extractor_times = {}  # extractor_name -> [times in ms]
    benchmark_mode = args.benchmark == "extractors"
    
    # Handle instance-based paths
    instance_path = None
    if args.instance or args.out is None:
        try:
            instance_path = get_instance_path(args.instance)
            if args.out is None:
                args.out = str(instance_path / "manifests")
            
            # Load instance config and credentials
            if instance_path:
                config = load_instance_config(instance_path)
                credentials = load_instance_credentials(instance_path)
                
                # Set environment variables from credentials
                for key, value in credentials.items():
                    if value:
                        os.environ[key] = value
                
                # Use repositories from config if provided
                if config.get("repositories") and not args.input:
                    # Use first repository as input if extractor needs it
                    repos = config.get("repositories", [])
                    if repos:
                        args.input = repos[0]
        except Exception as e:
            print(f"WARNING: Instance handling failed: {e}", file=sys.stderr)
            if args.out is None:
                print("ERROR: --out required when instance not available", file=sys.stderr)
                sys.exit(1)
    
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Extractor registry (auto-register available extractors)
    extractors = {
        "database_catalog": DatabaseCatalogExtractor(),
        "bi_tool": BIToolExtractor(),
    }
    
    # Try to register additional extractors
    try:
        from datashark_mcp.context.extractors.dbt_project import DBTProjectExtractor
        extractors["dbt_project"] = DBTProjectExtractor()
    except ImportError:
        pass
    
    try:
        from datashark_mcp.context.extractors.airflow_dag import AirflowDAGExtractor
        extractors["airflow_dag"] = AirflowDAGExtractor()
    except ImportError:
        pass
    
    try:
        from datashark_mcp.context.extractors.datahub_catalog import DataHubCatalogExtractor
        extractors["datahub_catalog"] = DataHubCatalogExtractor()
    except ImportError:
        pass
    
    # Initialize store
    store = GraphStore()
    
    # Run extractors (with telemetry tracking)
    import time
    
    # Benchmark loop
    for repeat in range(args.repeat if benchmark_mode else 1):
        if benchmark_mode:
            print(f"Benchmark run {repeat + 1}/{args.repeat}...", file=sys.stderr)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            all_nodes: List[Node] = []
            all_edges: List[Edge] = []
            all_manifests: List[Dict[str, Any]] = []
            
            # Run extractors (sequentially for now, parallelization can be added)
            for extractor_name in args.extractor:
                if extractor_name not in extractors:
                    print(f"ERROR: Unknown extractor: {extractor_name}", file=sys.stderr)
                    sys.exit(1)
                
                extractor = extractors[extractor_name]
                start_time = time.time()
                print(f"Running extractor: {extractor_name}...", file=sys.stderr)
                
                extractor_out = run_extractor(extractor_name, extractor, args.input, args.since, temp_path)
                
                extraction_time = (time.time() - start_time) * 1000
                
                # Track times for benchmark mode
                if benchmark_mode:
                    if extractor_name not in extractor_times:
                        extractor_times[extractor_name] = []
                    extractor_times[extractor_name].append(extraction_time)
                
                # Log telemetry (only on last run in benchmark mode)
                if instance_path and (not benchmark_mode or repeat == args.repeat - 1):
                    logs_dir = instance_path / "logs"
                    logs_dir.mkdir(parents=True, exist_ok=True)
                    telemetry_log = logs_dir / "extraction_telemetry.jsonl"
                    
                    telemetry_entry = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "extractor": extractor_name,
                        "extraction_time_ms": extraction_time,
                        "system": extractor.name() if hasattr(extractor, 'name') else extractor_name
                    }
                    
                    with open(telemetry_log, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(telemetry_entry) + "\n")
                
                # Validate and load artifacts
                nodes_path = extractor_out / "nodes.jsonl"
                edges_path = extractor_out / "edges.jsonl"
                manifest_path = extractor_out / "manifest.json"
                
                if not nodes_path.exists() or not edges_path.exists() or not manifest_path.exists():
                    print(f"ERROR: Extractor {extractor_name} did not produce required artifacts", file=sys.stderr)
                    sys.exit(1)
                
                # Load and validate
                nodes = load_jsonl(nodes_path, Node)
                edges = load_jsonl(edges_path, Edge)
                manifest = load_manifest(manifest_path)
                
                # Check for BUSINESS_CONCEPT nodes (not allowed in extractors)
                for node in nodes:
                    if node.type == "BUSINESS_CONCEPT":
                        print(f"ERROR: Extractor {extractor_name} emitted BUSINESS_CONCEPT node (not allowed)", file=sys.stderr)
                        sys.exit(1)
                
                # Compute hashes
                nodes_hash = compute_file_hash(nodes_path)
                edges_hash = compute_file_hash(edges_path)
                
                # Update manifest hashes
                manifest["hash_summaries"]["nodes_sha256"] = nodes_hash
                manifest["hash_summaries"]["edges_sha256"] = edges_hash
                
                all_nodes.extend(nodes)
                all_edges.extend(edges)
                all_manifests.append(manifest)
                
                print(f"  Loaded {len(nodes)} nodes, {len(edges)} edges", file=sys.stderr)
            
            # Merge all extracts using store (only on last iteration in benchmark mode)
            if not benchmark_mode or repeat == args.repeat - 1:
                print(f"Merging {len(all_nodes)} nodes and {len(all_edges)} edges...", file=sys.stderr)
                merge_result = merge_nodes_and_edges(all_nodes, all_edges, store, handle_deletions=False)
                
                # Get merged nodes/edges from store
                merged_nodes = store.nodes()
                merged_edges = store.edges()
                
                # Run ADCIL pipeline if enabled
                adcil_summary = None
                if instance_path:
                    try:
                        config = load_instance_config(instance_path)
                        adcil_config = config.get("adcil", {})
                        
                        if adcil_config.get("enabled", True):
                            from datashark_mcp.agentic.adcil.pipeline import ADCILPipeline
                            
                            print("Running ADCIL pipeline...", file=sys.stderr)
                            adcil_pipeline = ADCILPipeline(store, instance_path, config)
                            adcil_summary = adcil_pipeline.run()
                            
                            # Re-get nodes/edges after ADCIL (may have added new ones)
                            merged_nodes = store.nodes()
                            merged_edges = store.edges()
                            
                            print(f"ADCIL complete: {adcil_summary}", file=sys.stderr)
                    except Exception as e:
                        print(f"WARNING: ADCIL pipeline failed: {e}", file=sys.stderr)
                        adcil_summary = {"error": str(e)}
                
                # Write consolidated manifest
                consolidated_manifest = {
                    "graph_schema_version": "0.2.0",
                    "build_timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "extractor_count": len(args.extractor),
                    "node_count": len(merged_nodes),
                    "edge_count": len(merged_edges),
                    "extractor_manifests": all_manifests
                }
                
                if adcil_summary:
                    consolidated_manifest["adcil"] = adcil_summary
                
                # Write merged artifacts with normalized timestamps for determinism
                merged_nodes_path = out_dir / "nodes.jsonl"
                merged_edges_path = out_dir / "edges.jsonl"
                merged_manifest_path = out_dir / "manifest.json"
                
                # Sort nodes and edges by ID for deterministic ordering
                merged_nodes.sort(key=lambda n: n.id)
                merged_edges.sort(key=lambda e: e.id)
                
                with open(merged_nodes_path, 'w', encoding='utf-8') as f:
                    for node in merged_nodes:
                        # Normalize timestamps for deterministic hashing
                        node_dict = node.to_dict(normalize_timestamps=True)
                        # Ensure sorted keys for deterministic JSON
                        f.write(json.dumps(node_dict, ensure_ascii=False, sort_keys=True) + "\n")
                
                with open(merged_edges_path, 'w', encoding='utf-8') as f:
                    for edge in merged_edges:
                        # Normalize timestamps for deterministic hashing
                        edge_dict = edge.to_dict(normalize_timestamps=True)
                        # Ensure sorted keys for deterministic JSON
                        f.write(json.dumps(edge_dict, ensure_ascii=False, sort_keys=True) + "\n")
                
                with open(merged_manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(consolidated_manifest, f, indent=2, ensure_ascii=False)
                
                # Log run summary to instance logs if available
                if instance_path:
                    logs_dir = instance_path / "logs"
                    logs_dir.mkdir(parents=True, exist_ok=True)
                    run_log = logs_dir / "ingest_run.jsonl"
                    
                    run_summary = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "instance": args.instance or "active",
                        "extractors": args.extractor,
                        "node_count": len(merged_nodes),
                        "edge_count": len(merged_edges),
                        "output_dir": str(out_dir)
                    }
                    
                    with open(run_log, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(run_summary) + "\n")
                
                print(f"✅ Ingestion complete: {len(merged_nodes)} nodes, {len(merged_edges)} edges", file=sys.stderr)
                print(f"   Output: {out_dir}", file=sys.stderr)
    
    # Output benchmark summary if in benchmark mode
    if benchmark_mode:
        import statistics
        print("\n=== Benchmark Summary ===", file=sys.stderr)
        for extractor_name, times in extractor_times.items():
            avg_ms = statistics.mean(times)
            p95_ms = statistics.quantiles(times, n=20)[18] if len(times) > 1 else times[0]
            print(f"  {extractor_name}:", file=sys.stderr)
            print(f"    Runs: {len(times)}", file=sys.stderr)
            print(f"    Avg: {avg_ms:.2f}ms", file=sys.stderr)
            print(f"    P95: {p95_ms:.2f}ms", file=sys.stderr)
            
            # Check budget
            if p95_ms > 500.0:
                print(f"    ⚠️  P95 exceeds budget (500ms)", file=sys.stderr)
            else:
                print(f"    ✅ P95 within budget (500ms)", file=sys.stderr)
        
        # Output JSON summary
        summary = {
            "benchmark": "extractors",
            "runs": args.repeat,
            "extractors": {
                name: {
                    "runs": len(times),
                    "avg_ms": statistics.mean(times),
                    "p95_ms": statistics.quantiles(times, n=20)[18] if len(times) > 1 else times[0],
                    "min_ms": min(times),
                    "max_ms": max(times)
                }
                for name, times in extractor_times.items()
            }
        }
        print(json.dumps(summary))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

