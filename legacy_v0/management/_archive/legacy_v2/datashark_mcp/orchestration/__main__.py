"""
Main entry point for instance_hub module.
Supports --federated-summary command for deterministic aggregation testing.
"""
import argparse
import json
import sys
from pathlib import Path

from .instance_hub import InstanceHub, FederatedIntelligenceManager


def main():
    """Main entry point for federated-summary command."""
    parser = argparse.ArgumentParser(
        description="Instance Hub - Federated Intelligence Manager"
    )
    parser.add_argument(
        "--federated-summary",
        type=str,
        help="Output path for federated summary JSON"
    )
    
    args = parser.parse_args()
    
    if args.federated_summary:
        # Load instance registry
        import sys
        from pathlib import Path as P
        
        # Add tools directory to path
        # __file__ is at datashark-mcp/src/datashark_mcp/orchestration/__main__.py
        # We need to go up to project root: orchestration -> datashark_mcp -> src -> datashark-mcp -> project root
        current_file = P(__file__).resolve()
        # Go up 5 levels: __main__.py -> orchestration -> datashark_mcp -> src -> datashark-mcp -> project root
        project_root = current_file.parent.parent.parent.parent.parent
        tools_dir = project_root / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        
        from instance_manager.registry import InstanceRegistry
        
        registry = InstanceRegistry()
        instances = registry.list_instances()
        
        # Initialize hub
        hub = InstanceHub()
        
        # Register all instances
        for instance_name, instance_info in instances.items():
            instance_path = Path(instance_info["path"])
            hub.register_instance(instance_name, instance_path)
        
        # Collect federated metrics
        manager = FederatedIntelligenceManager(hub)
        metrics = manager.collect_federated_metrics()
        weights = manager.compute_confidence_weights(metrics)
        
        # Create summary
        summary = {
            "timestamp": metrics.get("timestamp"),
            "instances": metrics.get("instances", {}),
            "weights": weights,
            "aggregated": {
                "weighted_accuracy": sum(
                    m.get("avg_accuracy", 0.0) * weights.get(name, 0.0)
                    for name, m in metrics.get("instances", {}).items()
                ),
                "weighted_precision": sum(
                    m.get("avg_precision", 0.0) * weights.get(name, 0.0)
                    for name, m in metrics.get("instances", {}).items()
                ),
                "weighted_recall": sum(
                    m.get("avg_recall", 0.0) * weights.get(name, 0.0)
                    for name, m in metrics.get("instances", {}).items()
                ),
                "weighted_latency_ms": sum(
                    m.get("avg_latency_ms", 0.0) * weights.get(name, 0.0)
                    for name, m in metrics.get("instances", {}).items()
                ),
            }
        }
        
        # Write output
        output_path = Path(args.federated_summary)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        print(f"Federated summary written to: {output_path}")
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

