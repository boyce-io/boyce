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
    _CLI_EDITOR_NAMES,
    _get_existing_db_url,
    _merge_toml_config,
    _redact_dsn,
    _resolve_boyce_command,
    _run_wizard_noninteractive,
    detect_hosts,
    generate_server_entry,
    merge_config,
    run_wizard,
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


# ---------------------------------------------------------------------------
# _redact_dsn
# ---------------------------------------------------------------------------


def test_redact_dsn_hides_password():
    assert _redact_dsn("postgresql://user:secret@host:5432/db") == "postgresql://user:***@host:5432/db"


def test_redact_dsn_no_password():
    assert _redact_dsn("postgresql://host:5432/db") == "postgresql://host:5432/db"


def test_redact_dsn_handles_junk():
    assert _redact_dsn("not-a-url") == "not-a-url"


# ---------------------------------------------------------------------------
# _get_existing_db_url
# ---------------------------------------------------------------------------


def test_get_existing_db_url_finds_configured_dsn(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "boyce": {
                "command": "boyce",
                "env": {"BOYCE_DB_URL": "postgresql://u:p@host/db"}
            }
        }
    }))
    host = MCPHost(
        name="Test",
        config_path=config_path,
        project_level=True,
        exists=True,
        has_boyce=True,
    )
    assert _get_existing_db_url([host]) == "postgresql://u:p@host/db"


def test_get_existing_db_url_returns_none_when_no_dsn(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mcpServers": {"boyce": {"command": "boyce"}}
    }))
    host = MCPHost(
        name="Test",
        config_path=config_path,
        project_level=True,
        exists=True,
        has_boyce=True,
    )
    assert _get_existing_db_url([host]) is None


def test_get_existing_db_url_returns_none_when_no_boyce(tmp_path):
    host = MCPHost(
        name="Test",
        config_path=tmp_path / "nonexistent.json",
        project_level=True,
        exists=False,
        has_boyce=False,
    )
    assert _get_existing_db_url([host]) is None


# ---------------------------------------------------------------------------
# _CLI_EDITOR_NAMES
# ---------------------------------------------------------------------------


def test_cli_editor_names_covers_all_hosts():
    """Every host in _host_specs has a CLI name mapping."""
    from boyce.init_wizard import _host_specs
    host_names = {spec["name"] for spec in _host_specs()}
    mapped_names = set(_CLI_EDITOR_NAMES.values())
    assert host_names == mapped_names


# ---------------------------------------------------------------------------
# Non-interactive mode — _run_wizard_noninteractive
# ---------------------------------------------------------------------------


