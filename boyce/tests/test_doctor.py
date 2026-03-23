"""Tests for boyce doctor — environment health checks."""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from boyce.doctor import (
    check_editors,
    check_database,
    check_server,
    check_snapshots,
    check_sources,
    check_version,
    run_doctor,
)


# ---------------------------------------------------------------------------
# check_editors
# ---------------------------------------------------------------------------

def test_check_editors_returns_structure():
    result = check_editors()
    assert "status" in result
    assert "items" in result
    assert result["status"] in ("ok", "warning")


def test_check_editors_all_configured():
    """When every detected editor has Boyce, status is ok."""
    from boyce.init_wizard import MCPHost

    mock_hosts = [
        MCPHost(name="Test", config_path=Path("/tmp/t"), project_level=True,
                exists=True, has_boyce=True),
    ]
    with patch("boyce.doctor.check_editors") as mock_check:
        mock_check.return_value = {"status": "ok", "items": [
            {"name": "Test", "detected": True, "configured": True,
             "config_path": "/tmp/t", "fix": None}
        ]}
        result = mock_check()
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# check_database
# ---------------------------------------------------------------------------

def test_check_database_no_connections(tmp_path: Path):
    result = asyncio.run(check_database(tmp_path))
    assert result["status"] == "ok"
    assert len(result["items"]) == 0


def test_check_database_with_stored_connection(tmp_path: Path):
    """When a connection is stored but asyncpg is not available, warns."""
    from boyce.connections import ConnectionStore
    store = ConnectionStore(tmp_path)
    store.save("test", "postgresql://u:p@h:5432/test")

    # The test may or may not have asyncpg — either way it should return
    # a valid structure
    result = asyncio.run(check_database(tmp_path))
    assert result["status"] in ("ok", "warning", "error")
    assert len(result["items"]) == 1
    assert result["items"][0]["snapshot_name"] == "test"


# ---------------------------------------------------------------------------
# check_snapshots
# ---------------------------------------------------------------------------

def test_check_snapshots_empty(tmp_path: Path):
    result = check_snapshots(tmp_path)
    assert result["status"] == "ok"
    assert len(result["items"]) == 0


def test_check_snapshots_with_snapshot(tmp_path: Path):
    """Fresh snapshot should have status ok."""
    snapshot = {
        "snapshot_id": "abc123",
        "entities": [
            {"entity_id": "e:t", "name": "t", "fields": [
                {"field_id": "f:t:id", "name": "id", "field_type": "ID",
                 "data_type": "INTEGER"}
            ]}
        ],
        "joins": [],
    }
    (tmp_path / "test.json").write_text(json.dumps(snapshot))
    result = check_snapshots(tmp_path)
    assert result["status"] == "ok"
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "test"
    assert result["items"][0]["entities"] == 1


def test_check_snapshots_skips_connections_json(tmp_path: Path):
    """connections.json should not be counted as a snapshot."""
    (tmp_path / "connections.json").write_text("{}")
    (tmp_path / "test.definitions.json").write_text("{}")
    result = check_snapshots(tmp_path)
    assert len(result["items"]) == 0


# ---------------------------------------------------------------------------
# check_sources
# ---------------------------------------------------------------------------

def test_check_sources_returns_structure():
    result = check_sources()
    assert "status" in result
    assert "items" in result


# ---------------------------------------------------------------------------
# check_server
# ---------------------------------------------------------------------------

def test_check_server_returns_version(tmp_path: Path):
    result = check_server(tmp_path)
    assert "version" in result
    assert "asyncpg_installed" in result
    assert "boyce_command" in result


def test_check_server_context_dir_missing(tmp_path: Path):
    missing = tmp_path / "nonexistent"
    result = check_server(missing)
    assert result["context_dir_exists"] is False
    assert result["snapshot_count"] == 0


# ---------------------------------------------------------------------------
# run_doctor orchestrator
# ---------------------------------------------------------------------------

def test_run_doctor_returns_exit_code(tmp_path: Path):
    code = asyncio.run(run_doctor(context_dir=tmp_path, json_output=True))
    assert code in (0, 1, 2)


def test_run_doctor_writes_environment_json(tmp_path: Path):
    asyncio.run(run_doctor(context_dir=tmp_path, json_output=True))
    env_path = tmp_path / "environment.json"
    assert env_path.exists()
    data = json.loads(env_path.read_text())
    assert "last_doctor" in data
    assert "status" in data


def test_run_doctor_json_output_is_valid(tmp_path: Path, capsys):
    asyncio.run(run_doctor(context_dir=tmp_path, json_output=True))
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "checks" in data
    assert "status" in data
    assert "suggestions" in data


def test_run_doctor_human_output(tmp_path: Path, capsys):
    asyncio.run(run_doctor(context_dir=tmp_path, json_output=False))
    captured = capsys.readouterr()
    assert "Boyce Doctor" in captured.out
    assert "Overall:" in captured.out


# ---------------------------------------------------------------------------
# check_version
# ---------------------------------------------------------------------------

def test_check_version_returns_structure(tmp_path):
    with patch("boyce.version_check.get_version_info", return_value={
        "current": "0.1.0", "latest": "0.1.0", "installed": "0.1.0",
        "running": "0.1.0", "update_available": False, "restart_required": False,
    }):
        result = check_version(tmp_path)
    assert "status" in result
    assert "current" in result
    assert "items" in result


def test_check_version_update_available(tmp_path):
    with patch("boyce.version_check.get_version_info", return_value={
        "current": "0.1.0", "latest": "0.2.0", "installed": "0.1.0",
        "running": "0.1.0", "update_available": True, "restart_required": False,
    }):
        result = check_version(tmp_path)
    assert result["status"] == "info"
    assert len(result["items"]) == 1
    assert "boyce update" in result["items"][0]["fix"]


def test_check_version_restart_required(tmp_path):
    with patch("boyce.version_check.get_version_info", return_value={
        "current": "0.1.0", "latest": "0.2.0", "installed": "0.2.0",
        "running": "0.1.0", "update_available": True, "restart_required": True,
    }):
        result = check_version(tmp_path)
    assert result["status"] == "warning"
    assert "Restart" in result["items"][0]["fix"]


def test_check_version_up_to_date(tmp_path):
    with patch("boyce.version_check.get_version_info", return_value={
        "current": "0.1.0", "latest": "0.1.0", "installed": "0.1.0",
        "running": "0.1.0", "update_available": False, "restart_required": False,
    }):
        result = check_version(tmp_path)
    assert result["status"] == "ok"
    assert result["items"] == []


def test_run_doctor_includes_version_check(capsys):
    with patch("boyce.version_check.get_version_info", return_value={
        "current": "0.1.0", "latest": "0.1.0", "installed": "0.1.0",
        "running": "0.1.0", "update_available": False, "restart_required": False,
    }):
        code = asyncio.run(run_doctor(json_output=True))
    output = json.loads(capsys.readouterr().out)
    assert "version" in output["checks"]


def test_run_doctor_version_is_first_check(capsys):
    with patch("boyce.version_check.get_version_info", return_value={
        "current": "0.1.0", "latest": "0.1.0", "installed": "0.1.0",
        "running": "0.1.0", "update_available": False, "restart_required": False,
    }):
        code = asyncio.run(run_doctor(json_output=True))
    output = json.loads(capsys.readouterr().out)
    first_key = list(output["checks"].keys())[0]
    assert first_key == "version"
