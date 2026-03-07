"""
Tests for Orchestrator

Validates multi-repo merge correctness and determinism.
"""

import pytest
import tempfile
from pathlib import Path
from datashark_mcp.context.orchestrator.repo_manager import RepoManager, RepoState
from datashark_mcp.context.orchestrator.sync import sync_extractors


def test_repo_manager_register_and_get():
    """Test repository registration and retrieval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "repo_states.json"
        manager = RepoManager(state_file=state_file)
        
        state = manager.register_repo("repo1", "database", "1.0.0")
        
        assert state.repo_id == "repo1"
        assert state.system == "database"
        
        retrieved = manager.get_repo("repo1")
        assert retrieved is not None
        assert retrieved.repo_id == "repo1"


def test_repo_manager_deterministic_ordering():
    """Test that repos are stored in deterministic order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "repo_states.json"
        manager = RepoManager(state_file=state_file)
        
        # Register in non-alphabetical order
        manager.register_repo("repo_z", "database")
        manager.register_repo("repo_a", "dbt")
        manager.register_repo("repo_m", "bi_tool")
        
        repos = manager.list_repos()
        repo_ids = [r.repo_id for r in repos]
        
        assert repo_ids == sorted(repo_ids), "Repos must be sorted by repo_id"


def test_sync_multiple_extractors():
    """Test syncing multiple extractors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        
        configs = [
            {"name": "database_catalog", "system": "database", "repo_id": "db1"},
            {"name": "bi_tool", "system": "bi_tool", "repo_id": "bi1"}
        ]
        
        consolidated = sync_extractors(configs, output_dir)
        
        assert consolidated["status"] == "success"
        assert "nodes.jsonl" in [f.name for f in output_dir.iterdir()]
        assert "edges.jsonl" in [f.name for f in output_dir.iterdir()]
        assert "manifest.json" in [f.name for f in output_dir.iterdir()]


def test_sync_deterministic():
    """Test that sync produces deterministic results."""
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            output_dir1 = Path(tmpdir1) / "output"
            output_dir2 = Path(tmpdir2) / "output"
            
            configs = [
                {"name": "database_catalog", "system": "database"},
                {"name": "bi_tool", "system": "bi_tool"}
            ]
            
            consolidated1 = sync_extractors(configs, output_dir1)
            consolidated2 = sync_extractors(configs, output_dir2)
            
            # Hash summaries should be identical
            assert consolidated1["hash_summaries"] == consolidated2["hash_summaries"]

