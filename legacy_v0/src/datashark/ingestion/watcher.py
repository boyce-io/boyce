"""
Production-Grade File Watcher for DataShark Ingestion Engine

Monitors project directories for changes to SQL, YAML, and LookML files.
Implements debouncing to prevent duplicate events and handles OS-specific errors gracefully.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    raise ImportError(
        "watchdog is required for file watching. Install with: pip install watchdog"
    )

logger = logging.getLogger(__name__)


class DebouncedEventHandler(FileSystemEventHandler):
    """
    Event handler that debounces file system events.
    
    Prevents multiple rapid-fire events (e.g., 3 saves for one file edit)
    by collecting events and only firing the callback after a quiet period.
    """

    def __init__(
        self,
        callback: Callable[[Path], None],
        debounce_seconds: float = 0.5,
    ):
        """
        Initialize the debounced event handler.

        Args:
            callback: Function to call with the file path when events settle.
            debounce_seconds: Time to wait after last event before firing callback.
        """
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.pending_events: dict[Path, float] = {}
        self.lock = threading.Lock()
        self.timer: Optional[threading.Timer] = None

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        self._schedule_event(Path(event.src_path))

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        self._schedule_event(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return
        self._schedule_event(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events."""
        if event.is_directory:
            return
        # Handle both source and destination
        if hasattr(event, "src_path"):
            self._schedule_event(Path(event.src_path))
        if hasattr(event, "dest_path"):
            self._schedule_event(Path(event.dest_path))

    def _schedule_event(self, file_path: Path) -> None:
        """Schedule a debounced event for the given file path."""
        with self.lock:
            now = time.time()
            self.pending_events[file_path] = now

            # Cancel existing timer
            if self.timer is not None:
                self.timer.cancel()

            # Schedule new timer
            self.timer = threading.Timer(
                self.debounce_seconds, self._fire_pending_events
            )
            self.timer.start()

    def _fire_pending_events(self) -> None:
        """Fire callbacks for all pending events."""
        with self.lock:
            if not self.pending_events:
                return

            # Get all unique file paths that have pending events
            pending_paths = list(self.pending_events.keys())
            self.pending_events.clear()
            self.timer = None

        # Fire callbacks outside the lock to avoid deadlocks
        for file_path in pending_paths:
            try:
                # Only call callback if file still exists (for delete events, we still notify)
                if file_path.exists() or file_path not in pending_paths:
                    self.callback(file_path)
            except Exception as e:
                logger.error(f"Error in callback for {file_path}: {e}", exc_info=True)


class ProjectWatcher:
    """
    Production-grade file watcher for monitoring project directories.

    Handles OS-specific errors gracefully and implements debouncing to prevent
    duplicate events from rapid file saves.
    """

    # File extensions to monitor
    MONITORED_EXTENSIONS = {".sql", ".yml", ".yaml", ".lkml", ".lookml", ".json"}

    # Directories to ignore
    IGNORED_DIRS = {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",  # dbt build artifacts (except manifest.json)
    }

    def __init__(
        self,
        root_path: Path,
        on_change: Callable[[Path], None],
        debounce_seconds: float = 0.5,
    ):
        """
        Initialize the project watcher.

        Args:
            root_path: Root directory to watch.
            on_change: Callback function called when a monitored file changes.
                      Signature: `on_change(file_path: Path) -> None`
            debounce_seconds: Time to wait after last event before firing callback.
        """
        self.root_path = Path(root_path).resolve()
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds

        self.observer: Optional[Observer] = None
        self.event_handler: Optional[DebouncedEventHandler] = None
        self._is_watching = False
        self._lock = threading.Lock()

        if not self.root_path.exists():
            raise ValueError(f"Root path does not exist: {self.root_path}")
        if not self.root_path.is_dir():
            raise ValueError(f"Root path is not a directory: {self.root_path}")

    def start(self) -> None:
        """Start watching the project directory."""
        with self._lock:
            if self._is_watching:
                logger.warning("Watcher is already running")
                return

            try:
                self.event_handler = DebouncedEventHandler(
                    self._filtered_callback, self.debounce_seconds
                )
                self.observer = Observer()
                self.observer.schedule(
                    self.event_handler, str(self.root_path), recursive=True
                )
                self.observer.start()
                self._is_watching = True
                logger.info(f"Started watching: {self.root_path}")
            except PermissionError as e:
                logger.error(
                    f"Permission denied while starting watcher for {self.root_path}: {e}"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to start watcher: {e}", exc_info=True)
                raise

    def stop(self) -> None:
        """Stop watching the project directory."""
        with self._lock:
            if not self._is_watching:
                return

            if self.observer is not None:
                try:
                    self.observer.stop()
                    self.observer.join(timeout=5.0)
                except Exception as e:
                    logger.warning(f"Error stopping observer: {e}")

            if self.event_handler is not None and self.event_handler.timer is not None:
                self.event_handler.timer.cancel()

            self._is_watching = False
            logger.info("Stopped watching")

    def is_watching(self) -> bool:
        """Check if the watcher is currently active."""
        with self._lock:
            return self._is_watching

    def _filtered_callback(self, file_path: Path) -> None:
        """
        Filter callback that only fires for monitored file types.

        This prevents callbacks for irrelevant files (e.g., .pyc, .log).
        """
        try:
            # Check if file extension is monitored
            if file_path.suffix.lower() not in self.MONITORED_EXTENSIONS:
                return

            # Check if file is in an ignored directory
            path_parts = file_path.parts
            for ignored_dir in self.IGNORED_DIRS:
                if ignored_dir in path_parts:
                    # Special case: allow manifest.json in target/
                    if ignored_dir == "target" and file_path.name == "manifest.json":
                        pass  # Allow it
                    else:
                        return

            # File passed all filters, call the user's callback
            self.on_change(file_path)
        except PermissionError:
            logger.warning(f"Permission denied accessing {file_path}")
        except Exception as e:
            logger.error(f"Error in filtered callback for {file_path}: {e}", exc_info=True)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
