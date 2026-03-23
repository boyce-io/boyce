"""Tests for boyce.version_check — version lifecycle management."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from boyce.version_check import (
    _cache_is_fresh,
    _classify_update,
    _detect_install_method,
    _fetch_pypi_info,
    _get_restart_instructions,
    _read_cache,
    _write_cache,
    check_running_vs_installed,
    fetch_latest_version,
    get_cached_version_info,
    get_version_info,
    run_update,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pypi_response(version: str = "0.2.0", upload_time: str | None = None):
    """Build a mock PyPI JSON response."""
    if upload_time is None:
        upload_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    return json.dumps({
        "info": {"version": version},
        "releases": {
            version: [{"upload_time_iso_8601": upload_time}],
        },
    }).encode()


def _mock_urlopen(response_bytes):
    """Return a mock context manager that yields response_bytes."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_bytes
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# _fetch_pypi_info / fetch_latest_version
# ---------------------------------------------------------------------------

class TestFetchLatestVersion:
    def test_success(self):
        resp = _mock_urlopen(_make_pypi_response("0.3.0"))
        with patch("urllib.request.urlopen", return_value=resp):
            result = fetch_latest_version()
        assert result == "0.3.0"

    def test_timeout(self):
        import socket
        with patch("urllib.request.urlopen", side_effect=socket.timeout):
            result = fetch_latest_version()
        assert result is None

    def test_network_error(self):
        from urllib.error import URLError
        with patch("urllib.request.urlopen", side_effect=URLError("fail")):
            result = fetch_latest_version()
        assert result is None

    def test_bad_json(self):
        mock_resp = _mock_urlopen(b"not json")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_latest_version()
        assert result is None

    def test_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("BOYCE_DISABLE_UPDATE_CHECK", "1")
        # Should not make any network call
        result = fetch_latest_version()
        assert result is None

    def test_pypi_info_returns_upload_time(self):
        ts = "2026-03-20T12:00:00+00:00"
        resp = _mock_urlopen(_make_pypi_response("0.2.0", upload_time=ts))
        with patch("urllib.request.urlopen", return_value=resp):
            info = _fetch_pypi_info()
        assert info is not None
        assert info["version"] == "0.2.0"
        assert info["upload_time"] == ts


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

class TestDiskCache:
    def test_write_and_read(self, tmp_path):
        data = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "latest_version": "0.2.0",
            "current_version_at_check": "0.1.0",
        }
        _write_cache(tmp_path, data)
        result = _read_cache(tmp_path)
        assert result is not None
        assert result["latest_version"] == "0.2.0"

    def test_cache_expired(self, tmp_path):
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        data = {"last_check": old.isoformat(), "latest_version": "0.2.0"}
        _write_cache(tmp_path, data)
        assert not _cache_is_fresh(data)

    def test_cache_fresh(self, tmp_path):
        now = datetime.now(timezone.utc) - timedelta(hours=1)
        data = {"last_check": now.isoformat(), "latest_version": "0.2.0"}
        _write_cache(tmp_path, data)
        assert _cache_is_fresh(data)

    def test_write_failure_non_fatal(self, tmp_path):
        """Cache write failure should not raise."""
        bad_path = tmp_path / "nonexistent" / "deep" / "dir"
        # _write_cache creates dirs, so this actually works.
        # Instead, mock open to fail.
        with patch("builtins.open", side_effect=OSError("disk full")):
            _write_cache(tmp_path, {"test": True})  # Should not raise

    def test_read_no_file(self, tmp_path):
        result = _read_cache(tmp_path)
        assert result is None

    def test_read_corrupt_file(self, tmp_path):
        (tmp_path / "version_check.json").write_text("not json")
        result = _read_cache(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# get_cached_version_info
# ---------------------------------------------------------------------------

class TestGetCachedVersionInfo:
    def test_no_cache(self, tmp_path):
        result = get_cached_version_info(tmp_path)
        assert result is None

    def test_reads_cache(self, tmp_path):
        data = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "latest_version": "0.2.0",
        }
        _write_cache(tmp_path, data)
        with patch("boyce.__version__","0.1.0"):
            result = get_cached_version_info(tmp_path)
        assert result is not None
        assert result["update_available"] is True
        assert result["latest"] == "0.2.0"


