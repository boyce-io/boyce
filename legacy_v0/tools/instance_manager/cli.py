"""
Instance Management CLI

Command-line interface for managing DataShark instances.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

from .manager import InstanceManager
from .registry import InstanceRegistry

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new instance."""
    manager = InstanceManager()
    try:
        instance_path = manager.create_instance(args.name)
        print(json.dumps({
            "event": "instance_created",
            "name": args.name,
            "path": str(instance_path)
        }))
        return 0
    except Exception as e:
        logger.error(f"Failed to create instance: {e}")
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all instances."""
    registry = InstanceRegistry()
    instances = registry.list_instances()
    active = registry.get_active_instance()
    
    result = {
        "active": registry.load_registry().get("active"),
        "instances": instances
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    """Switch active instance."""
    registry = InstanceRegistry()
    try:
        registry.set_active_instance(args.name)
        print(json.dumps({
            "event": "instance_switched",
            "name": args.name
        }))
        return 0
    except Exception as e:
        logger.error(f"Failed to switch instance: {e}")
        return 1


def cmd_build(args: argparse.Namespace) -> int:
    """Build instance."""
    manager = InstanceManager()
    try:
        result = manager.build_instance(name=args.name)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        logger.error(f"Failed to build instance: {e}")
        return 1


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Upgrade instance."""
    manager = InstanceManager()
    try:
        result = manager.upgrade_instance(name=args.name, target_version=args.target)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        logger.error(f"Failed to upgrade instance: {e}")
        return 1


def cmd_destroy(args: argparse.Namespace) -> int:
    """Destroy instance."""
    manager = InstanceManager()
    try:
        manager.destroy_instance(args.name)
        print(json.dumps({
            "event": "instance_destroyed",
            "name": args.name
        }))
        return 0
    except Exception as e:
        logger.error(f"Failed to destroy instance: {e}")
        return 1


def cmd_ingest(args: argparse.Namespace) -> int:
    """Run ingestion pipeline."""
    import subprocess
    from pathlib import Path
    
    # Get instance
    registry = InstanceRegistry()
    instance_name = args.instance
    if not instance_name:
        active = registry.get_active_instance()
        if not active:
            logger.error("No active instance and no instance name provided")
            return 1
        instance_name = active["name"]
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    ingest_script = project_root / "datashark-mcp" / "tools" / "ingest.py"
    
    if not ingest_script.exists():
        logger.error(f"Ingest script not found at {ingest_script}")
        return 1
    
    # Build command
    cmd = [sys.executable, str(ingest_script), "--instance", instance_name]
    for extractor in args.extractor:
        cmd.extend(["--extractor", extractor])
    
    # Run ingestion
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return 1


def cmd_query(args: argparse.Namespace) -> int:
    """Execute query (SQL/DSL/NL)."""
    import asyncio
    from pathlib import Path
    
    # Add project root to path
    project_root = Path(__file__).parent.parent.parent
    datashark_mcp_src = project_root / "datashark-mcp" / "src"
    core_src = project_root / "core"
    sys.path.insert(0, str(datashark_mcp_src))
    sys.path.insert(0, str(core_src))
    
    from datashark.core.server import DataSharkMCPServer
    
    # Determine instance
    registry = InstanceRegistry()
    instance_name = args.instance
    if not instance_name:
        active = registry.get_active_instance()
        if not active:
            logger.error("No active instance and no instance name provided")
            return 1
        instance_name = active["name"]
    
    # Determine query type and query text
    if args.sql:
        query_type = "sql"
        query_text = args.sql
    elif args.dsl:
        query_type = "dsl"
        query_text = args.dsl
    elif args.nl:
        query_type = "nl"
        query_text = args.nl
    else:
        logger.error("Must specify --sql, --dsl, or --nl")
        return 1
    
    try:
        # Create server instance
        server = DataSharkMCPServer()
        
        # Run async query
        async def run_query():
            result = await server._run_query(
                query=query_text,
                query_type=query_type,
                instance_name=instance_name,
                limit=args.limit
            )
            return result
        
        # Execute query
        result = asyncio.run(run_query())
        
        # Print JSON result
        print(json.dumps(result, indent=2))
        
        # Log telemetry
        instance_info = registry.get_instance(instance_name)
        if instance_info:
            instance_path = Path(instance_info["path"])
            logs_dir = instance_path / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            telemetry_file = logs_dir / "ui_events.jsonl"
            telemetry_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "query_executed",
                "instance": instance_name,
                "query_type": query_type,
                "success": result.get("success", False),
                "latency_ms": result.get("latency_ms", 0),
                "row_count": result.get("count", 0),
                "trace_id": result.get("reasoning_trace_id")
            }
            with open(telemetry_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(telemetry_entry) + "\n")
        
        # Exit non-zero on error
        if not result.get("success", False) or result.get("error"):
            return 1
        
        return 0
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        # Log error to telemetry
        try:
            instance_info = registry.get_instance(instance_name)
            if instance_info:
                instance_path = Path(instance_info["path"])
                logs_dir = instance_path / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                telemetry_file = logs_dir / "ui_events.jsonl"
                telemetry_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "query_error",
                    "instance": instance_name,
                    "query_type": query_type,
                    "error": str(e)
                }
                with open(telemetry_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(telemetry_entry) + "\n")
        except:
            pass
        return 1


