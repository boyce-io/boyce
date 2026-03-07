"""
Connection Pooling

Manages database connection pool with auto-reconnect.
Handles Redshift connection timeouts and credential rotation.
"""

import logging
import time
from typing import Optional
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Manages connection pool with auto-reconnect.
    
    Features:
    - Handles Redshift connection timeouts (30 min idle)
    - Auto-reconnect with exponential backoff
    - Supports concurrent tool calls
    - Validates connections before returning
    """
    
    def __init__(self, min_conn: int = 1, max_conn: int = 5, lazy: bool = False):
        """
        Initialize connection pool.
        
        Args:
            min_conn: Minimum connections to maintain
            max_conn: Maximum connections in pool
            lazy: If True, don't create pool until first connection request
        """
        self.pool: Optional[pg_pool.ThreadedConnectionPool] = None
        self.config = self._load_config()
        self.min_conn = min_conn
        self.max_conn = max_conn
        self._initialized = False
        
        logger.info(f"Initializing connection pool (min={min_conn}, max={max_conn}, lazy={lazy})")
        
        if not lazy:
            self._create_pool()
    
    def _load_config(self) -> dict:
        """Load database configuration from environment"""
        import os
        
        config = {
            'host': os.getenv('REDSHIFT_HOST'),
            'port': int(os.getenv('REDSHIFT_PORT', '5439')),
            'database': os.getenv('REDSHIFT_DATABASE'),
            'user': os.getenv('REDSHIFT_USER'),
            'password': os.getenv('REDSHIFT_PASSWORD'),
        }
        
        # Validate config
        missing = [k for k, v in config.items() if v is None]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
        
        return config
    
    def _create_pool(self):
        """Create connection pool with retry logic"""
        if self._initialized:
            return
            
        logger.info("Creating connection pool...")
        
        try:
            self.pool = pg_pool.ThreadedConnectionPool(
                self.min_conn,
                self.max_conn,
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                connect_timeout=10,
                # Redshift-specific settings for connection stability
                sslmode='prefer',
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            self._initialized = True
            logger.info("✅ Connection pool created successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create connection pool: {e}")
            raise
    
    def get_connection(self):
        """
        Get connection from pool with auto-retry.
        
        Handles connection timeouts gracefully.
        
        Returns:
            Database connection
            
        Raises:
            ConnectionError: If all retry attempts fail
        """
        import psycopg2
        
        # Lazy initialization - create pool on first connection request
        if not self._initialized:
            self._create_pool()
        
        for attempt in range(3):
            try:
                conn = self.pool.getconn()
                
                # Test connection is alive with a simple query
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                
                logger.debug(f"✅ Got connection from pool (attempt {attempt + 1})")
                return conn
                
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                logger.warning(f"⚠️ Connection attempt {attempt + 1} failed: {e}")
                
                # If we have a bad connection, try to close it
                try:
                    if 'conn' in locals():
                        self.pool.putconn(conn, close=True)
                except:
                    pass
                
                if attempt == 2:
                    # Final attempt failed
                    raise ConnectionError(f"Failed to get connection after 3 attempts: {e}")
                
                # Exponential backoff
                time.sleep(2 ** attempt)
                
                # On second attempt, recreate entire pool
                if attempt == 1:
                    logger.warning("🔄 Recreating connection pool...")
                    try:
                        self.pool.closeall()
                    except:
                        pass
                    self._create_pool()
            
            except Exception as e:
                logger.error(f"❌ Unexpected error getting connection: {e}")
                raise
        
        raise ConnectionError("Failed to get connection after 3 attempts")
    
    def return_connection(self, conn, close: bool = False):
        """
        Return connection to pool.
        
        Args:
            conn: Database connection to return
            close: If True, close connection instead of returning to pool
        """
        if self.pool and conn:
            try:
                self.pool.putconn(conn, close=close)
                logger.debug(f"Returned connection to pool (closed={close})")
            except Exception as e:
                logger.error(f"Error returning connection: {e}")
    
    def close_all(self):
        """Close all connections in pool"""
        if self.pool:
            logger.info("Closing all connections in pool")
            try:
                self.pool.closeall()
                logger.info("✅ All connections closed")
            except Exception as e:
                logger.error(f"❌ Error closing pool: {e}")
    
    def test_connection(self) -> bool:
        """
        Test if pool can establish a connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Lazy initialization - create pool if not initialized
            if not self._initialized:
                self._create_pool()
            
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT current_database(), current_user, version()")
            result = cursor.fetchone()
            cursor.close()
            self.return_connection(conn)
            
            logger.info(f"✅ Connection test successful: {result[0]} as {result[1]}")
            logger.info(f"   Database version: {result[2][:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False