# ---------------------------------------------------------------------------
# get_version_info
# ---------------------------------------------------------------------------

class TestGetVersionInfo:
    def test_uses_fresh_cache(self, tmp_path):
        """If cache is fresh, should NOT call PyPI."""
        data = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "latest_version": "0.2.0",
            "current_version_at_check": "0.1.0",
        }
        _write_cache(tmp_path, data)
        with patch("boyce.__version__","0.1.0"), \
             patch("boyce.version_check._fetch_pypi_info") as mock_fetch:
            result = get_version_info(tmp_path)
        mock_fetch.assert_not_called()
        assert result["latest"] == "0.2.0"
        assert result["update_available"] is True

    def test_stale_cache_fetches(self, tmp_path):
        """If cache is stale, should call PyPI."""
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        data = {
            "last_check": old.isoformat(),
            "latest_version": "0.1.5",
        }
        _write_cache(tmp_path, data)
        resp = _mock_urlopen(_make_pypi_response("0.2.0"))
        with patch("boyce.__version__","0.1.0"), \
             patch("urllib.request.urlopen", return_value=resp):
            result = get_version_info(tmp_path)
        assert result["latest"] == "0.2.0"

    def test_disabled_by_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BOYCE_DISABLE_UPDATE_CHECK", "1")
        with patch("boyce.__version__","0.1.0"):
            result = get_version_info(tmp_path)
        assert result["latest"] is None
        assert result["update_available"] is False


# ---------------------------------------------------------------------------
# _classify_update
# ---------------------------------------------------------------------------

class TestClassifyUpdate:
    def test_major(self):
        assert _classify_update("0.1.0", "1.0.0") == "major"

    def test_minor(self):
        assert _classify_update("0.1.0", "0.2.0") == "minor"

    def test_patch(self):
        assert _classify_update("0.1.0", "0.1.1") == "patch"

    def test_downgrade(self):
        assert _classify_update("0.2.0", "0.1.0") is None

    def test_equal(self):
        assert _classify_update("0.1.0", "0.1.0") is None


# ---------------------------------------------------------------------------
# check_running_vs_installed
# ---------------------------------------------------------------------------

class TestRunningVsInstalled:
    def test_match(self):
        with patch("boyce.__version__","0.1.0"), \
             patch("importlib.metadata.version", return_value="0.1.0"):
            result = check_running_vs_installed()
        assert result["restart_required"] is False
        assert result["running"] == "0.1.0"
        assert result["installed"] == "0.1.0"

    def test_mismatch(self):
        with patch("boyce.__version__","0.1.0"), \
             patch("importlib.metadata.version", return_value="0.2.0"):
            result = check_running_vs_installed()
        assert result["restart_required"] is True


# ---------------------------------------------------------------------------
# _detect_install_method
# ---------------------------------------------------------------------------

