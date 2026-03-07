#!/usr/bin/env python3
"""
Sweep stray Cursor artifacts into cursor_workspace/.

Behavior:
- Scans the repository root for markdown, JSON, TXT, and PY files that are not part
  of the production codebase and moves them into cursor_workspace/.
- Ignores:
  - README.md
  - requirements.txt
  - CURSOR_WORKSPACE_RULES.md
  - Anything already under cursor_workspace/
- Does not touch files inside production directories:
  - core/, datashark-mcp/, datashark-extension/, docs/, scripts/, tests/, tools/
"""

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CURSOR_WS = ROOT / "cursor_workspace"


def is_production_dir(name: str) -> bool:
    return name in {
        "core",
        "datashark-mcp",
        "datashark-extension",
        "docs",
        "scripts",
        "tests",
        "tools",
        "_management_documents",
    }


def main() -> None:
    CURSOR_WS.mkdir(parents=True, exist_ok=True)

    moved: list[tuple[Path, Path]] = []

    # Only inspect the repo root for stray files
    for item in ROOT.iterdir():
        if item.is_dir():
            # Skip production directories and cursor_workspace itself
            if is_production_dir(item.name) or item.name == "cursor_workspace":
                continue
            # Other directories at root are left alone (safety)
            continue

        if not item.is_file():
            continue

        # Skip explicitly allowed root files
        if item.name in {"README.md", "requirements.txt", "CURSOR_WORKSPACE_RULES.md"}:
            continue

        # Only move certain file types
        if item.suffix.lower() not in {".md", ".json", ".txt", ".py"}:
            continue

        dest = CURSOR_WS / item.name
        dest = dest.with_suffix(item.suffix)  # keep same suffix
        shutil.move(str(item), str(dest))
        moved.append((item, dest))

    # Log moves
    if moved:
        print("Moved the following files into cursor_workspace/:")
        for src, dst in moved:
            print(f"  {src.name} -> cursor_workspace/{dst.name}")
    else:
        print("No stray files to move; cursor_workspace is up to date.")


if __name__ == "__main__":
    main()


