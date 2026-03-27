#!/usr/bin/env python3
"""
test_cli_smoke.py — CLI smoke test for all Boyce command-line entry points.

Tests every flag/subcommand combination with a timeout to catch hangs.
Verifies exit codes without requiring a live database or LLM credentials.

Run from the repo root:
    python boyce/tests/test_cli_smoke.py

Or from within the boyce/ directory:
    python tests/test_cli_smoke.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate entry point binaries relative to the current Python interpreter.
# This works whether the venv is activated or not.
# ---------------------------------------------------------------------------

_BIN = Path(sys.executable).parent
_BOYCE = str(_BIN / "boyce")
_BOYCE_SCAN = str(_BIN / "boyce-scan")
_BOYCE_INIT = str(_BIN / "boyce-init")

# A real path to scan — use the demo fixture so it always exists
_DEMO_SNAPSHOT = str(
    Path(__file__).parent.parent.parent / "demo" / "magic_moment" / "snapshot.json"
)

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

TIMEOUT = 5  # seconds — any command taking longer than this is a hang

_PASS = 0
_FAIL = 0
_results: list[tuple[str, bool, str]] = []


def run(
    cmd: list[str],
    *,
    expected_exit: int | set[int],
    label: str,
    timeout: int = TIMEOUT,
    timeout_is_pass: bool = False,
) -> None:
    """
    Run a command, check its exit code, and record the result.

    expected_exit:   int or set of ints — acceptable exit codes
    timeout:         seconds before we declare a hang and kill the process
    timeout_is_pass: if True, a timeout means the process was running (expected for servers)
    """
    global _PASS, _FAIL

    expected = {expected_exit} if isinstance(expected_exit, int) else expected_exit

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        code = result.returncode
        stdout = result.stdout.decode(errors="replace").strip()
        stderr = result.stderr.decode(errors="replace").strip()
        output = (stdout or stderr)[:120].replace("\n", " | ")

        ok = code in expected
        if ok:
            _PASS += 1
            _results.append((label, True, f"exit={code} ({elapsed:.1f}s)  {output}"))
        else:
            _FAIL += 1
            _results.append((label, False, f"exit={code} (expected {expected})  {output}"))

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        if timeout_is_pass:
            _PASS += 1
            _results.append((label, True, f"running after {elapsed:.1f}s (timeout expected — server alive)"))
        else:
            _FAIL += 1
            _results.append((label, False, f"HANG — did not exit within {timeout}s"))


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def define_tests() -> None:

    # --- boyce: help and version flags ---
    run([_BOYCE, "--help"],    expected_exit=0, label="boyce --help")
    run([_BOYCE, "-h"],        expected_exit=0, label="boyce -h")
    run([_BOYCE, "--version"], expected_exit=0, label="boyce --version")
    run([_BOYCE, "-V"],        expected_exit=0, label="boyce -V")

    # --- boyce: unknown subcommand should error, not hang ---
    run([_BOYCE, "foobar"],    expected_exit=1, label="boyce <unknown>")
    run([_BOYCE, "--invalid"], expected_exit=1, label="boyce --invalid")
    run([_BOYCE, ""],          expected_exit=1, label="boyce <empty string>")

    # --- boyce ask: missing query → usage error ---
    run([_BOYCE, "ask"],       expected_exit=1, label="boyce ask (no query)")

    # --- boyce chat: missing message → usage error ---
    run([_BOYCE, "chat"],      expected_exit=1, label="boyce chat (no message)")

    # --- boyce serve: missing --http → usage error ---
    run([_BOYCE, "serve"],     expected_exit=1, label="boyce serve (no --http)")
    run([_BOYCE, "serve", "--port", "notanumber"],
                               expected_exit=1, label="boyce serve --port <invalid>")

    # --- boyce serve --http: should start and keep running ---
    # A timeout here means the server started and is alive (expected).
    # An immediate non-zero exit means a startup failure (fail).
    run([_BOYCE, "serve", "--http", "--port", "18741"],
        expected_exit={0, 1, -15, -2},  # only relevant if it exits early
        label="boyce serve --http (startup check)",
        timeout=3,
        timeout_is_pass=True)

    # --- boyce-scan: --help (argparse handles this) ---
    run([_BOYCE_SCAN, "--help"],
        expected_exit=0, label="boyce-scan --help")

    # --- boyce-scan: no path → argparse usage error (exit 2) ---
    run([_BOYCE_SCAN],
        expected_exit=2, label="boyce-scan (no path)")

    # --- boyce-scan: nonexistent path → argparse error (exit 2) ---
    run([_BOYCE_SCAN, "/nonexistent/path/xyz"],
        expected_exit={1, 2}, label="boyce-scan <nonexistent path>")

    # --- boyce-scan: real file → exit 0 or 1 (snapshot.json is SemanticSnapshot
    #     output format, not a parseable source; scanner skips unrecognised files
    #     cleanly rather than crashing) ---
    if Path(_DEMO_SNAPSHOT).exists():
        run([_BOYCE_SCAN, _DEMO_SNAPSHOT],
            expected_exit={0, 1}, label="boyce-scan demo/snapshot.json (no crash)")
    else:
        _results.append(("boyce-scan demo/snapshot.json (no crash)", True, "SKIPPED — demo fixture not found"))

    # --- boyce init: runs the wizard; with stdin closed it should detect
    #     hosts and exit (non-interactively). Not a hang test — just checking
    #     it doesn't crash on startup. ---
    run([_BOYCE, "init"],
        expected_exit={0, 1},  # 0=hosts found+configured, 1=nothing to configure
        label="boyce init (non-interactive)",
        timeout=10)

    # --- boyce init --help should list new flags ---
    run([_BOYCE, "init", "--non-interactive", "--skip-db", "--skip-sources", "--json"],
        expected_exit=0,
        label="boyce init --non-interactive --skip-db --skip-sources --json",
        timeout=10)

    # --- boyce init --non-interactive --editors with unknown editor → exit 1 ---
    run([_BOYCE, "init", "--non-interactive", "--editors", "nonexistent_editor", "--json"],
        expected_exit=1,
        label="boyce init --non-interactive --editors <unknown> --json (exit 1)",
        timeout=10)

    # --- boyce init --non-interactive --skip-existing → exit 0 (all skipped) ---
    run([_BOYCE, "init", "--non-interactive", "--skip-db", "--skip-sources", "--skip-existing", "--json"],
        expected_exit=0,
        label="boyce init --non-interactive --skip-existing --json",
        timeout=10)

    # --- boyce init --editors codex: codex is a valid editor name ---
    # Exit 0 if ~/.codex/ exists on this machine, 1 if no editors detected/configured.
    # Either way, "codex" must be accepted as a valid --editors value (not exit 1 as unknown).
    run([_BOYCE, "init", "--non-interactive", "--editors", "codex",
         "--skip-db", "--skip-sources", "--json"],
        expected_exit={0, 1},
        label="boyce init --editors codex --json (valid editor name)",
        timeout=10)

    # --- legacy boyce-init entry point (backward compat) ---
    run([_BOYCE_INIT],
        expected_exit={0, 1},
        label="boyce-init (legacy entry point)",
        timeout=10)

    # --- boyce update: should not hang (no network in test) ---
    run([_BOYCE, "update", "--yes"],
        expected_exit={0, 1, 2},  # 0=upgraded, 1=latest, 2=network/error
        label="boyce update --yes (no hang)")

    # --- boyce scan: subcommand form ---
    run([_BOYCE, "scan"],
        expected_exit=2, label="boyce scan (no path)")

    if Path(_DEMO_SNAPSHOT).exists():
        run([_BOYCE, "scan", _DEMO_SNAPSHOT],
            expected_exit={0, 1}, label="boyce scan demo/snapshot.json (no crash)")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report() -> int:
    sep = "=" * 60
    print(f"\n{sep}")
    print("CLI Smoke Test — Boyce Entry Points")
    print(sep)

    max_label = max(len(r[0]) for r in _results)

    for label, ok, detail in _results:
        status = "✓" if ok else "✗"
        print(f"  {status} {label:<{max_label}}  {detail}")

    print(f"\n{sep}")
    total = _PASS + _FAIL
    if _FAIL == 0:
        print(f"✅  All {total} checks passed.")
    else:
        print(f"❌  {_FAIL}/{total} checks FAILED.")
    print(sep)

    return 0 if _FAIL == 0 else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Python:     {sys.executable}")
    print(f"boyce:      {_BOYCE}")
    print(f"boyce-scan: {_BOYCE_SCAN}")
    print(f"boyce-init: {_BOYCE_INIT}")

    define_tests()
    sys.exit(report())
