from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class CheckResult:
    name: str
    passed: bool
    messages: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class RepoChecksResult:
    passed: bool
    checks: List[CheckResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "messages": c.messages,
                    "errors": c.errors,
                }
                for c in self.checks
            ],
        }


ALLOWED_DIRS = {
    "_management_documents",
    ".github",
    "config",
    "core",
    "data",
    "datashark-extension",
    "datashark-mcp",
    "docs",
    "scripts",
    "tests",
    "tools",
    "cursor_workspace",
}

ALLOWED_FILES = {
    ".env.example",
    ".gitignore",
    "README.md",
    "requirements.txt",
    "CURSOR_WORKSPACE_RULES.md",
}


def _check_root_contents(root: Path) -> CheckResult:
    result = CheckResult(name="root_contents", passed=True)

    for item in root.iterdir():
        name = item.name
        # Ignore VCS metadata and pycache
        if name in {".git", ".idea", ".vscode", "__pycache__"}:
            continue

        if item.is_dir():
            if name not in ALLOWED_DIRS:
                result.passed = False
                result.errors.append(f"Unexpected top-level directory: {name}")
        elif item.is_file():
            # Ignore common OS metadata files
            if name in {".DS_Store"}:
                continue
            if name not in ALLOWED_FILES and not name.startswith(".git"):
                result.passed = False
                result.errors.append(f"Unexpected top-level file: {name}")

    if result.passed:
        result.messages.append("Top-level repo contents are canonical.")
    return result


def _check_forbidden_dirs(root: Path) -> CheckResult:
    result = CheckResult(name="forbidden_directories", passed=True)
    forbidden = {".datashark", ".venv"}

    for path in root.rglob("*"):
        if path.is_dir() and path.name in forbidden:
            result.passed = False
            result.errors.append(f"Forbidden directory present: {path.relative_to(root)}")

    # Special case: .pytest_cache only forbidden at root
    root_pytest_cache = root / ".pytest_cache"
    if root_pytest_cache.exists():
        result.passed = False
        result.errors.append("Forbidden root directory present: .pytest_cache/")

    if result.passed:
        result.messages.append("No forbidden directories (.datashark/, .venv/, root .pytest_cache/) found.")
    return result


def _check_cursor_workspace_isolation(root: Path) -> CheckResult:
    result = CheckResult(name="cursor_workspace_isolation", passed=True)

    # Only allow specific files at root; everything else of these types must
    # live in cursor_workspace/ or inside production directories.
    for item in root.iterdir():
        if not item.is_file():
            continue
        if item.suffix.lower() not in {".md", ".txt", ".json", ".py"}:
            continue

        if item.name in {"README.md", "CURSOR_WORKSPACE_RULES.md", "requirements.txt"}:
            continue
        if item.name == "scripts/validate_all.py":
            # This will not appear as a file at root; kept here for clarity.
            continue

        # Any other matching file at root is a violation
        rel = item.relative_to(root)
        result.passed = False
        result.errors.append(f"Stray root-level artifact: {rel}")

    if result.passed:
        result.messages.append(
            "Root-level markdown/txt/json/py files are limited to README.md and CURSOR_WORKSPACE_RULES.md."
        )
    return result


def run_repo_checks(root: Path) -> RepoChecksResult:
    """
    Run repo structure and hygiene checks starting from the given root.
    """
    checks: List[CheckResult] = []

    checks.append(_check_root_contents(root))
    checks.append(_check_forbidden_dirs(root))
    checks.append(_check_cursor_workspace_isolation(root))

    passed = all(c.passed for c in checks)
    return RepoChecksResult(passed=passed, checks=checks)