class TestDetectInstallMethod:
    def test_pipx(self):
        mock_result = MagicMock()
        mock_result.stdout = "boyce 0.1.0\n"
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/pipx" if x == "pipx" else None), \
             patch("subprocess.run", return_value=mock_result):
            method, cmd = _detect_install_method()
        assert method == "pipx"
        assert "upgrade" in cmd

    def test_uv(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/uv" if x == "uv" else None):
            method, cmd = _detect_install_method()
        assert method == "uv"
        assert "uv" in cmd[0]

    def test_pip_fallback(self):
        with patch("shutil.which", return_value=None):
            method, cmd = _detect_install_method()
        assert method == "pip"
        assert sys.executable in cmd


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

class TestCooldown:
    def test_fresh_release_triggers_cooldown(self, tmp_path):
        """Release < 48h old should set cooldown_active."""
        recent = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        resp = _mock_urlopen(_make_pypi_response("0.2.0", upload_time=recent))
        with patch("boyce.__version__","0.1.0"), \
             patch("urllib.request.urlopen", return_value=resp):
            result = get_version_info(tmp_path)
        assert result["cooldown_active"] is True

    def test_old_release_no_cooldown(self, tmp_path):
        """Release > 48h old should NOT set cooldown_active."""
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        resp = _mock_urlopen(_make_pypi_response("0.2.0", upload_time=old))
        with patch("boyce.__version__","0.1.0"), \
             patch("urllib.request.urlopen", return_value=resp):
            result = get_version_info(tmp_path)
        assert result["cooldown_active"] is False


# ---------------------------------------------------------------------------
# Nudge filtering
# ---------------------------------------------------------------------------

class TestNudgeFiltering:
    def test_patch_suppressed(self):
        """Patch-only updates should not be 'minor' or 'major'."""
        assert _classify_update("0.1.0", "0.1.1") == "patch"
        # Caller should suppress environment_suggestions for "patch"

    def test_minor_shown(self):
        assert _classify_update("0.1.0", "0.2.0") == "minor"
        # Caller should include in environment_suggestions


# ---------------------------------------------------------------------------
# Restart instructions
# ---------------------------------------------------------------------------

class TestRestartInstructions:
    def test_with_detected_editors(self):
        from boyce.init_wizard import MCPHost

        mock_hosts = [
            MCPHost(name="Cursor", config_path=Path("/tmp/c"),
                    project_level=True, exists=True, has_boyce=True),
        ]
        with patch("boyce.init_wizard.detect_hosts", return_value=mock_hosts):
            result = _get_restart_instructions()
        assert "Cursor" in result
        assert "Settings" in result

    def test_no_editors_shows_all(self):
        with patch("boyce.init_wizard.detect_hosts", return_value=[]):
            result = _get_restart_instructions()
        assert "Claude Code" in result
        assert "Cursor" in result


# ---------------------------------------------------------------------------
# run_update
# ---------------------------------------------------------------------------

class TestRunUpdate:
    def test_already_latest(self, capsys):
        with patch("boyce.__version__","0.2.0"), \
             patch("boyce.version_check.fetch_latest_version", return_value="0.2.0"):
            code = run_update(yes=True)
        assert code == 1
        assert "up to date" in capsys.readouterr().out

    def test_success(self, capsys):
        mock_subprocess = MagicMock()
        mock_subprocess.returncode = 0
        mock_verify = MagicMock()
        mock_verify.stdout = "boyce 0.3.0"

        with patch("boyce.__version__","0.1.0"), \
             patch("boyce.version_check.fetch_latest_version", return_value="0.3.0"), \
             patch("boyce.version_check._detect_install_method",
                   return_value=("pip", [sys.executable, "-m", "pip", "install", "--upgrade", "boyce"])), \
             patch("subprocess.run", side_effect=[mock_subprocess, mock_verify]), \
             patch("boyce.version_check._get_restart_instructions", return_value="Restart editor."):
            code = run_update(yes=True)
        assert code == 0
        output = capsys.readouterr().out
        assert "0.3.0" in output

    def test_upgrade_failure(self, capsys):
        mock_subprocess = MagicMock()
        mock_subprocess.returncode = 1

        with patch("boyce.__version__","0.1.0"), \
             patch("boyce.version_check.fetch_latest_version", return_value="0.3.0"), \
             patch("boyce.version_check._detect_install_method",
                   return_value=("pip", ["pip", "install", "--upgrade", "boyce"])), \
             patch("subprocess.run", return_value=mock_subprocess):
            code = run_update(yes=True)
        assert code == 2

    def test_network_failure(self, capsys):
        with patch("boyce.__version__","0.1.0"), \
             patch("boyce.version_check.fetch_latest_version", return_value=None):
            code = run_update(yes=True)
        assert code == 2
        assert "PyPI" in capsys.readouterr().out