def cmd_info(args: argparse.Namespace) -> int:
    """Show framework information."""
    import sys
    from pathlib import Path
    import json
    from datetime import datetime
    
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))
    
    from .registry import InstanceRegistry
    
    registry = InstanceRegistry()
    active = registry.get_active_instance()
    
    # Framework version
    version_file = project_root / "datashark-mcp" / "pyproject.toml"
    version = "0.3.0"  # Default
    if version_file.exists():
        try:
            import re
            content = version_file.read_text()
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if match:
                version = match.group(1)
        except:
            pass
    
    print("=" * 60)
    print("DataShark Framework Information")
    print("=" * 60)
    print(f"Framework Version: {version}")
    print(f"Active Instance: {active.get('name', 'None') if active else 'None'}")
    if active:
        instance_path = Path(active["path"])
        print(f"Instance Path: {instance_path}")
        
        # Manifest counts
        manifest_dir = instance_path / "manifests"
        if manifest_dir.exists():
            nodes_file = manifest_dir / "nodes.jsonl"
            edges_file = manifest_dir / "edges.jsonl"
            
            node_count = 0
            if nodes_file.exists():
                with open(nodes_file, 'r') as f:
                    node_count = sum(1 for line in f if line.strip())
            
            edge_count = 0
            if edges_file.exists():
                with open(edges_file, 'r') as f:
                    edge_count = sum(1 for line in f if line.strip())
            
            print(f"Manifest Counts: {node_count} nodes, {edge_count} edges")
        
        # Last learning run
        logs_dir = instance_path / "logs"
        learning_log = logs_dir / "learning_run.jsonl"
        if learning_log.exists():
            try:
                with open(learning_log, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        last_run = json.loads(lines[-1])
                        timestamp = last_run.get("timestamp", "")
                        print(f"Last Learning Run: {timestamp}")
            except:
                print("Last Learning Run: (unable to parse)")
        else:
            print("Last Learning Run: Never")
    
    print("=" * 60)
    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="DataShark Instance Management")
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # create
    create_parser = subparsers.add_parser('create', help='Create a new instance')
    create_parser.add_argument('name', help='Instance name')
    create_parser.set_defaults(func=cmd_create)
    
    # list
    list_parser = subparsers.add_parser('list', help='List all instances')
    list_parser.set_defaults(func=cmd_list)
    
    # switch
    switch_parser = subparsers.add_parser('switch', help='Switch active instance')
    switch_parser.add_argument('name', help='Instance name')
    switch_parser.set_defaults(func=cmd_switch)
    
    # build
    build_parser = subparsers.add_parser('build', help='Build instance')
    build_parser.add_argument('--name', help='Instance name (default: active)')
    build_parser.set_defaults(func=cmd_build)
    
    # upgrade
    upgrade_parser = subparsers.add_parser('upgrade', help='Upgrade instance')
    upgrade_parser.add_argument('--name', help='Instance name (default: active)')
    upgrade_parser.add_argument('--target', help='Target version (default: current)')
    upgrade_parser.set_defaults(func=cmd_upgrade)
    
    # destroy
    destroy_parser = subparsers.add_parser('destroy', help='Destroy instance')
    destroy_parser.add_argument('name', help='Instance name')
    destroy_parser.set_defaults(func=cmd_destroy)
    
    # learn
    learn_parser = subparsers.add_parser('learn', help='Run learning loop (feedback + retraining + evaluation)')
    learn_parser.add_argument('--instance', help='Instance name (default: active)')
    learn_parser.add_argument('--json', action='store_true', help='Output JSON format')
    learn_parser.set_defaults(func=cmd_learn)
    
    # info
    info_parser = subparsers.add_parser('info', help='Show framework information')
    info_parser.set_defaults(func=cmd_info)
    
    # ingest
    ingest_parser = subparsers.add_parser('ingest', help='Run ingestion pipeline')
    ingest_parser.add_argument('--instance', help='Instance name (default: active)')
    ingest_parser.add_argument('--extractor', action='append', required=True, 
                              choices=['database_catalog', 'bi_tool', 'dbt_project', 'airflow_dag', 'datahub_catalog'],
                              help='Extractor to run (can be repeated)')
    ingest_parser.set_defaults(func=cmd_ingest)
    
    # query
    query_parser = subparsers.add_parser('query', help='Execute SQL/DSL/Natural Language query')
    query_parser.add_argument('--instance', help='Instance name (default: active)')
    query_group = query_parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument('--sql', help='SQL query')
    query_group.add_argument('--dsl', help='DSL query')
    query_group.add_argument('--nl', help='Natural language query')
    query_parser.add_argument('--limit', type=int, default=100, help='Maximum rows to return (default: 100)')
    query_parser.set_defaults(func=cmd_query)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


