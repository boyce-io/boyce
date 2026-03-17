"""
Tests for boyce.discovery — auto-detection and ingestion of data sources.

Tests run against the committed fixtures in test_warehouses/.
All tests are offline — no DB, no LLM, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boyce.discovery import (
    _check_project_root,
    _resolve_parse_path,
    discover_sources,
    ingest_source,
)


# ---------------------------------------------------------------------------
# Locate test_warehouses relative to this file
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent  # boyce/tests/.. → boyce/ → repo root
_TW = _REPO_ROOT / "test_warehouses"


def _skip_if_missing(fixture_dir: str) -> Path:
    """Return the resolved fixture path or skip the test if missing."""
    path = _TW / fixture_dir
    if not path.exists():
        pytest.skip(f"Fixture not found: {fixture_dir}")
    return path.resolve()


# ---------------------------------------------------------------------------
# _check_project_root — detection per fixture
# ---------------------------------------------------------------------------


class TestDetection:
    """Verify _check_project_root identifies each committed fixture."""

    def test_detect_dbt_jaffle_shop(self):
        d = _skip_if_missing("jaffle_shop")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "dbt"
        assert src.confidence >= 0.9

    def test_detect_lookml_thelook(self):
        d = _skip_if_missing("thelook_lookml")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "lookml"
        assert src.confidence >= 0.85

    def test_detect_django_models(self):
        d = _skip_if_missing("django_models")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "django"

    def test_detect_sqlalchemy_models(self):
        d = _skip_if_missing("sqlalchemy_models")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "sqlalchemy"

    def test_detect_prisma_schema(self):
        d = _skip_if_missing("prisma_schema")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "prisma"

    def test_detect_airflow_ddl(self):
        d = _skip_if_missing("airflow_analytics/sql")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "ddl"
        assert src.confidence >= 0.7

    def test_detect_sqlite(self):
        d = _skip_if_missing("sample_sqlite")
        src = _check_project_root(d)
        assert src is not None
        assert src.parser_type == "sqlite"

    def test_no_false_positive_on_empty_dir(self, tmp_path):
        src = _check_project_root(tmp_path)
        assert src is None


# ---------------------------------------------------------------------------
# _resolve_parse_path — directory → file resolution
# ---------------------------------------------------------------------------


class TestResolveParsePath:

    def test_django_resolves_to_models_py(self):
        d = _skip_if_missing("django_models")
        src = _check_project_root(d)
        resolved = _resolve_parse_path(src)
        assert resolved.name == "models.py"
        assert resolved.is_file()

    def test_sqlalchemy_resolves_to_models_py(self):
        d = _skip_if_missing("sqlalchemy_models")
        src = _check_project_root(d)
        resolved = _resolve_parse_path(src)
        assert resolved.name == "models.py"
        assert resolved.is_file()

    def test_prisma_resolves_to_schema_prisma(self):
        d = _skip_if_missing("prisma_schema")
        src = _check_project_root(d)
        resolved = _resolve_parse_path(src)
        assert resolved.suffix == ".prisma"
        assert resolved.is_file()

    def test_dbt_stays_as_directory(self):
        d = _skip_if_missing("jaffle_shop")
        src = _check_project_root(d)
        resolved = _resolve_parse_path(src)
        assert resolved.is_dir()

    def test_file_source_unchanged(self):
        d = _skip_if_missing("sample_sqlite")
        src = _check_project_root(d)
        # SQLite detection returns the file, not the directory
        resolved = _resolve_parse_path(src)
        assert resolved == src.path


# ---------------------------------------------------------------------------
# discover_sources — walk + dedup
# ---------------------------------------------------------------------------


class TestDiscoverSources:

    def test_finds_multiple_types(self):
        results = discover_sources(search_roots=[_TW], max_depth=3)
        types_found = {r.parser_type for r in results}
        # At minimum these committed fixtures should be found
        assert "lookml" in types_found or "dbt" in types_found
        assert len(results) >= 3

    def test_results_sorted_by_confidence(self):
        results = discover_sources(search_roots=[_TW], max_depth=3)
        if len(results) >= 2:
            confidences = [r.confidence for r in results]
            assert confidences == sorted(confidences, reverse=True)

    def test_deduplicates_by_path(self):
        results = discover_sources(search_roots=[_TW, _TW], max_depth=3)
        paths = [r.path.resolve() for r in results]
        assert len(paths) == len(set(paths))

    def test_nonexistent_root_skipped(self):
        results = discover_sources(
            search_roots=[Path("/nonexistent/path/xyz")],
            max_depth=3,
        )
        assert results == []

    def test_empty_root_returns_empty(self, tmp_path):
        results = discover_sources(search_roots=[tmp_path], max_depth=3)
        assert results == []


# ---------------------------------------------------------------------------
# ingest_source — full discover → parse → save
# ---------------------------------------------------------------------------


class TestIngestion:
    """End-to-end: detect → resolve → parse → save for each fixture type."""

    @pytest.fixture(autouse=True)
    def _use_tmpdir(self, tmp_path, monkeypatch):
        """Run each test in a temp directory so _local_context/ goes there."""
        monkeypatch.chdir(tmp_path)

    def _ingest(self, fixture_dir: str) -> str:
        d = _skip_if_missing(fixture_dir)
        src = _check_project_root(d)
        assert src is not None, f"Detection failed for {fixture_dir}"
        return ingest_source(src)

    def test_ingest_dbt(self):
        result = self._ingest("jaffle_shop")
        assert "models" in result

    def test_ingest_lookml(self):
        result = self._ingest("thelook_lookml")
        assert "views" in result

    def test_ingest_django(self):
        result = self._ingest("django_models")
        assert "tables" in result

    def test_ingest_sqlalchemy(self):
        result = self._ingest("sqlalchemy_models")
        assert "tables" in result

    def test_ingest_prisma(self):
        result = self._ingest("prisma_schema")
        assert "tables" in result

    def test_ingest_ddl(self):
        result = self._ingest("airflow_analytics/sql")
        assert "tables" in result
        assert "columns" in result

    def test_ingest_sqlite(self):
        d = _skip_if_missing("sample_sqlite")
        src = _check_project_root(d)
        assert src is not None
        result = ingest_source(src)
        assert "tables" in result

    def test_ingest_saves_to_local_context(self, tmp_path):
        d = _skip_if_missing("jaffle_shop")
        src = _check_project_root(d)
        ingest_source(src)
        ctx = tmp_path / "_local_context"
        assert ctx.exists()
        json_files = list(ctx.glob("*.json"))
        assert len(json_files) >= 1

    def test_ingest_custom_name(self, tmp_path):
        d = _skip_if_missing("jaffle_shop")
        src = _check_project_root(d)
        ingest_source(src, name="my_custom_name")
        ctx = tmp_path / "_local_context"
        names = [f.stem for f in ctx.glob("*.json")]
        assert "my_custom_name" in names