def test_noninteractive_with_specific_editor(tmp_path):
    """Non-interactive mode configures a specific editor by CLI name."""
    specs = _make_specs(tmp_path)
    # Make Claude Code "exist" by creating its detection hint
    (tmp_path / ".claude").mkdir()

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = _run_wizard_noninteractive(
            editors=["claude_code"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=False,
        )
    assert code == 0
    # Verify config was written
    config = json.loads((tmp_path / ".mcp.json").read_text())
    assert "boyce" in config["mcpServers"]


def test_noninteractive_unknown_editor_exits_1(tmp_path):
    """Non-interactive mode exits 1 for unknown editor names."""
    specs = _make_specs(tmp_path)
    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = _run_wizard_noninteractive(
            editors=["nonexistent"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=False,
        )
    assert code == 1


def test_noninteractive_skip_existing(tmp_path):
    """--skip-existing skips already-configured editors."""
    specs = _make_specs(tmp_path)
    # Pre-configure Claude Code
    cc_path = tmp_path / ".mcp.json"
    cc_path.write_text(json.dumps({"mcpServers": {"boyce": {"command": "boyce"}}}))

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = _run_wizard_noninteractive(
            editors=None,
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=True,
            json_output=False,
        )
    # Should exit 0 even with empty list (all skipped)
    assert code == 0


def test_noninteractive_json_output_is_valid(tmp_path, capsys):
    """--json output is valid parseable JSON."""
    specs = _make_specs(tmp_path)
    (tmp_path / ".claude").mkdir()

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = _run_wizard_noninteractive(
            editors=["claude_code"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=True,
        )
    assert code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"
    assert "Claude Code" in result["editors_configured"]
    assert isinstance(result["config_paths"], list)


def test_noninteractive_json_error_is_valid(tmp_path, capsys):
    """Error JSON output is valid and contains error field."""
    specs = _make_specs(tmp_path)
    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = _run_wizard_noninteractive(
            editors=["fake_editor"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=True,
        )
    assert code == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "error"
    assert "error" in result


def test_noninteractive_idempotent_rerun(tmp_path):
    """Running non-interactive twice doesn't clobber the first run."""
    specs = _make_specs(tmp_path)
    (tmp_path / ".claude").mkdir()

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        # First run
        code1 = _run_wizard_noninteractive(
            editors=["claude_code"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=False,
        )
        assert code1 == 0

        # Write a second server to the same config (simulating another tool)
        config = json.loads((tmp_path / ".mcp.json").read_text())
        config["mcpServers"]["other-tool"] = {"command": "other"}
        (tmp_path / ".mcp.json").write_text(json.dumps(config))

        # Second run — should not clobber other-tool
        code2 = _run_wizard_noninteractive(
            editors=["claude_code"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=False,
        )
        assert code2 == 0

    final = json.loads((tmp_path / ".mcp.json").read_text())
    assert "boyce" in final["mcpServers"]
    assert "other-tool" in final["mcpServers"]


# ---------------------------------------------------------------------------
# run_wizard — routing
# ---------------------------------------------------------------------------


def test_run_wizard_routes_to_noninteractive(tmp_path):
    """run_wizard with non_interactive=True routes to non-interactive path."""
    specs = _make_specs(tmp_path)
    (tmp_path / ".claude").mkdir()

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = run_wizard(
            non_interactive=True,
            json_output=False,
            editors="claude_code",
            skip_db=True,
            skip_sources=True,
        )
    assert code == 0


def test_run_wizard_parses_comma_editors(tmp_path, capsys):
    """run_wizard splits comma-separated editor names."""
    specs = _make_specs(tmp_path)
    (tmp_path / ".claude").mkdir()
    # Create Cursor dir so it's detected
    (tmp_path / ".cursor").mkdir()

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = run_wizard(
            non_interactive=True,
            json_output=True,
            editors="claude_code,cursor",
            skip_db=True,
            skip_sources=True,
        )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert "Claude Code" in result["editors_configured"]
    assert "Cursor" in result["editors_configured"]


# ---------------------------------------------------------------------------
# Codex — TOML detection and config merge
# ---------------------------------------------------------------------------


def _make_specs_with_codex(tmp_path: Path) -> list:
    """Host spec list including Codex (TOML-based)."""
    return [
        {
            "name": "Codex",
            "path": tmp_path / ".codex" / "config.toml",
            "project_level": False,
            "servers_key": "mcp_servers",
            "installed_check": lambda: (tmp_path / ".codex").is_dir(),
            "restart_instruction": "Restart Codex",
            "is_toml": True,
        },
    ]


def test_detect_hosts_codex_detected_via_dir(tmp_path):
    """Codex detected when ~/.codex/ directory exists."""
    specs = _make_specs_with_codex(tmp_path)
    (tmp_path / ".codex").mkdir()

    hosts = detect_hosts(specs)
    codex = next(h for h in hosts if h.name == "Codex")
    assert codex.exists is True
    assert codex.has_boyce is False


def test_detect_hosts_codex_not_detected_without_dir(tmp_path):
    """Codex not detected when ~/.codex/ directory does not exist."""
    specs = _make_specs_with_codex(tmp_path)

    hosts = detect_hosts(specs)
    codex = next(h for h in hosts if h.name == "Codex")
    assert codex.exists is False


def test_detect_hosts_codex_reads_toml(tmp_path):
    """Codex host checks TOML for existing boyce entry."""
    import sys
    if sys.version_info < (3, 11):
        pytest.skip("tomllib requires Python 3.11+")

    specs = _make_specs_with_codex(tmp_path)
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    config_path = codex_dir / "config.toml"
    config_path.write_text(
        '[mcp_servers.boyce]\ncommand = "boyce"\nargs = []\nenabled = true\n',
        encoding="utf-8",
    )

    hosts = detect_hosts(specs)
    codex = next(h for h in hosts if h.name == "Codex")
    assert codex.exists is True
    assert codex.has_boyce is True


def test_detect_hosts_codex_has_boyce_false_without_boyce_entry(tmp_path):
    """Codex TOML exists but has no boyce entry — has_boyce is False."""
    import sys
    if sys.version_info < (3, 11):
        pytest.skip("tomllib requires Python 3.11+")

    specs = _make_specs_with_codex(tmp_path)
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    config_path = codex_dir / "config.toml"
    config_path.write_text(
        '[mcp_servers.other]\ncommand = "other"\nargs = []\nenabled = true\n',
        encoding="utf-8",
    )

    hosts = detect_hosts(specs)
    codex = next(h for h in hosts if h.name == "Codex")
    assert codex.has_boyce is False


def test_merge_toml_config_creates_new(tmp_path):
    """_merge_toml_config creates a valid TOML file when none exists."""
    config_path = tmp_path / ".codex" / "config.toml"
    entry = {"command": "/usr/local/bin/boyce", "args": []}
    _merge_toml_config(config_path, entry)

    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.boyce]" in content
    assert 'command = "/usr/local/bin/boyce"' in content
    assert "args = []" in content
    assert "enabled = true" in content


def test_merge_toml_config_creates_parent_dirs(tmp_path):
    """_merge_toml_config creates parent directories if they don't exist."""
    config_path = tmp_path / "deep" / "nested" / "config.toml"
    _merge_toml_config(config_path, {"command": "boyce", "args": []})
    assert config_path.exists()


def test_merge_toml_config_with_env(tmp_path):
    """_merge_toml_config writes env section when env vars are present."""
    config_path = tmp_path / "config.toml"
    entry = {
        "command": "boyce",
        "args": [],
        "env": {"BOYCE_DB_URL": "postgresql://user:pass@host/db"},
    }
    _merge_toml_config(config_path, entry)

    content = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.boyce.env]" in content
    assert 'BOYCE_DB_URL = "postgresql://user:pass@host/db"' in content


def test_merge_toml_config_preserves_existing(tmp_path):
    """_merge_toml_config preserves other mcp_servers entries on re-run."""
    import sys
    if sys.version_info < (3, 11):
        pytest.skip("tomllib requires Python 3.11+")

    config_path = tmp_path / "config.toml"
    # Write initial config with a different server
    initial = (
        "[mcp_servers.other-tool]\n"
        'command = "other"\n'
        "args = []\n"
        "enabled = true\n"
    )
    config_path.write_text(initial, encoding="utf-8")

    _merge_toml_config(config_path, {"command": "boyce", "args": []})

    content = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.boyce]" in content
    assert "[mcp_servers.other-tool]" in content


def test_merge_toml_config_overwrites_existing_boyce(tmp_path):
    """_merge_toml_config updates boyce entry on re-run without duplicating."""
    import sys
    if sys.version_info < (3, 11):
        pytest.skip("tomllib requires Python 3.11+")

    config_path = tmp_path / "config.toml"
    initial = (
        "[mcp_servers.boyce]\n"
        'command = "/old/path/boyce"\n'
        "args = []\n"
        "enabled = true\n"
    )
    config_path.write_text(initial, encoding="utf-8")

    _merge_toml_config(config_path, {"command": "/new/path/boyce", "args": []})

    content = config_path.read_text(encoding="utf-8")
    assert '/new/path/boyce"' in content
    assert "/old/path/boyce" not in content
    # Only one boyce section
    assert content.count("[mcp_servers.boyce]") == 1


def test_noninteractive_codex(tmp_path, capsys):
    """--editors codex works in non-interactive mode."""
    specs = _make_specs_with_codex(tmp_path)
    (tmp_path / ".codex").mkdir()

    with patch("boyce.init_wizard._host_specs", return_value=specs):
        code = _run_wizard_noninteractive(
            editors=["codex"],
            db_url=None,
            skip_db=True,
            skip_sources=True,
            skip_existing=False,
            json_output=True,
        )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert "Codex" in result["editors_configured"]

    # Verify the TOML file was written
    config_path = tmp_path / ".codex" / "config.toml"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.boyce]" in content
