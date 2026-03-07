"""
Test instance upgrade and destruction.
"""

import tempfile
from pathlib import Path
import sys

# Add tools to path
tools_path = Path(__file__).parent.parent.parent / "tools"
sys.path.insert(0, str(tools_path))

from instance_manager.manager import InstanceManager
from instance_manager.registry import InstanceRegistry


def test_upgrade_and_destroy():
    """Test version upgrade and instance destruction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir) / "instances"
        manager = InstanceManager(base_path=base_path)
        registry = InstanceRegistry(registry_path=base_path.parent / ".datashark" / "instances.json")
        
        # Create instance
        instance_path = manager.create_instance("test_upgrade")
        
        # Verify initial version
        version_file = instance_path / ".datashark_version"
        initial_version = version_file.read_text().strip()
        assert initial_version == "0.2.0"
        
        # Simulate version bump (upgrade to same version should be idempotent)
        result = manager.upgrade_instance("test_upgrade", target_version="0.2.0")
        assert result["current_version"] == "0.2.0"
        assert result["target_version"] == "0.2.0"
        
        # Upgrade to new version
        result = manager.upgrade_instance("test_upgrade", target_version="0.3.0")
        assert result["upgraded"] is True
        assert result["target_version"] == "0.3.0"
        
        # Verify version file updated
        new_version = version_file.read_text().strip()
        assert new_version == "0.3.0"
        
        # Verify registry updated
        instance_info = registry.get_instance("test_upgrade")
        assert instance_info["version"] == "0.3.0"
        
        # Destroy instance
        manager.destroy_instance("test_upgrade")
        
        # Verify removed from registry
        assert registry.get_instance("test_upgrade") is None
        
        # Verify directory removed
        assert not instance_path.exists()


if __name__ == "__main__":
    test_upgrade_and_destroy()
    print("✅ test_upgrade_and_destroy passed")

