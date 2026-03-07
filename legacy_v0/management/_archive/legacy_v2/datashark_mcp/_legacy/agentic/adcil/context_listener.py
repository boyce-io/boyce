"""
Context Listener

Monitors repositories and databases for changes, triggering ADCIL re-inference.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ChangeEvent:
    """Represents a change detected in a monitored source."""
    source_type: str  # "repository" | "database"
    source_id: str
    change_type: str  # "schema_change" | "new_table" | "column_added" | "commit"
    timestamp: datetime
    details: Dict[str, any]
    content_hash: Optional[str] = None


class ContextListener:
    """
    Monitors repositories and databases for changes.
    
    Tracks:
    - Repository commits (git-based)
    - Database schema changes (via catalog queries)
    - File modifications in monitored paths
    """
    
    def __init__(self, instance_path: Path):
        """
        Initialize context listener.
        
        Args:
            instance_path: Path to instance directory
        """
        self.instance_path = instance_path
        self.monitored_repos: Dict[str, Dict[str, any]] = {}
        self.monitored_databases: Dict[str, Dict[str, any]] = {}
        self.last_check_timestamp: Optional[datetime] = None
        
    def register_repository(self, repo_id: str, repo_path: str, config: Dict[str, any] = None):
        """Register a repository for monitoring."""
        self.monitored_repos[repo_id] = {
            "path": Path(repo_path).expanduser(),
            "last_commit": None,
            "config": config or {}
        }
        logger.info(f"Registered repository: {repo_id} at {repo_path}")
    
    def register_database(self, db_id: str, db_config: Dict[str, any]):
        """Register a database for schema change monitoring."""
        self.monitored_databases[db_id] = {
            "config": db_config,
            "last_schema_hash": None
        }
        logger.info(f"Registered database: {db_id}")
    
    def check_changes(self, since: Optional[datetime] = None) -> List[ChangeEvent]:
        """
        Check for changes in all monitored sources.
        
        Args:
            since: Only check changes after this timestamp (if None, check all)
            
        Returns:
            List of change events
        """
        events: List[ChangeEvent] = []
        
        # Check repositories
        for repo_id, repo_info in self.monitored_repos.items():
            repo_events = self._check_repository_changes(repo_id, repo_info, since)
            events.extend(repo_events)
        
        # Check databases
        for db_id, db_info in self.monitored_databases.items():
            db_events = self._check_database_changes(db_id, db_info, since)
            events.extend(db_events)
        
        self.last_check_timestamp = datetime.utcnow()
        
        if events:
            logger.info(f"Detected {len(events)} change events")
        else:
            logger.debug("No changes detected")
        
        return events
    
    def _check_repository_changes(
        self, 
        repo_id: str, 
        repo_info: Dict[str, any], 
        since: Optional[datetime]
    ) -> List[ChangeEvent]:
        """Check for changes in a git repository."""
        events: List[ChangeEvent] = []
        repo_path = repo_info["path"]
        
        if not repo_path.exists():
            logger.warning(f"Repository path does not exist: {repo_path}")
            return events
        
        # Check if it's a git repository
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            logger.debug(f"Not a git repository: {repo_path}")
            return events
        
        try:
            import subprocess
            
            # Get latest commit
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H|%ct", "--"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                commit_hash, commit_time = result.stdout.strip().split("|")
                commit_timestamp = datetime.fromtimestamp(int(commit_time))
                
                last_commit = repo_info.get("last_commit")
                if last_commit != commit_hash:
                    # Check what changed
                    if last_commit:
                        # Get diff since last commit
                        diff_result = subprocess.run(
                            ["git", "diff", "--name-status", last_commit, commit_hash],
                            cwd=str(repo_path),
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        changed_files = diff_result.stdout.strip().split("\n") if diff_result.returncode == 0 else []
                    else:
                        changed_files = []
                    
                    events.append(ChangeEvent(
                        source_type="repository",
                        source_id=repo_id,
                        change_type="commit",
                        timestamp=commit_timestamp,
                        details={
                            "commit": commit_hash,
                            "changed_files": changed_files
                        },
                        content_hash=commit_hash
                    ))
                    
                    repo_info["last_commit"] = commit_hash
        except Exception as e:
            logger.warning(f"Failed to check repository {repo_id}: {e}")
        
        return events
    
    def _check_database_changes(
        self,
        db_id: str,
        db_info: Dict[str, any],
        since: Optional[datetime]
    ) -> List[ChangeEvent]:
        """Check for schema changes in a database."""
        events: List[ChangeEvent] = []
        
        # For now, we'll use a simple approach: hash the schema
        # In production, this would query information_schema
        try:
            # Placeholder: would query actual database schema
            # For now, return empty (would need database adapter)
            logger.debug(f"Database schema change detection not yet implemented for {db_id}")
        except Exception as e:
            logger.warning(f"Failed to check database {db_id}: {e}")
        
        return events
    
    def get_state(self) -> Dict[str, any]:
        """Get current listener state for persistence."""
        return {
            "monitored_repos": {
                repo_id: {"last_commit": info.get("last_commit")}
                for repo_id, info in self.monitored_repos.items()
            },
            "monitored_databases": {
                db_id: {"last_schema_hash": info.get("last_schema_hash")}
                for db_id, info in self.monitored_databases.items()
            },
            "last_check": self.last_check_timestamp.isoformat() if self.last_check_timestamp else None
        }
    
    def load_state(self, state: Dict[str, any]):
        """Load listener state from persistence."""
        for repo_id, repo_state in state.get("monitored_repos", {}).items():
            if repo_id in self.monitored_repos:
                self.monitored_repos[repo_id]["last_commit"] = repo_state.get("last_commit")
        
        for db_id, db_state in state.get("monitored_databases", {}).items():
            if db_id in self.monitored_databases:
                self.monitored_databases[db_id]["last_schema_hash"] = db_state.get("last_schema_hash")
        
        last_check_str = state.get("last_check")
        if last_check_str:
            self.last_check_timestamp = datetime.fromisoformat(last_check_str)

