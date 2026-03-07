"""
Scan CLI — walk a file or directory tree and extract SemanticSnapshots.

Usage:
    boyce-scan <path> [--output out.json] [--verbose] [--save]

Stdout = clean JSON (pipeable to jq).
Stderr = progress (only with --verbose).
Exit codes: 0 = success, 1 = nothing parseable found, 2 = fatal error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from .parsers.registry import get_default_registry
from .validation import validate_snapshot

# Directories to skip during recursive walk
_SKIP_DIRS: Set[str] = {
    ".git", ".svn", ".hg",
    ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", ".tox", ".eggs",
    "_local_context",
}

# Max file size to attempt parsing (10 MB)
_MAX_FILE_SIZE: int = 10 * 1024 * 1024


def scan_path(target: Path, verbose: bool = False) -> Dict[str, Any]:
    """
    Walk *target* (single file or directory tree) and parse every recognisable
    source into a SemanticSnapshot.

    Args:
        target:  File or directory to scan.
        verbose: If True, print per-file progress to stderr.

    Returns:
        Summary dict with counts, per-source details, and failures.
    """
    registry = get_default_registry()

    sources: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    scanned = 0
    skipped = 0

    files = _collect_files(target)

    for file_path in sorted(files):
        scanned += 1

        # Size guard
        try:
            if file_path.stat().st_size > _MAX_FILE_SIZE:
                skipped += 1
                if verbose:
                    print(f"  SKIP (>10 MB) {file_path}", file=sys.stderr)
                continue
        except OSError:
            skipped += 1
            continue

        candidates = registry.detect(file_path)
        if not candidates:
            skipped += 1
            continue

        parser, confidence = candidates[0]
        parser_name = parser.source_type()

        if verbose:
            print(f"  PARSE [{parser_name}] {file_path}", file=sys.stderr)

        try:
            snapshot = parser.parse(file_path)
            snap_dict = snapshot.model_dump(mode="json")
            errors = validate_snapshot(snap_dict)

            sources.append({
                "path": str(file_path),
                "parser": parser_name,
                "entities": len(snapshot.entities),
                "fields": len(snapshot.fields),
                "joins": len(snapshot.joins),
                "validation_errors": errors,
                "snapshot_id": snapshot.snapshot_id,
            })
        except Exception as exc:
            failures.append({
                "path": str(file_path),
                "parser": parser_name,
                "error": str(exc),
            })

    entities_total = sum(s["entities"] for s in sources)
    fields_total = sum(s["fields"] for s in sources)
    joins_total = sum(s["joins"] for s in sources)

    return {
        "scanned": scanned,
        "parsed": len(sources),
        "failed": len(failures),
        "skipped": skipped,
        "entities_total": entities_total,
        "fields_total": fields_total,
        "joins_total": joins_total,
        "sources": sources,
        "failures": failures,
    }


def _collect_files(target: Path) -> List[Path]:
    """Return list of files under *target*, skipping hidden/build dirs."""
    if target.is_file():
        return [target]

    files: List[Path] = []
    for item in sorted(target.rglob("*")):
        # Skip items inside excluded directories
        if any(part in _SKIP_DIRS or part.startswith(".") for part in item.parts):
            continue
        if item.is_file():
            files.append(item)
    return files


def _save_snapshots(result: Dict[str, Any], target: Path) -> int:
    """Persist parsed snapshots to _local_context/ via SnapshotStore. Returns count saved."""
    from .store import SnapshotStore

    store = SnapshotStore(Path("_local_context"))
    saved = 0

    registry = get_default_registry()
    for source_info in result["sources"]:
        if source_info["validation_errors"]:
            continue
        file_path = Path(source_info["path"])
        try:
            snapshot = registry.parse(file_path)
            name = file_path.stem
            store.save(snapshot, name)
            saved += 1
        except Exception:
            pass
    return saved


def main() -> None:
    """CLI entry point for boyce-scan."""
    parser = argparse.ArgumentParser(
        prog="boyce-scan",
        description="Scan files and directories for parseable data schemas.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="File or directory to scan",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Write JSON result to file (default: stdout)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-file progress to stderr",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist each valid snapshot to _local_context/ via SnapshotStore",
    )
    args = parser.parse_args()

    target: Path = args.path.resolve()

    if not target.exists():
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        sys.exit(2)

    if verbose := args.verbose:
        print(f"Scanning {target} ...", file=sys.stderr)

    try:
        result = scan_path(target, verbose=verbose)
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.save and result["parsed"] > 0:
        saved = _save_snapshots(result, target)
        if verbose:
            print(f"Saved {saved} snapshot(s) to _local_context/", file=sys.stderr)

    output_json = json.dumps(result, indent=2)

    if args.output:
        args.output.write_text(output_json, encoding="utf-8")
        if verbose:
            print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output_json)

    if result["parsed"] == 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
