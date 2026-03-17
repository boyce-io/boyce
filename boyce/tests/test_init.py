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
            "path": tmp_path / ".mcp.json",
            "project_level": True,
            "detection_hint": tmp_path / ".claude",
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
# merge_config — servers_key parameter (VS Code uses "servers" not "mcpServers")
# ---------------------------------------------------------------------------


def test_merge_config_vscode_uses_servers_key(tmp_path):
    """VS Code config uses 'servers' as the top-level key, not 'mcpServers'."""
    config_path = tmp_path / "mcp.json"
    entry = {"command": "boyce", "args": []}
    merge_config(config_path, entry, servers_key="servers")

    data = json.loads(config_path.read_text())
    assert "servers" in data
    assert data["servers"]["boyce"] == entry
    assert "mcpServers" not in data


def test_merge_config_servers_key_preserves_other_entries(tmp_path):
    """merge_config with custom servers_key preserves other entries."""
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "servers": {
            "other-tool": {"command": "other"}
        }
    }))
    merge_config(config_path, {"command": "boyce", "args": []}, servers_key="servers")
    data = json.loads(config_path.read_text())
    assert "other-tool" in data["servers"]
    assert "boyce" in data["servers"]


# ---------------------------------------------------------------------------
# detect_hosts — VS Code, JetBrains, Windsurf
# ---------------------------------------------------------------------------


def _make_specs_with_new_platforms(tmp_path: Path) -> list:
    """Host spec list including VS Code, JetBrains, Windsurf."""
    return [
        {
            "name": "VS Code",
            "path": tmp_path / ".vscode" / "mcp.json",
            "project_level": True,
            "servers_key": "servers",
        },
        {
            "name": "JetBrains",
            "path": tmp_path / ".jb-mcp.json",
            "project_level": True,
            "servers_key": "mcpServers",
            "detection_hint": tmp_path / ".idea",
            "post_config_note": (
                "  Tip: You can also configure in your JetBrains IDE:\n"
                "       Settings → Tools → AI Assistant → Model Context Protocol (MCP) → Add"
            ),
        },
        {
            "name": "Windsurf",
            "path": tmp_path / "windsurf_mcp_config.json",
            "project_level": False,
            "servers_key": "mcpServers",
        },
    ]


def test_detect_hosts_vscode_not_detected_without_vscode_dir(tmp_path):
    """VS Code host is not detected when .vscode/ dir doesn't exist."""
    specs = _make_specs_with_new_platforms(tmp_path)
    hosts = detect_hosts(specs)
    vscode = next(h for h in hosts if h.name == "VS Code")
    assert vscode.exists is False


def test_detect_hosts_vscode_detected_with_config_file(tmp_path):
    """VS Code host detected when .vscode/mcp.json exists."""
    specs = _make_specs_with_new_platforms(tmp_path)
    vscode_path = tmp_path / ".vscode" / "mcp.json"
    vscode_path.parent.mkdir()
    vscode_path.write_text(json.dumps({"servers": {}}))

    hosts = detect_hosts(specs)
    vscode = next(h for h in hosts if h.name == "VS Code")
    assert vscode.exists is True
    assert vscode.has_boyce is False


def test_detect_hosts_vscode_reads_servers_key(tmp_path):
    """VS Code host checks 'servers' key (not 'mcpServers') for boyce entry."""
    specs = _make_specs_with_new_platforms(tmp_path)
    vscode_path = tmp_path / ".vscode" / "mcp.json"
    vscode_path.parent.mkdir()
    vscode_path.write_text(json.dumps({"servers": {"boyce": {"command": "boyce"}}}))

    hosts = detect_hosts(specs)
    vscode = next(h for h in hosts if h.name == "VS Code")
    assert vscode.has_boyce is True


def test_detect_hosts_jetbrains_detected_via_idea_dir(tmp_path):
    """JetBrains detected via .idea/ directory even without .jb-mcp.json."""
    specs = _make_specs_with_new_platforms(tmp_path)
    (tmp_path / ".idea").mkdir()

    hosts = detect_hosts(specs)
    jb = next(h for h in hosts if h.name == "JetBrains")
    assert jb.exists is True
    assert jb.has_boyce is False


def test_detect_hosts_jetbrains_has_post_config_note(tmp_path):
    """JetBrains MCPHost carries a non-empty post_config_note."""
    specs = _make_specs_with_new_platforms(tmp_path)
    hosts = detect_hosts(specs)
    jb = next(h for h in hosts if h.name == "JetBrains")
    assert jb.post_config_note is not None
    assert "Settings" in jb.post_config_note


def test_detect_hosts_windsurf_detected_with_config(tmp_path):
    """Windsurf detected when mcp_config.json exists."""
    specs = _make_specs_with_new_platforms(tmp_path)
    windsurf_path = tmp_path / "windsurf_mcp_config.json"
    windsurf_path.write_text(json.dumps({"mcpServers": {}}))

    hosts = detect_hosts(specs)
    windsurf = next(h for h in hosts if h.name == "Windsurf")
    assert windsurf.exists is True
    assert windsurf.has_boyce is False


def test_merge_config_jetbrains_uses_mcpservers(tmp_path):
    """JetBrains config uses mcpServers (same as Claude/Cursor)."""
    config_path = tmp_path / ".jb-mcp.json"
    entry = {"command": "boyce", "args": []}
    merge_config(config_path, entry, servers_key="mcpServers")

    data = json.loads(config_path.read_text())
    assert data["mcpServers"]["boyce"] == entry


# ---------------------------------------------------------------------------
# _resolve_boyce_command
# ---------------------------------------------------------------------------


def test_resolve_command_returns_full_path_when_on_path():
    """_resolve_boyce_command returns the full resolved path (not bare 'boyce')
    so that editor configs work without the user's venv being activated."""
    with patch("shutil.which", return_value="/usr/local/bin/boyce"):
        cmd = _resolve_boyce_command()
    assert cmd == "/usr/local/bin/boyce"


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
