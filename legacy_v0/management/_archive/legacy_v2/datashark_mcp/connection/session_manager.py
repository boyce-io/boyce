"""
Session Manager for DataShark MCP Server

Manages multiple database sessions with isolated connections.
Each session has its own connection and can maintain independent
transaction state.
"""

import logging
import uuid
from typing import Dict, Optional, Any
from datetime import datetime
import psycopg2

logger = logging.getLogger(__name__)


class Session:
    """Represents a single database session with isolated connection."""
    
    def __init__(self, session_id: str, connection_params: Dict[str, Any]):
        self.session_id = session_id
        self.connection_params = connection_params
        self.connection: Optional[Any] = None
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.in_transaction = False
        self._connect()
    
    def _connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params.get('port', 5439),
                database=self.connection_params['database'],
                user=self.connection_params['user'],
                password=self.connection_params['password'],
                sslmode='require',
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            self.connection.set_session(autocommit=True)
            logger.info(f"✅ Session {self.session_id} connected")
        except Exception as e:
            logger.error(f"❌ Failed to connect session {self.session_id}: {e}")
            raise
    
    def execute_query(self, sql: str, params: Optional[tuple] = None):
        """Execute a query in this session."""
        self.last_used = datetime.now()
        
        if not self.connection:
            raise ConnectionError(f"Session {self.session_id} not connected")
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                
                # If it's a SELECT query, fetch results
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return {'columns': columns, 'rows': rows}
                else:
                    # For non-SELECT queries
                    return {'rowcount': cursor.rowcount}
        except Exception as e:
            logger.error(f"❌ Query failed in session {self.session_id}: {e}")
            raise
    
    def begin_transaction(self):
        """Begin a transaction in this session."""
        if not self.connection:
            raise ConnectionError(f"Session {self.session_id} not connected")
        
        self.connection.set_session(autocommit=False)
        self.in_transaction = True
        logger.info(f"✅ Transaction started in session {self.session_id}")
    
    def commit(self):
        """Commit the transaction in this session."""
        if not self.connection:
            raise ConnectionError(f"Session {self.session_id} not connected")
        
        self.connection.commit()
        self.connection.set_session(autocommit=True)
        self.in_transaction = False
        logger.info(f"✅ Transaction committed in session {self.session_id}")
    
    def rollback(self):
        """Rollback the transaction in this session."""
        if not self.connection:
            raise ConnectionError(f"Session {self.session_id} not connected")
        
        self.connection.rollback()
        self.connection.set_session(autocommit=True)
        self.in_transaction = False
        logger.info(f"✅ Transaction rolled back in session {self.session_id}")
    
    def cancel_query(self) -> bool:
        """Cancel the currently executing query in this session."""
        if not self.connection:
            return False
        
        try:
            pid = self.connection.get_backend_pid()
            
            # Create a new connection to issue the cancel command
            cancel_conn = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params.get('port', 5439),
                database=self.connection_params['database'],
                user=self.connection_params['user'],
                password=self.connection_params['password'],
                sslmode='require',
                connect_timeout=5
            )
            
            try:
                with cancel_conn.cursor() as cur:
                    cur.execute("SELECT pg_cancel_backend(%s)", (pid,))
                    result = cur.fetchone()
                    success = result[0] if result else False
                    
                    if success:
                        logger.info(f"✅ Cancelled query in session {self.session_id}")
                    
                    return success
            finally:
                cancel_conn.close()
        
        except Exception as e:
            logger.error(f"❌ Error cancelling query in session {self.session_id}: {e}")
            return False
    
    def close(self):
        """Close this session and its connection."""
        if self.connection:
            try:
                if self.in_transaction:
                    self.rollback()
                self.connection.close()
                logger.info(f"✅ Session {self.session_id} closed")
            except Exception as e:
                logger.error(f"Error closing session {self.session_id}: {e}")
        
        self.connection = None


class SessionManager:
    """
    Manages multiple database sessions.
    
    Allows clients to create isolated sessions with their own
    connections and transaction state.
    """
    
    def __init__(self, connection_params: Dict[str, Any], lazy: bool = False):
        self.connection_params = connection_params
        self.sessions: Dict[str, Session] = {}
        self.default_session_id = 'default'
        self._lazy = lazy
        
        # Create default session (unless lazy mode)
        if not lazy:
            self._create_session(self.default_session_id)
        logger.info(f"✅ Session Manager initialized (lazy={lazy})")
    
    def _create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new session.
        
        Args:
            session_id: Optional session ID. If not provided, generates a UUID.
        
        Returns:
            Session ID
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        if session_id in self.sessions:
            raise ValueError(f"Session {session_id} already exists")
        
        session = Session(session_id, self.connection_params)
        self.sessions[session_id] = session
        
        logger.info(f"✅ Created session {session_id}")
        return session_id
    
    def create_session(self) -> str:
        """
        Create a new session with a generated ID.
        
        Returns:
            Session ID
        """
        return self._create_session()
    
    def get_session(self, session_id: str = 'default') -> Session:
        """
        Get a session by ID.
        
        Args:
            session_id: Session ID. Defaults to 'default'.
        
        Returns:
            Session object
        
        Raises:
            ValueError: If session doesn't exist
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        return self.sessions[session_id]
    
    def close_session(self, session_id: str):
        """
        Close and remove a session.
        
        Args:
            session_id: Session ID to close
        """
        if session_id == self.default_session_id:
            raise ValueError("Cannot close default session")
        
        if session_id in self.sessions:
            self.sessions[session_id].close()
            del self.sessions[session_id]
            logger.info(f"✅ Removed session {session_id}")
    
    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        List all active sessions with their metadata.
        
        Returns:
            Dictionary mapping session IDs to session metadata
        """
        return {
            session_id: {
                'created_at': session.created_at.isoformat(),
                'last_used': session.last_used.isoformat(),
                'in_transaction': session.in_transaction
            }
            for session_id, session in self.sessions.items()
        }
    
    def close_all(self):
        """Close all sessions."""
        for session_id, session in list(self.sessions.items()):
            session.close()
        
        self.sessions.clear()
        logger.info("✅ All sessions closed")
















