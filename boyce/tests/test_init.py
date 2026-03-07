"""
Tests for boyce.init_wizard

All tests are offline — no filesystem side effects outside tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from boyce.init_wizard import (
    MCPHost,
    _resolve_boyce_command,
    detect_hosts,
    generate_server_entry,
    merge_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_specs(tmp_path: Path) -> list:
    """Return a host spec list pointing entirely into tmp_path."""
    return [
        {
            "name": "Claude Desktop",
            "path": tmp_path / "claude_desktop_config.json",
            "project_level": False,
        },
        {
            "name": "Cursor",
            "path": tmp_path / ".cursor" / "mcp.json",
            "project_level": True,
        },
        {
            "name": "Claude Code",
            "path": tmp_path / ".claude" / "settings.json",
            "project_level": True,
        },
    ]


# ---------------------------------------------------------------------------
# detect_hosts
# ---------------------------------------------------------------------------


def test_detect_hosts_returns_one_per_spec(tmp_path):
    hosts = detect_hosts(_make_specs(tmp_path))
    assert len(hosts) == 3


def test_detect_hosts_none_exist_initially(tmp_path):
    hosts = detect_hosts(_make_specs(tmp_path))
    assert all(not h.exists for h in hosts)
    assert all(not h.has_boyce for h in hosts)


def test_detect_hosts_finds_existing_config(tmp_path):
    specs = _make_specs(tmp_path)
    desktop_path: Path = specs[0]["path"]
    desktop_path.write_text(json.dumps({"mcpServers": {}}))

    hosts = detect_hosts(specs)
    desktop = next(h for h in hosts if h.name == "Claude Desktop")
    assert desktop.exists is True
    assert desktop.has_boyce is False


def test_detect_hosts_detects_boyce_already_configured(tmp_path):
    specs = _make_specs(tmp_path)
    desktop_path: Path = specs[0]["path"]
    desktop_path.write_text(json.dumps({"mcpServers": {"boyce": {"command": "boyce"}}}))

    hosts = detect_hosts(specs)
    desktop = next(h for h in hosts if h.name == "Claude Desktop")
    assert desktop.has_boyce is True


def test_detect_hosts_survives_corrupt_json(tmp_path):
    specs = _make_specs(tmp_path)
    specs[0]["path"].write_text("not-valid-json{{")

    # Should not raise
    hosts = detect_hosts(specs)
    desktop = next(h for h in hosts if h.name == "Claude Desktop")
    assert desktop.exists is True
    assert desktop.has_boyce is False


def test_detect_hosts_names_are_correct(tmp_path):
    hosts = detect_hosts(_make_specs(tmp_path))
    names = [h.name for h in hosts]
    assert "Claude Desktop" in names
    assert "Cursor" in names
    assert "Claude Code" in names


# ---------------------------------------------------------------------------
# generate_server_entry
# ---------------------------------------------------------------------------


def test_generate_minimal_entry():
    entry = generate_server_entry()
    assert "command" in entry
    assert "args" in entry
    assert entry["args"] == []
    assert "env" not in entry  # no env when nothing configured


def test_generate_entry_with_db_url():
    entry = generate_server_entry(db_url="postgresql://user:pass@localhost/mydb")
    assert entry["env"]["BOYCE_DB_URL"] == "postgresql://user:pass@localhost/mydb"


def test_generate_entry_with_llm_anthropic():
    entry = generate_server_entry(
        want_llm=True,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test",
    )
    assert entry["env"]["BOYCE_PROVIDER"] == "anthropic"
    assert entry["env"]["BOYCE_MODEL"] == "claude-haiku-4-5-20251001"
    assert entry["env"]["ANTHROPIC_API_KEY"] == "sk-ant-test"


def test_generate_entry_with_llm_openai():
    entry = generate_server_entry(
        want_llm=True,
        provider="openai",
        model="gpt-4o",
        api_key="sk-openai-test",
    )
    assert entry["env"]["OPENAI_API_KEY"] == "sk-openai-test"


def test_generate_entry_llm_unknown_provider_uses_litellm_key():
    entry = generate_server_entry(
        want_llm=True,
        provider="cohere",
        model="command-r",
        api_key="co-test-key",
    )
    assert entry["env"]["LITELLM_API_KEY"] == "co-test-key"


def test_generate_entry_llm_no_api_key_omits_key():
    entry = generate_server_entry(want_llm=True, provider="anthropic", model="claude-haiku-4-5-20251001")
    assert "ANTHROPIC_API_KEY" not in entry.get("env", {})


def test_generate_entry_want_llm_false_omits_provider():
    entry = generate_server_entry(want_llm=False, provider="anthropic", model="claude-haiku-4-5-20251001")
    assert "BOYCE_PROVIDER" not in entry.get("env", {})


# ---------------------------------------------------------------------------
# merge_config
# ---------------------------------------------------------------------------


def test_merge_config_creates_new_file(tmp_path):
    config_path = tmp_path / "config.json"
    entry = {"command": "boyce", "args": []}
    merge_config(config_path, entry)

    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert data["mcpServers"]["boyce"] == entry


def test_merge_config_creates_parent_dirs(tmp_path):
    config_path = tmp_path / "nested" / "deep" / "config.json"
    merge_config(config_path, {"command": "boyce", "args": []})
    assert config_path.exists()


def test_merge_config_preserves_other_servers(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "other-tool": {"command": "other", "args": []}
        }
    }))

    merge_config(config_path, {"command": "boyce", "args": []})
    data = json.loads(config_path.read_text())
    assert "other-tool" in data["mcpServers"]
    assert "boyce" in data["mcpServers"]


def test_merge_config_overwrites_existing_boyce(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "boyce": {"command": "/old/path/boyce", "args": ["--old-flag"]}
        }
    }))

    new_entry = {"command": "boyce", "args": []}
    merge_config(config_path, new_entry)
    data = json.loads(config_path.read_text())
    assert data["mcpServers"]["boyce"] == new_entry


def test_merge_config_handles_corrupt_existing_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("this is not json {{")

    # Should not raise — treats corrupt file as empty
    merge_config(config_path, {"command": "boyce", "args": []})
    data = json.loads(config_path.read_text())
    assert "boyce" in data["mcpServers"]


def test_merge_config_output_is_valid_json(tmp_path):
    config_path = tmp_path / "config.json"
    merge_config(config_path, {"command": "boyce", "args": [], "env": {"X": "1"}})
    # Should parse without error
    data = json.loads(config_path.read_text())
    assert data["mcpServers"]["boyce"]["env"]["X"] == "1"


# ---------------------------------------------------------------------------
# _resolve_boyce_command
# ---------------------------------------------------------------------------


def test_resolve_command_returns_boyce_when_on_path():
    with patch("shutil.which", return_value="/usr/local/bin/boyce"):
        cmd = _resolve_boyce_command()
    assert cmd == "boyce"


def test_resolve_command_falls_back_to_venv_bin(tmp_path):
    fake_boyce = tmp_path / "boyce"
    fake_boyce.touch()
    with patch("shutil.which", return_value=None):
        with patch("sys.executable", str(tmp_path / "python")):
            cmd = _resolve_boyce_command()
    assert cmd == str(fake_boyce)


def test_resolve_command_last_resort_is_bare_boyce():
    with patch("shutil.which", return_value=None):
        with patch("sys.executable", "/nonexistent/python"):
            cmd = _resolve_boyce_command()
    assert cmd == "boyce"
