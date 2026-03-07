#!/usr/bin/env python3
"""
DataShark Stealth Installation Script

This script performs "hot-wire" injection of the DataShark MCP server
into Cursor's configuration without creating a separate installation.

Target: Corporate/Enterprise environments where traditional installation
is restricted.

Behavior:
- Detects Cursor config location
- Registers current repo path directly into Cursor's config.json
- Relies on user's local Python environment
- Remains invisible to "Add/Remove Programs" or "Extensions" lists
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


def find_cursor_config() -> Path:
    """
    Find Cursor's configuration directory.
    
    Returns:
        Path to Cursor config directory
        
    Raises:
        FileNotFoundError: If Cursor config cannot be found
    """
    # Cursor config is typically at:
    # macOS: ~/Library/Application Support/Cursor/User/globalStorage/
    # Linux: ~/.config/Cursor/User/globalStorage/
    # Windows: %APPDATA%/Cursor/User/globalStorage/
    
    if sys.platform == "darwin":
        config_base = Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage"
    elif sys.platform.startswith("linux"):
        config_base = Path.home() / ".config" / "Cursor" / "User" / "globalStorage"
    elif sys.platform == "win32":
        config_base = Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "globalStorage"
    else:
        raise FileNotFoundError(f"Unsupported platform: {sys.platform}")
    
    if not config_base.exists():
        raise FileNotFoundError(f"Cursor config directory not found at: {config_base}")
    
    return config_base


def get_repo_path() -> Path:
    """
    Get the current repository path (where this script is located).
    
    Returns:
        Path to repository root
    """
    # This script is at: <repo>/distribution/stealth/install_stealth.py
    # So we need to go up 3 levels: stealth -> distribution -> repo_root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent.parent
    return repo_root


def inject_mcp_server(config_dir: Path, repo_path: Path, test_mode: bool = False) -> None:
    """
    Inject MCP server configuration into Cursor's config.
    
    Args:
        config_dir: Cursor config directory
        repo_path: Repository root path
        test_mode: If True, use test config file instead of real Cursor config
        
    Raises:
        ValueError: If written config is invalid JSON
        FileNotFoundError: If mcp_server.py not found
    """
    # MCP config file location
    if test_mode:
        mcp_config_file = config_dir / "fake_config.json"
    else:
        mcp_config_file = config_dir / "mcp.json"
    
    # MCP server entrypoint path
    # After Enterprise Refactor: server is at <repo>/src/datashark/mcp_server.py
    # This script is at: <repo>/distribution/stealth/install_stealth.py
    # Relative path: ../../src/datashark/mcp_server.py
    script_dir = Path(__file__).resolve().parent
    mcp_server_path = script_dir / ".." / ".." / "src" / "datashark" / "mcp_server.py"
    mcp_server_path = mcp_server_path.resolve()
    
    # Safety check: Verify the server path exists
    if not mcp_server_path.exists():
        raise FileNotFoundError(
            f"MCP server not found at expected path: {mcp_server_path}\n"
            f"Repository root: {repo_path}\n"
            f"Script location: {script_dir}\n"
            f"Please ensure the Enterprise Refactor was completed correctly."
        )
    
    # Step 1: Backup existing config if it exists
    if mcp_config_file.exists():
        backup_file = mcp_config_file.with_suffix(".json.bak")
        import shutil
        shutil.copy2(mcp_config_file, backup_file)
        print(f"✅ Created backup: {backup_file}")
    
    # Step 2: Load existing MCP config or create new
    if mcp_config_file.exists():
        try:
            with open(mcp_config_file, "r") as f:
                mcp_config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Existing config file is invalid JSON: {e}")
    else:
        mcp_config = {}
    
    # Step 3: Idempotency - Check if datashark server already exists
    if "mcpServers" not in mcp_config:
        mcp_config["mcpServers"] = {}
    
    existing_server = mcp_config["mcpServers"].get("datashark")
    new_server_config = {
        "command": sys.executable,
        "args": [str(mcp_server_path)],
        "env": {
            "PYTHONPATH": str(repo_path / "src")
        }
    }
    
    # Step 4: Update if path changed, or add if new
    if existing_server:
        # Check if path changed
        existing_path = existing_server.get("args", [None])[0] if existing_server.get("args") else None
        new_path = str(mcp_server_path)
        
        if existing_path != new_path:
            print(f"⚠️  Updating existing DataShark server path")
            print(f"   Old: {existing_path}")
            print(f"   New: {new_path}")
            mcp_config["mcpServers"]["datashark"] = new_server_config
        else:
            print(f"✅ DataShark server already registered (path unchanged)")
            return  # No changes needed
    else:
        # Add new server
        mcp_config["mcpServers"]["datashark"] = new_server_config
    
    # Step 5: Write updated config
    mcp_config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(mcp_config_file, "w") as f:
        json.dump(mcp_config, f, indent=2)
    
    # Step 6: Validation - Ensure written file is valid JSON
    try:
        with open(mcp_config_file, "r") as f:
            json.load(f)  # Validate JSON
    except json.JSONDecodeError as e:
        # Restore backup if validation fails
        if mcp_config_file.with_suffix(".json.bak").exists():
            import shutil
            shutil.copy2(mcp_config_file.with_suffix(".json.bak"), mcp_config_file)
            raise ValueError(f"Written config is invalid JSON. Backup restored. Error: {e}")
        else:
            raise ValueError(f"Written config is invalid JSON: {e}")
    
    print(f"✅ Injected DataShark MCP server into Cursor config")
    print(f"   Config file: {mcp_config_file}")
    print(f"   Server path: {mcp_server_path}")


def main(test_config_dir: Optional[Path] = None):
    """
    Main installation routine.
    
    Args:
        test_config_dir: Optional test config directory (for testing)
    """
    print("=" * 80)
    print("DataShark Stealth Installation")
    print("=" * 80)
    print()
    print("Detecting Cursor config...")
    
    try:
        if test_config_dir:
            config_dir = test_config_dir
            print(f"✅ Using test config directory: {config_dir}")
        else:
            config_dir = find_cursor_config()
            print(f"✅ Found Cursor config at: {config_dir}")
        
        repo_path = get_repo_path()
        print(f"✅ Repository path: {repo_path}")
        
        print()
        print("Injecting MCP server...")
        inject_mcp_server(config_dir, repo_path, test_mode=(test_config_dir is not None))
        
        print()
        print("=" * 80)
        print("✅ Installation complete!")
        print("=" * 80)
        print()
        if not test_config_dir:
            print("DataShark is now registered with Cursor.")
            print("Restart Cursor to activate the MCP server.")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
