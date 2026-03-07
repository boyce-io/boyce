#!/usr/bin/env python3
"""
Telemetry Dashboard

Parses telemetry JSONL logs and generates aggregated metrics report.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any
from datashark_mcp.orchestration.instance_hub import InstanceHub, FederatedIntelligenceManager


def parse_telemetry_logs(telemetry_file: Path) -> List[Dict[str, Any]]:
    """Parse telemetry JSONL file."""
    logs = []
    with open(telemetry_file, "r") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))
    return logs


def aggregate_metrics(logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate metrics from logs."""
    # Group by phase/operation
    by_phase = defaultdict(list)
    by_extractor = defaultdict(list)
    by_api_method = defaultdict(list)
    
    for log in logs:
        phase = log.get("phase", "unknown")
        by_phase[phase].append(log)
        
        if "extractors" in log:
            for extractor in log.get("extractors", []):
                by_extractor[extractor].append(log)
        
        api_method = log.get("api_method")
        if api_method:
            by_api_method[api_method].append(log)
    
    # Compute statistics
    stats = {
        "total_runs": len(set(log.get("run_id") for log in logs if log.get("run_id"))),
        "by_phase": {},
        "by_extractor": {},
        "by_api_method": {},
        "node_growth": [],
        "edge_growth": []
    }
    
    # Aggregate by phase
    for phase, phase_logs in by_phase.items():
        durations = [log.get("duration_ms", 0) for log in phase_logs if log.get("duration_ms")]
        stats["by_phase"][phase] = {
            "count": len(phase_logs),
            "avg_duration_ms": statistics.mean(durations) if durations else 0,
            "p95_duration_ms": statistics.quantiles(durations, n=20)[18] if len(durations) > 1 else (durations[0] if durations else 0)
        }
    
    # Aggregate by extractor
    for extractor, extractor_logs in by_extractor.items():
        node_counts = [log.get("node_count", 0) for log in extractor_logs if log.get("node_count")]
        edge_counts = [log.get("edge_count", 0) for log in extractor_logs if log.get("edge_count")]
        stats["by_extractor"][extractor] = {
            "count": len(extractor_logs),
            "avg_nodes": statistics.mean(node_counts) if node_counts else 0,
            "avg_edges": statistics.mean(edge_counts) if edge_counts else 0
        }
    
    # Aggregate by API method
    for method, method_logs in by_api_method.items():
        durations = [log.get("duration_ms", 0) for log in method_logs if log.get("duration_ms")]
        stats["by_api_method"][method] = {
            "count": len(method_logs),
            "p50_ms": statistics.median(durations) if durations else 0,
            "p95_ms": statistics.quantiles(durations, n=20)[18] if len(durations) > 1 else (durations[0] if durations else 0)
        }
    
    # Track growth
    for log in sorted(logs, key=lambda x: x.get("timestamp", "")):
        if log.get("node_count") is not None and log.get("edge_count") is not None:
            stats["node_growth"].append({
                "timestamp": log.get("timestamp"),
                "count": log.get("node_count")
            })
            stats["edge_growth"].append({
                "timestamp": log.get("timestamp"),
                "count": log.get("edge_count")
            })
    
    return stats


