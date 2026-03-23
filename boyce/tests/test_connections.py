"""Tests for ConnectionStore — DSN persistence across server restarts."""

import json
from pathlib import Path

from boyce.connections import ConnectionStore


# ---------------------------------------------------------------------------
# ConnectionStore.save / load
# ---------------------------------------------------------------------------

def test_save_and_load(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("pagila", "postgresql://u:p@h:5432/pagila")
    assert store.load("pagila") == "postgresql://u:p@h:5432/pagila"


def test_save_stores_raw_dsn(tmp_path: Path):
    """Raw DSN with password is stored as-is (_local_context is gitignored)."""
    store = ConnectionStore(tmp_path)
    dsn = "postgresql://user:secret@host:5432/db"
    store.save("snap", dsn)
    with open(tmp_path / "connections.json") as f:
        data = json.load(f)
    assert data["snap"]["dsn"] == dsn


def test_load_missing_returns_none(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    assert store.load("nonexistent") is None


def test_save_creates_file(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("test", "postgresql://u:p@h:5432/test")
    assert (tmp_path / "connections.json").exists()


def test_save_overwrites(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("snap", "postgresql://u:p@h:5432/old")
    store.save("snap", "postgresql://u:p@h:5432/new")
    assert store.load("snap") == "postgresql://u:p@h:5432/new"


def test_save_preserves_created_timestamp(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("snap", "postgresql://u:p@h:5432/db")
    with open(tmp_path / "connections.json") as f:
        data1 = json.load(f)
    created1 = data1["snap"]["created"]

    store.save("snap", "postgresql://u:p@h:5432/db2")
    with open(tmp_path / "connections.json") as f:
        data2 = json.load(f)
    assert data2["snap"]["created"] == created1


def test_save_creates_directory(tmp_path: Path):
    nested = tmp_path / "deep" / "dir"
    store = ConnectionStore(nested)
    store.save("snap", "postgresql://u:p@h:5432/db")
    assert store.load("snap") == "postgresql://u:p@h:5432/db"


# ---------------------------------------------------------------------------
# ConnectionStore.touch
# ---------------------------------------------------------------------------

def test_touch_updates_last_used(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("snap", "postgresql://u:p@h:5432/db")
    with open(tmp_path / "connections.json") as f:
        ts1 = json.load(f)["snap"]["last_used"]

    store.touch("snap")
    with open(tmp_path / "connections.json") as f:
        ts2 = json.load(f)["snap"]["last_used"]

    assert ts2 >= ts1


def test_touch_nonexistent_is_noop(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.touch("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# ConnectionStore.remove
# ---------------------------------------------------------------------------

def test_remove_existing(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("snap", "postgresql://u:p@h:5432/db")
    assert store.remove("snap") is True
    assert store.load("snap") is None


def test_remove_nonexistent(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    assert store.remove("nonexistent") is False


# ---------------------------------------------------------------------------
# ConnectionStore.list_all — redaction at display time only
# ---------------------------------------------------------------------------

def test_list_all_returns_redacted(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("a", "postgresql://u:secret@h:5432/a")
    store.save("b", "postgresql://u:hunter2@h:5432/b")
    listing = store.list_all()
    assert "a" in listing
    assert "b" in listing
    assert "secret" not in listing["a"]["dsn_redacted"]
    assert "hunter2" not in listing["b"]["dsn_redacted"]
    assert "***" in listing["a"]["dsn_redacted"]


def test_list_all_empty(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    assert store.list_all() == {}


# ---------------------------------------------------------------------------
# ConnectionStore.snapshot_names
# ---------------------------------------------------------------------------

def test_snapshot_names(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    store.save("alpha", "postgresql://u:p@h:5432/alpha")
    store.save("beta", "postgresql://u:p@h:5432/beta")
    names = store.snapshot_names()
    assert set(names) == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_corrupted_file_returns_empty(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    (tmp_path / "connections.json").write_text("not json!!!")
    assert store.load("anything") is None
    assert store.list_all() == {}


def test_missing_dsn_key_returns_none(tmp_path: Path):
    store = ConnectionStore(tmp_path)
    (tmp_path / "connections.json").write_text(json.dumps({"snap": {"source": "test"}}))
    assert store.load("snap") is None
