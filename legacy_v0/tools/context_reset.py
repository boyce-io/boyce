#!/usr/bin/env python3
"""
Context Reset Tool

Reset manifests, cache, and telemetry for a DataShark instance.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Optional

# Add tools to path for import
tools_path = Path(__file__).parent
sys.path.insert(0, str(tools_path))

from instance_manager.registry import InstanceRegistry


def get_instance_path(instance_name: Optional[str] = None) -> Path:
    """Get instance path from name or active instance."""
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


def reset_instance(instance_path: Path, force: bool = False) -> dict:
    """
    Reset instance manifests, cache, and telemetry.
    
    Args:
        instance_path: Instance directory path
        force: Skip confirmation prompt
    
    Returns:
        Reset summary
    """
    if not instance_path.exists():
        raise ValueError(f"Instance path does not exist: {instance_path}")
    
    # Confirm unless force
    if not force:
        print(f"⚠️  This will reset manifests, cache, and telemetry for instance at:")
        print(f"   {instance_path}")
        response = input("Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Reset cancelled.")
            return {"cancelled": True}
    
    reset_summary = {
        "instance_path": str(instance_path),
        "timestamp": json.dumps({"timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z"}),
        "actions": []
    }
    
    # Reset manifests
    manifests_dir = instance_path / "manifests"
    if manifests_dir.exists():
        manifest_count = len(list(manifests_dir.glob("*.json"))) + len(list(manifests_dir.glob("*.jsonl")))
        shutil.rmtree(manifests_dir)
        manifests_dir.mkdir()
        reset_summary["actions"].append(f"Cleared {manifest_count} manifest files")
    
    # Reset cache
    cache_dir = instance_path / "cache"
    if cache_dir.exists():
        cache_count = len(list(cache_dir.rglob("*")))
        shutil.rmtree(cache_dir)
        cache_dir.mkdir()
        reset_summary["actions"].append(f"Cleared {cache_count} cache files")
    
    # Reset telemetry (keep logs directory but clear telemetry files)
    logs_dir = instance_path / "logs"
    if logs_dir.exists():
        telemetry_files = list(logs_dir.glob("*.jsonl")) + list(logs_dir.glob("telemetry*"))
        for tf in telemetry_files:
            tf.unlink()
        reset_summary["actions"].append(f"Cleared {len(telemetry_files)} telemetry files")
    
    return reset_summary


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Reset DataShark instance context")
    parser.add_argument("--instance", type=str, help="Instance name (default: active instance)")
    parser.add_argument("--system", type=str, help="Reset specific system (not implemented yet)")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    try:
        instance_path = get_instance_path(args.instance)
        result = reset_instance(instance_path, force=args.force)
        
        if result.get("cancelled"):
            return 1
        
        print(json.dumps(result, indent=2))
        print(f"✅ Instance reset complete: {instance_path}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

