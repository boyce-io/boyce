"""
CLI entry point: start the Ingestion Agent (watcher + vector store + embedder).
"""
from __future__ import annotations

from pathlib import Path

from src.ingestion.watcher import Watcher
from src.shared.embedder import LocalEmbedder
from src.shared.store import VectorStore


def main() -> None:
    _script_dir = Path(__file__).resolve().parent
    # Sibling: ../DataShark/DataShark_Lab  OR  Parent: ../DataShark_Lab
    candidates = [
        _script_dir.parent / "DataShark_Lab",
        _script_dir.parent / "DataShark" / "DataShark_Lab",
    ]
    TARGET_DIR = None
    for p in candidates:
        resolved = p.resolve()
        if resolved.is_dir():
            TARGET_DIR = resolved
            break
    if TARGET_DIR is None:
        raise FileNotFoundError("Cannot find DataShark_Lab")

    store = VectorStore()
    store.initialize_db()
    embedder = LocalEmbedder()

    print(f"🦈 DataShark Watcher Active on {TARGET_DIR}...")
    watcher = Watcher(store=store, embedder=embedder)
    watcher.start(TARGET_DIR)


if __name__ == "__main__":
    main()
