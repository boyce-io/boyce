"""
Test instance creation and listing.
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


def test_create_two_instances():
    """Create two instances and verify registry entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir) / "instances"
        manager = InstanceManager(base_path=base_path)
        registry = InstanceRegistry(registry_path=base_path.parent / ".datashark" / "instances.json")
        
        # Create first instance
        instance1_path = manager.create_instance("test_instance_1")
        assert instance1_path.exists()
        assert (instance1_path / "config.yaml").exists()
        assert (instance1_path / "credentials.env").exists()
        assert (instance1_path / ".datashark_version").exists()
        
        # Create second instance
        instance2_path = manager.create_instance("test_instance_2")
        assert instance2_path.exists()
        
        # Verify registry entries
        instances = registry.list_instances()
        assert "test_instance_1" in instances
        assert "test_instance_2" in instances
        assert instances["test_instance_1"]["path"] == str(instance1_path)
        assert instances["test_instance_2"]["path"] == str(instance2_path)
        
        # Verify directory structure
        for instance_name in ["test_instance_1", "test_instance_2"]:
            instance_info = registry.get_instance(instance_name)
            instance_path = Path(instance_info["path"])
            assert (instance_path / "manifests").exists()
            assert (instance_path / "cache").exists()
            assert (instance_path / "logs").exists()


if __name__ == "__main__":
    test_create_two_instances()
    print("✅ test_create_two_instances passed")

