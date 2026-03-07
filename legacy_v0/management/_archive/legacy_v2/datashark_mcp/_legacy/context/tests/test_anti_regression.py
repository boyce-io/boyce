"""
Anti-Regression Tests

Tests that no tool-specific vocabulary appears in core code.
"""

import pytest
import re
from pathlib import Path


def test_no_tool_names_in_code():
    """
    Test that core modules don't contain tool-specific names.
    
    Tool names should only appear in:
    - Test fixtures
    - Examples appendix (documentation)
    """
    project_root = Path(__file__).resolve().parents[4]
    context_dir = project_root / "datashark-mcp" / "src" / "datashark_mcp" / "context"
    
    # Tool names to check
    tool_names = ["looker", "dbt", "airflow", "tableau", "datahub"]
    
    # Files to check (exclude tests and __init__.py)
    core_files = [
        "models.py",
        "id_utils.py",
        "store.py",
        "merge.py",
        "manifest.py",
        "api.py",
        "security.py",
    ]
    
    violations = []
    
    for file_name in core_files:
        file_path = context_dir / file_name
        if not file_path.exists():
            continue
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")
            
            for line_num, line in enumerate(lines, 1):
                # Skip comments and docstrings in most cases, but check for tool names
                for tool_name in tool_names:
                    # Case-insensitive search
                    if re.search(rf"\b{tool_name}\b", line, re.IGNORECASE):
                        # Allow if it's in a test fixture or example
                        if "test" in line.lower() or "example" in line.lower() or "fixture" in line.lower():
                            continue
                        violations.append(f"{file_name}:{line_num}: {line.strip()}")
    
    if violations:
        pytest.fail(f"Tool names found in core code:\n" + "\n".join(violations))

