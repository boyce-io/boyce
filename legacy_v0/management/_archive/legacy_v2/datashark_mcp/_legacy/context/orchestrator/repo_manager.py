"""
Repository Manager

Tracks extractors per repository and manages state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone


@dataclass
class RepoState:
    """State for a repository."""
    repo_id: str
    system: str
    last_run: Optional[str] = None  # ISO 8601
    manifest_hash: Optional[str] = None  # SHA256 of manifest
    next_run_window: Optional[str] = None  # ISO 8601
    extractor_version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, any]:
        """Convert to dict."""
        return {
            "repo_id": self.repo_id,
            "system": self.system,
            "last_run": self.last_run,
            "manifest_hash": self.manifest_hash,
            "next_run_window": self.next_run_window,
            "extractor_version": self.extractor_version
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> RepoState:
        """Create from dict."""
        return cls(
            repo_id=data["repo_id"],
            system=data["system"],
            last_run=data.get("last_run"),
            manifest_hash=data.get("manifest_hash"),
            next_run_window=data.get("next_run_window"),
            extractor_version=data.get("extractor_version", "1.0.0")
        )


class RepoManager:
    """Manages repository state and extractors."""
    
    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize repository manager.
        
        Args:
            state_file: Path to state file (defaults to .repo_states.json)
        """
        if state_file is None:
            project_root = Path(__file__).resolve().parents[5]
            state_file = project_root / ".repo_states.json"
        
        self.state_file = state_file
        self._repos: Dict[str, RepoState] = {}
        self._load()
    
    def _load(self) -> None:
        """Load repository states."""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for repo_data in data.get("repos", []):
                    state = RepoState.from_dict(repo_data)
                    self._repos[state.repo_id] = state
        else:
            self._repos = {}
    
    def _save(self) -> None:
        """Save repository states."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "repos": [state.to_dict() for state in sorted(self._repos.values(), key=lambda x: x.repo_id)],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    
    def register_repo(self, repo_id: str, system: str, extractor_version: str = "1.0.0") -> RepoState:
        """
        Register a repository.
        
        Args:
            repo_id: Repository identifier
            system: System type
            extractor_version: Extractor version
            
        Returns:
            RepoState object
        """
        state = RepoState(
            repo_id=repo_id,
            system=system,
            extractor_version=extractor_version
        )
        self._repos[repo_id] = state
        self._save()
        return state
    
    def get_repo(self, repo_id: str) -> Optional[RepoState]:
        """Get repository state."""
        return self._repos.get(repo_id)
    
    def update_repo(self, repo_id: str, manifest_hash: str) -> None:
        """
        Update repository state after extraction.
        
        Args:
            repo_id: Repository identifier
            manifest_hash: SHA256 hash of manifest
        """
        if repo_id in self._repos:
            self._repos[repo_id].last_run = datetime.now(timezone.utc).isoformat()
            self._repos[repo_id].manifest_hash = manifest_hash
            self._save()
    
    def list_repos(self) -> list[RepoState]:
        """List all repositories (sorted by repo_id)."""
        return sorted(self._repos.values(), key=lambda x: x.repo_id)