def generate_report(stats: Dict[str, Any], output_file: Path) -> None:
    """Generate Markdown report."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Telemetry Report\n\n")
        f.write(f"**Generated:** {stats.get('timestamp', 'N/A')}\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"- **Total Runs:** {stats['total_runs']}\n\n")
        
        f.write("## Performance by Phase\n\n")
        f.write("| Phase | Count | Avg Duration (ms) | P95 Duration (ms) |\n")
        f.write("|-------|-------|-------------------|-------------------|\n")
        for phase, phase_stats in sorted(stats["by_phase"].items()):
            f.write(f"| {phase} | {phase_stats['count']} | {phase_stats['avg_duration_ms']:.2f} | {phase_stats['p95_duration_ms']:.2f} |\n")
        f.write("\n")
        
        f.write("## Performance by API Method\n\n")
        f.write("| Method | Count | P50 (ms) | P95 (ms) |\n")
        f.write("|--------|-------|----------|----------|\n")
        for method, method_stats in sorted(stats["by_api_method"].items()):
            f.write(f"| {method} | {method_stats['count']} | {method_stats['p50_ms']:.2f} | {method_stats['p95_ms']:.2f} |\n")
        f.write("\n")
        
        f.write("## Extractor Statistics\n\n")
        f.write("| Extractor | Count | Avg Nodes | Avg Edges |\n")
        f.write("|-----------|-------|-----------|-----------|\n")
        for extractor, extractor_stats in sorted(stats["by_extractor"].items()):
            f.write(f"| {extractor} | {extractor_stats['count']} | {extractor_stats['avg_nodes']:.0f} | {extractor_stats['avg_edges']:.0f} |\n")
        f.write("\n")


def summarize_telemetry(instance_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Generate summary of ingestion/learning/query latencies.
    
    Args:
        instance_path: Optional instance path (default: active instance)
        
    Returns:
        Summary dict with aggregated metrics
    """
    from datetime import datetime, timezone
    import sys
    
    if instance_path is None:
        # Get active instance
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root / "tools"))
        from instance_manager.registry import InstanceRegistry
        
        registry = InstanceRegistry()
        active = registry.get_active_instance()
        if not active:
            print("ERROR: No active instance", file=sys.stderr)
            return {}
        instance_path = Path(active["path"])
    
    logs_dir = instance_path / "logs"
    
    summary = {
        "instance": str(instance_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ingestion": {},
        "learning": {},
        "queries": {}
    }
    
    # Ingestion telemetry
    extraction_file = logs_dir / "extraction_telemetry.jsonl"
    if extraction_file.exists():
        ingestion_times = []
        with open(extraction_file, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if "extraction_time_ms" in data:
                        ingestion_times.append(data["extraction_time_ms"])
        
        if ingestion_times:
            summary["ingestion"] = {
                "count": len(ingestion_times),
                "avg_ms": sum(ingestion_times) / len(ingestion_times),
                "p95_ms": sorted(ingestion_times)[int(len(ingestion_times) * 0.95)] if len(ingestion_times) > 1 else ingestion_times[0],
                "min_ms": min(ingestion_times),
                "max_ms": max(ingestion_times)
            }
    
    # Learning telemetry
    learning_file = logs_dir / "learning_history.jsonl"
    if learning_file.exists():
        learning_times = []
        with open(learning_file, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if "avg_latency_ms" in data:
                        learning_times.append(data["avg_latency_ms"])
        
        if learning_times:
            summary["learning"] = {
                "count": len(learning_times),
                "avg_ms": sum(learning_times) / len(learning_times),
                "p95_ms": sorted(learning_times)[int(len(learning_times) * 0.95)] if len(learning_times) > 1 else learning_times[0],
                "min_ms": min(learning_times),
                "max_ms": max(learning_times)
            }
    
    # Query telemetry
    ui_events_file = logs_dir / "ui_events.jsonl"
    if ui_events_file.exists():
        query_times = []
        with open(ui_events_file, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if data.get("event") in ["query_success", "query_error"] and "latency_ms" in data:
                        query_times.append(data["latency_ms"])
        
        if query_times:
            summary["queries"] = {
                "count": len(query_times),
                "avg_ms": sum(query_times) / len(query_times),
                "p95_ms": sorted(query_times)[int(len(query_times) * 0.95)] if len(query_times) > 1 else query_times[0],
                "min_ms": min(query_times),
                "max_ms": max(query_times)
            }
    
    return summary


def main():
    """Main CLI entry point."""
    import sys
    from typing import Optional
    
    parser = argparse.ArgumentParser(description="Generate telemetry dashboard report")
    parser.add_argument("--telemetry", type=str, help="Path to telemetry.jsonl file")
    parser.add_argument("--output", type=str, help="Output markdown file (defaults to cursor_workspace/telemetry_report.md)")
    parser.add_argument("--summarize", action="store_true", help="Generate summary of latencies")
    parser.add_argument("--federated", action="store_true", help="Include federated intelligence metrics")
    parser.add_argument("--fed-output", type=str, help="Output markdown file for federated intelligence status")
    parser.add_argument("--instance", type=str, help="Instance path for --summarize (default: active instance)")
    
    args = parser.parse_args()
    
    if args.summarize and not args.federated:
        # Generate summary
        instance_path = None
        if args.instance:
            instance_path = Path(args.instance)
        
        summary = summarize_telemetry(instance_path)
        print(json.dumps(summary, indent=2))
        return 0

    if args.federated:
        # Build federated metrics using registered instances from registry
        project_root = Path(__file__).parent.parent.parent
        import sys
        sys.path.insert(0, str(project_root / "tools"))
        from instance_manager.registry import InstanceRegistry
        registry = InstanceRegistry()
        instances = registry.list_instances()
        hub = InstanceHub()
        for inst in instances:
            hub.register_instance(inst["name"], Path(inst["path"]))

        fim = FederatedIntelligenceManager(hub)
        metrics = fim.collect_federated_metrics()
        weights = fim.compute_confidence_weights(metrics)

        # Prepare markdown output
        output_file = Path(args.fed_output) if args.fed_output else (project_root / "cursor_workspace" / "FEDERATED_INTELLIGENCE_STATUS.md")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Federated Intelligence Status\n\n")
            f.write(f"**Generated:** {metrics.get('timestamp','N/A')}\n\n")
            f.write("## Per-Instance Metrics\n\n")
            f.write("| Instance | Accuracy | Precision | Recall | Avg Latency (ms) | Trust Weight |\n")
            f.write("|----------|----------|-----------|--------|------------------|--------------|\n")
            for name, m in sorted(metrics.get("instances", {}).items()):
                f.write(f"| {name} | {m['avg_accuracy']:.2%} | {m['avg_precision']:.2%} | {m['avg_recall']:.2%} | {m['avg_latency_ms']:.1f} | {weights.get(name,0.0):.3f} |\n")
            f.write("\n")
            # Weighted global averages
            def wavg(key: str) -> float:
                num = 0.0
                den = 0.0
                for name, m in metrics.get("instances", {}).items():
                    w = weights.get(name, 0.0)
                    num += w * float(m.get(key, 0.0))
                    den += w
                return (num / den) if den > 0 else 0.0

            f.write("## Weighted Global Averages\n\n")
            f.write(f"- **Accuracy:** {wavg('avg_accuracy'):.2%}\n")
            f.write(f"- **Precision:** {wavg('avg_precision'):.2%}\n")
            f.write(f"- **Recall:** {wavg('avg_recall'):.2%}\n")
            # Latency averages are in ms
            f.write(f"- **Latency (ms):** {wavg('avg_latency_ms'):.1f}\n")

        print(json.dumps({"file": str(output_file), "weights": weights}, indent=2))
        return 0
    
    if not args.telemetry:
        parser.error("--telemetry is required when not using --summarize")
    
    telemetry_file = Path(args.telemetry)
    if not telemetry_file.exists():
        print(f"Error: Telemetry file not found: {telemetry_file}", file=sys.stderr)
        sys.exit(1)
    
    if args.output:
        output_file = Path(args.output)
    else:
        project_root = Path(__file__).resolve().parents[2]
        output_file = project_root / "cursor_workspace" / "telemetry_report.md"
    
    # Parse logs
    logs = parse_telemetry_logs(telemetry_file)
    
    if not logs:
        print("Warning: No telemetry logs found", file=sys.stderr)
        return
    
    # Aggregate
    stats = aggregate_metrics(logs)
    stats["timestamp"] = logs[-1].get("timestamp", "N/A") if logs else "N/A"
    
    # Generate report
    generate_report(stats, output_file)
    
    print(f"Report generated: {output_file}", file=sys.stderr)


if __name__ == "__main__":
    import sys
    sys.exit(main())

