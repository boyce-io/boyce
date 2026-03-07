"""
Test instance switching and building.
"""

import tempfile
from pathlib import Path
import sys

# Add tools to path
tools_path = Path(__file__).parent.parent.parent / "tools"
sys.path.insert(0, str(tools_path))

from instance_manager.manager import InstanceManager
from instance_manager.registry import InstanceRegistry


def test_switch_and_build():
    """Switch active instance and run build."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir) / "instances"
        manager = InstanceManager(base_path=base_path)
        registry = InstanceRegistry(registry_path=base_path.parent / ".datashark" / "instances.json")
        
        # Create instance
        manager.create_instance("test_switch")
        
        # Switch to instance
        manager.switch_instance("test_switch")
        
        # Verify active instance
        active = registry.get_active_instance()
        assert active is not None
        assert active["path"].endswith("test_switch")
        
        # Verify registry.active
        registry_data = registry.load_registry()
        assert registry_data["active"] == "test_switch"
        
        # Run build (placeholder - actual build would run ingestion)
        result = manager.build_instance("test_switch")
        assert result["instance"] == "test_switch"
        assert "path" in result
        
        # Verify manifests directory exists (even if empty)
        instance_path = Path(active["path"])
        assert (instance_path / "manifests").exists()


if __name__ == "__main__":
    test_switch_and_build()
    print("✅ test_switch_and_build passed")

