"""
Safe file editing utilities for the Architect Agent.

Provides minimal, controlled operations for creating files and applying
search/replace patches with workspace and backup safety guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileEditor:
    """
    Safe file editor bound to a workspace root.

    All operations:
    - Are restricted to paths under `workspace_root`
    - Create a `.bak` backup before modifying an existing file
    - Fail safely (return False or raise) on ambiguous patches
    """

    workspace_root: Path

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    # --------------- Internal helpers ---------------
    def _resolve_safe_path(self, file_path: str) -> Optional[Path]:
        """
        Resolve `file_path` against the workspace root and ensure it does
        not escape via `..` or symlinks.

        Returns the resolved Path if safe, or None if outside workspace.
        """
        candidate = (self.workspace_root / file_path).resolve()
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError:
            # Path is outside the workspace; reject.
            return None
        return candidate

    def _make_backup(self, target: Path) -> None:
        """
        Create a simple `.bak` backup (target.ext.bak) before modifications.
        Overwrites any existing backup.
        """
        if not target.exists():
            return
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_bytes(target.read_bytes())

    # --------------- Public API ---------------
    def apply_patch(self, file_path: str, search_block: str, replace_block: str) -> bool:
        """
        Apply a safe search/replace patch:

        - Only operates on files under `workspace_root`.
        - Creates a `.bak` backup first.
        - Replaces the *exact* `search_block` text with `replace_block`.
        - Returns:
            - True  -> exactly one occurrence replaced and file written
            - False -> `search_block` not found or found multiple times
        """
        safe_path = self._resolve_safe_path(file_path)
        if safe_path is None or not safe_path.is_file():
            return False

        original_text = safe_path.read_text(encoding="utf-8")
        count = original_text.count(search_block)

        if count != 1:
            # Ambiguous or missing; do nothing.
            return False

        # Backup before write
        self._make_backup(safe_path)

        updated_text = original_text.replace(search_block, replace_block)
        safe_path.write_text(updated_text, encoding="utf-8")
        return True

    def create_file(self, file_path: str, content: str) -> None:
        """
        Create a new file at `file_path` (under workspace_root) with `content`.

        - Ensures parent directories exist.
        - Overwrites existing file contents if the file already exists.
        """
        safe_path = self._resolve_safe_path(file_path)
        if safe_path is None:
            raise ValueError(f"Refusing to create file outside workspace: {file_path}")

        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")


def default_editor() -> FileEditor:
    """
    Convenience factory for a FileEditor rooted at the repository root
    (assumes this file lives in `src/agent/`).
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    return FileEditor(workspace_root=repo_root)

