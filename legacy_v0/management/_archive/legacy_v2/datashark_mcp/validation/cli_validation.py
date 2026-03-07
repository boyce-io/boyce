from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any
import subprocess
import sys


@dataclass
class CLITestResult:
    name: str
    passed: bool
    messages: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class CLIValidationResult:
    passed: bool
    checks: List[CLITestResult] = field(default_factory=list)

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


def _run_cmd(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_cli_validation(root: Path) -> CLIValidationResult:
    """
    Validate CLI contracts for datashark-mcp/cli.py.
    """
    checks: List[CLITestResult] = []
    python_exe = sys.executable or "python3"
    cli_path = root / "datashark-mcp" / "cli.py"
    env = dict(**os.environ) if 'os' in globals() else None  # will be patched below

    # Ensure PYTHONPATH includes datashark-mcp/src
    mcp_src = root / "datashark-mcp" / "src"

    import os as _os
    os = _os  # keep reference local to avoid confusion
    env = os.environ.copy()
    env["PYTHONPATH"] = str(mcp_src)

    # 1. --help should succeed
    help_result = CLITestResult(name="cli_help", passed=True)
    proc = subprocess.run(
        [python_exe, str(cli_path), "-h"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        help_result.passed = False
        help_result.errors.append(f"--help failed with code {proc.returncode}: {proc.stderr.strip()}")
    else:
        help_result.messages.append("datashark-mcp/cli.py --help succeeded.")
    checks.append(help_result)

    # 2. reset/train/test must require --source
    for cmd in ["reset", "train", "test"]:
        name = f"{cmd}_requires_source"
        res = CLITestResult(name=name, passed=True)
        proc = subprocess.run(
            [python_exe, str(cli_path), cmd],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        if proc.returncode == 0:
            res.passed = False
            res.errors.append(f"{cmd} without --source unexpectedly succeeded.")
        else:
            stderr = (proc.stderr or "") + (proc.stdout or "")
            # Accept either our explicit message or argparse's required-arg message
            if "--source is required" in stderr or "the following arguments are required: --source" in stderr:
                res.messages.append(f"{cmd} correctly requires --source.")
            else:
                res.passed = False
                res.errors.append(
                    f"{cmd} without --source failed but error did not clearly mention missing --source. "
                    f"Stderr: {stderr.strip()}"
                )
        checks.append(res)

    # 3. Snapshot source correctness for arbitrary source name
    source_check = CLITestResult(name="train_with_custom_source_pathing", passed=True)
    custom_source = "foo"
    custom_root = root / "tests" / "fixtures" / "semantic" / custom_source

    # Clean any existing custom source snapshots
    if custom_root.exists():
        import shutil
        shutil.rmtree(custom_root)

    proc = subprocess.run(
        [
            python_exe,
            str(cli_path),
            "train",
            "--source",
            custom_source,
            "--sources",
            f"{custom_source}:tests/fixtures/minimal_looker_repo",
        ],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    if proc.returncode != 0:
        source_check.passed = False
        source_check.errors.append(
            f"train with custom --source failed (code {proc.returncode}): {proc.stderr.strip()}"
        )
    else:
        if not custom_root.exists():
            source_check.passed = False
            source_check.errors.append(
                f"Expected snapshots under tests/fixtures/semantic/{custom_source}/ but directory was not created."
            )
        else:
            source_check.messages.append(
                f"train with --source {custom_source} created snapshots under {custom_root}."
            )

    checks.append(source_check)

    passed = all(c.passed for c in checks)
    return CLIValidationResult(passed=passed, checks=checks)


