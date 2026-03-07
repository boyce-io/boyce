"""
Query History

SQLite-based query history storage.
Persists across MCP server restarts.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class QueryHistory:
    """
    SQLite-based query history storage.
    
    Features:
    - Persists across MCP server restarts
    - Fast lookups (indexed by timestamp)
    - Tracks success/failure and performance
    - Supports filtering and search
    """
    
    def __init__(self, db_path: str = "query_history.db"):
        """
        Initialize query history database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        
        logger.info(f"Initializing query history at {self.db_path}")
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database"""
        # TODO: Day 6 implementation
        self.conn = sqlite3.connect(self.db_path)
        
        # Create queries table
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sql TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                duration_ms REAL,
                row_count INTEGER,
                success BOOLEAN NOT NULL,
                error TEXT,
                user TEXT
            )
        ''')
        
        # Create index for fast lookups
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON queries(timestamp DESC)
        ''')
        
        self.conn.commit()
        logger.info("Query history database initialized")
    
    def add_query(
        self,
        sql: str,
        duration_ms: float,
        row_count: int,
        success: bool,
        error: Optional[str] = None,
        user: Optional[str] = None
    ):
        """
        Record query execution.
        
        Args:
            sql: SQL query executed
            duration_ms: Execution time in milliseconds
            row_count: Number of rows returned
            success: Whether query succeeded
            error: Error message if failed
            user: User who executed query
        """
        # TODO: Day 6 implementation
        try:
            self.conn.execute('''
                INSERT INTO queries (sql, timestamp, duration_ms, row_count, success, error, user)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (sql, datetime.now(), duration_ms, row_count, success, error, user))
            
            self.conn.commit()
            logger.debug(f"Recorded query: {sql[:50]}... (success={success})")
            
        except Exception as e:
            logger.error(f"Failed to record query: {e}")
    
    def get_recent(self, limit: int = 50) -> List[Dict]:
        """
        Get recent queries.
        
        Args:
            limit: Maximum number of queries to return
        
        Returns:
            List of query dicts with:
            - sql: Query text
            - timestamp: When executed
            - duration_ms: Execution time
            - row_count: Rows returned
            - success: Whether succeeded
            - error: Error message if failed
        """
        # TODO: Day 6 implementation
        try:
            cursor = self.conn.execute('''
                SELECT sql, timestamp, duration_ms, row_count, success, error
                FROM queries
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            results = [{
                'sql': row[0],
                'timestamp': row[1],
                'duration_ms': row[2],
                'row_count': row[3],
                'success': bool(row[4]),
                'error': row[5]
            } for row in cursor.fetchall()]
            
            logger.debug(f"Retrieved {len(results)} recent queries")
            return results
            
        except Exception as e:
            logger.error(f"Failed to get recent queries: {e}")
            return []
    
    def get_successful(self, limit: int = 50) -> List[Dict]:
        """Get recent successful queries"""
        try:
            cursor = self.conn.execute('''
                SELECT sql, timestamp, duration_ms, row_count
                FROM queries
                WHERE success = 1
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            return [{
                'sql': row[0],
                'timestamp': row[1],
                'duration_ms': row[2],
                'row_count': row[3]
            } for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Failed to get successful queries: {e}")
            return []
    
    def get_failed(self, limit: int = 50) -> List[Dict]:
        """Get recent failed queries"""
        try:
            cursor = self.conn.execute('''
                SELECT sql, timestamp, error
                FROM queries
                WHERE success = 0
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            return [{
                'sql': row[0],
                'timestamp': row[1],
                'error': row[2]
            } for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Failed to get failed queries: {e}")
            return []
    
    def close(self):
        """Close database connection"""
        if self.conn:
            logger.info("Closing query history database")
            self.conn.close()
            logger.info("Query history database closed")


