#!/usr/bin/env python3
"""
Generate API Documentation

Uses pdoc to generate API documentation for the context module.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Generate API docs."""
    project_root = Path(__file__).resolve().parents[1]
    context_module = project_root / "datashark-mcp" / "src" / "datashark_mcp" / "context"
    # Generated artifacts should live under cursor_workspace/, not in canonical documentation paths.
    output_dir = project_root / "cursor_workspace" / "docs" / "api"
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Try to use pdoc
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pdoc",
                "--html",
                "--output-dir", str(output_dir),
                "--force",
                str(context_module)
            ],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Warning: pdoc failed: {result.stderr}", file=sys.stderr)
            print("Install pdoc with: pip install pdoc3", file=sys.stderr)
            return 1
        
        print(f"API docs generated in {output_dir}", file=sys.stderr)
        return 0
    except FileNotFoundError:
        print("Error: pdoc not found. Install with: pip install pdoc3", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

