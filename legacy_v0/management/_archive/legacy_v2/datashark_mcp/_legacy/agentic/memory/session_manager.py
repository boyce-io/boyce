"""
Session Manager

Manages agent sessions with unique IDs and query history.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass
class QueryHistory:
    """Query history entry."""
    query_id: str
    timestamp: str  # ISO 8601
    query: str
    dsl_query: str
    result_count: int
    runtime_ms: float


@dataclass
class Session:
    """Agent session."""
    session_id: str
    created_at: str  # ISO 8601
    last_activity: str  # ISO 8601
    queries: List[QueryHistory]
    max_history: int = 100
    
    def to_dict(self) -> Dict[str, any]:
        """Convert to dict."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "queries": [asdict(q) for q in self.queries]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> Session:
        """Create from dict."""
        queries = [QueryHistory(**q) for q in data.get("queries", [])]
        return cls(
            session_id=data["session_id"],
            created_at=data["created_at"],
            last_activity=data["last_activity"],
            queries=queries,
            max_history=data.get("max_history", 100)
        )


class SessionManager:
    """Manages agent sessions."""
    
    def __init__(self, sessions_file: Optional[Path] = None):
        """
        Initialize session manager.
        
        Args:
            sessions_file: Path to sessions.json (defaults to docs/sessions.json)
        """
        if sessions_file is None:
            project_root = Path(__file__).resolve().parents[5]
            sessions_file = project_root / "docs" / "sessions" / "sessions.json"
        
        self.sessions_file = sessions_file
        self._sessions: Dict[str, Session] = {}
        self._load()
    
    def _load(self) -> None:
        """Load sessions from file."""
        if self.sessions_file.exists():
            with open(self.sessions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for session_data in data.get("sessions", []):
                    session = Session.from_dict(session_data)
                    self._sessions[session.session_id] = session
        else:
            self._sessions = {}
    
    def _save(self) -> None:
        """Save sessions to file."""
        self.sessions_file.parent.mkdir(parents=True, exist_ok=True)
        
        sessions_list = [
            session.to_dict()
            for session in sorted(self._sessions.values(), key=lambda x: x.created_at)
        ]
        
        data = {
            "sessions": sessions_list,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(self.sessions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    
    def create_session(self) -> Session:
        """
        Create new session.
        
        Returns:
            Session object
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        session = Session(
            session_id=session_id,
            created_at=now,
            last_activity=now,
            queries=[]
        )
        
        self._sessions[session_id] = session
        self._save()
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def add_query(
        self,
        session_id: str,
        query: str,
        dsl_query: str,
        result_count: int,
        runtime_ms: float
    ) -> None:
        """
        Add query to session history.
        
        Args:
            session_id: Session ID
            query: Natural language query
            dsl_query: Translated DSL query
            result_count: Number of results
            runtime_ms: Execution time
        """
        if session_id not in self._sessions:
            return
        
        session = self._sessions[session_id]
        
        query_history = QueryHistory(
            query_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
            dsl_query=dsl_query,
            result_count=result_count,
            runtime_ms=runtime_ms
        )
        
        session.queries.append(query_history)
        session.last_activity = datetime.now(timezone.utc).isoformat()
        
        # Trim history if needed
        if len(session.queries) > session.max_history:
            session.queries = session.queries[-session.max_history:]
        
        self._save()
    
    def list_sessions(self) -> List[Session]:
        """List all sessions (sorted by created_at)."""
        return sorted(self._sessions.values(), key=lambda x: x.created_at)

