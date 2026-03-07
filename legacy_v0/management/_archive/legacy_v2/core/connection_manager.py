"""
Connection Manager for Redshift
Handles secure credential management and connection pooling.
"""

import os
from typing import Optional
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor


class RedshiftConnectionManager:
    """
    Manages Redshift database connections.
    Designed for data scientists who think in pandas, not connection pools.
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize connection manager.
        Falls back to environment variables if parameters not provided.
        
        Args:
            host: Redshift cluster endpoint
            port: Port number (default 5439)
            database: Database name
            user: Username
            password: Password
        """
        self.host = host or os.getenv("REDSHIFT_HOST")
        self.port = port or int(os.getenv("REDSHIFT_PORT", "5439"))
        self.database = database or os.getenv("REDSHIFT_DATABASE")
        self.user = user or os.getenv("REDSHIFT_USER")
        self.password = password or os.getenv("REDSHIFT_PASSWORD")
        
        # Validate we have all required credentials
        self._validate_credentials()
    
    def _validate_credentials(self):
        """Ensure all required credentials are present."""
        missing = []
        if not self.host:
            missing.append("REDSHIFT_HOST")
        if not self.database:
            missing.append("REDSHIFT_DATABASE")
        if not self.user:
            missing.append("REDSHIFT_USER")
        if not self.password:
            missing.append("REDSHIFT_PASSWORD")
        
        if missing:
            raise ValueError(
                f"Missing required credentials: {', '.join(missing)}. "
                "Set them as environment variables or pass as parameters."
            )
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Automatically handles connection cleanup.
        
        Usage:
            with manager.get_connection() as conn:
                # do stuff with conn
        """
        conn = None
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                sslmode='require',  # Redshift requires SSL
                connect_timeout=10,
            )
            yield conn
        except psycopg2.OperationalError as e:
            raise ConnectionError(
                f"Failed to connect to Redshift: {str(e)}\n"
                "Check your credentials and network access."
            ) from e
        finally:
            if conn:
                conn.close()
    
    def test_connection(self) -> dict:
        """
        Test database connection and return basic info.
        Useful for setup validation.
        
        Returns:
            dict with connection status and database info
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version(), current_database(), current_user;")
                    version, db, user = cur.fetchone()
                    return {
                        "success": True,
                        "database": db,
                        "user": user,
                        "version": version.split()[0:2],  # Just Redshift version
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

