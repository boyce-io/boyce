#!/usr/bin/env python3
"""
DataShark Engine – System Validation Suite

Entrypoint:
    python3 scripts/validate_all.py

Runs a unified set of validation checks:
    - Repo structure & hygiene
    - Snapshot / schema / manifest validation
    - CLI contract validation
    - MCP server smoke test
    - Pytest suite (and optional lint if configured)

Writes a detailed markdown report to:
    _management_documents/VALIDATE_ALL_REPORT.md
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


ROOT = Path(__file__).resolve().parent.parent
MCP_SRC = ROOT / "datashark-mcp" / "src"
REPORT_PATH = ROOT / "_management_documents" / "VALIDATE_ALL_REPORT.md"

# Ensure datashark_mcp package is importable
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from datashark_mcp.validation.repo_checks import run_repo_checks
from datashark_mcp.validation.graph_validation import validate_snapshot_dir
from datashark_mcp.validation.cli_validation import run_cli_validation
from datashark_mcp.validation.mcp_smoke import run_mcp_smoke


@dataclass
class SectionResult:
    name: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationSummary:
    sections: List[SectionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.sections)


def _python_env() -> Dict[str, str]:
    env = os.environ.copy()
    # Ensure datashark-mcp/src is on PYTHONPATH for subprocesses
    existing = env.get("PYTHONPATH")
    if existing:
        env["PYTHONPATH"] = f"{MCP_SRC}:{existing}"
    else:
        env["PYTHONPATH"] = str(MCP_SRC)
    return env


def _run_subprocess(args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_python_env(),
    )


def run_repo_structure_checks() -> SectionResult:
    result = run_repo_checks(ROOT)
    return SectionResult(
        name="Repo Structure Checks",
        passed=result.passed,
        details=result.to_dict(),
    )


def run_snapshot_e2e_and_schema_checks() -> SectionResult:
    """
    Validate an existing snapshot fixture directory against the schemas.

    This suite is a repo validation tool and should not depend on long-running
    server processes or external credentials. Snapshot generation is handled
    separately; here we only validate what's already present in-repo.
    """
    details: Dict[str, Any] = {"errors": []}
    passed = True

    # Locate latest looker snapshot
    looker_root = ROOT / "tests" / "fixtures" / "semantic" / "looker"
    snapshot_dirs: List[Path] = []
    if looker_root.exists():
        for p in looker_root.iterdir():
            if p.is_dir():
                snapshot_dirs.append(p)

    if not snapshot_dirs:
        passed = False
        details.setdefault("errors", []).append(
            "No snapshot directories found under tests/fixtures/semantic/looker/."
        )
        return SectionResult(
            name="Snapshot / Schema Validation",
            passed=passed,
            details=details,
        )

    latest = sorted(snapshot_dirs, key=lambda p: p.name)[-1]
    details["latest_snapshot"] = str(latest)

    # Validate snapshot directory using shared helper
    snap_result = validate_snapshot_dir(latest)
    details["snapshot_validation"] = {
        "passed": snap_result.passed,
        "nodes_valid": snap_result.nodes_valid,
        "edges_valid": snap_result.edges_valid,
        "manifest_valid": snap_result.manifest_valid,
        "errors": snap_result.errors,
    }

    if not snap_result.passed:
        passed = False

    return SectionResult(
        name="Snapshot / Schema Validation",
        passed=passed,
        details=details,
    )


def run_cli_contract_checks() -> SectionResult:
    result = run_cli_validation(ROOT)
    return SectionResult(
        name="CLI Contract Validation",
        passed=result.passed,
        details=result.to_dict(),
    )


def run_mcp_smoke_checks() -> SectionResult:
    result = run_mcp_smoke()
    return SectionResult(
        name="MCP Server Smoke Test",
        passed=result.passed,
        details=result.to_dict(),
    )


def run_tests_and_lint() -> SectionResult:
    python_exe = sys.executable or "python3"
    details: Dict[str, Any] = {"pytest": {}, "lint": {}}
    passed = True

    # Run pytest (entire suite)
    proc = _run_subprocess([python_exe, "-m", "pytest"], cwd=ROOT)
    if "No module named pytest" in (proc.stderr or ""):
        details["pytest"] = {
            "skipped": True,
            "reason": "pytest is not installed in this environment.",
            "returncode": proc.returncode,
            "stderr": proc.stderr,
        }
    else:
        details["pytest"] = {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        if proc.returncode != 0:
            passed = False

    # Basic lint: only if a known linter is available
    import shutil

    lint_cmd: Optional[List[str]] = None
    if shutil.which("ruff"):
        lint_cmd = ["ruff", "check", "datashark-mcp", "core"]
    elif shutil.which("flake8"):
        lint_cmd = ["flake8", "datashark-mcp", "core"]

    if lint_cmd is not None:
        lproc = _run_subprocess(lint_cmd, cwd=ROOT)
        details["lint"] = {
            "cmd": lint_cmd,
            "returncode": lproc.returncode,
            "stdout": lproc.stdout,
            "stderr": lproc.stderr,
        }
        if lproc.returncode != 0:
            passed = False
    else:
        details["lint"] = {
            "skipped": True,
            "reason": "No ruff or flake8 executable found in PATH.",
        }

    return SectionResult(
        name="Tests / Lint",
        passed=passed,
        details=details,
    )


def write_markdown_report(summary: ValidationSummary) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    overall_status = "PASS" if summary.passed else "FAIL"
    lines.append(f"# DataShark Engine – System Validation Suite\n")
    lines.append(f"**Overall Status:** `{overall_status}`\n")
    lines.append("")

    for section in summary.sections:
        status = "PASS" if section.passed else "FAIL"
        lines.append(f"## {section.name}\n")
        lines.append(f"- **Status:** `{status}`\n")

        details = section.details
        # Dump details in a readable way; keep it lightweight
        for key, value in details.items():
            lines.append(f"- **{key}**: `{repr(value)[:4000]}`")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    sections: List[SectionResult] = []

    sections.append(run_repo_structure_checks())
    sections.append(run_snapshot_e2e_and_schema_checks())
    sections.append(run_cli_contract_checks())
    sections.append(run_mcp_smoke_checks())
    sections.append(run_tests_and_lint())

    summary = ValidationSummary(sections=sections)
    write_markdown_report(summary)

    if summary.passed:
        print("All validation checks passed. See _management_documents/VALIDATE_ALL_REPORT.md for details.")
        return 0
    else:
        failed = [s for s in summary.sections if not s.passed]
        print(
            f"Validation failed: {len(failed)} of {len(summary.sections)} sections failed "
            f"(see _management_documents/VALIDATE_ALL_REPORT.md)."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


