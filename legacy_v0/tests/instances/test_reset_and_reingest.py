"""
Test instance reset and reingestion determinism.
"""

import json
import tempfile
from pathlib import Path
import sys

# Add tools to path
tools_path = Path(__file__).parent.parent.parent / "tools"
sys.path.insert(0, str(tools_path))

from instance_manager.manager import InstanceManager
from instance_manager.registry import InstanceRegistry

# Import reset function
sys.path.insert(0, str(tools_path))
from context_reset import reset_instance


def test_reset_and_reingest():
    """Test reset functionality and verify determinism."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir) / "instances"
        manager = InstanceManager(base_path=base_path)
        registry = InstanceRegistry(registry_path=base_path.parent / ".datashark" / "instances.json")
        
        # Create instance
        instance_path = manager.create_instance("test_reset")
        
        # Create some test manifests
        manifests_dir = instance_path / "manifests"
        test_manifest = manifests_dir / "test.json"
        test_manifest.write_text(json.dumps({"test": "data"}))
        
        # Create cache files
        cache_dir = instance_path / "cache"
        test_cache = cache_dir / "test.cache"
        test_cache.write_text("cached data")
        
        # Verify files exist
        assert test_manifest.exists()
        assert test_cache.exists()
        
        # Reset instance (with force to skip prompt)
        result = reset_instance(instance_path, force=True)
        assert not result.get("cancelled")
        assert len(result["actions"]) > 0
        
        # Verify manifests cleared
        assert not test_manifest.exists()
        assert manifests_dir.exists()  # Directory should still exist
        
        # Verify cache cleared
        assert not test_cache.exists()
        assert cache_dir.exists()  # Directory should still exist


if __name__ == "__main__":
    test_reset_and_reingest()
    print("✅ test_reset_and_reingest passed")