def cmd_learn(args: argparse.Namespace) -> int:
    """Run learning loop (feedback collection + model updates + evaluation)."""
    import sys
    from pathlib import Path
    
    # Add project root to path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))
    
    from datashark_mcp.agentic.learning.feedback_collector import FeedbackCollector
    from datashark_mcp.agentic.learning.model_updater import ModelUpdater
    from datashark_mcp.agentic.learning.evaluation_tracker import EvaluationTracker
    
    # Get instance path
    registry = InstanceRegistry()
    
    if args.instance:
        instance_info = registry.get_instance(args.instance)
        if not instance_info:
            logger.error(f"Instance '{args.instance}' not found")
            return 1
        instance_path = Path(instance_info["path"])
    else:
        active = registry.get_active_instance()
        if not active:
            logger.error("No active instance and no instance name provided")
            return 1
        instance_path = Path(active["path"])
    
    try:
        # Initialize components
        feedback_collector = FeedbackCollector(instance_path)
        model_updater = ModelUpdater(instance_path)
        evaluation_tracker = EvaluationTracker(instance_path)
        
        # Collect feedback
        logger.info("Collecting feedback...")
        feedback = feedback_collector.aggregate_feedback()
        
        # Retrain models
        logger.info("Retraining models...")
        model_updates = model_updater.retrain_models()
        
        # Record evaluation metrics
        logger.info("Recording evaluation metrics...")
        evaluation_tracker.record_metric("learning_cycle", 1.0, {
            "feedback_events": feedback.get("telemetry_events", 0),
            "corrections": feedback.get("corrections", 0)
        })
        
        # Get metrics summary
        metrics_summary = evaluation_tracker.get_metrics_summary()
        
        # Write results
        result = {
            "event": "learning_complete",
            "instance": args.instance or "active",
            "feedback": feedback,
            "model_updates": model_updates,
            "metrics": metrics_summary
        }
        
        # Write to instance logs
        logs_dir = instance_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        learning_log = logs_dir / "learning_run.jsonl"
        
        with open(learning_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result) + "\n")
        
        # Print summary table
        print("\n" + "="*60)
        print("Learning Loop Summary")
        print("="*60)
        print(f"Instance: {args.instance or 'active'}")
        print(f"Feedback Entries: {feedback.get('total_feedback_entries', 0)}")
        print(f"Corrections: {feedback.get('corrections', 0)}")
        print(f"Errors: {feedback.get('metrics', {}).get('error_count', 0)}")
        print("\nMetrics:")
        print(f"  Accuracy: {metrics_summary.get('avg_accuracy', 0.0):.2%}")
        print(f"  Precision: {metrics_summary.get('avg_precision', 0.0):.2%}")
        print(f"  Recall: {metrics_summary.get('avg_recall', 0.0):.2%}")
        print(f"  p95 Latency: {metrics_summary.get('p95_latency_ms', 0.0):.1f} ms")
        if "latency_delta_ms" in metrics_summary:
            delta = metrics_summary["latency_delta_ms"]
            sign = "+" if delta >= 0 else ""
            print(f"  Latency Delta: {sign}{delta:.1f} ms")
        print("\nModel Updates:")
        print(f"  DSL Templates: {model_updates.get('dsl_templates', {}).get('templates_updated', 0)}")
        print(f"  Join Heuristics: {model_updates.get('join_heuristics', {}).get('patterns_updated', 0)}")
        print("="*60 + "\n")
        
        # Also output JSON for programmatic use
        if args.json:
            print(json.dumps(result, indent=2))
        
        return 0
        
    except Exception as e:
        logger.error(f"Learning loop failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())

