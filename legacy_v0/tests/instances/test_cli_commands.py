"""
Test CLI commands end-to-end.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
import sys


def test_cli_create_list():
    """Test create and list CLI commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set environment for test
        env = os.environ.copy()
        env["DATASHARK_TEST_INSTANCES_DIR"] = str(Path(tmpdir) / "instances")
        
        # Create instance via CLI
        result = subprocess.run(
            [sys.executable, "-m", "tools.instance_manager.cli", "create", "test_cli_instance"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
            env=env
        )
        
        # Should succeed (exit code 0)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # List instances
        result = subprocess.run(
            [sys.executable, "-m", "tools.instance_manager.cli", "list"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
            env=env
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "instances" in output
        assert "test_cli_instance" in output["instances"]


def test_cli_switch():
    """Test switch CLI command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["DATASHARK_TEST_INSTANCES_DIR"] = str(Path(tmpdir) / "instances")
        
        # Create and switch
        subprocess.run(
            [sys.executable, "-m", "tools.instance_manager.cli", "create", "test_switch_cli"],
            capture_output=True,
            cwd=Path(__file__).parent.parent.parent,
            env=env
        )
        
        result = subprocess.run(
            [sys.executable, "-m", "tools.instance_manager.cli", "switch", "test_switch_cli"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
            env=env
        )
        
        assert result.returncode == 0


def test_cli_destroy():
    """Test destroy CLI command."""
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["DATASHARK_TEST_INSTANCES_DIR"] = str(Path(tmpdir) / "instances")
        
        # Create instance
        subprocess.run(
            [sys.executable, "-m", "tools.instance_manager.cli", "create", "test_destroy_cli"],
            capture_output=True,
            cwd=Path(__file__).parent.parent.parent,
            env=env
        )
        
        # Destroy instance
        result = subprocess.run(
            [sys.executable, "-m", "tools.instance_manager.cli", "destroy", "test_destroy_cli"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
            env=env
        )
        
        assert result.returncode == 0


if __name__ == "__main__":
    import os
    test_cli_create_list()
    print("✅ test_cli_create_list passed")
    
    test_cli_switch()
    print("✅ test_cli_switch passed")
    
    test_cli_destroy()
    print("✅ test_cli_destroy passed")

