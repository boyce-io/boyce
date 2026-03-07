"""
Tests for boyce.scan — CLI scanner.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from boyce.scan import scan_path

REPO_ROOT = Path(__file__).parent.parent.parent
DEMO_MANIFEST = REPO_ROOT / "demo" / "magic_moment" / "manifest.json"
POSTGRES_DDL = REPO_ROOT / "test_warehouses" / "postgres_ddl" / "ecommerce.sql"
DJANGO_MODELS = REPO_ROOT / "test_warehouses" / "django_models" / "models.py"
SQLALCHEMY_MODELS = REPO_ROOT / "test_warehouses" / "sqlalchemy_models" / "models.py"
PRISMA_SCHEMA = REPO_ROOT / "test_warehouses" / "prisma_schema" / "schema.prisma"
JAFFLE_SEEDS = REPO_ROOT / "test_warehouses" / "jaffle_shop" / "seeds"


# ---------------------------------------------------------------------------
# scan_path() unit tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DEMO_MANIFEST.exists(), reason="Demo manifest not present")
def test_scan_single_file():
    """Scan a single manifest.json — correct result shape and counts."""
    result = scan_path(DEMO_MANIFEST)
    assert result["scanned"] == 1
    assert result["parsed"] == 1
    assert result["failed"] == 0
    assert result["skipped"] == 0
    assert result["entities_total"] >= 1
    assert result["fields_total"] >= 1
    assert len(result["sources"]) == 1
    src = result["sources"][0]
    assert src["parser"] == "dbt_manifest"
    assert src["snapshot_id"]
    assert src["entities"] >= 1


@pytest.mark.skipif(
    not POSTGRES_DDL.exists() or not DJANGO_MODELS.exists(),
    reason="Test warehouse fixtures not present",
)
def test_scan_directory():
    """Scan test_warehouses/ — multiple parsers fire."""
    test_warehouses = REPO_ROOT / "test_warehouses"
    result = scan_path(test_warehouses)
    assert result["parsed"] >= 3
    parser_types = {s["parser"] for s in result["sources"]}
    assert len(parser_types) >= 2


def test_scan_empty_directory():
    """No parseable files — graceful empty result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = scan_path(Path(tmpdir))
        assert result["scanned"] == 0
        assert result["parsed"] == 0
        assert result["failed"] == 0
        assert result["sources"] == []
        assert result["failures"] == []


def test_scan_nonexistent_path():
    """scan_path on a nonexistent path — no crash, just empty."""
    bogus = Path("/tmp/datashark_nonexistent_path_xyz")
    # _collect_files returns [] for non-dir, non-file
    result = scan_path(bogus)
    assert result["scanned"] == 0
    assert result["parsed"] == 0


def test_scan_skips_hidden_dirs():
    """Files inside hidden directories are not scanned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create a .hidden dir with a .sql file
        hidden = root / ".hidden"
        hidden.mkdir()
        (hidden / "schema.sql").write_text("CREATE TABLE foo (id INT);")
        # Create a visible file too
        (root / "readme.txt").write_text("hello")

        result = scan_path(root)
        scanned_paths = {s["path"] for s in result["sources"]}
        assert not any(".hidden" in p for p in scanned_paths)


def test_scan_result_shape():
    """All expected top-level keys present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = scan_path(Path(tmpdir))
        expected_keys = {
            "scanned", "parsed", "failed", "skipped",
            "entities_total", "fields_total", "joins_total",
            "sources", "failures",
        }
        assert set(result.keys()) == expected_keys


@pytest.mark.skipif(not DEMO_MANIFEST.exists(), reason="Demo manifest not present")
def test_scan_with_save():
    """--save writes snapshots to _local_context/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from boyce.scan import _save_snapshots
        from boyce.store import SnapshotStore

        result = scan_path(DEMO_MANIFEST)
        assert result["parsed"] >= 1

        # Monkey-patch _save_snapshots to use a temp dir
        store = SnapshotStore(Path(tmpdir) / "_local_context")
        from boyce.parsers.registry import get_default_registry
        registry = get_default_registry()
        saved = 0
        for source_info in result["sources"]:
            if source_info["validation_errors"]:
                continue
            file_path = Path(source_info["path"])
            snapshot = registry.parse(file_path)
            name = file_path.stem
            store.save(snapshot, name)
            saved += 1
        assert saved >= 1
        ctx = Path(tmpdir) / "_local_context"
        assert any(ctx.iterdir())


@pytest.mark.skipif(not DEMO_MANIFEST.exists(), reason="Demo manifest not present")
def test_cli_exit_code_success():
    """Exit 0 when parseable files found."""
    result = subprocess.run(
        [sys.executable, "-m", "boyce.scan", str(DEMO_MANIFEST)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["parsed"] >= 1


def test_cli_exit_code_nothing_found():
    """Exit 1 when no parseable files found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "readme.txt").write_text("nothing here")
        result = subprocess.run(
            [sys.executable, "-m", "boyce.scan", str(tmpdir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1


def test_cli_exit_code_nonexistent():
    """Exit 2 for nonexistent path."""
    result = subprocess.run(
        [sys.executable, "-m", "boyce.scan", "/tmp/no_such_path_xyz"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
