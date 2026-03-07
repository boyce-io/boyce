"""
Schema Loading Utility

Provides robust schema path resolution with multiple fallback strategies.
Includes schema caching to prevent I/O delays during repeated validations.
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from importlib import resources

# Schema cache to prevent repeated I/O
_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def get_schema_path(name: str) -> Path:
    """
    Get the path to a schema file with robust project root detection.
    
    Args:
        name: Schema file name (e.g., "graph_schema.json", "manifest_schema.json")
    
    Returns:
        Path to the schema file
    
    Raises:
        FileNotFoundError: If schema file cannot be found
    """
    # Strategy 1: Environment variable (highest priority)
    schema_dir = os.getenv("DATASHARK_SCHEMA_DIR")
    if schema_dir:
        schema_path = Path(schema_dir) / name
        if schema_path.exists():
            return schema_path
    
    # Strategy 2: Find project root docs/ first (preferred location)
    # Walk up from this file to find project root with docs/
    current = Path(__file__).resolve()
    max_depth = 10
    depth = 0
    
    while current != current.parent and depth < max_depth:
        # Check for docs/graph_schema.json in this directory (project root)
        schema_path = current / "docs" / name
        if schema_path.exists() and schema_path.is_file():
            return schema_path
        current = current.parent
        depth += 1
    
    # Strategy 3: Try git rev-parse --show-toplevel
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent
        )
        if result.returncode == 0:
            git_root = Path(result.stdout.strip())
            schema_path = git_root / "docs" / name
            if schema_path.exists():
                return schema_path
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    # Strategy 5: Last resort - relative to this file (parents[4] for context/models.py)
    # This is the original approach but more robust
    context_dir = Path(__file__).parent
    # Try going up from context/ to project root
    project_candidates = [
        context_dir.parent.parent.parent.parent,  # datashark-mcp/src/datashark_mcp/context -> project root
        context_dir.parent.parent.parent.parent.parent,  # Alternative path
    ]
    
    for project_root in project_candidates:
        schema_path = project_root / "docs" / name
        if schema_path.exists():
            return schema_path
    
    # If all strategies fail, raise with helpful error
    error_msg = (
        f"Schema file '{name}' not found. Tried:\n"
        f"  1. DATASHARK_SCHEMA_DIR environment variable\n"
        f"  2. Walking up from {Path(__file__).parent} looking for docs/{name}\n"
        f"  3. Git root + docs/{name}\n"
        f"  4. Relative paths from context module\n"
        f"\nPlease set DATASHARK_SCHEMA_DIR or ensure docs/{name} exists in project root."
    )
    raise FileNotFoundError(error_msg)


def load_graph_schema() -> Dict[str, Any]:
    """
    Load graph_schema.json with robust path resolution and caching.
    
    Returns:
        Parsed JSON schema as dictionary
    
    Raises:
        FileNotFoundError: If schema file cannot be found
        json.JSONDecodeError: If schema file is invalid JSON
    """
    # Check cache first
    if "graph_schema" in _SCHEMA_CACHE:
        return _SCHEMA_CACHE["graph_schema"]
    
    schema = None
    
    # Try importlib.resources first (for packaged schemas)
    try:
        from importlib import resources
        schema_package = resources.files("datashark_mcp.schemas")
        schema_file = schema_package / "graph_schema.json"
        if schema_file.is_file():
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
    except (ImportError, ModuleNotFoundError, AttributeError, FileNotFoundError):
        pass
    
    # Fallback to file path resolution
    if schema is None:
        schema_path = get_schema_path("graph_schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    
    # Cache the schema
    _SCHEMA_CACHE["graph_schema"] = schema
    return schema


def load_manifest_schema() -> Dict[str, Any]:
    """
    Load manifest_schema.json with robust path resolution and caching.
    
    Returns:
        Parsed JSON schema as dictionary
    
    Raises:
        FileNotFoundError: If schema file cannot be found
        json.JSONDecodeError: If schema file is invalid JSON
    """
    # Check cache first
    if "manifest_schema" in _SCHEMA_CACHE:
        return _SCHEMA_CACHE["manifest_schema"]
    
    schema = None
    
    # Try importlib.resources first (for packaged schemas)
    try:
        from importlib import resources
        schema_package = resources.files("datashark_mcp.schemas")
        schema_file = schema_package / "manifest_schema.json"
        if schema_file.is_file():
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
    except (ImportError, ModuleNotFoundError, AttributeError, FileNotFoundError):
        pass
    
    # Fallback to file path resolution
    if schema is None:
        schema_path = get_schema_path("manifest_schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    
    # Cache the schema
    _SCHEMA_CACHE["manifest_schema"] = schema
    return schema


def get_schema_root() -> Path:
    """
    Get the directory containing schema files.
    
    Returns:
        Path to docs/ directory containing schemas
    
    Raises:
        FileNotFoundError: If schema directory cannot be found
    """
    schema_path = get_schema_path("graph_schema.json")
    return schema_path.parent

