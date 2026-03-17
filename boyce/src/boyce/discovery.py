"""
boyce discovery — auto-detect data source projects on the local filesystem.

Used by the setup wizard (boyce-init) to find dbt projects, LookML repos,
SQL schema collections, ORM models, and similar sources without the user
having to know file paths.

No external dependencies — stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Standard locations to search
# ---------------------------------------------------------------------------

SEARCH_ROOTS: List[Path] = [
    Path.home() / "repos",
    Path.home() / "projects",
    Path.home() / "code",
    Path.home() / "src",
    Path.home() / "work",
    Path.home() / "dev",
    Path.home() / "github",
    Path.home() / "git",
    Path.home() / "workspace",
]

# Directories to skip when walking
_SKIP_DIRS: Set[str] = {
    ".git", ".svn", ".hg",
    ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".tox",
    "node_modules", ".eggs", "dist", "build", "target",
    "_local_context", ".cache", ".npm", ".cargo",
    "Library", "Applications", "System",
}

# Human-readable labels per parser type
_PARSER_LABELS: Dict[str, str] = {
    "dbt": "dbt project",
    "dbt_manifest": "dbt (compiled manifest)",
    "lookml": "LookML / Looker",
    "ddl": "SQL / DDL",
    "prisma": "Prisma schema",
    "django": "Django models",
    "sqlalchemy": "SQLAlchemy models",
    "sqlite": "SQLite database",
    "csv": "CSV file",
    "parquet": "Parquet file",
}


# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------


@dataclass
class DiscoveredSource:
    """A data source project root found on the filesystem."""

    path: Path
    parser_type: str        # "dbt", "lookml", "ddl", etc.
    label: str              # Human-readable: "dbt project"
    confidence: float       # 0.0–1.0
    is_git_repo: bool
    pre_selected: bool      # True = recommended for ingestion
    description: str = ""   # Populated after ingestion: "47 views, 89 joins"
    entities: int = 0
    fields: int = 0
    joins: int = 0


# ---------------------------------------------------------------------------
# Discovery entry point
# ---------------------------------------------------------------------------


def discover_sources(
    search_roots: Optional[List[Path]] = None,
    max_depth: int = 3,
) -> List[DiscoveredSource]:
    """
    Walk search_roots looking for data source project roots.

    Only looks for project-level markers (fast — no content parsing).
    Returns list of DiscoveredSource sorted by confidence descending.

    Args:
        search_roots: Directories to search. Defaults to SEARCH_ROOTS.
        max_depth:    Max directory depth to recurse into.
    """
    if search_roots is None:
        search_roots = [r for r in SEARCH_ROOTS if r.exists() and r.is_dir()]

    found: List[DiscoveredSource] = []
    visited: Set[Path] = set()

    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        _walk(root, depth=0, max_depth=max_depth, found=found, visited=visited)

    # Deduplicate by resolved path
    seen: Set[Path] = set()
    deduped: List[DiscoveredSource] = []
    for src in found:
        try:
            rp = src.path.resolve()
        except OSError:
            rp = src.path
        if rp not in seen:
            seen.add(rp)
            deduped.append(src)

    return sorted(deduped, key=lambda s: (-s.confidence, not s.is_git_repo, str(s.path)))


# ---------------------------------------------------------------------------
# Ingestion (called after user selects sources)
# ---------------------------------------------------------------------------


def ingest_source(source: DiscoveredSource, name: Optional[str] = None) -> str:
    """
    Parse and save a discovered source to _local_context/.

    Args:
        source: The DiscoveredSource to ingest.
        name:   Snapshot name. Defaults to directory/file stem.

    Returns:
        Human-readable result string, e.g. "47 views, 89 joins".

    Raises:
        Exception: If parsing or saving fails.
    """
    from .parsers.detect import parse_from_path
    from .store import SnapshotStore

    if name is None:
        name = source.path.stem if source.path.is_file() else source.path.name

    snapshot = parse_from_path(source.path)
    store = SnapshotStore(Path("_local_context"))
    store.save(snapshot, name)

    # Build result description
    entities = len(snapshot.entities)
    fields = len(snapshot.fields)
    joins = len(snapshot.joins)

    if source.parser_type == "lookml":
        parts = [f"{entities} views"]
        if joins:
            parts.append(f"{joins} joins")
    elif source.parser_type in ("dbt", "dbt_manifest"):
        parts = [f"{entities} models"]
        if joins:
            parts.append(f"{joins} joins")
    elif source.parser_type == "ddl":
        parts = [f"{entities} tables"]
        if fields:
            parts.append(f"{fields} columns")
    else:
        parts = [f"{entities} tables"]
        if joins:
            parts.append(f"{joins} joins")

    return ", ".join(parts) if parts else "ingested"


# ---------------------------------------------------------------------------
# Internal walk
# ---------------------------------------------------------------------------


def _walk(
    dir_path: Path,
    depth: int,
    max_depth: int,
    found: List[DiscoveredSource],
    visited: Set[Path],
) -> None:
    """Recursively walk dir_path looking for project markers."""
    try:
        real = dir_path.resolve()
    except OSError:
        return

    if real in visited:
        return
    visited.add(real)

    source = _check_project_root(dir_path)
    if source is not None:
        found.append(source)
        return  # Don't recurse into a project we found

    if depth >= max_depth:
        return

    try:
        for item in sorted(dir_path.iterdir()):
            if not item.is_dir():
                continue
            name = item.name
            if name.startswith(".") or name in _SKIP_DIRS:
                continue
            _walk(item, depth + 1, max_depth, found, visited)
    except PermissionError:
        pass


def _check_project_root(dir_path: Path) -> Optional[DiscoveredSource]:
    """
    Check if dir_path is the root of a recognizable data source project.
    Uses fast stat/glob checks — no full content parsing.
    Returns DiscoveredSource if found, None otherwise.
    """
    is_git = (dir_path / ".git").exists()

    try:
        children: Dict[str, Path] = {item.name: item for item in dir_path.iterdir()}
    except PermissionError:
        return None

    # dbt project — dbt_project.yml in root
    if "dbt_project.yml" in children:
        return _make_source(dir_path, "dbt", 0.95, is_git)

    # dbt compiled manifest
    if "manifest.json" in children:
        if _json_has_keys(children["manifest.json"], {"nodes", "sources"}):
            return _make_source(dir_path, "dbt_manifest", 0.9, is_git)

    # LookML — look for .lkml files (direct children or one level down)
    lkml_direct = [f for f in children.values()
                   if f.is_file() and f.suffix.lower() in (".lkml", ".lookml")]
    if lkml_direct:
        return _make_source(dir_path, "lookml", 0.9, is_git)

    # LookML files one level down (views/, explores/ subdirs are common)
    lkml_nested = 0
    for child in children.values():
        if child.is_dir() and child.name not in _SKIP_DIRS:
            try:
                lkml_nested += sum(
                    1 for f in child.iterdir()
                    if f.is_file() and f.suffix.lower() in (".lkml", ".lookml")
                )
            except PermissionError:
                pass
    if lkml_nested >= 2:
        return _make_source(dir_path, "lookml", 0.85, is_git)

    # Prisma
    if "schema.prisma" in children:
        return _make_source(dir_path, "prisma", 0.95, is_git)
    prisma_files = [f for f in children.values()
                    if f.is_file() and f.suffix.lower() == ".prisma"]
    if prisma_files:
        return _make_source(dir_path, "prisma", 0.9, is_git)

    # Django
    models_py = children.get("models.py")
    if models_py and models_py.is_file():
        if _file_contains(models_py, ("from django", "models.Model")):
            return _make_source(dir_path, "django", 0.9, is_git)

    # SQLAlchemy
    if models_py and models_py.is_file():
        if (
            _file_contains(models_py, ("from sqlalchemy", "import sqlalchemy"))
            and _file_contains(models_py, ("Column(", "__tablename__", "mapped_column("))
        ):
            return _make_source(dir_path, "sqlalchemy", 0.9, is_git)

    # DDL — multiple .sql files with CREATE TABLE
    sql_files = [f for f in children.values()
                 if f.is_file() and f.suffix.lower() == ".sql"]
    if len(sql_files) >= 2:
        create_count = sum(
            1 for f in sql_files
            if _file_contains(f, ("CREATE TABLE", "create table"))
        )
        if create_count >= 1:
            confidence = 0.8 if len(sql_files) >= 5 else 0.7
            return _make_source(dir_path, "ddl", confidence, is_git)

    # SQLite files — return the file itself, not the directory
    sqlite_exts = {".sqlite", ".db", ".sqlite3", ".db3"}
    for child in children.values():
        if child.is_file() and child.suffix.lower() in sqlite_exts:
            if _is_sqlite(child):
                return _make_source(child, "sqlite", 0.95, False)

    return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _make_source(
    path: Path,
    parser_type: str,
    confidence: float,
    is_git: bool,
) -> DiscoveredSource:
    label = _PARSER_LABELS.get(parser_type, parser_type)
    pre_selected = confidence >= 0.85 and is_git
    return DiscoveredSource(
        path=path,
        parser_type=parser_type,
        label=label,
        confidence=confidence,
        is_git_repo=is_git,
        pre_selected=pre_selected,
    )


def _json_has_keys(file_path: Path, required_keys: Set[str]) -> bool:
    """Check if a JSON file has all required top-level keys.

    Uses string matching on the first 4 KB rather than JSON parsing,
    because large files (e.g. dbt manifests, 50-500 KB) would fail
    json.loads() on a truncated read.
    """
    try:
        with open(file_path, encoding="utf-8") as fh:
            text = fh.read(4096)
        return all(f'"{key}"' in text for key in required_keys)
    except Exception:
        return False


def _file_contains(file_path: Path, patterns: tuple) -> bool:
    """Check if a file contains any of the given string patterns (reads first 4 KB)."""
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as fh:
            text = fh.read(4096)
        return any(p in text for p in patterns)
    except Exception:
        return False


def _is_sqlite(file_path: Path) -> bool:
    """Check SQLite magic bytes."""
    try:
        with open(file_path, "rb") as fh:
            return fh.read(16).startswith(b"SQLite format 3\x00")
    except Exception:
        return False
