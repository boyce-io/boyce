"""
Query Executor for Redshift
Simple, pandas-native interface for running SQL queries.
Designed for data scientists who just want DataFrames back.
"""

import time
from typing import Optional, Dict, Any
import pandas as pd
from core.connection_manager import RedshiftConnectionManager


class QueryExecutor:
    """
    Execute SQL queries and return pandas DataFrames.
    Handles errors gracefully and tracks query metadata.
    """
    
    def __init__(self, connection_manager: RedshiftConnectionManager):
        self.conn_manager = connection_manager
    
    def execute(
        self, 
        sql: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a SQL query and return results with metadata.
        
        Args:
            sql: SQL query string
            params: Optional parameters for parameterized queries
        
        Returns:
            Dict containing:
                - data: pandas DataFrame with results
                - row_count: number of rows returned
                - execution_time: query execution time in seconds
                - success: whether query succeeded
                - error: error message if query failed
        """
        result = {
            "data": None,
            "row_count": 0,
            "execution_time": 0.0,
            "success": False,
            "error": None,
        }
        
        start_time = time.time()
        
        try:
            with self.conn_manager.get_connection() as conn:
                # Execute query and load into DataFrame
                df = pd.read_sql(sql, conn, params=params)
                
                result["data"] = df
                result["row_count"] = len(df)
                result["success"] = True
                
        except Exception as e:
            result["error"] = str(e)
        
        finally:
            result["execution_time"] = time.time() - start_time
        
        return result
    
    def execute_no_result(self, sql: str) -> Dict[str, Any]:
        """
        Execute a SQL statement that doesn't return results (DDL, DML).
        
        Args:
            sql: SQL statement
        
        Returns:
            Dict with success status and execution metadata
        """
        result = {
            "success": False,
            "rows_affected": 0,
            "execution_time": 0.0,
            "error": None,
        }
        
        start_time = time.time()
        
        try:
            with self.conn_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    result["rows_affected"] = cur.rowcount
                    conn.commit()
                    result["success"] = True
        
        except Exception as e:
            result["error"] = str(e)
        
        finally:
            result["execution_time"] = time.time() - start_time
        
        return result
    
    def run_query(self, sql: str) -> pd.DataFrame:
        """
        Simple wrapper that just returns the DataFrame.
        For when you don't care about metadata.
        
        Args:
            sql: SQL query string
        
        Returns:
            pandas DataFrame with query results
        
        Raises:
            Exception if query fails
        """
        result = self.execute(sql)
        
        if not result["success"]:
            raise Exception(f"Query failed: {result['error']}")
        
        return result["data"]

