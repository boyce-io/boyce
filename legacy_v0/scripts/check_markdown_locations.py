#!/usr/bin/env python3
"""
Fail-fast guardrail: ensure repo markdown docs only live in canonical locations.

Canonical markdown locations:
  - project/
  - _management_documents/

Allowed exception:
  - README.md (repo root)

Ignored directories (non-project/vendor/build artifacts):
  - **/node_modules/**
  - **/dist/**
  - **/build/**
  - **/out/**
"""

from __future__ import annotations

from pathlib import Path
import sys


CANON_PREFIXES = ("project/", "_management_documents/")
ALLOWED_FILES = {"README.md"}
IGNORE_PARTS = {"node_modules", "dist", "build", "out", ".git", "__pycache__"}


def is_ignored(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    md_files = sorted([p for p in repo_root.rglob("*.md") if p.is_file()])

    stray: list[str] = []
    for p in md_files:
        rel = p.relative_to(repo_root)
        rel_str = rel.as_posix()

        if is_ignored(rel):
            continue
        if rel_str in ALLOWED_FILES:
            continue
        if rel_str.startswith(CANON_PREFIXES):
            continue

        stray.append(rel_str)

    if not stray:
        print("OK: No stray markdown files found outside canonical locations.")
        return 0

    print("ERROR: Stray markdown files found outside canonical locations:")
    for s in stray:
        print(f"- {s}")
    print("")
    print("Canonical markdown locations are restricted to: project/ and _management_documents/")
    print("Allowed exception: README.md at repo root")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


